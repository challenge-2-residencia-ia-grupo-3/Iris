"""bancada.py: a bancada de acompanhamento do RAG do Íris (protótipo).

Três coisas, sem rodar modelo nenhum (só lê o que as avaliações já gravaram em outputs/):

    python bancada.py registrar        # monta outputs/execucoes.jsonl: uma linha por configuração medida,
                                       # com as métricas, o intervalo de confiança e o commit que produziu
    python bancada.py rastro Q07       # no terminal: o caminho de uma pergunta pelo RAG
                                       # (o que cada configuração de busca trouxe, as respostas, os juízes)
    python bancada.py html             # gera reports/bancada.html (abas Rastro, Qualidade, Testes)

O HTML leva o texto integral dos trechos, inclusive de documentos sem licença aberta: fica em reports/,
que não vai para o git. O registro (execucoes.jsonl) só tem números e vai para o git.
Só biblioteca padrão do Python.
"""
from __future__ import annotations

import html
import json
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
OUT = AQUI / "outputs"
REPORTS = AQUI / "reports"
GAB = AQUI.parent / "gabarito" / "gabarito_rascunho_v0.json"
REGISTRO = OUT / "execucoes.jsonl"
SEMENTE = 20261106
AVISO = re.compile(r"sem refer[êe]ncias|n[ãa]o (constitui|serve como|é) evid[êe]ncia|"
                   r"n[ãa]o (usar|deve ser usad)|instru[çc][ãa]o de uso|aviso de uso", re.I)


# ---------------------------------------------------------------- leitura
def jl(nome: str) -> list[dict]:
    p = OUT / nome
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def por_id(linhas: list[dict]) -> dict[str, dict]:
    return {l["id"]: l for l in linhas}


def gabarito() -> dict[str, dict]:
    return {i["id"]: i for i in json.loads(GAB.read_text(encoding="utf-8"))["itens"]}


def origem(arquivo: Path) -> dict:
    """Commit que gravou o arquivo pela última vez (ou 'não versionado' se ele fica fora do git)."""
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%h|%ad", "--date=short", "--", arquivo.name],
                           cwd=arquivo.parent, capture_output=True, text=True, timeout=20)
        if r.stdout.strip():
            sha, data = r.stdout.strip().split("|")
            return {"commit": sha, "data": data}
    except (OSError, subprocess.SubprocessError):
        pass
    data = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%Y-%m-%d") if arquivo.exists() else ""
    return {"commit": "não versionado", "data": data}


def ic(vals: list[float], n_boot: int = 2000) -> tuple[float, float, float]:
    rng = random.Random(SEMENTE)
    m = sum(vals) / len(vals)
    bs = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(n_boot))
    return round(m, 3), round(bs[int(0.025 * n_boot)], 3), round(bs[int(0.975 * n_boot) - 1], 3)


# ---------------------------------------------------------------- 1. registro de execuções
def _busca(experimento, variante, descricao, linhas, fonte, extra=None):
    rec = [l["recall5"] for l in linhas]
    m, lo, hi = ic(rec)
    return {"experimento": experimento, "variante": variante, "descricao": descricao, "camada": "busca",
            "n": len(linhas), "metricas": {"recall@5": {"v": m, "ic": [lo, hi]},
                                           "hit@5": {"k": sum(bool(l["hit5"]) for l in linhas), "n": len(linhas)}},
            "fonte": fonte.name, **origem(fonte), **({"extra": extra} if extra else {})}


def _fidelidade(vered: dict) -> dict | None:
    fr = vered.get("frases") or []
    if not fr:
        return None
    sust = sum(x.get("sustentada") == "sim" for x in fr) / len(fr)
    return {"fid": sust, "toda": sust == 1.0, "util": vered.get("util")}


