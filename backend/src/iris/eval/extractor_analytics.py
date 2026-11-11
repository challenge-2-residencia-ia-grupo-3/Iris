"""Analytics dinâmico e benchmark do Agente Extrator Curricular (Issue #17 / RNF-07).

Registra e agrega exclusivamente telemetria operacional anônima (Zero-PII / LGPD):
latência total, tempo de carregamento (cold start) vs. inferência real, tokens/s,
taxa de descoberta de travas curriculares (Zero-Hint) e cortes por disciplina,
faixa etária e tipo de questão.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from iris.config import REPO_ROOT
from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.schemas.curriculum import ExtractionTelemetry

TELEMETRIA_PADRAO = REPO_ROOT / "reports" / "extractor_telemetry.jsonl"


def _resolver_caminho(caminho: Path | str | None) -> Path:
    return Path(caminho) if caminho is not None else TELEMETRIA_PADRAO


def registrar_telemetria(
    telemetry: ExtractionTelemetry,
    caminho: Path | str | None = None,
) -> Path:
    """Acrescenta um registro operacional anônimo ao log JSONL de telemetria."""
    destino = _resolver_caminho(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as f:
        f.write(json.dumps(telemetry.model_dump(), ensure_ascii=False) + "\n")
    return destino


def carregar_telemetria(caminho: Path | str | None = None) -> list[dict[str, Any]]:
    """Carrega todos os registros válidos de telemetria do arquivo JSONL."""
    origem = _resolver_caminho(caminho)
    if not origem.exists():
        return []
    registros: list[dict[str, Any]] = []
    for linha in origem.read_text(encoding="utf-8").splitlines():
        texto = linha.strip()
        if not texto:
            continue
        try:
            registros.append(json.loads(texto))
        except json.JSONDecodeError:
            continue
    return registros


def _bate_texto(valor_registro: Any, filtro: Optional[str]) -> bool:
    if not filtro:
        return True
    return filtro.strip().lower() in str(valor_registro or "").lower()


def filtrar_telemetria(
    registros: list[dict[str, Any]],
    *,
    disciplina: Optional[str] = None,
    faixa_etaria: Optional[str] = None,
    ano_escolar: Optional[str] = None,
    tema: Optional[str] = None,
    comando_conjugado: Optional[bool] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    apenas_ia: bool = False,
) -> list[dict[str, Any]]:
    """Filtra registros operacionais por tipo de questão, faixa etária e provedor."""
    filtrados: list[dict[str, Any]] = []
    for r in registros:
        if not _bate_texto(r.get("disciplina"), disciplina):
            continue
        if not _bate_texto(r.get("faixa_etaria"), faixa_etaria):
            continue
        if not _bate_texto(r.get("ano_escolar"), ano_escolar):
            continue
        if not _bate_texto(r.get("tema"), tema):
            continue
        if not _bate_texto(r.get("provider"), provider):
            continue
        if not _bate_texto(r.get("model"), model):
            continue
        if comando_conjugado is not None and r.get("comando_conjugado") is not comando_conjugado:
            continue
        if apenas_ia and r.get("used_fallback"):
            continue
        filtrados.append(r)
    return filtrados


def _classificar_tamanho(chars: int) -> str:
    if chars < 150:
        return "curta (<150 chars)"
    if chars <= 350:
        return "media (150-350 chars)"
    return "longa (>350 chars)"


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return round(ordenados[0], 2)
    idx = (len(ordenados) - 1) * (p / 100.0)
    baixo = math.floor(idx)
    alto = math.ceil(idx)
    if baixo == alto:
        return round(ordenados[baixo], 2)
    frac = idx - baixo
    return round(ordenados[baixo] * (1 - frac) + ordenados[alto] * frac, 2)


def _stats_serie(valores: list[float]) -> dict[str, float]:
    if not valores:
        return {"min": 0.0, "media": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "min": round(min(valores), 2),
        "media": round(sum(valores) / len(valores), 2),
        "p50": _percentil(valores, 50),
        "p95": _percentil(valores, 95),
        "max": round(max(valores), 2),
    }


def resumir_metricas(registros: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula estatísticas consolidadas de latência, throughput e qualidade de extração."""
    n = len(registros)
    if n == 0:
        return {
            "total_execucoes": 0,
            "execucoes_ia": 0,
            "fallbacks": 0,
            "taxa_fallback_pct": 0.0,
            "json_valido_direto_pct": 0.0,
            "total_ms": _stats_serie([]),
            "inference_ms": _stats_serie([]),
            "load_ms": {"media": 0.0, "max": 0.0, "cold_starts": 0},
            "tokens": {"prompt_medio": 0.0, "completion_medio": 0.0, "tokens_per_sec_medio": 0.0},
            "trava_recall_medio": None,
            "aderencia_rnf07": {
                "pct_ate_15s_inference": 0.0,
                "pct_ate_40s_inference": 0.0,
                "pct_ate_15s_total": 0.0,
                "pct_ate_40s_total": 0.0,
            },
        }

    totais = [float(r.get("total_ms") or 0.0) for r in registros]
    inferencias = [float(r.get("inference_ms") or r.get("total_ms") or 0.0) for r in registros]
    loads = [float(r.get("load_ms") or 0.0) for r in registros]
    prompts = [float(r.get("prompt_tokens") or 0.0) for r in registros]
    completions = [float(r.get("completion_tokens") or 0.0) for r in registros]
    tps = [float(r.get("tokens_per_sec") or 0.0) for r in registros if float(r.get("tokens_per_sec") or 0.0) > 0]
    recalls = [float(r["trava_recall"]) for r in registros if r.get("trava_recall") is not None]

    fallbacks = sum(1 for r in registros if r.get("used_fallback"))
    json_direto = sum(1 for r in registros if r.get("json_valido_direto", True))
    cold_starts = sum(1 for ld in loads if ld >= 500.0)

    return {
        "total_execucoes": n,
        "execucoes_ia": n - fallbacks,
        "fallbacks": fallbacks,
        "taxa_fallback_pct": round(100.0 * fallbacks / n, 1),
        "json_valido_direto_pct": round(100.0 * json_direto / n, 1),
        "total_ms": _stats_serie(totais),
        "inference_ms": _stats_serie(inferencias),
        "load_ms": {
            "media": round(sum(loads) / n, 2),
            "max": round(max(loads), 2),
            "cold_starts": cold_starts,
        },
        "tokens": {
            "prompt_medio": round(sum(prompts) / n, 1),
            "completion_medio": round(sum(completions) / n, 1),
            "tokens_per_sec_medio": round(sum(tps) / len(tps), 2) if tps else 0.0,
        },
        "trava_recall_medio": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "aderencia_rnf07": {
            "pct_ate_15s_inference": round(100.0 * sum(1 for x in inferencias if x <= 15000.0) / n, 1),
            "pct_ate_40s_inference": round(100.0 * sum(1 for x in inferencias if x <= 40000.0) / n, 1),
            "pct_ate_15s_total": round(100.0 * sum(1 for x in totais if x <= 15000.0) / n, 1),
            "pct_ate_40s_total": round(100.0 * sum(1 for x in totais if x <= 40000.0) / n, 1),
        },
    }


