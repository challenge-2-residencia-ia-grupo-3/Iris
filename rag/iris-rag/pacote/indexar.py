"""indexar.py: põe os trechos (chunks.jsonl) no banco vetorial Chroma, um modelo por coleção.

    chunks.jsonl -> vetores (cache/*.npy) -> Chroma em chroma/ (coleções 'iris_mpnet' e 'iris_qwen3')

O BM25 não vai para o Chroma: é recalculado em memória a partir de chunks.jsonl (leva ~1 s).
Rodar:  .venv/bin/python indexar.py            (os dois modelos)
        .venv/bin/python indexar.py mpnet      (só um)
Gera outputs/02-indexacao.txt com nº de chunks, tempo de embedding por modelo e tamanho em disco.
"""
from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path

import embeddings as emb
import ingestao

AQUI = Path(__file__).resolve().parent
PASTA_CHROMA = Path(os.environ.get("RAG_CHROMA", AQUI / "chroma"))
RELATORIO = AQUI / "outputs" / "02-indexacao.txt"
BARREIRAS = ["atencao_sustentada", "memoria_trabalho", "iniciacao_tarefa", "organizacao_sequencial",
             "sobrecarga_visual", "controle_inibitorio", "flexibilidade_cognitiva", "velocidade_processamento",
             "leitura_texto_longo"]


def nome_colecao(apelido: str) -> str:
    return f"iris_{apelido}"


def cliente_chroma():
    import chromadb
    from chromadb.config import Settings
    PASTA_CHROMA.mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=str(PASTA_CHROMA),
                                     settings=Settings(anonymized_telemetry=False))


def metadados_chroma(c: dict) -> dict:
    """O Chroma só guarda valores simples (texto, número, booleano). Listas viram texto
    separado por '|' e cada barreira vira um booleano ('barreira_memoria_trabalho': True) para filtrar."""
    m = {
        "doc_id": c["doc_id"], "titulo": c["titulo"], "orgao": c["orgao"], "ano": c["ano"],
        "url": c["url"], "licenca": c["licenca"], "secao": c["secao"],
        "pagina_inicio": c["pagina_inicio"] if c["pagina_inicio"] is not None else -1,
        "pagina_fim": c["pagina_fim"] if c["pagina_fim"] is not None else -1,
        "tema": "|".join(c["tema"]), "barreiras": "|".join(c["barreiras"]),
        "parte": c["parte"], "idioma": c["idioma"], "tipo_evidencia": c["tipo_evidencia"],
        "n_palavras": c["n_palavras"], "nao_usar_para": "|".join(c["nao_usar_para"]),
        "nota_uso": c["nota_uso"], "tipo_corte": c["tipo_corte"],
    }
    for b in BARREIRAS:
        m[f"barreira_{b}"] = b in c["barreiras"]
    return m


def indexar_modelo(chunks: list[dict], apelido: str, modelo: emb.ModeloDenso | None = None,
                   recriar: bool = True) -> dict:
    """Calcula (ou lê do cache) os vetores e grava a coleção do modelo no Chroma."""
    modelo = modelo or emb.ModeloDenso(apelido)
    textos = [c["texto_indexado"] for c in chunks]
    vetores = modelo.vetores_trechos(textos)
    cli = cliente_chroma()
    nome = nome_colecao(apelido)
    if recriar and nome in [c.name for c in cli.list_collections()]:
        cli.delete_collection(nome)
    col = cli.get_or_create_collection(nome, metadata={"hnsw:space": "cosine",
                                                       "modelo": emb.MODELOS_DENSOS[apelido]["nome"]})
    t0 = time.time()
    lote = 500
    for i in range(0, len(chunks), lote):
        parte = chunks[i:i + lote]
        col.add(ids=[c["chunk_id"] for c in parte],
                embeddings=vetores[i:i + lote].tolist(),
                documents=[c["texto"] for c in parte],
                metadatas=[metadados_chroma(c) for c in parte])
    return {"apelido": apelido, "modelo": emb.MODELOS_DENSOS[apelido]["nome"],
            "n": col.count(), "dimensao": int(vetores.shape[1]),
            "segundos_embedding": modelo.ultimo_tempo_s, "veio_do_cache": modelo.veio_do_cache,
            "dispositivo": modelo.disp, "segundos_chroma": time.time() - t0}