def montar_registro() -> list[dict]:
    R = []
    # 16: seis métodos de busca no gabarito do Opus (só há o .txt)
    t16 = OUT / "16-gabarito-opus.txt"
    if t16.exists():
        for l in t16.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(bm25|mpnet|qwen3\+rerank|qwen3|hibrido\+rerank|hibrido)\s+([\d.]+) \[([\d.]+)-([\d.]+)\]\s+"
                         r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", l)
            if m and not any(r["variante"] == m.group(1) for r in R):
                R.append({"experimento": "16 métodos de busca", "variante": m.group(1), "camada": "busca",
                          "descricao": "busca no gabarito do Opus (38 perguntas com resposta)", "n": 38,
                          "metricas": {"recall@5": {"v": float(m.group(2)), "ic": [float(m.group(3)), float(m.group(4))]},
                                       "hit@5": {"k": round(float(m.group(6)) * 38), "n": 38},
                                       "MRR": {"v": float(m.group(7))}},
                          "fonte": t16.name, **origem(t16)})
    # 17 HyDE
    H = jl("17-hyde.jsonl")
    for v, d in (("pergunta", "controle: a própria pergunta"), ("hyde_pt", "hipótese em português"),
                 ("hyde_en", "hipótese em inglês"), ("pergunta+hyde_en", "pergunta + hipótese em inglês")):
        if H:
            R.append(_busca("17 HyDE", v, d, [h[v] for h in H], OUT / "17-hyde.jsonl"))
    # 17 paráfrase leiga
    P = jl("17-busca-parafrases.jsonl")
    for v, d in (("original", "pergunta original"), ("parafrase", "mesma pergunta sem termos técnicos")):
        if P:
            R.append(_busca("17 paráfrase leiga", v, d, [p[v] for p in P], OUT / "17-busca-parafrases.jsonl"))
    # 18 bilíngue
    B = jl("18-bilingue.jsonl")
    desc18 = {"A_pt": "controle (pergunta em português)", "B_en": "só a tradução em inglês",
              "C_rrf": "RRF das duas listas", "D_uniao_pt": "união dos candidatos, reranker com a pergunta PT",
              "E_uniao_pt_en": "união, reranker PT+EN", "F_4listas": "4 listas (BM25 e Qwen3, PT e EN)"}
    for v, d in desc18.items():
        if B:
            R.append(_busca("18 busca bilíngue", v, d, [b[v] for b in B], OUT / "18-bilingue.jsonl"))
    # 19 modelos fortes (PC)
    M = jl("19-modelos-fortes.jsonl")
    for v in ("A_controle", "B_reranker_bge", "C_embedding_4b", "D_os_dois"):
        g = [m for m in M if m["variante"] == v]
        if g:
            vram = OUT / f"19-vram-{v}.txt"
            seg = sorted(x["segundos"] for x in g)[len(g) // 2]
            R.append(_busca("19 modelos maiores (PC)", v, f"embedding {g[0]['embedding']} + reranker {g[0]['reranker']}",
                            g, OUT / "19-modelos-fortes.jsonl",
                            {"VRAM": vram.read_text().strip() if vram.exists() else None, "s/pergunta (GPU)": seg}))
    # 17 juízes nas respostas v1
    resp = por_id(jl("17-respostas.jsonl"))
    respondeu = {q for q, r in resp.items() if not r["conferencia"]["absteve"]}
    for arq, nome in (("17-juiz-r1.jsonl", "gpt-oss-120b (Groq)"), ("17-juiz-local.jsonl", "gpt-oss-20b (local, PC)"),
                      ("17-juiz-haiku.jsonl", "Claude Haiku 5.5, rodada 1"), ("17-juiz-haiku-r2.jsonl", "Claude Haiku 5.5, rodada 2")):
        J = [j for j in jl(arq) if j["id"] in respondeu]
        S = [s for j in J if (s := _fidelidade(j.get("veredito", {})))]
        if S:
            m, lo, hi = ic([s["fid"] for s in S])
            R.append({"experimento": "17 juízes da resposta (prompt v1)", "variante": nome, "camada": "resposta",
                      "descricao": "fração de frases sustentadas pelo trecho, média por resposta", "n": len(S),
                      "metricas": {"fidelidade": {"v": m, "ic": [lo, hi]},
                                   "100% sustentada": {"k": sum(s["toda"] for s in S), "n": len(S)},
                                   "útil = sim": {"k": sum(s["util"] == "sim" for s in S), "n": len(S)}},
                      "fonte": arq, **origem(OUT / arq)})
    # 20 versões do prompt: comportamento mecânico (sem juiz ainda para v2/v3)
    for v, arq in (("v1", "17-respostas.jsonl"), ("v2", "17-respostas-v2.jsonl"), ("v3", "17-respostas-v3.jsonl")):
        rr = jl(arq)
        if not rr:
            continue
        resp_ids = [r for r in rr if not r["conferencia"]["absteve"]]
        R.append({"experimento": "20 versões do prompt", "variante": v, "camada": "resposta",
                  "descricao": "conferência mecânica, mesmos trechos para v2 e v3", "n": len(rr),
                  "metricas": {"respondeu": {"k": len(resp_ids), "n": len(rr)},
                               "abstenção certa Q39/Q40": {"k": sum(r["conferencia"]["absteve"] for r in rr if r["id"] in ("Q39", "Q40")), "n": 2},
                               "copia o aviso da curadoria": {"k": sum(bool(AVISO.search(r["resposta"])) for r in resp_ids), "n": len(resp_ids)},
                               "frases sem citação": {"k": sum(len(r["conferencia"].get("frases_sem_citacao", [])) for r in resp_ids)}},
                  "fonte": arq, **origem(OUT / arq)})
    return R


def etapa_registrar() -> None:
    R = montar_registro()
    REGISTRO.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in R), encoding="utf-8")
    print(f"{len(R)} configurações medidas -> {REGISTRO.relative_to(AQUI)}")
    for r in R:
        m = r["metricas"]
        principal = next(iter(m.items()))
        val = principal[1]
        txt = (f"{val['v']:.2f} [{val['ic'][0]:.2f}-{val['ic'][1]:.2f}]" if "ic" in val
               else f"{val['k']}/{val.get('n', '')}" if "k" in val else val.get("v"))
        print(f"  {r['experimento'][:34]:34s} {r['variante'][:30]:30s} {principal[0]:10s} {txt:20s} {r['commit']}")


