"""rodada_r50.py: rodada complementar com a reordenação sobre 50 candidatos (B50 e C50).

Registrada no PREREG em 12/11/2026 antes de rodar. Reutiliza os scripts da semana 3 sem alterá-los:
troca só a pasta de saída (saidas_r50/) e o número de candidatos do reranker (20 -> 50).

Passos (cada um é um subcomando; rodar nesta ordem):
  conferir   busca com 20 candidatos no PC tem de dar o mesmo top-5 gravado pela VPS      [ambiente com torch]
  busca      busca com 50 candidatos nas 40 perguntas; grava trechos e prompts; confere
             o recall@5 contra o valor de 09/11 (0,42; 33 de 38)                           [ambiente com torch]
  gerar      B50 (texto dos trechos) e C50 (Llama 3.1 8B, 3 repetições, prompt v1)         [Ollama]
  metricas   métricas sem juiz de B50 e C50 (saidas_r50/metricas.txt)
  lotes      lotes cegos novos para o juiz (testes rotulados B50 e C50 na chave)
  analise    métricas do juiz de B50 e C50 e comparações pareadas (saidas_r50/juiz_r50.txt)

Ambiente da busca: RAG_BANCO=memoria e RAG_CACHE apontando para a pasta com os vetores (.npy).
"""
from __future__ import annotations

import json
import sys
from collections import Counter

import comum as C

SAIDAS_PADRAO = C.SAIDAS
SAIDAS_R50 = C.AQUI / "saidas_r50"
CANDIDATOS = 50
ESPERADO_RECALL, ESPERADO_HIT = 0.42, 33      # outputs/18-variacoes-busca.txt (qwen3+rerank50, gabarito do Opus)


def apontar_para_r50() -> None:
    C.SAIDAS = SAIDAS_R50
    C.TRECHOS_BUSCA = SAIDAS_R50 / "trechos_busca.jsonl"
    C.PROMPTS_AC = SAIDAS_R50 / "prompts_ac.jsonl"
    SAIDAS_R50.mkdir(exist_ok=True)


def recall_e_hit(busca: dict[str, dict]) -> tuple[float, int, int]:
    """recall@5 e perguntas com ao menos 1 trecho relevante no top-5 (só nota 2), nas perguntas com resposta."""
    rs, hit = [], 0
    for it in C.itens_gabarito():
        rel = set(it.get("trechos_relevantes", []))
        if not rel:
            continue
        top5 = {x["chunk_id"] for x in busca[it["id"]]["ranking_top10"][:5]}
        rs.append(len(rel & top5) / len(rel))
        hit += bool(rel & top5)
    return sum(rs) / len(rs), hit, len(rs)


def conferir() -> None:
    C.adicionar_pacote_ao_path()
    import consultar
    assert consultar.CANDIDATOS_RERANK == 20, "esta conferência usa o padrão do código (20 candidatos)"
    vps = {l["id"]: l for l in C.ler_jsonl(SAIDAS_PADRAO / "trechos_busca.jsonl")}
    iguais, dif = 0, []
    for it in C.itens_gabarito():
        rk = consultar.ranking(it["pergunta"], "qwen3+rerank", 10)
        meu = [cid for cid, _ in rk[:5]]
        dela = [x["chunk_id"] for x in vps[it["id"]]["ranking_top10"][:5]]
        if meu == dela:
            iguais += 1
        else:
            dif.append((it["id"], len(set(meu) & set(dela))))
    print(f"banco={consultar.BANCO} | top-5 igual ao da VPS (mesma ordem) em {iguais} de {len(vps)} perguntas")
    for q, n in dif:
        print(f"   {q}: {n} de 5 trechos em comum")
    r, h, n = recall_e_hit(vps)
    print(f"recall@5 do arquivo da VPS (20 candidatos): {r:.3f}; ao menos 1 certo em {h} de {n}")
    if dif:
        raise SystemExit("PAROU: a busca do PC não reproduz a da VPS com 20 candidatos.")
    print("conferência 1 ok")


