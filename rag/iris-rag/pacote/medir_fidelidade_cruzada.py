"""Fidelidade das respostas com um terceiro juiz de outro fabricante (Issue #16, tarefa 4: Faithfulness).

    .venv/bin/python medir_fidelidade_cruzada.py julgar haiku     o Codex julga as 40 respostas do gerador (cache/)
    .venv/bin/python medir_fidelidade_cruzada.py julgar opus
    .venv/bin/python medir_fidelidade_cruzada.py medir            concordância com os juízes Sonnet e fidelidade (outputs/37)
    .venv/bin/python medir_fidelidade_cruzada.py desempatar       Opus julga só as respostas com frase dividida (cache/)
    .venv/bin/python medir_fidelidade_cruzada.py medir            de novo, agora com o desempate

Pergunta que responde: de cada 10 frases de conteúdo que a resposta escreve, quantas o trecho citado sustenta?
É a receita da Faithfulness do RAGAS (frases sustentadas pelo contexto / frases da resposta), com duas diferenças
ditas aqui para ninguém confundir com a biblioteca rodando:
  * a unidade é a frase da resposta (o mesmo divisor da segunda rodada), não a afirmação atômica que o RAGAS extrai
    com um LLM; uma frase com duas afirmações vale como uma só, e "em parte" conta como não sustentada;
  * a frase tem de estar no trecho que ela CITA, não em qualquer um dos cinco: é mais rigoroso que o RAGAS.

O que é novo em relação à segunda rodada (RESPOSTAS.md): lá os dois juízes eram Claude Sonnet, do mesmo fabricante
dos geradores (Claude Haiku e Opus). Aqui entra o Codex (modelo da OpenAI, pelo CLI), com a MESMA regra
(regra_juiz_respostas_v2.md), o MESMO prompt e as MESMAS frases. Os julgamentos Sonnet A e B já gravados em 05/11
são reaproveitados: julgar de novo custaria cerca de 1,4 milhão de tokens e não traria informação nova.

Alternativa descartada: rodar a biblioteca RAGAS com juiz. Exige chave de API de um provedor; esse caminho está em
backend/src/iris/eval/faithfulness.py. A conta a partir dos vereditos versionados, sem modelo e sem rede, está em
backend/src/iris/eval/fidelidade_frases.py.

Técnica: nenhum modelo é treinado. Modelos prontos julgam; o resto é contagem, kappa de Cohen (fórmula) e sorteio de
perguntas (bootstrap). A prova (passagem copiada do trecho) é conferida por script, como na segunda rodada.
"""
from __future__ import annotations

import math
import random
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import medir_respostas as mr

VERSIONADO = mr.AQUI / "respostas_vereditos_cruzado.json"   # só rótulos, sem o texto dos trechos
SAIDA = mr.SAIDAS / "37-fidelidade-juiz-de-outro-fabricante.txt"
FIGURA = mr.SAIDAS / "figuras" / "37-fidelidade-juiz-de-outro-fabricante.png"
META = 0.90                                  # FAITHFULNESS_MIN de backend/src/iris/eval/faithfulness.py
ESFORCO = "medium"                           # esforço de raciocínio pedido ao Codex
GERADORES = ("haiku", "opus")
CLASSES = ("apoiada", "parcial", "nao_apoiada", "rejeitado")


def chamar_codex(texto: str) -> tuple[str, dict]:
    """Uma chamada isolada ao Codex: pasta vazia, sem escrita, sem sessão gravada. Devolve a última mensagem."""
    with tempfile.TemporaryDirectory(prefix="iris-codex-") as vazio:
        destino = Path(vazio) / "saida.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
               "-c", f'model_reasoning_effort="{ESFORCO}"', "-o", str(destino), "-"]
        entrada = mr.SISTEMA_JUIZ + " Não rode comando nenhum: tudo o que você precisa está nesta mensagem.\n\n" + texto
        for tentativa in range(3):
            t0 = time.time()
            r = subprocess.run(cmd, check=False, input=entrada, capture_output=True, text=True, cwd=vazio, timeout=900)
            try:
                bruto = destino.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                bruto = ""
            if r.returncode == 0 and bruto:
                log = r.stdout + r.stderr
                modelo = next((ln.split(":", 1)[1].strip() for ln in log.splitlines() if ln.startswith("model:")), "")
                return bruto, {"modelo": modelo, "esforco": ESFORCO, "s": round(time.time() - t0)}
            time.sleep(10 * (tentativa + 1))
        raise RuntimeError(f"chamada ao Codex falhou: {r.stderr[-300:]}")