# ---------------------------------------------------------------- 2. rastro de uma pergunta
def montar_rastro() -> tuple[list[dict], dict[str, dict]]:
    G = gabarito()
    resp = {v: por_id(jl(a)) for v, a in (("v1", "17-respostas.jsonl"), ("v2", "17-respostas-v2.jsonl"),
                                          ("v3", "17-respostas-v3.jsonl"))}
    juizes = {n: por_id(jl(a)) for n, a in (("gpt-oss-120b", "17-juiz-r1.jsonl"), ("gpt-oss-20b local", "17-juiz-local.jsonl"),
                                           ("Haiku 5.5", "17-juiz-haiku.jsonl"))}
    hyde, par, bil = por_id(jl("17-hyde.jsonl")), por_id(jl("17-busca-parafrases.jsonl")), por_id(jl("18-bilingue.jsonl"))
    mf = {}
    for l in jl("19-modelos-fortes.jsonl"):
        mf.setdefault(l["id"], {})[l["variante"]] = l
    parafrases = json.loads((OUT / "17-parafrases.json").read_text(encoding="utf-8")) if (OUT / "17-parafrases.json").exists() else {}
    trad = json.loads((OUT / "18-traducoes.json").read_text(encoding="utf-8")) if (OUT / "18-traducoes.json").exists() else {}
    textos_v1 = {t["chunk_id"]: t["texto"] for r in resp["v1"].values() for t in r["trechos"]}
    chunks = {}
    cj = AQUI / "chunks.jsonl"
    if cj.exists():
        for l in cj.read_text(encoding="utf-8").splitlines():
            c = json.loads(l)
            chunks[c["chunk_id"]] = {"doc": c["doc_id"], "idioma": c.get("idioma"), "secao": c.get("secao"),
                                     "aviso": c.get("nota_uso") if c.get("nao_usar_para") else "", "texto": c["texto"]}
    perguntas, usados = [], set()
    for q, g in sorted(G.items()):
        buscas = []
        if q in resp["v1"]:
            buscas.append(("sistema atual (qwen3+rerank)", "o que o gerador recebeu", [t["chunk_id"] for t in resp["v1"][q]["trechos"]]))
        for v, d in (("B_en", "só em inglês"), ("D_uniao_pt", "bilíngue: união PT+EN"), ("F_4listas", "bilíngue: 4 listas")):
            if q in bil:
                buscas.append((f"18 {v}", d, bil[q][v]["top5"]))
        for v, d in (("C_embedding_4b", "embedding 4B (PC)"), ("D_os_dois", "4B + reranker bge-m3 (PC)")):
            if q in mf and v in mf[q]:
                buscas.append((f"19 {v}", d, mf[q][v]["top5"]))
        if q in hyde:
            buscas.append(("17 hyde_pt", "HyDE em português (rejeitado)", hyde[q]["hyde_pt"]["top5"]))
        if q in par:
            buscas.append(("17 paráfrase", "pergunta sem termos técnicos", par[q]["parafrase"]["top5"]))
        for _, _, ids in buscas:
            usados.update(ids)
        respostas = {v: {"texto": r[q]["resposta"], "absteve": r[q]["conferencia"]["absteve"],
                         "sem_citacao": len(r[q]["conferencia"].get("frases_sem_citacao", [])),
                         "copia_aviso": bool(AVISO.search(r[q]["resposta"]))}
                     for v, r in resp.items() if q in r}
        vereditos = {n: {"util": J[q]["veredito"].get("util"),
                         "frases": [{"frase": f.get("frase", ""), "sust": f.get("sustentada"), "cit": f.get("citacao"),
                                     "motivo": f.get("motivo", "")} for f in J[q]["veredito"].get("frases", [])]}
                     for n, J in juizes.items() if q in J}
        perguntas.append({"id": q, "tipo": g["tipo"], "pergunta": g["pergunta"], "barreira": g.get("barreira"),
                          "relevantes": g.get("trechos_relevantes", []), "parciais": g.get("trechos_parciais", []),
                          "traducao": trad.get(q, {}).get("en"), "parafrase": parafrases.get(q, {}).get("parafrase"),
                          "buscas": [{"config": c, "desc": d, "top5": ids} for c, d, ids in buscas],
                          "respostas": respostas, "juizes": vereditos})
        usados.update(g.get("trechos_relevantes", []))
    textos = {}
    for cid in usados:
        if cid in chunks:
            textos[cid] = chunks[cid]
        elif cid in textos_v1:
            textos[cid] = {"doc": cid.split("#")[0], "texto": textos_v1[cid]}
    return perguntas, textos


def etapa_rastro(q: str) -> None:
    perguntas, textos = montar_rastro()
    p = next((x for x in perguntas if x["id"] == q.upper()), None)
    if not p:
        sys.exit(f"pergunta {q} não existe (use Q01 a Q40)")
    rel, parc = set(p["relevantes"]), set(p["parciais"])
    print(f"\n{p['id']} [{p['tipo']}] {p['pergunta']}")
    if p["parafrase"]:
        print(f"   paráfrase leiga: {p['parafrase']}")
    print(f"   gabarito: {len(rel)} trechos que respondem, {len(parc)} que ajudam em parte\n")
    print("BUSCA  (R = responde, p = em parte, . = fora do gabarito)")
    for b in p["buscas"]:
        marcas = "".join("R" if c in rel else "p" if c in parc else "." for c in b["top5"])
        acertos = sum(c in rel for c in b["top5"])
        print(f"   {b['config'][:30]:30s} {marcas:5s}  {acertos}/{len(rel)} certos   {b['desc']}")
    print("\nTRECHOS ENTREGUES AO GERADOR")
    for i, c in enumerate(p["buscas"][0]["top5"] if p["buscas"] else [], 1):
        t = textos.get(c, {})
        marca = "R" if c in rel else "p" if c in parc else "."
        aviso = "  [aviso da curadoria]" if t.get("aviso") else ""
        print(f"   T{i} {marca} {c}{aviso}")
    for v, r in p["respostas"].items():
        print(f"\nRESPOSTA {v}" + ("  (absteve)" if r["absteve"] else "") + ("  (copia o aviso)" if r["copia_aviso"] else ""))
        print("   " + r["texto"].replace("\n", "\n   ")[:1200])
    for n, j in p["juizes"].items():
        cont = {}
        for f in j["frases"]:
            cont[f["sust"]] = cont.get(f["sust"], 0) + 1
        print(f"\nJUIZ {n}: útil={j['util']}  frases: " + ", ".join(f"{k}={v}" for k, v in sorted(cont.items(), key=lambda x: str(x[0]))))
        for f in j["frases"]:
            if f["sust"] != "sim":
                print(f"   - ({f['sust']}) {f['frase'][:110]}\n       motivo: {f['motivo'][:140]}")


