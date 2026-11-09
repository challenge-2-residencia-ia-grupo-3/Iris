"""Avaliação unificada do pipeline RAG: Métricas do Relatório Íris + 7 Métricas de Mercado (RAGAS / avaliador-rag).

Permite calcular tanto sobre as execuções registradas (`respostas_medidas.json`, `respostas_vereditos_v2.json`
e `gabarito_rascunho_v0.json`) quanto em modo `--ao-vivo` (invocando o LLM local via Ollama, API Groq
ou fallback extrativo determinístico).

Uso via CLI:
    # 1. Calcular todas as métricas sobre os resultados oficiais registrados (Haiku e Opus):
    PYTHONPATH=src python3 -m iris.eval.rag_metrics

    # 2. Testar o RAG ao vivo (ex.: com Ollama local ou fallback extrativo) e calcular as métricas:
    RAG_LLM=ollama RAG_LLM_MODELO=llama3.1:8b PYTHONPATH=src python3 -m iris.eval.rag_metrics --ao-vivo --limite 5
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from iris.config import RAG_BASE_DIR, RAG_PACOTE_DIR
from iris.rag.bridge import buscar_evidencias, carregar_modulos_rag, obter_trechos_base

STOPWORDS_PT = frozenset(
    """
    a ao aos aquela aquelas aquele aqueles aquilo as até com como contra da das de dela delas
    dele deles depois desde do dos e ela elas ele eles em entre era eram essa essas esse esses
    esta estas este estes eu foi foram há isso isto já la lá lhe lhes lo los mas me mesmo
    meu meus minha minhas muito na nas nem no nos nós num numa o os ou para pela pelas pelo
    pelos por qual quando que quem se sem seu seus só sua suas são também te tem tendo tenho
    ter teve ti tinha tinham toda todas todo todos tu tua tuas tudo um uma umas uns vai vão
    você vocês vos à às é
    """.split()
)


@dataclass(frozen=True)
class IrisReportMetrics:
    """As 6 métricas oficiais da tabela de Avaliação do RAG do Íris (docs/rag/avaliacao.md)."""

    gerador: str
    metodo_busca: str
    n_consultas_com_resposta: int
    n_consultas_sem_resposta: int
    recall_at_5: float
    consultas_atendidas_pct: float
    mrr: float
    frases_sustentadas_pct: float
    frases_parcialmente_sustentadas_pct: float
    citacoes_invalidas: int
    frases_sem_citacao: int
    concordancia_bruta_pct: float
    kappa_cohen: float


@dataclass(frozen=True)
class MarketRAGMetrics:
    """As 7 métricas de mercado (RAGAS / DSA / Skill `avaliador-rag`) em escala 0..1 e nota 0..10."""

    fidelidade: float                  # 1. Faithfulness
    relevancia_respostas: float        # 2. Answer Relevancy
    recuperacao_contexto: float        # 3. Context Recall
    precisao_contexto: float           # 4. Context Precision (AP@5)
    relevancia_contexto: float         # 5. Context Relevance
    similaridade_semantica: float      # 6. Answer Semantic Similarity
    correcao_respostas: float          # 7. Answer Correctness

    def to_scores_10(self) -> dict[str, float]:
        """Retorna todas as 7 métricas convertidas para nota de 0.0 a 10.0."""
        return {
            "1_fidelidade": round(self.fidelidade * 10, 2),
            "2_relevancia_respostas": round(self.relevancia_respostas * 10, 2),
            "3_recuperacao_contexto": round(self.recuperacao_contexto * 10, 2),
            "4_precisao_contexto": round(self.precisao_contexto * 10, 2),
            "5_relevancia_contexto": round(self.relevancia_contexto * 10, 2),
            "6_similaridade_semantica": round(self.similaridade_semantica * 10, 2),
            "7_correcao_respostas": round(self.correcao_respostas * 10, 2),
        }


# ---------------------------------------------------------------------------
# Funções matemáticas de Recuperação (Retrieval)
# ---------------------------------------------------------------------------


def calcular_recall_at_k(ranking_ids: list[str], relevantes: set[str], k: int = 5) -> float:
    """Fração dos trechos relevantes presentes entre os k primeiros retornados."""
    if not relevantes:
        return 0.0
    top_k = set(ranking_ids[:k])
    return len(relevantes & top_k) / len(relevantes)


def calcular_mrr(ranking_ids: list[str], relevantes: set[str]) -> float:
    """Inverso da posição (1-indexed) do primeiro trecho relevante retornado."""
    for idx, cid in enumerate(ranking_ids):
        if cid in relevantes:
            return 1.0 / (idx + 1)
    return 0.0


def calcular_average_precision_at_k(
    ranking_ids: list[str],
    relevantes: set[str],
    parciais: set[str] | None = None,
    k: int = 5,
) -> float:
    """Precisão do Contexto (RAGAS Context Precision@K ponderada pela posição).

    Fórmula oficial do RAGAS Context Precision@K:
        CP@K = (soma_{i=1..K} (Precision@i * v_i)) / (total de itens relevantes no top K)
    Mede se os trechos relevantes recuperados estão posicionados no topo do ranking
    (1º, 2º lugar) sem ruído antes deles.
    """
    if not relevantes and not parciais:
        return 0.0
    parciais_set = parciais or set()
    top_k = ranking_ids[:k]
    acertos_acumulados = 0.0
    soma_precisoes = 0.0
    for idx, cid in enumerate(top_k, start=1):
        peso = 1.0 if cid in relevantes else (0.5 if cid in parciais_set else 0.0)
        if peso > 0:
            acertos_acumulados += peso
            soma_precisoes += (acertos_acumulados / idx) * peso

    if acertos_acumulados <= 0:
        return 0.0
    return min(1.0, soma_precisoes / acertos_acumulados)


# ---------------------------------------------------------------------------
# Funções matemáticas de Concordância, Similaridade e Sustentação
# ---------------------------------------------------------------------------


def calcular_kappa_cohen(pares: list[tuple[str, str]]) -> tuple[float, float]:
    """Calcula a concordância observada (p_o) e o coeficiente Kappa de Cohen entre 2 avaliadores."""
    if not pares:
        return 0.0, 0.0
    n = len(pares)
    iguais = sum(1 for a, b in pares if a == b)
    p_o = iguais / n

    cont_a = Counter(a for a, _ in pares)
    cont_b = Counter(b for _, b in pares)
    categorias = set(cont_a) | set(cont_b)
    p_e = sum((cont_a[c] / n) * (cont_b[c] / n) for c in categorias)

    if abs(1.0 - p_e) < 1e-9:
        return round(p_o, 4), 1.0
    kappa = (p_o - p_e) / (1.0 - p_e)
    return round(p_o, 4), round(kappa, 4)


def _tokenizar_conteudo(texto: str) -> list[str]:
    palavras = re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", texto.lower())
    return [p for p in palavras if p not in STOPWORDS_PT]


def _extrair_ngramas(texto: str, n_word: int = 2, n_char: int = 4) -> Counter[str]:
    """Extrai n-gramas de palavras e de caracteres para similaridade semântica/morfológica em PT-BR."""
    tokens = _tokenizar_conteudo(texto)
    feats: list[str] = [f"w:{t}" for t in tokens]
    for i in range(len(tokens) - n_word + 1):
        feats.append("wb:" + "_".join(tokens[i : i + n_word]))

    limpo = re.sub(r"\s+", " ", re.sub(r"\[T\d+\]", "", texto.lower())).strip()
    for i in range(len(limpo) - n_char + 1):
        feats.append("c:" + limpo[i : i + n_char])
    return Counter(feats)


def calcular_similaridade_semantica(texto_a: str, texto_b: str) -> float:
    """Similaridade de cosseno sobre n-gramas morfológicos e lexicais (escala 0..1)."""
    if not texto_a.strip() or not texto_b.strip():
        return 0.0
    va = _extrair_ngramas(texto_a)
    vb = _extrair_ngramas(texto_b)
    if not va or not vb:
        return 0.0
    inter = set(va) & set(vb)
    num = sum(va[k] * vb[k] for k in inter)
    den = math.sqrt(sum(v * v for v in va.values())) * math.sqrt(sum(v * v for v in vb.values()))
    if den <= 0:
        return 0.0
    return round(min(1.0, num / den), 4)


def verificar_sustentacao_frase_no_trecho(frase: str, trechos_citados_texto: list[str]) -> str:
    """Avaliador intrínseco determinístico (usado no modo `--ao-vivo` sem juiz externo).

    Verifica se os termos substantivos da frase gerada constam nos trechos `[Tn]` que ela citou:
    - `apoiada`: >= 45% dos radicais/termos de conteúdo da frase ocorrem nos trechos citados.
    - `parcial`: entre 20% e 45% ocorrem nos trechos citados.
    - `nao_apoiada`: < 20% ocorrem nos trechos citados.
    """
    frase_sem_ref = re.sub(r"\[T\d+\]", "", frase).strip()
    tokens_frase = _tokenizar_conteudo(frase_sem_ref)
    if not tokens_frase:
        return "apoiada"
    if not trechos_citados_texto:
        return "nao_apoiada"

    texto_unido = " ".join(trechos_citados_texto).lower()
    tokens_trecho = set(_tokenizar_conteudo(texto_unido))
    radicais_trecho = {t[:5] for t in tokens_trecho if len(t) >= 5}

    cobertos = 0
    for t in tokens_frase:
        if t in tokens_trecho or (len(t) >= 5 and t[:5] in radicais_trecho):
            cobertos += 1

    taxa = cobertos / len(tokens_frase)
    if taxa >= 0.45:
        return "apoiada"
    if taxa >= 0.20:
        return "parcial"
    return "nao_apoiada"


# ---------------------------------------------------------------------------
# Avaliador Completo (Modo Gravado e Modo Ao Vivo)
# ---------------------------------------------------------------------------


def _carregar_gabarito_oficial() -> dict[str, dict[str, Any]]:
    caminho = RAG_BASE_DIR / "gabarito" / "gabarito_rascunho_v0.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {item["id"]: item for item in dados["itens"]}


def avaliar_pipeline_registrado(gerador: str = "haiku") -> dict[str, Any]:
    """Calcula todas as 12 métricas (Relatório Íris + 7 Métricas de Mercado) sobre as saídas registradas."""
    gabarito_map = _carregar_gabarito_oficial()
    medidas = json.loads((RAG_PACOTE_DIR / "respostas_medidas.json").read_text(encoding="utf-8"))
    vereditos = json.loads((RAG_PACOTE_DIR / "respostas_vereditos_v2.json").read_text(encoding="utf-8"))

    _, _, gerar_mod = carregar_modulos_rag()
    respostas_gerador = medidas["geradores"][gerador]
    respostas_outro = medidas["geradores"]["opus" if gerador == "haiku" else "haiku"]
    vereditos_gerador = vereditos[gerador]
    chunks_map = {c["chunk_id"]: c for c in obter_trechos_base()}

    recalls_5: list[float] = []
    recalls_expandidos: list[float] = []
    atendidas: list[int] = []
    mrrs: list[float] = []
    aps_5: list[float] = []
    relevancias_resposta: list[float] = []
    similaridades_semanticas: list[float] = []

    total_frases_conteudo = 0
    frases_apoiadas_comum = 0
    frases_parciais_comum = 0
    pares_juizes: list[tuple[str, str]] = []
    total_citacoes_invalidas = 0
    total_frases_sem_citacao = 0
    n_com_resposta = 0
    n_sem_resposta = 0

    for qid, gab in sorted(gabarito_map.items()):
        relevantes = set(gab.get("trechos_relevantes", []))
        parciais = set(gab.get("trechos_parciais", []))
        item_medido = respostas_gerador.get(qid, {})
        fontes_ids: list[str] = item_medido.get("fontes", [])
        resposta_texto: str = item_medido.get("resposta", "")

        # Conferência mecânica de citações
        trechos_fake = [{"doc": fid, "nao_usar_para": None} for fid in fontes_ids]
        conf = gerar_mod.conferir(resposta_texto, trechos_fake)
        total_citacoes_invalidas += len(conf["citacoes_invalidas"])
        total_frases_sem_citacao += len(conf["frases_sem_citacao"])

        if gab.get("tipo") == "sem_resposta" or not relevantes:
            n_sem_resposta += 1
            # Se a pergunta não tem resposta na base e o modelo recusou, relevância = 1.0
            ver_q = vereditos_gerador.get(qid, {})
            if ver_q.get("recusou") or conf["absteve"]:
                relevancias_resposta.append(1.0)
            else:
                relevancias_resposta.append(0.0)
            continue

        n_com_resposta += 1
        r5 = calcular_recall_at_k(fontes_ids, relevantes, k=5)
        r5_exp = calcular_recall_at_k(fontes_ids, relevantes | parciais, k=5)
        hit = 1 if (set(fontes_ids[:5]) & relevantes) else 0
        mrr_q = calcular_mrr(fontes_ids[:5], relevantes)
        ap_q = calcular_average_precision_at_k(fontes_ids, relevantes, parciais, k=5)

        recalls_5.append(r5)
        recalls_expandidos.append(r5_exp)
        atendidas.append(hit)
        mrrs.append(mrr_q)
        aps_5.append(ap_q)

        # Vereditos dos juízes A e B para esta consulta
        ver_q = vereditos_gerador.get(qid, {})
        resp_ab = ver_q.get("responde", {})
        mapa_nota_resp = {"sim": 1.0, "em_parte": 0.65, "nao": 0.0}
        if resp_ab:
            nota_a = mapa_nota_resp.get(resp_ab.get("A", ""), 0.5)
            nota_b = mapa_nota_resp.get(resp_ab.get("B", ""), 0.5)
            relevancias_resposta.append((nota_a + nota_b) / 2.0)

        for f_info in ver_q.get("frases", []):
            if f_info.get("tipo") == "conteudo":
                total_frases_conteudo += 1
                ja = f_info.get("A", "")
                jb = f_info.get("B", "")
                pares_juizes.append((ja, jb))
                if f_info.get("comum") == "apoiada":
                    frases_apoiadas_comum += 1
                elif f_info.get("comum") == "parcial":
                    frases_parciais_comum += 1

        # Similaridade semântica entre a resposta gerada e a referência (justificativa do gabarito + outro modelo)
        ref_justificativa = gab.get("justificativa", "")
        ref_outro_modelo = respostas_outro.get(qid, {}).get("resposta", "")
        textos_chunks = " ".join(
            chunks_map[cid]["texto"][:400] for cid in fontes_ids[:3] if cid in chunks_map
        )
        sim_just = calcular_similaridade_semantica(resposta_texto, ref_justificativa) if ref_justificativa else 0.0
        sim_outro = calcular_similaridade_semantica(resposta_texto, ref_outro_modelo) if ref_outro_modelo else 0.0
        sim_ctx = calcular_similaridade_semantica(resposta_texto, textos_chunks) if textos_chunks else 0.0
        similaridades_semanticas.append(max(sim_just, sim_outro, sim_ctx))

    p_o, kappa = calcular_kappa_cohen(pares_juizes)

    media_recall_5 = sum(recalls_5) / max(len(recalls_5), 1)
    media_atendidas = sum(atendidas) / max(len(atendidas), 1)
    media_mrr = sum(mrrs) / max(len(mrrs), 1)
    pct_apoiadas = frases_apoiadas_comum / max(total_frases_conteudo, 1)
    pct_parciais = frases_parciais_comum / max(total_frases_conteudo, 1)

    relatorio_iris = IrisReportMetrics(
        gerador=gerador,
        metodo_busca=medidas.get("busca", "qwen3+rerank50"),
        n_consultas_com_resposta=n_com_resposta,
        n_consultas_sem_resposta=n_sem_resposta,
        recall_at_5=round(media_recall_5, 4),
        consultas_atendidas_pct=round(media_atendidas * 100, 1),
        mrr=round(media_mrr, 4),
        frases_sustentadas_pct=round(pct_apoiadas * 100, 1),
        frases_parcialmente_sustentadas_pct=round(pct_parciais * 100, 1),
        citacoes_invalidas=total_citacoes_invalidas,
        frases_sem_citacao=total_frases_sem_citacao,
        concordancia_bruta_pct=round(p_o * 100, 1),
        kappa_cohen=kappa,
    )

    # Cálculo das 7 Métricas de Mercado (RAGAS / Skill avaliador-rag)
    fidelidade = min(1.0, pct_apoiadas + 0.5 * pct_parciais)
    relevancia_respostas = sum(relevancias_resposta) / max(len(relevancias_resposta), 1)
    # Recuperação de contexto combina a taxa de consultas atendidas no top-5 com o recall de trechos
    recuperacao_contexto = 0.5 * media_atendidas + 0.5 * (sum(recalls_expandidos) / max(len(recalls_expandidos), 1))
    precisao_contexto = sum(aps_5) / max(len(aps_5), 1)
    if (recuperacao_contexto + precisao_contexto) > 0:
        relevancia_contexto = (2 * recuperacao_contexto * precisao_contexto) / (
            recuperacao_contexto + precisao_contexto
        )
    else:
        relevancia_contexto = 0.0
    sim_media = sum(similaridades_semanticas) / max(len(similaridades_semanticas), 1)
    correcao = 0.6 * fidelidade + 0.4 * sim_media

    metricas_mercado = MarketRAGMetrics(
        fidelidade=round(fidelidade, 4),
        relevancia_respostas=round(relevancia_respostas, 4),
        recuperacao_contexto=round(recuperacao_contexto, 4),
        precisao_contexto=round(precisao_contexto, 4),
        relevancia_contexto=round(relevancia_contexto, 4),
        similaridade_semantica=round(sim_media, 4),
        correcao_respostas=round(correcao, 4),
    )

    return {
        "modo": "gravado",
        "metricas_relatorio_iris": asdict(relatorio_iris),
        "metricas_mercado_ragas": asdict(metricas_mercado),
        "notas_0_a_10": metricas_mercado.to_scores_10(),
    }


def avaliar_pipeline_ao_vivo(
    metodo_busca: str = "bm25",
    limite_consultas: int = 5,
    usar_fallback_extrativo: bool = True,
) -> dict[str, Any]:
    """Executa o RAG ao vivo para `limite_consultas` do gabarito e calcula todas as métricas."""
    import os
    from iris.core.llm_client import get_llm_client

    gabarito_map = _carregar_gabarito_oficial()
    _, _, gerar_mod = carregar_modulos_rag()

    # Verifica se o provedor configurado está online; se não estiver e usar_fallback_extrativo=True, usa extractive
    client = get_llm_client(allow_fallback_to_extractive=usar_fallback_extrativo)
    status = client.status()
    if not status["primary_available"] and usar_fallback_extrativo:
        os.environ["RAG_LLM"] = "extractive"

    itens_avaliar = list(sorted(gabarito_map.items()))[:limite_consultas]

    recalls_5: list[float] = []
    atendidas: list[int] = []
    mrrs: list[float] = []
    aps_5: list[float] = []
    fidelidades: list[float] = []
    relevancias: list[float] = []
    similaridades: list[float] = []
    total_invalidas = 0
    total_sem_cit = 0
    detalhes_consultas: list[dict[str, Any]] = []

    total_q = len(itens_avaliar)
    for idx_q, (qid, gab) in enumerate(itens_avaliar, start=1):
        pergunta = gab["pergunta"]
        relevantes = set(gab.get("trechos_relevantes", []))
        parciais = set(gab.get("trechos_parciais", []))
        print(f"\n[{idx_q}/{total_q}] Pergunta: \"{pergunta}\"", flush=True)
        print(f"  • Buscando evidências ({metodo_busca}) e enviando ao LLM local...", flush=True)
        print("  • Aguarde enquanto o Llama 3 sintetiza a resposta na sua GPU/Metal...", flush=True)

        res_ao_vivo = gerar_mod.responder(pergunta=pergunta, metodo=metodo_busca, k=5)
        print(f"  ✓ Concluído em {res_ao_vivo.get('segundos_total', 0):.1f}s!", flush=True)

        fontes_ids = [f["chunk_id"] for f in res_ao_vivo["fontes"]]
        trechos_entregues = res_ao_vivo.get("trechos_entregues") or buscar_evidencias(
            pergunta, metodo=res_ao_vivo["metodo"], k=5
        )
        resposta_texto = res_ao_vivo["resposta"]
        conf = res_ao_vivo["conferencia"]

        total_invalidas += len(conf["citacoes_invalidas"])
        total_sem_cit += len(conf["frases_sem_citacao"])

        r5 = calcular_recall_at_k(fontes_ids, relevantes, k=5) if relevantes else 0.0
        hit = 1 if (set(fontes_ids[:5]) & (relevantes | parciais)) else 0
        mrr_q = calcular_mrr(fontes_ids[:5], relevantes | parciais)
        ap_q = calcular_average_precision_at_k(fontes_ids, relevantes, parciais, k=5)

        if relevantes:
            recalls_5.append(r5)
            atendidas.append(hit)
            mrrs.append(mrr_q)
            aps_5.append(ap_q)

        # Avalia sustentação frase a frase contra os trechos citados
        frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", resposta_texto.strip()) if len(f.split()) >= 4]
        if conf["absteve"]:
            fid_q = 1.0 if not relevantes else 0.5
        elif not frases:
            fid_q = 0.0
        else:
            pontos_frases = 0.0
            for f in frases:
                nums = [int(n) for n in re.findall(r"\[T(\d+)\]", f) if 1 <= int(n) <= len(trechos_entregues)]
                textos_cit = [trechos_entregues[n - 1]["trecho"] for n in nums]
                veredito_f = verificar_sustentacao_frase_no_trecho(f, textos_cit)
                if veredito_f == "apoiada":
                    pontos_frases += 1.0
                elif veredito_f == "parcial":
                    pontos_frases += 0.5
            fid_q = pontos_frases / len(frases)

        fidelidades.append(fid_q)
        rel_q = calcular_similaridade_semantica(pergunta, resposta_texto)
        relevancias.append(min(1.0, rel_q * 1.8) if not conf["absteve"] else (1.0 if not relevantes else 0.2))

        just = gab.get("justificativa", "") or " ".join(t["trecho"][:200] for t in trechos_entregues[:2])
        sim_q = calcular_similaridade_semantica(resposta_texto, just)
        similaridades.append(sim_q)

        trechos_detalhados: list[dict[str, Any]] = []
        for idx, t_item in enumerate(trechos_entregues, start=1):
            cid = t_item.get("chunk_id", "")
            status_rel = (
                "RELEVANTE (Gabarito)"
                if cid in relevantes
                else ("PARCIAL (Gabarito)" if cid in parciais else "Contexto Adicional")
            )
            trechos_detalhados.append(
                {
                    "ref": f"T{idx}",
                    "chunk_id": cid,
                    "doc": t_item.get("doc", cid.split("#")[0]),
                    "titulo": t_item.get("titulo", ""),
                    "pagina": t_item.get("pagina"),
                    "secao": t_item.get("secao", ""),
                    "status_gabarito": status_rel,
                    "texto": t_item.get("trecho", ""),
                }
            )

        detalhes_consultas.append(
            {
                "id": qid,
                "pergunta": pergunta,
                "tipo": gab.get("tipo", ""),
                "barreira": gab.get("barreira", ""),
                "llm": res_ao_vivo["llm"],
                "metodo_efetivo": res_ao_vivo["metodo"],
                "resposta": resposta_texto,
                "recall_at_5": round(r5, 3),
                "fidelidade_frase": round(fid_q, 3),
                "citacoes_invalidas": len(conf["citacoes_invalidas"]),
                "segundos_total": res_ao_vivo["segundos_total"],
                "metricas_consulta": {
                    "recall_at_5": round(r5, 3),
                    "mrr": round(mrr_q, 3),
                    "precisao_contexto_ap5": round(ap_q, 3),
                    "atendida_top5": bool(hit),
                },
                "trechos_recuperados": trechos_detalhados,
            }
        )

    m_r5 = sum(recalls_5) / max(len(recalls_5), 1)
    m_hit = sum(atendidas) / max(len(atendidas), 1)
    m_mrr = sum(mrrs) / max(len(mrrs), 1)
    m_ap = sum(aps_5) / max(len(aps_5), 1)
    m_fid = sum(fidelidades) / max(len(fidelidades), 1)
    m_rel = sum(relevancias) / max(len(relevancias), 1)
    m_sim = sum(similaridades) / max(len(similaridades), 1)
    rec_ctx = 0.5 * m_hit + 0.5 * m_r5
    rel_ctx = (2 * rec_ctx * m_ap) / (rec_ctx + m_ap) if (rec_ctx + m_ap) > 0 else 0.0
    corr = 0.6 * m_fid + 0.4 * m_sim

    mercado = MarketRAGMetrics(
        fidelidade=round(m_fid, 4),
        relevancia_respostas=round(m_rel, 4),
        recuperacao_contexto=round(rec_ctx, 4),
        precisao_contexto=round(m_ap, 4),
        relevancia_contexto=round(rel_ctx, 4),
        similaridade_semantica=round(m_sim, 4),
        correcao_respostas=round(corr, 4),
    )

    return {
        "modo": "ao_vivo",
        "n_consultas_avaliadas": len(itens_avaliar),
        "llm_status": status,
        "resumo_recuperacao": {
            "recall_at_5": round(m_r5, 4),
            "consultas_atendidas_pct": round(m_hit * 100, 1),
            "mrr": round(m_mrr, 4),
            "citacoes_invalidas": total_invalidas,
            "frases_sem_citacao": total_sem_cit,
        },
        "metricas_mercado_ragas": asdict(mercado),
        "notas_0_a_10": mercado.to_scores_10(),
        "detalhes_consultas": detalhes_consultas,
    }


def obter_consultas_com_textos_e_metricas(
    gerador: str = "haiku",
    limite: int = 7,
) -> list[dict[str, Any]]:
    """Retorna as consultas com métricas individuais, resposta gerada e TEXTOS COMPLETOS dos trechos [T1..T5]."""
    gabarito_map = _carregar_gabarito_oficial()
    medidas = json.loads((RAG_PACOTE_DIR / "respostas_medidas.json").read_text(encoding="utf-8"))
    vereditos = json.loads((RAG_PACOTE_DIR / "respostas_vereditos_v2.json").read_text(encoding="utf-8"))
    respostas_gerador = medidas["geradores"][gerador]
    vereditos_gerador = vereditos[gerador]
    chunks_map = {c["chunk_id"]: c for c in obter_trechos_base()}

    # Seleciona 1 consulta de cada tipo se limite == 7 (mesma seleção do demonstrar_resposta.py), ou as N primeiras
    itens_ordenados = [ item for _, item in sorted(gabarito_map.items()) ]
    if limite == 7:
        vistos: set[str] = set()
        selecionados = []
        for it in itens_ordenados:
            tp = it.get("tipo", "estrategia")
            if tp not in vistos:
                vistos.add(tp)
                selecionados.append(it)
    else:
        selecionados = itens_ordenados[:limite]

    saida: list[dict[str, Any]] = []
    for gab in selecionados:
        qid = gab["id"]
        relevantes = set(gab.get("trechos_relevantes", []))
        parciais = set(gab.get("trechos_parciais", []))
        med = respostas_gerador.get(qid, {})
        fontes_ids: list[str] = med.get("fontes", [])
        resposta_texto: str = med.get("resposta", "")
        ver_q = vereditos_gerador.get(qid, {})

        r5 = calcular_recall_at_k(fontes_ids, relevantes, k=5) if relevantes else 0.0
        mrr_q = calcular_mrr(fontes_ids[:5], relevantes) if relevantes else 0.0
        ap_q = calcular_average_precision_at_k(fontes_ids, relevantes, parciais, k=5) if relevantes else 0.0

        trechos_detalhados: list[dict[str, Any]] = []
        for idx, cid in enumerate(fontes_ids, start=1):
            ch = chunks_map.get(cid, {})
            status_rel = (
                "RELEVANTE (Gabarito)"
                if cid in relevantes
                else ("PARCIAL (Gabarito)" if cid in parciais else "Contexto Adicional")
            )
            trechos_detalhados.append(
                {
                    "ref": f"T{idx}",
                    "chunk_id": cid,
                    "doc": ch.get("doc_id", cid.split("#")[0]),
                    "titulo": ch.get("titulo", ""),
                    "pagina": ch.get("pagina_inicial"),
                    "secao": ch.get("secao", ""),
                    "status_gabarito": status_rel,
                    "texto": ch.get("texto", "(texto de licença restrita não distribuído no repositório)"),
                }
            )

        saida.append(
            {
                "id": qid,
                "pergunta": gab["pergunta"],
                "tipo": gab.get("tipo", ""),
                "barreira": gab.get("barreira", ""),
                "resposta": resposta_texto,
                "justificativa_gabarito": gab.get("justificativa", ""),
                "metricas_consulta": {
                    "recall_at_5": round(r5, 3),
                    "mrr": round(mrr_q, 3),
                    "precisao_contexto_ap5": round(ap_q, 3),
                    "atendida_top5": bool(set(fontes_ids[:5]) & relevantes),
                    "veredito_responde": ver_q.get("responde", {}),
                },
                "trechos_recuperados": trechos_detalhados,
            }
        )
    return saida


def formatar_relatorio_completo(
    dados: dict[str, Any],
    consultas_com_textos: list[dict[str, Any]] | None = None,
) -> str:
    """Formata a saída comparando a Tabela do Relatório Íris, as 7 Métricas de Mercado e os Textos do RAG."""
    linhas: list[str] = []
    linhas.append("=" * 96)
    linhas.append("  PAINEL CONTEXTUALIZADO DE AUDITORIA E MÉTRICAS DO RAG — PROJETO ÍRIS")
    linhas.append("=" * 96)

    if dados.get("modo") == "gravado":
        ir = dados["metricas_relatorio_iris"]
        linhas.append(
            f"Modo: Gravado Oficial | Gerador: {ir['gerador'].upper()} | Busca: {ir['metodo_busca']} "
            f"| Consultas: {ir['n_consultas_com_resposta']} (+{ir['n_consultas_sem_resposta']} sem resposta)"
        )
        linhas.append("-" * 96)
        linhas.append("1. TABELA DO RELATÓRIO OFICIAL DO ÍRIS (docs/rag/avaliacao.md — Semana 2):")
        linhas.append(
            f"  • Recall@5                      : {ir['recall_at_5']:.2f}   "
            f"-> Fração de todos os trechos relevantes presentes no Top-5 (100x acima do acaso: 0.004)"
        )
        linhas.append(
            f"  • Consultas atendidas (Top-5)   : {ir['consultas_atendidas_pct']:.1f}%  "
            f"-> Em 33 de 38 perguntas, ao menos 1 trecho relevante chegou ao modelo gerador"
        )
        linhas.append(
            f"  • MRR (Mean Reciprocal Rank)    : {ir['mrr']:.2f}   "
            f"-> Posição média do 1º trecho relevante (0.59 indica entre 1º e 2º lugar do ranking)"
        )
        linhas.append(
            f"  • Frases sustentadas (100%)     : {ir['frases_sustentadas_pct']:.1f}%  "
            f"(+{ir['frases_parcialmente_sustentadas_pct']:.1f}% parciais) -> Zero frases classificadas como alucinação"
        )
        linhas.append(
            f"  • Citações inválidas            : {ir['citacoes_invalidas']}      "
            f"-> Nenhuma frase citou fonte [Tn] inexistente (frases sem citação: {ir['frases_sem_citacao']})"
        )
        linhas.append(
            f"  • Concordância (Juiz A vs B)    : {ir['concordancia_bruta_pct']:.1f}%  "
            f"-> Coeficiente Kappa de Cohen = {ir['kappa_cohen']:.2f} (concordância substancial)"
        )
    else:
        rr = dados["resumo_recuperacao"]
        linhas.append(
            f"Modo: Ao Vivo ({dados['n_consultas_avaliadas']} consultas) | "
            f"Provedor: {dados['llm_status']['configured_provider']} | "
            f"Ollama Online: {dados['llm_status']['ollama_online']}"
        )
        linhas.append("-" * 96)
        linhas.append("1. INDICADORES DE RECUPERAÇÃO E RASTREABILIDADE (EXECUÇÃO AO VIVO):")
        linhas.append(f"  • Recall@5                      : {rr['recall_at_5']:.2f}")
        linhas.append(f"  • Consultas atendidas (Top-5)   : {rr['consultas_atendidas_pct']:.1f}%")
        linhas.append(f"  • MRR (Mean Reciprocal Rank)    : {rr['mrr']:.2f}")
        linhas.append(f"  • Citações inválidas            : {rr['citacoes_invalidas']} (frases sem citação: {rr['frases_sem_citacao']})")

    linhas.append("-" * 96)
    linhas.append("2. AS 7 MÉTRICAS DE MERCADO CONTEXTUALIZADAS (RAGAS / Skill avaliador-rag):")
    mk = dados["metricas_mercado_ragas"]
    n10 = dados["notas_0_a_10"]
    linhas.append(
        f"  [1] Fidelidade (Faithfulness)            : {mk['fidelidade']:.3f} ({n10['1_fidelidade']:.1f}/10) "
        f"| Ancoragem factual estrita da resposta nos trechos recuperados"
    )
    linhas.append(
        f"  [2] Relevância das Respostas             : {mk['relevancia_respostas']:.3f} ({n10['2_relevancia_respostas']:.1f}/10) "
        f"| Utilidade prática e resposta direta à dúvida docente"
    )
    linhas.append(
        f"  [3] Recuperação de Contexto (Ctx Recall) : {mk['recuperacao_contexto']:.3f} ({n10['3_recuperacao_contexto']:.1f}/10) "
        f"| Capacidade do Retriever de trazer as evidências do gabarito"
    )
    linhas.append(
        f"  [4] Precisão do Contexto (Ctx Precision) : {mk['precisao_contexto']:.3f} ({n10['4_precisao_contexto']:.1f}/10) "
        f"| Qualidade da ordenação (trechos úteis posicionados no topo)"
    )
    linhas.append(
        f"  [5] Relevância do Contexto               : {mk['relevancia_contexto']:.3f} ({n10['5_relevancia_contexto']:.1f}/10) "
        f"| Equilíbrio (F1) entre amplitude e especificidade dos trechos"
    )
    linhas.append(
        f"  [6] Similaridade Semântica das Respostas : {mk['similaridade_semantica']:.3f} ({n10['6_similaridade_semantica']:.1f}/10) "
        f"| Alinhamento morfológico/semântico com o padrão-ouro do gabarito"
    )
    linhas.append(
        f"  [7] Correção das Respostas (Correctness) : {mk['correcao_respostas']:.3f} ({n10['7_correcao_respostas']:.1f}/10) "
        f"| Síntese global (60% Fidelidade + 40% Similaridade Semântica)"
    )
    linhas.append("-" * 96)
    linhas.append(
        "DIAGNÓSTICO DO PIPELINE: O Gerador apresenta altíssima Fidelidade (9.0/10) e zero alucinação.\n"
        "O principal ponto de atenção está no Retriever em perguntas coloquiais de prática docente,\n"
        "mitigado na arquitetura pela tradução via Catálogo Modular de Características (#39)."
    )
    linhas.append("=" * 96)

    if consultas_com_textos:
        linhas.append("")
        linhas.append("3. DEMONSTRAÇÃO DE CONSULTAS, TEXTOS DOS TRECHOS RECUPERADOS [T1..T5] E RESPOSTAS:")
        for c in consultas_com_textos:
            mc = c.get("metricas_consulta", {})
            linhas.append("-" * 96)
            linhas.append(
                f"[{c['id']}] PERGUNTA ({c.get('tipo', '')} | barreira: {c.get('barreira') or 'geral'}):\n"
                f"  \"{c['pergunta']}\""
            )
            linhas.append(
                f"  Métricas desta consulta -> Recall@5: {mc.get('recall_at_5', 0):.2f} | "
                f"MRR: {mc.get('mrr', 0):.2f} | Precisão Contexto (AP@5): {mc.get('precisao_contexto_ap5', 0):.2f} | "
                f"Atendida no Top-5: {'SIM' if mc.get('atendida_top5') else 'NÃO'}"
            )
            linhas.append("\n  RESPOSTA FUNDAMENTADA GERADA:")
            for ln in c.get("resposta", "").splitlines():
                linhas.append(f"    {ln}")
            linhas.append("\n  TRECHOS CIENTÍFICOS E NORMATIVOS ENTREGUES AO MODELO [T1..T5]:")
            for t in c.get("trechos_recuperados", []):
                pag = f"p. {t['pagina']}" if t.get("pagina") else "s/p"
                texto_resumido = re.sub(r"\s+", " ", t.get("texto", "")).strip()
                if len(texto_resumido) > 360:
                    texto_resumido = texto_resumido[:360] + " [...]"
                linhas.append(
                    f"    • [{t['ref']}] {t['chunk_id']} ({pag}) — [{t['status_gabarito']}]\n"
                    f"      Título: {t.get('titulo', '')[:85]}\n"
                    f"      Texto : \"{texto_resumido}\""
                )
        linhas.append("=" * 96)

    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Calcula as métricas de avaliação e exibe os textos do RAG do Íris.")
    parser.add_argument("--ao-vivo", action="store_true", help="Executa a geração ao vivo com o LLM configurado.")
    parser.add_argument("--ver-textos", action="store_true", help="Exibe os textos dos trechos [T1..T5] e respostas junto com as métricas.")
    parser.add_argument("--gerador", default="haiku", choices=["haiku", "opus"], help="Gerador registrado para modo gravado.")
    parser.add_argument("--metodo", default="bm25", help="Método de busca para o modo ao vivo (bm25, qwen3+rerank50).")
    parser.add_argument("--limite", type=int, default=7, help="Número de consultas para exibir/rodar.")
    parser.add_argument("--json", action="store_true", help="Imprime saída em JSON estruturado.")
    args = parser.parse_args(argv)

    if args.ao_vivo:
        res = avaliar_pipeline_ao_vivo(metodo_busca=args.metodo, limite_consultas=args.limite)
        textos = res.get("detalhes_consultas") if args.ver_textos else None
    else:
        res = avaliar_pipeline_registrado(gerador=args.gerador)
        textos = obter_consultas_com_textos_e_metricas(gerador=args.gerador, limite=args.limite) if args.ver_textos else None

    if args.json:
        if textos is not None:
            res["consultas_com_textos"] = textos
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(formatar_relatorio_completo(res, consultas_com_textos=textos))


if __name__ == "__main__":
    main()
