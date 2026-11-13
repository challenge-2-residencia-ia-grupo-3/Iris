"""teste_b.py: RAG sem LLM. A "resposta" é o texto cru do top-1 e do top-3 da busca (sem geração).

Determinístico, 1 rodada. Lê saidas/trechos_busca.jsonl (gravado por busca.py).
Métricas: recall@5, hit@5, MRR (mesma conta de pacote/avaliar_opus.py, só nota 2 do gabarito) e Flesch PT-BR
da resposta (função flesch_ptbr do grupo, se o código do grupo estiver acessível; senão fica vazio).
Saída: saidas/respostas_B.jsonl (uma linha por pergunta e variante top1/top3).

Uso: python3 semana3/teste_b.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import comum as C

GRUPO = Path(os.environ.get("IRIS_GRUPO", str(Path(__file__).resolve().parents[3])))  # raiz deste repositório


def _flesch():
    src = GRUPO / "backend" / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from iris.eval.readability import flesch_ptbr
        return flesch_ptbr
    except Exception:  # noqa: BLE001
        return lambda _t: None


def metricas_busca(rank: list[str], rel: set[str]) -> dict:
    if not rel:
        return {"recall@5": None, "hit@5": None, "MRR": None, "posicao_1o_relevante": None}
    pos = next((i for i, c in enumerate(rank) if c in rel), None)
    return {"recall@5": len(rel & set(rank[:5])) / len(rel), "hit@5": float(pos is not None and pos < 5),
            "MRR": 0.0 if pos is None else 1 / (pos + 1), "posicao_1o_relevante": None if pos is None else pos + 1}


def main() -> None:
    flesch = _flesch()
    busca = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    commit = C.commit_atual()
    linhas = []
    for it in C.itens_gabarito():
        b = busca[it["id"]]
        rank = [r["chunk_id"] for r in b["ranking_top10"]]
        m = metricas_busca(rank, set(it["trechos_relevantes"]))
        for var, n in (("top1", 1), ("top3", 3)):
            ts = b["trechos_top5"][:n]
            resposta = "\n\n".join(f"[T{i}] {t['titulo']}" + (f", p. {t['pagina']}" if t.get("pagina") else "")
                                   + f"\n{t['trecho']}" for i, t in enumerate(ts, 1))
            so_texto = "\n".join(t["trecho"] for t in ts)
            f = flesch(so_texto)
            linhas.append({"teste": "B", "variante": var, "id": it["id"], "repeticao": 1, "pergunta": it["pergunta"],
                           "categoria": it["categoria"], "doc_dominante": it["doc_dominante"],
                           "modelo": None, "metodo_busca": b["metodo"], "commit": commit, "data_hora": C.agora_iso(),
                           "trechos": [{"ref": f"T{i}", "chunk_id": t["chunk_id"], "doc": t["doc"],
                                        "score": t.get("score")} for i, t in enumerate(ts, 1)],
                           "trechos_relevantes_no_topn": sum(t["chunk_id"] in set(it["trechos_relevantes"]) for t in ts),
                           "resposta": resposta, "palavras": len(so_texto.split()),
                           "flesch_ptbr": None if f is None else round(f, 1),
                           "segundos_busca": b["segundos_busca"], **m, "erro": None})
    C.escrever_jsonl(C.SAIDAS / "respostas_B.jsonl", linhas)
    print(f"gravado: respostas_B.jsonl ({len(linhas)} linhas)")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
