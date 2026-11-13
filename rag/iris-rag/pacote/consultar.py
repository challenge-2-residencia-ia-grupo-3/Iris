"""consultar.py: a consulta do Agente Estrategista do Íris -> os 5 trechos mais úteis, com a fonte.

    buscar(pergunta, metodo, k=5, filtro_barreira=None, filtro_parte=None) -> trechos com doc, página,
    seção, score, URL, tipo de evidência e aviso de uso

Métodos: 'bm25' (palavra), 'mpnet' e 'qwen3' (sentido, no pgvector), 'hibrido' (BM25 + denso por RRF)
e 'hibrido+rerank' (os 20 primeiros da híbrida reordenados por um cross-encoder, que lê pergunta e
trecho JUNTOS em vez de comparar dois vetores feitos separadamente).
Rodar a demonstração:  .venv/bin/python consultar.py     (grava outputs/03-demonstracao.txt)
"""
from __future__ import annotations

import os
import re
import time
from functools import lru_cache
from pathlib import Path

import embeddings as emb
import ingestao

AQUI = Path(__file__).resolve().parent
METODOS = ["bm25", "mpnet", "qwen3", "hibrido", "hibrido+rerank", "qwen3+rerank", "qwen3+rerank50"]

# Padrão (definido em 05/11/2026, antes da validação humana do conjunto de referência): Qwen3 + reranker lendo os
# 50 primeiros. No gabarito do Opus (38 perguntas, marcado sem o buscador), contra o Qwen3 sozinho:
# recall@5 de 0,28 para 0,42 (+0,14, IC pareado +0,08 a +0,21) e perguntas com ao menos 1 trecho certo nos 5
# de 26 para 33 de 38. Ler 50 em vez de 20 candidatos: +0,06 (+0,01 a +0,13). No rascunho do Mac (19 perguntas)
# o recall@5 cai, mas 23 das 95 vagas são de trecho que nenhum juiz leu, então ele não é comparável.
# Os dois gabaritos são de modelo; a revisão humana ainda pode derrubar esta escolha.
# Custo: 463 ms por pergunta no Mac (40 ms sem reranker); na VPS, sem GPU, não foi medido.
# Para voltar: RAG_METODO=qwen3. Ver GABARITO-RASCUNHO.md e ../../outputs/18-variacoes-busca.txt.
METODO_PADRAO = os.environ.get("RAG_METODO", "qwen3+rerank50")

# Reranker (2º estágio): cross-encoder multilíngue. Lê "pergunta + trecho" num passe só e dá uma
# nota de relevância. É lento demais para os 1.368 trechos (precisa de 1 passe por par), então só
# reordena os N primeiros da busca híbrida.
RERANKERS = {
    # 118 M parâmetros, treinado no mMARCO (MS MARCO traduzido para 14 línguas, inclui português). Apache-2.0.
    "mminilm": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    # 568 M parâmetros, multilíngue, mais forte e ~5x mais lento na CPU. Apache-2.0.
    "bge-m3": "BAAI/bge-reranker-v2-m3",
}
RERANKER = os.environ.get("RAG_RERANKER", "mminilm")
CANDIDATOS_RERANK = 20
CANDIDATOS_RERANK_FUNDO = 50      # quantos o reranker lê no método qwen3+rerank50

# Banco vetorial: PostgreSQL com pgvector (ver banco_pg.py). Os vetores gravados são os de cache/*.npy.
BANCO = "pgvector"
# Denso usado no híbrido: qwen3 se a coleção existir (o melhor dos densos nesta base), senão mpnet.
DENSO_DO_HIBRIDO = os.environ.get("RAG_DENSO_HIBRIDO", "")
CANDIDATOS_RRF = 50       # quantos de cada lista entram na fusão

# Placeholder do dicionário de sinônimos: palavra do professor -> termo do documento (inclusive em
# inglês, porque o BM25 não cruza idiomas). DESLIGADO por padrão; o grupo deve montar a lista com
# consultas reais e medir com o gabarito antes de ligar. Os exemplos abaixo só mostram o formato.
SINONIMOS: dict[str, str] = {
    "se distrai": "se distrai atenção sustentada distração attention",
    "esquece o enunciado": "esquece o enunciado memória de trabalho working memory",
    "tempo extra": "tempo extra tempo adicional extended time",
    "laudo": "laudo diagnóstico relatório médico",
}


def expandir_sinonimos(pergunta: str, ligado: bool = False) -> str:
    if not ligado:
        return pergunta
    p = pergunta
    for termo, troca in SINONIMOS.items():
        p = re.sub(re.escape(termo), troca, p, flags=re.I)
    return p


# ---------------------------------------------------------------- carregar uma vez
@lru_cache(maxsize=1)
def _base():
    chunks = ingestao.carregar_chunks()
    por_id = {c["chunk_id"]: c for c in chunks}
    bm25 = emb.BuscaBM25([c["texto_indexado"] for c in chunks])
    return chunks, por_id, bm25


