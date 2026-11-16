"""figuras_do_relatorio.py: gera as figuras do relatório da semana 3 a partir de saidas/juiz_metricas.json.

Matplotlib aqui é exceção declarada à regra do repositório (Altair para gráfico exploratório): a figura é
final, vai impressa em PDF em tons de cinza, e o relatório de 09/11 usou o mesmo caminho.

Uso: python figuras_do_relatorio.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = Path(__file__).resolve().parent
SAIDAS = AQUI.parent / "saidas"
FIG = AQUI / "figuras"

COND = [("A|llama3.1-8b", "A\nLLM sozinho"), ("B|busca-top1", "B1\nbusca, 1 trecho"), ("B|busca-top3", "B3\nbusca, 3 trechos"),
        ("C|llama3.1-8b", "C\nRAG + LLM")]
COND_H4 = [("A|llama3.1-8b", "A\nLlama"), ("C|llama3.1-8b", "C\nLlama"), ("A|gpt-oss-20b", "A\ngpt-oss"),
           ("C|gpt-oss-20b", "C\ngpt-oss")]
METR = [("util_sim", "Resposta útil"), ("fidelidade", "Frases sustentadas pela base"), ("inventou", "Inventou fato ou fonte")]


def painel(res: dict, conds: list, nome: str) -> None:
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    fig, eixos = plt.subplots(1, 3, figsize=(7.2, 2.9), sharey=True)
    for ax, (campo, titulo) in zip(eixos, METR):
        xs, ys, lo, hi, rot = [], [], [], [], []
        for i, (c, r) in enumerate(conds):
            ic = res["condicoes"][c][campo]["media_ic95"]
            rot.append(r)
            if not ic:
                continue
            xs.append(i), ys.append(ic[0]), lo.append(ic[0] - ic[1]), hi.append(ic[2] - ic[0])
        ax.bar(xs, ys, color="#9ca3af", edgecolor="#111827", linewidth=0.6, width=0.62)
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor="#111827", capsize=3, linewidth=0.9)
        for x, y, h in zip(xs, ys, hi):
            ax.text(x, y + h + 0.025, f"{y:.2f}".replace(".", ","), ha="center", fontsize=8)
        ax.set_xticks(range(len(conds)), rot, fontsize=8)
        ax.set_title(titulo, fontsize=9)
        ax.set_ylim(0, 1.15)
        ax.spines[["top", "right"]].set_visible(False)
        if campo == "fidelidade" and any(not res["condicoes"][c][campo]["media_ic95"] for c, _ in conds):
            ax.text(1.5, 0.05, "não se aplica\na B", ha="center", fontsize=7.5, color="#374151")
    eixos[0].set_ylabel("proporção (média entre 40 perguntas)")
    fig.tight_layout()
    fig.savefig(FIG / nome, dpi=220)
    plt.close(fig)


def fora_da_base() -> None:
    """Figura 3: abstenção nas 27 perguntas sem resposta e escore da busca com e sem resposta na base."""
    s3 = SAIDAS.parent
    fora = s3 / "saidas_fora"
    if not (fora / "abstencao.json").exists():
        return
    ab = json.loads((fora / "abstencao.json").read_text(encoding="utf-8"))["com_q39_q40"]
    lim = json.loads((fora / "limiar.json").read_text(encoding="utf-8"))["20 candidatos | escore do 1º trecho"]
    gab = json.loads((s3.parent / "gabarito" / "gabarito_rascunho_v0.json").read_text(encoding="utf-8"))["itens"]
    com_resposta = {it["id"] for it in gab if it.get("trechos_relevantes")}
    linhas = [json.loads(l) for arq in (SAIDAS / "trechos_busca.jsonl", fora / "trechos_busca_20.jsonl")
              for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
    com = sorted(l["ranking_top10"][0]["score"] for l in linhas if l["id"] in com_resposta)
    sem = sorted(l["ranking_top10"][0]["score"] for l in linhas if l["id"] not in com_resposta)
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.9), gridspec_kw={"width_ratios": [1, 1.35]})
    rot = [("A", "A\nLLM sozinho"), ("C", "C\nRAG + LLM\n20 candidatos"), ("C50", "C50\nRAG + LLM\n50 candidatos")]
    ys = [ab[c]["taxa_ic95"][0] for c, _ in rot]
    lo = [ab[c]["taxa_ic95"][0] - ab[c]["taxa_ic95"][1] for c, _ in rot]
    hi = [ab[c]["taxa_ic95"][2] - ab[c]["taxa_ic95"][0] for c, _ in rot]
    a1.bar(range(3), ys, color="#9ca3af", edgecolor="#111827", linewidth=0.6, width=0.62)
    a1.errorbar(range(3), ys, yerr=[lo, hi], fmt="none", ecolor="#111827", capsize=3, linewidth=0.9)
    for x, y, h in zip(range(3), ys, hi):
        a1.text(x, y + h + 0.025, f"{y:.2f}".replace(".", ","), ha="center", fontsize=8)
    a1.set_xticks(range(3), [r for _, r in rot], fontsize=7.5)
    a1.set_ylim(0, 1.15)
    a1.set_ylabel("taxa de abstenção")
    a1.set_title("Abstenção em 27 perguntas\nsem resposta na base", fontsize=9)
    a1.spines[["top", "right"]].set_visible(False)
    for y0, v, marca in ((1, com, "o"), (0, sem, "s")):
        desloc = [((i * 37) % 11 - 5) / 22 for i in range(len(v))]      # espalha os pontos na vertical, sem sorteio
        a2.scatter(v, [y0 + d for d in desloc], s=14, marker=marca, facecolor="#9ca3af", edgecolor="#111827", linewidth=0.5)
    a2.axvline(lim["corte_youden"], color="#111827", linestyle="--", linewidth=0.9)
    a2.text(lim["corte_youden"] + 0.2, 0.5, f"corte {lim['corte_youden']:.2f}".replace(".", ","), fontsize=8, va="center")
    a2.set_yticks([0, 1], [f"sem resposta\n(n = {len(sem)})", f"com resposta\n(n = {len(com)})"], fontsize=8)
    a2.set_ylim(-0.6, 1.6)
    a2.set_xlabel("escore do 1º trecho no reordenador")
    a2.set_title(f"Escore da busca (AUC {lim['auc_ic95'][0]:.2f})".replace(".", ","), fontsize=9)
    a2.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "fig3-fora-da-base.png", dpi=220)
    plt.close(fig)


def main() -> None:
    res = json.loads((SAIDAS / "juiz_metricas.json").read_text(encoding="utf-8"))
    FIG.mkdir(exist_ok=True)
    painel(res, COND, "fig1-condicoes.png")
    if "C|gpt-oss-20b" in res["condicoes"]:
        painel(res, COND_H4, "fig2-modelos.png")
    fora_da_base()
    print("figuras gravadas em", FIG)


if __name__ == "__main__":
    main()
