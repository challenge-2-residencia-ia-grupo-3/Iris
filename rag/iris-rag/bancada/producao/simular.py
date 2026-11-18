"""simular.py: gera um log SINTÉTICO de produção e agrega em pacote/outputs/37-producao.json.

Analogia: é a maquete de um prédio antes de existir o prédio. Os números são inventados (com semente
fixa), mas o formato é exatamente o que o RegistradorProducao gravaria. Serve para o painel já ter a forma
da tela "o que as professoras fazem com as adaptações".

NADA AQUI É DADO REAL. Todo registro sai com "sintetico": true e o JSON de saída diz isso no topo.

Além da maquete, este script roda exercitar.py: o registrador ligado no código REAL do grupo (provedor
'eco', determinístico) para conferir que nenhum dado pessoal nem trecho do material chega ao rastro.

Uso:
    python simular.py                 # ~200 adaptações sintéticas + conferência no código do grupo
    python simular.py --sem-pipeline  # só a parte sintética (não importa o código do grupo)
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import rastro_producao as RP  # noqa: E402

IRIS_RAG = AQUI.parent.parent
SAIDA = IRIS_RAG / "pacote" / "outputs" / "37-producao.json"
LOG_SINTETICO = IRIS_RAG / "pacote" / "reports" / "producao" / "eventos-sintetico.jsonl"  # fora do git
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("onde", Path(__file__).resolve().parents[1] / "onde.py")
_onde = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_onde)
GRUPO = _onde.grupo()
SEMENTE = 20261112
N_ADAPTACOES_ALVO = 200

# Parâmetros INVENTADOS para a maquete ficar plausível (não vêm de medição nenhuma).
# chance de aceitar sem editar, editar, recusar, por característica (o resto vira 'sem_retorno')
PERFIL_CARAC = {
    "sobrecarga_memoria_trabalho_comandos_multiplos": (0.45, 0.35, 0.12),
    "retencao_dados_intermediarios_problemas_multietapas": (0.35, 0.40, 0.17),
    "atencao_sustentada_textos_longos": (0.30, 0.42, 0.20),
    "distratibilidade_poluicao_visual_layout": (0.40, 0.35, 0.15),
    "impulsividade_leitura_superficial_negacoes": (0.38, 0.38, 0.16),
    "organizacao_sequencial_expressao_escrita": (0.28, 0.45, 0.19),
    "fadiga_executiva_autorregulacao_provas_extensas": (0.33, 0.37, 0.22),
    "flexibilidade_cognitiva_alternancia_topicos": (0.30, 0.40, 0.20),
    "bloqueio_iniciacao_tarefas_abertas": (0.36, 0.40, 0.16),
    "ritmo_processamento_pressao_temporal": (0.42, 0.33, 0.15),
}
PESO_CARAC = [30, 14, 22, 10, 12, 8, 9, 5, 6, 8]  # a 1ª é a única com regra de escopo própria no grupo
MOTIVOS_PESO = {"mudou_o_que_a_questao_avalia": 4, "andaime_nao_ajuda_esta_caracteristica": 5,
                "linguagem_infantilizada": 3, "formatacao_quebrada": 3, "erro_de_conteudo": 2,
                "demorou_demais": 1, "outro": 2}
# latência inventada por etapa (mediana em ms, espalhamento lognormal)
LAT = {"filtro_pii": (4, 0.4), "validacao_conteudo": (1, 0.3), "decomposicao_estrutural": (25, 0.5),
       "extrator_curricular": (2500, 0.6), "busca_rag": (180, 0.4), "agente_adaptador": (6000, 0.6),
       "laudo_isolamento_escopo": (6, 0.3), "saida_de_reserva": (3, 0.3)}


def commit_grupo() -> str:
    try:
        return subprocess.run(["git", "-C", str(GRUPO), "rev-parse", "--short=7", "HEAD"], capture_output=True,
                              text=True, timeout=20).stdout.strip() or "desconhecido"
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"


def _ms(rnd: random.Random, etapa: str, fator: float = 1.0) -> float:
    med, sig = LAT[etapa]
    return round(med * fator * rnd.lognormvariate(0, sig), 1)


def gerar(semente: int = SEMENTE, alvo: int = N_ADAPTACOES_ALVO) -> list[dict]:
    """Gera os eventos passando PELO registrador (o mesmo esquema/validação de produção)."""
    rnd = random.Random(semente)
    inicio = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
    relogio_atual = {"t": inicio}
    caracs = list(PERFIL_CARAC)
    with tempfile.TemporaryDirectory() as tmp:
        reg = RP.RegistradorProducao(modo="eventos", pasta=tmp, retencao_dias=90, estrito=True, sintetico=True,
                                     relogio=lambda: relogio_atual["t"])
        n_adapt = 0
        k = 0
        while n_adapt < alvo:
            k += 1
            # horário escolar, 30 dias
            relogio_atual["t"] = inicio + timedelta(days=rnd.randrange(30), hours=rnd.randrange(12),
                                                    minutes=rnd.randrange(60))
            carac = rnd.choices(caracs, PESO_CARAC)[0]
            nivel = rnd.choices((1, 2, 3), (3, 5, 2))[0]
            n_q = min(rnd.choice((1, 2, 3, 3, 4, 5, 5, 6, 8)), alvo - n_adapt)
            material_falso = f"material sintetico numero {k} semente {semente}"  # nunca texto de verdade
            prov_ok = rnd.random() > 0.08  # 8% das requisições com o modelo fora do ar -> reserva
            with reg.requisicao(material_falso, formato=rnd.choices(RP.FORMATOS, (3, 1, 4, 4))[0]) as req:
                for e in ("filtro_pii", "validacao_conteudo", "decomposicao_estrutural"):
                    req.etapas.append({"etapa": e, "ms": _ms(rnd, e), "status": "ok"})
                req.definir(n_questoes=n_q, n_pii_substituidos=rnd.choices((0, 1, 2, 3), (6, 2, 1, 1))[0])
                req.campos["faixa_tamanho"] = rnd.choices(RP.FAIXAS_TAMANHO, (2, 5, 3, 1))[0]
                for ordem in range(1, n_q + 1):
                    with req.questao(ordem, carac, nivel) as q:
                        fator = 0.5 if nivel == 1 else 1.0
                        for e in ("extrator_curricular", "busca_rag", "agente_adaptador", "laudo_isolamento_escopo"):
                            q.etapas.append({"etapa": e, "ms": _ms(rnd, e, fator if e == "agente_adaptador" else 1),
                                             "status": "ok"})
                        escopo_ok = rnd.random() > (0.10 if carac == caracs[0] else 0.04)
                        if not prov_ok:
                            reserva, motivo, erro = True, "falha_llm", rnd.choice(("ReadTimeout", "ConnectError"))
                        elif not escopo_ok:
                            reserva, motivo, erro = True, "escopo_reprovado", None
                        else:
                            reserva, motivo, erro = False, "nenhum", None
                        if reserva:
                            q.etapas.append({"etapa": "saida_de_reserva", "ms": _ms(rnd, "saida_de_reserva"),
                                             "status": "ok"})
                        total_ms = sum(x["ms"] for x in q.etapas)
                        te, ts = int(rnd.gauss(900, 150)), int(rnd.gauss(220, 60))
                        q.definir(provedor="ollama", modelo="llama3:latest", tokens_entrada=max(te, 50),
                                  tokens_saida=max(ts, 10), usou_reserva=reserva, motivo_reserva=motivo,
                                  escopo_aprovado=True if reserva else escopo_ok,
                                  violacoes=[] if escopo_ok else [rnd.choice(("palavra_fora_vocabulario",
                                                                               "conceito_ausente",
                                                                               "ordem_alterada"))],
                                  trava_recall=round(min(1.0, rnd.betavariate(9, 1.2)), 3),
                                  dentro_limite_rnf07=total_ms <= (15_000 if nivel == 1 else 40_000),
                                  erro_codigo=erro)
                    n_adapt += 1
            # retorno da professora por questão (chega depois, pelo navegador)
            pa, pe, pr = PERFIL_CARAC[carac]
            if reserva_requisicao := (not prov_ok):
                pa, pe, pr = pa * 0.6, pe * 1.1, pr * 1.8  # reserva (só negrito/etapas) agrada menos
            if nivel == 3:
                pe += 0.05
            for _ in range(n_q):
                relogio_atual["t"] += timedelta(minutes=rnd.randrange(1, 15))
                u = rnd.random()
                decisao = "aceitou" if u < pa else "editou" if u < pa + pe else "recusou" if u < pa + pe + pr \
                    else "sem_retorno"
                pct = None
                if decisao == "editou":
                    pct = min(100, 5 * round(rnd.betavariate(1.6, 6 if nivel < 3 else 4) * 100 / 5))
                    pct = max(pct, 5)
                motivo = rnd.choices(list(MOTIVOS_PESO), list(MOTIVOS_PESO.values()))[0] if decisao == "recusou" \
                    else None
                reg.retorno(caracteristica=carac, nivel=nivel, decisao=decisao, pct_alterado=pct,
                            motivo_recusa=motivo, usou_reserva=reserva_requisicao,
                            segundos_ate_decisao=10 * rnd.randrange(3, 60), id_requisicao=req.id)
        eventos = [json.loads(l) for f in sorted(Path(tmp).glob("eventos-*.jsonl"))
                   for l in f.read_text(encoding="utf-8").splitlines() if l]
    return eventos


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--sem-pipeline", action="store_true", help="não roda a conferência no código do grupo")
    ap.add_argument("--saida", default=str(SAIDA))
    a = ap.parse_args(argv)

    eventos = gerar()
    assert all(e.get("sintetico") is True for e in eventos), "todo evento sintético precisa da marca"
    LOG_SINTETICO.parent.mkdir(parents=True, exist_ok=True)
    LOG_SINTETICO.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eventos), encoding="utf-8")
    agregado = RP.agregar(eventos, k_min=5)

    conferencia = None
    if not a.sem_pipeline:
        import exercitar

        r = exercitar.rodar()
        r.pop("_memoria", None)
        r.pop("agregado", None)
        conferencia = r

    saida = {
        "titulo": "Rastro de produção: o que as professoras fazem com as adaptações",
        "SINTETICO": True,
        "aviso_sintetico": ("Dados sintéticos: números inventados com semente fixa para mostrar como a tela ficaria. "
                            "Não medem uso real."),
        "semente": SEMENTE,
        "commit_grupo": commit_grupo(),
        "data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versao_esquema": RP.VERSAO_ESQUEMA,
        "proposta": "bancada/producao/PROPOSTA.md",
        "listas_fechadas": {"decisoes": list(RP.DECISOES), "motivos_recusa": list(RP.MOTIVOS_RECUSA),
                            "motivos_reserva": list(RP.MOTIVOS_RESERVA), "etapas": list(RP.ETAPAS)},
        "n_eventos": len(eventos),
        "metricas": agregado,
        "conferencia_no_codigo_do_grupo": conferencia,
        "aviso": "provedor determinístico: mede o encanamento, não a qualidade de um modelo"
                 if conferencia else None,
    }
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    g = agregado["geral"]
    print(f"sintético: {agregado['n_adaptacoes']} adaptações, {agregado['n_requisicoes']} requisições, "
          f"{agregado['n_retornos']} retornos")
    print(f"aceite (com ou sem edição): {g['aceite_com_ou_sem_edicao']}")
    if conferencia:
        print(f"conferência no código do grupo: {conferencia['registros_aceitos']} registros, "
              f"PII vazado={conferencia['pii_vazado_no_rastro']}, trigramas do material="
              f"{conferencia['trigramas_do_material_no_rastro']}, tentativas recusadas="
              f"{conferencia['tentativas_recusadas']}/{conferencia['tentativas_total']}")
    print(f"gravado: {a.saida}")
    return saida


if __name__ == "__main__":
    main()