def julgar(g: str) -> None:
    base, resp, _ = mr.carregar()
    destino = mr.PASTA / f"juiz2-X-{g}.json"
    feito = mr.ler(destino, {})
    ids = mr.so([i["id"] for i in base["itens"]])
    faltam = [i for i in base["itens"] if i["id"] in ids and i["id"] not in feito]

    def um(item: dict) -> tuple[str, dict]:
        p = mr.prompt_do_juiz2(item, resp[g][item["id"]]["resposta"], base["frase_sem_resposta"])
        for _ in range(2):
            bruto, uso = chamar_codex(p)
            d = mr.extrair_json(bruto)
            if d is not None:
                break
        return item["id"], {"json": d, "bruto": bruto if d is None else None, "uso": uso}

    with ThreadPoolExecutor(mr.EM_PARALELO) as ex:
        for qid, v in ex.map(um, faltam):
            feito[qid] = v
            mr.gravar(destino, feito)
            print("codex", g, qid, "ok" if v["json"] else "JSON INVÁLIDO", v["uso"], flush=True)
    print(f"codex / {g}: {len(feito)} julgamentos")


def binario(v: str) -> int | None:
    """1 = o trecho citado sustenta a frase inteira; 0 = em parte, não sustenta ou prova rejeitada; None = não é conteúdo."""
    return (1 if v == "apoiada" else 0) if v in CLASSES else None


def tabela(g: str, base: dict, resp: dict) -> dict:
    """Para cada pergunta respondida: o veredito conferido de cada juiz (A, B = Sonnet; X = Codex; O = Opus), por frase."""
    jz = {j: mr.ler(mr.PASTA / f"juiz2-{j}-{g}.json", {}) for j in "ABXO"}
    saida = {}
    for item in base["itens"]:
        qid = item["id"]
        texto = resp[g][qid]["resposta"]
        if mr.recusou(texto, base["frase_sem_resposta"]):
            continue
        blocos = mr.blocos_do_gerador(item)
        d = {j: (jz[j].get(qid) or {}).get("json") or {} for j in "ABXO"}
        linhas = []
        for n, f in enumerate(mr.frases_da_resposta(texto), 1):
            v = {j: mr.veredito2(next((x for x in d[j].get("frases") or [] if x.get("n") == n), None), f, blocos)
                 for j in "ABXO"}
            votos = {j: binario(v[j]) for j in "ABX"}
            conteudo = [b for b in votos.values() if b is not None]
            if len(conteudo) < 2:                                   # dois ou mais dizem que é comentário
                final, dividida = None, False
            else:
                # dividida = os dois Sonnet de um lado e o Codex do outro, ou empate sem terceiro voto
                dividida = ((votos["A"] is not None and votos["A"] == votos["B"] and votos["X"] is not None
                             and votos["X"] != votos["A"]) or sum(conteudo) * 2 == len(conteudo))
                final = int(sum(conteudo) * 2 > len(conteudo))
                if dividida and binario(v["O"]) is not None:
                    final = binario(v["O"])
            linhas.append({"n": n, **v, "final": final, "dividida": dividida})
        saida[qid] = linhas
    return saida


def fidelidade(tab: dict, chave: str) -> tuple[float, tuple[float, float], int, int]:
    """Média, por resposta, de frases sustentadas / frases de conteúdo, para um juiz ou para o veredito final."""
    por_resposta, sust, total = [], 0, 0
    for linhas in tab.values():
        b = [x["final"] if chave == "final" else binario(x[chave]) for x in linhas]
        b = [x for x in b if x is not None]
        if b:
            por_resposta.append(sum(b) / len(b))
            sust, total = sust + sum(b), total + len(b)
    return mr.media(por_resposta), mr.intervalo(por_resposta), sust, total


