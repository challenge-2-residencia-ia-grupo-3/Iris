"""Duas técnicas para a PRIMEIRA etapa da busca do Íris: resposta imaginária (HyDE) e reescrita da pergunta.

    .venv/bin/python medir_hyde.py contar     o teto: quantos trechos certos a primeira etapa perde hoje (outputs/28)
    .venv/bin/python medir_hyde.py gerar      um modelo escreve as perguntas curtas, as respostas imaginárias e as reescritas
    .venv/bin/python medir_hyde.py ranquear   busca com cada técnica e passa o reranker (cache/)
    .venv/bin/python medir_hyde.py posicoes   a posição exata de cada trecho certo, com a pergunta e com a resposta imaginária (cache/)
    .venv/bin/python medir_hyde.py medir      compara cada técnica com a busca de hoje (outputs/29)
    .venv/bin/python medir_hyde.py contar-leitor   segunda medida: teto dos candidatos e corte do trecho no reranker (outputs/30)
    .venv/bin/python medir_hyde.py notas-leitor    nota do reranker lendo a pergunta e lendo a resposta imaginária (cache/)
    .venv/bin/python medir_hyde.py medir-leitor    as quatro combinações de candidatos e leitor (outputs/31)
    .venv/bin/python medir_hyde.py comprimento     terceira contagem: o comprimento do trecho explica o que a busca perde? (outputs/32)

O que cada técnica faz, antes do reranker (que continua lendo os 50 candidatos com a pergunta que a pessoa digitou):
    P    a busca de hoje: o Qwen3 procura trechos parecidos com a PERGUNTA
    H    resposta imaginária sozinha (HyDE): um modelo de linguagem escreve um parágrafo que responderia à pergunta, sem
         consultar nada, e o Qwen3 procura trechos parecidos com esse PARÁGRAFO (lido como documento, sem a instrução de pergunta)
    PH   as duas listas (P e H) juntas pela posição (RRF, k=60)
    R    reescrita: o modelo de linguagem escreve 3 versões da pergunta com o vocabulário dos documentos; as 4 listas
         (pergunta e 3 versões) são juntas pela posição (RRF, k=60)

Conjuntos de perguntas:
    opus        38 perguntas do gabarito do Opus, como estão (de 12 a 27 palavras)
    rascunho    19 perguntas do rascunho ampliado (só vale se até 10% das vagas dos 5 primeiros forem de trecho nunca julgado)
    opus-curta  as mesmas 38 perguntas do Opus, encurtadas por um modelo para 3 a 6 palavras, com os mesmos trechos certos.
                É o caso do professor com pressa. EXPLORATÓRIO: a versão curta foi escrita por modelo, não por professor.

Técnica: nenhum modelo é treinado. Modelos prontos (Qwen3-Embedding, reranker mMiniLM e o Claude Haiku, que escreve os
textos), contagem e sorteio de perguntas (bootstrap). O Haiku NÃO é o modelo configurado no protótipo (Qwen, via Groq):
o que se mede aqui é a técnica, com outro escritor. A busca é a conta exata do cosseno (como o pgvector faz no servidor),
e não o índice aproximado do Chroma, para que a mesma pergunta dê sempre a mesma lista.
Os dois gabaritos são de modelo, sem conferência humana.
Expectativa e critério: GABARITO-RASCUNHO.md, "Resposta imaginária (HyDE) e reescrita", commitados antes de `gerar`.
Segunda medida: "Quem o reranker lê, e quantos candidatos", commitados antes de `notas-leitor`.
Não altera consultar.py.
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import avaliar            # noqa: E402
import medir_variacoes as mv  # noqa: E402  (gabaritos, diferença pareada; fixa RAG_BANCO=chroma)

SAIDAS = AQUI.parents[1] / "outputs"
CURTAS = AQUI / "perguntas_curtas.json"            # versionado: a medida depende dele
TEXTOS = AQUI / "hyde_textos.json"                 # versionado: respostas imaginárias e reescritas (só texto de modelo)
LISTAS = AQUI / "cache" / "hyde-listas.json"       # fora do Git
POSICOES = AQUI / "cache" / "hyde-posicoes.json"   # fora do Git
ESCRITOR = "haiku"
N_CAND = 50                                        # quantos candidatos o reranker lê (o padrão do produto)
FUNDO = 100
BRACOS = ["P", "H", "PH", "R"]
NOME = {"P": "P  pergunta (hoje)", "H": "H  resposta imaginária", "PH": "PH pergunta + imaginária", "R": "R  pergunta + 3 reescritas"}
PRATICAS = [f"Q{n:02d}" for n in range(1, 11)]     # as 10 perguntas práticas de professor (tipo estrategia)

SIS_CURTA = ("Você recebe a pergunta de um professor. Reescreva como um professor com pressa digitaria numa caixa de busca: "
             "de 3 a 6 palavras, em português, sem ponto final, mantendo o assunto principal. Devolva só a versão curta.")
SIS_HYDE = ("Escreva um trecho de documento que responda à pergunta do professor. O trecho é de um guia, diretriz, lei ou "
            "artigo de pesquisa sobre educação inclusiva. Em português, de 80 a 120 palavras, um parágrafo só. Se a pergunta "
            "for curta ou vaga, escolha a leitura mais provável para um professor de sala comum. Devolva só o trecho.")
SIS_REESCRITA = ("Você reescreve a pergunta de um professor para um buscador de documentos sobre educação inclusiva (guias, "
                 "diretrizes do Desenho Universal para a Aprendizagem, leis, artigos de pesquisa). Devolva 3 reescritas, uma por "
                 "linha, sem numeração: cada uma diz a mesma necessidade com outras palavras, usando os termos que esses "
                 "documentos usariam. Em português. Não responda à pergunta e não acrescente assunto que ela não tem.")


def ler(caminho: Path, padrao=None):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


def gravar(caminho: Path, dado) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")


def conjuntos(com_curtas: bool = True) -> dict[str, list[dict]]:
    """Cada item: id, pergunta (a que a pessoa digitou), tipo e o conjunto de trechos certos."""
    gabs, _ = mv.gabaritos()
    c = {"opus": gabs["opus"], "rascunho": gabs["rascunho"]}
    if com_curtas and CURTAS.exists():
        curta = ler(CURTAS)["perguntas"]
        c["opus-curta"] = [{**it, "pergunta": curta[it["id"]]} for it in gabs["opus"]]
    return c


# ---------------------------------------------------------------- a busca exata
class Busca:
    """Todos os vetores gravados, de comprimento 1: o produto pelo vetor da consulta é o cosseno. Ordem exata."""

    def __init__(self):
        import numpy as np
        import consultar
        self.np, self.consultar = np, consultar
        tudo = consultar._colecao("qwen3").get(include=["embeddings"])
        self.ids = list(tudo["ids"])
        E = np.asarray(tudo["embeddings"], dtype=np.float64)
        self.E = E / np.linalg.norm(E, axis=1, keepdims=True)
        self.modelo = consultar._modelo("qwen3")

    def _ordem(self, v) -> list[str]:
        np = self.np
        v = np.asarray(v, dtype=np.float64).ravel()
        return [self.ids[j] for j in np.argsort(-(self.E @ (v / np.linalg.norm(v))), kind="stable")[:FUNDO]]

    def por_pergunta(self, texto: str) -> list[str]:
        """O texto entra como PERGUNTA: recebe a instrução 'query' do Qwen3."""
        return self._ordem(self.modelo.vetor_pergunta(texto))

    def por_documento(self, texto: str) -> list[str]:
        """O texto entra como DOCUMENTO, sem instrução: é assim que os trechos da base foram transformados em vetor."""
        return self._ordem(self.modelo.modelo.encode([texto], normalize_embeddings=True, convert_to_numpy=True)[0])


def juntar(listas: list[list[str]]) -> list[str]:
    """Junta listas pela posição (RRF, k=60), olhando os 50 primeiros de cada uma."""
    import embeddings as emb
    return [cid for cid, _ in emb.rrf([l[:N_CAND] for l in listas], k=60)]


# ---------------------------------------------------------------- 1. o teto, antes de prever
def contar() -> None:
    por = mv.chunks_por_id()
    b = Busca()
    guardado = ler(LISTAS, {})
    L = ["O TETO DA PRIMEIRA ETAPA, CONTADO ANTES DE PREVER. Busca de hoje: Qwen3 com a pergunta, conta exata do cosseno.",
         "Técnica: contagem sobre os gabaritos de modelo (sem conferência humana). Nenhum modelo treinado.",
         f"A base tem {len(por)} trechos. O reranker lê os {N_CAND} primeiros: trecho certo fora deles não tem como chegar ao gerador.", ""]
    for nome, itens in conjuntos(com_curtas=False).items():
        g = guardado.setdefault(nome, {})
        tot = n5 = n50 = n100 = 0
        sem50 = []
        tam = sorted(len(it["pergunta"].split()) for it in itens)
        linhas = []
        for it in itens:
            lista = b.por_pergunta(it["pergunta"])
            g.setdefault(it["id"], {})["P"] = lista
            c = it["certos"]
            a5, a50, a100 = (len(c & set(lista[:k])) for k in (5, N_CAND, FUNDO))
            tot, n5, n50, n100 = tot + len(c), n5 + a5, n50 + a50, n100 + a100
            if a50 == 0:
                sem50.append(it["id"])
            linhas.append(f"  {it['id']:5s}{it['tipo']:12s}{len(c):7d}{a5:9d}{a50:10d}{a100:11d}{len(c) - a100:13d}")
        L += [f"===== {nome.upper()}: {len(itens)} perguntas, de {tam[0]} a {tam[-1]} palavras (mediana {tam[len(tam) // 2]}) =====",
              f"trechos certos: {tot} | entre os 5 primeiros do Qwen3: {n5} | entre os {N_CAND}: {n50} ({100 * n50 / tot:.0f}%) | "
              f"entre os {FUNDO}: {n100} | depois da posição {FUNDO}: {tot - n100}",
              f"perdidos antes do reranker (fora dos {N_CAND}): {tot - n50} de {tot} ({100 * (tot - n50) / tot:.0f}%). "
              f"Perguntas sem nenhum certo entre os {N_CAND}: {len(sem50)} ({', '.join(sem50) or '-'})",
              f"  {'id':5s}{'tipo':12s}{'certos':>7s}{'nos 5':>9s}{'nos 50':>10s}{'nos 100':>11s}{'depois de 100':>13s}", *linhas, ""]
        if nome == "opus":
            L.append("Por tipo de pergunta (certos entre os 50, de quantos):")
            for t in dict.fromkeys(i["tipo"] for i in itens):
                ix = [i for i in itens if i["tipo"] == t]
                c50 = sum(len(i["certos"] & set(g[i["id"]]["P"][:N_CAND])) for i in ix)
                L.append(f"  {t:12s} {c50:3d} de {sum(len(i['certos']) for i in ix):3d}")
            L.append("")
    L += ["Leitura: o que a resposta imaginária e a reescrita podem ganhar é o que está 'fora dos 50'. O que já está entre",
          "os 50 e não chega aos 5 é assunto do reranker, não destas duas técnicas.",
          "Nenhuma pergunta dos dois gabaritos tem menos de 7 palavras: o caso do professor que escreve curto não está neles.",
          "Por isso a medida inclui as mesmas perguntas do Opus encurtadas por modelo (perguntas_curtas.json), como recorte exploratório."]
    gravar(LISTAS, guardado)
    (SAIDAS / "28-teto-primeira-etapa.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 2. os textos que o modelo escreve
def curta_ok(v: str) -> bool:
    """A instrução pede uma linha só, de 3 a 6 palavras."""
    return "\n" not in v.strip() and 3 <= len(v.split()) <= 6


def linhas_reescrita(v: str) -> list[str]:
    """Uma reescrita por linha, sem numeração; linha que termina em dois-pontos é anúncio ("Reescritas:"), não reescrita."""
    ls = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", l).strip() for l in v.splitlines() if l.strip()]
    return [l for l in ls if not l.endswith(":")]


def gerar() -> None:
    from medir_respostas import chamar_claude
    gabs, _ = mv.gabaritos()
    gasto = {"entrada": 0, "saida": 0, "chamadas": 0, "refeitas por formato": 0}

    def em_lote(sistema: str, pedidos: dict[str, str], ok=lambda v: True, lembrete: str = "") -> dict[str, str]:
        """Uma chamada por pedido, 4 de cada vez. O que vier fora do formato é pedido de novo, até 4 vezes, com o lembrete
        do formato depois da pergunta; a conferência olha só o formato do texto (linhas e palavras), nunca a busca."""
        saida, faltam = {}, dict(pedidos)
        for rodada in range(5):
            if not faltam:
                break
            extra = f"\n\n({lembrete})" if rodada and lembrete else ""
            with ThreadPoolExecutor(4) as ex:
                res = list(ex.map(lambda kv: (kv[0], chamar_claude(ESCRITOR, sistema, kv[1] + extra)), faltam.items()))
            for k, (txt, uso) in res:
                gasto["entrada"] += uso["entrada"]; gasto["saida"] += uso["saida"]; gasto["chamadas"] += 1
                gasto["refeitas por formato"] += rodada > 0
                if ok(txt):
                    saida[k] = txt
                    del faltam[k]
        assert not faltam, f"fora do formato depois de 5 tentativas: {sorted(faltam)}"
        return saida

    # (a) perguntas curtas: o modelo lê só a pergunta, nunca os trechos certos
    curtas = ler(CURTAS, {"perguntas": {}})["perguntas"]
    curtas = {k: v for k, v in curtas.items() if curta_ok(v)}            # a que saiu fora do formato é pedida de novo
    faltam = {it["id"]: it["pergunta"] for it in gabs["opus"] if it["id"] not in curtas}
    if faltam:
        limpa = lambda v: v.strip().strip('"*').rstrip(".?")
        curtas.update({k: limpa(v) for k, v in em_lote(SIS_CURTA, faltam, lambda v: curta_ok(limpa(v)),
                                                        "Devolva uma linha só, com no máximo 6 palavras e no mínimo 3.").items()})
        como = (f"Escritas pelo Claude ({ESCRITOR}), uma chamada por pergunta, lendo só a pergunta original do gabarito do Opus, "
                "sem ver os trechos certos e sem revisão humana. Instrução em medir_hyde.py (SIS_CURTA). A que saiu fora do "
                "formato (mais de uma linha, menos de 3 ou mais de 6 palavras) foi pedida de novo, com um lembrete do formato, sem olhar a busca.")
        gravar(CURTAS, {"_como": como, "perguntas": dict(sorted(curtas.items()))})

    # (b) resposta imaginária e reescritas, para a pergunta de cada conjunto como ela foi digitada
    textos = ler(TEXTOS, {})
    for nome, itens in conjuntos().items():
        t = textos.setdefault(nome, {})
        for it in itens:                                                 # se a pergunta mudou, o texto guardado não serve
            if t.get(it["id"], {}).get("pergunta", it["pergunta"]) != it["pergunta"]:
                del t[it["id"]]
        falta_h = {it["id"]: it["pergunta"] for it in itens if "hyde" not in t.get(it["id"], {})}
        for k, v in em_lote(SIS_HYDE, falta_h).items():
            t.setdefault(k, {})["hyde"] = v.strip()
        falta_r = {it["id"]: it["pergunta"] for it in itens if len(t.get(it["id"], {}).get("reescritas", [])) != 3}
        for k, v in em_lote(SIS_REESCRITA, falta_r, lambda v: len(linhas_reescrita(v)) == 3,
                              "Devolva exatamente 3 linhas, uma reescrita em cada, sem título e sem numeração.").items():
            t.setdefault(k, {})["reescritas"] = linhas_reescrita(v)
        for it in itens:
            t[it["id"]]["pergunta"] = it["pergunta"]
        gravar(TEXTOS, textos)
        print(nome, "pronto:", len(itens))
    print("gasto:", gasto)
    for nome, itens in conjuntos().items():
        t = textos[nome]
        iguais = sum(r.strip().lower() == it["pergunta"].strip().lower() for it in itens for r in t[it["id"]]["reescritas"])
        print(nome, "reescritas iguais à pergunta digitada:", iguais, "de", 3 * len(itens))


# ---------------------------------------------------------------- 3. buscar com cada técnica e passar o reranker
def ranquear() -> None:
    b = Busca()
    textos = ler(TEXTOS)
    guardado = ler(LISTAS, {})
    for nome, itens in conjuntos().items():
        g = guardado.setdefault(nome, {})
        for it in itens:
            x = g.setdefault(it["id"], {})
            t = textos[nome][it["id"]]
            assert t["pergunta"] == it["pergunta"], "o texto guardado não é desta pergunta: rode `gerar`"
            p = b.por_pergunta(it["pergunta"])
            h = b.por_documento(t["hyde"])
            rs = [b.por_pergunta(r) for r in t["reescritas"]]
            antes = {"P": p, "H": h, "PH": juntar([p, h]), "R": juntar([p, *rs])}
            # o reranker dá uma nota a cada par (pergunta digitada, trecho): calcula uma vez e reaproveita entre as técnicas
            todos = sorted({cid for l in antes.values() for cid in l[:N_CAND]})
            nota = dict(b.consultar.reranquear(it["pergunta"], todos))
            x["antes"] = {m: l[:FUNDO] for m, l in antes.items()}
            x["depois"] = {m: sorted(l[:N_CAND], key=lambda cid: -nota[cid])[:10] for m, l in antes.items()}
        gravar(LISTAS, guardado)
        print(nome, "pronto:", len(itens), flush=True)


# ---------------------------------------------------------------- 3b. a posição exata de cada trecho certo
def posicoes() -> None:
    """Para cada trecho certo do gabarito do Opus, a posição exata dele na lista da pergunta (P) e na da resposta
    imaginária (H), sem cortar em 100. Serve para ver se a técnica aproxima o trecho que a busca de hoje perde."""
    import numpy as np
    b = Busca()
    textos = ler(TEXTOS)
    saida = {}
    for nome in ("opus", "opus-curta"):
        for it in conjuntos()[nome]:
            vp = b.modelo.vetor_pergunta(it["pergunta"])
            vh = b.modelo.modelo.encode([textos[nome][it["id"]]["hyde"]], normalize_embeddings=True, convert_to_numpy=True)[0]
            x = {}
            for sigla, v in (("P", vp), ("H", vh)):
                v = np.asarray(v, dtype=np.float64).ravel()
                ordem = np.argsort(-(b.E @ (v / np.linalg.norm(v))), kind="stable")
                pos = {b.ids[j]: k + 1 for k, j in enumerate(ordem)}
                x[sigla] = {c: pos[c] for c in sorted(it["certos"])}
            saida.setdefault(nome, {})[it["id"]] = x
    gravar(POSICOES, saida)
    print("posições gravadas:", {k: len(v) for k, v in saida.items()})


# ---------------------------------------------------------------- 5. quem o reranker lê, e quantos candidatos
# Segunda medida, pedida depois do resultado da primeira. Duas coisas mudam, uma de cada vez (desenho 2 x 2):
#   candidatos: os 50 da pergunta (hoje)  ou  os 50 da pergunta mais os 50 da resposta imaginária (até 100)
#   leitor:     o reranker lê a pergunta digitada (hoje)  ou  lê a resposta imaginária no lugar dela
NOTAS = AQUI / "cache" / "hyde-notas.json"         # fora do Git: nota do reranker por par (texto lido, trecho)
LIMITE = 512                                       # o reranker lê no máximo 512 pedaços de palavra (tokens) por par
CELULAS = {"P50|pergunta": "50 da pergunta, lê a pergunta (hoje)", "P50|imaginaria": "50 da pergunta, lê a imaginária",
           "UNIAO|pergunta": "50 + 50, lê a pergunta", "UNIAO|imaginaria": "50 + 50, lê a imaginária"}
HOJE = "P50|pergunta"


def candidatos(x: dict, quais: str) -> list[str]:
    """P50: os 50 primeiros da pergunta. UNIAO: esses e os 50 primeiros da resposta imaginária, sem repetir."""
    p50 = x["antes"]["P"][:N_CAND]
    return p50 if quais == "P50" else list(dict.fromkeys(p50 + x["antes"]["H"][:N_CAND]))


def contar_leitor() -> None:
    """O que dá para contar antes de prever: o teto dos candidatos e quanto do trecho o reranker deixa de ler."""
    import consultar
    por = mv.chunks_por_id()
    tok = consultar._reranker(consultar.RERANKER).tokenizer
    n_tok = lambda t: len(tok.encode(t, add_special_tokens=False))
    tam_chunk = {cid: n_tok(c["texto_indexado"]) for cid, c in por.items()}
    guardado, textos = ler(LISTAS), ler(TEXTOS)
    L = ["QUEM O RERANKER LÊ, E QUANTOS CANDIDATOS: O QUE SE CONTA ANTES DE PREVER. Contagem, sem modelo treinado.",
         f"O reranker (mMiniLM) lê pares (texto, trecho) de até {LIMITE} tokens; o que passa disso é cortado do lado mais longo.",
         "Gabarito do Opus, de modelo, sem conferência humana.", ""]
    for nome in ("opus", "opus-curta"):
        itens = conjuntos()[nome]
        g = guardado[nome]
        tot = sum(len(i["certos"]) for i in itens)
        c_p = sum(len(i["certos"] & set(candidatos(g[i["id"]], "P50"))) for i in itens)
        c_u = sum(len(i["certos"] & set(candidatos(g[i["id"]], "UNIAO"))) for i in itens)
        n_u = [len(candidatos(g[i["id"]], "UNIAO")) for i in itens]
        L += [f"===== {nome.upper()}: {len(itens)} perguntas, {tot} trechos certos =====",
              f"trechos certos entre os candidatos: {c_p} com os 50 da pergunta | {c_u} com os 50 + 50 (teto do ganho: {c_u - c_p})",
              f"candidatos por pergunta com 50 + 50, sem repetir: de {min(n_u)} a {max(n_u)}, mediana {mv.mediana(n_u)}"]
        for leitor in ("pergunta", "imaginaria"):
            lido = [n_tok(i["pergunta"] if leitor == "pergunta" else textos[nome][i["id"]]["hyde"]) for i in itens]
            cortados = total = 0
            fracoes = []
            for i, lq in zip(itens, lido):
                for cid in candidatos(g[i["id"]], "UNIAO"):
                    lc = tam_chunk[cid]
                    sobra = max(0, lq + lc + 4 - LIMITE)             # 4 tokens de marcação por par
                    corte_chunk = min(sobra, max(0, lc - lq)) + max(0, sobra - max(0, lc - lq) + 1) // 2 if sobra else 0
                    total += 1
                    cortados += sobra > 0
                    fracoes.append((lc - corte_chunk) / lc)
            L.append(f"o reranker lê a {leitor:10s}: texto lido de {min(lido)} a {max(lido)} tokens (mediana {mv.mediana(lido)}); "
                     f"pares cortados: {cortados} de {total} ({100 * cortados / total:.0f}%); fração do trecho lida, mediana "
                     f"{mv.mediana(fracoes):.2f}, pior caso {min(fracoes):.2f}")
        L.append("")
    tc = sorted(tam_chunk.values())
    L += [f"Tamanho dos {len(tc)} trechos da base, em tokens do reranker: mediana {mv.mediana(tc)}, máximo {tc[-1]}; "
          f"acima de {LIMITE - 4}: {sum(t > LIMITE - 4 for t in tc)}.",
          "Leitura: trocar a pergunta pela resposta imaginária dá ao reranker um texto mais longo e deixa menos espaço para o trecho."]
    (SAIDAS / "30-teto-leitor-do-reranker.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def notas_leitor() -> None:
    """A nota do reranker para cada candidato da união, com cada leitor. Guarda em cache/ e continua de onde parou."""
    import time
    import consultar
    guardado, textos = ler(LISTAS), ler(TEXTOS)
    notas = ler(NOTAS, {})
    consultar.reranquear("aquecimento", guardado["opus"]["Q01"]["antes"]["P"][:8])     # carrega o modelo fora do cronômetro
    for nome, itens in conjuntos().items():
        n = notas.setdefault(nome, {})
        for it in itens:
            if it["id"] in n:
                continue
            x = guardado[nome][it["id"]]
            uniao = candidatos(x, "UNIAO")
            lido = {"pergunta": it["pergunta"], "imaginaria": textos[nome][it["id"]]["hyde"]}
            reg = {"ms": {}}
            for leitor, texto in lido.items():
                t = time.perf_counter()
                reg[leitor] = dict(consultar.reranquear(texto, uniao))
                reg["ms"][leitor] = 1000 * (time.perf_counter() - t)
            reg["n_uniao"] = len(uniao)
            n[it["id"]] = reg
        gravar(NOTAS, notas)
        print(nome, "pronto:", len(itens), flush=True)


def entregues(x: dict, nota: dict, celula: str) -> list[str]:
    """Os 10 primeiros de uma célula: os candidatos dela, na ordem da nota do leitor dela (empate fica na ordem de chegada)."""
    quais, leitor = celula.split("|")
    return sorted(candidatos(x, quais), key=lambda cid: -nota[leitor][cid])[:10]


def medir_leitor() -> None:
    por = mv.chunks_por_id()
    guardado, notas = ler(LISTAS), ler(NOTAS)
    julg = mv.julgados_rascunho()
    cj = conjuntos()
    L = ["QUEM O RERANKER LÊ, E QUANTOS CANDIDATOS. Gabaritos de modelo, sem conferência humana. Nenhum modelo treinado.",
         "Candidatos: os 50 da pergunta (hoje), ou esses mais os 50 da resposta imaginária, sem repetir ('50 + 50').",
         "Leitor: o reranker lê a pergunta digitada (hoje), ou a resposta imaginária no lugar dela. Em todos os casos entrega 5.",
         "Técnica: modelos prontos (Qwen3, reranker mMiniLM; resposta imaginária escrita pelo Claude haiku, que não é o modelo do",
         f"produto), contagem e sorteio. Bootstrap de 95%: {mv.N_BOOT} sorteios de perguntas, semente {mv.SEMENTE}. "
         f"Acaso no recall@5: {5 / len(por):.3f}.", ""]
    dif, nj_tudo = {}, {}
    for nome, itens in cj.items():
        g, nt = guardado[nome], notas[nome]
        n = len(itens)
        certos = [i["certos"] for i in itens]
        tot = sum(len(c) for c in certos)
        listas = {c: [entregues(g[i["id"]], nt[i["id"]], c) for i in itens] for c in CELULAS}
        igual = sum(listas[HOJE][j][:5] == g[itens[j]["id"]]["depois"]["P"][:5] for j in range(n))
        fim = {c: [avaliar.metricas_pergunta(l, cs) for l, cs in zip(listas[c], certos)] for c in CELULAS}
        aviso = " (EXPLORATÓRIO: perguntas encurtadas por modelo)" if nome == "opus-curta" else ""
        L += [f"===== {nome.upper()}: {n} perguntas, {tot} trechos certos; uma pergunta vale {100 / n:.1f} pontos{aviso} =====",
              f"conferência: a célula de hoje devolve os mesmos 5 trechos da medida anterior (outputs/29) em {igual} de {n} perguntas",
              f"{'combinação':38s}{'certos nos candidatos':>23s} |{'recall@5 final':>22s}{'ao menos 1 certo nos 5':>24s}{'MRR':>7s}{'ms':>7s}"]
        for c, rot in CELULAS.items():
            quais, leitor = c.split("|")
            cc = sum(len(cs & set(candidatos(g[i["id"]], quais))) for i, cs in zip(itens, certos))
            v = [p["recall@5"] for p in fim[c]]
            lo, hi = avaliar.bootstrap(v)
            acerto = sum(bool(cs & set(l[:5])) for l, cs in zip(listas[c], certos))
            # tempo: a nota foi calculada sobre a união; para os 50 da pergunta, o tempo é proporcional ao número de pares
            ms = mv.mediana([nt[i["id"]]["ms"][leitor] * (len(candidatos(g[i["id"]], quais)) / nt[i["id"]]["n_uniao"]) for i in itens])
            L.append(f"{rot:38s}{cc:>16d} de {tot:<3d} |{f'{mv.media(v):.2f} [{lo:.2f}-{hi:.2f}]':>22s}"
                     f"{acerto:>17d} de {n}{mv.media(p['MRR'] for p in fim[c]):7.2f}{ms:7.0f}")
        L += ["  (ms: tempo mediano só do reranker neste Mac; para os 50 da pergunta é estimado pela proporção de pares lidos)", "",
              "A matriz 2 x 2 do recall@5 final:",
              f"{'':34s}{'lê a pergunta':>16s}{'lê a imaginária':>18s}",
              f"{'candidatos: 50 da pergunta':34s}{mv.media(p['recall@5'] for p in fim['P50|pergunta']):16.2f}{mv.media(p['recall@5'] for p in fim['P50|imaginaria']):18.2f}",
              f"{'candidatos: 50 + 50':34s}{mv.media(p['recall@5'] for p in fim['UNIAO|pergunta']):16.2f}{mv.media(p['recall@5'] for p in fim['UNIAO|imaginaria']):18.2f}",
              "", "Diferença pareada contra a busca de hoje (combinação menos hoje), IC 95%, perguntas em que ganhou/empatou/perdeu:"]
        for c, rot in list(CELULAS.items())[1:]:
            f = mv.diferenca([p["recall@5"] for p in fim[c]], [p["recall@5"] for p in fim[HOJE]])
            dif[(nome, c)] = f
            L.append(f"{rot:38s} recall@5 final {f[0]:+.2f} [{f[1]:+.2f} a {f[2]:+.2f}] {f[3]}/{f[4]}/{f[5]}")
        L.append("")
        if nome.startswith("opus"):
            L += ["Recall@5 final por tipo de pergunta (todos os recortes que o gabarito permite):",
                  f"{'tipo':30s}" + "".join(f"{c:>18s}" for c in CELULAS)]
            for t in dict.fromkeys(i["tipo"] for i in itens):
                ix = [j for j, i in enumerate(itens) if i["tipo"] == t]
                L.append(f"{t + ' (n=' + str(len(ix)) + ')':30s}" + "".join(f"{mv.media(fim[c][j]['recall@5'] for j in ix):18.2f}" for c in CELULAS))
            ix = [j for j, i in enumerate(itens) if i["id"] in PRATICAS]
            tt = sum(len(certos[j]) for j in ix)
            L += ["", f"As 10 perguntas práticas de professor ({tt} trechos certos): certos nos 5 entregues, por combinação:"]
            for c, rot in CELULAS.items():
                c5 = sum(len(certos[j] & set(listas[c][j][:5])) for j in ix)
                zero = [itens[j]["id"] for j in ix if not certos[j] & set(listas[c][j][:5])]
                L.append(f"  {rot:38s} {c5:2d} de {tt} | perguntas sem nenhum certo nos 5: {', '.join(zero) or '-'}")
            L.append("")
        if nome == "rascunho" and julg is not None:
            L.append("Vagas dos 5 entregues ocupadas por trecho que nenhum juiz do rascunho leu (acima de 10% a comparação não vale):")
            for c, rot in CELULAS.items():
                nj = sum(x not in julg[int(i["id"][1:])] for i, l in zip(itens, listas[c]) for x in l[:5])
                nj_tudo[c] = nj
                L.append(f"  {rot:38s} {nj:3d} de {5 * n} ({100 * nj / (5 * n):.0f}%)")
            L.append("")
    L += ["CRITÉRIO (escrito antes de rodar): passa a combinação cujo recall@5 final menos o de hoje tem o intervalo todo acima de zero",
          "no gabarito do Opus, com as perguntas como estão. As perguntas encurtadas têm veredito próprio, exploratório. O rascunho só",
          "conta com até 10% de vagas não julgadas. Passar não muda o padrão do produto."]
    n_r = len(cj["rascunho"])
    for c, rot in list(CELULAS.items())[1:]:
        o, r, k = dif[("opus", c)], dif[("rascunho", c)], dif[("opus-curta", c)]
        comparavel = c in nj_tudo and nj_tudo[c] <= 0.10 * 5 * n_r
        if o[1] <= 0:
            v = "NÃO PASSA (o intervalo encosta, passa pelo zero ou fica abaixo dele)"
        elif not comparavel:
            v = "PASSA NO OPUS; rascunho não comparável"
        elif r[2] < 0:
            v = "NÃO PASSA (piora no rascunho)"
        else:
            v = "PASSA"
        L += [f"{rot:38s} Opus {o[0]:+.2f} [{o[1]:+.2f} a {o[2]:+.2f}]; rascunho {r[0]:+.2f} [{r[1]:+.2f} a {r[2]:+.2f}], "
              f"não julgados {nj_tudo.get(c, '-')} de {5 * n_r}: {v}",
              f"{'':38s} perguntas curtas {k[0]:+.2f} [{k[1]:+.2f} a {k[2]:+.2f}]: "
              + ("PASSA (exploratório)" if k[1] > 0 else "PIORA (o intervalo fica todo abaixo de zero)" if k[2] < 0
                 else "NÃO PASSA (o intervalo encosta ou passa pelo zero)")]
    (SAIDAS / "31-leitor-do-reranker.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 6. o comprimento do trecho explica o que a busca perde?
LONGO = LIMITE - 4                                 # acima disso o trecho não cabe inteiro no reranker nem sozinho


def intervalo_dif(a: list[float], b: list[float], f) -> tuple[float, float, float]:
    """f(a) menos f(b), com intervalo de 95%: sorteia os trechos de cada grupo, com reposição, N_BOOT vezes."""
    import random
    rnd = random.Random(mv.SEMENTE)
    ds = sorted(f([rnd.choice(a) for _ in a]) - f([rnd.choice(b) for _ in b]) for _ in range(mv.N_BOOT))
    return f(a) - f(b), ds[int(.025 * mv.N_BOOT)], ds[int(.975 * mv.N_BOOT) - 1]


def comprimento() -> None:
    import consultar
    from collections import Counter
    por = mv.chunks_por_id()
    tok_r = consultar._reranker(consultar.RERANKER).tokenizer
    tok_q = consultar._modelo("qwen3").modelo.tokenizer
    nr = lambda t: len(tok_r.encode(t, add_special_tokens=False))
    tam = {cid: nr(c["texto_indexado"]) for cid, c in por.items()}
    cab = {cid: tam[cid] - nr(c["texto"]) for cid, c in por.items()}
    tam_q = {cid: len(tok_q.encode(c["texto_indexado"], add_special_tokens=False)) for cid, c in por.items()}
    longo = lambda cid: tam[cid] > LONGO
    parte = lambda xs: sum(xs) / len(xs)
    guardado = ler(LISTAS)
    cj = conjuntos()
    base = sorted(tam.values())
    L = ["O COMPRIMENTO DO TRECHO EXPLICA O QUE A BUSCA PERDE? Contagem. Nenhum modelo treinado, nenhum modelo de linguagem chamado.",
         f"Comprimento = tokens do reranker (mMiniLM) no trecho com o cabeçalho. Longo = mais de {LONGO} tokens: não cabe inteiro",
         f"no reranker, que lê {LIMITE} por par. Busca de hoje: Qwen3 com a pergunta (conta exata) e reranker sobre os 50.",
         f"Intervalos de 95%: {mv.N_BOOT} sorteios dos trechos de cada grupo, semente {mv.SEMENTE}. Gabarito do Opus, de modelo.", "",
         f"A BASE: {len(base)} trechos; mediana {mv.mediana(base)} tokens, de {base[0]} a {base[-1]}; longos: {sum(t > LONGO for t in base)} "
         f"({100 * parte([t > LONGO for t in base]):.0f}%).",
         f"Cabeçalho (Documento e Seção) que vai na frente de cada trecho: mediana {mv.mediana(list(cab.values()))} tokens, máximo {max(cab.values())}.",
         f"Tokens por palavra: português {mv.media(tam[c] / max(por[c]['n_palavras'], 1) for c in por if por[c]['idioma'] != 'en'):.2f}, "
         f"inglês {mv.media(tam[c] / max(por[c]['n_palavras'], 1) for c in por if por[c]['idioma'] == 'en'):.2f} "
         f"(com o cabeçalho). Mediana de palavras por trecho: {mv.mediana([c['n_palavras'] for c in por.values()])}.",
         f"No Qwen3, que faz os vetores e lê até 1.024 tokens dele: maior trecho {max(tam_q.values())} tokens; acima de 1.024: "
         f"{sum(t > 1024 for t in tam_q.values())}.", ""]
    # ---- 1. o destino de cada trecho certo do Opus, com as perguntas como estão
    itens = cj["opus"]
    g = guardado["opus"]
    grupos = {"entregue entre os 5": [], "entre os 50, não entregue": [], "fora dos 50": []}
    cortado = {True: [], False: []}                      # par cortado -> lista de "foi entregue?" (só trechos certos entre os 50)
    for it in itens:
        x = g[it["id"]]
        p50, e5 = set(x["antes"]["P"][:N_CAND]), set(x["depois"]["P"][:5])
        lq = nr(it["pergunta"])
        for c in sorted(it["certos"]):
            destino = "entregue entre os 5" if c in e5 else "entre os 50, não entregue" if c in p50 else "fora dos 50"
            grupos[destino].append(c)
            if c in p50:
                cortado[lq + tam[c] + 4 > LIMITE].append(c in e5)
    dentro = grupos["entregue entre os 5"] + grupos["entre os 50, não entregue"]
    L += [f"1. OS {sum(len(v) for v in grupos.values())} TRECHOS CERTOS DO OPUS, PELO DESTINO NA BUSCA DE HOJE (38 perguntas como estão)",
          f"{'destino':30s}{'trechos':>9s}{'mediana de tokens':>19s}{'longos':>10s}{'% longos':>10s}{'mediana de palavras':>21s}"]
    for rot, cs in [*grupos.items(), ("(entre os 50, somados)", dentro), ("(a base inteira)", list(por))]:
        L.append(f"{rot:30s}{len(cs):9d}{mv.mediana([tam[c] for c in cs]):19d}{sum(longo(c) for c in cs):10d}"
                 f"{100 * parte([longo(c) for c in cs]):9.0f}%{mv.mediana([por[c]['n_palavras'] for c in cs]):21d}")
    fora = grupos["fora dos 50"]
    d1 = intervalo_dif([float(longo(c)) for c in fora], [float(longo(c)) for c in dentro], parte)
    d2 = intervalo_dif([tam[c] for c in fora], [tam[c] for c in dentro], mv.mediana)
    d3 = intervalo_dif([float(longo(c)) for c in grupos["entre os 50, não entregue"]],
                       [float(longo(c)) for c in grupos["entregue entre os 5"]], parte)
    L += ["", f"fora dos 50 menos entre os 50: parte de longos {100 * d1[0]:+.0f} pontos [{100 * d1[1]:+.0f} a {100 * d1[2]:+.0f}]; "
              f"mediana de tokens {d2[0]:+.0f} [{d2[1]:+.0f} a {d2[2]:+.0f}]",
          f"entre os 50: não entregue menos entregue: parte de longos {100 * d3[0]:+.0f} pontos [{100 * d3[1]:+.0f} a {100 * d3[2]:+.0f}]", "",
          "2. O RERANKER E O CORTE: trechos certos que estavam entre os 50 candidatos (matriz)",
          f"{'':34s}{'entregue entre os 5':>21s}{'não entregue':>14s}{'% entregue':>12s}"]
    for rot, k in (("par cortado (não lê o fim)", True), ("par não cortado (lê inteiro)", False)):
        v = cortado[k]
        L.append(f"{rot:34s}{sum(v):21d}{len(v) - sum(v):14d}{100 * parte(v):11.0f}%")
    d4 = intervalo_dif([float(x) for x in cortado[True]], [float(x) for x in cortado[False]], parte)
    L += [f"cortado menos não cortado: {100 * d4[0]:+.0f} pontos [{100 * d4[1]:+.0f} a {100 * d4[2]:+.0f}]", "",
          "3. CADA ETAPA PREFERE OU EVITA TRECHO LONGO? Não depende do gabarito: todas as vagas, nas 57 perguntas dos dois conjuntos",
          f"{'onde':46s}{'vagas':>8s}{'% longos':>10s}{'mediana de tokens':>19s}"]
    vagas = {"os 5 primeiros do Qwen3 (sem reranker)": [], "os 50 candidatos do Qwen3": [], "os 5 entregues (depois do reranker)": []}
    for nome in ("opus", "rascunho"):
        for it in cj[nome]:
            x = guardado[nome][it["id"]]
            vagas["os 5 primeiros do Qwen3 (sem reranker)"] += x["antes"]["P"][:5]
            vagas["os 50 candidatos do Qwen3"] += x["antes"]["P"][:N_CAND]
            vagas["os 5 entregues (depois do reranker)"] += x["depois"]["P"][:5]
    L.append(f"{'a base inteira':46s}{len(por):8d}{100 * parte([longo(c) for c in por]):9.0f}%{mv.mediana(base):19d}")
    for rot, cs in vagas.items():
        L.append(f"{rot:46s}{len(cs):8d}{100 * parte([longo(c) for c in cs]):9.0f}%{mv.mediana([tam[c] for c in cs]):19d}")
    # o que o reranker faz com os candidatos longos e curtos: de cada 50 candidatos, a parte que vira entregue
    lg = [c in set(guardado[n][it["id"]]["depois"]["P"][:5]) for n in ("opus", "rascunho") for it in cj[n]
          for c in guardado[n][it["id"]]["antes"]["P"][:N_CAND] if longo(c)]
    ct = [c in set(guardado[n][it["id"]]["depois"]["P"][:5]) for n in ("opus", "rascunho") for it in cj[n]
          for c in guardado[n][it["id"]]["antes"]["P"][:N_CAND] if not longo(c)]
    d5 = intervalo_dif([float(x) for x in lg], [float(x) for x in ct], parte)
    L += [f"dos candidatos longos, o reranker entrega {100 * parte(lg):.1f}% ({sum(lg)} de {len(lg)}); dos que cabem inteiros, "
          f"{100 * parte(ct):.1f}% ({sum(ct)} de {len(ct)}); se não olhasse o comprimento, seriam 10% dos dois.",
          f"longos menos os que cabem: {100 * d5[0]:+.1f} pontos [{100 * d5[1]:+.1f} a {100 * d5[2]:+.1f}]", "",
          "4. ONDE ESTÃO OS TRECHOS LONGOS (defeito se espalha; fenômeno se concentra)",
          f"{'documento':52s}{'idioma':>8s}{'longos':>8s}{'de':>6s}{'% do doc':>10s}"]
    por_doc, tot_doc = Counter(mv.doc(c) for c in por if longo(c)), Counter(mv.doc(c) for c in por)
    for d, n in por_doc.most_common(8):
        L.append(f"{d[:50]:52s}{next(por[c]['idioma'] for c in por if mv.doc(c) == d):>8s}{n:8d}{tot_doc[d]:6d}{100 * n / tot_doc[d]:9.0f}%")
    top3 = sum(n for _, n in por_doc.most_common(3))
    en = [c for c in por if por[c]["idioma"] == "en"]
    L += [f"os 3 documentos com mais trechos longos têm {top3} dos {sum(por_doc.values())} ({100 * top3 / sum(por_doc.values()):.0f}%); "
          f"documentos com algum trecho longo: {len(por_doc)} de {len(tot_doc)}.",
          f"por idioma: inglês {100 * parte([longo(c) for c in en]):.0f}% de longos ({len(en)} trechos); "
          f"português {100 * parte([longo(c) for c in por if c not in set(en)]):.0f}% ({len(por) - len(en)} trechos).",
          "por tipo de corte: " + "; ".join(f"{t} {100 * parte([longo(c) for c in por if por[c]['tipo_corte'] == t]):.0f}% "
                                            f"({sum(por[c]['tipo_corte'] == t for c in por)})" for t in sorted({c['tipo_corte'] for c in por.values()}))]
    (SAIDAS / "32-comprimento-dos-trechos.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 4. medir
def medir() -> None:
    por = mv.chunks_por_id()
    guardado = ler(LISTAS)
    julg = mv.julgados_rascunho()
    cj = conjuntos()
    L = ["RESPOSTA IMAGINÁRIA (HyDE) E REESCRITA DA PERGUNTA, NA PRIMEIRA ETAPA DA BUSCA. Gabaritos de modelo, sem conferência humana.",
         "P pergunta (a busca de hoje) | H resposta imaginária sozinha | PH pergunta + resposta imaginária | R pergunta + 3 reescritas.",
         f"Depois de cada uma, o mesmo reranker lê os {N_CAND} primeiros com a pergunta digitada e entrega 5.",
         f"Técnica: modelos prontos (Qwen3, reranker mMiniLM; textos escritos pelo Claude {ESCRITOR}, que não é o modelo configurado no protótipo),",
         f"contagem e sorteio. Busca pela conta exata do cosseno. Bootstrap de 95%: {mv.N_BOOT} sorteios de perguntas, semente {mv.SEMENTE}.",
         f"Acaso no recall@5: {5 / len(por):.3f} (5 de {len(por)} trechos). Nenhum modelo treinado.", ""]
    dif, nj_tudo = {}, {}
    for nome, itens in cj.items():
        g = guardado[nome]
        n = len(itens)
        certos = [i["certos"] for i in itens]
        tot = sum(len(c) for c in certos)
        r50 = {m: [len(c & set(g[i["id"]]["antes"][m][:N_CAND])) / len(c) for i, c in zip(itens, certos)] for m in BRACOS}
        fim = {m: [avaliar.metricas_pergunta(g[i["id"]]["depois"][m], c) for i, c in zip(itens, certos)] for m in BRACOS}
        aviso = " (EXPLORATÓRIO: perguntas encurtadas por modelo)" if nome == "opus-curta" else ""
        L += [f"===== {nome.upper()}: {n} perguntas, {tot} trechos certos; uma pergunta vale {100 / n:.1f} pontos{aviso} =====",
              f"{'técnica':28s}{'certos nos 50':>15s}{'recall@50':>11s} |{'recall@5 final':>22s}{'ao menos 1 certo nos 5':>24s}{'MRR':>7s}"]
        for m in BRACOS:
            c50 = sum(len(c & set(g[i["id"]]["antes"][m][:N_CAND])) for i, c in zip(itens, certos))
            v = [p["recall@5"] for p in fim[m]]
            lo, hi = avaliar.bootstrap(v)
            acerto = sum(bool(c & set(g[i["id"]]["depois"][m][:5])) for i, c in zip(itens, certos))
            L.append(f"{NOME[m]:28s}{c50:>8d} de {tot:<3d}{mv.media(r50[m]):11.2f} |{f'{mv.media(v):.2f} [{lo:.2f}-{hi:.2f}]':>22s}"
                     f"{acerto:>17d} de {n}{mv.media(p['MRR'] for p in fim[m]):7.2f}")
        # coluna acrescentada DEPOIS de ver o resultado (não estava na expectativa): os 5 primeiros de cada lista sem o reranker
        sem = {m: [avaliar.metricas_pergunta(g[i["id"]]["antes"][m], c)["recall@5"] for i, c in zip(itens, certos)] for m in BRACOS}
        L += ["", "Sem o reranker (os 5 primeiros da própria lista). Não previsto antes de rodar; descreve, não decide:"]
        for m in BRACOS:
            d = mv.diferenca(sem[m], sem["P"])
            L.append(f"{NOME[m]:28s} recall@5 sem reranker {mv.media(sem[m]):.2f}"
                     + ("" if m == "P" else f" | menos P: {d[0]:+.2f} [{d[1]:+.2f} a {d[2]:+.2f}] {d[3]}/{d[4]}/{d[5]}"))
        L += ["", "Diferença pareada contra P (técnica menos P), IC 95%, perguntas em que ganhou/empatou/perdeu:"]
        for m in BRACOS[1:]:
            a = mv.diferenca(r50[m], r50["P"])
            f = mv.diferenca([p["recall@5"] for p in fim[m]], [p["recall@5"] for p in fim["P"]])
            dif[(nome, m, "r50")], dif[(nome, m, "r5")] = a, f
            L.append(f"{NOME[m]:28s} recall@50 {a[0]:+.2f} [{a[1]:+.2f} a {a[2]:+.2f}] {a[3]}/{a[4]}/{a[5]}"
                     f" | recall@5 final {f[0]:+.2f} [{f[1]:+.2f} a {f[2]:+.2f}] {f[3]}/{f[4]}/{f[5]}")
        L.append("")
        if nome.startswith("opus"):
            L += ["Recall@5 final por tipo de pergunta (todos os recortes que o gabarito permite), e certos nos 50 entre parênteses:",
                  f"{'tipo':20s}" + "".join(f"{m:>16s}" for m in BRACOS)]
            for t in dict.fromkeys(i["tipo"] for i in itens):
                ix = [j for j, i in enumerate(itens) if i["tipo"] == t]
                tt = sum(len(certos[j]) for j in ix)
                L.append(f"{t + ' (n=' + str(len(ix)) + ', ' + str(tt) + ' certos)':20s}" + "".join(
                    f"{mv.media(fim[m][j]['recall@5'] for j in ix):10.2f} ({sum(len(certos[j] & set(g[itens[j]['id']]['antes'][m][:N_CAND])) for j in ix):2d})"
                    for m in BRACOS))
            ix = [j for j, i in enumerate(itens) if i["id"] in PRATICAS]
            tt = sum(len(certos[j]) for j in ix)
            L += ["", f"As 10 perguntas práticas de professor ({tt} trechos certos): certos nos 50 e certos nos 5 entregues, por técnica:"]
            for m in BRACOS:
                c50 = sum(len(certos[j] & set(g[itens[j]["id"]]["antes"][m][:N_CAND])) for j in ix)
                c5 = sum(len(certos[j] & set(g[itens[j]["id"]]["depois"][m][:5])) for j in ix)
                zero = [itens[j]["id"] for j in ix if not certos[j] & set(g[itens[j]["id"]]["depois"][m][:5])]
                L.append(f"  {NOME[m]:28s} nos 50: {c50:2d} de {tt} | nos 5: {c5:2d} de {tt} | perguntas sem nenhum certo nos 5: {', '.join(zero) or '-'}")
            L.append("")
            # a matriz: cada trecho certo, cruzando "a pergunta alcança" com "a resposta imaginária alcança" (50 primeiros)
            em = lambda j, m: certos[j] & set(g[itens[j]["id"]]["antes"][m][:N_CAND])
            for rot, quais in (("todas as perguntas", range(n)), ("só as 10 práticas", ix)):
                dois = sum(len(em(j, "P") & em(j, "H")) for j in quais)
                so_p = sum(len(em(j, "P") - em(j, "H")) for j in quais)
                so_h = sum(len(em(j, "H") - em(j, "P")) for j in quais)
                tq = sum(len(certos[j]) for j in quais)
                L += [f"Matriz dos {tq} trechos certos ({rot}): quem alcança cada um entre os seus 50 primeiros",
                      f"{'':34s}{'imaginária alcança':>20s}{'imaginária não alcança':>24s}",
                      f"{'a pergunta alcança':34s}{dois:20d}{so_p:24d}",
                      f"{'a pergunta não alcança':34s}{so_h:20d}{tq - dois - so_p - so_h:24d}",
                      f"  lendo os 50 de cada uma (até 100 candidatos), o teto seria {dois + so_p + so_h} de {tq}; "
                      f"{tq - dois - so_p - so_h} não aparecem em nenhuma das duas listas", ""]
            pos = (ler(POSICOES) or {}).get(nome)
            if pos:
                fora = [(pos[itens[j]["id"]]["P"][c], pos[itens[j]["id"]]["H"][c]) for j in range(n) for c in certos[j]
                        if pos[itens[j]["id"]]["P"][c] > N_CAND]
                sobe = sum(h < p_ for p_, h in fora)
                L += [f"Os {len(fora)} trechos certos que a pergunta deixa fora dos 50: posição mediana com a pergunta "
                      f"{mv.mediana([p_ for p_, _ in fora])}, com a resposta imaginária {mv.mediana([h for _, h in fora])}; "
                      f"{sobe} sobem de posição, {sum(h <= N_CAND for _, h in fora)} entram nos 50.",
                      f"Posição exata de cada trecho certo nas 10 perguntas práticas (de {len(por)} trechos), pergunta | resposta imaginária:"]
                for j in ix:
                    q = itens[j]["id"]
                    pares = sorted((pos[q]["P"][c], pos[q]["H"][c]) for c in certos[j])
                    L.append(f"  {q}  P: {', '.join(str(a_) for a_, _ in pares):32s} | H: {', '.join(str(h) for _, h in pares)}")
                L.append("")
        if nome == "rascunho" and julg is not None:
            L.append("Vagas dos 5 entregues ocupadas por trecho que nenhum juiz do rascunho leu (acima de 10% a comparação não vale):")
            for m in BRACOS:
                nj = sum(x not in julg[int(i["id"][1:])] for i in itens for x in g[i["id"]]["depois"][m][:5])
                nj_tudo[m] = nj
                L.append(f"  {NOME[m]:28s} {nj:3d} de {5 * n} ({100 * nj / (5 * n):.0f}%)")
            L.append("")
    L += ["CRITÉRIO (escrito antes de gerar os textos): passa a técnica cujo recall@5 final menos o de P tem o intervalo todo",
          "acima de zero no gabarito do Opus (perguntas como estão) e não tem o intervalo todo abaixo de zero no rascunho. O rascunho",
          "só conta se até 10% das vagas dos 5 entregues forem de trecho nunca julgado. Passar não muda o padrão do produto: a técnica",
          "vira candidata, porque custa uma chamada de modelo a mais por pergunta e os gabaritos não têm conferência humana.",
          "O recorte das perguntas curtas tem veredito próprio, pelo mesmo intervalo, e vale como exploratório."]
    n_r = len(cj["rascunho"])
    for m in BRACOS[1:]:
        o, r = dif[("opus", m, "r5")], dif[("rascunho", m, "r5")]
        comparavel = m in nj_tudo and nj_tudo[m] <= 0.10 * 5 * n_r
        if o[1] <= 0:
            v = "NÃO PASSA (no Opus o intervalo encosta ou passa pelo zero)"
        elif not comparavel:
            v = "PASSA NO OPUS; rascunho não comparável"
        elif r[2] < 0:
            v = "NÃO PASSA (piora no rascunho)"
        else:
            v = "PASSA"
        L.append(f"{NOME[m]:28s} Opus {o[0]:+.2f} [{o[1]:+.2f} a {o[2]:+.2f}]; rascunho {r[0]:+.2f} [{r[1]:+.2f} a {r[2]:+.2f}], "
                 f"não julgados {nj_tudo.get(m, '-')} de {5 * n_r}: {v}")
        if "opus-curta" in cj:
            c = dif[("opus-curta", m, "r5")]
            L.append(f"{'':28s} perguntas curtas {c[0]:+.2f} [{c[1]:+.2f} a {c[2]:+.2f}]: "
                     f"{'PASSA (exploratório)' if c[1] > 0 else 'NÃO PASSA (o intervalo encosta ou passa pelo zero)'}")
    if "opus-curta" in cj:
        lon = [avaliar.metricas_pergunta(guardado["opus"][i["id"]]["depois"]["P"], i["certos"])["recall@5"] for i in cj["opus"]]
        cur = [avaliar.metricas_pergunta(guardado["opus-curta"][i["id"]]["depois"]["P"], i["certos"])["recall@5"] for i in cj["opus-curta"]]
        x = mv.diferenca(cur, lon)
        L += ["", f"Quanto a busca de hoje perde quando a pergunta é curta (P curta menos P como está, recall@5 final): "
                  f"{x[0]:+.2f} [{x[1]:+.2f} a {x[2]:+.2f}] {x[3]}/{x[4]}/{x[5]}"]
        for m in BRACOS[1:]:
            ml = [avaliar.metricas_pergunta(guardado["opus-curta"][i["id"]]["depois"][m], i["certos"])["recall@5"] for i in cj["opus-curta"]]
            y = mv.diferenca(ml, lon)
            L.append(f"  {NOME[m]:28s} com a pergunta curta, contra P com a pergunta inteira: {y[0]:+.2f} [{y[1]:+.2f} a {y[2]:+.2f}]")
    (SAIDAS / "29-hyde-e-reescrita.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    {"contar": contar, "gerar": gerar, "ranquear": ranquear, "posicoes": posicoes, "medir": medir, "contar-leitor": contar_leitor, "notas-leitor": notas_leitor,
     "medir-leitor": medir_leitor, "comprimento": comprimento}[sys.argv[1]]()
