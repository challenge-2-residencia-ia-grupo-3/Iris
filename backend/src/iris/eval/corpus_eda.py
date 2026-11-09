"""Utilitários de suporte à EDA do corpus normativo/científico e benchmark (Épico 4.2)."""

from __future__ import annotations

from typing import Any, Dict, List

from iris.eval.readability import analyze_question, summarize


def analisar_distribuicao_perguntas(perguntas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Retorna sumário estatístico e contagem por disciplina e ano."""
    disciplinas: Dict[str, int] = {}
    anos: Dict[str, int] = {}
    analisadas = []

    for p in perguntas:
        disc = str(p.get("disciplina", "Outro"))
        ano = str(p.get("ano", "Outro"))
        disciplinas[disc] = disciplinas.get(disc, 0) + 1
        anos[ano] = anos.get(ano, 0) + 1

        stats = analyze_question(str(p.get("id", "")), p.get("enunciado", ""))
        row = dict(p)
        row.update(stats.__dict__)
        analisadas.append(row)

    resumo = summarize(analisadas)
    resumo["distribuicao_disciplinas"] = disciplinas
    resumo["distribuicao_anos"] = anos
    return resumo