def pares(tab: dict, a: str, b: str, duas: bool = False) -> list[tuple[str, str]]:
    """Os vereditos de dois juízes nas frases que os dois chamam de conteúdo."""
    ps = [(x[a], x[b]) for linhas in tab.values() for x in linhas if x[a] in CLASSES and x[b] in CLASSES]
    return [(str(binario(p)), str(binario(q))) for p, q in ps] if duas else ps


def medir() -> None:
    base, resp, _ = mr.carregar()
    tabs = {g: tabela(g, base, resp) for g in GERADORES}
    tem_opus = any(x["O"] != "sem_veredito" for t in tabs.values() for ls in t.values() for x in ls)
    brutos = {g: mr.ler(mr.PASTA / f"juiz2-X-{g}.json", {}) for g in GERADORES}
    modelo = Counter(v["uso"]["modelo"] for b in brutos.values() for v in b.values()).most_common(1)[0][0]
    nome = {"A": "Sonnet A", "B": "Sonnet B", "X": "Codex", "final": "maioria dos três" + (" + Opus" if tem_opus else "")}
    L = ["FIDELIDADE DAS RESPOSTAS COM UM JUIZ DE OUTRO FABRICANTE (regra versão 2, as mesmas 80 respostas e frases).",
         f"Juízes: Claude Sonnet A e B (gravados em 05/11/2026, reaproveitados) e Codex ({modelo}, esforço {ESFORCO}).",
         "Geradores Claude Haiku e Opus, não o modelo configurado no protótipo. Sem conferência humana: a nota é prata.",
         (
             f"Técnica: modelos prontos julgam; contagem; kappa de Cohen; sorteio de perguntas ({mr.N_BOOT} sorteios, semente "
             f"{mr.SEMENTE}). Nenhum modelo treinado."
         ),
         "Fidelidade = frases que o trecho citado sustenta por inteiro / frases de conteúdo, média por resposta.",
         "'Em parte' e prova rejeitada (passagem que não existe no trecho) contam como não sustentada. Recusas ficam fora.",
         f"Meta (FAITHFULNESS_MIN): {META:.2f}.", ""]
    versionado = {}
    for g in GERADORES:
        t = tabs[g]
        L += [f"=== gerador {g}: {len(t)} respostas julgadas (as recusas ficam fora)", "",
              f"{'quem julga':28s}{'fidelidade':>12s}{'IC 95%':>16s}{'frases sustentadas':>22s}"]
        for j in ("A", "B", "X", "final"):
            m, (lo, hi), s, n = fidelidade(t, j)
            L.append(f"{nome[j]:28s}{m:>12.3f}{f'[{lo:.3f}-{hi:.3f}]':>16s}{f'{s} de {n}':>22s}")
        L += ["", "Concordância frase a frase, nas frases que os dois juízes chamam de conteúdo:",
              f"{'par':22s}{'frases':>8s}{'igual, 4 vereditos':>20s}{'kappa':>8s}{'igual, sustenta ou não':>24s}{'kappa':>8s}"]
        for a, b in (("A", "B"), ("A", "X"), ("B", "X")):
            p4, p2 = pares(t, a, b), pares(t, a, b, duas=True)
            L.append(f"{nome[a] + ' x ' + nome[b]:22s}{len(p4):>8d}{sum(x == y for x, y in p4) / len(p4):>20.1%}"
                     f"{mr.kappa(p4):>8.2f}{sum(x == y for x, y in p2) / len(p2):>24.1%}{mr.kappa(p2):>8.2f}")
        for a in "AB":
            c = Counter((x[a], x["X"]) for ls in t.values() for x in ls)
            cols = [*CLASSES, "comentario_correto", "comentario_errado", "sem_veredito"]
            L += ["", f"Matriz {nome[a]} (linhas) x Codex (colunas), todas as frases:",
                  f"{'':20s}" + "".join(f"{k[:11]:>12s}" for k in cols)]
            L += [f"{la:20s}" + "".join(f"{c[(la, k)]:>12d}" for k in cols) for la in cols
                  if any(c[(la, k)] for k in cols)]
        tipo = [(x["A"] in CLASSES, x["X"] in CLASSES) for ls in t.values() for x in ls
                if "sem_veredito" not in (x["A"], x["X"])]
        div = [(q, x) for q, ls in t.items() for x in ls if x["dividida"]]
        rej = Counter(x["X"] for ls in t.values() for x in ls)
        L += [
            "",
            (
                f"Sonnet A e Codex concordam no tipo da frase (conteúdo ou comentário) em "
                f"{sum(a == b for a, b in tipo)} de {len(tipo)}."
            ),
            (
                f"Vereditos do Codex rejeitados por passagem que não existe no trecho citado: {rej['rejeitado']} de "
                f"{sum(rej[k] for k in CLASSES)} frases de conteúdo. Sem veredito: {rej['sem_veredito']}."
            ),
            (
                "Frases reprovadas por inteiro (nao_apoiada) pelos três juízes: "
                f"{sum(x['A'] == x['B'] == x['X'] == 'nao_apoiada' for ls in t.values() for x in ls)}; "
                "só pelo Codex: "
                f"{sum(x['X'] == 'nao_apoiada' and 'nao_apoiada' not in (x['A'], x['B']) for ls in t.values() for x in ls)}."
            ),
            (
                f"Frases divididas (os dois Sonnet de um lado e o Codex do outro, ou empate): {len(div)}, em "
                f"{len({q for q, _ in div})} respostas."
            ),
        ]
        if tem_opus:
            o = Counter((binario(x["A"]) if x["A"] == x["B"] or binario(x["A"]) == binario(x["B"]) else "empate",
                         binario(x["X"]), binario(x["O"])) for _, x in div)
            com_s = sum(n for (a, x, op), n in o.items() if op is not None and op == a)
            com_x = sum(n for (a, x, op), n in o.items() if op is not None and op == x and op != a)
            L.append(f"Desempate do Opus nas divididas: ficou com os Sonnet em {com_s}, com o Codex em {com_x}; "
                     f"sem veredito de conteúdo em {sum(n for (a, x, op), n in o.items() if op is None)}.")
        L.append("")
        versionado[g] = {q: [{k: x[k] for k in ("n", "A", "B", "X", "O", "final", "dividida")} for x in ls]
                         for q, ls in t.items()}
    a, b = tabs["haiku"], tabs["opus"]
    comuns = [q for q in a if q in b]
    d = [fidelidade({q: b[q]}, "final")[0] - fidelidade({q: a[q]}, "final")[0] for q in comuns]
    d = [x for x in d if not math.isnan(x)]
    rnd = random.Random(mr.SEMENTE)
    ms = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(mr.N_BOOT))
    L.append(f"Opus menos Haiku na fidelidade final, pergunta a pergunta ({len(d)} perguntas respondidas pelos dois): "
             f"{mr.media(d):+.3f} [{ms[int(.025 * mr.N_BOOT)]:+.3f} a {ms[int(.975 * mr.N_BOOT) - 1]:+.3f}].")
    SAIDA.write_text("\n".join(L) + "\n", encoding="utf-8")
    mr.gravar(VERSIONADO, versionado)
    print("\n".join(L))
    figura(tabs, nome)


