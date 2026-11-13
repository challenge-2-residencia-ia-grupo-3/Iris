"""metricas.py: checagem de integridade e métricas determinísticas (sem juiz) de A, B, C e D.

Lê saidas/respostas_*.jsonl e grava:
  saidas/integridade.json      vazias, erros de API, duplicatas e faltantes por arquivo (antes de pontuar)
  saidas/metricas_por_resposta.jsonl   uma linha por resposta de A e C com as métricas
  saidas/metricas.json e saidas/metricas.txt   agregados, comparações pareadas e estabilidade

Não usa nada do juiz: fidelidade por frase e utilidade só existem depois do julgamento.
Uso: python3 semana3/metricas.py
"""
from __future__ import annotations

import math
import random
import re
import sys
from collections import defaultdict

import comum as C

C.adicionar_pacote_ao_path()
FRASE_SEM_RESPOSTA = "Não encontrei nos documentos da base informação suficiente para responder."
LIMITE_RNF07_S = 40.0
N_BOOT = 2000


# ---------------------------------------------------------------- estatística
def ic_media(v: list[float]) -> list[float] | None:
    v = [x for x in v if x is not None]
    if not v:
        return None
    rng = random.Random(C.SEMENTE)
    bs = sorted(sum(rng.choice(v) for _ in v) / len(v) for _ in range(N_BOOT))
    return [round(sum(v) / len(v), 4), round(bs[int(0.025 * N_BOOT)], 4), round(bs[int(0.975 * N_BOOT) - 1], 4)]


def ic_agrupado(valores: dict[str, float], grupo: dict[str, str]) -> list[float] | None:
    """Bootstrap que sorteia grupos (documento dominante), não perguntas."""
    por_g: dict[str, list[float]] = defaultdict(list)
    for k, v in valores.items():
        if v is not None:
            por_g[grupo.get(k) or "sem_doc"].append(v)
    gs = list(por_g)
    if not gs:
        return None
    rng = random.Random(C.SEMENTE)
    tudo = [x for g in gs for x in por_g[g]]
    bs = []
    for _ in range(N_BOOT):
        amostra = [x for g in (rng.choice(gs) for _ in gs) for x in por_g[g]]
        bs.append(sum(amostra) / len(amostra))
    bs.sort()
    return [round(sum(tudo) / len(tudo), 4), round(bs[int(0.025 * N_BOOT)], 4), round(bs[int(0.975 * N_BOOT) - 1], 4)]


def wilcoxon(dif: list[float]) -> float | None:
    try:
        from scipy.stats import wilcoxon as w
        if not any(abs(d) > 1e-12 for d in dif):
            return 1.0
        return round(float(w(dif).pvalue), 4)
    except Exception:  # noqa: BLE001 - scipy ausente: só o IC
        return None


def p95(v: list[float]) -> float | None:
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    return round(v[min(len(v) - 1, math.ceil(0.95 * len(v)) - 1)], 2)


# ---------------------------------------------------------------- integridade
def integridade(arquivos: dict[str, list[dict]], esperado: dict[str, int]) -> dict:
    out = {}
    for nome, linhas in arquivos.items():
        chaves = [(l.get("config", l.get("variante", "")), l["id"], l.get("repeticao", 1)) for l in linhas]
        cont = defaultdict(int)
        for k in chaves:
            cont[k] += 1
        ok = [l for l in linhas if not l.get("erro")]
        texto = lambda l: l.get("resposta") if "resposta" in l else l.get("adaptado")  # noqa: E731
        out[nome] = {
            "linhas": len(linhas),
            "esperado": esperado.get(nome),
            "erros_api": sum(1 for l in linhas if l.get("erro")),
            "vazias": sum(1 for l in ok if not (texto(l) or "").strip()),
            "duplicatas": sum(n - 1 for n in cont.values() if n > 1),
            "validas_unicas": len({k for k, l in zip(chaves, linhas) if not l.get("erro") and (texto(l) or "").strip()}),
            "cortadas_por_limite_de_tokens": sum(1 for l in ok if l.get("fim") == "length"),
        }
        if esperado.get(nome):
            out[nome]["faltantes"] = esperado[nome] - out[nome]["validas_unicas"]
    return out


