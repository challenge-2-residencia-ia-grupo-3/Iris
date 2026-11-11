"""Orquestração do Sistema Multiagentes (Extrator Curricular, Estrategista RAG, Adaptador e Auditor)."""
from iris.agents.adapter_agent import AdapterAgent, get_adapter_agent
from iris.agents.curriculum_extractor import (
    CurriculumExtractorAgent,
    get_curriculum_extractor,
)

__all__ = [
    "AdapterAgent",
    "get_adapter_agent",
    "CurriculumExtractorAgent",
    "get_curriculum_extractor",
]