def figura(tabs: dict, nome: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rot = {"apoiada": "sustenta", "parcial": "em parte", "nao_apoiada": "não sustenta", "rejeitado": "prova\nrejeitada",
           "comentario": "comentário"}
    ordem = list(rot)

    def agrupa(v: str) -> str | None:
        return v if v in CLASSES else "comentario" if v.startswith("comentario") else None

    fig, eixos = plt.subplots(1, 3, figsize=(16, 5.2), gridspec_kw={"width_ratios": [1, 1, 1.15]})
    for ax, g in zip(eixos[:2], GERADORES):
        c = Counter((agrupa(x["A"]), agrupa(x["X"])) for ls in tabs[g].values() for x in ls)
        m = [[c[(la, co)] for co in ordem] for la in ordem]
        ax.imshow(m, cmap="Blues", vmax=40)
        for i, linha in enumerate(m):
            for k, n in enumerate(linha):
                ax.text(k, i, n, ha="center", va="center", color="white" if n > 25 else "black", fontsize=11)
        ax.set_xticks(range(len(ordem)), [rot[o] for o in ordem], fontsize=9)
        ax.set_yticks(range(len(ordem)), [rot[o] for o in ordem], fontsize=9)
        ax.set_xlabel("Codex (OpenAI)")
        ax.set_ylabel("Sonnet A (Anthropic)")
        ax.set_title(f"Respostas do {g.capitalize()}: frase a frase", fontsize=11)
    ax = eixos[2]
    cores = {"A": "#7aa6c2", "B": "#7aa6c2", "X": "#d98b3a", "final": "#333333"}
    y = 0
    marcas, nomes = [], []
    for g in GERADORES:
        for j in ("A", "B", "X", "final"):
            m, (lo, hi), _, _ = fidelidade(tabs[g], j)
            ax.errorbar(m, y, xerr=[[m - lo], [hi - m]], fmt="o", color=cores[j], capsize=4, markersize=7)
            ax.text(hi + 0.006, y, f"{m:.2f}", va="center", fontsize=9)
            marcas.append(y)
            nomes.append(f"{g.capitalize()} · {nome[j]}")
            y -= 1
        y -= 0.6
    ax.axvline(META, color="crimson", ls="--", lw=1)
    ax.text(META, 0.7, f"meta {META:.2f}", color="crimson", ha="center", fontsize=9)
    ax.set_yticks(marcas, nomes, fontsize=9)
    ax.set_xlim(0.6, 1.04)
    ax.set_xlabel("fidelidade: frases sustentadas / frases de conteúdo (média por resposta, IC 95%)")
    ax.set_title("Fidelidade por quem julga", fontsize=11)
    fig.suptitle("Íris: o trecho citado sustenta a frase? Juízes de dois fabricantes, mesma regra, mesmas frases",
                 fontsize=12)
    fig.tight_layout()
    FIGURA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURA, dpi=130)
    print("figura:", FIGURA)