# ---------------------------------------------------------------- 3. HTML
TESTES = [
    # (comando, o que faz, situação)
    ("make help / check / test", "lista de comandos, smoke-check do ambiente, 67 testes automáticos", "existe no repo do grupo"),
    ("make rag", "central interativa do RAG (métricas, busca, chunks)", "existe no repo do grupo"),
    ("make extrator / extrator-bench / extrator-analytics", "menu, benchmark de 30 questões e painel do extrator (Ian)", "existe no repo do grupo"),
    ("make docs", "portal MkDocs", "existe no repo do grupo"),
    ("make bancada", "gera este painel (só lê outputs/)", "protótipo"),
    ("make rastro Q=Q07", "caminho de uma pergunta pelo RAG, no terminal", "protótipo"),
    ("make registrar", "uma linha por configuração medida, com IC e commit", "protótipo"),
    ("make regressao", "compara com a linha de base e falha (código 1) se uma métrica cair", "protótipo"),
    ("make repetir", "reprodutibilidade da busca e dos juízes", "protótipo"),
    ("make custo", "latência, tokens e custo por peça", "protótipo"),
    ("make revisao", "frases em que os juízes discordam, para conferência humana", "protótipo"),
    ("make rastro-pipeline", "o Íris inteiro, etapa por etapa, para um material", "protótipo"),
    ("make adversarial", "dados pessoais, injeção de prompt e formatos difíceis", "protótipo"),
    ("make ablacao", "com e sem cada peça", "protótipo"),
    ("make mapa", "módulos, quem importa quem, testes, etapas do pipeline", "protótipo"),
    ("vigia (timer a cada 10 min)", "commit novo -> portões -> publica só se tudo passar; senão mantém o último bom", "protótipo"),
    ("make parafrase", "perguntas sem termos técnicos (já medido no RAG: -0,13)", "proposta"),
    ("CI no pull request", "rodar make test + make regressao a cada PR do grupo", "proposta"),
]


def _opcional(nome: str, json_=True):
    p = OUT / nome
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")) if json_ else p.read_text(encoding="utf-8")
    except json.JSONDecodeError:
        return None


CSS = """:root{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--bd:#30363d;--tx:#e6edf3;--tx2:#8b949e;--az:#58a6ff;
--vd:#3fb950;--am:#d29922;--vm:#f85149;--rx:#bc8cff}
*{box-sizing:border-box}html{color-scheme:dark}body{font:14px/1.5 -apple-system,system-ui,"Segoe UI",sans-serif;margin:0;color:var(--tx);background:var(--bg)}
header{padding:14px 22px;border-bottom:1px solid var(--bd);background:var(--bg2)}header h1{font-size:18px;margin:0}
header p{margin:3px 0 0;color:var(--tx2);font-size:12px}
nav{display:flex;flex-wrap:wrap;gap:4px;padding:8px 22px;background:var(--bg2);border-bottom:1px solid var(--bd);position:sticky;top:0;z-index:5}
nav button{border:1px solid var(--bd);background:var(--bg3);color:var(--tx);border-radius:6px;padding:6px 12px;cursor:pointer;font-size:13px}
nav button:hover{border-color:var(--az)}nav button.on{background:#1f6feb;border-color:#1f6feb;color:#fff}
main{padding:14px 22px;max-width:1360px}.aba{display:none}.aba.on{display:block}
.card{background:var(--bg2);border:1px solid var(--bd);border-radius:8px;padding:12px 14px;margin:10px 0}
h2{font-size:15px;margin:2px 0 8px}h3{font-size:13px;margin:6px 0}.m{color:var(--tx2);font-size:12px}
select{font-size:13px;padding:6px;max-width:100%;background:var(--bg3);color:var(--tx);border:1px solid var(--bd);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:12.5px}td,th{border-bottom:1px solid var(--bd);padding:5px 6px;text-align:left;vertical-align:top}
th{color:var(--tx2);font-weight:600}tr:hover td{background:#1c2128}
.chip{display:inline-block;min-width:26px;text-align:center;padding:2px 6px;margin:1px;border-radius:5px;cursor:pointer;font-size:11.5px;border:1px solid #3d444d;background:#2a313c;color:#c9d1d9}
.R{background:#2ea043;color:#fff;border-color:#3fb950;font-weight:600}.p{background:#d29922;color:#0d1117;border-color:#e3b341;font-weight:600}
pre{white-space:pre-wrap;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--bg);border:1px solid var(--bd);padding:8px;border-radius:6px;max-height:300px;overflow:auto;color:var(--tx)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}
.s-sim{color:var(--vd)}.s-parcial{color:var(--am)}.s-nao{color:var(--vm)}
.tag{font-size:11px;padding:1px 7px;border-radius:10px;background:var(--bg3);border:1px solid var(--bd);margin-left:4px;color:var(--tx2)}
.ok td:last-child{color:var(--vd)}.prot td:last-child{color:var(--az)}.prop td:last-child{color:var(--am)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px}
.kpi{background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:10px}.kpi span{color:#c9d1d9;font-size:13px;font-weight:600}.kpi b{display:block;font-size:22px}
.vazio{color:var(--tx2);font-style:italic}.st-ok{color:var(--vd)}.st-erro{color:var(--vm)}.st-nao_implementada,.st-ausente{color:var(--tx2)}.st-parcial{color:var(--am)}
.mermaid-src{display:none}code{background:var(--bg3);padding:1px 5px;border-radius:4px}
svg text{fill:var(--tx)}"""

