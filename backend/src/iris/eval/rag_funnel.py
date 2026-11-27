"""Funil Vivo de Causa Raiz do RAG em 4 Gavetas (Issue #156).

Separa os gargalos do RAG contra o código e o índice atuais (sem depender de snapshots antigos
e sem expor textos de documentos sob licença restrita):
  1. Corpus e Filtro de Barreiras (trechos buscáveis, docs sem barreira, cobertura do gabarito);
  2. Busca 1ª Etapa (Top-50): o trecho relevante entrou nos candidatos iniciais?;
  3. Reordenação (Top-50 -> Top-5): o reranker preservou o trecho no Top-5? (+ IDBasedContextPrecision RAGAS);
  4. Geração, Citação e Abstenção: status do gerador e do gate determinístico `RAG_RERANK_MIN_SCORE`.

Uso via CLI:
    uv run python -m iris.eval.rag_funnel --metodo bm25
    uv run python -m iris.eval.rag_funnel --metodo auto --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iris.config import BENCHMARKS_DIR, RAG_PACOTE_DIR, REPO_ROOT
from iris.eval.precisao_contexto import carregar_gabarito, conferir_universo, pontuar_ragas_por_id
from iris.eval.rag_metrics import (
    avaliar_pipeline_registrado,
    calcular_average_precision_at_k,
    calcular_mrr,
    calcular_recall_at_k,
)
from iris.rag.bridge import carregar_catalogo_fontes, carregar_modulos_rag, erros_de_infraestrutura, obter_trechos_base
from iris.schemas.catalog import BARREIRAS_RAG_VALIDAS

RanqueadorComScore = Callable[[str, str, int], list[tuple[str, float]]]

DOCS_SEM_BARREIRA_INTENCIONAIS = frozenset(
    {
        "DALGAARD-2022-INCLUSAO-META",
        "DEKKER-2012-NEUROMITOS",
        "SIMOES-2022-NEUROMITOS-BRASIL",
    }
)


def _eh_doc_sem_barreira_intencional(doc: dict[str, Any]) -> bool:
    """Documentos normativos (Parte C) ou de inclusão/neuromitos gerais ficam sem tag de barreira."""
    return str(doc.get("parte") or "") == "C" or str(doc.get("id") or "") in DOCS_SEM_BARREIRA_INTENCIONAIS


def _git_commit_curto() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        out = (proc.stdout or "").strip()
        return out or "desconhecido"
    except OSError:
        return "desconhecido"


def _chunks_sha256(caminho: Path | None = None) -> str:
    alvo = caminho or (RAG_PACOTE_DIR / "chunks.jsonl")
    if not alvo.exists():
        return "ausente"
    return hashlib.sha256(alvo.read_bytes()).hexdigest()[:16]


def _resumo_scores(valores: list[float]) -> dict[str, Any]:
    if not valores:
        return {"n": 0, "min": None, "mediana": None, "max": None}
    ord_vals = sorted(float(v) for v in valores)
    n = len(ord_vals)
    meio = n // 2
    mediana = ord_vals[meio] if n % 2 == 1 else (ord_vals[meio - 1] + ord_vals[meio]) / 2.0
    return {
        "n": n,
        "min": round(ord_vals[0], 4),
        "mediana": round(mediana, 4),
        "max": round(ord_vals[-1], 4),
    }


def _resolver_ranqueador(
    metodo: str,
    ranqueador: RanqueadorComScore | None,
) -> tuple[RanqueadorComScore, str, bool, str | None]:
    _, consultar, _ = carregar_modulos_rag()
    pedido = (metodo or "auto").strip()
    if pedido != "auto":
        consultar.validar_metodo(pedido)

    if ranqueador is not None:
        efetivo = "bm25" if pedido == "auto" else pedido
        return ranqueador, efetivo, False, None

    alvo = "qwen3+rerank50" if pedido == "auto" else pedido
    if alvo == "bm25":
        return consultar.ranking, "bm25", False, None

    try:
        # Probe leve apenas quando o método denso/híbrido é solicitado
        teste = consultar.ranking("memoria de trabalho", alvo, 1)
        if isinstance(teste, list):
            return consultar.ranking, alvo, False, None
    except erros_de_infraestrutura() as exc:
        if pedido != "auto":
            # Se o usuário pediu explicitamente qwen3+rerank50, ainda faz fallback seguro avisando
            pass
        return (
            consultar.ranking,
            "bm25",
            True,
            f"Infraestrutura vetorial indisponível ({type(exc).__name__}); diagnóstico executado com BM25.",
        )

    return consultar.ranking, alvo, False, None


FUNNEL_CACHE_PATH = REPO_ROOT / "reports" / "rag_funnel_cache.json"


def _chave_cache_funil(
    git_commit: str,
    chunks_sha: str,
    metodo_efetivo: str,
    k: int,
    top_candidatos: int,
    incluir_fora_da_base: bool,
    limiar_valor: float | None,
) -> str:
    bruto = "|".join(
        [
            git_commit,
            chunks_sha,
            metodo_efetivo,
            str(k),
            str(top_candidatos),
            "1" if incluir_fora_da_base else "0",
            "" if limiar_valor is None else str(limiar_valor),
        ]
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:24]


def _ler_cache_funil(chave: str) -> dict[str, Any] | None:
    if not FUNNEL_CACHE_PATH.exists():
        return None
    try:
        dados = json.loads(FUNNEL_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entradas = dados.get("entradas") if isinstance(dados, dict) else None
    if not isinstance(entradas, dict):
        return None
    hit = entradas.get(chave)
    return hit if isinstance(hit, dict) else None


def _gravar_cache_funil(chave: str, payload: dict[str, Any]) -> None:
    try:
        if FUNNEL_CACHE_PATH.exists():
            dados = json.loads(FUNNEL_CACHE_PATH.read_text(encoding="utf-8"))
            if not isinstance(dados, dict):
                dados = {}
        else:
            dados = {}
    except (OSError, json.JSONDecodeError):
        dados = {}
    entradas = dados.setdefault("entradas", {})
    if not isinstance(entradas, dict):
        entradas = {}
        dados["entradas"] = entradas
    entradas[chave] = payload
    try:
        FUNNEL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FUNNEL_CACHE_PATH.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def _carregar_perguntas_fora_base() -> list[dict[str, Any]]:
    caminho = BENCHMARKS_DIR / "perguntas_fora_da_base_v1.json"
    if not caminho.exists():
        return []
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return list(dados.get("perguntas", []))


def _ler_calibracao_recusa() -> dict[str, Any] | None:
    caminho = REPO_ROOT / "reports" / "rag_calibracao_recusa.json"
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(dados, dict) or dados.get("limiar_recomendado") is None:
        return None
    val = dados.get("validacao") or {}
    return {
        "limiar_recomendado": dados.get("limiar_recomendado"),
        "metodo_efetivo": dados.get("metodo_efetivo"),
        "recusa_fora_validacao": val.get("recusa_fora_base"),
        "falsa_recusa_validacao": val.get("falsa_recusa_dentro_base"),
    }


def _acao_gate_recusa(calibracao: dict[str, Any] | None) -> str:
    if calibracao and calibracao.get("limiar_recomendado") is not None:
        return (
            f"Definir RAG_RERANK_MIN_SCORE={calibracao['limiar_recomendado']} "
            "(calibrado em reports/rag_calibracao_recusa.txt) ou recalibrar com python -m iris.eval.calibrar_recusa."
        )
    return "Rodar python -m iris.eval.calibrar_recusa para calibrar o limiar entre dentro vs. fora da base."


def executar_funil_rag(
    metodo: str = "auto",
    k: int = 5,
    top_candidatos: int = 50,
    incluir_fora_da_base: bool = True,
    ranqueador: RanqueadorComScore | None = None,
    usar_cache: bool = True,
) -> dict[str, Any]:
    """Executa o diagnóstico vivo em 4 gavetas contra o código e o índice atuais."""
    fn_ranking, metodo_efetivo, modo_reduzido, aviso_modo = _resolver_ranqueador(metodo, ranqueador)
    git_commit = _git_commit_curto()
    chunks_sha = _chunks_sha256()
    limiar_raw = os.environ.get("RAG_RERANK_MIN_SCORE", "").strip()
    limiar_valor = float(limiar_raw) if limiar_raw else None
    chave_cache = _chave_cache_funil(
        git_commit=git_commit,
        chunks_sha=chunks_sha,
        metodo_efetivo=metodo_efetivo,
        k=k,
        top_candidatos=top_candidatos,
        incluir_fora_da_base=incluir_fora_da_base,
        limiar_valor=limiar_valor,
    )
    if usar_cache and ranqueador is None:
        hit = _ler_cache_funil(chave_cache)
        if hit is not None:
            copia = dict(hit)
            meta = dict(copia.get("metadados") or {})
            meta.update(
                {
                    "metodo_solicitado": metodo,
                    "modo_reduzido": modo_reduzido,
                    "aviso_modo": aviso_modo,
                    "origem_cache": True,
                }
            )
            copia["metadados"] = meta
            calibracao = _ler_calibracao_recusa()
            gavetas = dict(copia.get("gavetas") or {})
            g4 = dict(gavetas.get("4_geracao_e_abstencao") or {})
            g4["calibracao_disponivel"] = calibracao
            gavetas["4_geracao_e_abstencao"] = g4
            copia["gavetas"] = gavetas
            if not g4.get("gate_recusa_ativo"):
                nova_acao = _acao_gate_recusa(calibracao)
                copia["diagnostico_prioritario"] = [
                    {**d, "acao": nova_acao} if d.get("gaveta") == "4_geracao_e_abstencao" else d
                    for d in (copia.get("diagnostico_prioritario") or [])
                ]
            return copia

    # ------------------------------------------------------------------
    # Gaveta 1: Corpus & Filtro de Barreiras
    # ------------------------------------------------------------------
    catalogo = carregar_catalogo_fontes()
    docs_aceitos = [
        d
        for d in catalogo.get("documentos", [])
        if str(d.get("status", "")).startswith("aceito") and not d.get("quase_duplicata_de")
    ]
    docs_sem_barreira = sorted(d["id"] for d in docs_aceitos if not d.get("barreiras"))
    docs_sem_barreira_pedagogicos = sorted(
        d["id"]
        for d in docs_aceitos
        if not d.get("barreiras") and not _eh_doc_sem_barreira_intencional(d)
    )
    docs_sem_barreira_intencionais = sorted(
        d["id"]
        for d in docs_aceitos
        if not d.get("barreiras") and _eh_doc_sem_barreira_intencional(d)
    )

    chunks = obter_trechos_base()
    chunks_buscaveis = [c for c in chunks if c.get("n_palavras")]
    chunks_restritos = len(chunks) - len(chunks_buscaveis)
    chunks_com_barreira = sum(1 for c in chunks_buscaveis if c.get("barreiras"))
    chunks_sem_barreira = len(chunks_buscaveis) - chunks_com_barreira

    cobertura_por_barreira = {
        b: sum(1 for c in chunks_buscaveis if b in (c.get("barreiras") or []))
        for b in sorted(BARREIRAS_RAG_VALIDAS)
    }

    itens_gabarito = carregar_gabarito()
    ids_base = {c["chunk_id"] for c in chunks}
    trechos_gabarito_ausentes = conferir_universo(itens_gabarito, ids_base)

    gaveta_1 = {
        "origem_metrica": "deterministico",
        "docs_aceitos": len(docs_aceitos),
        "docs_com_barreira": len(docs_aceitos) - len(docs_sem_barreira),
        "docs_sem_barreira": docs_sem_barreira,
        "docs_sem_barreira_pedagogicos": docs_sem_barreira_pedagogicos,
        "docs_sem_barreira_intencionais": docs_sem_barreira_intencionais,
        "total_chunks": len(chunks),
        "chunks_buscaveis": len(chunks_buscaveis),
        "chunks_restritos_placeholder": chunks_restritos,
        "chunks_com_barreira": chunks_com_barreira,
        "chunks_sem_barreira": chunks_sem_barreira,
        "cobertura_por_barreira": cobertura_por_barreira,
        "trechos_gabarito_ausentes": trechos_gabarito_ausentes,
    }

    # ------------------------------------------------------------------
    # Gavetas 2 e 3: Busca Top-50 e Reranker / Top-5
    # ------------------------------------------------------------------
    recalls_50: list[float] = []
    hits_50: list[int] = []
    recalls_5: list[float] = []
    hits_5: list[int] = []
    mrrs: list[float] = []
    aps_5: list[float] = []
    precisoes_ragas_id: list[float] = []
    ragas_disponivel = True

    total_rel_top50 = 0
    total_rel_top5 = 0
    total_perdidos_rerank = 0
    por_tipo_top50: dict[str, list[float]] = defaultdict(list)
    por_tipo_top5: dict[str, list[float]] = defaultdict(list)
    scores_dentro: list[float] = []

    n_fetch = max(top_candidatos, k)
    for item in itens_gabarito:
        pergunta = item["pergunta"]
        relevantes = set(item.get("trechos_relevantes") or [])
        parciais = set(item.get("trechos_parciais") or [])
        tipo = str(item.get("tipo") or "geral")

        ranking_pares = fn_ranking(pergunta, metodo_efetivo, n_fetch)
        ranking_ids = [cid for cid, _ in ranking_pares]
        if ranking_pares:
            scores_dentro.append(float(ranking_pares[0][1]))

        top50_ids = ranking_ids[:top_candidatos]
        top_k_ids = ranking_ids[:k]

        r50 = calcular_recall_at_k(top50_ids, relevantes, k=top_candidatos)
        r5 = calcular_recall_at_k(top_k_ids, relevantes, k=k)
        hit50 = 1 if (set(top50_ids) & relevantes) else 0
        hit5 = 1 if (set(top_k_ids) & relevantes) else 0
        mrr_q = calcular_mrr(top_k_ids, relevantes)
        ap_q = calcular_average_precision_at_k(top_k_ids, relevantes, parciais, k=k)

        recalls_50.append(r50)
        hits_50.append(hit50)
        recalls_5.append(r5)
        hits_5.append(hit5)
        mrrs.append(mrr_q)
        aps_5.append(ap_q)
        por_tipo_top50[tipo].append(r50)
        por_tipo_top5[tipo].append(r5)

        rel_no_50 = set(top50_ids) & relevantes
        rel_no_5 = set(top_k_ids) & relevantes
        total_rel_top50 += len(rel_no_50)
        total_rel_top5 += len(rel_no_5)
        total_perdidos_rerank += len(rel_no_50 - rel_no_5)

        if ragas_disponivel:
            try:
                precisoes_ragas_id.append(pontuar_ragas_por_id(top_k_ids, sorted(relevantes)))
            except ImportError:
                ragas_disponivel = False

    scores_fora: list[float] = []
    if incluir_fora_da_base:
        for q_fora in _carregar_perguntas_fora_base():
            pares_f = fn_ranking(q_fora["pergunta"], metodo_efetivo, 1)
            if pares_f:
                scores_fora.append(float(pares_f[0][1]))

    n_q = max(len(itens_gabarito), 1)
    gaveta_2 = {
        "origem_metrica": "deterministico",
        "n_consultas": len(itens_gabarito),
        "top_candidatos": top_candidatos,
        "recall_at_50": round(sum(recalls_50) / n_q, 4),
        "consultas_com_relevante_top50_pct": round((sum(hits_50) / n_q) * 100.0, 1),
        "por_tipo": {
            tp: {
                "n": len(vals),
                "recall_at_50": round(sum(vals) / len(vals), 4),
                "recall_at_5": round(sum(por_tipo_top5[tp]) / len(por_tipo_top5[tp]), 4),
            }
            for tp, vals in sorted(por_tipo_top50.items())
        },
    }

    taxa_retencao = round(total_rel_top5 / total_rel_top50, 4) if total_rel_top50 > 0 else 0.0
    gaveta_3 = {
        "origem_metrica": "ragas_oficial" if ragas_disponivel and precisoes_ragas_id else "deterministico",
        "k": k,
        "recall_at_5": round(sum(recalls_5) / n_q, 4),
        "consultas_atendidas_pct": round((sum(hits_5) / n_q) * 100.0, 1),
        "mrr": round(sum(mrrs) / n_q, 4),
        "ap_at_5": round(sum(aps_5) / n_q, 4),
        "precisao_ragas_id": round(sum(precisoes_ragas_id) / len(precisoes_ragas_id), 4)
        if precisoes_ragas_id
        else None,
        "relevantes_no_top50": total_rel_top50,
        "relevantes_no_top5": total_rel_top5,
        "perdidos_no_rerank": total_perdidos_rerank,
        "taxa_retencao_top50_para_top5": taxa_retencao,
        "scores_top1": {
            "dentro_da_base": _resumo_scores(scores_dentro),
            "fora_da_base": _resumo_scores(scores_fora),
        },
    }

    # ------------------------------------------------------------------
    # Gaveta 4: Geração, Citações & Gate de Abstenção
    # ------------------------------------------------------------------
    limiar_raw = os.environ.get("RAG_RERANK_MIN_SCORE", "").strip()
    limiar_valor = float(limiar_raw) if limiar_raw else None
    calibracao_disponivel = _ler_calibracao_recusa()
    try:
        reg = avaliar_pipeline_registrado(gerador="haiku")
        ir = reg["metricas_relatorio_iris"]
        gaveta_4 = {
            "origem_metrica": "juiz_llm_snapshot",
            "gerador_referencia": ir["gerador"],
            "frases_sustentadas_pct": ir["frases_sustentadas_pct"],
            "citacoes_invalidas": ir["citacoes_invalidas"],
            "frases_sem_citacao": ir["frases_sem_citacao"],
            "kappa_cohen": ir["kappa_cohen"],
            "gate_recusa_ativo": limiar_valor is not None,
            "rag_rerank_min_score": limiar_valor,
            "calibracao_disponivel": calibracao_disponivel,
        }
    except OSError:
        gaveta_4 = {
            "origem_metrica": "nao_medido",
            "gate_recusa_ativo": limiar_valor is not None,
            "rag_rerank_min_score": limiar_valor,
            "calibracao_disponivel": calibracao_disponivel,
        }

    # ------------------------------------------------------------------
    # Diagnóstico Prioritário Acionável
    # ------------------------------------------------------------------
    diagnostico: list[dict[str, str]] = []
    if docs_sem_barreira_pedagogicos:
        diagnostico.append(
            {
                "gaveta": "1_corpus_e_filtros",
                "severidade": "alta" if len(docs_sem_barreira_pedagogicos) >= 3 else "media",
                "achado": (
                    f"{len(docs_sem_barreira_pedagogicos)} docs pedagógicos "
                    f"({chunks_sem_barreira} trechos buscáveis totais) estão sem tag de barreira."
                ),
                "acao": "Revisar barreiras em rag/iris-rag/fontes.json nos documentos pedagógicos e sincronizar chunks.jsonl.",
            }
        )
    elif chunks_sem_barreira > 0:
        diagnostico.append(
            {
                "gaveta": "1_corpus_e_filtros",
                "severidade": "info",
                "achado": (
                    f"{chunks_sem_barreira} trechos buscáveis "
                    f"({len(docs_sem_barreira_intencionais)} docs de legislação/neuromitos/inclusão geral) "
                    "estão intencionalmente sem tag de barreira."
                ),
                "acao": "Comportamento esperado: documentos normativos e transversais não são vinculados a uma barreira específica.",
            }
        )
    if gaveta_2["por_tipo"]:
        pior_tipo, pior_stats = min(gaveta_2["por_tipo"].items(), key=lambda kv: kv[1]["recall_at_50"])
        diagnostico.append(
            {
                "gaveta": "2_busca_top50",
                "severidade": "alta" if pior_stats["recall_at_50"] < 0.5 else "info",
                "achado": f"Menor cobertura no Top-{top_candidatos} está em '{pior_tipo}' (Recall@{top_candidatos}={pior_stats['recall_at_50']}).",
                "acao": "Reforçar guias práticos em PT-BR no corpus ou ajustar vocabulário/chunking para esse estrato.",
            }
        )
    if total_perdidos_rerank > 0:
        diagnostico.append(
            {
                "gaveta": "3_reranker_top5",
                "severidade": "media",
                "achado": f"{total_perdidos_rerank} de {total_rel_top50} trechos relevantes no Top-{top_candidatos} ficaram fora do Top-{k}.",
                "acao": "Avaliar reranker ou aumentar k entregue (ex.: k=10/20 em modelos com janela ampla).",
            }
        )
    if not gaveta_4["gate_recusa_ativo"]:
        diagnostico.append(
            {
                "gaveta": "4_geracao_e_abstencao",
                "severidade": "media",
                "achado": "Gate determinístico de recusa (RAG_RERANK_MIN_SCORE) está desligado.",
                "acao": _acao_gate_recusa(calibracao_disponivel),
            }
        )

    resultado: dict[str, Any] = {
        "metadados": {
            "frescor": "commit_atual",
            "git_commit": git_commit,
            "chunks_sha256": chunks_sha,
            "metodo_solicitado": metodo,
            "metodo_efetivo": metodo_efetivo,
            "modo_reduzido": modo_reduzido,
            "aviso_modo": aviso_modo,
            "origem_cache": False,
            "gerado_em": datetime.now(timezone.utc).isoformat(),
        },
        "gavetas": {
            "1_corpus_e_filtros": gaveta_1,
            "2_busca_top50": gaveta_2,
            "3_reranker_top5": gaveta_3,
            "4_geracao_e_abstencao": gaveta_4,
        },
        "diagnostico_prioritario": diagnostico,
    }
    if ranqueador is None:
        _gravar_cache_funil(chave_cache, resultado)
    return resultado


def formatar_relatorio_texto(funil: dict[str, Any]) -> str:
    meta = funil["metadados"]
    g1 = funil["gavetas"]["1_corpus_e_filtros"]
    g2 = funil["gavetas"]["2_busca_top50"]
    g3 = funil["gavetas"]["3_reranker_top5"]
    g4 = funil["gavetas"]["4_geracao_e_abstencao"]
    linhas = [
        "FUNIL DE CAUSA RAIZ DO RAG (4 GAVETAS — COMMIT ATUAL)",
        f"Commit: {meta['git_commit']} | Chunks SHA256: {meta['chunks_sha256']} | Método: {meta['metodo_efetivo']}"
        + (" (modo reduzido)" if meta["modo_reduzido"] else ""),
        "",
        f"[1. Corpus & Filtros] docs={g1['docs_com_barreira']}/{g1['docs_aceitos']} com barreira | "
        f"chunks buscáveis={g1['chunks_buscaveis']} (com_barreira={g1['chunks_com_barreira']}, sem_barreira={g1['chunks_sem_barreira']})",
        f"[2. Busca Top-{g2['top_candidatos']}] Recall@{g2['top_candidatos']}={g2['recall_at_50']} | "
        f"atendidas={g2['consultas_com_relevante_top50_pct']}%",
        f"[3. Top-{g3['k']}] Recall@{g3['k']}={g3['recall_at_5']} | MRR={g3['mrr']} | AP@{g3['k']}={g3['ap_at_5']} | "
        f"RAGAS ID={g3['precisao_ragas_id']} | perdidos_rerank={g3['perdidos_no_rerank']}/{g3['relevantes_no_top50']}",
        f"[4. Geração & Gate] gate_recusa_ativo={g4['gate_recusa_ativo']} "
        f"(RAG_RERANK_MIN_SCORE={g4['rag_rerank_min_score']}) | "
        f"snapshot_sustentadas={g4.get('frases_sustentadas_pct')}% ({g4['origem_metrica']})",
        "",
        "DIAGNÓSTICO PRIORITÁRIO:",
    ]
    for item in funil["diagnostico_prioritario"]:
        linhas.append(f"  - [{item['severidade'].upper()}] {item['achado']} -> {item['acao']}")
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Funil Vivo de Causa Raiz do RAG (4 Gavetas)")
    parser.add_argument("--metodo", default="auto", help="auto, bm25, qwen3+rerank50, etc.")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--top-candidatos", type=int, default=50)
    parser.add_argument("--sem-fora-base", action="store_true", help="Não consultar perguntas_fora_da_base_v1.json")
    parser.add_argument("--sem-cache", action="store_true", help="Ignora o cache e recalcula do zero")
    parser.add_argument("--json", action="store_true", help="Imprime JSON estruturado")
    args = parser.parse_args()

    res = executar_funil_rag(
        metodo=args.metodo,
        k=args.k,
        top_candidatos=args.top_candidatos,
        incluir_fora_da_base=not args.sem_fora_base,
        usar_cache=not args.sem_cache,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(formatar_relatorio_texto(res))


if __name__ == "__main__":
    main()
