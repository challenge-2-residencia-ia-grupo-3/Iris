"""O guia de dicas da ABDA ocupa vagas entre os 5 trechos entregues. O que acontece com a busca do Íris sem ele?

    .venv/bin/python medir_sem_abda.py contar   quantas vagas o guia ocupa hoje e quantos trechos dele o gabarito marca (outputs/34)
    .venv/bin/python medir_sem_abda.py notas    nota do reranker para os candidatos que entram no lugar (cache/)
    .venv/bin/python medir_sem_abda.py medir    compara a busca de hoje com as duas variações (outputs/35)

Variações, as duas sobre a busca de hoje (Qwen3 com a pergunta, conta exata do cosseno, reranker sobre 50, entrega 5):
    SEM    o guia fica fora da busca: os 50 candidatos são os 50 primeiros do Qwen3 que não são do guia
    MAX1   o guia continua na busca, mas só o trecho dele mais bem colocado pode ficar entre os 5 entregues

O guia é ABDA-GUIA-PROFESSORES-2012: uma cartilha de dicas para professores, sem estudo que sustente cada dica (na base ela
leva o aviso de uso). O gabarito do Opus marca alguns trechos dela como resposta: tirar o guia tira esses também.

Técnica: nenhum modelo é treinado e nenhum modelo de linguagem é chamado. São dois modelos prontos (Qwen3-Embedding e o
reranker mMiniLM), contagem e sorteio de perguntas (bootstrap). Gabaritos de modelo, sem conferência humana.
Expectativa e critério: GABARITO-RASCUNHO.md, "A busca sem o guia da ABDA", commitados antes de `notas`.
Não altera consultar.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import avaliar            # noqa: E402
import medir_hyde as mh   # noqa: E402  (listas da busca de hoje, conjuntos de perguntas, leitura de arquivos)
import medir_variacoes as mv  # noqa: E402

GUIA = "ABDA-GUIA-PROFESSORES-2012"
NOTAS = AQUI / "cache" / "abda-notas.json"          # fora do Git
SAIDAS = AQUI.parents[1] / "outputs"
N_CAND = mh.N_CAND
BRACOS = {"HOJE": "a busca de hoje", "SEM": "sem o guia na busca", "MAX1": "guia limitado a 1 entre os 5"}
PRATICAS = mh.PRATICAS


def do_guia(cid: str) -> bool:
    return mv.doc(cid) == GUIA


def candidatos_sem(x: dict) -> list[str]:
    """Os 50 primeiros do Qwen3 que não são do guia (a lista guardada vai até a posição 100)."""
    return [c for c in x["antes"]["P"] if not do_guia(c)][:N_CAND]


def limitar_guia(ordenados: list[str], maximo: int = 1) -> list[str]:
    """Anda na lista já ordenada pelo reranker e pula o trecho do guia depois que `maximo` deles já entraram."""
    saida, n = [], 0
    for c in ordenados:
        if do_guia(c):
            if n >= maximo:
                continue
            n += 1
        saida.append(c)
    return saida


def conjuntos() -> dict[str, list[dict]]:
    c = mh.conjuntos()
    return {"opus": c["opus"], "rascunho": c["rascunho"]}


# ---------------------------------------------------------------- 1. contar antes de prever
def contar() -> None:
    por = mv.chunks_por_id()
    guardado = mh.ler(mh.LISTAS)
    guia = sorted(c for c in por if do_guia(c))
    L = ["O GUIA DA ABDA NA BUSCA DE HOJE: O QUE SE CONTA ANTES DE PREVER. Contagem, sem modelo treinado.",
         f"O guia tem {len(guia)} trechos, de {len(por)} na base ({100 * len(guia) / len(por):.1f}%). "
         f"Palavras por trecho: {', '.join(str(por[c]['n_palavras']) for c in guia)}.",
         "Busca de hoje: Qwen3 com a pergunta (conta exata), reranker sobre os 50, entrega 5. Gabaritos de modelo.", ""]
    for nome, itens in conjuntos().items():
        g = guardado[nome]
        for rot, sub in (("todas as perguntas", itens), ("só as 10 práticas", [i for i in itens if i["id"] in PRATICAS])):
            if not sub:
                continue
            certos = sum(len(i["certos"]) for i in sub)
            certos_g = sum(do_guia(c) for i in sub for c in i["certos"])
            ent = [(i, c) for i in sub for c in g[i["id"]]["depois"]["P"][:5]]
            ent_g = [(i, c) for i, c in ent if do_guia(c)]
            ent_g_certo = sum(c in i["certos"] for i, c in ent_g)
            cand_g = sum(do_guia(c) for i in sub for c in g[i["id"]]["antes"]["P"][:N_CAND])
            com = sum(any(do_guia(c) for c in g[i["id"]]["depois"]["P"][:5]) for i in sub)
            # teto sem o guia: trechos certos que não são do guia e estão entre os 50 candidatos sem o guia
            teto = sum(len({c for c in i["certos"] if not do_guia(c)} & set(candidatos_sem(g[i["id"]]))) for i in sub)
            hoje = sum(len(i["certos"] & set(g[i["id"]]["depois"]["P"][:5])) for i in sub)
            L += [f"===== {nome.upper()}, {rot}: {len(sub)} perguntas, {certos} trechos certos =====",
                  f"trechos certos que são do guia: {certos_g} de {certos}",
                  f"vagas entre os 5 entregues ocupadas pelo guia: {len(ent_g)} de {len(ent)} ({100 * len(ent_g) / len(ent):.0f}%); "
                  f"por acaso seriam {100 * len(guia) / len(por):.1f}%. Perguntas com ao menos 1 trecho do guia entregue: {com} de {len(sub)}",
                  f"dessas {len(ent_g)} vagas: {ent_g_certo} são de trecho que o gabarito marca como certo, {len(ent_g) - ent_g_certo} não",
                  f"vagas entre os 50 candidatos ocupadas pelo guia: {cand_g} de {N_CAND * len(sub)}",
                  f"trechos certos entregues hoje: {hoje} de {certos}. Sem o guia, os que ainda podem ser entregues "
                  f"(não são do guia e estão entre os 50): {teto}", ""]
        if nome == "opus":
            L += [f"  {'id':5s}{'certos':>7s}{'certos do guia':>16s}{'guia nos 5':>12s}{'dos quais certos':>18s}{'certos entregues hoje':>23s}"]
            for i in itens:
                if i["id"] in PRATICAS:
                    e5 = g[i["id"]]["depois"]["P"][:5]
                    L.append(f"  {i['id']:5s}{len(i['certos']):7d}{sum(do_guia(c) for c in i['certos']):16d}{sum(do_guia(c) for c in e5):12d}"
                             f"{sum(do_guia(c) and c in i['certos'] for c in e5):18d}{len(i['certos'] & set(e5)):23d}")
            L.append("")
    L += ["Leitura: cada vaga do guia que não é de trecho certo é uma vaga que outro trecho pode ocupar. Cada trecho certo do guia",
          "que hoje é entregue é uma perda garantida ao tirar o guia."]
    (SAIDAS / "34-guia-abda-na-busca.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 2. as notas do reranker
def notas() -> None:
    """Nota do reranker (lendo a pergunta) para a união dos 50 de hoje com os 50 sem o guia. Continua de onde parou."""
    import consultar
    guardado = mh.ler(mh.LISTAS)
    nt = mh.ler(NOTAS, {})
    for nome, itens in conjuntos().items():
        n = nt.setdefault(nome, {})
        for it in itens:
            if it["id"] in n:
                continue
            x = guardado[nome][it["id"]]
            todos = list(dict.fromkeys(x["antes"]["P"][:N_CAND] + candidatos_sem(x)))
            n[it["id"]] = dict(consultar.reranquear(it["pergunta"], todos))
        mh.gravar(NOTAS, nt)
        print(nome, "pronto:", len(itens), flush=True)


def entregues(x: dict, nota: dict, braco: str) -> list[str]:
    ordena = lambda cs: sorted(cs, key=lambda c: -nota[c])
    if braco == "SEM":
        return ordena(candidatos_sem(x))[:10]
    hoje = ordena(x["antes"]["P"][:N_CAND])
    return (limitar_guia(hoje) if braco == "MAX1" else hoje)[:10]


# ---------------------------------------------------------------- 3. medir
def medir() -> None:
    por = mv.chunks_por_id()
    guardado, nt = mh.ler(mh.LISTAS), mh.ler(NOTAS)
    julg = mv.julgados_rascunho()
    L = ["A BUSCA DO ÍRIS SEM O GUIA DA ABDA. Gabaritos de modelo, sem conferência humana. Nenhum modelo treinado.",
         "HOJE: Qwen3 com a pergunta (conta exata), reranker sobre os 50, entrega 5.",
         "SEM: o guia fica fora da busca. MAX1: o guia continua, mas só 1 trecho dele pode ficar entre os 5 entregues.",
         f"Técnica: modelos prontos, contagem e sorteio. Bootstrap de 95%: {mv.N_BOOT} sorteios de perguntas, semente {mv.SEMENTE}. "
         f"Acaso no recall@5: {5 / len(por):.3f}.", ""]
    dif, nj_tudo, entregues_praticas = {}, {}, {}
    for nome, itens in conjuntos().items():
        g, n = guardado[nome], len(itens)
        listas = {b: [entregues(g[i["id"]], nt[nome][i["id"]], b) for i in itens] for b in BRACOS}
        igual = sum(listas["HOJE"][j][:5] == g[itens[j]["id"]]["depois"]["P"][:5] for j in range(n))
        certos = [i["certos"] for i in itens]
        fim = {b: [avaliar.metricas_pergunta(l, c) for l, c in zip(listas[b], certos)] for b in BRACOS}
        L += [f"===== {nome.upper()}: {n} perguntas, {sum(len(c) for c in certos)} trechos certos; uma pergunta vale {100 / n:.1f} pontos =====",
              f"conferência: HOJE devolve os mesmos 5 trechos da medida anterior (outputs/29) em {igual} de {n} perguntas",
              f"{'busca':32s}{'recall@5 final':>22s}{'ao menos 1 certo nos 5':>24s}{'MRR':>7s}{'certos entregues':>18s}{'vagas do guia':>15s}"]
        for b, rot in BRACOS.items():
            v = [p["recall@5"] for p in fim[b]]
            lo, hi = avaliar.bootstrap(v)
            L.append(f"{rot:32s}{f'{mv.media(v):.2f} [{lo:.2f}-{hi:.2f}]':>22s}"
                     f"{sum(bool(c & set(l[:5])) for l, c in zip(listas[b], certos)):>17d} de {n}{mv.media(p['MRR'] for p in fim[b]):7.2f}"
                     f"{sum(len(c & set(l[:5])) for l, c in zip(listas[b], certos)):18d}{sum(do_guia(x) for l in listas[b] for x in l[:5]):15d}")
        L += ["", "Diferença pareada contra HOJE (variação menos hoje), IC 95%, perguntas em que ganhou/empatou/perdeu:"]
        for b in ("SEM", "MAX1"):
            f = mv.diferenca([p["recall@5"] for p in fim[b]], [p["recall@5"] for p in fim["HOJE"]])
            dif[(nome, b)] = f
            L.append(f"{BRACOS[b]:32s} recall@5 final {f[0]:+.2f} [{f[1]:+.2f} a {f[2]:+.2f}] {f[3]}/{f[4]}/{f[5]}")
        L.append("")
        if nome == "opus":
            ix = [j for j, i in enumerate(itens) if i["id"] in PRATICAS]
            fora = [j for j in range(n) if j not in ix]
            for rot, quais in (("AS 10 PERGUNTAS PRÁTICAS", ix), ("AS OUTRAS 28 PERGUNTAS", fora)):
                tt = sum(len(certos[j]) for j in quais)
                L += [f"{rot} ({tt} trechos certos):",
                      f"  {'busca':32s}{'recall@5 final':>16s}{'certos entregues':>18s}{'vagas do guia':>15s}{'guia e certo':>14s}   perguntas sem nenhum certo nos 5"]
                for b, rotb in BRACOS.items():
                    zero = [itens[j]["id"] for j in quais if not certos[j] & set(listas[b][j][:5])]
                    L.append(f"  {rotb:32s}{mv.media(fim[b][j]['recall@5'] for j in quais):16.2f}"
                             f"{sum(len(certos[j] & set(listas[b][j][:5])) for j in quais):12d} de {tt}"
                             f"{sum(do_guia(x) for j in quais for x in listas[b][j][:5]):15d}"
                             f"{sum(do_guia(x) and x in certos[j] for j in quais for x in listas[b][j][:5]):14d}"
                             f"   {', '.join(zero) if len(zero) <= 8 else str(len(zero)) + ' perguntas'}")
                    entregues_praticas[(rot, b)] = sum(len(certos[j] & set(listas[b][j][:5])) for j in quais)
                for b in ("SEM", "MAX1"):
                    f = mv.diferenca([fim[b][j]["recall@5"] for j in quais], [fim["HOJE"][j]["recall@5"] for j in quais])
                    dif[(rot, b)] = f
                    L.append(f"  {BRACOS[b]:32s} menos hoje: {f[0]:+.2f} [{f[1]:+.2f} a {f[2]:+.2f}] {f[3]}/{f[4]}/{f[5]}")
                L.append("")
            # a matriz do que entrou e saiu nas práticas: cada vaga trocada, pelo que o gabarito diz do trecho que saiu e do que entrou
            for b in ("SEM", "MAX1"):
                sai_c = sai_n = ent_c = ent_n = 0
                for j in ix:
                    antes, depois = set(listas["HOJE"][j][:5]), set(listas[b][j][:5])
                    sai_c += len((antes - depois) & certos[j]); sai_n += len((antes - depois) - certos[j])
                    ent_c += len((depois - antes) & certos[j]); ent_n += len((depois - antes) - certos[j])
                L += [f"Matriz das vagas trocadas nas práticas, {BRACOS[b]} (o que o gabarito diz do trecho):",
                      f"{'':22s}{'trecho certo':>14s}{'não marcado':>13s}",
                      f"{'saiu dos 5':22s}{sai_c:14d}{sai_n:13d}",
                      f"{'entrou nos 5':22s}{ent_c:14d}{ent_n:13d}", ""]
            # de que documento são os trechos que entraram no lugar do guia, nas práticas
            from collections import Counter
            ent = Counter(mv.doc(x) for j in ix for x in set(listas["SEM"][j][:5]) - set(listas["HOJE"][j][:5]))
            L += ["De onde vêm os trechos que entraram no lugar do guia nas práticas (sem o guia na busca):"]
            L += [f"  {d[:52]:54s}{k:3d}  ({por[next(c for c in por if mv.doc(c) == d)]['idioma']})" for d, k in ent.most_common()]
            L.append("")
        if nome == "rascunho" and julg is not None:
            L.append("Vagas dos 5 entregues ocupadas por trecho que nenhum juiz do rascunho leu (acima de 10% a comparação não vale):")
            for b, rot in BRACOS.items():
                nj = sum(x not in julg[int(i["id"][1:])] for i, l in zip(itens, listas[b]) for x in l[:5])
                nj_tudo[b] = nj
                L.append(f"  {rot:32s} {nj:3d} de {5 * n} ({100 * nj / (5 * n):.0f}%)")
            L.append("")
    L += ["CRITÉRIO (escrito antes de rodar): a variação é candidata se, no gabarito do Opus, o recall@5 final das 38 perguntas",
          "menos o de hoje NÃO tem o intervalo todo abaixo de zero, e nas 10 práticas os trechos certos entregues não caem.",
          "Com o intervalo todo acima de zero nas 38, passa. O rascunho só conta com até 10% de vagas não julgadas."]
    for b in ("SEM", "MAX1"):
        o, pr = dif[("opus", b)], dif[("AS 10 PERGUNTAS PRÁTICAS", b)]
        v = "PASSA" if o[1] > 0 else "PIORA (intervalo todo abaixo de zero)" if o[2] < 0 else "NÃO SE DISTINGUE DE HOJE"
        antes, depois = entregues_praticas[("AS 10 PERGUNTAS PRÁTICAS", "HOJE")], entregues_praticas[("AS 10 PERGUNTAS PRÁTICAS", b)]
        cand = "É CANDIDATA" if o[2] >= 0 and depois >= antes else "NÃO É CANDIDATA"
        L.append(f"{BRACOS[b]:32s} 38 perguntas {o[0]:+.2f} [{o[1]:+.2f} a {o[2]:+.2f}]: {v}; práticas {pr[0]:+.2f} [{pr[1]:+.2f} a {pr[2]:+.2f}], "
                 f"trechos certos entregues nas práticas de {antes} para {depois}: {cand}")
    (SAIDAS / "35-busca-sem-o-guia-abda.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    {"contar": contar, "notas": notas, "medir": medir}[sys.argv[1]]()
