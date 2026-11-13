"""Orquestração do Sistema Multiagentes (Extrator Curricular, Estrategista RAG, Adaptador e Auditor)."""
from iris.agents.adapter_agent import AdapterAgent, CicloComAuditor, get_adapter_agent
from iris.agents.curriculum_extractor import (
    CurriculumExtractorAgent,
    get_curriculum_extractor,
)
from iris.agents.strategist_agent import StrategistAgent, get_strategist_agent

__all__ = [
    "AdapterAgent",
    "CicloComAuditor",
    "get_adapter_agent",
    "CurriculumExtractorAgent",
    "get_curriculum_extractor",
    "StrategistAgent",
    "get_strategist_agent",
]

