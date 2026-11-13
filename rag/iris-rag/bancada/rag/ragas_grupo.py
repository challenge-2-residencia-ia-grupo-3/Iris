"""ragas_grupo.py: as métricas de RAG do grupo, com a biblioteca RAGAS de verdade, sem copiar o código deles.

O grupo já tem (crédito a quem fez, ver git log do clone):
  * iris.eval.precisao_contexto.pontuar_ragas_por_id: Context Precision do RAGAS (IDBasedContextPrecision) por
    identificador de trecho, testada em backend/tests/test_precisao_contexto_ragas.py;
  * iris.eval.fidelidade_frases.medir: fidelidade por frase a partir dos vereditos cruzados versionados
    (rag/iris-rag/pacote/respostas_vereditos_cruzado.json), a Faithfulness do RAGAS com a frase como unidade.

Este script só CHAMA essas funções (o clone do grupo entra no sys.path, sem nenhum arquivo alterado e sem .pyc):
  1. precisão do contexto do RAGAS sobre os top-5 que a busca padrão (qwen3+rerank) já gravou nos experimentos da
     bancada (outputs/17-respostas.jsonl: campo dos trechos recuperados), contra o gabarito do grupo;
  2. a fidelidade por frase do grupo, como o grupo a mede.
Nenhuma chamada a modelo, nenhuma rede. Grava pacote/outputs/38-ragas-grupo.json.

Uso:  python bancada/rag/ragas_grupo.py --grupo CAMINHO_DO_CLONE   (python de um venv com ragas==0.4.3 e
      langchain-community<0.4, as mesmas travas do pyproject do grupo)
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PACOTE = AQUI.parent.parent / "pacote"
OUT = PACOTE / "outputs"


def ic(vals: list[float], semente: int = 20261105, n_boot: int = 2000) -> list[float]:
    if not vals:
        return [0.0, 0.0]
    rnd = random.Random(semente)
    m = sorted(sum(rnd.choice(vals) for _ in vals) / len(vals) for _ in range(n_boot))
    return [round(m[int(0.025 * n_boot)], 4), round(m[int(0.975 * n_boot) - 1], 4)]


def top5_gravados() -> dict[str, list[str]]:
    """Trechos que a busca padrão devolveu em cada pergunta, como gravados nas respostas da v1."""
    out = {}
    for l in (OUT / "17-respostas.jsonl").read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        ids = r.get("top5") or r.get("trechos_ids") or [t.get("chunk_id") or t.get("id") for t in (r.get("trechos") or []) if isinstance(t, dict)]
        ids = [i for i in ids if i]
        if ids:
            out[r["id"]] = ids[:5]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grupo", required=True, type=Path)
    a = ap.parse_args()
    grupo = a.grupo.resolve()
    sys.path.insert(0, str(grupo / "backend" / "src"))
    from iris.eval import fidelidade_frases as FF          # noqa: E402  (código do grupo, só leitura)
    from iris.eval import precisao_contexto as PC          # noqa: E402

    commit = subprocess.run(["git", "-C", str(grupo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    gab = {i["id"]: i for i in PC.carregar_gabarito()}
    top5 = top5_gravados()
    por_pergunta = []
    for qid, item in sorted(gab.items()):
        if qid not in top5:
            continue
        certos = list(item["trechos_relevantes"])
        rec = top5[qid]
        por_pergunta.append({"id": qid, "precisao_ragas": round(PC.pontuar_ragas_por_id(rec, certos), 4),
                             "teto": min(len(certos), 5) / 5, "acertos_no_top5": sum(1 for c in rec if c in certos)})
    vals = [p["precisao_ragas"] for p in por_pergunta]
    tetos = [p["teto"] for p in por_pergunta]

    fid = FF.medir(FF.carregar_vereditos())
    fid_resumo = {g: {"fidelidade_final": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d["fidelidade"]["final"].items()},
                      "leitura": d["leitura"], "kappa_AxB": round(d["concordancia"]["AxB"]["kappa"], 3)}
                  for g, d in fid["geradores"].items()}

    import ragas
    dado = {
        "titulo": "métricas de RAG do grupo com a biblioteca RAGAS",
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit_grupo": commit, "ragas_versao": ragas.__version__,
        "credito": "funções do grupo: iris.eval.precisao_contexto (PR #68) e iris.eval.fidelidade_frases; a bancada só chama",
        "precisao_contexto": {
            "metrica": "ragas.metrics.IDBasedContextPrecision (via iris.eval.precisao_contexto.pontuar_ragas_por_id)",
            "busca": "top-5 gravados da configuração padrão (qwen3+rerank) em outputs/17-respostas.jsonl",
            "n": len(vals), "media": round(sum(vals) / len(vals), 4) if vals else None, "ic95": ic(vals),
            "teto_medio": round(sum(tetos) / len(tetos), 4) if tetos else None,
            "leitura": "fração dos 5 trechos recuperados que está no gabarito; o teto não é 1 porque muitas perguntas têm menos de 5 trechos certos",
            "por_pergunta": por_pergunta},
        "fidelidade_por_frase": {
            "metrica": "iris.eval.fidelidade_frases.medir (Faithfulness do RAGAS com a frase como unidade, vereditos versionados)",
            "meta": fid["meta"], "por_gerador": fid_resumo,
            "aviso": "vereditos de juízes-modelo (Sonnet A, Sonnet B, Codex, Opus); não calibrados contra pessoas (ver 33-juiz-calibracao.json)"},
    }
    (OUT / "38-ragas-grupo.json").write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"38-ragas-grupo.json: precisão do contexto (RAGAS) {dado['precisao_contexto']['media']} "
          f"IC95 {dado['precisao_contexto']['ic95']} em {len(vals)} perguntas; teto {dado['precisao_contexto']['teto_medio']}")
    for g_, d in fid_resumo.items():
        print(f"  fidelidade {g_}: {d['fidelidade_final']['media']} {d['fidelidade_final']['ic95']} ({d['leitura']})")
    return 0 if vals else 2


if __name__ == "__main__":
    sys.exit(main())
