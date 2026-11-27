"""Calibragem reproduzível do limiar `RAG_RERANK_MIN_SCORE` para abstenção (Issue #156 / #86).

Compara o maior score de recuperação (`top1_score`) das perguntas com resposta
(`gabarito_rascunho_v0.json`) contra as perguntas fora da base (`data/benchmarks/perguntas_fora_da_base_v1.json`).
Faz a seleção do limiar exclusivamente na partição de treino (60%) e mede o resultado uma única vez
na partição reservada de validação (40%), evitando sobreajuste ao conjunto de escolha.

Uso via CLI:
    uv run python -m iris.eval.calibrar_recusa --metodo auto
"""
from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iris.config import BENCHMARKS_DIR, REPO_ROOT
from iris.eval.precisao_contexto import carregar_gabarito
from iris.eval.rag_funnel import _resolver_ranqueador

SAIDA_JSON = REPO_ROOT / "reports" / "rag_calibracao_recusa.json"
SAIDA_TXT = REPO_ROOT / "reports" / "rag_calibracao_recusa.txt"

RanqueadorComScore = Callable[[str, str, int], list[tuple[str, float]]]


def dividir_treino_validacao(
    dentro: list[Any],
    fora: list[Any],
    proporcao_treino: float = 0.6,
    semente: int = 20261126,
) -> tuple[tuple[list[Any], list[Any]], tuple[list[Any], list[Any]]]:
    """Divide listas dentro/fora em treino e validação de forma determinística."""
    rnd = random.Random(semente)
    dentro_c = list(dentro)
    fora_c = list(fora)
    rnd.shuffle(dentro_c)
    rnd.shuffle(fora_c)

    corte_d = max(1, min(len(dentro_c) - 1, int(round(len(dentro_c) * proporcao_treino)))) if len(dentro_c) > 1 else len(dentro_c)
    corte_f = max(1, min(len(fora_c) - 1, int(round(len(fora_c) * proporcao_treino)))) if len(fora_c) > 1 else len(fora_c)

    return (dentro_c[:corte_d], fora_c[:corte_f]), (dentro_c[corte_d:], fora_c[corte_f:])


def avaliar_limiar(scores_dentro: list[float], scores_fora: list[float], limiar: float) -> dict[str, Any]:
    """Avalia taxa de recusa fora da base e falsa recusa dentro da base para um limiar."""
    total_fora = len(scores_fora)
    total_dentro = len(scores_dentro)
    acertos_fora = sum(1 for s in scores_fora if s < limiar)
    falsas_recusas = sum(1 for s in scores_dentro if s < limiar)

    recusa_fora = acertos_fora / max(total_fora, 1)
    falsa_recusa = falsas_recusas / max(total_dentro, 1)
    cobertura_dentro = 1.0 - falsa_recusa

    # F1 equilibrando detecção de fora da base (recusa_fora) e preservação dentro da base (cobertura_dentro)
    if (recusa_fora + cobertura_dentro) > 0:
        f1 = (2.0 * recusa_fora * cobertura_dentro) / (recusa_fora + cobertura_dentro)
    else:
        f1 = 0.0

    return {
        "limiar": round(float(limiar), 4),
        "recusa_fora_base": round(recusa_fora, 4),
        "falsa_recusa_dentro_base": round(falsa_recusa, 4),
        "cobertura_dentro_base": round(cobertura_dentro, 4),
        "f1_abstencao": round(f1, 4),
        "acertos_fora": acertos_fora,
        "total_fora": total_fora,
        "falsas_recusas": falsas_recusas,
        "total_dentro": total_dentro,
    }


def calibrar_limiares(
    scores_dentro: list[float],
    scores_fora: list[float],
    meta_recusa: float = 0.93,
    max_falsa_recusa: float = 0.10,
    semente: int = 20261126,
) -> dict[str, Any]:
    """Seleciona o melhor limiar no treino e mede uma vez na validação reservada."""
    if not scores_dentro or not scores_fora:
        raise ValueError("São necessários scores dentro e fora da base para calibrar o limiar.")

    (treino_d, treino_f), (val_d, val_f) = dividir_treino_validacao(
        scores_dentro, scores_fora, proporcao_treino=0.6, semente=semente
    )

    todos_treino = sorted(set(round(float(x), 4) for x in [*treino_d, *treino_f]))
    candidatos: list[float] = []
    for i in range(len(todos_treino) - 1):
        candidatos.append(round((todos_treino[i] + todos_treino[i + 1]) / 2.0, 4))
    if not candidatos:
        candidatos = [round(todos_treino[0], 4)]

    curva_treino = [avaliar_limiar(treino_d, treino_f, lim) for lim in candidatos]
    atingem_meta = [
        c for c in curva_treino if c["recusa_fora_base"] >= meta_recusa and c["falsa_recusa_dentro_base"] <= max_falsa_recusa
    ]
    if atingem_meta:
        melhor_treino = max(
            atingem_meta,
            key=lambda c: (c["cobertura_dentro_base"], c["recusa_fora_base"], -c["limiar"]),
        )
        criterio_escolha = "meta_recusa_e_cobertura"
    else:
        melhor_treino = max(
            curva_treino,
            key=lambda c: (c["f1_abstencao"], c["recusa_fora_base"], -c["falsa_recusa_dentro_base"]),
        )
        criterio_escolha = "melhor_f1_equilibrio"

    limiar_escolhido = melhor_treino["limiar"]
    avaliacao_validacao = avaliar_limiar(val_d, val_f, limiar_escolhido) if (val_d and val_f) else melhor_treino

    return {
        "limiar_recomendado": limiar_escolhido,
        "criterio_escolha": criterio_escolha,
        "meta_recusa": meta_recusa,
        "max_falsa_recusa": max_falsa_recusa,
        "treino": melhor_treino,
        "validacao": avaliacao_validacao,
        "curva_treino": curva_treino,
    }


