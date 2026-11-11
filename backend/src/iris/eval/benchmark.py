"""Estruturação e carregador do dataset Golden Benchmark (História 4.2.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GoldenQuestion:
    """Representa uma questão do Golden Benchmark de questões escolares."""

    id: str
    disciplina: str
    ano: str
    tema: str
    enunciado: str
    comando_conjugado_esperado: bool
    status: str = "rascunho"
    # Conceitos da trava; "a|b" = alternativas aceitas. Lista no JSON ou texto separado por ";".
    trava_curricular: Optional[tuple[str, ...]] = None
    habilidade_bncc: Optional[str] = None


def _como_tupla(valor: object) -> Optional[tuple[str, ...]]:
    """Normaliza a trava: lista/tupla de conceitos ou texto separado por ';'."""
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.split(";")
    conceitos = tuple(str(c).strip() for c in valor if str(c).strip())
    return conceitos or None


def carregar_golden_benchmark(
    caminho: Optional[Path | str] = None,
) -> list[GoldenQuestion]:
    """Carrega as questões do Golden Benchmark a partir do JSON."""
    if caminho is None:
        from iris.config import REPO_ROOT

        caminho = REPO_ROOT / "data" / "golden_benchmark.json"

    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Golden benchmark não encontrado em: {path}")

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenQuestion(
            id=q["id"],
            disciplina=q["disciplina"],
            ano=q["ano"],
            tema=q.get("tema", ""),
            enunciado=q["enunciado"],
            comando_conjugado_esperado=bool(q.get("comando_conjugado_esperado", False)),
            status=q.get("status", "rascunho"),
            trava_curricular=_como_tupla(q.get("trava_curricular")),
            habilidade_bncc=q.get("habilidade_bncc"),
        )
        for q in raw_data
    ]
