"""gerar_ac.py: testes A (LLM sozinho) e C (RAG + LLM, prompt v1) — 40 perguntas x 3 repetições.

Lê os prompts exatos de saidas/prompts_ac.jsonl (gravados por busca.py) e grava uma linha por resposta em
saidas/respostas_<teste>_<modelo>.jsonl, com o log de proveniência (pergunta, condição, trechos com score,
resposta, modelo, data/hora, commit, tokens, tempo). Retoma de onde parou se for interrompido.
Ordem: repetição 1 das 40 perguntas, depois a 2, depois a 3 (se o dia acabar no meio, as repetições
completas ficam inteiras).

Uso:
    python semana3/gerar_ac.py --modelo qwen3.8-27b --testes A,C        (VPS, Groq)
    python semana3/gerar_ac.py --modelo llama3.1-8b --testes A,C        (PC, Ollama; ver RODAR-NO-PC.md)
"""
from __future__ import annotations

import argparse
import sys
import time

import comum as C


def arquivo(teste: str, modelo: str):
    return C.SAIDAS / f"respostas_{teste}_{modelo}.jsonl"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True, choices=list(C.MODELOS))
    ap.add_argument("--testes", default="A,C")
    ap.add_argument("--repeticoes", type=int, default=C.REPETICOES, help="até qual repetição gerar")
    ap.add_argument("--rep-inicial", type=int, default=1)
    ap.add_argument("--limite", type=int, default=None, help="só as N primeiras perguntas (teste rápido)")
    args = ap.parse_args(argv)

    prompts = C.ler_jsonl(C.PROMPTS_AC)
    if len(prompts) != 40:
        raise SystemExit(f"{C.PROMPTS_AC} tem {len(prompts)} linhas (esperado 40). Rode busca.py antes.")
    if args.limite:
        prompts = prompts[: args.limite]
    busca = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    cats = {it["id"]: it for it in C.itens_gabarito()}
    provedor, id_modelo = C.MODELOS[args.modelo]
    commit = C.commit_atual()
    testes = [t for t in args.testes.split(",") if t]
    reps = list(range(args.rep_inicial, args.repeticoes + 1))
    total = len(testes) * len(reps) * len(prompts)
    feito = 0
    ja = {t: {(l["id"], l["repeticao"]) for l in C.ler_jsonl(arquivo(t, args.modelo)) if not l.get("erro")}
          for t in testes}
    for rep in reps:                      # ordem do PREREG: repetição por fora, A e C dentro
        for teste in testes:
            arq = arquivo(teste, args.modelo)
            for p in prompts:
                feito += 1
                if (p["id"], rep) in ja[teste]:
                    continue
                prompt = p["prompt_A"] if teste == "A" else p["prompt_C"]
                b = busca.get(p["id"], {})
                linha = {"teste": teste, "id": p["id"], "repeticao": rep, "pergunta": p["pergunta"],
                         "categoria": cats[p["id"]]["categoria"], "doc_dominante": cats[p["id"]]["doc_dominante"],
                         "modelo": args.modelo, "provedor": provedor, "id_modelo": id_modelo,
                         "temperatura": C.TEMPERATURA, "versao_prompt": "A-v1" if teste == "A" else "v1",
                         "sha16_prompt": C.sha16(prompt), "commit": commit, "data_hora": C.agora_iso(),
                         # trechos: em C foram entregues ao modelo; em A são os que a busca teria trazido
                         # (o modelo NÃO os viu; servem para o juiz checar as frases contra a base)
                         "trechos_entregues_ao_modelo": teste == "C",
                         "trechos": [{"ref": f"T{i}", "chunk_id": t["chunk_id"], "doc": t["doc"],
                                      "score": t.get("score")} for i, t in enumerate(b.get("trechos_top5", []), 1)],
                         "segundos_busca": b.get("segundos_busca") if teste == "C" else None}
                t0 = time.time()
                try:
                    r = C.chamar(args.modelo, prompt)
                    linha.update({"resposta": r["texto"], "resposta_bruta_tinha_think": "<think>" in r["texto_bruto"],
                                  "tokens_entrada": r["tokens_entrada"], "tokens_saida": r["tokens_saida"],
                                  "segundos_geracao": r["segundos_geracao"],
                                  "segundos_espera_limite": r["segundos_espera_limite"],
                                  "modelo_informado": r["modelo_informado"], "fim": r["fim"],
                                  "custo_usd": C.custo_usd(args.modelo, r["tokens_entrada"], r["tokens_saida"]),
                                  "erro": None})
                except C.LimiteDiario as e:
                    print(f"limite diário do Groq atingido; parar e rodar de novo depois ({e})", flush=True)
                    return
                except Exception as e:  # noqa: BLE001 - erro fica gravado e é contado na checagem de integridade
                    linha.update({"resposta": None, "erro": f"{type(e).__name__}: {str(e)[:200]}"})
                linha["segundos_total_chamada"] = round(time.time() - t0, 2)
                C.acrescentar_jsonl(arq, linha)
                txt = (linha.get("resposta") or linha["erro"] or "").replace("\n", " ")[:70]
                print(f"[{feito}/{total}] {teste} {p['id']} r{rep} {linha['segundos_total_chamada']:.1f} s | {txt}",
                      flush=True)
    print("fim", flush=True)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