JS = r"""
const D=DADOS,P=D.perguntas,T=D.textos,REG=D.registro;
function esc(s){return (s===null||s===undefined?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function aba(n){document.querySelectorAll('.aba').forEach(a=>a.classList.toggle('on',a.id==n));document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.a==n));location.hash=n}
function vazio(msg){return `<div class=card><p class=vazio>${esc(msg)}</p></div>`}
function mostra(cid){const t=T[cid]||{};document.getElementById('trecho').innerHTML=`<h3>${esc(cid)} <span class=m>${esc(t.idioma||'')} · ${esc(t.secao||'')}</span></h3>${t.aviso?`<p class=m><b>Aviso da curadoria:</b> ${esc(t.aviso)}</p>`:''}<pre>${esc(t.texto||'(texto não disponível)')}</pre>`}
function rastro(){const p=P.find(x=>x.id==document.getElementById('q').value);const rel=new Set(p.relevantes),par=new Set(p.parciais);
let h=`<div class=card><h2>${p.id} <span class=tag>${p.tipo}</span> <span class=tag>${esc(p.barreira||'')}</span></h2><p>${esc(p.pergunta)}</p>`;
if(p.parafrase)h+=`<p class=m>Paráfrase leiga: ${esc(p.parafrase)}</p>`;if(p.traducao)h+=`<p class=m>Tradução da busca bilíngue: ${esc(p.traducao)}</p>`;
h+=`<p class=m>Gabarito rascunho: ${rel.size} trechos que respondem (verde), ${par.size} que ajudam em parte (amarelo). Clique num trecho para ler.</p></div>`;
h+=`<div class=card><h2>1. Busca: os 5 primeiros de cada configuração</h2><table><tr><th>configuração</th><th>top-5</th><th>certos</th></tr>`;
for(const b of p.buscas){const ac=b.top5.filter(c=>rel.has(c)).length;h+=`<tr><td><b>${esc(b.config)}</b><br><span class=m>${esc(b.desc)}</span></td><td>`+b.top5.map((c,i)=>`<span class="chip ${rel.has(c)?'R':par.has(c)?'p':''}" title="${esc(c)}" onclick="mostra('${c}')">${i+1} ${esc(c.split('#')[0].slice(0,14))}</span>`).join('')+`</td><td>${ac}/${rel.size}</td></tr>`}
h+=`</table><div id=trecho class=m style="margin-top:8px">Clique num trecho.</div></div><div class=card><h2>2. Respostas (mesmos 5 trechos do sistema atual)</h2><div class=cols>`;
for(const [v,r] of Object.entries(p.respostas)){h+=`<div><h3>Prompt ${v}${r.absteve?' <span class=tag>absteve</span>':''}${r.copia_aviso?' <span class=tag>copia o aviso</span>':''}</h3><pre>${esc(r.texto)}</pre></div>`}
h+=`</div></div><div class=card><h2>3. Juízes da resposta v1, frase a frase</h2><div class=cols>`;
for(const [n,j] of Object.entries(p.juizes)){h+=`<div><h3>${esc(n)} <span class=tag>útil: ${esc(j.util)}</span></h3><table>`+j.frases.map(f=>`<tr><td class="s-${f.sust}"><b>${esc(f.sust)}</b></td><td>${esc(f.frase)}${f.sust!='sim'?`<br><span class=m>${esc(f.motivo)}</span>`:''}</td></tr>`).join('')+`</table></div>`}
document.getElementById('rastro').innerHTML=h+`</div></div>`}
function grafico(rs,k){const W=660,L=220,lin=24,H=rs.length*lin+30,x=v=>L+v*(W-L-30);let h=`<svg width=100% viewBox="0 0 ${W} ${H}" style="max-width:${W}px">`;
for(let t=0;t<=1.0001;t+=0.2){h+=`<line x1=${x(t)} x2=${x(t)} y1=0 y2=${H-20} stroke=#30363d /><text x=${x(t)} y=${H-6} font-size=10 text-anchor=middle>${t.toFixed(1)}</text>`}
rs.forEach((r,i)=>{const m=r.metricas[k],y=i*lin+14;h+=`<text x=${L-6} y=${y+4} font-size=11 text-anchor=end>${esc(r.variante.slice(0,30))}</text><line x1=${x(m.ic[0])} x2=${x(m.ic[1])} y1=${y} y2=${y} stroke=#58a6ff stroke-width=3 /><circle cx=${x(m.v)} cy=${y} r=5 fill=#58a6ff /><text x=${x(m.ic[1])+6} y=${y+4} font-size=10>${m.v.toFixed(2)}</text>`});
return h+`</svg><p class=m>Ponto = média (${esc(k)}); barra = intervalo de confiança de 95%. Barras que se sobrepõem muito não mostram diferença.</p>`}
function qualidade(){const g={};REG.forEach(r=>(g[r.experimento]=g[r.experimento]||[]).push(r));let h='';
if(D.regressao)h+=`<div class=card><h2>Regressão contra a linha de base</h2><pre>${esc(D.regressao)}</pre></div>`;
for(const [e,rs] of Object.entries(g)){const k=Object.keys(rs[0].metricas)[0];h+=`<div class=card><h2>${esc(e)}</h2><p class=m>${esc(rs[0].descricao)} · fonte ${esc(rs[0].fonte)} · commit ${esc(rs[0].commit)} (${esc(rs[0].data)})</p>`;
if(rs.every(r=>r.metricas[k].ic))h+=grafico(rs,k);
h+=`<table><tr><th>variante</th>`+Object.keys(rs[0].metricas).map(m=>`<th>${esc(m)}</th>`).join('')+`<th>n</th></tr>`;
rs.forEach(r=>{h+=`<tr><td><b>${esc(r.variante)}</b>${r.extra?`<br><span class=m>${esc(Object.entries(r.extra).map(([a,b])=>a+': '+b).join(' · '))}</span>`:''}</td>`+Object.values(r.metricas).map(m=>`<td>${m.ic?`${m.v.toFixed(2)} [${m.ic[0].toFixed(2)}–${m.ic[1].toFixed(2)}]`:m.k!==undefined?`${m.k}${m.n!==undefined?'/'+m.n:''}`:m.v}</td>`).join('')+`<td>${r.n}</td></tr>`});
h+=`</table></div>`}document.getElementById('qualidade').innerHTML=h}
function pipeline(){const R=D.pipeline;if(!R){document.getElementById('pipeline').innerHTML=vazio('Ainda sem rastro do pipeline: rode make rastro-pipeline.');return}
let h=`<div class=card><p class=m>Código do grupo no commit ${esc(R.commit_grupo)} · provedor ${esc(R.provedor)} · gerado em ${esc(R.gerado_em)}. Com o provedor determinístico os textos não medem qualidade, só mostram o caminho.</p></div>`;
for(const ex of R.execucoes||[]){h+=`<div class=card><h2>${esc(ex.material_id)} <span class=tag>${esc(ex.run_id)}</span></h2><table><tr><th>#</th><th>etapa</th><th>status</th><th>latência</th><th>entrada → saída</th><th>resumo da saída</th></tr>`;
for(const e of ex.etapas||[])h+=`<tr><td>${e.ordem}</td><td><b>${esc(e.etapa)}</b></td><td class="st-${esc(e.status)}">${esc(e.status)}</td><td>${e.latencia_s!=null?Number(e.latencia_s).toFixed(3)+' s':''}</td><td>${esc(e.tamanho_entrada)} → ${esc(e.tamanho_saida)}</td><td>${esc(e.resumo_saida)}</td></tr>`;
h+=`</table></div>`}document.getElementById('pipeline').innerHTML=h}
function seguranca(){let h='';const A=D.adversarial;
if(A){h+=`<div class=card><h2>Bateria adversarial</h2><pre>${esc(A)}</pre></div>`}else h+=vazio('Ainda sem bateria adversarial: rode make adversarial.');
if(D.ablacao)h+=`<div class=card><h2>Ablação: com e sem cada peça</h2><pre>${esc(D.ablacao)}</pre></div>`;else h+=vazio('Ainda sem ablação: rode make ablacao.');
document.getElementById('seguranca').innerHTML=h}
function confianca(){let h='';if(D.repeticao)h+=`<div class=card><h2>Reprodutibilidade</h2><pre>${esc(D.repeticao)}</pre></div>`;
if(D.custo)h+=`<div class=card><h2>Custo e latência por peça</h2><table><tr><th>peça</th><th>onde</th><th>n</th><th>mediana</th><th>observação</th></tr>`+D.custo.map(c=>`<tr><td><b>${esc(c.peca)}</b></td><td>${esc(c.onde)}</td><td>${c.n}</td><td>${c.mediana_s} s</td><td class=m>${esc(c.extra)}</td></tr>`).join('')+`</table></div>`;
document.getElementById('confianca').innerHTML=h||vazio('Rode make repetir e make custo.')}
function revisao(){const V=D.divergencias;if(!V){document.getElementById('revisao').innerHTML=vazio('Rode make revisao.');return}
let h=`<div class=card><h2>${V.n} frases em que os juízes discordam</h2><p class=m>Fila para conferência humana: a decisão de uma pessoa nessas frases diz qual juiz usar como régua.</p></div>`;
for(const i of V.itens){h+=`<div class=card><p class=m>${esc(i.id)} · ${esc(i.pergunta)}</p><p><b>${esc(i.frase)}</b> <span class=tag>${esc(i.refs.join(' '))}</span></p><table>`+Object.entries(i.votos).map(([n,v])=>`<tr><td style="width:120px">${esc(n)}</td><td class="s-${esc(v.sustentada)}" style="width:70px"><b>${esc(v.sustentada)}</b></td><td class=m>${esc(v.motivo)}</td></tr>`).join('')+`</table></div>`}
document.getElementById('revisao').innerHTML=h}
function mapa(){const M=D.mapa;if(!M){document.getElementById('mapa').innerHTML=vazio('Ainda sem mapa: rode make mapa.');return}
const me=M.metricas||{};let h=`<div class=card><div class=kpis><div class=kpi><span class=m>módulos</span><b>${me.modulos??''}</b></div><div class=kpi><span class=m>funções</span><b>${me.funcoes??''}</b></div><div class=kpi><span class=m>arquivos de teste</span><b>${me.testes??''}</b></div><div class=kpi><span class=m>módulos sem teste</span><b>${me.modulos_sem_teste??''}</b></div></div><p class=m>Código do grupo no commit ${esc(M.commit_grupo)} · análise estática aproximada.</p></div>`;
h+=`<div class=card><h2>Etapas do pipeline</h2><table><tr><th>#</th><th>etapa</th><th>status</th><th>onde</th><th>evidência</th></tr>`+(M.etapas_pipeline||[]).map(e=>`<tr><td>${e.ordem}</td><td><b>${esc(e.etapa)}</b></td><td class="st-${esc(e.status)}">${esc(e.status)}</td><td><code>${esc(e.modulo)}${e.funcao?':'+esc(e.funcao):''}</code></td><td class=m>${esc(e.evidencia)}</td></tr>`).join('')+`</table></div>`;
const mods=[...(M.modulos||[])].sort((a,b)=>(b.importado_por||[]).length-(a.importado_por||[]).length);
h+=`<div class=card><h2>Módulos</h2><p class=m>Ordenados por quantos outros módulos dependem deles. Sem teste em vermelho.</p><table><tr><th>módulo</th><th>linhas</th><th>funções</th><th>usado por</th><th>usa</th><th>LLM</th><th>testes</th></tr>`+mods.map(m=>`<tr><td><code>${esc(m.id)}</code></td><td>${m.linhas}</td><td>${(m.funcoes||[]).length}</td><td>${(m.importado_por||[]).length}</td><td>${(m.importa||[]).length}</td><td>${m.usa_llm?'sim':''}</td><td class="${(m.testado_por||[]).length?'st-ok':'st-erro'}">${(m.testado_por||[]).length}</td></tr>`).join('')+`</table></div>`;
document.getElementById('mapa').innerHTML=h}
document.getElementById('q').innerHTML=P.map(p=>`<option value=${p.id}>${p.id} · ${p.tipo} · ${esc(p.pergunta.slice(0,90))}</option>`).join('');
rastro();qualidade();pipeline();seguranca();confianca();revisao();mapa();
const ini=(location.hash||'').slice(1);if(ini&&document.getElementById(ini))aba(ini);
"""