def busca() -> None:
    apontar_para_r50()
    C.adicionar_pacote_ao_path()
    import consultar
    consultar.CANDIDATOS_RERANK = CANDIDATOS
    import busca as B
    B.main()
    linhas = C.ler_jsonl(C.TRECHOS_BUSCA)
    C.escrever_jsonl(C.TRECHOS_BUSCA, [l | {"metodo": "qwen3+rerank50", "candidatos_rerank": CANDIDATOS} for l in linhas])
    b = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    r, h, n = recall_e_hit(b)
    print(f"recall@5 com {CANDIDATOS} candidatos: {r:.3f}; ao menos 1 certo em {h} de {n} "
          f"(esperado {ESPERADO_RECALL:.2f} e {ESPERADO_HIT} de 38)")
    padrao = {l["id"]: l for l in C.ler_jsonl(SAIDAS_PADRAO / "trechos_busca.jsonl")}
    mudou = sum([x["chunk_id"] for x in b[q]["ranking_top10"][:5]] != [x["chunk_id"] for x in padrao[q]["ranking_top10"][:5]] for q in b)
    print(f"perguntas em que o top-5 mudou em relação à busca de 20 candidatos: {mudou} de {len(b)}")
    if round(r, 2) != ESPERADO_RECALL or h != ESPERADO_HIT:
        raise SystemExit("PAROU: o recall com 50 candidatos não reproduz o de 09/11.")
    print("conferência 2 ok")


def gerar() -> None:
    apontar_para_r50()
    import gerar_ac
    import teste_b
    teste_b.main()
    gerar_ac.main(["--modelo", "llama3.1-8b", "--testes", "C"])


def metricas() -> None:
    apontar_para_r50()
    import metricas as M
    M.main()


def lotes() -> None:
    """Mesma montagem de pacotes_juiz.py, com os testes rotulados B50 e C50 e os trechos da busca nova."""
    apontar_para_r50()
    import pacotes_juiz as P
    busca_r50 = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    itens = [it | {"teste": it["teste"] + "50"} for it in P.itens_ac_b(busca_r50)]
    itens.sort(key=P._chave_item)
    itens = P.agrupar_repeticoes_iguais(itens)
    arq = C.JUIZ / "chave.json"
    dados = json.loads(arq.read_text(encoding="utf-8"))
    chave = dados["chave"]
    ja = {P._chave_item(v) for v in chave.values()}
    novos = [x for x in itens if P._chave_item(x) not in ja]
    n_global = max(int(k[1:]) for k in chave)
    ultimo = max(int(v["lote"].rsplit("-", 1)[1]) for v in chave.values() if v["lote"].startswith("resp"))
    cont = Counter()
    for i, it in enumerate(C.embaralhar(novos, C.SEMENTE + n_global)):
        n_global += 1
        idc, lote = f"R{n_global:04d}", f"resp-lote-{ultimo + i // P.TAM_LOTE + 1:02d}"
        chave[idc] = ({k: it.get(k) for k in ("teste", "modelo", "config", "id_pergunta", "repeticao")}
                      | {"repeticoes": it["repeticoes"], "lote": lote})
        C.acrescentar_jsonl(C.JUIZ / f"{lote}.jsonl", P.linha_cega(it, idc))
        cont[lote] += 1
    C.escrever_json(arq, dados | {"n": len(chave), "gerado_em": C.agora_iso(), "chave": chave})
    print(f"novos itens: {sum(cont.values())} em {dict(cont)}")
    print(dict(Counter(f"{k['teste']}|{k['modelo']}" for k in chave.values() if k["teste"].endswith("50"))))