def _agrupar_por(
    registros: list[dict[str, Any]],
    chave_fn: Callable[[dict[str, Any]], str],
) -> dict[str, dict[str, Any]]:
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in registros:
        grupos[chave_fn(r)].append(r)
    return {
        chave: resumir_metricas(itens)
        for chave, itens in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    }


def _rotulo_comando(r: dict[str, Any]) -> str:
    val = r.get("comando_conjugado")
    if val is True:
        return "comando_conjugado"
    if val is False:
        return "comando_simples"
    return "nao_informado"


def gerar_analytics(
    registros: list[dict[str, Any]],
    *,
    disciplina: Optional[str] = None,
    faixa_etaria: Optional[str] = None,
    ano_escolar: Optional[str] = None,
    tema: Optional[str] = None,
    comando_conjugado: Optional[bool] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    apenas_ia: bool = False,
) -> dict[str, Any]:
    """Gera painel analítico filtrado por tipo de questão, faixa etária e modelo."""
    filtrados = filtrar_telemetria(
        registros,
        disciplina=disciplina,
        faixa_etaria=faixa_etaria,
        ano_escolar=ano_escolar,
        tema=tema,
        comando_conjugado=comando_conjugado,
        provider=provider,
        model=model,
        apenas_ia=apenas_ia,
    )
    return {
        "filtros_aplicados": {
            "disciplina": disciplina,
            "faixa_etaria": faixa_etaria,
            "ano_escolar": ano_escolar,
            "tema": tema,
            "comando_conjugado": comando_conjugado,
            "provider": provider,
            "model": model,
            "apenas_ia": apenas_ia,
        },
        "resumo_geral": resumir_metricas(filtrados),
        "por_disciplina": _agrupar_por(filtrados, lambda r: str(r.get("disciplina") or "Não informada")),
        "por_faixa_etaria": _agrupar_por(filtrados, lambda r: str(r.get("faixa_etaria") or "Não informado")),
        "por_tipo_comando": _agrupar_por(filtrados, _rotulo_comando),
        "por_faixa_tamanho": _agrupar_por(
            filtrados,
            lambda r: _classificar_tamanho(int(r.get("tamanho_enunciado_chars") or 0)),
        ),
        "por_modelo": _agrupar_por(
            filtrados,
            lambda r: f"{r.get('provider', 'unknown')}:{r.get('model', 'unknown')}",
        ),
    }