ABAS = [("rastro-aba", "Rastro do RAG"), ("pipeline-aba", "Pipeline inteiro"), ("qualidade-aba", "Qualidade por versão"),
        ("confianca-aba", "Reprodutibilidade e custo"), ("revisao-aba", "Revisão humana"), ("seguranca-aba", "Segurança e ablação"),
        ("mapa-aba", "Mapa do código"), ("testes-aba", "Comandos")]


def _git_log(repo: Path, ref: str | list[str], n: int, caminho: str | None = None) -> list[dict]:
    """Commits em ordem topológica (mais novo primeiro), com os pais, para desenhar o grafo."""
    refs = [ref] if isinstance(ref, str) else ref
    cmd = ["git", "-C", str(repo), "log", "--topo-order", f"-n{n}", "--format=%H%x1f%P%x1f%an%x1f%aI%x1f%s", *refs]
    if caminho:
        cmd += ["--", caminho]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    linhas = []
    for l in out.splitlines():
        sha, pais, autor, data, titulo = (l.split("\x1f") + [""] * 5)[:5]
        linhas.append({"sha": sha, "pais": pais.split(), "autor": autor, "data": data, "titulo": titulo})
    return linhas


def faixas(commits: list[dict]) -> list[dict]:
    """Atribui uma faixa (coluna) a cada commit, como o `git log --graph`.

    `entrada` = o que cada faixa espera antes da linha; `saida` = depois. O painel liga entrada[i] -> saida[j] quando
    é o mesmo commit esperado (linha que só passa), e o ponto do commit às faixas dos pais (bifurcação/merge)."""
    faixa: list[str | None] = []
    for c in commits:
        entrada = list(faixa)
        col = faixa.index(c["sha"]) if c["sha"] in faixa else (faixa.index(None) if None in faixa else len(faixa))
        if col == len(faixa):
            faixa.append(None)
        faixa = [None if v == c["sha"] else v for v in faixa]     # filhos que esperavam este commit se juntam aqui
        pais = c["pais"]
        for k, p in enumerate(pais):
            if p in faixa:
                continue                      # o pai já tem faixa: a linha vai até ela, sem abrir outra
            if k == 0 and faixa[col] is None:
                faixa[col] = p
            else:
                livre = faixa.index(None) if None in faixa else len(faixa)
                if livre == len(faixa):
                    faixa.append(None)
                faixa[livre] = p
        while faixa and faixa[-1] is None:
            faixa.pop()
        c.update({"col": col, "entrada": [v[:7] if v else None for v in entrada], "saida": [v[:7] if v else None for v in faixa]})
        c["pais"] = [p[:7] for p in pais]
        c["sha"] = c["sha"][:7]
    return commits