def analise() -> None:
    import analise_juiz as A
    import metricas as M
    chave, ver, avisos = A.carregar()
    resp, _, cobertura = A.expandir(chave, ver)
    gab = {it["id"]: it for it in C.itens_gabarito()}
    cat = {k: v["categoria"] for k, v in gab.items()}
    grp = {k: v["doc_dominante"] for k, v in gab.items()}
    pc: dict[str, list[dict]] = {}
    for m in resp:
        pc.setdefault(m["condicao"], []).append(m)
    mod = "llama3.1-8b"
    conds = {c: A.por_condicao(pc[c], cat, grp) for c in
             (f"A|{mod}", f"C|{mod}", f"C50|{mod}", "B|busca-top1", "B50|busca-top1", "B|busca-top3", "B50|busca-top3") if c in pc}
    ac = ["fidelidade", "fidelidade_sem_abstencao", "util_sim", "util_sim_ou_parcial", "inventou", "absteve_juiz",
          "tem_frase_que_contradiz"]
    bb = ["util_sim", "util_sim_ou_parcial", "inventou"]
    pares = {
        f"C50 - C|{mod}": A.comparar(pc[f"C|{mod}"], pc[f"C50|{mod}"], ac, cat, grp),
        f"C50 - A|{mod}": A.comparar(pc[f"A|{mod}"], pc[f"C50|{mod}"], ac, cat, grp),
        "B50 - B|busca-top1": A.comparar(pc["B|busca-top1"], pc["B50|busca-top1"], bb, cat, grp),
        "B50 - B|busca-top3": A.comparar(pc["B|busca-top3"], pc["B50|busca-top3"], bb, cat, grp),
        f"C50|{mod} - B50|busca-top3": A.comparar(pc["B50|busca-top3"], pc[f"C50|{mod}"], bb, cat, grp),
        f"C50|{mod} - B50|busca-top1": A.comparar(pc["B50|busca-top1"], pc[f"C50|{mod}"], bb, cat, grp),
    }
    sj = json.loads((SAIDAS_R50 / "metricas.json").read_text(encoding="utf-8"))
    g = sj["A_C"][f"C|{mod}"]
    portoes = {"abstencao_q39_q40": g["abstencao_correta_q39_q40"], "passa_abstencao": bool(g["abstencao_correta_todas"]),
               "latencia_p95_s": g["latencia_p95_s"], "passa_latencia": bool(g["latencia_p95_dentro_rnf07"]),
               "cobertura_38": g["cobertura_38"], "pct_frases_com_citacao": g["pct_frases_com_citacao_media"],
               "texto_identico_nas_3": g["estabilidade"]["texto_identico_em_todas"]}
    res = {"gerado_em": C.agora_iso(), "commit": C.commit_atual(), "candidatos_rerank": CANDIDATOS,
           "cobertura": {k: v for k, v in cobertura.items() if "50" in k}, "avisos": avisos,
           "portoes_C50": portoes, "B50_busca": sj["B"], "condicoes": conds, "pareados": pares}
    L = [f"SEMANA 3 - RODADA COMPLEMENTAR, REORDENAÇÃO SOBRE {CANDIDATOS} CANDIDATOS (juiz Claude Opus, não validado por pessoa)",
         f"gerado em {res['gerado_em']} | commit {res['commit']}", "", f"cobertura: {res['cobertura']}",
         f"portões do C50 (código): {json.dumps(portoes, ensure_ascii=False)}",
         f"busca: recall@5 {sj['B']['recall@5']} | hit@5 {sj['B']['hit@5']} | MRR {sj['B']['MRR']}", "",
         "Condições; [média entre perguntas, IC95 inferior, superior]:"]
    for c, v in conds.items():
        L.append(f"  {c}  respostas={v['respostas']} frases={v['frases_sustentadas']}/{v['frases_julgadas']} útil={v['util_contagem']}")
        for nome in A.CAMPOS_RESP:
            L.append(f"      {nome:26s} {A.fmt(v[nome]['media_ic95'])}  n={v[nome]['n_perguntas']}")
    L += ["", "Diferenças pareadas por pergunta (segundo - primeiro):"]
    for par, campos in pares.items():
        L.append(f"  {par}")
        for nome, r in campos.items():
            L.append(f"      {nome:26s} n={r['n']} dif={A.fmt(r['dif_media_ic95'])} por documento {A.fmt(r['dif_ic95_agrupado_por_documento'])} "
                     f"Wilcoxon p={r['wilcoxon_p']} melhoraram={r['perguntas_melhoraram']} pioraram={r['perguntas_pioraram']}")
    C.escrever_json(SAIDAS_R50 / "juiz_r50.json", res)
    (SAIDAS_R50 / "juiz_r50.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    {"conferir": conferir, "busca": busca, "gerar": gerar, "metricas": metricas, "lotes": lotes, "analise": analise}.get(
        acao, lambda: sys.exit("use: conferir | busca | gerar | metricas | lotes | analise"))()