def ultima_valida(linhas: list[dict], chave) -> dict:
    """Se houver erro seguido de acerto, fica a linha válida mais recente."""
    out = {}
    for l in linhas:
        if l.get("erro"):
            continue
        out[chave(l)] = l
    return out


# ---------------------------------------------------------------- métricas A e C
def por_resposta(l: dict, trechos5: list[dict]) -> dict:
    import gerar
    txt = l["resposta"] or ""
    fr = C.frases(txt)
    if l["teste"] == "A":
        absteve = C.FRASE_NAO_SEI.lower()[:30] in txt.lower()
        conf = {"frases_com_citacao": None, "pct_frases_com_citacao": None, "citacoes_invalidas": None,
                "citacao_existente": None, "citou_trecho_com_aviso": None,
                "menciona_fonte": bool(re.search(r"\b(19|20)\d{2}\b|\bet al\b|\bLei\b|\bResolução\b|\bDecreto\b", txt))}
    else:
        c = gerar.conferir(txt, trechos5)
        absteve = c["absteve"]
        com = [f for f in fr if re.search(r"\[T\d+\]", f)]
        conf = {"frases_com_citacao": len(com),
                "pct_frases_com_citacao": None if absteve or not fr else round(len(com) / len(fr), 4),
                "citacoes_invalidas": c["citacoes_invalidas"], "citacao_existente": not c["citacoes_invalidas"],
                "citou_trecho_com_aviso": c["citou_trecho_com_aviso"], "menciona_fonte": None}
    lat = (l.get("segundos_geracao") or 0) + (l.get("segundos_busca") or 0)
    return {"teste": l["teste"], "modelo": l["modelo"], "id": l["id"], "repeticao": l["repeticao"],
            "categoria": l["categoria"], "doc_dominante": l["doc_dominante"], "absteve": absteve,
            "frases": len(fr), "caracteres": len(txt), "palavras": len(txt.split()), **conf,
            "latencia_s": round(lat, 2), "segundos_espera_limite": l.get("segundos_espera_limite"),
            "tokens_entrada": l.get("tokens_entrada"), "tokens_saida": l.get("tokens_saida"),
            "custo_usd": l.get("custo_usd"), "sha16_resposta": C.sha16(txt)}


def agregar_ac(ms: list[dict]) -> dict:
    sem = [m for m in ms if m["categoria"] == "fora_da_base"]
    com = [m for m in ms if m["categoria"] != "fora_da_base"]
    reps = sorted({m["repeticao"] for m in ms})
    resp = [m for m in ms if not m["absteve"]]
    return {
        "respostas": len(ms), "repeticoes": reps,
        "abstencao_correta_q39_q40": f"{sum(m['absteve'] for m in sem)}/{len(sem)}",
        "abstencao_correta_todas": bool(sem) and all(m["absteve"] for m in sem),
        "cobertura_38": round(sum(not m["absteve"] for m in com) / len(com), 4) if com else None,
        "abstencoes_indevidas_nas_38": sum(m["absteve"] for m in com),
        "pct_frases_com_citacao_media": _media([m["pct_frases_com_citacao"] for m in resp]),
        "respostas_com_citacao_invalida": sum(1 for m in ms if m["citacoes_invalidas"]),
        "respostas_que_citam_trecho_com_aviso": sum(1 for m in ms if m["citou_trecho_com_aviso"]),
        "respostas_que_mencionam_ano_lei_ou_autor": sum(1 for m in ms if m["menciona_fonte"]),
        "frases_media": _media([m["frases"] for m in resp]),
        "palavras_media": _media([m["palavras"] for m in resp]),
        "latencia_mediana_s": _mediana([m["latencia_s"] for m in ms]),
        "latencia_p95_s": p95([m["latencia_s"] for m in ms]),
        "latencia_p95_dentro_rnf07": (p95([m["latencia_s"] for m in ms]) or 0) <= LIMITE_RNF07_S,
        "tokens_entrada_media": _media([m["tokens_entrada"] for m in ms]),
        "tokens_saida_media": _media([m["tokens_saida"] for m in ms]),
        "custo_usd_total": round(sum(m["custo_usd"] or 0 for m in ms), 4),
        "custo_usd_por_mil_respostas": round(1000 * sum(m["custo_usd"] or 0 for m in ms) / len(ms), 2) if ms else None,
    }


