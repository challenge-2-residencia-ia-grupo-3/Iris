"""rodada_fora.py: rodada complementar com 25 perguntas que a base não responde (rejeição negativa).

Registrada no PREREG em 13/11/2026 antes de rodar. Perguntas: gabarito/fora_da_base_v1.json (20 "perto",
5 "longe"). Condições: A, C (20 candidatos) e C50 (50 candidatos), Llama 3.1 8B, 3 repetições, mesmos
prompts e parâmetros da análise principal. Saídas em saidas_fora/.

Subcomandos (nesta ordem):
  busca     busca com 20 e com 50 candidatos; grava trechos e os prompts exatos           [ambiente com torch]
  gerar     A, C e C50 com o Llama                                                         [Ollama]
  abstencao taxa de abstenção pelo detector de código, com IC 95% (saidas_fora/abstencao.txt)
  limiar    o escore do reordenador separa pergunta com resposta de pergunta sem?          (limiar.txt)
  lotes     lotes cegos para o juiz, só com os textos em que o sistema NÃO se absteve
  analise   o que o juiz achou das respostas dadas sem a base responder (juiz_fora.txt)
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter

import comum as C

SAIDAS_FORA = C.AQUI / "saidas_fora"
PERGUNTAS = C.IRIS_RAG / "gabarito" / "fora_da_base_v1.json"
MODELO = "llama3.1-8b"
CONDICOES = ("A", "C", "C50")
CANDIDATOS = {"C": 20, "C50": 50}
B = 2000                                     # reamostragens do bootstrap, igual à análise principal


def perguntas() -> list[dict]:
    return json.loads(PERGUNTAS.read_text(encoding="utf-8"))["itens"]


def arq_trechos(cond: str):
    return SAIDAS_FORA / f"trechos_busca_{CANDIDATOS[cond]}.jsonl"


def arq_resp(cond: str):
    return SAIDAS_FORA / f"respostas_{cond}_{MODELO}.jsonl"


# ---------------------------------------------------------------- busca e prompts
def busca() -> None:
    SAIDAS_FORA.mkdir(exist_ok=True)
    C.adicionar_pacote_ao_path()
    import time

    import consultar
    import gerar
    assert gerar.PROMPT_VERSAO == "v1"
    commit = C.commit_atual()
    for cond, cand in CANDIDATOS.items():
        consultar.CANDIDATOS_RERANK = cand          # único parâmetro que muda entre C e C50
        feitos = {l["id"] for l in C.ler_jsonl(arq_trechos(cond))}
        for it in perguntas():
            if it["id"] in feitos:
                continue
            t0 = time.time()
            rk = consultar.ranking(it["pergunta"], "qwen3+rerank", 10)
            seg = round(time.time() - t0, 2)
            top5 = [consultar.trecho(cid, pos, nota) for pos, (cid, nota) in enumerate(rk[:5], 1)]
            C.acrescentar_jsonl(arq_trechos(cond), {
                "id": it["id"], "pergunta": it["pergunta"], "estrato": it["estrato"], "candidatos_rerank": cand,
                "banco": consultar.BANCO, "reranker": consultar.RERANKER,
                "ranking_top10": [{"chunk_id": cid, "score": round(float(n), 4)} for cid, n in rk],
                "trechos_top5": top5, "segundos_busca": seg, "data_hora": C.agora_iso(), "commit": commit})
            print(f"{cond} {it['id']} busca {seg:.1f} s top1={rk[0][0]} escore={rk[0][1]:.2f}", flush=True)
    tr = {c: {l["id"]: l for l in C.ler_jsonl(arq_trechos(c))} for c in CANDIDATOS}
    linhas = []
    for it in perguntas():
        p = {"A": C.montar_prompt_a(it["pergunta"])}
        for c in CANDIDATOS:
            p[c] = gerar.montar_prompt(it["pergunta"], tr[c][it["id"]]["trechos_top5"], "v1")
        linhas.append({"id": it["id"], "estrato": it["estrato"], "pergunta": it["pergunta"]}
                      | {f"prompt_{c}": p[c] for c in CONDICOES} | {f"sha16_prompt_{c}": C.sha16(p[c]) for c in CONDICOES})
    C.escrever_jsonl(SAIDAS_FORA / "prompts.jsonl", linhas)
    print(f"prompts gravados: {len(linhas)} perguntas", flush=True)


# ---------------------------------------------------------------- geração
def gerar() -> None:
    import time
    prompts = C.ler_jsonl(SAIDAS_FORA / "prompts.jsonl")
    assert len(prompts) == 25, "rode 'busca' antes"
    tr = {c: {l["id"]: l for l in C.ler_jsonl(arq_trechos(c))} for c in CANDIDATOS}
    provedor, id_modelo = C.MODELOS[MODELO]
    commit = C.commit_atual()
    ja = {c: {(l["id"], l["repeticao"]) for l in C.ler_jsonl(arq_resp(c)) if not l.get("erro")} for c in CONDICOES}
    n, total = 0, C.REPETICOES * len(CONDICOES) * len(prompts)
    for rep in range(1, C.REPETICOES + 1):
        for cond in CONDICOES:
            for p in prompts:
                n += 1
                if (p["id"], rep) in ja[cond]:
                    continue
                b = tr.get(cond, tr["C"])[p["id"]]      # em A os trechos não são vistos pelo modelo
                linha = {"teste": cond, "id": p["id"], "estrato": p["estrato"], "repeticao": rep,
                         "pergunta": p["pergunta"], "categoria": "fora_da_base", "modelo": MODELO,
                         "provedor": provedor, "id_modelo": id_modelo, "temperatura": C.TEMPERATURA,
                         "versao_prompt": "A-v1" if cond == "A" else "v1", "sha16_prompt": C.sha16(p[f"prompt_{cond}"]),
                         "commit": commit, "data_hora": C.agora_iso(), "trechos_entregues_ao_modelo": cond != "A",
                         "trechos": [{"ref": f"T{i}", "chunk_id": t["chunk_id"], "doc": t["doc"], "score": t.get("score")}
                                     for i, t in enumerate(b["trechos_top5"], 1)],
                         "segundos_busca": b["segundos_busca"] if cond != "A" else None}
                t0 = time.time()
                try:
                    r = C.chamar(MODELO, p[f"prompt_{cond}"])
                    linha.update({"resposta": r["texto"], "tokens_entrada": r["tokens_entrada"],
                                  "tokens_saida": r["tokens_saida"], "segundos_geracao": r["segundos_geracao"],
                                  "modelo_informado": r["modelo_informado"], "fim": r["fim"], "erro": None})
                except Exception as e:  # noqa: BLE001 - o erro fica gravado e é contado
                    linha.update({"resposta": None, "erro": f"{type(e).__name__}: {str(e)[:200]}"})
                linha["segundos_total_chamada"] = round(time.time() - t0, 2)
                C.acrescentar_jsonl(arq_resp(cond), linha)
                print(f"[{n}/{total}] {cond} {p['id']} r{rep} | {(linha.get('resposta') or linha['erro']).replace(chr(10), ' ')[:80]}",
                      flush=True)
    print("fim", flush=True)


# ---------------------------------------------------------------- abstenção (detector de código)
def absteve(cond: str, texto: str) -> bool:
    """O mesmo critério de metricas.por_resposta: frase fixa de abstenção do prompt de cada condição."""
    if cond == "A":
        return C.FRASE_NAO_SEI.lower()[:30] in texto.lower()
    C.adicionar_pacote_ao_path()
    import gerar
    return gerar.FRASE_SEM_RESPOSTA.lower()[:40] in texto.lower()


def ic_proporcao(por_pergunta: list[float]) -> list[float]:
    """Média entre perguntas e IC 95% por bootstrap sobre perguntas (semente da análise principal)."""
    rng = random.Random(C.SEMENTE)
    n = len(por_pergunta)
    medias = sorted(sum(rng.choice(por_pergunta) for _ in range(n)) / n for _ in range(B))
    return [round(sum(por_pergunta) / n, 4), round(medias[int(0.025 * B)], 4), round(medias[int(0.975 * B) - 1], 4)]


def abstencao() -> None:
    res, L = {}, ["RODADA COMPLEMENTAR - PERGUNTAS FORA DA BASE: taxa de abstenção (detector de código)",
                  f"gerado em {C.agora_iso()} | commit {C.commit_atual()} | modelo {MODELO} | 3 repetições", "",
                  "[média entre perguntas, IC95 inferior, superior]; 'sempre' = absteve nas 3 repetições"]
    estr = {it["id"]: it["estrato"] for it in perguntas()}
    for cond in CONDICOES:
        linhas = [l for l in C.ler_jsonl(arq_resp(cond)) if not l.get("erro")]
        pq: dict[str, list[bool]] = {}
        for l in linhas:
            pq.setdefault(l["id"], []).append(absteve(cond, l["resposta"] or ""))
        res[cond] = {"respostas": len(linhas), "erros": len(C.ler_jsonl(arq_resp(cond))) - len(linhas)}
        L += ["", f"{cond}  respostas={len(linhas)}"]
        for nome, ids in (("perto", [k for k in pq if estr[k] == "perto"]), ("longe", [k for k in pq if estr[k] == "longe"]),
                          ("todas", list(pq))):
            taxa = [sum(pq[k]) / len(pq[k]) for k in sorted(ids)]
            r = {"n_perguntas": len(ids), "taxa_ic95": ic_proporcao(taxa),
                 "sempre": sum(all(pq[k]) for k in ids), "nunca": sum(not any(pq[k]) for k in ids),
                 "instavel": sorted(k for k in ids if 0 < sum(pq[k]) < len(pq[k]))}
            res[cond][nome] = r
            L.append(f"    {nome:6s} n={r['n_perguntas']:2d} taxa={r['taxa_ic95']} sempre={r['sempre']} nunca={r['nunca']} "
                     f"instável={r['instavel']}")
        res[cond]["nao_absteve"] = sorted(k for k in pq if not all(pq[k]))
        L.append(f"    não se absteve em: {res[cond]['nao_absteve']}")
    # junto com Q39 e Q40 da análise principal (27 perguntas sem resposta), só A e C: C50 tem saída própria
    junto = {}
    for cond, arq in (("A", C.SAIDAS / f"respostas_A_{MODELO}.jsonl"), ("C", C.SAIDAS / f"respostas_C_{MODELO}.jsonl"),
                      ("C50", C.AQUI / "saidas_r50" / f"respostas_C_{MODELO}.jsonl")):
        pq = {}
        for l in C.ler_jsonl(arq):
            if l["id"] in ("Q39", "Q40") and not l.get("erro"):
                pq.setdefault(l["id"], []).append(absteve(cond, l["resposta"] or ""))
        for l in C.ler_jsonl(arq_resp(cond)):
            if not l.get("erro"):
                pq.setdefault(l["id"], []).append(absteve(cond, l["resposta"] or ""))
        junto[cond] = {"n_perguntas": len(pq), "taxa_ic95": ic_proporcao([sum(v) / len(v) for _, v in sorted(pq.items())]),
                       "sempre": sum(all(v) for v in pq.values())}
    res["com_q39_q40"] = junto
    L += ["", "Com Q39 e Q40 da análise principal (27 perguntas sem resposta):"]
    L += [f"    {c:4s} n={v['n_perguntas']} taxa={v['taxa_ic95']} sempre={v['sempre']}" for c, v in junto.items()]
    C.escrever_json(SAIDAS_FORA / "abstencao.json", res)
    (SAIDAS_FORA / "abstencao.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- limiar de escore
def auc(pos: list[float], neg: list[float]) -> float:
    """Probabilidade de uma pergunta COM resposta ter escore maior que uma SEM resposta (empate vale meio)."""
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def limiar() -> None:
    res, L = {}, ["RODADA COMPLEMENTAR - LIMIAR DE ESCORE DA BUSCA",
                  "O escore do reordenador separa as perguntas com resposta (38) das sem resposta (Q39, Q40 e as 25 novas)?",
                  "AUC = chance de uma pergunta com resposta ter escore maior que uma sem; 0,5 é acaso, 1,0 é separação perfeita.",
                  "O corte (índice de Youden) é escolhido e relatado no mesmo conjunto: número otimista.", ""]
    gab = {it["id"]: it for it in C.itens_gabarito()}
    for nome, arq_q, cond in (("20 candidatos", C.SAIDAS / "trechos_busca.jsonl", "C"),
                              ("50 candidatos", C.AQUI / "saidas_r50" / "trechos_busca.jsonl", "C50")):
        linhas = C.ler_jsonl(arq_q) + C.ler_jsonl(arq_trechos(cond))
        for medida, f in (("escore do 1º trecho", lambda l: l["ranking_top10"][0]["score"]),
                          ("média dos 3 primeiros", lambda l: sum(x["score"] for x in l["ranking_top10"][:3]) / 3)):
            pos = [(l["id"], f(l)) for l in linhas if l["id"] in gab and gab[l["id"]]["categoria"] != "fora_da_base"]
            neg = [(l["id"], f(l)) for l in linhas if l["id"] not in gab or gab[l["id"]]["categoria"] == "fora_da_base"]
            a = auc([x for _, x in pos], [x for _, x in neg])
            rng = random.Random(C.SEMENTE)
            bs = sorted(auc([rng.choice(pos)[1] for _ in pos], [rng.choice(neg)[1] for _ in neg]) for _ in range(B))
            cortes = sorted({x for _, x in pos + neg})
            melhor = max(cortes, key=lambda c: sum(x >= c for _, x in pos) / len(pos) + sum(x < c for _, x in neg) / len(neg))
            r = {"n_com": len(pos), "n_sem": len(neg), "auc_ic95": [round(a, 3), round(bs[int(0.025 * B)], 3), round(bs[int(0.975 * B) - 1], 3)],
                 "corte_youden": round(melhor, 2),
                 "com_resposta_acima_do_corte": sum(x >= melhor for _, x in pos),
                 "sem_resposta_abaixo_do_corte": sum(x < melhor for _, x in neg),
                 "sem_resposta_acima_do_corte": sorted(i for i, x in neg if x >= melhor),
                 "com_resposta_abaixo_do_corte": sorted(i for i, x in pos if x < melhor),
                 "mediana_com": round(sorted(x for _, x in pos)[len(pos) // 2], 2),
                 "mediana_sem": round(sorted(x for _, x in neg)[len(neg) // 2], 2)}
            # conferência mais dura, acrescentada depois de ver o AUC: tira uma pergunta, escolhe o corte nas
            # outras e classifica a que ficou de fora (o corte nunca vê a pergunta que classifica)
            todos = [(i, x, 1) for i, x in pos] + [(i, x, 0) for i, x in neg]
            certos_com = certos_sem = 0
            for j, (_, x, rot) in enumerate(todos):
                resto = todos[:j] + todos[j + 1:]
                rp, rn = [v for _, v, t in resto if t], [v for _, v, t in resto if not t]
                c = max(sorted({v for _, v, _ in resto}),
                        key=lambda k: sum(v >= k for v in rp) / len(rp) + sum(v < k for v in rn) / len(rn))
                certos_com += rot == 1 and x >= c
                certos_sem += rot == 0 and x < c
            r |= {"fora_da_amostra_com_resposta_liberadas": certos_com, "fora_da_amostra_sem_resposta_barradas": certos_sem}
            res[f"{nome} | {medida}"] = r
            loo = f"    deixando uma de fora: com resposta liberadas {certos_com}/{len(pos)}, sem resposta barradas {certos_sem}/{len(neg)}"
            L += [f"{nome} | {medida}", f"    com resposta n={r['n_com']} (mediana {r['mediana_com']}) | sem resposta n={r['n_sem']} (mediana {r['mediana_sem']})",
                  f"    AUC {r['auc_ic95']}", f"    corte {r['corte_youden']}: com resposta acima {r['com_resposta_acima_do_corte']}/{r['n_com']}, "
                  f"sem resposta abaixo {r['sem_resposta_abaixo_do_corte']}/{r['n_sem']}",
                  f"    sem resposta que passariam: {r['sem_resposta_acima_do_corte']}",
                  f"    com resposta que seriam barradas: {r['com_resposta_abaixo_do_corte']}", loo, ""]
    C.escrever_json(SAIDAS_FORA / "limiar.json", res)
    (SAIDAS_FORA / "limiar.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- juiz
def lotes() -> None:
    """Só os textos distintos em que o sistema NÃO se absteve. Testes rotulados NA, NC e NC50 na chave."""
    import pacotes_juiz as P
    itens = []
    for cond in CONDICOES:
        tr = {l["id"]: l for l in C.ler_jsonl(arq_trechos(cond if cond != "A" else "C"))}
        vistos = {}
        for l in C.ler_jsonl(arq_resp(cond)):
            if not l.get("erro") and (l.get("resposta") or "").strip() and not absteve(cond, l["resposta"]):
                vistos[(l["id"], l["repeticao"])] = l
        for l in vistos.values():
            itens.append({"tipo_tarefa": "resposta_ao_professor", "teste": "N" + cond, "modelo": MODELO,
                          "id_pergunta": l["id"], "repeticao": l["repeticao"], "pergunta": l["pergunta"],
                          "trechos": P._trechos(tr[l["id"]]["trechos_top5"]), "resposta": l["resposta"]})
    itens.sort(key=P._chave_item)
    itens = P.agrupar_repeticoes_iguais(itens)
    arq = C.JUIZ / "chave.json"
    dados = json.loads(arq.read_text(encoding="utf-8"))
    chave = dados["chave"]
    ja = {P._chave_item(v) for v in chave.values()}
    novos = [x for x in itens if P._chave_item(x) not in ja]
    n_global = max(int(k[1:]) for k in chave)
    ultimo = max(int(v["lote"].rsplit("-", 1)[1]) for v in chave.values() if v["lote"].startswith("resp"))
    n_lotes = max(1, -(-len(novos) // P.TAM_LOTE))
    tam = -(-len(novos) // n_lotes)                # lotes de tamanho parecido
    cont = Counter()
    for i, it in enumerate(C.embaralhar(novos, C.SEMENTE + n_global)):
        n_global += 1
        idc, lote = f"R{n_global:04d}", f"resp-lote-{ultimo + i // tam + 1:02d}"
        chave[idc] = ({k: it.get(k) for k in ("teste", "modelo", "config", "id_pergunta", "repeticao")}
                      | {"repeticoes": it["repeticoes"], "lote": lote})
        C.acrescentar_jsonl(C.JUIZ / f"{lote}.jsonl", P.linha_cega(it, idc))
        cont[lote] += 1
    C.escrever_json(arq, dados | {"n": len(chave), "gerado_em": C.agora_iso(), "chave": chave})
    print(f"novos itens: {sum(cont.values())} em {dict(cont)}")
    print(dict(Counter(k["teste"] for k in chave.values() if k["teste"].startswith("N"))))


def analise() -> None:
    import analise_juiz as A
    chave, ver, avisos = A.carregar()
    resp, _, cobertura = A.expandir(chave, ver)
    estr = {it["id"]: it["estrato"] for it in perguntas()}
    res = {"gerado_em": C.agora_iso(), "commit": C.commit_atual(), "avisos": avisos,
           "cobertura": {k: v for k, v in cobertura.items() if "|N" in k}, "condicoes": {}}
    L = ["RODADA COMPLEMENTAR - PERGUNTAS FORA DA BASE: o que o juiz achou das respostas dadas",
         "(juiz Claude Opus, não validado por pessoa; só os textos em que o detector de código não viu abstenção)",
         f"gerado em {res['gerado_em']} | commit {res['commit']}", f"cobertura: {res['cobertura']}", ""]
    for cond in CONDICOES:
        ms = [m for m in resp if m["teste"] == "N" + cond]
        total = len([l for l in C.ler_jsonl(arq_resp(cond)) if not l.get("erro")])
        pergs = sorted({m["id"] for m in ms})
        inv = sorted({m["id"] for m in ms if m["inventou"] == "sim"})
        r = {"respostas_geradas": total, "respostas_sem_abstencao_julgadas": len(ms), "perguntas": len(pergs),
             "juiz_viu_abstencao": sum(m["absteve_juiz"] == "sim" for m in ms),
             "inventou_sim": sum(m["inventou"] == "sim" for m in ms), "perguntas_com_invencao": inv,
             "inventou_sobre_todas_as_geradas": round(sum(m["inventou"] == "sim" for m in ms) / total, 4) if total else None,
             "frases_julgadas": sum(m["n_frases"] for m in ms), "frases_sustentadas": sum(m["frases_sustentadas"] for m in ms),
             "frases_que_contradizem": sum(m["frases_que_contradizem"] for m in ms),
             "util": dict(Counter(m["util"] for m in ms)),
             "por_estrato": {e: {"julgadas": sum(estr[m["id"]] == e for m in ms),
                                 "inventou_sim": sum(estr[m["id"]] == e and m["inventou"] == "sim" for m in ms)}
                             for e in ("perto", "longe")}}
        res["condicoes"][cond] = r
        L += [f"{cond}: geradas {total}; sem abstenção e julgadas {len(ms)} (em {len(pergs)} perguntas); juiz viu abstenção em {r['juiz_viu_abstencao']}",
              f"    inventou fato ou fonte: {r['inventou_sim']} respostas = {r['inventou_sobre_todas_as_geradas']} de todas as geradas; perguntas: {inv}",
              f"    frases sustentadas {r['frases_sustentadas']}/{r['frases_julgadas']}; contradizem {r['frases_que_contradizem']}; útil {r['util']}",
              f"    por estrato: {r['por_estrato']}", ""]
    C.escrever_json(SAIDAS_FORA / "juiz_fora.json", res)
    (SAIDAS_FORA / "juiz_fora.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    {"busca": busca, "gerar": gerar, "abstencao": abstencao, "limiar": limiar, "lotes": lotes, "analise": analise}.get(
        acao, lambda: sys.exit("use: busca | gerar | abstencao | limiar | lotes | analise"))()