def montar_commits(historico: list[dict]) -> dict:
    """Grafo de commits do repositório do grupo (dev + PRs abertos) + o veredito de cada rodada do vigia ligado ao commit que ela verificou."""
    import os
    import importlib.util as _ilu
    _sp = _ilu.spec_from_file_location("onde", AQUI.parent / "bancada" / "onde.py")
    _onde = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_onde)
    grupo = _onde.grupo()
    ref_g = "origin/dev" if subprocess.run(["git", "-C", str(grupo), "rev-parse", "-q", "--verify", "origin/dev"],
                                           capture_output=True).returncode == 0 else "HEAD"
    rodadas = []
    vistos = set()
    for r in historico:
        chave = (r.get("rodada_em"), r.get("commit_grupo"), r.get("commit_privado"))
        if chave in vistos or not r.get("commit_grupo"):
            continue
        vistos.add(chave)
        rodadas.append({k: r.get(k) for k in ("commit_grupo", "commit_privado", "rodada_em", "aprovado", "portoes", "commit_grupo_titulo",
                                              "metricas", "alvo", "pr", "branch")})
    # PRs abertos entram como ramos: a cabeça de cada PR (refs/remotes/origin/pr/N, trazidas pelo vigia com git fetch)
    gh = OUT / "30-github.json"
    prs = json.loads(gh.read_text(encoding="utf-8")).get("prs", []) if gh.exists() else []
    refs, cabecas = [ref_g], {}
    for p in prs:
        ref_pr = f"refs/remotes/origin/pr/{p['numero']}"
        if subprocess.run(["git", "-C", str(grupo), "rev-parse", "-q", "--verify", ref_pr], capture_output=True).returncode == 0:
            refs.append(ref_pr)
            cabecas[p["sha"][:7]] = p["numero"]
    log_g = faixas(_git_log(grupo, refs, 48))
    for c in log_g:
        if c["sha"] in cabecas:
            c["pr"] = cabecas[c["sha"]]
    return {"grupo": log_g, "rodadas": rodadas}     # só o repositório do grupo: commits privados não aparecem


