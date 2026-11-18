"""comparar_versoes.py: o RAG antigo contra o novo, no protocolo do relatório de 09/11/2026, com as métricas do RAGAS.

Qualquer pessoa do grupo reproduz em três passos (ver avaliacao_versoes/README.md):

    .venv/bin/python comparar_versoes.py gerar antigo     # Llama 3.1 8B local (Ollama), prompt de antes
    .venv/bin/python comparar_versoes.py gerar novo       # Haiku 5.5 pela API da Anthropic, prompt com esclarecimento
    .venv/bin/python comparar_versoes.py ragas antigo     # juiz do RAGAS: Sonnet 5.5 (IRIS_RAGAS_JUIZ)
    .venv/bin/python comparar_versoes.py ragas novo
    .venv/bin/python comparar_versoes.py relatorio        # outputs/40-comparacao-versoes.txt, só contagem

Perguntas: as 40 do relatório de 09/11 (gabarito/perguntas_v0.json; 38 com resposta na base, 2 sem) e as 25 fora da
base (gabarito/fora_da_base_v1.json). A busca é a mesma para as duas versões e é feita uma vez: o que muda é só quem
escreve e com que instrução. As respostas, os trechos entregues (chunk_id) e as notas de cada pergunta ficam em
avaliacao_versoes/; o passo `relatorio` refaz todos os números a partir desses arquivos, sem chamar modelo, e dá o mesmo
resultado em qualquer máquina. Gerar ou julgar de novo dá números próximos, não idênticos (os modelos não são
determinísticos); a diferença esperada está dentro dos intervalos de confiança.

Métricas (RAGAS 0.4, biblioteca `ragas`):
    Faithfulness       o que a resposta afirma está nos trechos entregues (juiz modelo)
    AnswerRelevancy    a resposta trata da pergunta (juiz modelo e vetores locais do Qwen3)
    IDBasedContextPrecision / IDBasedContextRecall   trechos entregues contra o gabarito de 09/11, por chunk_id, sem modelo
E as contagens do relatório de 09/11: recusa nas perguntas sem resposta, recusa indevida nas com resposta, citação de
trecho inexistente, frase sem citação. Nenhum modelo é treinado.
Custo: o juiz Sonnet 5.5 e o gerador Haiku cobram na ANTHROPIC_API_KEY; o roteiro soma os tokens e para no teto
(IRIS_RAGAS_TETO_DOLAR, padrão 8).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PASTA = AQUI / "avaliacao_versoes"
GABARITO = AQUI.parent / "gabarito"
SAIDA = AQUI / "outputs" / "40-comparacao-versoes.txt"
SEMENTE, N_BOOT, K = 20261118, 2000, 5

VERSOES = {
    "antigo": {"RAG_LLM": "ollama", "RAG_LLM_MODELO": "llama3.1:8b", "RAG_PROMPT_ESCLARECIMENTO": "off"},
    "novo": {"RAG_LLM": "anthropic", "RAG_LLM_MODELO": "claude-haiku-5-5", "RAG_PROMPT_ESCLARECIMENTO": "on"},
    # braço do reteste: o novo recebendo 20 trechos em vez de 5 (piloto de 17/11: úteis de 0,62 para 0,75)
    "novo20": {"RAG_LLM": "anthropic", "RAG_LLM_MODELO": "claude-haiku-5-5", "RAG_PROMPT_ESCLARECIMENTO": "on", "k": 20},
}
JUIZ = os.environ.get("IRIS_RAGAS_JUIZ", "claude-sonnet-5-5")
EMBEDDINGS = os.environ.get("IRIS_RAGAS_EMBEDDINGS", "Qwen/Qwen3-Embedding-0.6B")
# preço por milhão de tokens (entrada, saída), tabela da Anthropic; só para o teto e o registro do custo
PRECO = {"claude-sonnet-5-5": (3.0, 15.0), "claude-haiku-5-5": (1.0, 5.0)}
TETO = float(os.environ.get("IRIS_RAGAS_TETO_DOLAR", "8"))
GASTO = {"entrada": 0, "saida": 0, "modelo": JUIZ}


def _ler(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x] if p.exists() else []


def _gravar(p: Path, linhas: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in linhas), encoding="utf-8")


def perguntas() -> list[dict]:
    def lista(arq):
        d = json.loads((GABARITO / arq).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
    gab = {g["id"]: g for g in lista("gabarito_rascunho_v0.json")}
    out = []
    for p in lista("perguntas_v0.json"):
        g = gab.get(p["id"], {})
        rel = list(g.get("trechos_relevantes") or [])
        out.append({"id": p["id"], "pergunta": p["pergunta"], "tipo": p.get("tipo"), "tem_resposta": bool(rel),
                    "gabarito": rel})
    for p in lista("fora_da_base_v1.json"):
        out.append({"id": p["id"], "pergunta": p["pergunta"], "tipo": "fora_da_base", "tem_resposta": False, "gabarito": []})
    return out


CACHE = AQUI / "cache" / "comparar_versoes"     # fora do Git: guarda o texto dos trechos (parte da base não é distribuída)


def buscar_uma_vez(k: int = K) -> list[dict]:
    """A busca de hoje, uma vez para as duas versões (mesmos trechos para os dois geradores).

    Versionado: avaliacao_versoes/busca_ids.jsonl, só com os chunk_id. O texto dos trechos fica em cache/."""
    arq = CACHE / ("busca.jsonl" if k == K else f"busca_{k}.jsonl")
    if not arq.exists():
        import consultar
        linhas = []
        for p in perguntas():
            t = consultar.buscar(p["pergunta"], consultar.METODO_PADRAO, k=k)
            linhas.append({**p, "metodo": consultar.METODO_PADRAO, "trechos": t})
        _gravar(arq, linhas)
        _gravar(PASTA / ("busca_ids.jsonl" if k == K else f"busca_ids_{k}.jsonl"), [{k: v for k, v in x.items() if k != "trechos"}
                                            | {"chunk_ids": [t["chunk_id"] for t in x["trechos"]]} for x in linhas])
    return _ler(arq)


def busca_ids() -> list[dict]:
    """O que o relatório precisa da busca, a partir do arquivo versionado: refaz os números sem a base local."""
    return _ler(PASTA / "busca_ids.jsonl")


def gerar_versao(versao: str) -> None:
    import gerar
    cfg = dict(VERSOES[versao])
    k = int(cfg.pop("k", K))
    os.environ.update(cfg)
    arq = PASTA / f"respostas_{versao}.jsonl"
    feitas = {x["id"]: x for x in _ler(arq)}
    for b in buscar_uma_vez(k):
        if b["id"] in feitas:
            continue
        t0 = time.time()
        prompt = gerar.montar_prompt(b["pergunta"], b["trechos"])
        try:
            resposta, uso = gerar.gerar(prompt)
            erro = None
        except Exception as e:  # noqa: BLE001 - falha do gerador vira dado, não derruba a rodada
            resposta, uso, erro = "", {}, f"{type(e).__name__}: {str(e)[:200]}"
        feitas[b["id"]] = {"id": b["id"], "versao": versao, "modelo": VERSOES[versao]["RAG_LLM_MODELO"],
                           "resposta": resposta, "erro": erro, "conferencia": gerar.conferir(resposta, b["trechos"]),
                           "uso": uso, "segundos": round(time.time() - t0, 1)}
        _gravar(arq, list(feitas.values()))
        print(b["id"], versao, "erro" if erro else "ok", f"{time.time() - t0:.0f} s", flush=True)


def _juiz():
    """Faithfulness e AnswerRelevancy do RAGAS com o Claude como juiz; soma os tokens para o teto."""
    if os.environ.get("LIB_ANTHROPIC"):                 # SDK fora do ambiente; o grupo instala com `uv add anthropic`
        sys.path.append(os.environ["LIB_ANTHROPIC"])
    from anthropic import AsyncAnthropic
    from ragas.embeddings import HuggingFaceEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, Faithfulness

    cliente = AsyncAnthropic()
    original = cliente.messages.create

    async def contar(*a, **k):
        k.pop("temperature", None)                      # os modelos novos recusam temperature
        k.pop("top_p", None)
        k["max_tokens"] = max(int(k.get("max_tokens") or 0), 4000)
        r = await original(*a, **k)
        GASTO["entrada"] += getattr(r.usage, "input_tokens", 0) or 0
        GASTO["saida"] += getattr(r.usage, "output_tokens", 0) or 0
        if _dolar() > TETO:
            raise RuntimeError(f"teto de {TETO} dólares atingido")
        return r
    cliente.messages.create = contar
    # O RAGAS pede resposta estruturada pelo modo de ferramentas do Instructor, com tool_choice forçado, que os modelos
    # Claude 5 recusam (erro 400, achado no piloto de 17/11/2026). O modo de JSON da Anthropic dá a mesma estrutura.
    # Só durante a criação do modelo; depois a função original volta, para não mudar o Instructor no resto do processo.
    import instructor
    original = instructor.from_anthropic
    instructor.from_anthropic = lambda c, **kw: original(c, mode=instructor.Mode.ANTHROPIC_JSON)
    try:
        llm = llm_factory(JUIZ, provider="anthropic", client=cliente)
    finally:
        instructor.from_anthropic = original
    emb = HuggingFaceEmbeddings(model=EMBEDDINGS)
    return Faithfulness(llm=llm), AnswerRelevancy(llm=llm, embeddings=emb)


def _dolar() -> float:
    e, s = PRECO.get(GASTO["modelo"], (3.0, 15.0))
    return (GASTO["entrada"] * e + GASTO["saida"] * s) / 1e6


def ragas_versao(versao: str, limite: int | None = None) -> None:
    busca = {b["id"]: b for b in buscar_uma_vez(int(VERSOES[versao].get("k", K)))}
    resp = {r["id"]: r for r in _ler(PASTA / f"respostas_{versao}.jsonl")}
    arq = PASTA / f"ragas_{versao}.jsonl"
    feitas = {x["id"]: x for x in _ler(arq)}
    fiel, relev = _juiz()
    alvo = [i for i in busca if busca[i]["tem_resposta"] and i in resp and i not in feitas][:limite]

    async def uma(i):
        b, r = busca[i], resp[i]
        contextos = [t["trecho"] for t in b["trechos"]]
        nota = {"id": i, "versao": versao, "juiz": JUIZ}
        for nome, m, kw in (("faithfulness", fiel, {"retrieved_contexts": contextos}), ("answer_relevancy", relev, {})):
            try:
                v = (await m.ascore(user_input=b["pergunta"], response=r["resposta"] or "(sem resposta)", **kw)).value
                nota[nome] = None if v is None or v != v else round(float(v), 4)        # NaN vira None
            except Exception as e:  # noqa: BLE001
                nota[nome], nota[f"erro_{nome}"] = None, f"{type(e).__name__}: {str(e)[:160]}"
        return nota

    async def todas():
        sem = asyncio.Semaphore(4)

        async def com_limite(i):
            async with sem:
                return await uma(i)
        for fut in asyncio.as_completed([com_limite(i) for i in alvo]):
            n = await fut
            feitas[n["id"]] = n
            _gravar(arq, list(feitas.values()))
            print(n["id"], versao, n.get("faithfulness"), n.get("answer_relevancy"), f"US$ {_dolar():.3f}", flush=True)
    asyncio.run(todas())
    custo = PASTA / "custo.json"
    reg = json.loads(custo.read_text(encoding="utf-8")) if custo.exists() else {}
    reg[f"ragas_{versao}_{len(alvo)}"] = {"juiz": JUIZ, "entrada": GASTO["entrada"], "saida": GASTO["saida"],
                                          "dolar": round(_dolar(), 4)}
    custo.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def _boot(valores: list[float]) -> tuple[float, float]:
    rnd = random.Random(SEMENTE)
    ms = sorted(sum(rnd.choice(valores) for _ in valores) / len(valores) for _ in range(N_BOOT))
    return ms[int(0.025 * N_BOOT)], ms[int(0.975 * N_BOOT) - 1]


def relatorio() -> str:
    busca = {b["id"]: b for b in busca_ids()}
    R = {v: {r["id"]: r for r in _ler(PASTA / f"respostas_{v}.jsonl")} for v in VERSOES}
    G = {v: {g["id"]: g for g in _ler(PASTA / f"ragas_{v}.jsonl")} for v in VERSOES}
    com = [i for i in busca if busca[i]["tem_resposta"]]
    sem = [i for i in busca if not busca[i]["tem_resposta"]]
    T = ["O RAG ANTIGO CONTRA O NOVO, NO PROTOCOLO DO RELATÓRIO DE 09/11/2026",
         f"Perguntas: {len(com)} com resposta na base (gabarito de 09/11) e {len(sem)} sem (2 do relatório e 25 fora da base).",
         "Busca: a mesma para as duas versões (qwen3+rerank50, 5 trechos). Antigo: Llama 3.1 8B local, prompt de antes. "
         "Novo: Haiku 5.5, prompt com esclarecimento.",
         f"Juiz do RAGAS: {JUIZ}; vetores {EMBEDDINGS}. Intervalos de 95% por reamostragem das perguntas ({N_BOOT}). "
         "Nenhum modelo foi treinado.", ""]
    # busca: igual nas duas versões
    prec, rec, um = [], [], 0
    for i in com:
        ids = busca[i]["chunk_ids"]
        gab = set(busca[i]["gabarito"])
        prec.append(sum(x in gab for x in ids) / len(ids))
        rec.append(len(gab & set(ids)) / len(gab))
        um += any(x in gab for x in ids)
    T += ["BUSCA (igual nas duas versões; gabarito de 09/11, por chunk_id, sem modelo)",
          f"  recall@5 (IDBasedContextRecall)      {sum(rec) / len(rec):.2f} [{_boot(rec)[0]:.2f}; {_boot(rec)[1]:.2f}]",
          f"  precisão@5 (IDBasedContextPrecision) {sum(prec) / len(prec):.2f} [{_boot(prec)[0]:.2f}; {_boot(prec)[1]:.2f}]",
          f"  perguntas com ao menos um trecho do gabarito: {um} de {len(com)}", ""]
    T.append(f"{'':48}" + "".join(f"{v:>14}" for v in VERSOES))

    def linha(nome, f, ids):
        vals = {v: [f(v, i) for i in ids if R[v].get(i)] for v in VERSOES}
        s = {v: (sum(x for x in vals[v] if x is not None), sum(x is not None for x in vals[v])) for v in VERSOES}
        T.append(f"  {nome:46}" + "".join(f"{f'{a} de {n}':>14}" for a, n in s.values()))
    linha("recusa nas perguntas sem resposta", lambda v, i: R[v][i]["conferencia"]["absteve"], sem)
    linha("recusa indevida nas perguntas com resposta", lambda v, i: R[v][i]["conferencia"]["absteve"], com)
    linha("pediu esclarecimento", lambda v, i: R[v][i]["conferencia"].get("pediu_esclarecimento", False), com + sem)
    linha("resposta com citação de trecho inexistente", lambda v, i: bool(R[v][i]["conferencia"]["citacoes_invalidas"]), com)
    linha("resposta com frase sem citação", lambda v, i: bool(R[v][i]["conferencia"]["frases_sem_citacao"]), com)
    linha("erro do gerador", lambda v, i: bool(R[v][i].get("erro")), com + sem)
    T.append("")
    T.append(f"RAGAS NAS {len(com)} PERGUNTAS COM RESPOSTA (média; recusa entra como resposta e tende a nota baixa em relevância)")
    def respondeu(v, i):        # afirmou algo: nem recusa nem pedido de esclarecimento
        if i not in R[v]:
            return False
        c = R[v][i]["conferencia"]
        return not c["absteve"] and not c.get("pediu_esclarecimento")
    for x, y in (("antigo", "novo"), ("novo", "novo20"), ("antigo", "novo20")):
        if not (G[x] and G[y]):
            continue
        for rotulo, filtro in (("todas as respostas (recusa vale 0)", lambda i: True),
                               ("só onde as duas versões responderam", lambda i: respondeu(x, i) and respondeu(y, i))):
            T.append(f"  {y} contra {x}, {rotulo}")
            for met in ("faithfulness", "answer_relevancy"):
                pares = [(G[x][i][met], G[y][i][met]) for i in com
                         if filtro(i) and i in G[x] and i in G[y]
                         and G[x][i].get(met) is not None and G[y][i].get(met) is not None]
                if not pares:
                    T.append(f"    {met}: sem notas")
                    continue
                a, n = [p[0] for p in pares], [p[1] for p in pares]
                d = [q - p for p, q in pares]
                lo, hi = _boot(d)
                T.append(f"    {met:20} {x} {sum(a) / len(a):.2f}   {y} {sum(n) / len(n):.2f}   "
                         f"diferença {sum(d) / len(d):+.2f} [{lo:+.2f}; {hi:+.2f}]   ({len(pares)} perguntas)")
    custo = PASTA / "custo.json"
    if custo.exists():
        T += ["", "custo registrado na chave (juiz do RAGAS): " + "; ".join(f"{k} US$ {v['dolar']}" for k, v in
                                                                         json.loads(custo.read_text(encoding="utf-8")).items())]
    texto = "\n".join(T) + "\n"
    SAIDA.write_text(texto, encoding="utf-8")
    print(texto)
    return texto


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "gerar":
        gerar_versao(sys.argv[2])
    elif cmd == "ragas":
        ragas_versao(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
    elif cmd == "relatorio":
        relatorio()
    else:
        raise SystemExit(__doc__)