def executar_benchmark_extrator(
    extractor: Any,
    questoes: list[GoldenQuestion],
    *,
    caminho_saida: Path | str | None = None,
    refazer: bool = False,
    limite: Optional[int] = None,
    warmup: bool = True,
    progresso: Callable[[str], None] | None = print,
) -> dict[str, Any]:
    """Executa o Extrator em lote (Zero-Hint) no Golden Benchmark e retorna analytics."""
    destino = _resolver_caminho(caminho_saida)
    if refazer and destino.exists():
        destino.unlink()

    if warmup and hasattr(extractor, "llm_client") and hasattr(extractor.llm_client, "warmup"):
        w = extractor.llm_client.warmup()
        if progresso and w.get("warmed"):
            progresso(f"[Warmup] Modelo pré-carregado em {w.get('latency_ms', 0.0):.0f} ms.")

    alvo = questoes[:limite] if limite else questoes
    novos: list[dict[str, Any]] = []
    for i, q in enumerate(alvo, 1):
        res = extractor.extract_golden_with_telemetry(q, include_trava_hint=False)
        registrar_telemetria(res.telemetry, caminho=destino)
        novos.append(res.telemetry.model_dump())
        if progresso:
            rec_str = f"{res.telemetry.trava_recall * 100:.0f}%" if res.telemetry.trava_recall is not None else "n/a"
            fb = " [FALLBACK]" if res.telemetry.used_fallback else ""
            progresso(
                f"[{i}/{len(alvo)}] {q.id} | {q.disciplina} ({q.ano}) | "
                f"inf={res.telemetry.inference_ms:.0f}ms (load={res.telemetry.load_ms:.0f}ms) | "
                f"recall={rec_str} | {res.telemetry.tokens_per_sec:.1f} tok/s{fb}"
            )

    analytics = gerar_analytics(novos)
    analytics["arquivo_telemetria"] = str(destino)
    return analytics


def _formatar_bloco_grupo(titulo: str, grupo: dict[str, dict[str, Any]]) -> list[str]:
    if not grupo:
        return []
    linhas = [
        f"\n{titulo}:",
        f"  {'Categoria':<32} {'N':>4} {'Inf Média':>10} {'Inf P50':>9} {'Inf P95':>9} {'Tok/s':>7} {'Recall':>8}",
        "  " + "-" * 83,
    ]
    for nome, m in grupo.items():
        inf = m["inference_ms"]
        tps = m["tokens"]["tokens_per_sec_medio"]
        rec = f"{m['trava_recall_medio'] * 100:.1f}%" if m["trava_recall_medio"] is not None else "n/a"
        linhas.append(
            f"  {nome[:32]:<32} {m['total_execucoes']:>4} {inf['media']:>8.0f}ms "
            f"{inf['p50']:>7.0f}ms {inf['p95']:>7.0f}ms {tps:>7.1f} {rec:>8}"
        )
    return linhas


