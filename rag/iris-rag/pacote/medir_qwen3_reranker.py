"""Mede Qwen3 + reranker, que a demonstração não tinha: os 20 primeiros do Qwen3 reordenados pelo cross-encoder.

    .venv/bin/python medir_qwen3_reranker.py ranquear   busca, tempos e trechos novos para os juízes
    .venv/bin/python medir_qwen3_reranker.py medir      lê os juízes e grava a saída
    .venv/bin/python medir_qwen3_reranker.py divergencia  testa por que o rascunho discorda do Opus

Técnica: nenhum modelo é treinado. São dois modelos prontos (Qwen3-Embedding e mMiniLM) e contagens sobre o rascunho.
Não altera consultar.py. Expectativa e critério estão em GABARITO-RASCUNHO.md, commitados antes de rodar.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import avaliar  # noqa: E402

NOVO = "qwen3+rerank"
ORDEM = ["bm25", "mpnet", "qwen3", "hibrido", "hibrido+rerank", NOVO]
RANK = AQUI / "cache" / "rankings-15.json"
NOVOS = AQUI / "cache" / "candidatos-novos.json"
SAIDA = AQUI.parents[1] / "outputs" / "15-qwen3-reranker.txt"
PROFUNDIDADE = 8  # a mesma do conjunto julgado no rascunho
N_BOOT, SEMENTE = 2000, 20261105


def gabarito() -> list[dict]:
    return json.loads((AQUI / "gabarito_rascunho.json").read_text(encoding="utf-8"))["itens"]


def ranquear() -> None:
    import consultar
    from ingestao import carregar_chunks
    por_id = {c["chunk_id"]: c for c in carregar_chunks()}
    itens = gabarito()
    consultar.ranking(itens[0]["pergunta"], "hibrido+rerank", 10)  # aquece os modelos fora do cronômetro

    def novo(p: str, n: int) -> list[tuple[str, float]]:
        # Mesmos 20 candidatos e mesmo reranker da híbrida + reranker: só muda quem fornece os candidatos.
        cands = [cid for cid, _ in consultar.ranking(p, "qwen3", max(n, consultar.CANDIDATOS_RERANK))]
        return consultar.reranquear(p, cands, None)[:n]

    rank, ms = {}, {}
    for m in ORDEM:
        rank[m], tempos = [], []
        for it in itens:
            t = time.perf_counter()
            r = novo(it["pergunta"], 10) if m == NOVO else consultar.ranking(it["pergunta"], m, 10)
            tempos.append(1000 * (time.perf_counter() - t))
            rank[m].append([cid for cid, _ in r])
        ms[m] = sorted(tempos)[len(tempos) // 2]
    RANK.write_text(json.dumps({"rank": rank, "ms_mediana": ms}, ensure_ascii=False), encoding="utf-8")
    julgados = json.loads((AQUI / "cache" / "candidatos.json").read_text(encoding="utf-8"))
    saida, total = [], 0
    for n, (it, antes) in enumerate(zip(itens, julgados), 1):
        visto = {c["chunk_id"] for c in antes["candidatos"]}
        ids = sorted(set(rank[NOVO][n - 1][:PROFUNDIDADE]) - visto)
        random.Random(n).shuffle(ids)
        total += len(ids)
        saida.append({"n": n, "pergunta": it["pergunta"], "candidatos": [
            {"chunk_id": c, "documento": por_id[c]["titulo"], "texto": por_id[c]["texto"]} for c in ids]})
    NOVOS.write_text(json.dumps(saida, ensure_ascii=False, indent=0), encoding="utf-8")
    print("trechos nunca julgados entre os", PROFUNDIDADE, "primeiros do método novo:", total, "de", PROFUNDIDADE * len(itens))


def juizes(novos: list[dict]) -> tuple[dict, dict, int]:
    """Devolve os marcados pelos dois e por um só, por pergunta. Citação que não é literal é rejeitada."""
    textos = {(q["n"], c["chunk_id"]): c["texto"] for q in novos for c in q["candidatos"]}
    norm = lambda s: " ".join(s.split())
    votos, rejeitadas = {"A": {}, "B": {}}, 0
    for j in votos:
        for q in json.loads((AQUI / "cache" / f"juiz-novos-{j}.json").read_text(encoding="utf-8"))["julgamentos"]:
            ok = set()
            for r in q["relevantes"]:
                t = textos.get((q["n"], r["chunk_id"]))
                if t is not None and norm(r["trecho"]) in norm(t):
                    ok.add(r["chunk_id"])
                else:
                    rejeitadas += 1
            votos[j][q["n"]] = ok
    ambos = {n: votos["A"].get(n, set()) & votos["B"].get(n, set()) for n in range(1, 21)}
    um = {n: (votos["A"].get(n, set()) ^ votos["B"].get(n, set())) for n in range(1, 21)}
    return ambos, um, rejeitadas


def tabela(rank: dict, rel: list[set]) -> tuple[dict, list[int]]:
    validas = [i for i, s in enumerate(rel) if s]
    res = {}
    for m in ORDEM:
        por = [avaliar.metricas_pergunta(rank[m][i], rel[i]) for i in validas]
        res[m] = {"por": por}
        for k in ("recall@5", "recall@10", "MRR"):
            v = [p[k] for p in por]
            res[m][k] = (sum(v) / len(v), *avaliar.bootstrap(v))
    return res, validas


def diferenca(res: dict, a: str, b: str, k: str) -> tuple[float, float, float, int, int, int]:
    """a menos b, pergunta a pergunta. O sorteio reamostra perguntas, mantendo os dois métodos juntos."""
    d = [x[k] - y[k] for x, y in zip(res[a]["por"], res[b]["por"])]
    rnd = random.Random(SEMENTE)
    medias = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(N_BOOT))
    return (sum(d) / len(d), medias[int(.025 * N_BOOT)], medias[int(.975 * N_BOOT) - 1],
            sum(x > 1e-9 for x in d), sum(abs(x) <= 1e-9 for x in d), sum(x < -1e-9 for x in d))


def medir() -> None:
    from ingestao import carregar_chunks
    por_id = {c["chunk_id"]: c for c in carregar_chunks()}
    dados = json.loads(RANK.read_text(encoding="utf-8"))
    rank, ms = dados["rank"], dados["ms_mediana"]
    itens = gabarito()
    novos = json.loads(NOVOS.read_text(encoding="utf-8"))
    n_novos = sum(len(q["candidatos"]) for q in novos)
    ambos, um, rejeitadas = juizes(novos)
    como_esta = [set(i["trechos_relevantes"]) for i in itens]
    ampliado = [como_esta[n] | ambos[n + 1] for n in range(20)]
    L = ["QWEN3 + RERANKER NO RASCUNHO DE GABARITO. Sem conferência humana. Nenhum modelo treinado.",
         f"Bootstrap de 95%: {N_BOOT} sorteios de perguntas, semente {SEMENTE}.",
         f"Trechos novos levados aos dois juízes cegos: {n_novos}. Marcados pelos dois: {sum(map(len, ambos.values()))}. "
         f"Por um só: {sum(map(len, um.values()))}. Citações rejeitadas: {rejeitadas}.", ""]
    for nome, rel in (("GABARITO COMO ESTAVA", como_esta), ("GABARITO AMPLIADO COM OS TRECHOS NOVOS", ampliado)):
        res, validas = tabela(rank, rel)
        L += [f"{nome}: {len(validas)} perguntas", f"{'método':16s}{'recall@5':>20s}{'recall@10':>20s}{'MRR':>20s}"]
        for m in ORDEM:
            c = lambda k: f"{res[m][k][0]:.2f} [{res[m][k][1]:.2f}-{res[m][k][2]:.2f}]"
            L.append(f"{m:16s}{c('recall@5'):>20s}{c('recall@10'):>20s}{c('MRR'):>20s}")
        L += ["", "Diferença pareada (primeiro menos segundo), IC 95%, perguntas em que ganhou/empatou/perdeu:"]
        for a, b in ((NOVO, "qwen3"), (NOVO, "hibrido+rerank")):
            for k in ("recall@5", "MRR"):
                d = diferenca(res, a, b, k)
                L.append(f"{a} - {b:15s} {k:9s} {d[0]:+.2f} [{d[1]:+.2f} a {d[2]:+.2f}]  {d[3]}/{d[4]}/{d[5]}")
        L.append("")
        if rel is ampliado:
            L += ["Posição do primeiro trecho relevante ('-' = fora do top-10):",
                  f"{'pergunta':60s}{'qwen3':>8s}{'novo':>8s}"]
            for j, i in enumerate(validas):
                a, b = res["qwen3"]["por"][j]["posicao"], res[NOVO]["por"][j]["posicao"]
                L.append(f"{itens[i]['pergunta'][:58]:60s}{(a or '-'):>8}{(b or '-'):>8}")
            L.append("")
    L += [f"{'método':16s}{'mediana ms':>11s}{'ABDA no top-5':>15s}{'ABDA em 1º':>12s}{'inglês no top-5':>17s}"]
    for m in ORDEM:
        top = [c for r in rank[m] for c in r[:5]]
        L.append(f"{m:16s}{ms[m]:11.0f}{sum(c.startswith('ABDA') for c in top):15d}"
                 f"{sum(r[0].startswith('ABDA') for r in rank[m]):12d}{sum(por_id[c]['idioma'] == 'en' for c in top):17d}")
    SAIDA.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def divergencia() -> None:
    """Testa duas explicações para o rascunho discordar do gabarito do Opus. Só contagem e sorteio, sem modelo."""
    from ingestao import carregar_chunks
    por = {c["chunk_id"]: c for c in carregar_chunks()}
    rank = json.loads(RANK.read_text(encoding="utf-8"))["rank"]
    itens = gabarito()
    novos = json.loads(NOVOS.read_text(encoding="utf-8"))
    antes = json.loads((AQUI / "cache" / "candidatos.json").read_text(encoding="utf-8"))
    ambos, um, _ = juizes(novos)
    dois = [set(i["trechos_relevantes"]) | ambos[n + 1] for n, i in enumerate(itens)]
    qualquer = [dois[n] | set(i["a_conferir"]) | um[n + 1] for n, i in enumerate(itens)]
    q, r = "qwen3", NOVO
    L = ["DIVERGÊNCIA ENTRE RASCUNHO E GABARITO DO OPUS: contagens no rascunho ampliado. Nenhum modelo treinado.", ""]
    for m in (q, r):
        fora = 0
        for n, c in enumerate(antes):
            visto = {x["chunk_id"] for x in c["candidatos"]} | {x["chunk_id"] for x in novos[n]["candidatos"]}
            fora += sum(x not in visto for x in rank[m][n][:5])
        L.append(f"{m}: trechos do top-5 nunca julgados: {fora}")
    L.append("")
    for nome, rel in (("marcados pelos dois juízes", dois), ("marcados por qualquer juiz", qualquer)):
        idx = [i for i, s in enumerate(rel) if s]
        a = [len(rel[i] & set(rank[q][i][:5])) for i in idx]
        b = [len(rel[i] & set(rank[r][i][:5])) for i in idx]
        d = [y - x for x, y in zip(a, b)]
        rnd = random.Random(SEMENTE)
        med = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(N_BOOT))
        L.append(f"{nome}: {len(idx)} perguntas, certos no top-5 de {5 * len(idx)}: qwen3 {sum(a)}, novo {sum(b)}; "
                 f"novo ganhou/empatou/perdeu {sum(y > x for x, y in zip(a, b))}/{sum(y == x for x, y in zip(a, b))}/"
                 f"{sum(y < x for x, y in zip(a, b))}; diferença por pergunta {sum(d) / len(d):+.2f} "
                 f"[{med[int(.025 * N_BOOT)]:+.2f} a {med[int(.975 * N_BOOT) - 1]:+.2f}]")
    L.append("")
    so_en = [i for i, s in enumerate(dois) if s and all(por[c]["idioma"] == "en" for c in s)]
    algum = [i for i, s in enumerate(dois) if s and any(por[c]["idioma"] == "en" for c in s)]
    sem = [i for i, s in enumerate(dois) if s and i not in algum]
    for nome, ix in (("certo só em inglês", so_en), ("algum certo em inglês", algum), ("nenhum certo em inglês", sem)):
        f = lambda m: sum(avaliar.metricas_pergunta(rank[m][i], dois[i])["recall@5"] for i in ix) / len(ix)
        L.append(f"{nome}: {len(ix)} perguntas, recall@5 qwen3 {f(q):.2f}, novo {f(r):.2f}")
    res, _ = tabela(rank, dois)
    L.append("")
    for k in ("recall@5", "MRR"):
        d = diferenca(res, "qwen3", "mpnet", k)
        L.append(f"qwen3 - mpnet {k}: {d[0]:+.2f} [{d[1]:+.2f} a {d[2]:+.2f}]")
    destino = SAIDA.with_name("15b-divergencia-gabaritos.txt")
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    {"ranquear": ranquear, "medir": medir, "divergencia": divergencia}[sys.argv[1]]()