def executar_calibracao(
    metodo: str = "auto",
    salvar: bool = True,
    ranqueador: RanqueadorComScore | None = None,
) -> dict[str, Any]:
    """Coleta os scores top-1 dentro/fora da base e executa a calibragem."""
    fn_ranking, metodo_efetivo, modo_reduzido, aviso_modo = _resolver_ranqueador(metodo, ranqueador)
    itens_dentro = carregar_gabarito()
    arq_fora = BENCHMARKS_DIR / "perguntas_fora_da_base_v1.json"
    itens_fora = json.loads(arq_fora.read_text(encoding="utf-8")).get("perguntas", [])

    scores_dentro: list[float] = []
    for item in itens_dentro:
        pares = fn_ranking(item["pergunta"], metodo_efetivo, 1)
        if pares:
            scores_dentro.append(float(pares[0][1]))

    scores_fora: list[float] = []
    for item in itens_fora:
        pares = fn_ranking(item["pergunta"], metodo_efetivo, 1)
        if pares:
            scores_fora.append(float(pares[0][1]))

    calibracao = calibrar_limiares(scores_dentro, scores_fora)
    resultado = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "metodo_solicitado": metodo,
        "metodo_efetivo": metodo_efetivo,
        "modo_reduzido": modo_reduzido,
        "aviso_modo": aviso_modo,
        "n_dentro": len(scores_dentro),
        "n_fora": len(scores_fora),
        **calibracao,
    }

    if salvar:
        SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
        SAIDA_JSON.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        SAIDA_TXT.write_text(formatar_calibracao_texto(resultado) + "\n", encoding="utf-8")
    return resultado


def formatar_calibracao_texto(res: dict[str, Any]) -> str:
    tr = res["treino"]
    va = res["validacao"]
    eh_rerank = "rerank" in str(res.get("metodo_efetivo") or "")
    orientacao = (
        f"Sugestão de uso (método {res['metodo_efetivo']}):\n  RAG_RERANK_MIN_SCORE={res['limiar_recomendado']}"
        if eh_rerank
        else "Aviso: esta execução usou método sem reranker (escala BM25). Para calibrar RAG_RERANK_MIN_SCORE, rode com pgvector ativo (`--metodo qwen3+rerank50`)."
    )
    linhas = [
        "CALIBRAGEM DO LIMIAR DE RECUSA DO RAG (RAG_RERANK_MIN_SCORE)",
        f"Método: {res['metodo_efetivo']}" + (" (modo reduzido BM25)" if res.get("modo_reduzido") else ""),
        f"Limiar recomendado: {res['limiar_recomendado']} (critério: {res['criterio_escolha']})",
        f"Treino (60%): recusa_fora={tr['recusa_fora_base']} ({tr['acertos_fora']}/{tr['total_fora']}) | "
        f"falsa_recusa={tr['falsa_recusa_dentro_base']} ({tr['falsas_recusas']}/{tr['total_dentro']})",
        f"Validação (40%): recusa_fora={va['recusa_fora_base']} ({va['acertos_fora']}/{va['total_fora']}) | "
        f"falsa_recusa={va['falsa_recusa_dentro_base']} ({va['falsas_recusas']}/{va['total_dentro']})",
        "",
        orientacao,
    ]
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibragem do limiar RAG_RERANK_MIN_SCORE")
    parser.add_argument("--metodo", default="auto", help="auto, qwen3+rerank50, bm25, etc.")
    parser.add_argument("--no-save", action="store_true", help="Não grava reports/rag_calibracao_recusa.*")
    args = parser.parse_args()

    res = executar_calibracao(metodo=args.metodo, salvar=not args.no_save)
    print(formatar_calibracao_texto(res))


if __name__ == "__main__":
    main()
