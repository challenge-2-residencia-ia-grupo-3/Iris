"""bancada_checks.py: verificações da bancada que só leem o que já foi medido (sem modelo, sem API).

    python bancada_checks.py regressao     # compara o registro atual com a linha de base; falha (código 1) se cair
    python bancada_checks.py linha-de-base # promove o registro atual a linha de base (outputs/execucoes-base.jsonl)
    python bancada_checks.py repetir       # reprodutibilidade: mesma configuração rodada de novo dá o mesmo resultado?
    python bancada_checks.py custo         # latência, tokens e custo por peça, a partir dos registros gravados
    python bancada_checks.py divergencias  # frases em que os juízes discordam -> fila de revisão humana

Saídas em outputs/ (21-regressao.txt, 22-repeticao.txt/.json, 23-custo.txt/.json, 28-divergencias-juizes.json).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from bancada import OUT, REGISTRO, ic, jl, por_id

BASE = OUT / "execucoes-base.jsonl"
PRECO_HAIKU = {"entrada": 0.10, "saida": 0.50}   # US$ por milhão de tokens, prompts até 100 mil (11/2026)


def _ler(arq: Path) -> dict[tuple[str, str], dict]:
    return {(r["experimento"], r["variante"]): r
            for r in (json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip())}


def _principal(r: dict) -> tuple[str, dict] | None:
    for nome, m in r["metricas"].items():
        if "ic" in m:
            return nome, m
    return None


# ---------------------------------------------------------------- regressão
def regressao() -> int:
    if not REGISTRO.exists():
        sys.exit("rode antes: python bancada.py registrar")
    if not BASE.exists():
        shutil.copy(REGISTRO, BASE)
        print(f"sem linha de base: o registro atual virou a base ({BASE.name}). Nada a comparar ainda.")
        return 0
    atual, base = _ler(REGISTRO), _ler(BASE)
    L = ["REGRESSÃO: registro atual x linha de base (outputs/execucoes-base.jsonl)",
         "Regra: cai quando a média atual fica abaixo do limite inferior do IC 95% da base (mesma configuração).",
         "Só compara configurações presentes nos dois; configuração nova ou removida é listada à parte.", ""]
    caiu, n = [], 0
    for chave in sorted(set(atual) & set(base)):
        pa, pb = _principal(atual[chave]), _principal(base[chave])
        if not pa or not pb or pa[0] != pb[0]:
            continue
        n += 1
        nome, ma = pa
        mb = pb[1]
        estado = "CAIU" if ma["v"] < mb["ic"][0] else "subiu" if ma["v"] > mb["ic"][1] else "igual"
        if estado == "CAIU":
            caiu.append(chave)
        L.append(f"  {estado:6s} {chave[0][:30]:30s} {chave[1][:28]:28s} {nome:10s} base {mb['v']:.2f} "
                 f"[{mb['ic'][0]:.2f}-{mb['ic'][1]:.2f}] -> atual {ma['v']:.2f}  ({base[chave].get('commit')} -> {atual[chave].get('commit')})")
    novas, sumiram = sorted(set(atual) - set(base)), sorted(set(base) - set(atual))
    L += ["", f"Comparadas: {n}. Caíram: {len(caiu)}. Novas: {len(novas)}. Sumiram do registro: {len(sumiram)}."]
    L += [f"  nova: {a} / {b}" for a, b in novas] + [f"  sumiu: {a} / {b}" for a, b in sumiram]
    L.append("RESULTADO: " + ("FALHOU (alguma métrica caiu)" if caiu else "ok"))
    txt = "\n".join(L) + "\n"
    (OUT / "21-regressao.txt").write_text(txt, encoding="utf-8")
    print(txt)
    return 1 if caiu else 0


def linha_de_base() -> None:
    shutil.copy(REGISTRO, BASE)
    print(f"{REGISTRO.name} -> {BASE.name} ({sum(1 for _ in BASE.open())} configurações)")


# ---------------------------------------------------------------- repetição
def _kappa(a: list, b: list) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def _fid(v: dict) -> float | None:
    fr = v.get("frases") or []
    return sum(x.get("sustentada") == "sim" for x in fr) / len(fr) if fr else None


def repetir() -> None:
    L = ["REPRODUTIBILIDADE: a mesma configuração, rodada de novo, dá o mesmo resultado?", ""]
    dados = {}
    # 1) busca: o mesmo método (qwen3 0.6B + mMiniLM, top-5) em três rodadas independentes
    cfg = {"VPS 05/11 (16, gabarito Opus)": None,
           "VPS 06/11 (18, controle A_pt)": {b["id"]: b["A_pt"] for b in jl("18-bilingue.jsonl")},
           "PC RTX 06/11 (19, A_controle)": {m["id"]: m for m in jl("19-modelos-fortes.jsonl") if m["variante"] == "A_controle"},
           "VPS 06/11 (17, controle do HyDE)": {h["id"]: h["pergunta"] for h in jl("17-hyde.jsonl")}}
    rodadas = {k: v for k, v in cfg.items() if v}
    nomes = list(rodadas)
    L.append("1. Busca (qwen3 + reranker mMiniLM, top-5), mesmas 38 perguntas, rodadas em dias e máquinas diferentes")
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            q = sorted(set(rodadas[a]) & set(rodadas[b]))
            iguais = sum(rodadas[a][x]["top5"] == rodadas[b][x]["top5"] for x in q)
            mesmo_rec = sum(abs(rodadas[a][x]["recall5"] - rodadas[b][x]["recall5"]) < 1e-9 for x in q)
            L.append(f"   {a} x {b}: top-5 idêntico (mesma ordem) em {iguais}/{len(q)}; recall@5 igual em {mesmo_rec}/{len(q)}")
            dados[f"busca: {a} x {b}"] = {"top5_identico": iguais, "recall_igual": mesmo_rec, "n": len(q)}
    # 2) juízes: o mesmo juiz duas vezes nas mesmas respostas
    L += ["", "2. Juízes: mesmo juiz, mesmas respostas (prompt v1), duas rodadas"]
    resp = por_id(jl("17-respostas.jsonl"))
    respondeu = {q for q, r in resp.items() if not r["conferencia"]["absteve"]}
    for nome, a1, a2, nota in (("Claude Haiku 5.5", "17-juiz-haiku.jsonl", "17-juiz-haiku-r2.jsonl", "sem controle de temperatura"),
                               ("gpt-oss-120b (Groq)", "17-juiz-r1.jsonl", "17-juiz-r2.jsonl", "temperatura 0; rodada 2 incompleta (limite do Groq)")):
        j1, j2 = por_id(jl(a1)), por_id(jl(a2))
        q = sorted(set(j1) & set(j2) & respondeu)
        if not q:
            continue
        f1 = [_fid(j1[x]["veredito"]) for x in q]
        f2 = [_fid(j2[x]["veredito"]) for x in q]
        pares = [(a, b) for a, b in zip(f1, f2) if a is not None and b is not None]
        dif = [b - a for a, b in pares]
        m, lo, hi = ic(dif)
        t1, t2 = [a == 1.0 for a, _ in pares], [b == 1.0 for _, b in pares]
        u1 = [j1[x]["veredito"].get("util") for x in q]
        u2 = [j2[x]["veredito"].get("util") for x in q]
        L.append(f"   {nome} ({nota}), n={len(pares)}: fidelidade r2-r1 {m:+.3f} [{lo:+.3f} a {hi:+.3f}]; "
                 f"'100% sustentada' igual em {sum(a == b for a, b in zip(t1, t2))}/{len(t1)} (kappa {_kappa(t1, t2):.2f}); "
                 f"'útil' igual em {sum(a == b for a, b in zip(u1, u2))}/{len(u1)} (kappa {_kappa(u1, u2):.2f})")
        dados[f"juiz: {nome}"] = {"n": len(pares), "dif_fidelidade": [m, lo, hi], "kappa_toda": _kappa(t1, t2), "kappa_util": _kappa(u1, u2)}
    # 3) gerador: o mesmo prompt? não há duas rodadas da v1 com os mesmos trechos; registrar a lacuna
    L += ["", "3. Gerador (qwen3.8-27b, temperatura 0): sem duas rodadas do mesmo prompt com os mesmos trechos.",
          "   Lacuna registrada: para medir, gerar a v1 de novo com `avaliar_resposta.py gerar_salvos v1` (sufixo -v1b) e comparar.",
          "", "Leitura: uma diferença entre versões menor que a oscilação da própria régua não conta como melhora."]
    txt = "\n".join(L) + "\n"
    (OUT / "22-repeticao.txt").write_text(txt, encoding="utf-8")
    (OUT / "22-repeticao.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(txt)


# ---------------------------------------------------------------- custo
def _mediana(v: list[float]) -> float:
    v = sorted(v)
    return v[len(v) // 2] if v else float("nan")


def custo() -> None:
    L = ["CUSTO E LATÊNCIA POR PEÇA (a partir do que já foi gravado; máquinas diferentes, ler com cuidado)", ""]
    dados = []

    def linha(peca, onde, n, seg, extra=""):
        dados.append({"peca": peca, "onde": onde, "n": n, "mediana_s": round(seg, 2), "extra": extra})
        L.append(f"  {peca:44s} {onde:24s} n={n:3d}  mediana {seg:7.2f} s  {extra}")

    r = jl("17-respostas.jsonl")
    if r:
        linha("busca + geração (qwen3+rerank, qwen3.8-27b Groq)", "VPS CPU + Groq", len(r), _mediana([x["segundos"] for x in r]),
              "inclui espera do limite do Groq")
    b = jl("18-bilingue.jsonl")
    if b:
        linha("busca bilíngue (6 variantes juntas)", "VPS CPU", len(b), _mediana([x["segundos"] for x in b]), "inclui tradução no Groq")
    m = jl("19-modelos-fortes.jsonl")
    for v in ("A_controle", "B_reranker_bge", "C_embedding_4b", "D_os_dois"):
        g = [x for x in m if x["variante"] == v]
        if g:
            vram = OUT / f"19-vram-{v}.txt"
            linha(f"busca {g[0]['embedding']} + {g[0]['reranker']}", "PC RTX 5070 Ti", len(g), _mediana([x["segundos"] for x in g]),
                  f"VRAM {vram.read_text().strip()}" if vram.exists() else "")
    h = jl("17-juiz-haiku.jsonl")
    if h:
        te = sum(x["uso"].get("input_tokens", 0) for x in h)
        ts = sum(x["uso"].get("output_tokens", 0) for x in h)
        us = te / 1e6 * PRECO_HAIKU["entrada"] + ts / 1e6 * PRECO_HAIKU["saida"]
        linha("juiz Claude Haiku 5.5", "API Anthropic", len(h), _mediana([x["segundos"] for x in h]),
              f"tokens {te} entrada + {ts} saída = US$ {us:.3f} na rodada (US$ {us / len(h) * 1000:.2f} por mil respostas)")
    lo = jl("17-juiz-local.jsonl")
    if lo:
        te = sum(x["uso"].get("prompt_tokens") or 0 for x in lo)
        ts = sum(x["uso"].get("output_tokens") or 0 for x in lo)
        linha("juiz gpt-oss-20b local", "PC RTX (Ollama)", len(lo), _mediana([x["segundos"] for x in lo]),
              f"tokens {te} + {ts}; custo de API zero; ~24 tokens/s medidos (abaixo do esperado, ver skill de hardware)")
    L += ["", "Leitura: o gargalo de latência na VPS é o reranker na CPU (~5 s por consulta); na GPU a busca inteira leva",
          "~0,1 s. O juiz pago custa centavos por rodada; o custo real é o limite diário do plano gratuito do Groq."]
    txt = "\n".join(L) + "\n"
    (OUT / "23-custo.txt").write_text(txt, encoding="utf-8")
    (OUT / "23-custo.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(txt)


# ---------------------------------------------------------------- divergências entre juízes -> revisão
def _norm(f: str) -> str:
    return re.sub(r"\W+", " ", re.sub(r"\[T\d\]", "", f)).strip().lower()[:70]


def divergencias() -> None:
    resp = por_id(jl("17-respostas.jsonl"))
    juizes = {"gpt-oss-120b": por_id(jl("17-juiz-r1.jsonl")), "gpt-oss-20b": por_id(jl("17-juiz-local.jsonl")),
              "haiku": por_id(jl("17-juiz-haiku.jsonl"))}
    itens = []
    for q, r in sorted(resp.items()):
        if r["conferencia"]["absteve"]:
            continue
        por_frase: dict[str, dict] = {}
        for nome, J in juizes.items():
            for f in J.get(q, {}).get("veredito", {}).get("frases", []):
                k = _norm(f.get("frase", ""))
                if k:
                    por_frase.setdefault(k, {"frase": re.sub(r"\s*(\[T\d\])+", "", f["frase"]).strip(),
                                             "refs": re.findall(r"T\d", f["frase"]), "votos": {}})["votos"][nome] = {
                        "sustentada": f.get("sustentada"), "motivo": f.get("motivo", "")}
        for k, d in por_frase.items():
            v = {n: x["sustentada"] for n, x in d["votos"].items()}
            if len(v) >= 2 and len(set(v.values())) > 1:
                itens.append({"id": q, "pergunta": r["pergunta"], "frase": d["frase"], "refs": d["refs"], "votos": d["votos"]})
    destino = OUT / "28-divergencias-juizes.json"
    destino.write_text(json.dumps({"n": len(itens), "itens": itens}, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    padrao = Counter(" / ".join(f"{n}={x['sustentada']}" for n, x in sorted(i["votos"].items())) for i in itens)
    print(f"{len(itens)} frases em que os juízes discordam -> {destino.name}")
    for p, c in padrao.most_common(6):
        print(f"  {c:3d}  {p}")


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else ""
    acoes = {"regressao": regressao, "linha-de-base": linha_de_base, "repetir": repetir, "custo": custo,
             "divergencias": divergencias}
    if a not in acoes:
        print(__doc__)
        sys.exit(0)
    sys.exit(acoes[a]() or 0)