def desempatar() -> None:
    """O Opus julga, com o mesmo prompt, só as respostas que têm frase dividida. Só o veredito dessas frases é usado."""
    base, resp, _ = mr.carregar()
    for g in GERADORES:
        tab = tabela(g, base, resp)
        quais = {q for q, ls in tab.items() if any(x["dividida"] for x in ls)}
        destino = mr.PASTA / f"juiz2-O-{g}.json"
        feito = mr.ler(destino, {})
        faltam = [i for i in base["itens"] if i["id"] in quais and i["id"] not in feito]

        def um(item: dict, gerador: str = g) -> tuple[str, dict]:
            p = mr.prompt_do_juiz2(item, resp[gerador][item["id"]]["resposta"], base["frase_sem_resposta"])
            for _ in range(2):
                bruto, uso = mr.chamar_claude("opus", mr.SISTEMA_JUIZ, p)
                d = mr.extrair_json(bruto)
                if d is not None:
                    break
            return item["id"], {"json": d, "bruto": bruto if d is None else None, "uso": uso}

        with ThreadPoolExecutor(mr.EM_PARALELO) as ex:
            for qid, v in ex.map(um, faltam):
                feito[qid] = v
                mr.gravar(destino, feito)
                print("opus", g, qid, "ok" if v["json"] else "JSON INVÁLIDO", flush=True)
        print(f"opus / {g}: {len(feito)} de {len(quais)} respostas com frase dividida; entrada "
              f"{sum(v['uso']['entrada'] for v in feito.values())} tokens, saída {sum(v['uso']['saida'] for v in feito.values())}")


if __name__ == "__main__":
    passo = sys.argv[1] if len(sys.argv) > 1 else ""
    if passo == "julgar":
        julgar(sys.argv[2])
    elif passo == "medir":
        medir()
    elif passo == "desempatar":
        desempatar()
    else:
        print(__doc__)
