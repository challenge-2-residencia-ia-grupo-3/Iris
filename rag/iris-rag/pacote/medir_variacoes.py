"""Diagnóstico da busca do Íris e três variações baratas, nos dois gabaritos de modelo.

    .venv/bin/python medir_variacoes.py diagnostico   onde a busca erra e o teto de cada variação (outputs/17)
    .venv/bin/python medir_variacoes.py ranquear      roda as variações e guarda as listas em cache/
    .venv/bin/python medir_variacoes.py medir         compara cada variação com o Qwen3 sozinho (outputs/18)
    .venv/bin/python medir_variacoes.py teto          teto da combinação de A com C, contado antes de rodar (outputs/19)
    .venv/bin/python medir_variacoes.py combinar [N]  roda a combinação D e guarda as listas em cache/ (N = 2, 3...: repetição)
    .venv/bin/python medir_variacoes.py estabilidade  compara a busca do banco com a conta exata do cosseno (outputs/21)
    RAG_PG_DSN=... .venv/bin/python medir_variacoes.py estabilidade-pg N   a mesma comparação no pgvector, execução N (cache/)
    .venv/bin/python medir_variacoes.py medir-estabilidade-pg              junta as execuções do pgvector (outputs/22)
    .venv/bin/python medir_variacoes.py medir-combinacao   compara D com o Qwen3, com A e com C (outputs/20)

Variações (nenhuma muda o chunking, então os chunk_id dos dois gabaritos continuam valendo):
    A  qwen3+rerank50   o reranker relê os 50 primeiros do Qwen3, em vez dos 20
    B  qwen3+max2doc    a ordem do Qwen3, pulando o trecho cujo documento já tem 2 na lista
    C  qwen3 pt+en      duas buscas do Qwen3 (pergunta em português e em inglês), juntas pela posição (RRF, k=60)
    D  pt+en+rerank50   a lista de C, e o reranker relê os 50 primeiros dela com a pergunta em português

Técnica: nenhum modelo é treinado. São dois modelos prontos (Qwen3-Embedding e o reranker mMiniLM), contagens e
sorteio de perguntas (bootstrap). As traduções de perguntas_en.json foram escritas por um modelo (Claude), lendo
só a pergunta, sem ver os trechos certos, e sem revisão humana.
Gabaritos: o rascunho ampliado do Mac (dois juízes de modelo) e o do Opus (um marcador de modelo), lido do
commit em que foi criado. Nenhum dos dois teve revisão humana.
Expectativa e critério: GABARITO-RASCUNHO.md, "Três variações baratas", commitados antes de rodar `ranquear`;
e "Combinação de A com C", commitados antes de rodar `combinar`; e "A busca do pgvector repete?", antes de `estabilidade-pg`.
Não altera consultar.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ["RAG_BANCO"] = "chroma"
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import avaliar  # noqa: E402

OPUS_REF = "f1fae96:challenges/challenge-02-qualidade-de-vida/iris-rag/gabarito/gabarito_rascunho_v0.json"
CACHE = AQUI / "cache" / "rankings-17.json"       # listas do Qwen3 até a posição 100 (português e inglês)
RANK = AQUI / "cache" / "rankings-18.json"        # listas das variações e tempos
SAIDAS = AQUI.parents[1] / "outputs"
FUNDO = 100                                        # até onde o diagnóstico olha
N_BOOT, SEMENTE = 2000, 20261105
BASE, RR20 = "qwen3", "qwen3+rerank"
VARIACOES = {"qwen3+rerank50": "A", "qwen3+max2doc": "B", "qwen3 pt+en": "C"}
ORDEM = [BASE, RR20, *VARIACOES]
MAX_POR_DOC = 2


# ---------------------------------------------------------------- gabaritos e listas
def gabaritos() -> tuple[dict[str, list[dict]], str]:
    """{'opus': [...], 'rascunho': [...]} só com perguntas que têm trecho certo, e o sha256 do arquivo do Opus."""
    ras = json.loads((AQUI / "gabarito_rascunho.json").read_text(encoding="utf-8"))["itens"]
    novos = {q["n"]: set(q["marcados_pelos_dois"]) for q in
             json.loads((AQUI / "gabarito_rascunho_novos.json").read_text(encoding="utf-8"))["itens"]}
    r = [{"id": f"R{n:02d}", "pergunta": i["pergunta"], "tipo": "-",
          "certos": set(i["trechos_relevantes"]) | novos.get(n, set())} for n, i in enumerate(ras, 1)]
    # o mesmo arquivo do commit registrado em OPUS_REF (sha256 conferido em 06/11/2026); lido do disco para rodar fora do git
    bruto = (AQUI.parent / "gabarito" / "gabarito_rascunho_v0.json").read_bytes()
    o = [{"id": i["id"], "pergunta": i["pergunta"], "tipo": i["tipo"], "certos": set(i["trechos_relevantes"])}
         for i in json.loads(bruto)["itens"]]
    return ({"opus": [x for x in o if x["certos"]], "rascunho": [x for x in r if x["certos"]]},
            hashlib.sha256(bruto).hexdigest())


def traducoes() -> dict[str, str]:
    return json.loads((AQUI / "perguntas_en.json").read_text(encoding="utf-8"))["perguntas"]


def chunks_por_id() -> dict[str, dict]:
    from ingestao import carregar_chunks
    return {c["chunk_id"]: c for c in carregar_chunks()}


def listas_qwen3(perguntas: list[str], lingua: str) -> dict[str, list[str]]:
    """Os FUNDO primeiros do Qwen3 para cada pergunta. Guarda em cache/ para não buscar de novo."""
    guardado = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    feito = guardado.setdefault(lingua, {})
    faltam = [p for p in perguntas if p not in feito]
    if faltam:
        import consultar
        for p in faltam:
            feito[p] = [cid for cid, _ in consultar.ranking(p, "qwen3", FUNDO)]
        CACHE.write_text(json.dumps(guardado, ensure_ascii=False), encoding="utf-8")
    return {p: feito[p] for p in perguntas}


def doc(cid: str) -> str:
    return cid.split("#")[0]


def limitar_por_doc(lista: list[str], maximo: int = MAX_POR_DOC) -> list[str]:
    """Anda na lista e pula o trecho cujo documento já apareceu `maximo` vezes."""
    visto, saida = Counter(), []
    for cid in lista:
        if visto[doc(cid)] < maximo:
            visto[doc(cid)] += 1
            saida.append(cid)
    return saida


def media(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)


def mediana(xs) -> float:
    s = sorted(xs)
    return s[len(s) // 2]


# ---------------------------------------------------------------- 1. diagnóstico
def diagnostico() -> None:
    por = chunks_por_id()
    gabs, sha = gabaritos()
    L = ["DIAGNÓSTICO DA BUSCA (Qwen3 sozinho) NOS DOIS GABARITOS DE MODELO. Sem conferência humana. Nenhum modelo treinado.",
         "Técnica: contagem sobre as listas do Qwen3-Embedding (modelo pronto) até a posição 100.",
         f"Gabarito do Opus lido de {OPUS_REF.split(':')[0]}, sha256 {sha[:16]}. Rascunho: ampliado com os trechos novos.",
         f"Acaso: 5 de {len(por)} trechos = recall@5 de {5 / len(por):.3f} (fórmula, para pergunta com 1 trecho certo).", ""]
    for nome, itens in gabs.items():
        R = listas_qwen3([i["pergunta"] for i in itens], "pt")
        ranks = [R[i["pergunta"]] for i in itens]
        certos = [i["certos"] for i in itens]
        n = len(itens)
        L += [f"===== {nome.upper()}: {n} perguntas, {sum(map(len, certos))} trechos certos "
              f"({media(map(len, certos)):.1f} por pergunta) =====", "",
              "1. Até onde é preciso olhar para achar o que é certo",
              f"{'primeiros':>10s}{'recall':>8s}{'perguntas com ao menos 1 certo':>33s}"]
        for k in (5, 10, 20, 50, 100):
            rec = media(len(c & set(r[:k])) / len(c) for r, c in zip(ranks, certos))
            L.append(f"{k:10d}{rec:8.2f}{sum(bool(c & set(r[:k])) for r, c in zip(ranks, certos)):22d} de {n}")
        if nome == "opus":
            L += ["", "2. Por tipo de pergunta",
                  f"{'tipo':12s}{'n':>4s}{'certos/perg.':>14s}{'recall@5':>10s}{'recall@20':>11s}{'posição do 1º certo (mediana)':>32s}"]
            tipos = defaultdict(list)
            for i, r in zip(itens, ranks):
                pos = next((p + 1 for p, c in enumerate(r) if c in i["certos"]), FUNDO + 1)
                tipos[i["tipo"]].append((len(i["certos"]), len(i["certos"] & set(r[:5])) / len(i["certos"]),
                                         len(i["certos"] & set(r[:20])) / len(i["certos"]), pos))
            for t, v in tipos.items():
                L.append(f"{t:12s}{len(v):4d}{media(x[0] for x in v):14.1f}{media(x[1] for x in v):10.2f}"
                         f"{media(x[2] for x in v):11.2f}{mediana([x[3] for x in v]):32d}")
            L.append(f"(posição {FUNDO + 1} = não apareceu entre os {FUNDO} primeiros)")
        top5 = [c for r in ranks for c in r[:5]]
        L += ["", "3. Repetição entre os 5 primeiros",
              f"documentos diferentes entre os 5 primeiros, em média: {media(len({doc(c) for c in r[:5]}) for r in ranks):.2f}"]
        pares = Counter()
        com_vizinho = 0
        for r, c in zip(ranks, certos):
            s = sorted((doc(x), int(x.split("#")[1]), x) for x in r[:5])
            viz = [(a[2], b[2]) for a, b in zip(s, s[1:]) if a[0] == b[0] and b[1] - a[1] == 1]
            com_vizinho += bool(viz)
            for a, b in viz:
                pares[(a in c) + (b in c)] += 1
        L += [f"perguntas com trechos vizinhos (um logo depois do outro no documento) entre os 5 primeiros: {com_vizinho} de {n}",
              f"pares de vizinhos: {sum(pares.values())}; os dois certos: {pares[2]}; um certo: {pares[1]}; nenhum certo: {pares[0]}",
              f"cartilha da ABDA (aviso: não usar como evidência de eficácia) entre os 5 primeiros: "
              f"{sum(c.startswith('ABDA') for c in top5)} de {len(top5)}; marcada como certa no gabarito: "
              f"{sum(x.startswith('ABDA') for c in certos for x in c)} de {sum(map(len, certos))} trechos certos",
              "", "4. Idioma",
              f"inglês na base: {sum(c['idioma'] == 'en' for c in por.values())} de {len(por)}",
              f"inglês entre os trechos certos: {sum(por[x]['idioma'] == 'en' for c in certos for x in c)} de {sum(map(len, certos))}",
              f"inglês entre os 5 primeiros: {sum(por[c]['idioma'] == 'en' for c in top5)} de {len(top5)}"]
        fora = [x for r, c in zip(ranks, certos) for x in c - set(r[:5])]
        L += [f"trechos certos que ficaram fora dos 5 primeiros: {len(fora)}; em inglês: {sum(por[x]['idioma'] == 'en' for x in fora)}",
              "", "5. Teto de cada variação (o máximo que ela pode dar, contado antes de rodar)",
              f"A  o reranker só reordena o que recebe: recall entre os 20 primeiros "
              f"{media(len(c & set(r[:20])) / len(c) for r, c in zip(ranks, certos)):.2f}; entre os 50 primeiros "
              f"{media(len(c & set(r[:50])) / len(c) for r, c in zip(ranks, certos)):.2f}"]
        livre = media(min(5, len(c)) / len(c) for c in certos)
        preso = media(min(5, sum(min(MAX_POR_DOC, v) for v in Counter(map(doc, c)).values())) / len(c) for c in certos)
        tres = sum(max(Counter(map(doc, c)).values()) > MAX_POR_DOC for c in certos)
        L += [f"B  teto do recall@5 sem limite {livre:.2f}; com no máximo {MAX_POR_DOC} por documento {preso:.2f}; "
              f"perguntas com 3 ou mais trechos certos no mesmo documento: {tres} de {n}",
              "C  ver o item 4: trechos certos em inglês fora dos 5 primeiros", ""]
    # corte de tokens: quanto de cada trecho o modelo deixa de ler
    import embeddings as emb
    from transformers import AutoTokenizer
    textos = [c["texto_indexado"] for c in por.values()]
    L.append("6. Trechos que passam do limite de leitura de cada modelo (contagem de tokens, com a etiqueta)")
    for ap, cfg in emb.MODELOS_DENSOS.items():
        tk = AutoTokenizer.from_pretrained(cfg["nome"])
        n_tok = sorted(len(tk(t, add_special_tokens=True)["input_ids"]) for t in textos)
        L.append(f"{ap:6s} limite {cfg['max_tokens']:5d}: cortados {sum(x > cfg['max_tokens'] for x in n_tok)} de {len(n_tok)}; "
                 f"mediana {n_tok[len(n_tok) // 2]} tokens, maior {n_tok[-1]}")
    destino = SAIDAS / "17-diagnostico-busca.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 2. as variações
def ranquear() -> None:
    import consultar
    import embeddings as emb
    gabs, _ = gabaritos()
    en = traducoes()
    aquece = [cid for cid, _ in consultar.ranking("aquecimento", "qwen3", 20)]
    consultar.reranquear("aquecimento", aquece)             # carrega os dois modelos fora do cronômetro
    saida = {}
    for nome, itens in gabs.items():
        rank = {m: [] for m in ORDEM}
        ms = {m: [] for m in ORDEM}
        for it in itens:
            p = it["pergunta"]

            def cronometra(f):
                t = time.perf_counter()
                r = f()
                return r, 1000 * (time.perf_counter() - t)

            pt, t_pt = cronometra(lambda: [cid for cid, _ in consultar.ranking(p, "qwen3", FUNDO)])
            ing, t_en = cronometra(lambda: [cid for cid, _ in consultar.ranking(en[it["id"]], "qwen3", FUNDO)])
            r20, t_20 = cronometra(lambda: [cid for cid, _ in consultar.reranquear(p, pt[:20])])
            r50, t_50 = cronometra(lambda: [cid for cid, _ in consultar.reranquear(p, pt[:50])])
            listas = {BASE: (pt, t_pt), RR20: (r20, t_pt + t_20), "qwen3+rerank50": (r50, t_pt + t_50),
                      "qwen3+max2doc": (limitar_por_doc(pt), t_pt),
                      "qwen3 pt+en": ([cid for cid, _ in emb.rrf([pt[:50], ing[:50]], k=60)], t_pt + t_en)}
            for m, (lista, t) in listas.items():
                rank[m].append(lista[:10])
                ms[m].append(t)
        saida[nome] = {"ids": [it["id"] for it in itens], "rank": rank, "ms_mediana": {m: mediana(v) for m, v in ms.items()}}
        print(nome, "pronto:", len(itens), "perguntas")
    RANK.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")


def diferenca(a: list[float], b: list[float]) -> tuple[float, float, float, int, int, int]:
    """a menos b, pergunta a pergunta. O sorteio reamostra perguntas, mantendo os dois métodos juntos."""
    d = [x - y for x, y in zip(a, b)]
    rnd = random.Random(SEMENTE)
    medias = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(N_BOOT))
    return (sum(d) / len(d), medias[int(.025 * N_BOOT)], medias[int(.975 * N_BOOT) - 1],
            sum(x > 1e-9 for x in d), sum(abs(x) <= 1e-9 for x in d), sum(x < -1e-9 for x in d))


def julgados_rascunho() -> dict[int, set[str]] | None:
    """Trechos que os dois juízes do rascunho chegaram a ler, por pergunta. Fica em cache/, fora do Git."""
    a, b = AQUI / "cache" / "candidatos.json", AQUI / "cache" / "candidatos-novos.json"
    if not (a.exists() and b.exists()):
        return None
    visto = defaultdict(set)
    for n, q in enumerate(json.loads(a.read_text(encoding="utf-8")), 1):
        visto[n] |= {c["chunk_id"] for c in q["candidatos"]}
    for q in json.loads(b.read_text(encoding="utf-8")):
        visto[q["n"]] |= {c["chunk_id"] for c in q["candidatos"]}
    return visto


def medir() -> None:
    por = chunks_por_id()
    gabs, sha = gabaritos()
    dados = json.loads(RANK.read_text(encoding="utf-8"))
    julg = julgados_rascunho()
    L = ["TRÊS VARIAÇÕES BARATAS DA BUSCA, NOS DOIS GABARITOS DE MODELO. Sem conferência humana. Nenhum modelo treinado.",
         "A qwen3+rerank50: reranker sobre os 50 primeiros do Qwen3. B qwen3+max2doc: no máximo 2 trechos por documento.",
         "C qwen3 pt+en: busca com a pergunta em português e em inglês, juntas pela posição (RRF, k=60).",
         f"Técnica: modelos prontos, contagem e sorteio. Bootstrap de 95%: {N_BOOT} sorteios de perguntas, semente {SEMENTE}.",
         f"Gabarito do Opus: sha256 {sha[:16]}. Acaso no recall@5: {5 / len(por):.3f} (5 de {len(por)} trechos).", ""]
    dif = {}
    for nome, itens in gabs.items():
        d = dados[nome]
        assert d["ids"] == [i["id"] for i in itens], "as listas guardadas não são destas perguntas: rode `ranquear`"
        certos = [i["certos"] for i in itens]
        n = len(itens)
        por_m = {m: [avaliar.metricas_pergunta(r, c) for r, c in zip(d["rank"][m], certos)] for m in ORDEM}
        L += [f"===== {nome.upper()}: {n} perguntas; uma pergunta vale {100 / n:.1f} pontos =====",
              f"{'método':16s}{'recall@5':>20s}{'recall@10':>11s}{'MRR':>20s}{'ao menos 1 certo nos 5':>24s}{'ms':>7s}"]
        for m in ORDEM:
            def c(k):
                v = [p[k] for p in por_m[m]]
                lo, hi = avaliar.bootstrap(v)
                return f"{media(v):.2f} [{lo:.2f}-{hi:.2f}]"
            acerto = sum(bool(cs & set(r[:5])) for r, cs in zip(d["rank"][m], certos))
            L.append(f"{m:16s}{c('recall@5'):>20s}{media(p['recall@10'] for p in por_m[m]):11.2f}{c('MRR'):>20s}"
                     f"{acerto:>17d} de {n}{d['ms_mediana'][m]:7.0f}")
        L += ["", "Diferença pareada (primeiro menos segundo), IC 95%, perguntas em que ganhou/empatou/perdeu:"]
        for a, b in [(m, BASE) for m in ORDEM[1:]] + [("qwen3+rerank50", RR20)]:
            for k in ("recall@5", "MRR"):
                x = diferenca([p[k] for p in por_m[a]], [p[k] for p in por_m[b]])
                dif[(nome, a, b, k)] = x
                L.append(f"{a:15s} - {b:13s} {k:9s} {x[0]:+.2f} [{x[1]:+.2f} a {x[2]:+.2f}]  {x[3]}/{x[4]}/{x[5]}")
        L += ["", f"{'método':16s}{'inglês nos 5':>14s}{'ABDA nos 5':>12s}{'documentos nos 5':>18s}{'não julgados nos 5':>20s}"]
        nj = {}
        for m in ORDEM:
            top = [x for r in d["rank"][m] for x in r[:5]]
            if nome == "rascunho" and julg is not None:
                nj[m] = sum(x not in julg[int(i["id"][1:])] for i, r in zip(itens, d["rank"][m]) for x in r[:5])
            L.append(f"{m:16s}{sum(por[x]['idioma'] == 'en' for x in top):14d}{sum(x.startswith('ABDA') for x in top):12d}"
                     f"{media(len({doc(x) for x in r[:5]}) for r in d['rank'][m]):18.2f}"
                     f"{(str(nj[m]) + ' de ' + str(len(top))) if m in nj else '-':>20s}")
        L.append("")
        if nome == "opus":
            so_en = [j for j, cs in enumerate(certos) if all(por[x]["idioma"] == "en" for x in cs)]
            resto = [j for j in range(n) if j not in so_en]
            L += ["Recall@5 por recorte (todos os recortes que o gabarito permite):",
                  f"{'recorte':28s}" + "".join(f"{m:>16s}" for m in ORDEM)]
            recortes = [(f"certo só em inglês (n={len(so_en)})", so_en), (f"algum certo em português (n={len(resto)})", resto)]
            for t in dict.fromkeys(i["tipo"] for i in itens):
                ix = [j for j, i in enumerate(itens) if i["tipo"] == t]
                recortes.append((f"tipo {t} (n={len(ix)})", ix))
            for rot, ix in recortes:
                L.append(f"{rot:28s}" + "".join(f"{media(por_m[m][j]['recall@5'] for j in ix):16.2f}" for m in ORDEM))
            L.append("")
        if nome == "rascunho":
            L += ["CRITÉRIO (escrito antes de rodar): passa a variação cujo recall@5 menos o do Qwen3 sozinho tem o intervalo todo",
                  "acima de zero no gabarito do Opus e não tem o intervalo todo abaixo de zero no rascunho. O rascunho só conta",
                  "se até 10% das vagas dos 5 primeiros forem de trecho nunca julgado. Passar não muda o padrão: vira candidata",
                  "a conferir no gabarito revisado por pessoas."]
            for m, letra in VARIACOES.items():
                o, r = dif[("opus", m, BASE, "recall@5")], dif[("rascunho", m, BASE, "recall@5")]
                comparavel = m in nj and nj[m] <= 0.10 * 5 * n
                if o[1] <= 0:
                    v = "NÃO PASSA (no Opus o intervalo encosta ou passa pelo zero)"
                elif not comparavel:
                    v = "PASSA NO OPUS; rascunho não comparável"
                elif r[2] < 0:
                    v = "NÃO PASSA (piora no rascunho)"
                else:
                    v = "PASSA"
                L.append(f"{letra} {m:15s} Opus {o[0]:+.2f} [{o[1]:+.2f} a {o[2]:+.2f}]; rascunho {r[0]:+.2f} [{r[1]:+.2f} a {r[2]:+.2f}], "
                         f"não julgados {nj.get(m, '-')} de {5 * n}: {v}")
            x = dif[("opus", "qwen3+rerank50", RR20, "recall@5")]
            L.append(f"Trocar 20 por 50 candidatos no reranker (Opus): {x[0]:+.2f} [{x[1]:+.2f} a {x[2]:+.2f}]: "
                     f"{'vale a troca' if x[1] > 0 else 'não se distingue de 20'}")
    destino = SAIDAS / "18-variacoes-busca.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 3. a combinação de A com C
COMBINA = "pt+en+rerank50"                          # D: a lista junta de C, relida pelo reranker de A


def lista_junta(pt: list[str], ing: list[str]) -> list[str]:
    """A lista da variação C: os 50 primeiros de cada busca, juntos pela posição (RRF, k=60)."""
    import embeddings as emb
    return [cid for cid, _ in emb.rrf([pt[:50], ing[:50]], k=60)]


def teto() -> None:
    """Conta, sem rodar o reranker, o máximo que a combinação pode dar: o reranker só reordena o que recebe."""
    gabs, sha = gabaritos()
    en = traducoes()
    julg = julgados_rascunho()
    L = ["TETO DA COMBINAÇÃO (D): reranker sobre os 50 primeiros da lista junta (português + inglês). Contado ANTES de rodar.",
         "Técnica: contagem sobre as listas do Qwen3-Embedding (modelo pronto) já guardadas. Nenhum modelo treinado, e o",
         "reranker não foi chamado. O reranker só reordena o que recebe: o recall entre os 50 que ele lê é o teto dele.",
         f"Gabarito do Opus: sha256 {sha[:16]}. Os dois gabaritos são de modelo, sem conferência humana.", ""]
    for nome, itens in gabs.items():
        pt = listas_qwen3([i["pergunta"] for i in itens], "pt")
        ing = listas_qwen3([en[i["id"]] for i in itens], "en")
        certos = [i["certos"] for i in itens]
        so_pt = [pt[i["pergunta"]] for i in itens]
        junta = [lista_junta(pt[i["pergunta"]], ing[en[i["id"]]]) for i in itens]
        n = len(itens)

        def rec(listas, k):
            return media(len(c & set(r[:k])) / len(c) for r, c in zip(listas, certos))

        L += [f"===== {nome.upper()}: {n} perguntas, {sum(map(len, certos))} trechos certos =====",
              f"{'o reranker lê':44s}{'recall (teto)':>14s}{'perguntas com ao menos 1 certo':>33s}",
              f"{'A: 50 primeiros da busca em português':44s}{rec(so_pt, 50):14.2f}"
              f"{sum(bool(c & set(r[:50])) for r, c in zip(so_pt, certos)):22d} de {n}",
              f"{'D: 50 primeiros da lista junta':44s}{rec(junta, 50):14.2f}"
              f"{sum(bool(c & set(r[:50])) for r, c in zip(junta, certos)):22d} de {n}",
              f"{'(lista junta inteira, até 100 trechos)':44s}{rec(junta, 100):14.2f}",
              f"tamanho da lista junta: mediana {mediana([len(r) for r in junta])} trechos "
              f"(50 = as duas buscas trouxeram os mesmos; 100 = nenhum em comum)"]
        ganha = sum(len(c & set(j[:50])) > len(c & set(p[:50])) for j, p, c in zip(junta, so_pt, certos))
        perde = sum(len(c & set(j[:50])) < len(c & set(p[:50])) for j, p, c in zip(junta, so_pt, certos))
        L.append(f"perguntas em que os 50 da lista junta têm mais trechos certos que os 50 do português: {ganha}; menos: {perde}; "
                 f"igual: {n - ganha - perde}")
        if nome == "rascunho" and julg is not None:
            for rot, listas in (("A", so_pt), ("D", junta)):
                tot = sum(len(r[:50]) for r in listas)
                nj = sum(x not in julg[int(i["id"][1:])] for i, r in zip(itens, listas) for x in r[:50])
                L.append(f"trechos nunca julgados entre os 50 que o reranker lê em {rot}: {nj} de {tot} ({100 * nj / tot:.0f}%)")
        L.append("")
    destino = SAIDAS / "19-teto-combinacao.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


RANK_D = AQUI / "cache" / "rankings-20.json"       # listas da combinação D e tempos
ORDEM_D = [BASE, "qwen3+rerank50", "qwen3 pt+en", COMBINA]
LETRA = {BASE: "Qwen3 sozinho", "qwen3+rerank50": "A", "qwen3 pt+en": "C", COMBINA: "D"}


def arquivo_d(rep: int) -> Path:
    return RANK_D if rep == 1 else RANK_D.with_name(f"rankings-20-rep{rep}.json")


def combinar(rep: int = 1) -> None:
    """Roda D: as duas buscas, a junção pela posição e o reranker sobre os 50 primeiros da lista junta.
    Roda A de novo na mesma sessão, para o tempo das duas ser comparável e para conferir que A repete.
    rep > 1 grava num arquivo à parte: serve para ver se o resultado repete de um processo para outro."""
    import consultar
    gabs, _ = gabaritos()
    en = traducoes()
    antes = json.loads(RANK.read_text(encoding="utf-8"))
    aquece = [cid for cid, _ in consultar.ranking("aquecimento", "qwen3", 20)]
    consultar.reranquear("aquecimento", aquece)             # carrega os dois modelos fora do cronômetro
    saida = {}
    for nome, itens in gabs.items():
        listas, ms_d, ms_a, a_repete = [], [], [], 0
        for j, it in enumerate(itens):
            p = it["pergunta"]

            def cronometra(f):
                t = time.perf_counter()
                r = f()
                return r, 1000 * (time.perf_counter() - t)

            pt, t_pt = cronometra(lambda: [cid for cid, _ in consultar.ranking(p, "qwen3", FUNDO)])       # busca em português
            ing, t_en = cronometra(lambda: [cid for cid, _ in consultar.ranking(en[it["id"]], "qwen3", FUNDO)])  # busca em inglês
            junta, t_j = cronometra(lambda: lista_junta(pt, ing))                                        # a lista da variação C
            d, t_d = cronometra(lambda: [cid for cid, _ in consultar.reranquear(p, junta[:50])])          # reranker lê 50 da lista junta
            a, t_a = cronometra(lambda: [cid for cid, _ in consultar.reranquear(p, pt[:50])])             # A, de novo, para comparar tempo
            listas.append(d[:10])
            ms_d.append(t_pt + t_en + t_j + t_d)
            ms_a.append(t_pt + t_a)
            a_repete += a[:10] == antes[nome]["rank"]["qwen3+rerank50"][j]
        saida[nome] = {"ids": [it["id"] for it in itens], "rank": listas, "ms_mediana": mediana(ms_d),
                       "ms_mediana_A": mediana(ms_a), "A_repete": a_repete}
        print(nome, "pronto:", len(itens), "perguntas; A repetiu a lista guardada em", a_repete)
    arquivo_d(rep).write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")


def medir_combinacao() -> None:
    por = chunks_por_id()
    gabs, sha = gabaritos()
    antes = json.loads(RANK.read_text(encoding="utf-8"))
    novo = json.loads(RANK_D.read_text(encoding="utf-8"))
    julg = julgados_rascunho()
    L = ["COMBINAÇÃO D: pergunta em português e em inglês (RRF, k=60) e reranker sobre os 50 primeiros da lista junta.",
         "Comparada com o Qwen3 sozinho, com A (reranker sobre 50 da busca em português) e com C (pt+en, sem reranker).",
         "Gabaritos de modelo, sem conferência humana. Nenhum modelo treinado: modelos prontos, contagem e sorteio.",
         f"Bootstrap de 95%: {N_BOOT} sorteios de perguntas, semente {SEMENTE}. Gabarito do Opus: sha256 {sha[:16]}.",
         f"Acaso no recall@5: {5 / len(por):.3f} (5 de {len(por)} trechos).", ""]
    dif, nj_d, n_ras = {}, None, 0
    for nome, itens in gabs.items():
        a, d = antes[nome], novo[nome]
        assert a["ids"] == d["ids"] == [i["id"] for i in itens], "as listas guardadas não são destas perguntas"
        rank = {m: a["rank"][m] for m in ORDEM_D[:-1]} | {COMBINA: d["rank"]}
        ms = {m: a["ms_mediana"][m] for m in ORDEM_D[:-1]} | {COMBINA: d["ms_mediana"]}
        certos = [i["certos"] for i in itens]
        n = len(itens)
        por_m = {m: [avaliar.metricas_pergunta(r, c) for r, c in zip(rank[m], certos)] for m in ORDEM_D}
        L += [f"===== {nome.upper()}: {n} perguntas; uma pergunta vale {100 / n:.1f} pontos =====",
              f"{'método':16s}{'':4s}{'recall@5':>20s}{'recall@10':>11s}{'MRR':>20s}{'ao menos 1 certo nos 5':>24s}{'ms':>7s}"]
        for m in ORDEM_D:
            def c(k):
                v = [p[k] for p in por_m[m]]
                lo, hi = avaliar.bootstrap(v)
                return f"{media(v):.2f} [{lo:.2f}-{hi:.2f}]"
            acerto = sum(bool(cs & set(r[:5])) for r, cs in zip(rank[m], certos))
            L.append(f"{m:16s}{LETRA[m][:1] if m != BASE else '':4s}{c('recall@5'):>20s}{media(p['recall@10'] for p in por_m[m]):11.2f}"
                     f"{c('MRR'):>20s}{acerto:>17d} de {n}{ms[m]:7.0f}")
        L += [f"(tempo de A medido de novo na mesma sessão de D: {d['ms_mediana_A']:.0f} ms; "
              f"A repetiu a lista guardada em {d['A_repete']} de {n} perguntas)",
              "", "Diferença pareada (primeiro menos segundo), IC 95%, perguntas em que ganhou/empatou/perdeu:"]
        for b in ORDEM_D[:-1]:
            for k in ("recall@5", "MRR"):
                x = diferenca([p[k] for p in por_m[COMBINA]], [p[k] for p in por_m[b]])
                dif[(nome, b, k)] = x
                L.append(f"{COMBINA:15s} - {b:15s} {k:9s} {x[0]:+.2f} [{x[1]:+.2f} a {x[2]:+.2f}]  {x[3]}/{x[4]}/{x[5]}")
        L += ["", f"{'método':16s}{'inglês nos 5':>14s}{'ABDA nos 5':>12s}{'documentos nos 5':>18s}{'não julgados nos 5':>20s}"]
        for m in ORDEM_D:
            top = [x for r in rank[m] for x in r[:5]]
            nj = None
            if nome == "rascunho" and julg is not None:
                nj = sum(x not in julg[int(i["id"][1:])] for i, r in zip(itens, rank[m]) for x in r[:5])
                if m == COMBINA:
                    nj_d, n_ras = nj, n
            L.append(f"{m:16s}{sum(por[x]['idioma'] == 'en' for x in top):14d}{sum(x.startswith('ABDA') for x in top):12d}"
                     f"{media(len({doc(x) for x in r[:5]}) for r in rank[m]):18.2f}"
                     f"{(str(nj) + ' de ' + str(len(top))) if nj is not None else '-':>20s}")
        iguais = media(len(set(x[:5]) & set(y[:5])) for x, y in zip(rank[COMBINA], rank["qwen3+rerank50"]))
        L += [f"trechos em comum entre os 5 primeiros de D e os 5 primeiros de A, em média: {iguais:.2f} de 5", ""]
        if nome == "opus":
            so_en = [j for j, cs in enumerate(certos) if all(por[x]["idioma"] == "en" for x in cs)]
            resto = [j for j in range(n) if j not in so_en]
            L += ["Recall@5 por recorte (todos os recortes que o gabarito permite; médias de poucas perguntas, sem intervalo):",
                  f"{'recorte':34s}" + "".join(f"{m:>16s}" for m in ORDEM_D)]
            recortes = [(f"certo só em inglês (n={len(so_en)})", so_en), (f"algum certo em português (n={len(resto)})", resto)]
            for t in dict.fromkeys(i["tipo"] for i in itens):
                ix = [j for j, i in enumerate(itens) if i["tipo"] == t]
                recortes.append((f"tipo {t} (n={len(ix)})", ix))
            for rot, ix in recortes:
                L.append(f"{rot:34s}" + "".join(f"{media(por_m[m][j]['recall@5'] for j in ix):16.2f}" for m in ORDEM_D))
            L.append("")
    reps = [r for r in range(2, 10) if arquivo_d(r).exists()]
    if reps:
        L += [f"REPETIÇÃO: D rodou em {len(reps) + 1} processos separados. A busca do banco (Chroma, HNSW) é aproximada e, lá pela",
              "posição 50, não devolve sempre a mesma lista de um processo para outro (ver outputs/21). O vetor da pergunta é idêntico.",
              f"{'gabarito':10s}{'rodada':>8s}{'recall@5 de D':>15s}{'MRR de D':>10s}{'5 primeiros iguais aos da rodada 1':>36s}{'A repetiu a lista guardada':>28s}"]
        for nome, itens in gabs.items():
            certos = [i["certos"] for i in itens]
            um = novo[nome]["rank"]
            for r in [1, *reps]:
                dd = json.loads(arquivo_d(r).read_text(encoding="utf-8"))[nome]
                mm = [avaliar.metricas_pergunta(x, c) for x, c in zip(dd["rank"], certos)]
                L.append(f"{nome:10s}{r:8d}{media(q['recall@5'] for q in mm):15.4f}{media(q['MRR'] for q in mm):10.4f}"
                         f"{sum(a[:5] == b[:5] for a, b in zip(dd['rank'], um)):29d} de {len(itens)}"
                         f"{dd['A_repete']:21d} de {len(itens)}")
        L.append("")
    x = dif[("opus", "qwen3+rerank50", "recall@5")]
    if x[1] > 0:
        v = "D VALE COMO CANDIDATA NO LUGAR DE A (intervalo todo acima de zero)"
    elif x[2] < 0:
        v = "D ATRAPALHA (intervalo todo abaixo de zero)"
    else:
        v = "D NÃO SE DISTINGUE DE A (o intervalo encosta ou passa pelo zero): fica como candidata a mais simples, A"
    L += ["CRITÉRIO (escrito antes de rodar): D só vale como candidata no lugar de A se o recall@5 de D menos o de A tiver o",
          "intervalo todo acima de zero no gabarito do Opus. Se encostar no zero, fica A, que é mais simples. Passar não muda o padrão.",
          f"D - A no Opus: {x[0]:+.2f} [{x[1]:+.2f} a {x[2]:+.2f}], ganhou {x[3]}, empatou {x[4]}, perdeu {x[5]}: {v}"]
    if nj_d is not None:
        r = dif[("rascunho", BASE, "recall@5")]
        if nj_d <= 0.10 * 5 * n_ras:
            estado = "comparável; " + ("piora no rascunho" if r[2] < 0 else "não piora no rascunho")
        else:
            estado = "rascunho não comparável (acima de 10% das vagas com trecho nunca julgado)"
        L.append(f"Rascunho: D - Qwen3 {r[0]:+.2f} [{r[1]:+.2f} a {r[2]:+.2f}], não julgados {nj_d} de {5 * n_ras}: {estado}")
    destino = SAIDAS / "20-combinacao-busca.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def estabilidade() -> None:
    """A busca do banco contra a conta exata do cosseno, pergunta a pergunta. O resultado desta contagem pode mudar
    de uma execução para outra: é justamente isso que ela mede."""
    import numpy as np
    import consultar
    gabs, _ = gabaritos()
    en = traducoes()
    guard = json.loads(CACHE.read_text(encoding="utf-8"))
    modelo = consultar._modelo("qwen3")
    col = consultar._colecao("qwen3")
    tudo = col.get(include=["embeddings"])                        # todos os vetores gravados
    E = np.asarray(tudo["embeddings"], dtype=np.float64)
    E /= np.linalg.norm(E, axis=1, keepdims=True)                 # comprimento 1: o produto vira cosseno
    cortes = (5, 10, 20, 50, 100)
    L = ["ESTABILIDADE DA BUSCA DO BANCO (Chroma, HNSW) CONTRA A CONTA EXATA DO COSSENO. Qwen3, mesmas perguntas dos gabaritos.",
         "Técnica: contagem. Para cada pergunta, a lista que o banco devolve é comparada com a ordem exata (produto do vetor",
         "da pergunta por todos os vetores gravados). Nenhum modelo treinado.",
         f"O índice HNSW é uma busca aproximada: {len(tudo['ids'])} vetores, ef_search 100. ATENÇÃO: esta contagem pode mudar",
         "de uma execução para outra; é isso que ela mede. A coluna 'guardada' é a lista gravada pelo diagnóstico (outputs/17).", "",
         f"{'gabarito':10s}{'língua':>8s}{'n':>4s}" + "".join(f"{'≠ exata nos ' + str(k):>18s}" for k in cortes)
         + f"{'exata = guardada nos 50':>26s}"]
    agora = {}                                                    # a lista do banco nesta execução, por pergunta e língua
    for nome, itens in gabs.items():
        for lingua in ("pt", "en"):
            dif = Counter()
            igual_guard = 0
            for it in itens:
                q = it["pergunta"] if lingua == "pt" else en[it["id"]]
                v = np.asarray(modelo.vetor_pergunta(q), dtype=np.float64).ravel()
                exata = [tudo["ids"][j] for j in np.argsort(-(E @ (v / np.linalg.norm(v))), kind="stable")[:FUNDO]]
                banco = [cid for cid, _ in consultar.ranking(q, "qwen3", FUNDO)]
                agora[(nome, lingua, it["id"])] = banco
                for k in cortes:
                    dif[k] += banco[:k] != exata[:k]
                igual_guard += exata[:50] == guard[lingua][q][:50]
            L.append(f"{nome:10s}{lingua:>8s}{len(itens):4d}" + "".join(f"{dif[k]:18d}" for k in cortes) + f"{igual_guard:20d} de {len(itens)}")
    L += ["", "Leitura: '≠ exata nos 50' = perguntas em que os 50 primeiros do banco não são os 50 primeiros da conta exata.", "",
          "Listas que não usam o reranker, refeitas agora e comparadas com as guardadas em cache/rankings-18.json (outputs/18):"]
    antes = json.loads(RANK.read_text(encoding="utf-8"))
    for nome, itens in gabs.items():
        base = sum(agora[(nome, "pt", it["id"])][:10] == antes[nome]["rank"][BASE][j] for j, it in enumerate(itens))
        c5 = sum(lista_junta(agora[(nome, "pt", it["id"])], agora[(nome, "en", it["id"])])[:5]
                 == antes[nome]["rank"]["qwen3 pt+en"][j][:5] for j, it in enumerate(itens))
        c10 = sum(lista_junta(agora[(nome, "pt", it["id"])], agora[(nome, "en", it["id"])])[:10]
                  == antes[nome]["rank"]["qwen3 pt+en"][j] for j, it in enumerate(itens))
        L.append(f"{nome:10s} Qwen3 sozinho, 10 primeiros iguais: {base} de {len(itens)} | C (pt+en), 5 primeiros iguais: {c5} de {len(itens)}; "
                 f"10 primeiros iguais: {c10} de {len(itens)}")
    destino = SAIDAS / "21-estabilidade-busca.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 4. a mesma pergunta no pgvector
CORTES = (5, 10, 20, 50, 100)


def arquivo_pg(rep: int) -> Path:
    return AQUI / "cache" / f"pg-listas-rep{rep}.json"


def estabilidade_pg(rep: int) -> None:
    """Uma execução: para cada pergunta, a lista do pgvector como o pacote pede, a lista com o índice HNSW forçado
    e a ordem exata do cosseno. Só consultas de leitura; os SET valem para a sessão e não mudam o banco."""
    import numpy as np
    import psycopg
    from pgvector.psycopg import register_vector
    import banco_pg as bp
    import consultar

    def conexao():
        con = psycopg.connect(bp.DSN, autocommit=True)            # sem CREATE EXTENSION: aqui nada é escrito
        register_vector(con)
        return con

    hoje, forcado = conexao(), conexao()
    forcado.execute("SET enable_seqscan = off")                    # obriga o plano a passar pelo índice HNSW
    gabs, _ = gabaritos()
    en = traducoes()
    modelo = consultar._modelo("qwen3")
    linhas = hoje.execute(f"SELECT chunk_id, vec_qwen3 FROM {bp.TABELA} ORDER BY chunk_id").fetchall()
    ids = [r[0] for r in linhas]
    E = np.asarray([r[1] for r in linhas], dtype=np.float64)
    E /= np.linalg.norm(E, axis=1, keepdims=True)                 # comprimento 1: o produto vira cosseno

    def plano(con, v) -> str:
        con.execute("SET hnsw.ef_search = 100")
        r = con.execute(f"EXPLAIN SELECT chunk_id FROM {bp.TABELA} WHERE vec_qwen3 IS NOT NULL "
                        f"ORDER BY vec_qwen3 <=> %s LIMIT 100", [v]).fetchall()
        return " > ".join(x[0].strip().split("  (")[0].lstrip("-> ") for x in r if "Sort Key" not in x[0] and "Filter" not in x[0]
                          and "Order By" not in x[0])

    saida = {"versao": {"postgres": hoje.execute("show server_version").fetchone()[0].split(" ")[0],
                        "pgvector": hoje.execute("select extversion from pg_extension where extname='vector'").fetchone()[0]},
             "n_vetores": len(ids), "plano": {}, "listas": {}}
    for nome, itens in gabs.items():
        saida["listas"][nome] = {}
        for lingua in ("pt", "en"):
            d = {}
            for it in itens:
                q = it["pergunta"] if lingua == "pt" else en[it["id"]]
                v = modelo.vetor_pergunta(q)
                v32 = np.asarray(v, dtype=np.float32)
                if not saida["plano"]:
                    saida["plano"] = {"hoje": plano(hoje, v32), "forcado": plano(forcado, v32)}
                sim = E @ (np.asarray(v, dtype=np.float64).ravel() / np.linalg.norm(v))
                d[it["id"]] = {"hoje": [c for c, _ in bp.buscar_denso(hoje, v, "qwen3", FUNDO)],        # como o pacote busca
                               "forcado": [c for c, _ in bp.buscar_denso(forcado, v, "qwen3", FUNDO)],  # com o índice
                               "exata": [ids[j] for j in np.argsort(-sim, kind="stable")[:FUNDO]]}      # a conta à parte
            saida["listas"][nome][lingua] = d
        print(nome, "pronto")
    arquivo_pg(rep).write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print("planos:", saida["plano"])


def medir_estabilidade_pg() -> None:
    reps = [r for r in range(1, 10) if arquivo_pg(r).exists()]
    dados = {r: json.loads(arquivo_pg(r).read_text(encoding="utf-8")) for r in reps}
    um = dados[reps[0]]
    L = ["ESTABILIDADE DA BUSCA DO PGVECTOR CONTRA A CONTA EXATA DO COSSENO. Qwen3, mesmas perguntas dos gabaritos, pt e en.",
         "Técnica: contagem. Nenhum modelo treinado. O pgvector está na VPS e foi lido por túnel, só com consultas de leitura;",
         "o vetor da pergunta foi calculado no Mac. A conta exata é o produto do vetor da pergunta por todos os vetores da tabela.",
         f"PostgreSQL {um['versao']['postgres']}, pgvector {um['versao']['pgvector']}, {um['n_vetores']} vetores, hnsw.ef_search 100 (o que o pacote usa).",
         f"Plano da busca como o pacote faz hoje: {um['plano']['hoje']}",
         f"Plano com o índice forçado (SET enable_seqscan = off, só na sessão da medida): {um['plano']['forcado']}",
         f"Execuções em processos separados: {len(reps)}.", ""]
    total = {}
    for modo, rotulo in (("hoje", "COMO O PACOTE BUSCA HOJE"), ("forcado", "COM O ÍNDICE HNSW FORÇADO")):
        L += [f"===== {rotulo}: listas diferentes da conta exata (execução 1) =====",
              f"{'gabarito':10s}{'língua':>8s}{'n':>5s}" + "".join(f"{'nos ' + str(k):>19s}" for k in CORTES),
              f"{'':23s}" + "".join(f"{'ordem / conjunto':>19s}" for _ in CORTES)]
        soma_o, soma_c, n_tot, curtas = Counter(), Counter(), 0, 0
        for nome, linguas in um["listas"].items():
            for lingua, d in linguas.items():
                ordem, conj = Counter(), Counter()
                for x in d.values():
                    curtas += len(x[modo]) < FUNDO
                    for k in CORTES:
                        ordem[k] += x[modo][:k] != x["exata"][:k]
                        conj[k] += set(x[modo][:k]) != set(x["exata"][:k])
                L.append(f"{nome:10s}{lingua:>8s}{len(d):5d}" + "".join(f"{str(ordem[k]) + ' / ' + str(conj[k]):>19s}" for k in CORTES))
                soma_o += ordem
                soma_c += conj
                n_tot += len(d)
        L += [f"{'total':10s}{'':>8s}{n_tot:5d}" + "".join(f"{str(soma_o[k]) + ' / ' + str(soma_c[k]):>19s}" for k in CORTES),
              f"(ordem = a lista não é idêntica; conjunto = entrou um trecho diferente. Listas com menos de {FUNDO} trechos: {curtas})", ""]
        total[modo] = (soma_o, soma_c, n_tot)
    L.append("===== REPETE DE UM PROCESSO PARA OUTRO? listas com os 100 primeiros idênticos aos da execução 1 =====")
    repete = {}
    for modo in ("hoje", "forcado", "exata"):
        for r in reps[1:]:
            igual = sum(dados[r]["listas"][nome][lingua][i][modo] == x[modo]
                        for nome, linguas in um["listas"].items() for lingua, d in linguas.items() for i, x in d.items())
            repete[(modo, r)] = igual
            L.append(f"{modo:8s} execução {r}: {igual} de {total['hoje'][2]}")
    n = total["hoje"][2]
    ok_rep = all(repete[("hoje", r)] == n for r in reps[1:]) and len(reps) > 1
    ok_exato = total["hoje"][1][50] == 0
    L += ["", "CRITÉRIO (escrito antes de rodar):",
          f"1. Repete (os mesmos 100 primeiros, na mesma ordem, nas {n} listas, em todas as execuções): {'SIM' if ok_rep else 'NÃO'}",
          f"2. É exato hoje (nenhuma lista com conjunto diferente da conta exata nos 50 primeiros): {'SIM' if ok_exato else 'NÃO'}"]
    destino = SAIDAS / "22-estabilidade-pgvector.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "combinar":
        combinar(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    elif cmd == "estabilidade-pg":
        estabilidade_pg(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        {"diagnostico": diagnostico, "ranquear": ranquear, "medir": medir, "teto": teto,
         "medir-combinacao": medir_combinacao, "estabilidade": estabilidade,
         "medir-estabilidade-pg": medir_estabilidade_pg}[cmd]()
