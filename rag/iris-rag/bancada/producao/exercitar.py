"""exercitar.py: liga o RegistradorProducao no código REAL do grupo, sem editar o código do grupo.

Analogia: é colocar um cronômetro e uma prancheta ao lado da linha de montagem, sem mexer nas máquinas.
As funções do grupo (filtro de PII, decomposição, Extrator, busca RAG, Adaptador, laudo de escopo e
saída de reserva) são chamadas de dentro dos contextos do registrador; as que são chamadas por dentro de
outras (laudo e reserva, chamados pelo Adaptador) são envolvidas em tempo de execução e desfeitas no fim.

Provedor: só o 'eco' do trace.py (determinístico, sem rede).
Provedor determinístico: mede o encanamento, não a qualidade de um modelo.

O que este arquivo confere de verdade:
  * o registrador aceita os metadados que o pipeline real produz (nenhum registro descartado);
  * nenhum dado pessoal plantado nos materiais sintéticos aparece no que foi aceito;
  * nenhuma sequência de 3 palavras do material aparece no que foi aceito;
  * tentativas deliberadas de gravar o enunciado, o texto adaptado ou um nome são recusadas.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import rastro_producao as RP  # noqa: E402


def _carregar(nome: str, caminho: Path):
    if nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _modulos():
    pipe = AQUI.parent / "pipeline"
    T = _carregar("bancada_trace", pipe / "trace.py")
    RPIPE = _carregar("bancada_rastro_pipeline", pipe / "rastro_pipeline.py")
    return T, RPIPE


# ---------------------------------------------------------------- envoltórios em tempo de execução
class _Atual:
    questao: Any = None  # _Questao aberta (para os envoltórios saberem onde cronometrar)


def _instalar_envoltorios() -> list:
    import iris.agents.adapter_agent as aa

    desfazer = []
    original_escopo = aa.verificar_escopo

    def escopo(*a, **k):
        q = _Atual.questao
        if q is None:
            return original_escopo(*a, **k)
        with q.etapa("laudo_isolamento_escopo"):
            return original_escopo(*a, **k)

    aa.verificar_escopo = escopo
    desfazer.append(lambda: setattr(aa, "verificar_escopo", original_escopo))

    original_reserva = aa.AdapterAgent.__dict__["_saida_de_reserva"]
    fn = original_reserva.__func__

    def reserva(req):
        q = _Atual.questao
        if q is None:
            return fn(req)
        with q.etapa("saida_de_reserva"):
            return fn(req)

    aa.AdapterAgent._saida_de_reserva = staticmethod(reserva)
    desfazer.append(lambda: setattr(aa.AdapterAgent, "_saida_de_reserva", original_reserva))
    return desfazer


# ---------------------------------------------------------------- uma requisição real
def adaptar_material(reg: RP.RegistradorProducao, material: dict, cliente, caracteristica: str, nivel: int,
                     T, RPIPE, max_questoes: int = 3) -> list[dict]:
    """Roda o material pelo código do grupo e devolve, SÓ EM MEMÓRIA, os textos adaptados (para o retorno)."""
    from iris.agents.adapter_agent import AdapterAgent
    from iris.agents.curriculum_extractor import CurriculumExtractorAgent
    from iris.parsers.structural_decomposer import decompose_material
    from iris.rag import bridge
    from iris.schemas.adaptation import AdaptationRequest
    from iris.schemas.materials import validate_material_content
    from iris.security.pii_scrubber import sanitize_pii

    texto = material["texto"]
    saidas: list[dict] = []
    with reg.requisicao(texto, formato="texto") as req:
        with req.etapa("filtro_pii"):
            sanitizado, n_pii = sanitize_pii(texto)
        req.definir(n_pii_substituidos=n_pii)
        with req.etapa("validacao_conteudo"):
            validate_material_content(sanitizado)
        with req.etapa("decomposicao_estrutural"):
            estrutura = decompose_material(sanitizado)
        questoes = [RPIPE.enunciado_da_questao(q) for q in estrutura.questions] or [sanitizado]
        req.definir(n_questoes=len(estrutura.questions))
        for ordem, enunciado in enumerate(questoes[:max_questoes], start=1):
            if len(enunciado) < 15:
                continue
            with req.questao(ordem, caracteristica, nivel) as q:
                _Atual.questao = q
                try:
                    tok = {"e": 0, "s": 0}
                    with q.etapa("extrator_curricular"):
                        res = CurriculumExtractorAgent(llm_client=cliente).extract_with_telemetry(  # type: ignore[arg-type]
                            enunciado, disciplina=material.get("disciplina"), ano_escolar=material.get("ano"))
                    tok["e"] += res.telemetry.prompt_tokens
                    tok["s"] += res.telemetry.completion_tokens
                    with q.etapa("busca_rag"):
                        bridge.buscar_por_caracteristica_atomica(caracteristica, nivel=nivel,
                                                                 pergunta_adicional=enunciado, metodo="bm25", k=5)
                    # agente_estrategista não existe no commit do grupo: não é cronometrado
                    pedido = AdaptationRequest(enunciado=enunciado, id_caracteristica=caracteristica, nivel=nivel,
                                               invariantes=res.invariants)
                    with q.etapa("agente_adaptador"):
                        resultado = AdapterAgent(llm_client=cliente).adapt(pedido)  # type: ignore[arg-type]
                    tel = resultado.telemetry
                    tok["e"] += tel.prompt_tokens
                    tok["s"] += tel.completion_tokens
                    erro = None
                    if tel.motivo_fallback and tel.motivo_fallback.startswith("falha_llm:"):
                        erro = RP.codigo_erro(tel.motivo_fallback.split(":", 1)[1])
                    q.definir(
                        provedor=RP.PROVEDORES[3] if cliente.provider_name == "eco" else "outro",
                        modelo=T.nome_modelo(cliente),
                        tokens_entrada=int(tok["e"]), tokens_saida=int(tok["s"]),
                        usou_reserva=bool(tel.used_fallback),
                        motivo_reserva=RP.motivo_reserva(tel.motivo_fallback),
                        escopo_aprovado=bool(resultado.escopo.aprovado),
                        violacoes=sorted({RP.categoria_violacao(v) for v in resultado.escopo.violacoes}),
                        trava_recall=res.telemetry.trava_recall,
                        dentro_limite_rnf07=bool(tel.dentro_do_limite),
                        erro_codigo=erro,
                    )
                    saidas.append({"ordem": ordem, "original": enunciado, "adaptado": resultado.texto_adaptado,
                                   "usou_reserva": bool(tel.used_fallback)})
                finally:
                    _Atual.questao = None
    return saidas


def _edicao_sintetica(texto: str, i: int) -> str:
    """Simula a professora editando a minuta (determinístico): troca 'Passo' por 'Etapa' e corta o fim."""
    t = texto.replace("**Passo", "**Etapa")
    return t[: max(15, int(len(t) * (0.9 - 0.1 * (i % 3))))]


def _ngramas(texto: str, n: int = 3) -> set[str]:
    p = re.findall(r"\w+", texto.casefold())
    return {" ".join(p[i:i + n]) for i in range(len(p) - n + 1)}


def rodar(caracteristica: str = "sobrecarga_memoria_trabalho_comandos_multiplos") -> dict:
    T, RPIPE = _modulos()
    T.preparar_ambiente()
    T.preparar_rag()
    cliente = T.criar_cliente("eco")
    desfazer = [T.instalar_cliente_nos_agentes(cliente), *_instalar_envoltorios()]
    reg = RP.RegistradorProducao(modo="desligado", estrito=False, sintetico=True)  # nada vai para disco
    textos_material, pii_plantado, retornos = [], [], 0
    try:
        for i, mat in enumerate(RPIPE.MATERIAIS):
            mat = RPIPE.expandir_texto(mat)
            textos_material.append(mat["texto"])
            pii_plantado += mat.get("pii_plantado", [])
            for nivel in (1, 2, 3):
                saidas = adaptar_material(reg, mat, cliente, caracteristica, nivel, T, RPIPE)
                for j, s in enumerate(saidas):
                    # retorno sintético da professora; o % é calculado aqui, em memória, e só o número vai ao log
                    decisao = ("aceitou", "editou", "recusou")[(i + j + nivel) % 3]
                    final = _edicao_sintetica(s["adaptado"], j) if decisao == "editou" else s["adaptado"]
                    reg.retorno(caracteristica=caracteristica, nivel=nivel, decisao=decisao,
                                pct_alterado=RP.pct_alterado(s["adaptado"], final),
                                motivo_recusa="formatacao_quebrada" if decisao == "recusou" else None,
                                usou_reserva=s["usou_reserva"], segundos_ate_decisao=60)
                    retornos += 1
    finally:
        for d in reversed(desfazer):
            d()

    # ---- auditoria do que foi aceito
    aceito = json.dumps(reg.memoria, ensure_ascii=False).casefold()
    pii_vazado = [p for p in pii_plantado if p.casefold() in aceito]
    ngramas_material = set().union(*(_ngramas(t) for t in textos_material))
    ngramas_vazados = sorted(ngramas_material & _ngramas(aceito.replace("_", " ")))

    # ---- tentativas deliberadas de vazar (devem ser recusadas)
    tentativas = {
        "enunciado_em_campo_novo": {"enunciado": RPIPE.MATERIAIS[0]["texto"][:200]},
        "texto_adaptado_em_campo_novo": {"texto_adaptado": "**Leia** o texto e explique"},
        "nome_em_erro_codigo": {"erro_codigo": "Fulana Ficticia Teste"},
        "nome_colado_em_erro_codigo": {"erro_codigo": "FulanaFicticiaError"},
        "nome_colado_em_modelo": {"modelo": "fulana-ficticia-teste"},
        "cpf_em_modelo": {"modelo": "111.111.111-11"},
        "palavra_do_material_em_erro_codigo": {"erro_codigo": "CLOROPLASTOS_ERRO"},
        "motivo_recusa_texto_livre": {"motivo_recusa": "a professora achou ruim"},
    }
    sentinela = RP.palavras_sentinela(RPIPE.MATERIAIS[0]["texto"])
    resultado_tentativas = {}
    for nome, extra in tentativas.items():
        base = {"tipo": "retorno" if "motivo_recusa" in extra else "adaptacao", "versao_esquema": 1,
                "dia": "2026-11-12", "caracteristica": caracteristica, "nivel": 2, "decisao": "recusou"}
        if base["tipo"] == "adaptacao":
            base.pop("decisao")
        try:
            RP.validar_registro(base | extra, sentinela=sentinela, estrito=True)
            resultado_tentativas[nome] = "ACEITO (falha)"
        except RP.CampoRecusado as e:
            resultado_tentativas[nome] = f"recusado: {e.motivo}"

    from collections import Counter

    return {
        "provedor": "eco",
        "aviso": "provedor determinístico: mede o encanamento, não a qualidade de um modelo",
        "materiais": len(RPIPE.MATERIAIS),
        "niveis": [1, 2, 3],
        "registros_aceitos": len(reg.memoria),
        "registros_por_tipo": dict(Counter(r["tipo"] for r in reg.memoria)),
        "campos_recusados_no_fluxo_real": reg.recusas,
        "pii_plantado": len(pii_plantado),
        "pii_vazado_no_rastro": len(pii_vazado),
        "trigramas_do_material_no_rastro": len(ngramas_vazados),
        "tentativas_de_vazamento": resultado_tentativas,
        "tentativas_recusadas": sum(v.startswith("recusado") for v in resultado_tentativas.values()),
        "tentativas_total": len(resultado_tentativas),
        "agregado": RP.agregar(reg.memoria, k_min=1),
        "_memoria": reg.memoria,  # removido antes de gravar no output (fica só no relatório local)
    }


if __name__ == "__main__":
    r = rodar()
    r.pop("_memoria")
    r.pop("agregado")
    print(json.dumps(r, ensure_ascii=False, indent=1))