def tamanho_pasta(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def _mb(n: int) -> str:
    return f"{n / 1e6:.1f} MB"


def escrever_relatorio(chunks: list[dict], resultados: list[dict], seg_bm25: float) -> None:
    RELATORIO.parent.mkdir(exist_ok=True)
    import torch
    L = ["RELATÓRIO DE INDEXAÇÃO - Íris: base de conhecimento (semana 2)",
         f"Sistema: {platform.system()} {platform.machine()} | {os.cpu_count()} CPUs | Python {platform.python_version()} | "
         f"torch {torch.__version__} | dispositivo: {emb.dispositivo()}",
         "", f"Chunks indexados: {len(chunks)} (de chunks.jsonl; ver outputs/01-chunking.txt)",
         f"BM25 (rank_bm25, em memória): montado em {seg_bm25:.1f} s; não vai para o Chroma.", ""]
    L.append(f"{'modelo':8s} {'coleção':18s} {'n':>5s} {'dim':>5s} {'embedding':>12s} {'por chunk':>10s}  observação")
    for r in resultados:
        s = r["segundos_embedding"]
        tempo = f"{s / 60:.1f} min" if s else "?"
        por = f"{1000 * s / r['n']:.0f} ms" if s else "?"
        obs = "tempo da 1ª vez (lido do cache)" if r["veio_do_cache"] else "calculado agora"
        L.append(f"{r['apelido']:8s} {nome_colecao(r['apelido']):18s} {r['n']:5d} {r['dimensao']:5d} "
                 f"{tempo:>12s} {por:>10s}  {obs}; {r['dispositivo']}")
    if len(resultados) == 2 and all(r["segundos_embedding"] for r in resultados):
        a, b = resultados
        L.append(f"  {b['apelido']} levou {b['segundos_embedding'] / a['segundos_embedding']:.1f}x "
                 f"o tempo do {a['apelido']} ({b['segundos_embedding']:.0f} s contra {a['segundos_embedding']:.0f} s), "
                 f"nos mesmos {a['n']} chunks.")
    L.append("")
    L.append("Tamanho em disco:")
    L.append(f"  chroma/ (as {len(resultados)} coleções, com texto e metadados): {_mb(tamanho_pasta(PASTA_CHROMA))}")
    for f in sorted(emb.CACHE.glob("vetores-*.npy")):
        L.append(f"  cache/{f.name}: {_mb(f.stat().st_size)}")
    L.append(f"  chunks.jsonl: {_mb((AQUI / 'chunks.jsonl').stat().st_size)}")
    L.append("")
    L.append("Notas:")
    L.append("  - Textos indexados = 'Documento: <titulo> | Seção: <secao>' + texto do trecho.")
    L.append("  - mpnet lê até 512 tokens e qwen3 até 1024; trecho maior é cortado no fim (ver ARQUITETURA.md, limitações).")
    L.append("  - Os vetores ficam em cache/ com a assinatura dos textos no nome: mudou o chunking, recalcula sozinho.")
    L.append("  - Na VPS não há GPU; no Mac (mps) ou na RTX (cuda) o tempo cai bastante.")
    RELATORIO.write_text("\n".join(L) + "\n", encoding="utf-8")


def rodar(apelidos: list[str] | None = None) -> list[dict]:
    apelidos = apelidos or ["mpnet", "qwen3"]
    chunks = ingestao.carregar_chunks()
    t0 = time.time()
    emb.BuscaBM25([c["texto_indexado"] for c in chunks])
    seg_bm25 = time.time() - t0
    resultados = []
    for a in apelidos:
        print(f"[{a}] indexando {len(chunks)} chunks...", flush=True)
        r = indexar_modelo(chunks, a)
        print(f"[{a}] ok: {r['n']} vetores de {r['dimensao']} dimensões; "
              f"embedding {r['segundos_embedding'] or 0:.0f} s ({'cache' if r['veio_do_cache'] else 'calculado'})", flush=True)
        resultados.append(r)
    escrever_relatorio(chunks, resultados, seg_bm25)
    return resultados


if __name__ == "__main__":
    rodar(sys.argv[1:] or None)
    print(RELATORIO.read_text(encoding="utf-8"))
