"""analise_complementar.py: três análises sobre o dado já julgado (nenhuma geração, nenhum juiz novo).

Registrada no PREREG em 13/11/2026 (item d), depois de conhecidos os resultados; é complemento, não entra
na regra de decisão.

  1. Busca certa x busca errada: a qualidade do C quando o top-5 trouxe um trecho relevante do gabarito
     e quando não trouxe. Separa erro de busca de erro de redação. O A entra como controle: ele não vê os
     trechos, então uma diferença no A indicaria que as perguntas "acertadas" são só mais fáceis.
  2. Correção de Holm: os valores-p de Wilcoxon das comparações pareadas do Llama, ajustados para o
     número de comparações feitas.
  3. Menor diferença detectável: com o número de perguntas e a dispersão observada, de que tamanho uma
     diferença precisa ser para aparecer em 80% das vezes (alfa de 5%, bilateral).

Saída: saidas/analise_complementar.txt e .json
Uso: python semana3/analise_complementar.py   (ambiente com scipy)
"""
from __future__ import annotations

import math
import random

from scipy.stats import wilcoxon

import analise_juiz as A
import comum as C
import metricas as M

MOD = "llama3.1-8b"
B = 2000


def ic_dif_grupos(a: list[float], b: list[float]) -> list[float] | None:
    """Diferença de médias b - a entre dois grupos de perguntas diferentes; IC 95% por bootstrap."""
    if not a or not b:
        return None
    rng = random.Random(C.SEMENTE)
    bs = sorted(sum(rng.choice(b) for _ in b) / len(b) - sum(rng.choice(a) for _ in a) / len(a) for _ in range(B))
    return [round(sum(b) / len(b) - sum(a) / len(a), 4), round(bs[int(0.025 * B)], 4), round(bs[int(0.975 * B) - 1], 4)]


def busca_certa_x_errada(resp: list[dict]) -> tuple[dict, list[str]]:
    gab = {it["id"]: it for it in C.itens_gabarito()}
    res, L = {}, ["1. BUSCA CERTA x BUSCA ERRADA (38 perguntas com resposta; gabarito sem revisão humana)",
                  "   certa = o top-5 trouxe ao menos um trecho marcado como relevante no gabarito", ""]
    campos = ["fidelidade_sem_abstencao", "util_sim", "util_sim_ou_parcial", "inventou", "tem_frase_que_contradiz",
              "absteve_juiz"]
    for cond, arq in ((f"C|{MOD}", C.SAIDAS / "trechos_busca.jsonl"), (f"C50|{MOD}", C.AQUI / "saidas_r50" / "trechos_busca.jsonl"),
                      ("B|busca-top3", C.SAIDAS / "trechos_busca.jsonl"), ("B50|busca-top3", C.AQUI / "saidas_r50" / "trechos_busca.jsonl"),
                      (f"A|{MOD}", C.SAIDAS / "trechos_busca.jsonl")):
        busca = {l["id"]: l for l in C.ler_jsonl(arq)}
        certa = {q for q, it in gab.items() if it["trechos_relevantes"]
                 and set(it["trechos_relevantes"]) & {x["chunk_id"] for x in busca[q]["ranking_top10"][:5]}}
        errada = {q for q, it in gab.items() if it["trechos_relevantes"]} - certa
        ms = [m for m in resp if m["condicao"] == cond]
        res[cond] = {"perguntas_busca_certa": len(certa), "perguntas_busca_errada": len(errada),
                     "ids_busca_errada": sorted(errada), "campos": {}}
        nota = " (controle: não vê os trechos)" if cond.startswith("A|") else ""
        L.append(f"   {cond}{nota}: busca certa em {len(certa)} perguntas, errada em {len(errada)} {sorted(errada)}")
        for nome in campos:
            if cond.startswith("B") and nome not in ("util_sim", "util_sim_ou_parcial"):
                continue
            pq = M.media_por_pergunta(ms, A.CAMPOS_RESP[nome])
            vc, ve = [v for k, v in pq.items() if k in certa], [v for k, v in pq.items() if k in errada]
            r = {"certa": M.ic_media(vc), "n_certa": len(vc), "errada": M.ic_media(ve), "n_errada": len(ve),
                 "dif_certa_menos_errada": ic_dif_grupos(ve, vc)}
            res[cond]["campos"][nome] = r
            L.append(f"       {nome:26s} certa {A.fmt(r['certa'])} (n={len(vc)}) | errada {A.fmt(r['errada'])} (n={len(ve)}) "
                     f"| certa - errada {A.fmt(r['dif_certa_menos_errada'])}")
        L.append("")
    return res, L