def estabilidade(ms: list[dict]) -> dict:
    por_id: dict[str, list[dict]] = defaultdict(list)
    for m in ms:
        por_id[m["id"]].append(m)
    completos = {k: v for k, v in por_id.items() if len(v) >= 2}
    if not completos:
        return {"perguntas_com_2_ou_mais_repeticoes": 0}
    return {"perguntas_com_2_ou_mais_repeticoes": len(completos),
            "texto_identico_em_todas": sum(len({m["sha16_resposta"] for m in v}) == 1 for v in completos.values()),
            "abstencao_igual_em_todas": sum(len({m["absteve"] for m in v}) == 1 for v in completos.values()),
            "perguntas_com_abstencao_instavel": sorted(k for k, v in completos.items()
                                                       if len({m["absteve"] for m in v}) > 1)}


def _media(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 4) if v else None


def _mediana(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return round(v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2, 2)


def media_por_pergunta(ms: list[dict], campo) -> dict[str, float]:
    """Média das repetições por pergunta (cada pergunta pesa igual)."""
    acc: dict[str, list[float]] = defaultdict(list)
    for m in ms:
        v = campo(m)
        if v is not None:
            acc[m["id"]].append(float(v))
    return {k: sum(v) / len(v) for k, v in acc.items()}


def pareado(a: dict[str, float], b: dict[str, float], grupo: dict[str, str]) -> dict:
    comuns = sorted(set(a) & set(b))
    dif = {k: b[k] - a[k] for k in comuns}
    return {"n": len(comuns), "dif_media_ic95": ic_media(list(dif.values())),
            "dif_ic95_agrupado_por_documento": ic_agrupado(dif, grupo),
            "wilcoxon_p": wilcoxon(list(dif.values())) if comuns else None}


# ---------------------------------------------------------------- D
def agregar_d(ls: list[dict]) -> dict:
    ok = [l for l in ls if not l.get("erro") and l.get("adaptado")]
    resolv = [l for l in ok if (l["cmd_conjugados_antes"] or 0) > 0]
    return {
        "saidas_validas": len(ok), "erros": sum(1 for l in ls if l.get("erro")),
        "trcc_media": _media([l["trcc"] for l in ok]),
        "pct_trcc_ge_095": _media([float(l["trcc"] >= 0.95) for l in ok if l["trcc"] is not None]),
        "flesch_antes_media": _media([l["flesch_antes"] for l in ok]),
        "flesch_depois_media": _media([l["flesch_depois"] for l in ok]),
        "questoes_com_cmd_conjugado_antes": len(resolv),
        "pct_cmd_conjugado_resolvido": _media([float((l["cmd_conjugados_depois"] or 0) == 0) for l in resolv]),
        "cmd_conjugados_depois_media": _media([l["cmd_conjugados_depois"] for l in ok]),
        "pct_aderencia_nivel": _media([float(bool(l["aderencia_nivel"])) for l in ok]),
        "pct_alterou_texto": _media([float(bool(l["alterou_texto"])) for l in ok]),
        "pct_escopo_aprovado": _media([float(bool(l["escopo_aprovado"])) for l in ok]),
        "pct_reserva": _media([float(bool(l["reserva"])) for l in ok]),
        "tokens_media": _media([l["tokens"] for l in ok]),
        "ciclo_ms_mediana": _mediana([l["ciclo_ms"] for l in ok]),
        "ciclo_s_p95": p95([(l["ciclo_ms"] or 0) / 1000 for l in ok]),
        "pct_dentro_rnf07": _media([float(bool(l["dentro_rnf07"])) for l in ok]),
        "latencia_s_mediana": _mediana([l["latencia_s"] for l in ok]),
    }


def pareado_d(ls: list[dict]) -> dict:
    """completo - sem_rag, por questão (média das rodadas)."""
    ok = [l for l in ls if not l.get("erro") and l.get("adaptado")]
    metr = {"trcc": lambda l: l["trcc"], "flesch_depois": lambda l: l["flesch_depois"],
            "cmd_conjugado_resolvido": lambda l: None if not l["cmd_conjugados_antes"] else float(l["cmd_conjugados_depois"] == 0),
            "aderencia_nivel": lambda l: float(bool(l["aderencia_nivel"]))}
    out = {}
    for nome, f in metr.items():
        a = media_por_pergunta([l for l in ok if l["config"] == "sem_rag"], f)
        b = media_por_pergunta([l for l in ok if l["config"] == "completo"], f)
        out[nome] = pareado(a, b, {})
        out[nome].pop("dif_ic95_agrupado_por_documento")
    return out


# ---------------------------------------------------------------- principal
def main() -> None:
    busca = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    itens = {it["id"]: it for it in C.itens_gabarito()}
    grupo_doc = {k: v["doc_dominante"] for k, v in itens.items()}
    arquivos = {p.name: C.ler_jsonl(p) for p in sorted(C.SAIDAS.glob("respostas_*.jsonl"))}
    esperado = {}
    for nome in arquivos:
        if nome.startswith(("respostas_A_", "respostas_C_")):
            esperado[nome] = 40 * C.REPETICOES
        elif nome == "respostas_B.jsonl":
            esperado[nome] = 80
        elif nome.startswith("respostas_D_"):
            esperado[nome] = 60 * max([l.get("repeticao", 1) for l in arquivos[nome]] or [1])
    integ = integridade(arquivos, esperado)
    integ["_gerado_em"] = C.agora_iso()
    C.escrever_json(C.SAIDAS / "integridade.json", integ)

    res: dict = {"gerado_em": C.agora_iso(), "commit": C.commit_atual(), "integridade": integ, "A_C": {}, "B": {},
                 "D": {}, "pareado_A_C": {}}
    por_resp = []
    ms_por: dict[tuple[str, str], list[dict]] = {}
    for nome, linhas in arquivos.items():
        m = re.match(r"respostas_([AC])_(.+)\.jsonl", nome)
        if not m:
            continue
        validas = ultima_valida(linhas, lambda l: (l["id"], l["repeticao"])).values()
        ms = [por_resposta(l, busca[l["id"]]["trechos_top5"]) for l in validas]
        por_resp += ms
        ms_por[(m.group(1), m.group(2))] = ms
        # só repetições completas (40 perguntas) entram no agregado principal
        reps_ok = [r for r in sorted({x["repeticao"] for x in ms}) if sum(x["repeticao"] == r for x in ms) == 40]
        msc = [x for x in ms if x["repeticao"] in reps_ok]
        res["A_C"][f"{m.group(1)}|{m.group(2)}"] = {
            "repeticoes_completas": reps_ok, **agregar_ac(msc), "estabilidade": estabilidade(msc),
            "por_categoria": {cat: agregar_ac([x for x in msc if x["categoria"] == cat])
                              for cat in ("factual", "sintese", "fora_da_base") if any(x["categoria"] == cat for x in msc)}}
    C.escrever_jsonl(C.SAIDAS / "metricas_por_resposta.jsonl", por_resp)

    # pareado A x C (mesmo modelo), métricas determinísticas por pergunta
    for modelo in sorted({k[1] for k in ms_por}):
        a, c = ms_por.get(("A", modelo)), ms_por.get(("C", modelo))
        if not a or not c:
            continue
        res["pareado_A_C"][modelo] = {
            "absteve (C - A)": pareado(media_por_pergunta(a, lambda m: float(m["absteve"])),
                                       media_por_pergunta(c, lambda m: float(m["absteve"])), grupo_doc),
            "palavras (C - A)": pareado(media_por_pergunta(a, lambda m: m["palavras"]),
                                        media_por_pergunta(c, lambda m: m["palavras"]), grupo_doc),
            "latencia_s (C - A)": pareado(media_por_pergunta(a, lambda m: m["latencia_s"]),
                                          media_por_pergunta(c, lambda m: m["latencia_s"]), grupo_doc)}

    b = arquivos.get("respostas_B.jsonl", [])
    if b:
        top1 = [l for l in b if l["variante"] == "top1" and l["recall@5"] is not None]
        res["B"] = {"perguntas_com_gabarito": len(top1),
                    "recall@5": ic_media([l["recall@5"] for l in top1]),
                    "hit@5": f"{int(sum(l['hit@5'] for l in top1))}/{len(top1)}",
                    "MRR": ic_media([l["MRR"] for l in top1]),
                    "recall@5_ic_agrupado_por_documento": ic_agrupado({l["id"]: l["recall@5"] for l in top1}, grupo_doc),
                    "top1_relevante": f"{sum(l['trechos_relevantes_no_topn'] > 0 for l in top1)}/{len(top1)}",
                    "top3_com_algum_relevante": f"{sum(l['trechos_relevantes_no_topn'] > 0 for l in b if l['variante'] == 'top3' and l['recall@5'] is not None)}/{len(top1)}",
                    "flesch_top1_media": _media([l["flesch_ptbr"] for l in b if l["variante"] == "top1"]),
                    "flesch_top3_media": _media([l["flesch_ptbr"] for l in b if l["variante"] == "top3"]),
                    "palavras_top1_media": _media([l["palavras"] for l in b if l["variante"] == "top1"]),
                    "palavras_top3_media": _media([l["palavras"] for l in b if l["variante"] == "top3"]),
                    "latencia_busca_mediana_s": _mediana([l["segundos_busca"] for l in top1]),
                    "latencia_busca_p95_s": p95([l["segundos_busca"] for l in b if l["variante"] == "top1"]),
                    "por_categoria": {cat: {"n": len(v), "recall@5": _media([l["recall@5"] for l in v]),
                                            "hit@5": _media([l["hit@5"] for l in v])}
                                      for cat in ("factual", "sintese")
                                      for v in [[l for l in top1 if l["categoria"] == cat]]}}

    for nome, linhas in arquivos.items():
        m = re.match(r"respostas_D_(.+)\.jsonl", nome)
        if not m:
            continue
        res["D"][m.group(1)] = {cfg: agregar_d([l for l in linhas if l["config"] == cfg]) for cfg in ("completo", "sem_rag")}
        res["D"][m.group(1)]["pareado_completo_menos_sem_rag"] = pareado_d(linhas)
        res["D"][m.group(1)]["liberacao_externa"] = sorted({str(l.get("liberacao_externa")) for l in linhas})
        res["D"][m.group(1)]["rodadas"] = sorted({l["repeticao"] for l in linhas})

    C.escrever_json(C.SAIDAS / "metricas.json", res)
    (C.SAIDAS / "metricas.txt").write_text(texto(res), encoding="utf-8")
    print(texto(res))


def texto(res: dict) -> str:
    L = ["SEMANA 3 - MÉTRICAS DETERMINÍSTICAS (sem juiz; fidelidade e utilidade vêm do julgamento)",
         f"gerado em {res['gerado_em']} | commit {res['commit']}", "", "Integridade (antes de pontuar):"]
    for nome, i in res["integridade"].items():
        if nome.startswith("_"):
            continue
        L.append(f"  {nome:40s} linhas={i['linhas']} válidas={i['validas_unicas']}/{i.get('esperado')} "
                 f"erros={i['erros_api']} vazias={i['vazias']} duplicatas={i['duplicatas']} cortadas={i['cortadas_por_limite_de_tokens']}")
    L += ["", "A (LLM sozinho) e C (RAG + LLM, prompt v1), só repetições completas:"]
    for k, a in res["A_C"].items():
        e = a["estabilidade"]
        L.append(f"  {k:22s} reps={a['repeticoes_completas']} abstenção Q39/Q40={a['abstencao_correta_q39_q40']} "
                 f"cobertura38={a['cobertura_38']} frases c/ citação={a['pct_frases_com_citacao_media']} "
                 f"cit. inválida={a['respostas_com_citacao_invalida']} palavras={a['palavras_media']} "
                 f"lat. mediana={a['latencia_mediana_s']} s p95={a['latencia_p95_s']} s "
                 f"tokens={a['tokens_entrada_media']}+{a['tokens_saida_media']} US$/mil={a['custo_usd_por_mil_respostas']}")
        if e.get("perguntas_com_2_ou_mais_repeticoes"):
            L.append(f"  {'':22s} estabilidade: texto idêntico {e['texto_identico_em_todas']}/{e['perguntas_com_2_ou_mais_repeticoes']}, "
                     f"abstenção igual {e['abstencao_igual_em_todas']}/{e['perguntas_com_2_ou_mais_repeticoes']}")
    if res["B"]:
        b = res["B"]
        L += ["", "B (só busca, qwen3+rerank):",
              f"  recall@5 {b['recall@5']} | hit@5 {b['hit@5']} | MRR {b['MRR']} | recall@5 IC por documento {b['recall@5_ic_agrupado_por_documento']}",
              f"  top-1 relevante {b['top1_relevante']} | top-3 com algum relevante {b['top3_com_algum_relevante']}",
              f"  Flesch top1 {b['flesch_top1_media']} top3 {b['flesch_top3_media']} | palavras top1 {b['palavras_top1_media']} top3 {b['palavras_top3_media']}",
              f"  busca: mediana {b['latencia_busca_mediana_s']} s, p95 {b['latencia_busca_p95_s']} s (VPS, CPU)"]
    for modelo, p in res["pareado_A_C"].items():
        L += ["", f"Pareado por pergunta, C - A ({modelo}); [média, IC95 inferior, superior]:"]
        for k, v in p.items():
            L.append(f"  {k:20s} n={v['n']} dif={v['dif_media_ic95']} IC por documento={v['dif_ic95_agrupado_por_documento']} Wilcoxon p={v['wilcoxon_p']}")
    for modelo, d in res["D"].items():
        L += ["", f"D (Adaptador, Golden Benchmark, {modelo}; rodadas {d['rodadas']}; liberação externa {d['liberacao_externa']}):"]
        for cfg in ("completo", "sem_rag"):
            x = d[cfg]
            L.append(f"  {cfg:9s} válidas={x['saidas_validas']} erros={x['erros']} TRCC={x['trcc_media']} TRCC>=0,95={x['pct_trcc_ge_095']} "
                     f"Flesch {x['flesch_antes_media']}->{x['flesch_depois_media']} cmd conj. resolvido={x['pct_cmd_conjugado_resolvido']} "
                     f"nível={x['pct_aderencia_nivel']} escopo={x['pct_escopo_aprovado']} reserva={x['pct_reserva']} "
                     f"tokens={x['tokens_media']} ciclo p95={x['ciclo_s_p95']} s RNF-07={x['pct_dentro_rnf07']}")
        for k, v in d["pareado_completo_menos_sem_rag"].items():
            L.append(f"  completo - sem_rag {k:24s} n={v['n']} dif={v['dif_media_ic95']} Wilcoxon p={v['wilcoxon_p']}")
    L += ["", "Leitura: só diferença com IC que exclui o zero conta. Uma pergunta vale 2,6 pontos (38); uma questão do D, 3,3.",
          "Latências de A e C incluem espera do limite do Groq na geração? Não: 'segundos_geracao' é só a chamada que deu certo;",
          "a espera fica em 'segundos_espera_limite'. No C soma-se o tempo da busca daquela pergunta (VPS, CPU)."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
