"""banco_pg.py: o banco vetorial no PostgreSQL com a extensão pgvector.

Uma tabela só (iris_trechos): cada linha é um trecho, com o texto, os metadados e uma coluna de
vetor por modelo (vec_mpnet: 768 números; vec_qwen3: 1024). Índice HNSW com distância cosseno em
cada coluna de vetor. A busca por palavra (BM25) continua em Python, igual à versão com Chroma.

Conexão: variável RAG_PG_DSN (padrão: postgresql://iris:iris@127.0.0.1:5433/iris).
Subir o banco no Mac ou na VPS (uma vez):
    docker run -d --name iris-pgvector --restart unless-stopped -e POSTGRES_USER=iris \\
      -e POSTGRES_PASSWORD=iris -e POSTGRES_DB=iris -p 127.0.0.1:5433:5432 pgvector/pgvector:pg17

Rodar:  python banco_pg.py           (cria a tabela, grava trechos e os vetores que já estão em cache/)
"""
from __future__ import annotations

import os
import sys
import time

import embeddings as emb
import ingestao

DSN = os.environ.get("RAG_PG_DSN", "postgresql://iris:iris@127.0.0.1:5433/iris")
TABELA = "iris_trechos"
DIM = {"mpnet": 768, "qwen3": 1024}


def conectar():
    import psycopg
    from pgvector.psycopg import register_vector
    con = psycopg.connect(DSN, autocommit=True)
    con.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(con)
    return con


def criar_tabela(con) -> None:
    """Cria a tabela se não existir. Os metadados viram colunas de verdade (com tipo), não texto
    com '|' como no Chroma: barreiras e tema são listas (text[]), página é inteiro."""
    cols_vetor = ",\n".join(f"  vec_{m} vector({d})" for m, d in DIM.items())
    con.execute(f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
  chunk_id text PRIMARY KEY,
  doc_id text NOT NULL,
  parte text, idioma text, tipo_evidencia text,
  titulo text, orgao text, ano text, url text, licenca text,
  secao text, pagina_inicio int, pagina_fim int,
  tema text[], barreiras text[], nao_usar_para text[], nota_uso text,
  tipo_corte text, n_palavras int,
  texto text NOT NULL, texto_indexado text NOT NULL,
{cols_vetor}
)""")
    for m in DIM:
        con.execute(f"CREATE INDEX IF NOT EXISTS {TABELA}_hnsw_{m} ON {TABELA} "
                    f"USING hnsw (vec_{m} vector_cosine_ops)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {TABELA}_doc ON {TABELA} (doc_id)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {TABELA}_barreiras ON {TABELA} USING gin (barreiras)")


def gravar_trechos(con, chunks: list[dict]) -> None:
    """Apaga e regrava os trechos (o chunk_id muda quando o chunking muda)."""
    con.execute(f"TRUNCATE {TABELA}")
    campos = ["chunk_id", "doc_id", "parte", "idioma", "tipo_evidencia", "titulo", "orgao", "ano", "url",
              "licenca", "secao", "pagina_inicio", "pagina_fim", "tema", "barreiras", "nao_usar_para",
              "nota_uso", "tipo_corte", "n_palavras", "texto", "texto_indexado"]
    with con.cursor() as cur:
        with cur.copy(f"COPY {TABELA} ({', '.join(campos)}) FROM STDIN") as cp:
            for c in chunks:
                cp.write_row([c.get(k) for k in campos])


def gravar_vetores(con, chunks: list[dict], apelido: str, modelo: emb.ModeloDenso | None = None) -> dict:
    """Calcula (ou lê do cache/) os vetores do modelo e grava na coluna vec_<apelido>."""
    import numpy as np
    modelo = modelo or emb.ModeloDenso(apelido)
    V = modelo.vetores_trechos([c["texto_indexado"] for c in chunks])
    t0 = time.time()
    with con.cursor() as cur:
        cur.executemany(f"UPDATE {TABELA} SET vec_{apelido} = %s WHERE chunk_id = %s",
                        [(np.asarray(v, dtype=np.float32), c["chunk_id"]) for v, c in zip(V, chunks)])
    return {"apelido": apelido, "n": len(chunks), "segundos_embedding": modelo.ultimo_tempo_s,
            "veio_do_cache": modelo.veio_do_cache, "segundos_pg": time.time() - t0}


def colunas_prontas(con) -> list[str]:
    """Modelos que têm vetor gravado em todos os trechos."""
    prontos = []
    existe = con.execute("SELECT to_regclass(%s)", [TABELA]).fetchone()[0]
    if existe is None:
        return prontos
    total = con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]
    for m in DIM:
        n = con.execute(f"SELECT count(vec_{m}) FROM {TABELA}").fetchone()[0]
        if total and n == total:
            prontos.append(m)
    return prontos


def buscar_denso(con, vetor, apelido: str, n: int, filtro: dict | None = None) -> list[tuple[str, float]]:
    """Os n trechos mais perto do vetor da pergunta. '<=>' é a distância cosseno do pgvector."""
    import numpy as np
    where, params = [f"vec_{apelido} IS NOT NULL"], []
    if filtro and filtro.get("barreira"):
        where.append("%s = ANY(barreiras)")
        params.append(filtro["barreira"])
    if filtro and filtro.get("parte"):
        where.append("parte = %s")
        params.append(filtro["parte"])
    v = np.asarray(vetor, dtype=np.float32)
    sql = (f"SELECT chunk_id, 1 - (vec_{apelido} <=> %s) AS cosseno FROM {TABELA} "
           f"WHERE {' AND '.join(where)} ORDER BY vec_{apelido} <=> %s LIMIT %s")
    # hnsw.ef_search maior = busca mais completa no índice aproximado (padrão 40)
    con.execute("SET hnsw.ef_search = 100")
    return [(r[0], float(r[1])) for r in con.execute(sql, [v, *params, v, n]).fetchall()]


def tamanho_tabela(con) -> str:
    return con.execute(f"SELECT pg_size_pretty(pg_total_relation_size('{TABELA}'))").fetchone()[0]


def rodar(apelidos: list[str] | None = None) -> None:
    chunks = ingestao.carregar_chunks()
    con = conectar()
    criar_tabela(con)
    ids_banco = {r[0] for r in con.execute(f"SELECT chunk_id FROM {TABELA}").fetchall()}
    if ids_banco != {c["chunk_id"] for c in chunks}:
        # o chunking mudou: regrava os trechos (apaga os vetores antigos, que não valem mais)
        gravar_trechos(con, chunks)
        print(f"{len(chunks)} trechos gravados em {TABELA}")
    else:
        # mesmos trechos: não apaga nada (rodar só 'qwen3' não pode zerar os vetores do mpnet)
        print(f"{len(chunks)} trechos já estavam em {TABELA}; só os vetores pedidos são (re)gravados")
    for a in apelidos or list(DIM):
        try:
            r = gravar_vetores(con, chunks, a)
            print(f"[{a}] vetores gravados ({'cache' if r['veio_do_cache'] else 'calculados'}; "
                  f"{r['segundos_pg']:.1f} s no banco)")
        except KeyboardInterrupt:
            raise
    print("prontos:", colunas_prontas(con), "| tamanho da tabela com índices:", tamanho_tabela(con))


if __name__ == "__main__":
    rodar(sys.argv[1:] or None)
