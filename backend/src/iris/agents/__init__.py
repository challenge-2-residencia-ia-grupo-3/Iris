"""Orquestração do Sistema Multiagentes (Extrator Curricular, Estrategista RAG, Adaptador e Auditor)."""
from iris.agents.curriculum_extractor import (
    CurriculumExtractorAgent,
    get_curriculum_extractor,
)

__all__ = [
    "CurriculumExtractorAgent",
    "get_curriculum_extractor",
]

