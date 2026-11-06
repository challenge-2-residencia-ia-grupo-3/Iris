"""avaliar.py: mede a busca com o gabarito do GRUPO (quando ele existir).

    .venv/bin/python avaliar.py gabarito.json [--metodos bm25,mpnet,qwen3,hibrido] [--saida outputs/04-avaliacao.txt]

Para cada pergunta do gabarito: o sistema busca os 10 primeiros trechos e confere se algum dos
'trechos_relevantes' (chunk_id) apareceu.
    recall@5   fração dos trechos relevantes que apareceram entre os 5 primeiros (média por pergunta)
    recall@10  o mesmo entre os 10 primeiros
    MRR        1 / posição do primeiro relevante (1º = 1; 2º = 0,5; não achou = 0), média por pergunta
Intervalo de confiança de 95% por bootstrap (reamostra as perguntas 2000 vezes, semente fixa).

O gabarito segue gabarito_modelo.json. Perguntas sem trecho relevante marcado são puladas (e contadas).
Nada aqui foi rodado com gabarito real: o gabarito é tarefa do grupo.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SEMENTE = 20261104
N_BOOT = 2000


def carregar_gabarito(caminho: Path) -> list[dict]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    itens = dados["itens"] if isinstance(dados, dict) else dados
    return itens


def metricas_pergunta(ranking: list[str], relevantes: set[str]) -> dict:
    pos = next((i for i, c in enumerate(ranking) if c in relevantes), None)
    return {"recall@5": len(relevantes & set(ranking[:5])) / len(relevantes),
            "recall@10": len(relevantes & set(ranking[:10])) / len(relevantes),
            "MRR": 0.0 if pos is None else 1.0 / (pos + 1),
            "posicao": None if pos is None else pos + 1}


def bootstrap(valores: list[float], n: int = N_BOOT, semente: int = SEMENTE) -> tuple[float, float]:
    rnd = random.Random(semente)
    m = len(valores)
    medias = sorted(sum(rnd.choice(valores) for _ in range(m)) / m for _ in range(n))
    return medias[int(0.025 * n)], medias[int(0.975 * n) - 1]


def avaliar(gabarito: list[dict], metodos: list[str], buscar_ids=None) -> dict:
    """buscar_ids(pergunta, metodo, k) -> lista de chunk_id. Por padrão usa consultar.ranking."""
    if buscar_ids is None:
        import consultar
        buscar_ids = lambda p, m, k: [cid for cid, _ in consultar.ranking(p, m, k)]
    validos = [g for g in gabarito if g.get("trechos_relevantes")]
    out = {"n_perguntas": len(validos), "n_puladas": len(gabarito) - len(validos), "metodos": {}}
    for m in metodos:
        por = []
        for g in validos:
            r = buscar_ids(g["pergunta"], m, 10)
            x = metricas_pergunta(r, set(g["trechos_relevantes"]))
            x["pergunta"] = g["pergunta"]
            por.append(x)
        res = {}
        for k in ("recall@5", "recall@10", "MRR"):
            vals = [p[k] for p in por]
            media = sum(vals) / len(vals) if vals else float("nan")
            lo, hi = bootstrap(vals) if vals else (float("nan"), float("nan"))
            res[k] = {"media": media, "ic95": [lo, hi]}
        res["detalhes"] = por
        out["metodos"][m] = res
    return out


def relatorio(res: dict) -> str:
    n = res["n_perguntas"]
    L = [f"AVALIAÇÃO DA BUSCA: {n} perguntas com trecho relevante marcado "
         f"({res['n_puladas']} puladas sem marcação). IC 95% por bootstrap ({N_BOOT} reamostras, semente {SEMENTE}).",
         f"Com {n} perguntas, uma pergunta vale {100 / max(n, 1):.1f} pontos percentuais de recall.", "",
         f"{'método':10s} {'recall@5':>22s} {'recall@10':>22s} {'MRR':>22s}"]
    for m, r in res["metodos"].items():
        cel = lambda k: f"{r[k]['media']:.2f} [{r[k]['ic95'][0]:.2f}-{r[k]['ic95'][1]:.2f}]"
        L.append(f"{m:10s} {cel('recall@5'):>22s} {cel('recall@10'):>22s} {cel('MRR'):>22s}")
    L.append("")
    L.append("Posição do primeiro trecho relevante por pergunta ('-' = fora do top-10):")
    ms = list(res["metodos"])
    L.append(f"{'pergunta':60s} " + " ".join(f"{m:>8s}" for m in ms))
    for i in range(n):
        p = res["metodos"][ms[0]]["detalhes"][i]["pergunta"]
        pos = [res["metodos"][m]["detalhes"][i]["posicao"] for m in ms]
        L.append(f"{p[:60]:60s} " + " ".join(f"{(x or '-'):>8}" for x in pos))
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gabarito")
    ap.add_argument("--metodos", default="bm25,mpnet,qwen3,hibrido")
    ap.add_argument("--saida", default=str(AQUI / "outputs" / "04-avaliacao.txt"))
    a = ap.parse_args()
    res = avaliar(carregar_gabarito(Path(a.gabarito)), a.metodos.split(","))
    txt = relatorio(res)
    Path(a.saida).write_text(txt + "\n", encoding="utf-8")
    print(txt)