def _sem_itens(d):
    """O 32 tem uma linha por questão (275 KB): o painel só precisa das que falharam."""
    if isinstance(d, dict) and isinstance(d.get("itens"), list):
        d = dict(d, itens=[i for i in d["itens"] if not (i.get("roda_sem_erro") and i.get("trcc_aprovado") and i.get("escopo_gabarito_aprovado"))])
    return d


def etapa_html() -> None:
    import os
    import painel
    if not REGISTRO.exists():
        etapa_registrar()
    registro = [json.loads(l) for l in REGISTRO.read_text(encoding="utf-8").splitlines() if l.strip()]
    perguntas, textos = montar_rastro()
    status = json.loads(os.environ["BANCADA_STATUS"]) if os.environ.get("BANCADA_STATUS") else None
    hist_arq = Path(os.environ.get("BANCADA_HISTORICO", ""))
    historico = ([json.loads(l) for l in hist_arq.read_text(encoding="utf-8").splitlines() if l.strip()]
                 if os.environ.get("BANCADA_HISTORICO") and hist_arq.exists() else [])
    historico = [h for h in historico if not h.get("sabotagem")]     # testes de sabotagem provam o portão; não são veredito
    # uma linha por commit do grupo (dev ou cabeça de PR): rodadas repetidas do mesmo commit, disparadas antes por
    # commits do repositório privado, ficam só com a mais recente
    if status:
        historico = historico + [{k: status.get(k) for k in ("commit_grupo", "commit_grupo_titulo", "commit_privado", "rodada_em", "aprovado",
                                                                "portoes", "metricas", "alvo", "pr", "branch")}]
    ultimo = {}
    for h in historico:
        ultimo[(h.get("alvo") or "dev", h.get("pr"), h.get("commit_grupo"))] = h
    historico = sorted(ultimo.values(), key=lambda h: h.get("rodada_em") or "")
    dados = {"perguntas": perguntas, "textos": textos, "registro": registro, "status": status, "historico": historico,
             "gerado": datetime.now().strftime("%d/%m/%Y %H:%M"),
             "regressao": _opcional("21-regressao.txt", False), "repeticao": _opcional("22-repeticao.txt", False),
             "custo": _opcional("23-custo.json"), "adversarial_casos": jl("24-adversarial.jsonl"),
             "ablacao": _opcional("25-ablacao.txt", False), "pipeline": _opcional("26-rastro-pipeline-resumo.json"),
             "mapa": _opcional("27-mapa-codigo.json"), "divergencias": _opcional("28-divergencias-juizes.json"),
             "q_avaliacao": _sem_itens(_opcional("32-avaliacao.json")), "q_juiz": _opcional("33-juiz-calibracao.json"),
             "q_rag": _opcional("34-rag-triade.json"), "q_ataque": _opcional("35-ataque.json"),
             "q_orcamento": _opcional("36-orcamento.json"), "q_producao": _opcional("37-producao.json"),
             "langgraph": _opcional("39-langgraph.json"),
             "llmxrag": _opcional("40-llm-x-rag.json"), "llmxrag_textos": _opcional("40-llm-x-rag-textos.json"),
             "q_ragas": _opcional("38-ragas-grupo.json"),
             "gitnexus": _opcional("29-gitnexus.json"), "github": _opcional("30-github.json"),
             "etapas": _opcional("31-etapas.json"), "commits": montar_commits(historico)}
    pagina = painel.gerar(dados, TESTES)
    REPORTS.mkdir(exist_ok=True)
    destino = REPORTS / "bancada.html"
    destino.write_text(pagina, encoding="utf-8")
    print(f"{destino.relative_to(AQUI)}: {len(pagina) / 1024:.0f} KB, {len(perguntas)} perguntas, {len(registro)} configurações, "
          f"{len(dados['achados'])} achados ({sum(a['nivel'] == 'grave' for a in dados['achados'])} graves)")


if __name__ == "__main__":
    a = sys.argv[1:] or ["ajuda"]
    if a[0] == "registrar":
        etapa_registrar()
    elif a[0] == "rastro" and len(a) > 1:
        etapa_rastro(a[1])
    elif a[0] == "html":
        etapa_html()
    else:
        print(__doc__)
