"""avaliar_opus.py: os 6 métodos no gabarito do Opus (40 perguntas marcadas por leitura, sem usar o buscador).

    .venv/bin/python avaliar_opus.py        grava outputs/16-gabarito-opus.txt e outputs/16-gabarito-opus.json

Papel deste gabarito (diferente do rascunho do Mac): os trechos certos foram marcados lendo os textos,
sem depender de algum método tê-los achado. Por isso mede o que o rascunho do Mac não mede: trecho certo
que nenhum método traz. Também tem 12 perguntas com resposta só em inglês e 2 sem resposta na base.

Relevância graduada: nota 2 = 'trechos_relevantes' (responde), nota 1 = 'trechos_parciais' (ajuda).
recall@k e MRR usam só nota 2 (igual ao avaliar.py); nDCG@5 usa as duas notas.
Nada é treinado. Mesma semente e bootstrap do avaliar.py.
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import consultar

AQUI = Path(__file__).resolve().parent
GAB = AQUI.parent / "gabarito" / "gabarito_rascunho_v0.json"
METODOS = ["bm25", "mpnet", "qwen3", "hibrido", "hibrido+rerank", "qwen3+rerank"]
SAIDA = AQUI / "outputs" / "16-gabarito-opus.txt"
N_BOOT, SEMENTE = 2000, 20261105


def ndcg5(rank: list[str], nota: dict[str, int]) -> float:
    dcg = sum((2 ** nota.get(c, 0) - 1) / math.log2(i + 2) for i, c in enumerate(rank[:5]))
    ideal = sorted(nota.values(), reverse=True)[:5]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def metricas(rank: list[str], rel: set[str], parc: set[str]) -> dict:
    pos = next((i for i, c in enumerate(rank) if c in rel), None)
    nota = {c: 2 for c in rel} | {c: 1 for c in parc if c not in rel}
    return {"recall@5": len(rel & set(rank[:5])) / len(rel), "recall@10": len(rel & set(rank[:10])) / len(rel),
            "hit@5": float(pos is not None and pos < 5), "MRR": 0.0 if pos is None else 1 / (pos + 1),
            "nDCG@5": ndcg5(rank, nota), "posicao": None if pos is None else pos + 1}


def boot(v: list[float], rnd: random.Random) -> tuple[float, float]:
    m = len(v)
    ms = sorted(sum(rnd.choice(v) for _ in range(m)) / m for _ in range(N_BOOT))
    return ms[int(0.025 * N_BOOT)], ms[int(0.975 * N_BOOT) - 1]


def boot_par(a: list[float], b: list[float], rnd: random.Random) -> tuple[float, float, float]:
    d = [x - y for x, y in zip(a, b)]
    m = len(d)
    ms = sorted(sum(d[rnd.randrange(m)] for _ in range(m)) / m for _ in range(N_BOOT))
    return sum(d) / m, ms[int(0.025 * N_BOOT)], ms[int(0.975 * N_BOOT) - 1]


def main() -> None:
    g = json.loads(GAB.read_text(encoding="utf-8"))
    itens = g["itens"]
    com = [i for i in itens if i["trechos_relevantes"]]
    sem = [i for i in itens if not i["trechos_relevantes"]]
    consultar.ranking(itens[0]["pergunta"], "hibrido+rerank", 10)        # aquece os modelos fora do cronômetro
    rk, tempos = {}, {m: [] for m in METODOS}
    for m in METODOS:
        rk[m] = {}
        for it in itens:
            t0 = time.time()
            rk[m][it["id"]] = [cid for cid, _ in consultar.ranking(it["pergunta"], m, 10)]
            tempos[m].append((time.time() - t0) * 1000)
    res = {m: [metricas(rk[m][i["id"]], set(i["trechos_relevantes"]), set(i.get("trechos_parciais", [])))
               for i in com] for m in METODOS}
    rnd = random.Random(SEMENTE)
    L = ["GABARITO DO OPUS (rascunho v0): 40 perguntas escritas antes de abrir os trechos; trechos marcados por",
         "leitura, sem usar o buscador. Um marcador (modelo Claude Opus), SEM conferência humana. Nada treinado.",
         f"chunking congelado: {g['chunking_congelado'][:16]}... | banco: {consultar.BANCO} | "
         f"{len(com)} perguntas com resposta, {len(sem)} sem resposta de propósito.",
         f"Com {len(com)} perguntas, uma vale {100 / len(com):.1f} pontos. IC 95% por bootstrap ({N_BOOT}, semente {SEMENTE}).",
         "", f"{'método':16s}{'recall@5':>20s}{'recall@10':>8s}{'hit@5':>7s}{'MRR':>20s}{'nDCG@5':>8s}{'ms (mediana)':>14s}"]
    for m in METODOS:
        def cel(k):
            v = [r[k] for r in res[m]]
            lo, hi = boot(v, rnd)
            return f"{sum(v) / len(v):.2f} [{lo:.2f}-{hi:.2f}]"
        med = lambda k: sum(r[k] for r in res[m]) / len(res[m])
        tm = sorted(tempos[m])[len(tempos[m]) // 2]
        L.append(f"{m:16s}{cel('recall@5'):>20s}{med('recall@10'):8.2f}{med('hit@5'):7.2f}{cel('MRR'):>20s}"
                 f"{med('nDCG@5'):8.2f}{tm:14.0f}")
    L += ["", "Comparações pareadas (diferença média e IC 95%; só diz 'melhor' se o IC exclui o zero):"]
    for a, b in [("qwen3+rerank", "qwen3"), ("qwen3", "hibrido"), ("qwen3", "mpnet"), ("qwen3", "bm25"),
                 ("hibrido+rerank", "hibrido")]:
        for k in ("recall@5", "MRR"):
            d, lo, hi = boot_par([r[k] for r in res[a]], [r[k] for r in res[b]], rnd)
            veredito = "IC exclui o zero" if lo > 0 or hi < 0 else "IC passa pelo zero"
            L.append(f"  {a:15s} - {b:15s} {k:9s} {d:+.2f} [{lo:+.2f} a {hi:+.2f}]  {veredito}")
    # recortes
    L += ["", "Recorte: perguntas cuja resposta está só em documento em inglês (tipos evidencia, mito, so_ingles):"]
    ing = [k for k, i in enumerate(com) if i["tipo"] in ("evidencia", "mito", "so_ingles")]
    pt = [k for k in range(len(com)) if k not in ing]
    for m in METODOS:
        r_ing = sum(res[m][k]["recall@5"] for k in ing) / len(ing)
        r_pt = sum(res[m][k]["recall@5"] for k in pt) / len(pt)
        L.append(f"  {m:16s} recall@5 inglês {r_ing:.2f} (n={len(ing)}) | português {r_pt:.2f} (n={len(pt)})")
    L += ["", "Recorte por tipo de pergunta (recall@5):", f"  {'tipo':12s}" + "".join(f"{m:>16s}" for m in METODOS)]
    for t in sorted({i["tipo"] for i in com}):
        ks = [k for k, i in enumerate(com) if i["tipo"] == t]
        L.append(f"  {t:12s}" + "".join(f"{sum(res[m][k]['recall@5'] for k in ks) / len(ks):16.2f}" for m in METODOS)
                 + f"   (n={len(ks)})")
    # cartilha ABDA e aviso de uso
    _, por_id, _ = consultar._base()
    L += ["", "Trechos com aviso de evidência fraca (cartilha ABDA, 'evidencia_de_eficacia') no top-5, nas 40:"]
    for m in METODOS:
        n = sum(1 for i in itens for c in rk[m][i["id"]][:5] if "evidencia_de_eficacia" in por_id[c]["nao_usar_para"])
        L.append(f"  {m:16s} {n:3d} de {5 * len(itens)}")
    L += ["", "Perguntas sem resposta na base (o top-5 deveria ser fraco; a abstenção é medida na geração):"]
    for i in sem:
        L.append(f"  {i['id']} {i['pergunta'][:80]}")
        L.append(f"     qwen3 1º: {rk['qwen3'][i['id']][0]}")
    L += ["", "Posição do primeiro trecho certo por pergunta ('-' = fora do top-10):",
          f"  {'id':5s}{'tipo':11s}" + "".join(f"{m[:9]:>10s}" for m in METODOS)]
    for k, i in enumerate(com):
        L.append(f"  {i['id']:5s}{i['tipo'][:10]:11s}" + "".join(f"{(res[m][k]['posicao'] or '-'):>10}" for m in METODOS))
    L += ["", "LIMITES: um só marcador, que é modelo; quem escreveu as perguntas conhecia os títulos da base;",
          "a marcação por leitura/grep pode ter perdido trecho relevante (aí um método 'erra' sem errar);",
          "relevante = responde à pergunta, não 'é boa evidência'. Ler junto com o rascunho do Mac (2 juízes, kappa 0,69)."]
    SAIDA.write_text("\n".join(L) + "\n", encoding="utf-8")
    SAIDA.with_suffix(".json").write_text(json.dumps({"rankings": rk, "metricas": res}, ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
