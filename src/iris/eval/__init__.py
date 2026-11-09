"""Módulo de avaliação, métricas de legibilidade e Golden Benchmark (Épico 4.2)."""

from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.corpus_eda import analisar_distribuicao_perguntas
from iris.eval.metrics import calcular_flesch, calcular_trcc, verificar_aderencia_nivel
from iris.eval.readability import (
    COMMAND_VERBS,
    QuestionStats,
    analyze_benchmark,
    analyze_question,
    count_conjugated_commands,
    count_syllables,
    find_commands,
    flesch_band,
    flesch_ptbr,
    load_questions,
    split_sentences,
    split_words,
    summarize,
)

__all__ = [
    "COMMAND_VERBS",
    "GoldenQuestion",
    "QuestionStats",
    "analisar_distribuicao_perguntas",
    "analyze_benchmark",
    "analyze_question",
    "calcular_flesch",
    "calcular_trcc",
    "carregar_golden_benchmark",
    "count_conjugated_commands",
    "count_syllables",
    "find_commands",
    "flesch_band",
    "flesch_ptbr",
    "load_questions",
    "split_sentences",
    "split_words",
    "summarize",
    "verificar_aderencia_nivel",
]
