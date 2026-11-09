"""Executor do benchmark (Semana 3): roda um sistema (LLM puro ou Íris) sobre o Golden Benchmark.

Um *adaptador* é qualquer função ``f(questao: GoldenQuestion) -> str | dict``:
  * ``str``: o texto adaptado;
  * ``dict``: ``{"adaptado": str, "contextos": [str, ...], ...}``. ``contextos`` são os trechos
    que o RAG recuperou (necessários para medir Faithfulness); campos extras são gravados.

Saída: ``reports/saidas/<sistema>.jsonl``, uma linha por questão::

    {"id", "sistema", "adaptado", "contextos", "latencia_s", "erro"}

Retomada: questões já gravadas sem erro são puladas (use --refazer para refazer tudo).
Uma questão que falha grava ``erro`` e o executor segue; o relatório trata como "sem saída".

Uso:
    uv run python -m iris.eval.executar --sistema iris --adaptador meu_pacote.modulo:funcao
    uv run python -m iris.eval.executar --sistema teste --adaptador iris.eval.executar:adaptador_identidade
"""

from __future__ import annotations

import argparse
import importlib
import json
import time
from collections.abc import Callable
from pathlib import Path

from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark

SAIDAS_PADRAO = Path("reports/saidas")

Adaptador = Callable[[GoldenQuestion], "str | dict"]


def adaptador_identidade(questao: GoldenQuestion) -> dict:
    """Adaptador de teste: devolve o próprio enunciado (TRCC deve dar 100%)."""
    return {"adaptado": questao.enunciado, "contextos": []}


def carregar_adaptador(especificacao: str) -> Adaptador:
    """Resolve ``"pacote.modulo:funcao"`` para a função."""
    if ":" not in especificacao:
        raise ValueError('Adaptador deve ter a forma "pacote.modulo:funcao".')
    modulo, nome = especificacao.split(":", 1)
    return getattr(importlib.import_module(modulo), nome)


def ler_saidas(caminho: str | Path) -> dict[str, dict]:
    """Lê um .jsonl de saídas. Se um id aparece mais de uma vez, vale a última linha."""
    p = Path(caminho)
    if not p.exists():
        return {}
    ultimo: dict[str, dict] = {}
    for linha in p.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            registro = json.loads(linha)
            ultimo[registro["id"]] = registro
    return ultimo


def executar_sistema(
    adaptador: Adaptador,
    questoes: list[GoldenQuestion],
    sistema: str,
    pasta: str | Path = SAIDAS_PADRAO,
    refazer: bool = False,
    limite: int | None = None,
    progresso: Callable[[str], None] | None = print,
) -> dict:
    """Roda o adaptador nas questões pendentes e acrescenta as saídas ao .jsonl do sistema."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{sistema}.jsonl"
    if refazer and destino.exists():
        destino.unlink()

    feitas = {qid for qid, r in ler_saidas(destino).items() if not r.get("erro")}
    pendentes = [q for q in questoes if q.id not in feitas]
    if limite:
        pendentes = pendentes[:limite]

    ok = falhas = 0
    with destino.open("a", encoding="utf-8") as f:
        for i, q in enumerate(pendentes, 1):
            inicio = time.perf_counter()
            try:
                saida = adaptador(q)
                registro = dict(saida) if isinstance(saida, dict) else {"adaptado": saida}
                texto = registro.get("adaptado")
                if not isinstance(texto, str) or not texto.strip():
                    raise ValueError("o adaptador não devolveu texto em 'adaptado'")
                registro["erro"] = None
                ok += 1
            except Exception as exc:  # noqa: BLE001 - uma questão ruim não derruba o benchmark
                registro = {"adaptado": "", "erro": f"{type(exc).__name__}: {exc}"}
                falhas += 1
            registro["contextos"] = list(registro.get("contextos") or [])
            registro.update(id=q.id, sistema=sistema, latencia_s=round(time.perf_counter() - inicio, 3))
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            f.flush()
            if progresso:
                estado = "ERRO" if registro["erro"] else "ok"
                progresso(f"[{sistema}] {i}/{len(pendentes)} {q.id}: {estado}")

    return {"destino": str(destino), "executadas": ok, "falhas": falhas, "puladas": len(feitas)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sistema", required=True, help='nome do sistema, ex.: "iris" ou "llm_puro"')
    ap.add_argument("--adaptador", required=True, help='"pacote.modulo:funcao"')
    ap.add_argument("--benchmark", default=None, help="caminho do golden_benchmark.json (padrão: data/)")
    ap.add_argument("--saidas", default=str(SAIDAS_PADRAO))
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--limite", type=int, default=None, help="roda só as N primeiras pendentes (teste rápido)")
    args = ap.parse_args(argv)

    resumo = executar_sistema(
        carregar_adaptador(args.adaptador),
        carregar_golden_benchmark(args.benchmark),
        args.sistema,
        pasta=args.saidas,
        refazer=args.refazer,
        limite=args.limite,
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()