def difs(resp: list[dict], cond_a: str, cond_b: str, campo: str) -> list[float]:
    pa = M.media_por_pergunta([m for m in resp if m["condicao"] == cond_a], A.CAMPOS_RESP[campo])
    pb = M.media_por_pergunta([m for m in resp if m["condicao"] == cond_b], A.CAMPOS_RESP[campo])
    return [pb[k] - pa[k] for k in sorted(set(pa) & set(pb))]


def holm_e_poder(resp: list[dict]) -> tuple[dict, list[str]]:
    familia = [(f"C - A, frases sustentadas", f"A|{MOD}", f"C|{MOD}", "fidelidade"),
               (f"C - A, útil", f"A|{MOD}", f"C|{MOD}", "util_sim"),
               (f"C - A, inventou", f"A|{MOD}", f"C|{MOD}", "inventou"),
               ("C - B1, útil", "B|busca-top1", f"C|{MOD}", "util_sim"),
               ("C - B3, útil", "B|busca-top3", f"C|{MOD}", "util_sim"),
               ("A - B1, útil", "B|busca-top1", f"A|{MOD}", "util_sim"),
               ("A - B3, útil", "B|busca-top3", f"A|{MOD}", "util_sim"),
               ("C - B1, inventou", "B|busca-top1", f"C|{MOD}", "inventou"),
               ("C - B3, inventou", "B|busca-top3", f"C|{MOD}", "inventou")]
    linhas = []
    for nome, a, b, campo in familia:
        d = difs(resp, a, b, campo)
        n = len(d)
        media = sum(d) / n
        dp = math.sqrt(sum((x - media) ** 2 for x in d) / (n - 1))
        p = 1.0 if all(abs(x) < 1e-12 for x in d) else float(wilcoxon(d, zero_method="wilcox").pvalue)
        linhas.append({"comparacao": nome, "n": n, "dif_media": round(media, 4), "dp_das_diferencas": round(dp, 4),
                       "p_wilcoxon": p, "menor_diferenca_detectavel": round((1.96 + 0.8416) * dp / math.sqrt(n), 3)})
    # Holm: ordena os p do menor para o maior; o i-ésimo é multiplicado por (m - i); mantém a ordem crescente
    m, anterior = len(linhas), 0.0
    for i, l in enumerate(sorted(linhas, key=lambda x: x["p_wilcoxon"])):
        anterior = max(anterior, min(1.0, (m - i) * l["p_wilcoxon"]))
        l["p_holm"] = anterior
    L = ["2. CORREÇÃO DE HOLM e 3. MENOR DIFERENÇA DETECTÁVEL (comparações pareadas do Llama, análise principal)",
         f"   família de {m} comparações; Wilcoxon de postos sinalizados (scipy), bilateral",
         "   menor diferença detectável = (1,96 + 0,84) x desvio-padrão das diferenças / raiz(n): poder de 80%, alfa de 5%", "",
         f"   {'comparação':28s} {'n':>3s} {'dif.':>7s} {'dp':>6s} {'p':>9s} {'p Holm':>9s} {'detectável':>10s}  passa a 5%?"]
    for l in linhas:
        L.append(f"   {l['comparacao']:28s} {l['n']:3d} {l['dif_media']:+7.3f} {l['dp_das_diferencas']:6.3f} {l['p_wilcoxon']:9.5f} "
                 f"{l['p_holm']:9.5f} {l['menor_diferenca_detectavel']:10.3f}  {'sim' if l['p_holm'] < 0.05 else 'não'}")
    return {"familia": linhas}, L


def main() -> None:
    chave, ver, _ = A.carregar()
    resp, _, _ = A.expandir(chave, ver)
    r1, l1 = busca_certa_x_errada(resp)
    r2, l2 = holm_e_poder(resp)
    cab = ["SEMANA 3 - ANÁLISES COMPLEMENTARES (juiz Claude Opus, não validado por pessoa)",
           f"gerado em {C.agora_iso()} | commit {C.commit_atual()}", ""]
    C.escrever_json(C.SAIDAS / "analise_complementar.json", {"busca_certa_x_errada": r1, "holm_e_poder": r2})
    (C.SAIDAS / "analise_complementar.txt").write_text("\n".join(cab + l1 + l2) + "\n", encoding="utf-8")
    print("\n".join(cab + l1 + l2))


if __name__ == "__main__":
    import sys
    sys.dont_write_bytecode = True
    main()