@lru_cache(maxsize=2)
def _modelo(apelido: str) -> emb.ModeloDenso:
    return emb.ModeloDenso(apelido)


@lru_cache(maxsize=2)
def _reranker(nome: str):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(RERANKERS[nome], device=emb.dispositivo(), max_length=512)


def reranquear(pergunta: str, candidatos: list[str], nome: str | None = None) -> list[tuple[str, float]]:
    """Reordena chunk_ids pela nota do cross-encoder (lê o texto com o prefixo Documento | Seção)."""
    _, por_id, _ = _base()
    modelo = _reranker(nome or RERANKER)
    pares = [(pergunta, por_id[c]["texto_indexado"]) for c in candidatos]
    notas = modelo.predict(pares, batch_size=8, show_progress_bar=False)
    return sorted(zip(candidatos, [float(x) for x in notas]), key=lambda x: -x[1])


@lru_cache(maxsize=1)
def _pg():
    import banco_pg
    return banco_pg, banco_pg.conectar()


def modelos_prontos() -> list[str]:
    """Modelos densos com vetores gravados no banco."""
    bp, con = _pg()
    return bp.colunas_prontas(con)


def denso_do_hibrido() -> str:
    if DENSO_DO_HIBRIDO:
        return DENSO_DO_HIBRIDO
    return "qwen3" if "qwen3" in modelos_prontos() else "mpnet"


def _passa_filtro(c: dict, filtro: dict | None) -> bool:
    """filtro = {'barreira': 'memoria_trabalho'} e/ou {'parte': 'C'}."""
    if not filtro:
        return True
    if filtro.get("barreira") and filtro["barreira"] not in c["barreiras"]:
        return False
    if filtro.get("parte") and c["parte"] != filtro["parte"]:
        return False
    return True


# ---------------------------------------------------------------- os buscadores (devolvem ids e notas)
def _ranking_bm25(pergunta: str, n: int, filtro: dict | None) -> list[tuple[str, float]]:
    chunks, _, bm25 = _base()
    notas = bm25.notas(pergunta)
    ordem = sorted(range(len(chunks)), key=lambda i: -notas[i])
    out = []
    for i in ordem:
        if _passa_filtro(chunks[i], filtro):
            out.append((chunks[i]["chunk_id"], float(notas[i])))
            if len(out) == n:
                break
    return out


def _ranking_denso(pergunta: str, apelido: str, n: int, filtro: dict | None) -> list[tuple[str, float]]:
    v = _modelo(apelido).vetor_pergunta(pergunta)
    bp, con = _pg()
    return bp.buscar_denso(con, v, apelido, n, filtro)


def ranking(pergunta: str, metodo: str, n: int, filtro: dict | None = None) -> list[tuple[str, float]]:
    if metodo == "bm25":
        return _ranking_bm25(pergunta, n, filtro)
    if metodo in emb.MODELOS_DENSOS:
        return _ranking_denso(pergunta, metodo, n, filtro)
    if metodo == "hibrido":
        m = max(n, CANDIDATOS_RRF)
        a = [cid for cid, _ in _ranking_bm25(pergunta, m, filtro)]
        b = [cid for cid, _ in _ranking_denso(pergunta, denso_do_hibrido(), m, filtro)]
        return emb.rrf([a, b], k=60)[:n]
    if metodo.startswith("hibrido+rerank"):
        nome = metodo.split(":", 1)[1] if ":" in metodo else None
        cands = [cid for cid, _ in ranking(pergunta, "hibrido", max(n, CANDIDATOS_RERANK), filtro)]
        return reranquear(pergunta, cands, nome)[:n]
    if metodo == "qwen3+rerank":
        # mesmos 20 candidatos e mesmo reranker da híbrida + reranker; só muda quem fornece os candidatos
        cands = [cid for cid, _ in ranking(pergunta, "qwen3", max(n, CANDIDATOS_RERANK), filtro)]
        return reranquear(pergunta, cands)[:n]
    if metodo == "qwen3+rerank50":
        # o trecho certo costuma estar entre os 50 primeiros do Qwen3 e não entre os 5: o reranker relê os 50
        cands = [cid for cid, _ in ranking(pergunta, "qwen3", max(n, CANDIDATOS_RERANK_FUNDO), filtro)]
        return reranquear(pergunta, cands)[:n]
    raise ValueError(f"método desconhecido: {metodo} (use {METODOS})")