def formatar_relatorio_terminal(analytics: dict[str, Any]) -> str:
    """Formata o relatório analítico para leitura rápida no terminal."""
    r = analytics["resumo_geral"]
    if r["total_execucoes"] == 0:
        return "\nNenhum registro de telemetria encontrado para os filtros informados."

    inf = r["inference_ms"]
    tot = r["total_ms"]
    ld = r["load_ms"]
    rnf = r["aderencia_rnf07"]
    rec_geral = f"{r['trava_recall_medio'] * 100:.1f}%" if r["trava_recall_medio"] is not None else "n/a"

    linhas = [
        "\n" + "=" * 83,
        " ANALYTICS DO AGENTE EXTRATOR CURRICULAR (ISSUE #17)",
        "=" * 83,
        f" Execuções: {r['total_execucoes']} (IA: {r['execucoes_ia']} | Fallbacks: {r['fallbacks']} [{r['taxa_fallback_pct']}%])",
        f" JSON válido direto: {r['json_valido_direto_pct']}% | Recall Médio de Trava (Zero-Hint): {rec_geral}",
        f" Inferência Real (sem cold start): média {inf['media']:.0f}ms | P50 {inf['p50']:.0f}ms | P95 {inf['p95']:.0f}ms | máx {inf['max']:.0f}ms",
        f" Tempo Total (com cold start)    : média {tot['media']:.0f}ms | P95 {tot['p95']:.0f}ms | cold starts: {ld['cold_starts']}",
        f" Tokens médios: prompt={r['tokens']['prompt_medio']} | saída={r['tokens']['completion_medio']} | {r['tokens']['tokens_per_sec_medio']} tok/s",
        f" Aderência RNF-07 (Inferência): <=15s em {rnf['pct_ate_15s_inference']}% | <=40s em {rnf['pct_ate_40s_inference']}%",
    ]
    linhas.extend(_formatar_bloco_grupo("POR DISCIPLINA", analytics["por_disciplina"]))
    linhas.extend(_formatar_bloco_grupo("POR FAIXA ETÁRIA", analytics["por_faixa_etaria"]))
    linhas.extend(_formatar_bloco_grupo("POR TIPO DE COMANDO", analytics["por_tipo_comando"]))
    linhas.extend(_formatar_bloco_grupo("POR TAMANHO DO ENUNCIADO", analytics["por_faixa_tamanho"]))
    linhas.extend(_formatar_bloco_grupo("POR MODELO / PROVEDOR", analytics["por_modelo"]))
    linhas.append("=" * 83)
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Analytics e Benchmark do Agente Extrator (Issue #17)")
    ap.add_argument("--benchmark", action="store_true", help="Executa o Extrator sobre o Golden Benchmark")
    ap.add_argument("--limite", type=int, default=None, help="Limita quantidade de questões no benchmark")
    ap.add_argument("--refazer", action="store_true", help="Limpa telemetria anterior antes do benchmark")
    ap.add_argument("--no-warmup", action="store_true", help="Não executa warmup prévio no Ollama")
    ap.add_argument("--provider", default=None, help="Filtrar ou rodar com provedor (ollama, groq, extractive)")
    ap.add_argument("--model", default=None, help="Filtrar ou rodar com modelo específico")
    ap.add_argument("--disciplina", default=None, help="Filtrar analytics por disciplina")
    ap.add_argument("--faixa-etaria", default=None, help="Filtrar analytics por faixa etária")
    ap.add_argument("--comando-conjugado", choices=["sim", "nao"], default=None, help="Filtrar por comando conjugado")
    ap.add_argument("--json", action="store_true", help="Imprime saída completa em JSON")
    args = ap.parse_args(argv)

    if args.benchmark:
        from iris.agents.curriculum_extractor import get_curriculum_extractor
        from iris.core.llm_client import get_llm_client

        llm = get_llm_client(provider=args.provider, model=args.model, allow_fallback_to_extractive=True)
        extractor = get_curriculum_extractor(llm_client=llm)
        questoes = carregar_golden_benchmark()
        analytics = executar_benchmark_extrator(
            extractor,
            questoes,
            refazer=args.refazer,
            limite=args.limite,
            warmup=not args.no_warmup,
        )
    else:
        cmd_bool: Optional[bool] = None
        if args.comando_conjugado == "sim":
            cmd_bool = True
        elif args.comando_conjugado == "nao":
            cmd_bool = False
        registros = carregar_telemetria()
        analytics = gerar_analytics(
            registros,
            disciplina=args.disciplina,
            faixa_etaria=args.faixa_etaria,
            comando_conjugado=cmd_bool,
            provider=args.provider,
            model=args.model,
        )

    if args.json:
        print(json.dumps(analytics, ensure_ascii=False, indent=2))
    else:
        print(formatar_relatorio_terminal(analytics))


if __name__ == "__main__":
    main()
