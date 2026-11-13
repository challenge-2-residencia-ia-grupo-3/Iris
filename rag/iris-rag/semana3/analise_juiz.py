"""analise_juiz.py: desembaralha os vereditos do juiz e calcula o que o PREREG pede (seções Métricas,
Análise estatística e Regra de decisão).

Escrito em 12/11/2026 ANTES de abrir juiz/chave.json com vereditos em mãos: nenhuma escolha de cálculo
deste arquivo foi feita olhando o resultado do juiz.

Entradas:
  juiz/chave.json                   id_cego -> teste, modelo, config, id_pergunta, repeticoes
  juiz/vereditos/veredito-*.jsonl   uma linha por id_cego (formato de juiz/INSTRUCOES-JUIZ.md)
  saidas/metricas.json              métricas sem juiz (portões da regra de decisão; H3 do D)
  saidas/respostas_D_*.jsonl        só para saber quais saídas do D caíram na reserva
Saídas:
  saidas/juiz_por_resposta.jsonl    uma linha por (condição, pergunta, repetição), sem texto
  saidas/juiz_metricas.json e saidas/juiz_metricas.txt

Escolhas de cálculo (todas do PREREG, salvo as duas marcadas como complemento):
  - Fidelidade por frase = frases sustentadas / frases da resposta. Frase que só diz "não sei" conta
    como sustentada (INSTRUCOES-JUIZ.md). B não tem fidelidade (a resposta é o próprio trecho).
  - Por pergunta: média das 3 repetições; depois média entre perguntas (cada pergunta pesa igual).
  - Diferença pareada por pergunta, IC 95% por bootstrap (2.000, semente 20261112), IC agrupado por
    documento dominante e Wilcoxon. "Diferença" só quando o IC exclui o zero.
  - Útil: conta "sim". "parcial" NÃO conta como útil e é contado à parte (complemento 1: o PREREG
    não diz como pontuar "parcial"; a leitura conservadora é a mesma das instruções do juiz).
  - Complemento 2 (não entra na regra de decisão): fidelidade só nas respostas em que o sistema
    respondeu, isto é, sem as abstenções, porque uma abstenção vale fidelidade 1 por construção.
Uso: python semana3/analise_juiz.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

import comum as C
import metricas as M

VEREDITOS = C.JUIZ / "vereditos"
CATEGORIAS = ("factual", "sintese", "fora_da_base")


def sim(v) -> float | None:
    return None if v is None else float(v == "sim")


def carregar() -> tuple[dict, dict, list[str]]:
    chave = json.loads((C.JUIZ / "chave.json").read_text(encoding="utf-8"))["chave"]
    ver: dict[str, dict] = {}
    avisos: list[str] = []
    for arq in sorted(VEREDITOS.glob("veredito-*.jsonl")):
        for l in C.ler_jsonl(arq):
            if l["id_cego"] in ver:
                avisos.append(f"id_cego repetido em mais de um arquivo: {l['id_cego']} ({arq.name})")
            ver[l["id_cego"]] = l | {"_arquivo": arq.name}
    return chave, ver, avisos


def expandir(chave: dict, ver: dict) -> tuple[list[dict], list[dict], dict]:
    """Uma linha por (condição, pergunta, repetição): o veredito de um item vale para todas as suas repetições."""
    resp, adapt = [], []
    cont = Counter()
    for idc, k in sorted(chave.items()):
        v = ver.get(idc)
        cond = f"{k['teste']}|{k['modelo']}" + (f"|{k['config']}" if k.get("config") else "")
        if v is None:
            cont[f"sem_veredito|{cond}"] += 1
            continue
        if v.get("erro"):
            cont[f"erro_do_juiz|{cond}"] += 1
            continue
        for rep in k.get("repeticoes") or [k["repeticao"]]:
            base = {"id_cego": idc, "condicao": cond, "teste": k["teste"], "modelo": k["modelo"],
                    "config": k.get("config"), "id": k["id_pergunta"], "repeticao": rep}
            if k["teste"] == "D":
                adapt.append(base | {c: v.get(c) for c in ("util", "entrega_resposta", "mudou_o_que_avalia",
                                                           "inventou", "nivel_respeitado")})
            else:
                fr = v.get("frases")
                n = len(fr) if fr else 0
                sust = sum(1 for f in fr if f["sustentada"] == "sim") if fr else 0
                contr = sum(1 for f in fr if f.get("contradiz") == "sim") if fr else 0
                resp.append(base | {"n_frases": n, "frases_sustentadas": sust, "frases_que_contradizem": contr,
                                    "fidelidade": round(sust / n, 4) if n else None,
                                    "util": v.get("util"), "inventou": v.get("inventou"),
                                    "absteve_juiz": v.get("absteve")})
            cont[f"julgada|{cond}"] += 1
    return resp, adapt, dict(sorted(cont.items()))


CAMPOS_RESP = {
    "fidelidade": lambda m: m["fidelidade"],
    "fidelidade_sem_abstencao": lambda m: None if m["absteve_juiz"] == "sim" else m["fidelidade"],
    "util_sim": lambda m: sim(m["util"]),
    "util_sim_ou_parcial": lambda m: float(m["util"] in ("sim", "parcial")),
    "inventou": lambda m: sim(m["inventou"]),
    "absteve_juiz": lambda m: sim(m["absteve_juiz"]),
    "tem_frase_que_contradiz": lambda m: None if not m["n_frases"] else float(m["frases_que_contradizem"] > 0),
}


def por_condicao(ms: list[dict], categoria: dict[str, str], grupo: dict[str, str]) -> dict:
    out = {"respostas": len(ms), "perguntas": len({m["id"] for m in ms}),
           "repeticoes": sorted({m["repeticao"] for m in ms}),
           "frases_julgadas": sum(m["n_frases"] for m in ms),
           "frases_sustentadas": sum(m["frases_sustentadas"] for m in ms),
           "frases_que_contradizem": sum(m["frases_que_contradizem"] for m in ms),
           "util_contagem": dict(Counter(m["util"] for m in ms))}
    for nome, f in CAMPOS_RESP.items():
        pq = M.media_por_pergunta(ms, f)
        out[nome] = {"n_perguntas": len(pq), "media_ic95": M.ic_media(list(pq.values())),
                     "ic95_agrupado_por_documento": M.ic_agrupado(pq, grupo)}
        out[nome]["por_categoria"] = {
            cat: {"n_perguntas": len(v), "media_ic95": M.ic_media(v)}
            for cat in CATEGORIAS if (v := [x for k, x in pq.items() if categoria.get(k) == cat])}
    return out


def comparar(a: list[dict], b: list[dict], campos: list[str], categoria: dict[str, str],
             grupo: dict[str, str]) -> dict:
    """b - a, pareado por pergunta (média das repetições), geral e por categoria."""
    out = {}
    for nome in campos:
        pa, pb = M.media_por_pergunta(a, CAMPOS_RESP[nome]), M.media_por_pergunta(b, CAMPOS_RESP[nome])
        r = M.pareado(pa, pb, grupo)
        comuns = sorted(set(pa) & set(pb))
        r["perguntas_melhoraram"] = sum(pb[k] > pa[k] + 1e-12 for k in comuns)
        r["perguntas_pioraram"] = sum(pb[k] < pa[k] - 1e-12 for k in comuns)
        r["por_categoria"] = {}
        for cat in CATEGORIAS:
            ks = [k for k in comuns if categoria.get(k) == cat]
            if ks:
                d = [pb[k] - pa[k] for k in ks]
                r["por_categoria"][cat] = {"n": len(ks), "dif_media_ic95": M.ic_media(d), "wilcoxon_p": M.wilcoxon(d)}
        out[nome] = r
    return out


def ic_exclui_zero(ic) -> bool:
    return bool(ic) and (ic[1] > 0 or ic[2] < 0)


def decidir(modelo: str, conds: dict, pares: dict, sem_juiz: dict) -> dict:
    """Regra de decisão do Estrategista (PREREG), aplicada a um modelo."""
    cand = {}
    for t in ("A", "C"):
        m = sem_juiz.get("A_C", {}).get(f"{t}|{modelo}")
        if not m or f"{t}|{modelo}" not in conds:
            continue
        cand[t] = {"portao_a_abstencao_q39_q40": m["abstencao_correta_q39_q40"],
                   "portao_a_passa": bool(m["abstencao_correta_todas"]) and m["repeticoes_completas"] == [1, 2, 3],
                   "portao_b_latencia_p95_s": m["latencia_p95_s"], "portao_b_passa": bool(m["latencia_p95_dentro_rnf07"]),
                   "fidelidade": conds[f"{t}|{modelo}"]["fidelidade"]["media_ic95"]}
        cand[t]["concorre"] = cand[t]["portao_a_passa"] and cand[t]["portao_b_passa"]
    cand["B"] = {"portao_a_passa": False, "concorre": False,
                 "motivo": "B sempre devolve trechos: não tem como se abster (PREREG); entra como referência de utilidade"}
    concorrem = [t for t in ("A", "C") if cand.get(t, {}).get("concorre")]
    out = {"candidatas": cand, "concorrem": concorrem}
    if not concorrem:
        out["vencedor"] = None
        out["motivo"] = "nenhuma condição passou nos dois portões"
    elif len(concorrem) == 1:
        out["vencedor"] = concorrem[0]
        out["motivo"] = "única condição que passou nos portões"
    else:
        d = pares[f"C - A|{modelo}"]["fidelidade"]["dif_media_ic95"]
        if ic_exclui_zero(d):
            out["vencedor"] = "C" if d[0] > 0 else "A"
            out["motivo"] = f"maior fidelidade por frase; diferença C - A = {d}"
        else:
            out["vencedor"] = "A"
            out["motivo"] = f"empate na fidelidade (IC da diferença C - A passa pelo zero: {d}); vence a mais simples (ordem B, A, C)"
    return out


def analisar_d(adapt: list[dict]) -> dict:
    campos = ("util_sim", "entrega_resposta", "mudou_o_que_avalia", "inventou", "nivel_respeitado")
    val = {"util_sim": lambda m: sim(m["util"])} | {c: (lambda m, c=c: sim(m[c])) for c in campos[1:]}
    out = {}
    for modelo in sorted({m["modelo"] for m in adapt}):
        reserva = {(l["config"], l["id"], l["repeticao"]): bool(l.get("reserva"))
                   for l in C.ler_jsonl(C.SAIDAS / f"respostas_D_{modelo}.jsonl") if not l.get("erro")}
        ms = [m | {"reserva": reserva.get((m["config"], m["id"], m["repeticao"]))} for m in adapt if m["modelo"] == modelo]
        r: dict = {"saidas_julgadas": len(ms), "por_config": {}, "por_config_e_reserva": {}}
        for cfg in ("completo", "sem_rag"):
            sel = [m for m in ms if m["config"] == cfg]
            r["por_config"][cfg] = {"saidas": len(sel), "reserva": sum(bool(m["reserva"]) for m in sel),
                                    "util_contagem": dict(Counter(m["util"] for m in sel))} | {
                c: M.ic_media(list(M.media_por_pergunta(sel, val[c]).values())) for c in campos}
            for res in (True, False):
                s2 = [m for m in sel if bool(m["reserva"]) == res]
                r["por_config_e_reserva"][f"{cfg}|{'reserva' if res else 'adaptador_passou'}"] = {
                    "saidas": len(s2), "questoes": len({m["id"] for m in s2})} | {
                    c: (round(sum(val[c](m) for m in s2) / len(s2), 4) if s2 else None) for c in campos}
        # completo - sem_rag em todas as questões (média das rodadas)
        r["pareado_completo_menos_sem_rag_todas"] = {}
        for c in campos:
            a = M.media_por_pergunta([m for m in ms if m["config"] == "sem_rag"], val[c])
            b = M.media_por_pergunta([m for m in ms if m["config"] == "completo"], val[c])
            p = M.pareado(a, b, {})
            p.pop("dif_ic95_agrupado_por_documento", None)
            r["pareado_completo_menos_sem_rag_todas"][c] = p
        # só onde o Adaptador passou nas duas configurações, na mesma questão e rodada
        pares = defaultdict(dict)
        for m in ms:
            if m["reserva"] is False:
                pares[(m["id"], m["repeticao"])][m["config"]] = m
        ambos = {k: v for k, v in pares.items() if len(v) == 2}
        r["adaptador_passou_nas_duas"] = {
            "pares_questao_rodada": len(ambos), "questoes": sorted({k[0] for k in ambos}),
            "por_rodada": dict(sorted(Counter(k[1] for k in ambos).items())),
            "completo": {c: (round(sum(val[c](v["completo"]) for v in ambos.values()) / len(ambos), 4) if ambos else None) for c in campos},
            "sem_rag": {c: (round(sum(val[c](v["sem_rag"]) for v in ambos.values()) / len(ambos), 4) if ambos else None) for c in campos},
            "aviso": "poucas questões: não sustenta conclusão"}
        out[modelo] = r
    return out


def fmt(ic) -> str:
    return "n/d" if not ic else f"{ic[0]:.3f} [{ic[1]:.3f}, {ic[2]:.3f}]"


def texto(res: dict) -> str:
    L = ["SEMANA 3 - MÉTRICAS DO JUIZ (Claude Opus; juiz NÃO validado por pessoa)",
         f"gerado em {res['gerado_em']} | commit {res['commit']}", "",
         "Cobertura do julgamento (respostas por condição, já expandidas pelas repetições):"]
    L += [f"  {k}: {v}" for k, v in res["cobertura"].items()]
    L += [f"  AVISO: {a}" for a in res["avisos"]]
    L += ["", "Respostas ao professor, por condição; [média entre perguntas, IC95 inferior, superior]:"]
    for cond, c in res["condicoes"].items():
        L.append(f"  {cond}  respostas={c['respostas']} perguntas={c['perguntas']} frases={c['frases_sustentadas']}/{c['frases_julgadas']} "
                 f"contradizem={c['frases_que_contradizem']} útil={c['util_contagem']}")
        for nome in CAMPOS_RESP:
            L.append(f"      {nome:26s} {fmt(c[nome]['media_ic95'])}  n={c[nome]['n_perguntas']}  por documento {fmt(c[nome]['ic95_agrupado_por_documento'])}")
            for cat, v in c[nome]["por_categoria"].items():
                L.append(f"          {cat:14s} {fmt(v['media_ic95'])}  n={v['n_perguntas']}")
    L += ["", "Diferenças pareadas por pergunta (segundo - primeiro):"]
    for par, campos in res["pareados"].items():
        L.append(f"  {par}")
        for nome, r in campos.items():
            L.append(f"      {nome:26s} n={r['n']} dif={fmt(r['dif_media_ic95'])} por documento {fmt(r['dif_ic95_agrupado_por_documento'])} "
                     f"Wilcoxon p={r['wilcoxon_p']} melhoraram={r['perguntas_melhoraram']} pioraram={r['perguntas_pioraram']}")
            for cat, v in r["por_categoria"].items():
                L.append(f"          {cat:14s} n={v['n']} dif={fmt(v['dif_media_ic95'])} p={v['wilcoxon_p']}")
    L += ["", "Regra de decisão do Estrategista (PREREG):"]
    for modelo, d in res["decisao"].items():
        L.append(f"  {modelo}: vencedor = {d['vencedor']} ({d['motivo']})")
        for t, c in d["candidatas"].items():
            L.append(f"      {t}: {json.dumps(c, ensure_ascii=False)}")
    L += ["", "Hipóteses:"] + [f"  {h}: {v}" for h, v in res["hipoteses"].items()]
    L += ["", "D (adaptações), pelo juiz:"]
    for modelo, d in res["D"].items():
        L.append(f"  {modelo}: {d['saidas_julgadas']} saídas julgadas")
        for cfg, v in d["por_config"].items():
            L.append(f"      {cfg}: {json.dumps(v, ensure_ascii=False)}")
        for k, v in d["por_config_e_reserva"].items():
            L.append(f"      {k}: {json.dumps(v, ensure_ascii=False)}")
        for c, v in d["pareado_completo_menos_sem_rag_todas"].items():
            L.append(f"      completo - sem_rag {c:22s} n={v['n']} dif={fmt(v['dif_media_ic95'])} p={v['wilcoxon_p']}")
        L.append(f"      adaptador passou nas duas: {json.dumps(d['adaptador_passou_nas_duas'], ensure_ascii=False)}")
    return "\n".join(L) + "\n"


def main() -> None:
    sys.dont_write_bytecode = True
    chave, ver, avisos = carregar()
    resp, adapt, cobertura = expandir(chave, ver)
    gab = {it["id"]: it for it in C.itens_gabarito()}
    categoria = {k: v["categoria"] for k, v in gab.items()}
    grupo = {k: v["doc_dominante"] for k, v in gab.items()}
    sem_juiz = json.loads((C.SAIDAS / "metricas.json").read_text(encoding="utf-8"))

    por_cond: dict[str, list[dict]] = defaultdict(list)
    for m in resp:
        por_cond[m["condicao"]].append(m)
    conds = {c: por_condicao(ms, categoria, grupo) for c, ms in sorted(por_cond.items())}

    campos_ac = ["fidelidade", "fidelidade_sem_abstencao", "util_sim", "util_sim_ou_parcial", "inventou",
                 "absteve_juiz", "tem_frase_que_contradiz"]
    campos_b = ["util_sim", "util_sim_ou_parcial", "inventou"]
    pareados, decisao = {}, {}
    modelos = sorted({m["modelo"] for m in resp if m["teste"] in ("A", "C")})
    for mod in modelos:
        a, c = por_cond.get(f"A|{mod}", []), por_cond.get(f"C|{mod}", [])
        if a and c:
            pareados[f"C - A|{mod}"] = comparar(a, c, campos_ac, categoria, grupo)
        for var in ("busca-top1", "busca-top3"):
            b = por_cond.get(f"B|{var}", [])
            if b and c:
                pareados[f"C|{mod} - B|{var}"] = comparar(b, c, campos_b, categoria, grupo)
            if b and a:
                pareados[f"A|{mod} - B|{var}"] = comparar(b, a, campos_b, categoria, grupo)
        decisao[mod] = decidir(mod, conds, pareados, sem_juiz)

    d = analisar_d(adapt)
    hip = {}
    prod = "llama3.1-8b"
    if f"C - A|{prod}" in pareados:
        h1 = pareados[f"C - A|{prod}"]["fidelidade"]["dif_media_ic95"]
        hip["H1 (C mais sustentada que A)"] = (
            f"dif C - A na fidelidade = {h1}: " + ("confirmada" if ic_exclui_zero(h1) and h1[0] > 0 else
                                                  "contrariada" if ic_exclui_zero(h1) else "sem diferença (IC passa pelo zero)"))
    for var in ("busca-top1", "busca-top3"):
        k = f"C|{prod} - B|{var}"
        if k in pareados:
            h2 = pareados[k]["util_sim"]["dif_media_ic95"]
            hip[f"H2 (B menos útil que C), {var}"] = (
                f"dif C - B em útil = {h2}: " + ("confirmada" if ic_exclui_zero(h2) and h2[0] > 0 else
                                                "contrariada" if ic_exclui_zero(h2) else "sem diferença (IC passa pelo zero)"))
    dsj = sem_juiz.get("D", {}).get(prod, {}).get("pareado_completo_menos_sem_rag", {})
    if dsj:
        lim = {"trcc": -0.05, "cmd_conjugado_resolvido": -0.05, "flesch_depois": -5.0}
        ok = {k: (dsj[k]["dif_media_ic95"][1] > v) for k, v in lim.items() if k in dsj}
        hip["H3 (RAG não piora o Adaptador), métricas do grupo"] = (
            f"limite inferior do IC de completo - sem_rag acima do limiar? {ok}: " + ("confirmada" if all(ok.values()) else "não confirmada"))
        if prod in d:
            er = d[prod]["pareado_completo_menos_sem_rag_todas"]["entrega_resposta"]["dif_media_ic95"]
            hip["H3, juiz: 'entrega a resposta' em completo - sem_rag"] = (
                f"{er}: " + ("o juiz aponta MAIS entrega no completo" if ic_exclui_zero(er) and er[0] > 0 else
                             "o juiz não aponta mais entrega no completo"))
    if len(decisao) > 1:
        v = {m: x["vencedor"] for m, x in decisao.items()}
        hip["H4 (modelo maior não muda a decisão)"] = f"vencedores por modelo: {v}: " + (
            "confirmada" if len(set(v.values())) == 1 else "não confirmada (a decisão continua com o Llama)")
    else:
        hip["H4 (modelo maior não muda a decisão)"] = "não medido nesta entrega (só um modelo julgado)"

    res = {"gerado_em": C.agora_iso(), "commit": C.commit_atual(), "juiz": "Claude Opus (assinatura), não validado por pessoa",
           "cobertura": cobertura, "avisos": avisos, "condicoes": conds, "pareados": pareados, "decisao": decisao,
           "hipoteses": hip, "D": d}
    C.escrever_jsonl(C.SAIDAS / "juiz_por_resposta.jsonl", resp + adapt)
    C.escrever_json(C.SAIDAS / "juiz_metricas.json", res)
    (C.SAIDAS / "juiz_metricas.txt").write_text(texto(res), encoding="utf-8")
    print(texto(res))


if __name__ == "__main__":
    main()