def buscar(pergunta: str, metodo: str = METODO_PADRAO, k: int = 5, filtro_barreira: str | None = None,
           filtro_parte: str | None = None, sinonimos: bool = False,
           priorizar_sem_aviso: bool = True) -> list[dict]:
    """Os k trechos mais bem colocados, com tudo o que é preciso para citar a fonte."""
    _, por_id, _ = _base()
    q = expandir_sinonimos(pergunta, sinonimos)
    filtro = {k_: v for k_, v in (("barreira", filtro_barreira), ("parte", filtro_parte)) if v} or None
    n_busca = max(k * 3, k + 10) if (priorizar_sem_aviso and k > 0) else k
    candidatos = ranking(q, metodo, n_busca, filtro)
    if priorizar_sem_aviso and len(candidatos) > k:
        sem_aviso = [(cid, nota) for cid, nota in candidatos if not por_id[cid].get("nao_usar_para")]
        com_aviso = [(cid, nota) for cid, nota in candidatos if por_id[cid].get("nao_usar_para")]
        selecionados = (sem_aviso + com_aviso)[:k]
    else:
        selecionados = candidatos[:k]
    out = []
    for pos, (cid, nota) in enumerate(selecionados, 1):
        c = por_id[cid]
        pag = (None if c["pagina_inicio"] is None else
               str(c["pagina_inicio"]) if c["pagina_inicio"] == c["pagina_fim"]
               else f"{c['pagina_inicio']}-{c['pagina_fim']}")
        out.append({"posicao": pos, "chunk_id": cid, "doc": c["doc_id"], "titulo": c["titulo"],
                    "pagina": pag, "secao": c["secao"], "score": round(float(nota), 4),
                    "idioma": c["idioma"], "parte": c["parte"], "tipo_evidencia": c["tipo_evidencia"],
                    "url": c["url"], "nao_usar_para": c["nao_usar_para"], "nota_uso": c["nota_uso"],
                    "trecho": c["texto"]})
    return out


def mostrar(resultados: list[dict], largura: int = 220) -> str:
    linhas = []
    for r in resultados:
        aviso = f"  [AVISO não usar para: {', '.join(r['nao_usar_para'])}]" if r["nao_usar_para"] else ""
        linhas.append(f"  {r['posicao']}. {r['score']:.4f}  {r['doc']}  p. {r['pagina'] or '-'}  "
                      f"[{r['idioma']}] | {r['secao'][:55]}{aviso}")
        linhas.append(f"       {r['url']}")
        linhas.append("       \"" + re.sub(r"\s+", " ", r["trecho"])[:largura] + "...\"")
    return "\n".join(linhas)


# ---------------------------------------------------------------- demonstração (smoke test)
# Consultas no formato do Agente Estrategista (barreira + tipo de atividade + o que preservar),
# mais duas de professor e uma de norma. Escritas por quem montou a base, ANTES de rodar a busca.
PERGUNTAS_DEMO = [
    "aluno com TDAH perde o fio em enunciados longos com vários comandos na mesma questão: como reorganizar a questão sem mudar a habilidade avaliada?",
    "dificuldade de memória de trabalho em problema de matemática de várias etapas: que apoio dar sem resolver o problema por ele?",
    "tempo adicional na prova ajuda alunos com TDAH?",
    "a escola pode exigir laudo médico para fazer adaptação ou oferecer atendimento educacional especializado?",
    "diferença entre acomodação e modificação: o que pode mudar na avaliação sem reduzir o objetivo?",
    "fonte especial para dislexia melhora a leitura?",
    "o aluno aprende melhor com imagem porque é visual: adaptar ao estilo de aprendizagem funciona?",
    "como o desenho universal para a aprendizagem orienta oferecer várias formas de o aluno mostrar o que aprendeu?",
]


def _tem_colecao(apelido: str) -> bool:
    return apelido in modelos_prontos()


def demonstracao(perguntas: list[str] | None = None, k: int = 5,
                 caminho: Path = AQUI / "outputs" / "03-demonstracao.txt") -> dict:
    perguntas = perguntas or PERGUNTAS_DEMO
    metodos = [m for m in METODOS if m not in emb.MODELOS_DENSOS or _tem_colecao(m)]
    L = ["DEMONSTRAÇÃO (SMOKE TEST) - Íris: base de conhecimento (semana 2)",
         f"ATENÇÃO: isto NÃO é avaliação. São {len(perguntas)} consultas escritas por quem montou a base,",
         "sem gabarito e sem conferência do grupo. Serve para ver a busca funcionando de ponta a ponta.",
         f"Banco vetorial: {BANCO}. Métodos: {', '.join(metodos)} (híbrido = BM25 + {denso_do_hibrido()} por RRF, k=60). "
         f"Top-{k}. Sinônimos: desligados. Sem filtro.", ""]
    tudo = {}
    for p in perguntas:
        L.append("=" * 110)
        L.append(f"PERGUNTA: {p}")
        tudo[p] = {}
        for m in metodos:
            t0 = time.time()
            r = buscar(p, m, k=k)
            ms = (time.time() - t0) * 1000
            tudo[p][m] = r
            L.append(f"\n[{m}]  ({ms:.0f} ms)")
            L.append(mostrar(r))
        L.append("")
    caminho.parent.mkdir(exist_ok=True)
    caminho.write_text("\n".join(L) + "\n", encoding="utf-8")
    return tudo


if __name__ == "__main__":
    demonstracao()
    print((AQUI / "outputs" / "03-demonstracao.txt").read_text(encoding="utf-8"))
