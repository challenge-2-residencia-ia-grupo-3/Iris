"""concordancia_rejulgamento.py: estabilidade do juiz nos lotes julgados duas vezes (01 e 03).

Compara juiz/vereditos/substituidos/veredito-<lote>-*.jsonl (primeiro julgamento) com
juiz/vereditos/veredito-<lote>-*-r2.jsonl (rejulgamento, que é o que vale): mesmo item, mesmo modelo de
juiz (Claude Opus), sessões diferentes. Não usa a chave: é concordância item a item.

Saída: saidas/juiz_concordancia.txt e saidas/juiz_concordancia.json
Uso: python semana3/concordancia_rejulgamento.py
"""
from __future__ import annotations

import comum as C

VER = C.JUIZ / "vereditos"


def kappa(pares: list[tuple[str, str]]) -> float | None:
    """Kappa de Cohen para rótulos categóricos."""
    n = len(pares)
    if not n:
        return None
    po = sum(a == b for a, b in pares) / n
    rot = {x for p in pares for x in p}
    pe = sum((sum(a == r for a, _ in pares) / n) * (sum(b == r for _, b in pares) / n) for r in rot)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def resumo(pares: list[tuple[str, str]]) -> dict:
    return {"n": len(pares), "iguais": sum(a == b for a, b in pares),
            "concordancia": round(sum(a == b for a, b in pares) / len(pares), 3) if pares else None,
            "kappa": kappa(pares)}


def main() -> None:
    res, linhas = {}, ["ESTABILIDADE DO JUIZ: primeiro julgamento x rejulgamento (lotes 01 e 03)", ""]
    tudo: dict[str, list] = {k: [] for k in ("frase_sustentada", "util", "inventou", "absteve")}
    fid = []
    for antigo in sorted((VER / "substituidos").glob("veredito-*.jsonl")):
        lote = antigo.name.split("-claude")[0].replace("veredito-", "")
        novo = next(VER.glob(f"veredito-{lote}-*-r2.jsonl"), None)
        if novo is None:
            linhas.append(f"{lote}: rejulgamento ainda não existe")
            continue
        a = {l["id_cego"]: l for l in C.ler_jsonl(antigo)}
        b = {l["id_cego"]: l for l in C.ler_jsonl(novo)}
        assert set(a) == set(b), f"{lote}: ids diferentes entre os dois julgamentos"
        par: dict[str, list] = {k: [] for k in tudo}
        for i in sorted(a):
            fa, fb = a[i].get("frases"), b[i].get("frases")
            if fa and fb:
                assert len(fa) == len(fb), f"{i}: número de frases diferente"
                par["frase_sustentada"] += [(x["sustentada"], y["sustentada"]) for x, y in zip(fa, fb)]
                fid.append((sum(x["sustentada"] == "sim" for x in fa) / len(fa),
                            sum(y["sustentada"] == "sim" for y in fb) / len(fb)))
            for c in ("util", "inventou", "absteve"):
                par[c].append((a[i][c], b[i][c]))
        res[lote] = {k: resumo(v) for k, v in par.items()}
        linhas.append(f"{lote} ({len(a)} respostas)")
        for k, v in res[lote].items():
            linhas.append(f"    {k:18s} iguais {v['iguais']}/{v['n']} = {v['concordancia']}  kappa {v['kappa']}")
        for k in tudo:
            tudo[k] += par[k]
    res["os_dois_lotes"] = {k: resumo(v) for k, v in tudo.items()}
    linhas += ["", "Os dois lotes juntos"]
    for k, v in res["os_dois_lotes"].items():
        linhas.append(f"    {k:18s} iguais {v['iguais']}/{v['n']} = {v['concordancia']}  kappa {v['kappa']}")
    if fid:
        dif = [y - x for x, y in fid]
        res["fidelidade_por_resposta"] = {
            "n": len(fid), "media_primeiro": round(sum(x for x, _ in fid) / len(fid), 4),
            "media_rejulgamento": round(sum(y for _, y in fid) / len(fid), 4),
            "dif_media_absoluta": round(sum(abs(d) for d in dif) / len(dif), 4),
            "respostas_com_fidelidade_igual": sum(abs(d) < 1e-9 for d in dif)}
        linhas += ["", f"Fidelidade por resposta (só respostas com frases): {res['fidelidade_por_resposta']}"]
    util = tudo["util"]
    if util:
        rot = ("sim", "parcial", "não")
        linhas += ["", "útil: primeiro julgamento (linha) x rejulgamento (coluna)", "            " + "  ".join(f"{r:>8s}" for r in rot)]
        for ra in rot:
            linhas.append(f"    {ra:8s}" + "  ".join(f"{sum(1 for x, y in util if x == ra and y == rb):8d}" for rb in rot))
    C.escrever_json(C.SAIDAS / "juiz_concordancia.json", res)
    (C.SAIDAS / "juiz_concordancia.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
