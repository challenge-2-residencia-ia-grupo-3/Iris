"""grafo_iris.py: protótipo da arquitetura de agentes do Íris escrita em LangGraph.

Analogia: o pipeline de hoje é uma receita lida de cima para baixo. O LangGraph é um fluxograma
que o computador executa: cada caixa (nó) faz um passo, as setas (arestas) dizem para onde ir e uma
ficha (o "estado") passa de caixa em caixa. Algumas setas têm condição (a volta do Auditor ao
Adaptador) e uma caixa pode parar e esperar uma pessoa (a revisão da professora).

O que este arquivo faz:
  * monta o grafo (StateGraph) com estado tipado e um nó por etapa do Íris;
  * cada nó chama a função REAL do grupo (código do dev + arquivos novos dos PRs #81, #74 e #80,
    montados por montar_codigo.py numa pasta fora do clone); nada do grupo é copiado aqui;
  * roda os 3 materiais sintéticos do arnês (M1, M2, M3) e 2 casos que forçam o Auditor a reprovar,
    com o provedor determinístico 'eco' (sem rede, sem modelo);
  * grava pacote/outputs/39-langgraph.json para o painel.

Uso (na VPS):
    PYTHONDONTWRITEBYTECODE=1 nice -n 19 <venv langgraph>/bin/python grafo_iris.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # não gravar __pycache__ (nem aqui nem na cópia do código do grupo)

import argparse
import importlib.util
import json
import operator
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, Callable, Optional, TypedDict

AQUI = Path(__file__).resolve().parent
IRIS_RAG = AQUI.parent.parent
SAIDA_PADRAO = IRIS_RAG / "pacote" / "outputs" / "39-langgraph.json"
MONTADO = Path(os.environ.get("IRIS_MONTADO") or (Path(__file__).resolve().parent / ".montado"))  # cópia montada pelo montar_codigo.py

# Limite de voltas do Auditor ao Adaptador: o grupo decidiu max_retries = 2 (docs/arquitetura.md, ADR-06).
# Duas voltas = até três tentativas do Adaptador, o mesmo que MAX_TENTATIVAS_PADRAO = 3 do auditor.py (PR #74).
LIMITE_VOLTAS = 2
CARACTERISTICA_PADRAO = "sobrecarga_memoria_trabalho_comandos_multiplos"
NIVEL_PADRAO = 2
MAX_QUESTOES = 3


# ---------------------------------------------------------------- código do grupo (montado) e arnês
def _montagem() -> dict:
    """Garante a cópia montada (dev + PRs) e devolve o MONTAGEM.json com os shas usados."""
    arq = MONTADO / "MONTAGEM.json"
    if not arq.exists():
        spec = importlib.util.spec_from_file_location("bancada_montar_codigo", AQUI / "montar_codigo.py")
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mod.montar(MONTADO)
    return json.loads(arq.read_text(encoding="utf-8"))


MONTAGEM = _montagem()
# o arnês (trace.py) põe no sys.path o código que estiver em IRIS_GRUPO: aqui, a cópia montada
os.environ["IRIS_GRUPO"] = str(MONTADO)


def _carregar(nome: str, caminho: Path):
    if nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# rastro_pipeline.py carrega o trace.py e chama preparar_ambiente(); reaproveitamos materiais, perfil e provedor
RP = _carregar("bancada_rastro_pipeline", IRIS_RAG / "bancada" / "pipeline" / "rastro_pipeline.py")
T = RP.T

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.runtime import Runtime  # noqa: E402
from langgraph.types import Command, interrupt  # noqa: E402

# funções do grupo (cópia montada)
from iris.agents.adapter_agent import AdapterAgent  # noqa: E402
from iris.agents.auditor import AgenteAuditor, caracteristicas_nao_selecionadas  # noqa: E402  (PR #74)
from iris.agents.curriculum_extractor import CurriculumExtractorAgent  # noqa: E402
from iris.agents.strategist_agent import StrategistAgent  # noqa: E402  (PR #81)
from iris.api.routes.catalogs import select_surgical_characteristics_service  # noqa: E402
from iris.parsers.document_extractor import extract_text_from_file  # noqa: E402
from iris.parsers.structural_decomposer import decompose_material  # noqa: E402
from iris.schemas.adaptation import AdaptationRequest  # noqa: E402
from iris.schemas.curriculum import CurriculumInvariants  # noqa: E402
from iris.schemas.materials import validate_file_size_limit, validate_material_content  # noqa: E402
from iris.schemas.profile import validar_perfil  # noqa: E402
from iris.schemas.strategy import StrategyRequest  # noqa: E402  (PR #81)
from iris.security.pii_scrubber import sanitize_pii  # noqa: E402


# ---------------------------------------------------------------- o estado (a "ficha" que passa entre os nós)
class EstadoIris(TypedDict, total=False):
    """Estado do grafo. Regra: nenhum campo leva dado pessoal; o texto bruto do arquivo NUNCA entra aqui.

    O arquivo e o texto bruto ficam no Contexto (abaixo), que o LangGraph entrega aos nós mas não salva
    no checkpointer. A descrição de cada campo está em CAMPOS_ESTADO e vai para o JSON do painel.
    """

    material_id: str
    formato: str
    tamanho_bytes: int
    n_caracteres_extraidos: int
    texto_sanitizado: str
    n_pii_removidos: int
    questoes: list[dict]
    caracteristica: str
    nivel: int
    n_caracteristicas_bloqueadas: int
    perfil_codigo: str
    indice_questao: int
    questao_id: Optional[str]
    enunciado: str
    invariantes: dict
    chunk_ids: list[str]
    trechos_fora_do_filtro: list[str]
    diretiva: str
    estrategista_reserva: Optional[str]
    tentativa: int
    minuta: str
    minuta_anterior: Optional[str]
    feedback_auditor: Optional[str]
    escopo_aprovado: bool
    auditoria: dict
    voltas_auditor: int
    rota: str
    texto_proposto: str
    alerta_professora: Optional[str]
    decisao_professora: Optional[str]
    texto_final: str
    resultados: Annotated[list[dict], operator.add]
    caminho: Annotated[list[str], operator.add]
    latencias: Annotated[list[list], operator.add]


CAMPOS_ESTADO: list[dict] = [
    {"campo": "material_id", "tipo": "str", "quem_escreve": "quem chama o grafo", "contem_dado_pessoal": False,
     "observacao": "id sintético do material; em produção, um id aleatório (nunca o nome do arquivo)"},
    {"campo": "formato", "tipo": "str", "quem_escreve": "entrada", "contem_dado_pessoal": False,
     "observacao": "só a extensão (txt, docx, pdf); o nome do arquivo pode ter nome de aluno e fica fora"},
    {"campo": "tamanho_bytes", "tipo": "int", "quem_escreve": "entrada", "contem_dado_pessoal": False, "observacao": None},
    {"campo": "n_caracteres_extraidos", "tipo": "int", "quem_escreve": "extracao_documento", "contem_dado_pessoal": False,
     "observacao": "só a contagem; o texto bruto fica no Contexto, fora do estado e do checkpointer"},
    {"campo": "texto_sanitizado", "tipo": "str", "quem_escreve": "filtro_pii", "contem_dado_pessoal": False,
     "observacao": "texto depois do sanitize_pii do grupo; só é livre de dado pessoal se o filtro pegou tudo "
                   "(no M3 o filtro deixa passar um nome: ver 'pii_no_estado' em cada execução)"},
    {"campo": "n_pii_removidos", "tipo": "int", "quem_escreve": "filtro_pii", "contem_dado_pessoal": False, "observacao": None},
    {"campo": "questoes", "tipo": "list[{id, enunciado}]", "quem_escreve": "decomposicao", "contem_dado_pessoal": False,
     "observacao": "enunciados recortados do texto já sanitizado"},
    {"campo": "caracteristica / nivel", "tipo": "str / int", "quem_escreve": "quem chama o grafo", "contem_dado_pessoal": False,
     "observacao": "escolha da professora (catálogo)"},
    {"campo": "n_caracteristicas_bloqueadas", "tipo": "int", "quem_escreve": "selecao_caracteristica", "contem_dado_pessoal": False, "observacao": None},
    {"campo": "perfil_codigo", "tipo": "str", "quem_escreve": "perfil", "contem_dado_pessoal": False,
     "observacao": "código anônimo do Perfil Pedagógico Portátil (#26); as barreiras observadas não entram no estado"},
    {"campo": "indice_questao / questao_id / enunciado", "tipo": "int / str / str", "quem_escreve": "proxima_questao",
     "contem_dado_pessoal": False, "observacao": "a questão da vez, já sanitizada"},
    {"campo": "invariantes", "tipo": "dict (CurriculumInvariants)", "quem_escreve": "extrator", "contem_dado_pessoal": False,
     "observacao": "conceitos e termos da trava curricular"},
    {"campo": "chunk_ids / trechos_fora_do_filtro", "tipo": "list[str]", "quem_escreve": "busca_rag", "contem_dado_pessoal": False,
     "observacao": "só os ids dos trechos; o texto dos trechos (há licença restrita) fica no Contexto"},
    {"campo": "diretiva / estrategista_reserva", "tipo": "str / str|None", "quem_escreve": "estrategista", "contem_dado_pessoal": False,
     "observacao": "diretiva citada [T1..Tn] ou a de reserva do catálogo, com o motivo"},
    {"campo": "tentativa / minuta / minuta_anterior / escopo_aprovado", "tipo": "int / str / str|None / bool",
     "quem_escreve": "adaptador", "contem_dado_pessoal": False, "observacao": "minuta feita a partir do enunciado sanitizado"},
    {"campo": "auditoria / feedback_auditor", "tipo": "dict / str|None", "quem_escreve": "auditor", "contem_dado_pessoal": False,
     "observacao": "aprovado, TRCC, motivos e a correção pedida ao Adaptador"},
    {"campo": "voltas_auditor / rota", "tipo": "int / str", "quem_escreve": "decisao", "contem_dado_pessoal": False,
     "observacao": "contador do laço e a seta escolhida (aprovado, refazer, limite)"},
    {"campo": "texto_proposto / alerta_professora", "tipo": "str / str|None", "quem_escreve": "decisao ou saida_de_reserva",
     "contem_dado_pessoal": False, "observacao": "o que a professora vai ver"},
    {"campo": "decisao_professora / texto_final", "tipo": "str / str", "quem_escreve": "revisao_professora",
     "contem_dado_pessoal": False, "observacao": "aceitou ou editou; a edição real viria do front (#21, #22)"},
    {"campo": "resultados", "tipo": "list[dict] (acumula)", "quem_escreve": "revisao_professora", "contem_dado_pessoal": False,
     "observacao": "um resumo por questão"},
    {"campo": "caminho / latencias", "tipo": "list (acumula)", "quem_escreve": "todos os nós (embrulho de medição)",
     "contem_dado_pessoal": False, "observacao": "ids dos nós visitados e o tempo de cada um"},
]


@dataclass
class Contexto:
    """O que os nós recebem mas o checkpointer NÃO salva: arquivo, texto bruto, clientes e caches.

    É como a mesa de trabalho: o que está nela some quando a requisição termina. O estado é a ficha que
    fica arquivada a cada passo; por isso dado pessoal fica na mesa e não na ficha.
    """

    nome_arquivo: str = ""
    dados: bytes = b""
    cliente: Any = None
    juiz: Any = None
    disciplina: Optional[str] = None
    ano: Optional[str] = None
    texto_bruto: Optional[str] = None  # apagado pelo filtro_pii logo depois de usado
    buscas: dict = field(default_factory=dict)  # resultado da busca por questão (tem texto de trecho)
    falhar_adaptador_uma_vez: bool = False  # só para a demonstração de "retomar após falha"
    chamadas: dict = field(default_factory=dict)  # quantas vezes cada nó rodou (demonstração)


# ---------------------------------------------------------------- substitutos da bancada (sem modelo)
class JuizEco:
    """Substituto da bancada para o juiz LLM do Auditor: sempre responde 'nada a apontar' em JSON válido.

    As checagens determinísticas do Auditor (TRCC, termos intocáveis, marca de gabarito, cálculo
    resolvido, alternativas eliminadas) são as do grupo e rodam de verdade. Só a parte do modelo é trocada.
    """

    provider_name = "eco"
    model = "juiz-eco-deterministico"

    def __init__(self) -> None:
        self.chamadas = 0

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500, **_: Any) -> str:
        self.chamadas += 1
        return json.dumps({"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []})


class ClienteForcado:
    """Embrulha o cliente 'eco' e estraga a minuta do Adaptador para exercitar o laço do Auditor.

    modo 'uma_vez': acrescenta uma marca de gabarito na 1ª tentativa; quando o pedido traz a correção do
    Auditor (campo feedback_auditor do PR #80), obedece e devolve a minuta limpa.
    modo 'sempre': acrescenta a marca em todas as tentativas, para o laço bater no limite.
    """

    MARCA = "Resposta correta: a) oxigênio"

    def __init__(self, base: Any, modo: str) -> None:
        self.base = base
        self.modo = modo
        self.provider_name = base.provider_name
        self.estragadas = 0

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500,
                 system_prompt: Optional[str] = None, json_mode: bool = False):
        r = self.base.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens,
                               system_prompt=system_prompt, json_mode=json_mode)
        e_adaptador = "Agente Adaptador Pedagógico" in (system_prompt or "")
        corrigindo = "CORREÇÃO PEDIDA PELO AUDITOR" in prompt
        if e_adaptador and (self.modo == "sempre" or not corrigindo):
            import dataclasses

            d = json.loads(r.text)
            d["texto_adaptado"] = d["texto_adaptado"].rstrip() + "\n" + self.MARCA
            r = dataclasses.replace(r, text=json.dumps(d, ensure_ascii=False))  # LLMResponse é imutável
            self.estragadas += 1
        return r


# ---------------------------------------------------------------- embrulho de medição dos nós
def medido(no_id: str) -> Callable:
    """Mede o tempo do nó e acrescenta seu id ao 'caminho' do estado."""

    def deco(fn: Callable) -> Callable:
        # sem functools.wraps: ele faria o LangGraph ler a assinatura (estado, ctx) da função de dentro
        # e deixar de entregar o 'runtime'
        def nó(estado: EstadoIris, runtime: Runtime[Contexto]) -> dict:
            ctx = runtime.context
            ctx.chamadas[no_id] = ctx.chamadas.get(no_id, 0) + 1
            t0 = time.perf_counter()
            saida = fn(estado, ctx) or {}
            s = round(time.perf_counter() - t0, 4)
            idx = saida.get("indice_questao", estado.get("indice_questao", -1))
            return {**saida, "caminho": [no_id], "latencias": [[idx, no_id, s]]}

        nó.__name__ = f"no_{no_id}"
        nó.__doc__ = fn.__doc__
        return nó

    return deco


# ---------------------------------------------------------------- nós da camada do material
@medido("entrada")
def no_entrada(estado: EstadoIris, ctx: Contexto) -> dict:
    tamanho = validate_file_size_limit(ctx.dados)
    return {"formato": Path(ctx.nome_arquivo).suffix.lstrip(".").lower(), "tamanho_bytes": int(tamanho),
            "indice_questao": -1, "voltas_auditor": 0}


@medido("extracao_documento")
def no_extracao(estado: EstadoIris, ctx: Contexto) -> dict:
    texto, _fmt = extract_text_from_file(ctx.nome_arquivo, ctx.dados)
    ctx.texto_bruto = texto  # fica na mesa (Contexto), não na ficha (estado)
    return {"n_caracteres_extraidos": len(texto)}


@medido("filtro_pii")
def no_filtro_pii(estado: EstadoIris, ctx: Contexto) -> dict:
    sanitizado, n = sanitize_pii(ctx.texto_bruto or "")
    ctx.texto_bruto = None  # descarta o bruto assim que filtrado (RNF-02)
    ctx.dados = b""
    return {"texto_sanitizado": sanitizado, "n_pii_removidos": int(n)}


@medido("decomposicao")
def no_decomposicao(estado: EstadoIris, ctx: Contexto) -> dict:
    texto = estado["texto_sanitizado"]
    validate_material_content(texto)
    estrutura = decompose_material(texto)
    questoes = [{"id": q.id, "enunciado": RP.enunciado_da_questao(q)} for q in estrutura.questions]
    if not questoes:  # mesma decisão do arnês: sem questão detectada, o texto inteiro vira uma questão
        questoes = [{"id": "texto_inteiro", "enunciado": texto}]
    return {"questoes": questoes[:MAX_QUESTOES]}


@medido("selecao_caracteristica")
def no_selecao(estado: EstadoIris, ctx: Contexto) -> dict:
    sel = select_surgical_characteristics_service({"selected_ids": [estado["caracteristica"]]}).model_dump()
    return {"n_caracteristicas_bloqueadas": int(sel["blocked_count"])}


@medido("perfil")
def no_perfil(estado: EstadoIris, ctx: Contexto) -> dict:
    dados = dict(RP.PERFIL_SINTETICO)
    dados["barreiras_observadas"] = [{"id_caracteristica": estado["caracteristica"],
                                      "observacao": "Perde etapas quando o enunciado tem vários comandos."}]
    perfil = validar_perfil(dados)
    return {"perfil_codigo": perfil.codigo_anonimo}


# ---------------------------------------------------------------- nós da camada da questão
@medido("proxima_questao")
def no_proxima_questao(estado: EstadoIris, ctx: Contexto) -> dict:
    i = estado.get("indice_questao", -1) + 1
    questoes = estado.get("questoes", [])
    # o contrato dos agentes recusa enunciado com menos de 15 caracteres: pula e registra
    pulados = []
    while i < len(questoes) and len(questoes[i]["enunciado"]) < 15:
        pulados.append({"questao": questoes[i]["id"], "resultado": "erro", "motivo": "enunciado < 15 caracteres"})
        i += 1
    if i >= len(questoes):
        return {"indice_questao": i, "rota": "fim", "resultados": pulados}
    q = questoes[i]
    return {"indice_questao": i, "questao_id": q["id"], "enunciado": q["enunciado"], "rota": "questao",
            "tentativa": 0, "voltas_auditor": 0, "minuta": "", "minuta_anterior": None, "feedback_auditor": None,
            "alerta_professora": None, "decisao_professora": None, "resultados": pulados}


@medido("extrator")
def no_extrator(estado: EstadoIris, ctx: Contexto) -> dict:
    agente = CurriculumExtractorAgent(llm_client=ctx.cliente)  # type: ignore[arg-type]
    res = agente.extract_with_telemetry(estado["enunciado"], disciplina=ctx.disciplina, ano_escolar=ctx.ano,
                                        question_id=estado.get("questao_id"))
    return {"invariantes": res.invariants.model_dump()}


def _pedido_estrategia(estado: EstadoIris) -> StrategyRequest:
    return StrategyRequest(caracteristicas=[estado["caracteristica"]], nivel=estado["nivel"],
                           invariantes=CurriculumInvariants(**estado["invariantes"]),
                           enunciado=estado["enunciado"], metodo="bm25", k=5, question_id=estado.get("questao_id"))


@medido("busca_rag")
def no_busca_rag(estado: EstadoIris, ctx: Contexto) -> dict:
    T.preparar_rag()  # chunks.jsonl congelado da bancada; só bm25 (sem torch nem banco)
    agente = StrategistAgent(llm_client=ctx.cliente)  # type: ignore[arg-type]
    buscas, fora, sem_evidencia = agente._buscar(_pedido_estrategia(estado))  # filtro estrito do PR #81
    ctx.buscas[estado["questao_id"]] = (buscas, fora, sem_evidencia)  # texto dos trechos fica no Contexto
    return {"chunk_ids": [t["chunk_id"] for b in buscas for t in b["trechos_rag"]], "trechos_fora_do_filtro": fora}


@medido("estrategista")
def no_estrategista(estado: EstadoIris, ctx: Contexto) -> dict:
    agente = StrategistAgent(llm_client=ctx.cliente)  # type: ignore[arg-type]
    pronto = ctx.buscas.get(estado["questao_id"])
    if pronto is not None:  # reaproveita a busca do nó anterior (wrapper na instância, sem tocar na classe)
        agente._buscar = lambda req: pronto  # type: ignore[method-assign]
    res = agente.strategize(_pedido_estrategia(estado))
    return {"diretiva": res.diretiva, "estrategista_reserva": res.telemetry.motivo_fallback}


def _pedido_adaptacao(estado: EstadoIris) -> AdaptationRequest:
    return AdaptationRequest(enunciado=estado["enunciado"], id_caracteristica=estado["caracteristica"],
                             nivel=estado["nivel"], invariantes=CurriculumInvariants(**estado["invariantes"]),
                             diretiva_psicopedagogica=estado.get("diretiva") or None,
                             feedback_auditor=estado.get("feedback_auditor"),
                             minuta_anterior=estado.get("minuta_anterior"), question_id=estado.get("questao_id"))


@medido("adaptador")
def no_adaptador(estado: EstadoIris, ctx: Contexto) -> dict:
    if ctx.falhar_adaptador_uma_vez:
        ctx.falhar_adaptador_uma_vez = False
        raise RuntimeError("falha simulada do Adaptador (ex.: o Ollama caiu)")
    tentativa = estado.get("tentativa", 0) + 1
    res = AdapterAgent(llm_client=ctx.cliente).adapt(_pedido_adaptacao(estado), tentativa=tentativa)  # type: ignore[arg-type]
    return {"tentativa": tentativa, "minuta": res.texto_adaptado, "escopo_aprovado": res.escopo.aprovado}


@medido("auditor")
def no_auditor(estado: EstadoIris, ctx: Contexto) -> dict:
    auditor = AgenteAuditor(juiz=ctx.juiz)
    nao_sel = caracteristicas_nao_selecionadas([estado["caracteristica"]])
    r = auditor.auditar(estado["enunciado"], estado["minuta"], CurriculumInvariants(**estado["invariantes"]), nao_sel)
    return {"auditoria": {"aprovado": r.aprovado, "trcc": r.trcc.trcc, "motivos": list(r.motivos),
                          "resolucao_indevida": r.resolucao_indevida},
            "feedback_auditor": None if r.aprovado else r.feedback()}


def fabricar_no_decisao(limite: int) -> Callable:
    @medido("decisao")
    def no_decisao(estado: EstadoIris, ctx: Contexto) -> dict:
        voltas = estado.get("voltas_auditor", 0)
        if estado["auditoria"]["aprovado"]:
            return {"rota": "aprovado", "texto_proposto": estado["minuta"], "alerta_professora": None}
        if voltas < limite:  # volta ao Adaptador levando a correção e a minuta reprovada (PR #80)
            return {"rota": "refazer", "voltas_auditor": voltas + 1, "minuta_anterior": estado["minuta"]}
        return {"rota": "limite"}

    return no_decisao


@medido("saida_de_reserva")
def no_reserva(estado: EstadoIris, ctx: Contexto) -> dict:
    # mesma reserva por regras que o Adaptador usa quando o modelo falha (para outras características,
    # devolve o enunciado original: o único texto garantido)
    texto, _just = AdapterAgent._saida_de_reserva(_pedido_adaptacao(estado))
    motivos = "; ".join(estado["auditoria"]["motivos"])[:300]
    return {"texto_proposto": texto,
            "alerta_professora": f"O Auditor reprovou {estado.get('voltas_auditor', 0) + 1} tentativa(s). Motivos: {motivos}"}


@medido("revisao_professora")
def no_revisao(estado: EstadoIris, ctx: Contexto) -> dict:
    # O grafo PARA aqui. O que vai na pausa é salvo no checkpointer: só texto já sanitizado.
    resposta = interrupt({"questao_id": estado.get("questao_id"), "texto_proposto": estado["texto_proposto"],
                          "alerta": estado.get("alerta_professora")})
    decisao = resposta.get("decisao", "aceitou")
    final = resposta.get("texto_editado") or estado["texto_proposto"]
    resultado = "aprovado" if estado.get("rota") == "aprovado" else "reserva"
    return {"decisao_professora": decisao, "texto_final": final,
            "resultados": [{"questao": estado.get("questao_id"), "resultado": resultado,
                            "voltas_auditor": estado.get("voltas_auditor", 0), "decisao_professora": decisao}]}


# ---------------------------------------------------------------- roteadores (as setas com condição)
def rota_questao(estado: EstadoIris) -> str:
    return "extrator" if estado.get("rota") == "questao" else END


def rota_decisao(estado: EstadoIris) -> str:
    return {"aprovado": "revisao_professora", "refazer": "adaptador", "limite": "saida_de_reserva"}[estado["rota"]]


# ---------------------------------------------------------------- o grafo
def construir_grafo(limite_voltas: int = LIMITE_VOLTAS, checkpointer: Any = None):
    g = StateGraph(EstadoIris, context_schema=Contexto)
    for nome, fn in [("entrada", no_entrada), ("extracao_documento", no_extracao), ("filtro_pii", no_filtro_pii),
                     ("decomposicao", no_decomposicao), ("selecao_caracteristica", no_selecao), ("perfil", no_perfil),
                     ("proxima_questao", no_proxima_questao), ("extrator", no_extrator), ("busca_rag", no_busca_rag),
                     ("estrategista", no_estrategista), ("adaptador", no_adaptador), ("auditor", no_auditor),
                     ("decisao", fabricar_no_decisao(limite_voltas)), ("saida_de_reserva", no_reserva),
                     ("revisao_professora", no_revisao)]:
        g.add_node(nome, fn)
    for a, b in [(START, "entrada"), ("entrada", "extracao_documento"), ("extracao_documento", "filtro_pii"),
                 ("filtro_pii", "decomposicao"), ("decomposicao", "selecao_caracteristica"),
                 ("selecao_caracteristica", "perfil"), ("perfil", "proxima_questao"), ("extrator", "busca_rag"),
                 ("busca_rag", "estrategista"), ("estrategista", "adaptador"), ("adaptador", "auditor"),
                 ("auditor", "decisao"), ("saida_de_reserva", "revisao_professora"),
                 ("revisao_professora", "proxima_questao")]:
        g.add_edge(a, b)
    g.add_conditional_edges("proxima_questao", rota_questao, {"extrator": "extrator", END: END})
    g.add_conditional_edges("decisao", rota_decisao, {"revisao_professora": "revisao_professora",
                                                      "adaptador": "adaptador", "saida_de_reserva": "saida_de_reserva"})
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


# ---------------------------------------------------------------- descrição para o painel
NOS: list[dict] = [
    {"id": "entrada", "nome": "Entrada do arquivo", "o_que_faz": "Confere o tamanho do arquivo enviado pela professora.",
     "funcao_grupo": "iris.schemas.materials:validate_file_size_limit", "origem": "dev", "tipo": "deterministico", "camada": "material"},
    {"id": "extracao_documento", "nome": "Extração do texto", "o_que_faz": "Tira o texto do PDF, DOCX ou TXT; o texto bruto fica fora do estado.",
     "funcao_grupo": "iris.parsers.document_extractor:extract_text_from_file", "origem": "dev", "tipo": "deterministico", "camada": "material"},
    {"id": "filtro_pii", "nome": "Filtro de dados pessoais", "o_que_faz": "Troca nomes, CPF, telefone e escola por marcadores e descarta o texto bruto.",
     "funcao_grupo": "iris.security.pii_scrubber:sanitize_pii", "origem": "dev", "tipo": "deterministico", "camada": "material"},
    {"id": "decomposicao", "nome": "Decomposição em questões", "o_que_faz": "Confere o conteúdo e separa o material em questões.",
     "funcao_grupo": "iris.parsers.structural_decomposer:decompose_material", "origem": "dev", "tipo": "deterministico", "camada": "material"},
    {"id": "selecao_caracteristica", "nome": "Seleção da característica", "o_que_faz": "Valida a característica escolhida pela professora no catálogo.",
     "funcao_grupo": "iris.api.routes.catalogs:select_surgical_characteristics_service", "origem": "dev", "tipo": "deterministico", "camada": "material"},
    {"id": "perfil", "nome": "Perfil pedagógico", "o_que_faz": "Valida o perfil anônimo do aluno (só código e barreiras observadas).",
     "funcao_grupo": "iris.schemas.profile:validar_perfil", "origem": "dev", "tipo": "deterministico", "camada": "material"},
    {"id": "proxima_questao", "nome": "Próxima questão", "o_que_faz": "Pega a próxima questão da lista ou encerra quando acabam (substituto da bancada).",
     "funcao_grupo": None, "origem": "bancada", "tipo": "decisao", "camada": "questao"},
    {"id": "extrator", "nome": "Agente Extrator", "o_que_faz": "Descobre o que a questão avalia (conceitos que não podem sumir).",
     "funcao_grupo": "iris.agents.curriculum_extractor:CurriculumExtractorAgent.extract_with_telemetry", "origem": "dev", "tipo": "agente", "camada": "questao"},
    {"id": "busca_rag", "nome": "Busca na base científica", "o_que_faz": "Busca trechos de pesquisa filtrados pela barreira da característica.",
     "funcao_grupo": "iris.agents.strategist_agent:StrategistAgent._buscar (usa iris.rag.bridge:buscar_por_caracteristica_atomica)",
     "origem": "PR #81", "tipo": "deterministico", "camada": "questao"},
    {"id": "estrategista", "nome": "Agente Estrategista", "o_que_faz": "Transforma os trechos numa orientação de apoio com citação [T1..Tn].",
     "funcao_grupo": "iris.agents.strategist_agent:StrategistAgent.strategize", "origem": "PR #81", "tipo": "agente", "camada": "questao"},
    {"id": "adaptador", "nome": "Agente Adaptador", "o_que_faz": "Reescreve a apresentação da questão; na volta, recebe a correção do Auditor.",
     "funcao_grupo": "iris.agents.adapter_agent:AdapterAgent.adapt", "origem": "PR #80", "tipo": "agente", "camada": "questao"},
    {"id": "auditor", "nome": "Agente Auditor", "o_que_faz": "Confere se a adaptação manteve os conceitos e não entregou a resposta (juiz LLM é substituto da bancada).",
     "funcao_grupo": "iris.agents.auditor:AgenteAuditor.auditar", "origem": "PR #74", "tipo": "agente", "camada": "questao"},
    {"id": "decisao", "nome": "Decisão do laço", "o_que_faz": f"Aprovado segue; reprovado volta ao Adaptador até {LIMITE_VOLTAS} vezes; depois vai para a reserva.",
     "funcao_grupo": None, "origem": "bancada", "tipo": "decisao", "camada": "questao"},
    {"id": "saida_de_reserva", "nome": "Saída de reserva", "o_que_faz": "Entrega a versão por regras (ou o original) com um alerta para a professora.",
     "funcao_grupo": "iris.agents.adapter_agent:AdapterAgent._saida_de_reserva", "origem": "dev", "tipo": "reserva", "camada": "questao"},
    {"id": "revisao_professora", "nome": "Revisão da professora", "o_que_faz": "O grafo para e espera a professora aceitar ou editar (no protótipo, decisão sintética).",
     "funcao_grupo": None, "origem": "bancada", "tipo": "pessoa", "camada": "questao"},
]

ARESTAS: list[dict] = [
    {"de": "entrada", "para": "extracao_documento", "tipo": "normal", "condicao": None},
    {"de": "extracao_documento", "para": "filtro_pii", "tipo": "normal", "condicao": None},
    {"de": "filtro_pii", "para": "decomposicao", "tipo": "normal", "condicao": None},
    {"de": "decomposicao", "para": "selecao_caracteristica", "tipo": "normal", "condicao": None},
    {"de": "selecao_caracteristica", "para": "perfil", "tipo": "normal", "condicao": None},
    {"de": "perfil", "para": "proxima_questao", "tipo": "normal", "condicao": None},
    {"de": "proxima_questao", "para": "extrator", "tipo": "condicional", "condicao": "ainda há questão"},
    {"de": "proxima_questao", "para": "__end__", "tipo": "condicional", "condicao": "acabaram as questões"},
    {"de": "extrator", "para": "busca_rag", "tipo": "normal", "condicao": None},
    {"de": "busca_rag", "para": "estrategista", "tipo": "normal", "condicao": None},
    {"de": "estrategista", "para": "adaptador", "tipo": "normal", "condicao": None},
    {"de": "adaptador", "para": "auditor", "tipo": "normal", "condicao": None},
    {"de": "auditor", "para": "decisao", "tipo": "normal", "condicao": None},
    {"de": "decisao", "para": "revisao_professora", "tipo": "condicional", "condicao": "aprovado"},
    {"de": "decisao", "para": "adaptador", "tipo": "laco", "condicao": f"reprovado e voltas < {LIMITE_VOLTAS}"},
    {"de": "decisao", "para": "saida_de_reserva", "tipo": "condicional", "condicao": f"reprovado e {LIMITE_VOLTAS} voltas feitas"},
    {"de": "saida_de_reserva", "para": "revisao_professora", "tipo": "normal", "condicao": None},
    {"de": "revisao_professora", "para": "proxima_questao", "tipo": "laco", "condicao": "segue para a próxima questão"},
]

CAMINHO_HOJE = ["entrada", "extracao_documento", "filtro_pii", "decomposicao", "selecao_caracteristica", "perfil",
                "extrator", "busca_rag", "adaptador"]

COMPARACAO: list[dict] = [
    {"aspecto": "Laço Auditor-Adaptador",
     "hoje": "No PR #74 o laço é um for dentro de AgenteAuditor.executar_ciclo; o PR #80 liga o Adaptador por CicloComAuditor. Funciona, mas fica escondido dentro de uma função.",
     "com_langgraph": "O laço vira uma seta com condição (decisao -> adaptador) e um contador no estado; o limite de 2 voltas (ADR-06) fica visível no desenho.",
     "custo_ou_risco": "Duas formas do mesmo laço não podem conviver: ao adotar, executar_ciclo deixa de ser chamado pelo pipeline (continua útil em testes)."},
    {"aspecto": "Pausa para a professora",
     "hoje": "Não existe no backend: a revisão (#21, #22) seria outra requisição do front, sem ligação com o que o pipeline já fez.",
     "com_langgraph": "interrupt() para o grafo na revisão e Command(resume=...) continua de onde parou, com o mesmo estado.",
     "custo_ou_risco": "Para pausar entre duas requisições HTTP o estado precisa ficar guardado nesse intervalo: choca com zero retenção (RNF-01/RNF-02). Ver a linha do checkpointer."},
    {"aspecto": "Retomar após falha",
     "hoje": "Se o modelo cai no meio (ex.: Ollama), a requisição falha e tudo recomeça do upload.",
     "com_langgraph": "Com checkpointer, invoke(None) retoma do último passo salvo; no protótipo, o Extrator e a busca não rodaram de novo.",
     "custo_ou_risco": "Só vale enquanto o estado estiver guardado; com MemorySaver por requisição, só dentro da mesma requisição."},
    {"aspecto": "Ver o estado de cada passo",
     "hoje": "Só com print/log ou com o arnês da bancada (wrappers).",
     "com_langgraph": "get_state_history() devolve a ficha completa depois de cada passo, com o próximo nó.",
     "custo_ou_risco": "O histórico guarda o texto da questão e a minuta a cada passo: memória cresce com o material; apagar ao fim (delete_thread)."},
    {"aspecto": "Rastro e observabilidade",
     "hoje": "Telemetria por agente (total_ms, tokens) e resumir_ciclo para o RNF-07.",
     "com_langgraph": "stream(stream_mode='updates') entrega cada passo em tempo real; o caminho e a latência por nó saem de graça.",
     "custo_ou_risco": "O rastreamento pronto do ecossistema é o LangSmith, serviço externo e pago: não usar com material de aluno; manter a telemetria própria."},
    {"aspecto": "Testes",
     "hoje": "Cada agente tem teste unitário com mock do LLM (RNF-12).",
     "com_langgraph": "Os mesmos testes continuam; somam-se testes de fluxo (o laço respeita o limite, o grafo para na revisão, o estado não tem dado pessoal).",
     "custo_ou_risco": "Mais uma camada para testar; os testes de fluxo precisam de provedor determinístico (como o eco)."},
    {"aspecto": "Dependência nova e licença",
     "hoje": "O pyproject do dev não declara langgraph; ele já aparece no uv.lock como dependência indireta (langchain-community -> langchain -> langgraph).",
     "com_langgraph": "Declarar langgraph (licença MIT) direto no pyproject, com versão fixa, via uv (RNF-11).",
     "custo_ou_risco": "Traz langchain-core e langsmith (cliente) junto; a API mudou várias vezes entre versões 0.x e 1.x: fixar versão e ler o changelog antes de subir."},
    {"aspecto": "Curva de aprendizado",
     "hoje": "Python comum: qualquer pessoa do grupo lê a sequência de chamadas.",
     "com_langgraph": "É preciso entender estado, nó, aresta condicional, checkpointer e interrupt.",
     "custo_ou_risco": "Cerca de um dia para o grupo; erro comum é guardar no estado coisa que não devia (texto bruto, objetos grandes)."},
    {"aspecto": "Zero retenção com checkpointer",
     "hoje": "Nada é salvo: a requisição termina e o texto some (RNF-01, RNF-02, #35, #37).",
     "com_langgraph": "O checkpointer salva o estado a cada passo. Solução do protótipo: MemorySaver só durante a requisição, texto bruto fora do estado (no Contexto) e delete_thread ao terminar.",
     "custo_ou_risco": "Checkpointer em banco (SqliteSaver, PostgresSaver) guardaria texto de aluno em disco: proibido pelo RNF-01 sem um estado sem conteúdo (só ids e contagens)."},
]


# ---------------------------------------------------------------- execução
MATERIAIS_FORCADOS: list[dict] = [
    {
        "material_id": "M4-forcado-volta",
        "formato": "txt",
        "disciplina": "Ciências",
        "ano": "6º ano",
        "texto": (
            "Escola Estadual Ficticia do Teste\n"
            "Aluno: Fulano Ficticio da Silva\n"
            "CPF do responsável: 111.111.111-11\n\n"
            "Leia o texto: as plantas usam a luz solar, a água e o gás carbônico para produzir glicose e liberar oxigênio.\n\n"
            "1) Observe o texto e responda: qual gás é liberado na fotossíntese?\n"
            "a) oxigênio\nb) nitrogênio\nc) hélio\n"
        ),
        "pii_plantado": ["Fulano Ficticio da Silva", "111.111.111-11", "Escola Estadual Ficticia do Teste"],
        # característica sem regra de escopo no grupo: o laudo do Adaptador só olha a trava curricular,
        # então a marca de gabarito passa por ele e quem pega é o Auditor
        "caracteristica": "impulsividade_leitura_superficial_negacoes",
        "forcar": "uma_vez",
    },
]
MATERIAIS_FORCADOS.append({**MATERIAIS_FORCADOS[0], "material_id": "M5-forcado-limite", "forcar": "sempre"})


def preparar_contexto(material: dict, cliente: Any) -> Contexto:
    nome, dados = RP.montar_arquivo(material)
    return Contexto(nome_arquivo=nome, dados=dados, cliente=cliente, juiz=JuizEco(),
                    disciplina=material.get("disciplina"), ano=material.get("ano"))


def decisao_sintetica(pausa: dict) -> dict:
    """Decisão da 'professora' no protótipo: aceita o aprovado; edita o que veio com alerta."""
    if pausa.get("alerta"):
        return {"decisao": "editou", "texto_editado": pausa["texto_proposto"].rstrip() + "\n(Revisado pela professora.)"}
    return {"decisao": "aceitou"}


def rodar_material(grafo: Any, material: dict, cliente: Any, thread_id: str, caracteristica: str = CARACTERISTICA_PADRAO,
                   nivel: int = NIVEL_PADRAO, decidir: Callable[[dict], dict] = decisao_sintetica,
                   ctx: Optional[Contexto] = None) -> dict:
    """Roda um material até o fim, retomando cada pausa da professora. Devolve pausas e o estado final."""
    ctx = ctx or preparar_contexto(material, cliente)
    cfg = {"configurable": {"thread_id": thread_id}}
    entrada = {"material_id": material["material_id"], "caracteristica": material.get("caracteristica", caracteristica),
               "nivel": nivel}
    pausas: list[dict] = []
    erro = None
    try:
        saida = grafo.invoke(entrada, cfg, context=ctx)
        while saida.get("__interrupt__"):
            pausa = saida["__interrupt__"][0].value
            parado_em = grafo.get_state(cfg).next
            pausas.append({"questao_id": pausa["questao_id"], "parado_em": list(parado_em), "com_alerta": bool(pausa["alerta"])})
            saida = grafo.invoke(Command(resume=decidir(pausa)), cfg, context=ctx)
    except Exception as exc:  # noqa: BLE001 - registra e devolve
        erro = f"{type(exc).__name__}: {str(exc)[:200]}"
    return {"pausas": pausas, "erro": erro, "config": cfg, "contexto": ctx}


def historico(grafo: Any, cfg: dict) -> list:
    """Estados salvos, do primeiro ao último."""
    return list(reversed(list(grafo.get_state_history(cfg))))


def pii_em(textos: list[str], plantado: list[str]) -> list[str]:
    alvo = "\n".join(textos).casefold()
    return [p for p in plantado if p.casefold() in alvo]


def bytes_do_checkpointer(saver: InMemorySaver, thread_id: str) -> bytes:
    """Tudo o que o MemorySaver guardou para a thread, em bytes (para procurar dado pessoal)."""
    partes: list[bytes] = []

    def coletar(obj: Any) -> None:
        if isinstance(obj, (bytes, bytearray)):
            partes.append(bytes(obj))
        elif isinstance(obj, str):
            partes.append(obj.encode("utf-8", "ignore"))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                coletar(k)
                coletar(v)
        elif isinstance(obj, (list, tuple, set)):
            for v in obj:
                coletar(v)

    coletar(saver.storage.get(thread_id, {}))
    coletar({k: v for k, v in saver.writes.items() if k[0] == thread_id})
    coletar({k: v for k, v in saver.blobs.items() if k[0] == thread_id})
    return b"\n".join(partes)


def resumir_execucoes(grafo: Any, material: dict, rodada: dict, limite: int) -> list[dict]:
    """Uma linha por questão, no formato do contrato do painel."""
    snaps = historico(grafo, rodada["config"])
    final = snaps[-1].values if snaps else {}
    resultados = {r["questao"]: r for r in final.get("resultados", [])}
    pausas = {p["questao_id"]: p for p in rodada["pausas"]}
    plantado = material.get("pii_plantado", [])
    caminho_total, lat_total = final.get("caminho", []), final.get("latencias", [])
    questoes = final.get("questoes", [])
    linhas = []
    for i, q in enumerate(questoes):
        # cada passo foi registrado com o índice da questão da vez; os passos do material (-1) entram na 1ª
        da_questao = [(no, s) for idx, no, s in lat_total if idx == i or (i == 0 and idx == -1)]
        if not da_questao:
            continue
        caminho = [no for no, _ in da_questao]
        lat: dict[str, float] = {}
        for no, s in da_questao:
            lat[no] = round(lat.get(no, 0.0) + s, 4)
        snaps_q = [s for s in snaps if s.values.get("indice_questao", -1) in ((i, -1) if i == 0 else (i,))]
        textos_q = [json.dumps(s.values, ensure_ascii=False, default=str) for s in snaps_q]
        r = resultados.get(q["id"], {})
        linhas.append({
            "material": material["material_id"],
            "questao": q["id"],
            "caminho": caminho,
            "voltas_auditor": int(r.get("voltas_auditor", 0)),
            "limite_voltas": limite,
            "parou_para_professora": q["id"] in pausas,
            "latencia_s": lat,
            "resultado": r.get("resultado", "erro") if not rodada["erro"] else "erro",
            "checkpoints": len(snaps_q),
            "decisao_professora": r.get("decisao_professora"),
            "caracteristica": final.get("caracteristica"),
            "pii_no_estado": pii_em(textos_q, plantado),
            "observacao": ("os passos do material rodaram uma vez e aparecem na 1ª questão" if i == 0 else None),
        })
    if rodada["erro"] and not linhas:
        linhas.append({"material": material["material_id"], "questao": None, "caminho": caminho_total,
                       "voltas_auditor": 0, "limite_voltas": limite, "parou_para_professora": False,
                       "latencia_s": {}, "resultado": "erro", "checkpoints": len(snaps), "erro": rodada["erro"]})
    return linhas


def demonstrar_retomada(cliente: Any) -> dict:
    """Simula a queda do Adaptador e retoma do último checkpoint, sem refazer Extrator nem busca."""
    grafo = construir_grafo()
    m = RP.MATERIAIS[1]
    ctx = preparar_contexto(m, cliente)
    ctx.falhar_adaptador_uma_vez = True
    cfg = {"configurable": {"thread_id": "demo-retomada"}}
    entrada = {"material_id": m["material_id"], "caracteristica": CARACTERISTICA_PADRAO, "nivel": NIVEL_PADRAO}
    falhou_em = None
    try:
        grafo.invoke(entrada, cfg, context=ctx)
    except RuntimeError as exc:
        falhou_em = {"erro": str(exc), "proximo_no_salvo": list(grafo.get_state(cfg).next)}
    antes = dict(ctx.chamadas)
    saida = grafo.invoke(None, cfg, context=ctx)  # retoma do último passo salvo
    while saida.get("__interrupt__"):
        saida = grafo.invoke(Command(resume=decisao_sintetica(saida["__interrupt__"][0].value)), cfg, context=ctx)
    return {"material": m["material_id"], "falhou": falhou_em, "chamadas_antes_de_retomar": antes,
            "chamadas_no_fim": dict(ctx.chamadas),
            "extrator_repetido": ctx.chamadas.get("extrator", 0) > len(saida.get("questoes", [])),
            "observacao": "a retomada partiu do adaptador: extrator, busca e estrategista da 1ª questão não rodaram de novo"}


def executar(saida_json: Path = SAIDA_PADRAO, gravar: bool = True) -> dict:
    import logging

    # os agentes avisam no log quando usam a reserva; aqui isso já vai para o JSON
    logging.getLogger("iris").setLevel(logging.ERROR)
    cliente_eco = T.criar_cliente("eco")
    saver = InMemorySaver()  # só durante esta execução; nada vai para disco
    grafo = construir_grafo(LIMITE_VOLTAS, saver)

    execucoes: list[dict] = []
    retencao: list[dict] = []
    historico_exemplo: list[dict] = []
    for m in [*RP.MATERIAIS, *MATERIAIS_FORCADOS]:
        cliente = ClienteForcado(cliente_eco, m["forcar"]) if m.get("forcar") else cliente_eco
        tid = f"lg-{m['material_id']}"
        rodada = rodar_material(grafo, m, cliente, tid)
        linhas = resumir_execucoes(grafo, m, rodada, LIMITE_VOLTAS)
        execucoes.extend(linhas)
        if m["material_id"] == "M4-forcado-volta":
            for s in historico(grafo, rodada["config"]):
                historico_exemplo.append({"passo": s.metadata.get("step"), "proximo": list(s.next),
                                          "ultimo_no": (s.values.get("caminho") or [None])[-1],
                                          "tentativa": s.values.get("tentativa"), "voltas_auditor": s.values.get("voltas_auditor"),
                                          "auditor_aprovou": (s.values.get("auditoria") or {}).get("aprovado"),
                                          "campos_preenchidos": len(s.values)})
        bruto = bytes_do_checkpointer(saver, tid)
        retencao.append({"material": m["material_id"], "bytes_guardados": len(bruto),
                         "pii_plantado_no_checkpointer": [p for p in m.get("pii_plantado", []) if p.encode() in bruto]})
        saver.delete_thread(tid)  # zero retenção: apaga a ficha ao terminar a requisição
        retencao[-1]["bytes_depois_de_apagar"] = len(bytes_do_checkpointer(saver, tid))
        for l in linhas:
            print(f"{l['material']:<20} {str(l['questao']):<14} {l['resultado']:<9} voltas={l['voltas_auditor']} "
                  f"pausou={l['parou_para_professora']} checkpoints={l['checkpoints']} pii_no_estado={l.get('pii_no_estado')}")
            print("    caminho:", " > ".join(l["caminho"]))

    retomada = demonstrar_retomada(cliente_eco)

    mermaid = grafo.get_graph().draw_mermaid()
    grafo_lg = grafo.get_graph()
    estrutura_lg = {"nos": sorted(grafo_lg.nodes.keys()),
                    "arestas": [{"de": e.source, "para": e.target, "condicional": e.conditional} for e in grafo_lg.edges]}

    sobre = {s["pr"]: s["sha"] for s in MONTAGEM["sobreposto"]}
    limitacoes = [
        "Provedor determinístico 'eco': o Extrator e o Adaptador devolvem respostas por regras no formato pedido; mostra o fluxo, não a qualidade.",
        "O Estrategista (PR #81) recebe do 'eco' um texto que não é JSON e cai na diretiva de reserva do catálogo (motivo falha_llm): o caminho com modelo dele não foi exercitado.",
        "O juiz LLM do Auditor (PR #74) foi trocado por um substituto da bancada que nunca acusa nada; as checagens determinísticas do Auditor (TRCC, termos intocáveis, gabarito, cálculo, alternativas) são as do grupo.",
        "A reprovação foi forçada: um embrulho do cliente acrescenta 'Resposta correta: a) oxigênio' à minuta do Adaptador. Usou a característica de impulsividade porque, na de comandos múltiplos, o próprio laudo de escopo do Adaptador já barra a marca e usa a reserva.",
        "No laço, AgenteAuditor.executar_ciclo e CicloComAuditor (PR #80) não são chamados: o laço deles virou a aresta decisao -> adaptador; as peças chamadas (adapt e auditar) são as mesmas.",
        "A revisão da professora é sintética: aceita o aprovado e 'edita' o que vem com alerta. Não há front (#21, #22).",
        "A pausa e a retomada acontecem dentro do mesmo processo; numa API real, a pausa atravessa duas requisições e o estado teria de ficar guardado nesse meio-tempo.",
        "Os __init__.py de agents e schemas ficaram como no dev (os PRs #80 e #81 mudam o mesmo arquivo de jeitos diferentes); os módulos novos são importados pelo caminho completo.",
        "A busca usa só bm25 sobre o chunks.jsonl congelado da bancada (sem embeddings, sem banco).",
        "O estado só fica livre de dado pessoal se o filtro do grupo pegar tudo: no M3 o sanitize_pii deixa passar o nome 'Ciclana Exemplo Falso' e ele entra no estado (achado já registrado nas saídas 26 e 35).",
        "As latências medem o encanamento numa VPS sem GPU; não dizem nada sobre o RNF-07 com modelo de verdade.",
    ] + MONTAGEM.get("limitacoes", [])

    dados = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versao_langgraph": version("langgraph"),
        "provedor": "eco",
        "aviso": "Provedor determinístico (sem rede e sem modelo): mostra o fluxo, não a qualidade das adaptações.",
        "codigo_montado": {
            "dev": MONTAGEM["dev"],
            "estrategista": f"PR #81 {sobre['PR #81']}" if "PR #81" in sobre else None,
            "auditor": f"PR #74 {sobre['PR #74']}" if "PR #74" in sobre else None,
            "observacao": ("Cópia do dev numa pasta fora do clone, com os arquivos novos do PR #81 (strategist_agent.py, "
                           "schemas/strategy.py), do PR #74 (agents/auditor.py) e a versão do PR #80 de adapter_agent.py e "
                           f"schemas/adaptation.py (feedback do Auditor; sha {sobre.get('PR #80')}); o dev não mexeu nesses "
                           "dois arquivos desde a base do PR, então não houve conflito. O clone do grupo não foi alterado."),
            "arquivos": MONTAGEM["sobreposto"],
            "deixados_de_fora": MONTAGEM["deixados_de_fora"],
        },
        "nos": NOS,
        "arestas": ARESTAS,
        "estado": CAMPOS_ESTADO,
        "mermaid": mermaid,
        "estrutura_langgraph": estrutura_lg,
        "execucoes": execucoes,
        "historico_exemplo": {"material": "M4-forcado-volta",
                              "explicacao": "get_state_history(): uma linha por estado salvo, do primeiro ao último",
                              "passos": historico_exemplo},
        "demonstracoes": {"retomar_apos_falha": retomada, "retencao_checkpointer": retencao},
        "hoje": {"caminho": CAMINHO_HOJE,
                 "observacao": ("No dev (65e1f09) a API faz só entrada, extração, filtro e decomposição; os agentes ainda não "
                                "são chamados por nenhuma rota. A sequência acima é a que o arnês da bancada chama, em Python "
                                "corrido. Não há Estrategista (PR #81), Auditor (PR #74), laço nem pausa para a professora.")},
        "comparacao": COMPARACAO,
        "limitacoes": limitacoes,
    }
    if gravar:
        T.escrever_json(saida_json, dados)
        print(f"\ngravado: {saida_json}")
    return dados


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", default=str(SAIDA_PADRAO))
    ap.add_argument("--mermaid", action="store_true", help="só imprime o desenho do grafo em Mermaid")
    a = ap.parse_args(argv)
    if a.mermaid:
        print(construir_grafo().get_graph().draw_mermaid())
        return
    executar(Path(a.saida))


if __name__ == "__main__":
    main()
