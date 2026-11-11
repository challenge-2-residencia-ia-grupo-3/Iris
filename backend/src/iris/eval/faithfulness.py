"""Faithfulness (RAGAS) das saídas de um sistema com RAG.

Faithfulness mede se cada afirmação do texto adaptado é sustentada pelos trechos recuperados.
Só faz sentido para sistemas que recuperam contexto (Íris); o LLM puro não tem ``contextos``.

Precisa de um LLM juiz (chave de API do provedor). A pontuação é injetável (``pontuar``), então
o restante do código é testável sem rede. O juiz real é criado por ``criar_pontuador_ragas``.

Uso:
    export OPENAI_API_KEY=...            # ou ANTHROPIC_API_KEY (provider anthropic)
    uv run python -m iris.eval.faithfulness --sistema iris --provider openai --modelo gpt-4o-mini

Grava ``reports/saidas/<sistema>.faithfulness.json``::

    {"juiz": "...", "scores": {"Q01": 0.92, "Q02": null}, "erros": {"Q02": "..."}}
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.executar import SAIDAS_PADRAO, ler_saidas

FAITHFULNESS_MIN = 0.90

# (pergunta, resposta adaptada, contextos recuperados) -> nota de 0 a 1
Pontuador = Callable[[str, str, Sequence[str]], Awaitable[float]]


def criar_pontuador_ragas(provider: str, modelo: str) -> Pontuador:
    """Cria o juiz com a API ``ragas.metrics.collections`` (ragas >= 0.4).

    provider: "openai" (usa OPENAI_API_KEY) ou "anthropic" (usa ANTHROPIC_API_KEY; exige
    ``uv add anthropic``).
    """
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness

    if provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
    elif provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic()
    else:
        raise ValueError(f"provider '{provider}' não suportado (use openai ou anthropic).")

    metrica = Faithfulness(llm=llm_factory(modelo, provider=provider, client=client))

    async def pontuar(pergunta: str, resposta: str, contextos: Sequence[str]) -> float:
        resultado = await metrica.ascore(
            user_input=pergunta, response=resposta, retrieved_contexts=list(contextos)
        )
        return float(resultado.value)

    return pontuar


async def _medir(
    itens: list[dict], pontuar: Pontuador, concorrencia: int
) -> tuple[dict[str, float | None], dict[str, str]]:
    semaforo = asyncio.Semaphore(concorrencia)
    scores: dict[str, float | None] = {}
    erros: dict[str, str] = {}

    async def um(item: dict) -> None:
        async with semaforo:
            try:
                nota = await pontuar(item["pergunta"], item["resposta"], item["contextos"])
                scores[item["id"]] = None if nota is None else float(nota)
            except Exception as exc:  # noqa: BLE001 - registra e segue
                scores[item["id"]] = None
                erros[item["id"]] = f"{type(exc).__name__}: {exc}"

    await asyncio.gather(*(um(i) for i in itens))
    return scores, erros


def medir_faithfulness(
    questoes: list[GoldenQuestion],
    saidas: dict[str, dict],
    pontuar: Pontuador,
    concorrencia: int = 4,
) -> dict:
    """Mede a Faithfulness das questões que têm saída válida E contextos recuperados."""
    itens = []
    sem_contexto = []
    for q in questoes:
        reg = saidas.get(q.id)
        if not reg or reg.get("erro") or not reg.get("adaptado"):
            continue
        if not reg.get("contextos"):
            sem_contexto.append(q.id)
            continue
        itens.append(
            {"id": q.id, "pergunta": q.enunciado, "resposta": reg["adaptado"], "contextos": reg["contextos"]}
        )
    scores, erros = asyncio.run(_medir(itens, pontuar, concorrencia))
    return {"scores": scores, "erros": erros, "sem_contexto": sorted(sem_contexto)}


def ler_faithfulness(pasta: str | Path, sistema: str) -> dict | None:
    """Lê as notas gravadas e resume. Devolve None se o arquivo não existe."""
    caminho = Path(pasta) / f"{sistema}.faithfulness.json"
    if not caminho.exists():
        return None
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    notas = {qid: v for qid, v in dados.get("scores", {}).items() if v is not None}
    return {
        "juiz": dados.get("juiz"),
        "media": round(sum(notas.values()) / len(notas), 4) if notas else None,
        "n_medidas": len(notas),
        "n_sem_nota": len(dados.get("scores", {})) - len(notas) + len(dados.get("sem_contexto", [])),
        "scores": dados.get("scores", {}),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sistema", required=True)
    ap.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    ap.add_argument("--modelo", required=True, help="modelo do juiz, ex.: gpt-4o-mini")
    ap.add_argument("--benchmark", default=None)
    ap.add_argument("--saidas", default=str(SAIDAS_PADRAO))
    ap.add_argument("--concorrencia", type=int, default=4)
    args = ap.parse_args(argv)

    questoes = carregar_golden_benchmark(args.benchmark)
    saidas = ler_saidas(Path(args.saidas) / f"{args.sistema}.jsonl")
    if not saidas:
        raise SystemExit(f"Sem saídas em {args.saidas}/{args.sistema}.jsonl. Rode iris.eval.executar antes.")

    resultado = medir_faithfulness(
        questoes, saidas, criar_pontuador_ragas(args.provider, args.modelo), args.concorrencia
    )
    resultado["juiz"] = f"{args.provider}/{args.modelo}"
    destino = Path(args.saidas) / f"{args.sistema}.faithfulness.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    medidas = [v for v in resultado["scores"].values() if v is not None]
    media = sum(medidas) / len(medidas) if medidas else None
    print(f"Faithfulness média: {media if media is None else round(media, 4)} "
          f"({len(medidas)} medidas, {len(resultado['erros'])} erros, "
          f"{len(resultado['sem_contexto'])} sem contexto). Gravado em {destino}")


if __name__ == "__main__":
    main()