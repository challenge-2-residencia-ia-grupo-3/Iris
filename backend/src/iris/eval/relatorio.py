"""Relatório de validação automática do benchmark (Semana 3): LLM puro x Íris.

Lê ``reports/saidas/<sistema>.jsonl`` (iris.eval.executar) e, se existir,
``<sistema>.faithfulness.json`` (iris.eval.faithfulness). Não chama LLM nem o pipeline.

Critérios (RNF-04/05/06):
  * completude: todas as questões do benchmark têm saída sem erro;
  * TRCC >= 95% (leitura micro: conceitos retidos / conceitos esperados; obrigatório);
  * TRCC >= 95% em cada questão (leitura mais rígida; informativo até a equipe decidir);
  * Faithfulness (RAGAS) >= 0,90 (obrigatório; "nao_medido" sem as notas do juiz);
  * hipótese informativa: o LLM puro retém menos conteúdo que a Íris (TRCC < 80%).

Veredito: REPROVADO (algum critério obrigatório falhou) > INCOMPLETO (falta saída ou medida)
> PRELIMINAR (passou, mas o benchmark ainda é rascunho) > APROVADO.

Uso:
    uv run python -m iris.eval.relatorio --alvo iris --referencia llm_puro
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.executar import SAIDAS_PADRAO, ler_saidas
from iris.eval.faithfulness import FAITHFULNESS_MIN, ler_faithfulness
from iris.eval.readability import analyze_question
from iris.eval.trcc import LIMIAR_PADRAO, agregar, avaliar_trcc

HIPOTESE_LLM_PURO_MAX = 0.80
RELATORIO_PADRAO = Path("reports")


def _media(valores) -> float | None:
    v = [x for x in valores if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return round(sum(v) / len(v), 4) if v else None


def metricas_sistema(
    questoes: list[GoldenQuestion], saidas: dict[str, dict], limiar: float = LIMIAR_PADRAO
) -> dict:
    """Métricas de um sistema sobre as questões que têm saída válida."""
    validas = {
        q.id: saidas[q.id]["adaptado"]
        for q in questoes
        if q.id in saidas and not saidas[q.id].get("erro") and saidas[q.id].get("adaptado")
    }
    com_erro = sorted(q.id for q in questoes if q.id in saidas and q.id not in validas)
    sem_saida = sorted(q.id for q in questoes if q.id not in saidas)
    usadas = [q for q in questoes if q.id in validas]

    resultados = {q.id: avaliar_trcc(q.trava_curricular, validas[q.id]) for q in usadas}
    trcc = agregar(resultados, limiar) if resultados else None

    antes = [analyze_question(q.id, q.enunciado) for q in usadas]
    depois = [analyze_question(q.id, validas[q.id]) for q in usadas]
    latencias = [saidas[q.id].get("latencia_s") for q in usadas]

    return {
        "n_questoes_benchmark": len(questoes),
        "n_com_saida": len(usadas),
        "com_erro": com_erro,
        "sem_saida": sem_saida,
        "completo": not com_erro and not sem_saida,
        "trcc": trcc,
        "trcc_por_questao": {qid: r.trcc for qid, r in resultados.items()},
        "ausentes_por_questao": {qid: list(r.ausentes) for qid, r in resultados.items() if r.ausentes},
        "flesch_antes": _media(a.flesch for a in antes),
        "flesch_depois": _media(d.flesch for d in depois),
        "comando_conjugado_antes_pct": _pct(a.has_conjugated_command for a in antes),
        "comando_conjugado_depois_pct": _pct(d.has_conjugated_command for d in depois),
        "latencia_media_s": _media(latencias),
    }


def _pct(flags) -> float | None:
    flags = [bool(f) for f in flags]
    return round(100 * sum(flags) / len(flags), 1) if flags else None


def comparar_pareado(alvo: dict, referencia: dict) -> dict:
    """Wilcoxon pareado do TRCC por questão (alvo vs referência) nas questões comuns."""
    comuns = sorted(
        q for q in alvo["trcc_por_questao"]
        if q in referencia["trcc_por_questao"]
        and alvo["trcc_por_questao"][q] is not None
        and referencia["trcc_por_questao"][q] is not None
    )
    a = [alvo["trcc_por_questao"][q] for q in comuns]
    b = [referencia["trcc_por_questao"][q] for q in comuns]
    base = {"n_pares": len(comuns), "media_alvo": _media(a), "media_referencia": _media(b)}
    if len(comuns) < 6:
        return {**base, "p_valor": None, "nota": "poucos pares para um teste estatístico (< 6)"}
    if all(x == y for x, y in zip(a, b)):
        return {**base, "p_valor": 1.0, "nota": "sem diferença entre os sistemas"}
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return {**base, "p_valor": None, "nota": "scipy não instalado"}
    return {**base, "p_valor": round(float(wilcoxon(a, b).pvalue), 6), "nota": "Wilcoxon pareado (bicaudal)"}


def _status(ok: bool | None, incompleto: bool = False) -> str:
    if incompleto:
        return "incompleto"
    if ok is None:
        return "nao_medido"
    return "aprovado" if ok else "reprovado"


def avaliar_criterios(
    alvo: dict, faith: dict | None, referencia: dict | None, limiar: float = LIMIAR_PADRAO
) -> dict[str, dict]:
    trcc = alvo["trcc"]
    inc = not alvo["completo"]
    micro = trcc["trcc_micro"] if trcc else None
    criterios = {
        "completude": {
            "obrigatorio": True,
            "status": _status(alvo["completo"]),
            "detalhe": f"{alvo['n_com_saida']}/{alvo['n_questoes_benchmark']} questões com saída",
        },
        "trcc_micro": {
            "obrigatorio": True,
            "status": _status(None if micro is None else micro >= limiar - 1e-9, incompleto=inc and micro is not None and micro >= limiar),
            "valor": micro,
            "meta": limiar,
        },
        "trcc_por_questao": {
            "obrigatorio": False,
            "status": _status(None if trcc is None else trcc["aprovado_todas_as_questoes"]),
            "valor": None if trcc is None else trcc["pct_questoes_aprovadas"],
            "detalhe": None if trcc is None else f"abaixo do limiar: {trcc['questoes_abaixo_do_limiar']}",
        },
        "faithfulness": {
            "obrigatorio": True,
            "status": _status(None if not faith or faith["media"] is None else faith["media"] >= FAITHFULNESS_MIN),
            "valor": None if not faith else faith["media"],
            "meta": FAITHFULNESS_MIN,
            "detalhe": None if not faith else f"{faith['n_medidas']} medidas; juiz {faith['juiz']}",
        },
    }
    if referencia and referencia["trcc"]:
        ref = referencia["trcc"]["trcc_micro"]
        criterios["hipotese_llm_puro"] = {
            "obrigatorio": False,
            "status": _status(ref < HIPOTESE_LLM_PURO_MAX),
            "valor": ref,
            "meta": f"< {HIPOTESE_LLM_PURO_MAX}",
            "detalhe": "informativo: o LLM puro perde conteúdo curricular?",
        }
    return criterios


def veredito(criterios: dict[str, dict], rascunho: bool) -> str:
    obrig = [c["status"] for c in criterios.values() if c["obrigatorio"]]
    if "reprovado" in obrig:
        return "REPROVADO"
    if any(s in ("incompleto", "nao_medido") for s in obrig):
        return "INCOMPLETO"
    return "PRELIMINAR" if rascunho else "APROVADO"


def gerar_relatorio(
    questoes: list[GoldenQuestion],
    pasta_saidas: str | Path,
    alvo: str = "iris",
    referencia: str | None = "llm_puro",
    limiar: float = LIMIAR_PADRAO,
) -> dict:
    saidas_alvo = ler_saidas(Path(pasta_saidas) / f"{alvo}.jsonl")
    if not saidas_alvo:
        raise FileNotFoundError(f"Sem saídas de '{alvo}' em {pasta_saidas}. Rode iris.eval.executar.")
    m_alvo = metricas_sistema(questoes, saidas_alvo, limiar)

    m_ref = None
    if referencia:
        saidas_ref = ler_saidas(Path(pasta_saidas) / f"{referencia}.jsonl")
        m_ref = metricas_sistema(questoes, saidas_ref, limiar) if saidas_ref else None

    faith = ler_faithfulness(pasta_saidas, alvo)
    criterios = avaliar_criterios(m_alvo, faith, m_ref, limiar)
    rascunho = any(getattr(q, "status", None) == "rascunho" for q in questoes)
    return {
        "veredito": veredito(criterios, rascunho),
        "benchmark_rascunho": rascunho,
        "alvo": alvo,
        "referencia": referencia if m_ref else None,
        "criterios": criterios,
        "metricas": {alvo: m_alvo, **({referencia: m_ref} if m_ref else {})},
        "comparacao_pareada": comparar_pareado(m_alvo, m_ref) if m_ref else None,
    }


def _fmt(v) -> str:
    return "—" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))


def para_markdown(rel: dict) -> str:
    L = [f"# Relatório do benchmark — {rel['alvo']}"
         + (f" vs {rel['referencia']}" if rel["referencia"] else ""), ""]
    L += [f"**Veredito: {rel['veredito']}**", ""]
    if rel["benchmark_rascunho"]:
        L += ["> ⚠️ O Golden Benchmark ainda está como `rascunho` (sem revisão pedagógica): "
              "o resultado é preliminar.", ""]
    L += ["## Critérios", "", "| Critério | Obrigatório | Status | Valor | Meta | Detalhe |", "|---|---|---|---|---|---|"]
    for nome, c in rel["criterios"].items():
        L.append(f"| {nome} | {'sim' if c['obrigatorio'] else 'não'} | {c['status']} | "
                 f"{_fmt(c.get('valor'))} | {_fmt(c.get('meta'))} | {c.get('detalhe') or ''} |")
    L += ["", "## Métricas por sistema", "",
          "| Sistema | Saídas | TRCC micro | TRCC macro | Flesch antes→depois | Cmd. conjugado % antes→depois | Latência média (s) |",
          "|---|---|---|---|---|---|---|"]
    for nome, m in rel["metricas"].items():
        t = m["trcc"] or {}
        L.append(f"| {nome} | {m['n_com_saida']}/{m['n_questoes_benchmark']} | {_fmt(t.get('trcc_micro'))} | "
                 f"{_fmt(t.get('trcc_macro'))} | {_fmt(m['flesch_antes'])}→{_fmt(m['flesch_depois'])} | "
                 f"{_fmt(m['comando_conjugado_antes_pct'])}→{_fmt(m['comando_conjugado_depois_pct'])} | "
                 f"{_fmt(m['latencia_media_s'])} |")
    p = rel["comparacao_pareada"]
    if p:
        L += ["", "## Comparação pareada (TRCC por questão)", "",
              f"- pares: {p['n_pares']} · média {rel['alvo']}: {_fmt(p['media_alvo'])} · "
              f"média {rel['referencia']}: {_fmt(p['media_referencia'])}",
              f"- p-valor: {_fmt(p['p_valor'])} ({p['nota']})"]
    aus = rel["metricas"][rel["alvo"]]["ausentes_por_questao"]
    if aus:
        L += ["", f"## Conceitos perdidos por {rel['alvo']}", ""]
        L += [f"- {qid}: {', '.join(c)}" for qid, c in aus.items()]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--alvo", default="iris")
    ap.add_argument("--referencia", default="llm_puro")
    ap.add_argument("--benchmark", default=None)
    ap.add_argument("--saidas", default=str(SAIDAS_PADRAO))
    ap.add_argument("--destino", default=str(RELATORIO_PADRAO))
    ap.add_argument("--limiar", type=float, default=LIMIAR_PADRAO)
    args = ap.parse_args(argv)

    rel = gerar_relatorio(
        carregar_golden_benchmark(args.benchmark), args.saidas, args.alvo, args.referencia, args.limiar
    )
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "benchmark_relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    (destino / "benchmark_relatorio.md").write_text(para_markdown(rel), encoding="utf-8")
    print(para_markdown(rel))


if __name__ == "__main__":
    main()