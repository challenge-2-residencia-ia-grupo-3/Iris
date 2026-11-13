"""busca.py: roda a busca padrão (qwen3+rerank) UMA vez nas 40 perguntas e grava os trechos.

Todos os testes usam estes mesmos trechos: B devolve o texto deles, C os entrega ao LLM e o pacote do juiz
os mostra para checar as frases de A e C. Também grava os prompts exatos de A e C (saidas/prompts_ac.jsonl),
para o PC gerar com o Llama sem precisar do modelo de embedding nem do reranker.

Uso (VPS, ~5 a 10 min na CPU; um job pesado por vez):
    python semana3/busca.py        (no ambiente de rag/iris-rag/pacote)
"""
from __future__ import annotations

import sys
import time

import comum as C

C.adicionar_pacote_ao_path()


def main() -> None:
    import consultar
    import gerar

    assert gerar.PROMPT_VERSAO == "v1", "o teste C usa o prompt v1 (o que está em produção)"
    feitos = {l["id"] for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    commit = C.commit_atual()
    for it in C.itens_gabarito():
        if it["id"] in feitos:
            continue
        t0 = time.time()
        ranking = consultar.ranking(it["pergunta"], consultar.METODO_PADRAO, 10)
        seg = round(time.time() - t0, 2)
        top5 = [consultar.trecho(cid, pos, nota) for pos, (cid, nota) in enumerate(ranking[:5], 1)]
        C.acrescentar_jsonl(C.TRECHOS_BUSCA, {
            "id": it["id"], "pergunta": it["pergunta"], "metodo": consultar.METODO_PADRAO,
            "banco": consultar.BANCO, "reranker": consultar.RERANKER,
            "ranking_top10": [{"chunk_id": cid, "score": round(float(n), 4)} for cid, n in ranking],
            "trechos_top5": top5, "segundos_busca": seg, "data_hora": C.agora_iso(), "commit": commit})
        print(f"{it['id']} busca {seg:.1f} s  top1={ranking[0][0]}", flush=True)

    # prompts exatos de A e C (um por pergunta), a partir dos trechos gravados
    busca = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    linhas = []
    for it in C.itens_gabarito():
        b = busca[it["id"]]
        p_c = gerar.montar_prompt(it["pergunta"], b["trechos_top5"], "v1")
        p_a = C.montar_prompt_a(it["pergunta"])
        linhas.append({"id": it["id"], "pergunta": it["pergunta"], "prompt_A": p_a, "prompt_C": p_c,
                       "sha16_prompt_A": C.sha16(p_a), "sha16_prompt_C": C.sha16(p_c), "versao_prompt_C": "v1"})
    C.escrever_jsonl(C.PROMPTS_AC, linhas)
    print(f"gravado: {C.TRECHOS_BUSCA.name} ({len(busca)} perguntas) e {C.PROMPTS_AC.name}", flush=True)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
