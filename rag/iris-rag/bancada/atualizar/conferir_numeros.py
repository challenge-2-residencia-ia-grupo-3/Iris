"""conferir_numeros.py: confere se os números que o painel e o relatório mostram são os mesmos das saídas que os geraram.

Três famílias de checagem, cada uma vira um portão no vigia (ok / reprovado / aviso):
  1. painel = fonte     o painel embute os dados de pacote/outputs/*.json; números escritos à mão no texto do painel
                        (guia, glossário, telas) batem com a saída de onde vieram; a aba LLM x RAG copia certo
                        os números da semana 3.
  2. relatório = saídas  as células das tabelas 3, 4, 6 e 8 do relatório da semana 3 batem com juiz_metricas,
                        metricas e juiz_r50 (arredondado como o relatório escreve: duas casas, vírgula).
  3. julgamento íntegro  cada resposta dos lotes tem um único veredito; cada veredito tem exatamente as frases do
                        lote; nenhum lote traz campo que revele a condição; a chave cobre todos os ids.

Uso (na pasta pacote/):  python ../bancada/atualizar/conferir_numeros.py [--html reports/bancada.html]
Saída: JSON com uma linha por portão; sai com 1 se algum reprovou. Só biblioteca padrão.
Se uma entrada não existe nesta versão (por exemplo, o relatório ainda não foi escrito), o portão vira aviso.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PACOTE = Path(__file__).resolve().parents[2] / "pacote"
IRIS = PACOTE.parent
S3 = IRIS / "semana3"
RELATORIO = IRIS.parent / "entregas/2026-11-13-llm-x-rag/relatorio.md"


def ler(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() and p.stat().st_size else None


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def br(v: float, casas: int = 2) -> str:
    """Como o relatório escreve: 0,77 / −0,32 / +0,33 sem sinal."""
    # arredonda meio para cima, como o relatório (0,175 -> 0,18); o f-string do Python daria 0,17 pelo binário
    t = str(Decimal(str(abs(v))).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)).replace(".", ",")
    return ("−" if v < 0 and t.strip("0,") else "") + t


def ic_br(a) -> str:
    return f"{br(a[0])} [{br(a[1])}; {br(a[2])}]"


def portao(nome: str, falhas: list[str], conferidos: int, aviso: str = "") -> dict:
    if aviso and not conferidos:
        return {"portao": nome, "ok": None, "detalhe": aviso}
    return {"portao": nome, "ok": not falhas,
            "detalhe": "; ".join(falhas[:8]) + (f" (+{len(falhas) - 8})" if len(falhas) > 8 else "") if falhas
            else f"{conferidos} números conferidos"}


# 1 ---------------------------------------------------------------- painel = fonte
def p_painel(html: Path | None) -> dict:
    falhas, n = [], 0
    out = PACOTE / "outputs"
    # 1a. números escritos à mão no texto do painel
    av, at = ler(out / "32-avaliacao.json"), ler(out / "35-ataque.json")
    textos = {a: (PACOTE / a).read_text(encoding="utf-8") for a in ("guia.py", "glossario.js", "qualidade.js") if (PACOTE / a).exists()}
    esperado = {}
    if av:
        esperado[r"(\d[\d.]*) questões"] = (int(av.get("n_avaliados") or (av.get("conjunto") or {}).get("n_itens") or 0), "32-avaliacao.json n_avaliados")
    if at:
        esperado[r"(\d[\d.]*) casos"] = (int((at.get("n") or {}).get("casos") or 0), "35-ataque.json n.casos")
    for arq, t in textos.items():
        for padrao, (v, fonte) in esperado.items():
            for m in re.finditer(padrao, t):
                n += 1
                escrito = int(m.group(1).replace(".", ""))
                if escrito != v:
                    falhas.append(f"{arq}: texto diz '{m.group(0)}', {fonte} = {v}")
    # 1b. o HTML publicado embute as mesmas saídas que estão em outputs/
    if html and html.exists():
        h = html.read_text(encoding="utf-8")
        i = h.find("const DADOS=")
        if i < 0:
            falhas.append("painel sem o bloco DADOS")
        else:
            fim = h.find(";</script>", i)
            dados = json.loads(h[i + len("const DADOS="):fim].replace("<\\/", "</"))
            for chave, arq in (("langgraph", "39-langgraph.json"), ("q_juiz", "33-juiz-calibracao.json"), ("q_rag", "34-rag-triade.json"),
                               ("q_ataque", "35-ataque.json"), ("q_orcamento", "36-orcamento.json"), ("q_producao", "37-producao.json"),
                               ("llmxrag", "40-llm-x-rag.json"), ("etapas", "31-etapas.json")):
                f = ler(out / arq)
                if f is None:
                    continue
                n += 1
                if dados.get(chave) != f:
                    falhas.append(f"painel mostra {chave} diferente de outputs/{arq} (painel gerado antes da saída mudar?)")
    # 1c. a aba LLM x RAG copia os números da semana 3 sem trocar nada
    X, J, R = ler(out / "40-llm-x-rag.json"), ler(S3 / "saidas/juiz_metricas.json"), ler(S3 / "saidas_r50/juiz_r50.json")
    if X and J:
        pares = {"A": "A|llama3.1-8b", "B1": "B|busca-top1", "B3": "B|busca-top3", "C": "C|llama3.1-8b",
                 "A-gptoss": "A|gpt-oss-20b", "C-gptoss": "C|gpt-oss-20b"}
        for nome, chave in pares.items():
            for m in ("fidelidade", "util_sim", "inventou", "fidelidade_sem_abstencao"):
                fonte = ((J["condicoes"].get(chave) or {}).get(m) or {}).get("media_ic95")
                n += 1
                if fonte != (X["condicoes"].get(nome) or {}).get(m):
                    falhas.append(f"LLM x RAG: {nome}.{m} = {(X['condicoes'].get(nome) or {}).get(m)}, juiz_metricas = {fonte}")
        n += 1
        if X.get("decisao") != J.get("decisao"):
            falhas.append("LLM x RAG: decisão diferente da do juiz_metricas")
        p = (J["pareados"].get("C - A|llama3.1-8b") or {}).get("fidelidade") or {}
        n += 1
        if ((X["pareados"].get("C − A") or {}).get("fidelidade") or {}).get("dif") != p.get("dif_media_ic95"):
            falhas.append("LLM x RAG: diferença C − A em fidelidade diferente do juiz_metricas")
        if R:
            n += 1
            if (X["condicoes"].get("C50") or {}).get("util_sim") != R["condicoes"]["C50|llama3.1-8b"]["util_sim"]["media_ic95"]:
                falhas.append("LLM x RAG: C50 útil diferente do juiz_r50")
        # nota por pergunta: média das repetições do juiz_por_resposta
        por = jl(S3 / "saidas/juiz_por_resposta.jsonl")
        if por:
            q = next((p for p in X["perguntas"] if p["id"] == "Q40"), None)
            linhas = [l for l in por if l["id"] == "Q40" and l["condicao"] == "C|llama3.1-8b"]
            if q and linhas:
                n += 1
                esper = round(sum(l["util"] == "sim" for l in linhas) / len(linhas), 4)
                if (q.get("notas") or {}).get("C", {}).get("util") != esper:
                    falhas.append(f"LLM x RAG: Q40/C útil {(q.get('notas') or {}).get('C', {}).get('util')} ≠ {esper}")
    return portao("painel = fonte", falhas, n, "nada para conferir nesta versão")


# 2 ---------------------------------------------------------------- relatório = saídas
def celulas(md: str, legenda: str) -> list[list[str]]:
    i = md.find(legenda)
    if i < 0:
        return []
    linhas = []
    for l in md[i:].splitlines()[1:]:
        if l.startswith("|"):
            linhas.append([c.strip() for c in l.strip().strip("|").split("|")])
        elif linhas:
            break
    return linhas[2:]       # sem cabeçalho e sem a linha ---


def p_relatorio() -> dict:
    J, M, R = ler(S3 / "saidas/juiz_metricas.json"), ler(S3 / "saidas/metricas.json"), ler(S3 / "saidas_r50/juiz_r50.json")
    if not (RELATORIO.exists() and J and M):
        return portao("relatório = saídas", [], 0, "relatório da semana 3 ou saídas ausentes nesta versão")
    md = RELATORIO.read_text(encoding="utf-8")
    falhas, n = [], 0
    C = J["condicoes"]

    def conf(onde: str, escrito: str, esperado: str):
        nonlocal n
        n += 1
        if escrito.replace(" ", "") != esperado.replace(" ", ""):
            falhas.append(f"{onde}: relatório '{escrito}', saída '{esperado}'")

    t3 = {l[0]: l[1:] for l in celulas(md, "Tabela 3 –")}
    cols = ["A|llama3.1-8b", "B|busca-top1", "B|busca-top3", "C|llama3.1-8b"]
    for rot, m in (("Frases sustentadas pela base (juiz)", "fidelidade"), ("Idem, só quando o sistema respondeu", "fidelidade_sem_abstencao"),
                   ("Resposta útil (juiz)", "util_sim"), ("Inventou fato ou fonte (juiz)", "inventou")):
        for j, c in enumerate(cols):
            if rot in t3 and m in C[c] and j < len(t3[rot]) and "[" in t3[rot][j]:
                conf(f"Tabela 3, {rot}, {c}", t3[rot][j], ic_br(C[c][m]["media_ic95"]))
    if "Abstenção em Q39 e Q40 (código)" in t3:
        for j, c in ((0, "A|llama3.1-8b"), (3, "C|llama3.1-8b")):
            conf(f"Tabela 3, abstenção, {c}", t3["Abstenção em Q39 e Q40 (código)"][j], M["A_C"][c]["abstencao_correta_q39_q40"].replace("/", " de "))
    if "Latência, percentil 95" in t3:
        for j, c in ((0, "A|llama3.1-8b"), (3, "C|llama3.1-8b")):
            conf(f"Tabela 3, latência, {c}", t3["Latência, percentil 95"][j], br(M["A_C"][c]["latencia_p95_s"], 1) + " s")

    P = J["pareados"]
    for l in celulas(md, "Tabela 4 –"):
        comp, met, dif = l[0], l[1], l[2]
        chave = {"C − A": "C - A|llama3.1-8b", "C − B1": "C|llama3.1-8b - B|busca-top1", "C − B3": "C|llama3.1-8b - B|busca-top3"}.get(comp)
        m = {"frases sustentadas": "fidelidade", "resposta útil": "util_sim", "inventou": "inventou", "útil ou parcial": "util_sim_ou_parcial",
             "idem, só respondidas (n = 22)": "fidelidade_sem_abstencao"}.get(met)
        if chave and m and m in P[chave]:
            d = P[chave][m]["dif_media_ic95"]
            conf(f"Tabela 4, {comp}, {met}", dif.lstrip("+"), ic_br(d))

    t6 = {l[0]: l[1:] for l in celulas(md, "Tabela 6 –")}
    cols6 = ["A|llama3.1-8b", "C|llama3.1-8b", "A|gpt-oss-20b", "C|gpt-oss-20b"]
    for rot, m in (("Frases sustentadas pela base", "fidelidade"), ("Resposta útil", "util_sim"), ("Inventou fato ou fonte", "inventou")):
        for j, c in enumerate(cols6):
            if rot in t6 and "[" in t6[rot][j]:
                conf(f"Tabela 6, {rot}, {c}", t6[rot][j], ic_br(C[c][m]["media_ic95"]))

    if R:
        t8 = {l[0]: l[1:] for l in celulas(md, "Tabela 8 –")}
        RC = R["condicoes"]
        for rot, m in (("Frases sustentadas pela base", "fidelidade"), ("Resposta útil", "util_sim")):
            for j, c in ((1, "C50|llama3.1-8b"), (3, "B50|busca-top3")):
                if rot in t8 and "[" in t8[rot][j] and m in RC[c]:
                    conf(f"Tabela 8, {rot}, {c}", t8[rot][j], ic_br(RC[c][m]["media_ic95"]))

    # números do texto corrido que viraram manchete
    b = M["B"]
    n += 1
    if f"recall@5 de {br(b['recall@5'][0])}" not in md:
        falhas.append(f"seção 6.3 não traz o recall@5 da saída ({br(b['recall@5'][0])})")
    d = J["D"]["llama3.1-8b"]["por_config"]["completo"]
    n += 1
    if f"{d['reserva']} das {d['saidas']} saídas" not in md:
        falhas.append(f"seção 6.4 não traz '{d['reserva']} das {d['saidas']} saídas' de reserva")
    venc = J["decisao"]["llama3.1-8b"]["vencedor"]
    n += 1
    if f"a condição escolhida é {venc}" not in md:
        falhas.append(f"seção 8.1 não diz que a regra escolheu {venc}")
    return portao("relatório = saídas", falhas, n)


# 3 ---------------------------------------------------------------- julgamento íntegro
REVELA = {"teste", "modelo", "config", "condicao", "repeticao", "repeticoes", "provedor", "id_modelo", "versao_prompt"}


def p_julgamento() -> dict:
    chave = (ler(S3 / "juiz/chave.json") or {}).get("chave")
    vered = sorted((S3 / "juiz/vereditos").glob("veredito-*.jsonl")) if (S3 / "juiz/vereditos").exists() else []
    if not chave or not vered:
        return portao("julgamento íntegro", [], 0, "chave ou vereditos ausentes nesta versão")
    falhas, n = [], 0
    ver: dict[str, dict] = {}
    for arq in vered:
        for l in jl(arq):
            n += 1
            if l["id_cego"] in ver:
                falhas.append(f"{l['id_cego']} julgado duas vezes ({ver[l['id_cego']]['_arq']} e {arq.name})")
            ver[l["id_cego"]] = l | {"_arq": arq.name}
            if l["id_cego"] not in chave:
                falhas.append(f"{arq.name}: {l['id_cego']} não existe na chave")
    sem = [k for k in chave if k not in ver]
    if sem:
        falhas.append(f"{len(sem)} respostas da chave sem veredito (ex.: {', '.join(sem[:3])})")
    lotes = sorted((S3 / "juiz").glob("*lote-*.jsonl"))
    for arq in lotes:                       # os lotes ficam fora do git: só confere onde existem (VPS e PC)
        for l in jl(arq):
            vaz = REVELA & set(l)
            if vaz:
                falhas.append(f"{arq.name}: {l['id_cego']} traz {sorted(vaz)} (quebra o cegamento)")
            v = ver.get(l["id_cego"])
            if v is None:
                continue
            fl = l.get("frases")
            fv = v.get("frases")
            n += 1
            if fl is None and fv not in (None, []):
                falhas.append(f"{l['id_cego']}: trecho cru julgado frase a frase")
            elif fl is not None and [f["n"] for f in fl] != [f["n"] for f in fv or []]:
                falhas.append(f"{l['id_cego']}: lote tem {len(fl)} frases, veredito tem {len(fv or [])}")
            for f in fv or []:
                if f.get("sustentada") not in ("sim", "parcial", "não"):
                    falhas.append(f"{l['id_cego']} frase {f.get('n')}: valor '{f.get('sustentada')}' fora da rubrica")
    for v in ver.values():
        for campo in ("util", "inventou"):
            if campo in v and v[campo] not in ("sim", "parcial", "não"):
                falhas.append(f"{v['id_cego']}: {campo} = '{v[campo]}' fora da rubrica")
    return portao("julgamento íntegro", falhas, n,
                  "" if lotes else "lotes ausentes nesta versão (ficam fora do git): conferida só a chave")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", type=Path, default=PACOTE / "reports/bancada.html")
    a = ap.parse_args()
    portoes = [p_painel(a.html), p_relatorio(), p_julgamento()]
    print(json.dumps(portoes, ensure_ascii=False, indent=1))
    return 1 if any(p["ok"] is False for p in portoes) else 0


if __name__ == "__main__":
    sys.exit(main())
