"""Orquestração do Sistema Multiagentes (Extrator Curricular, Estrategista RAG, Adaptador e Auditor)."""
from iris.agents.adapter_agent import AdapterAgent, CicloComAuditor, get_adapter_agent
from iris.agents.auditor import AgenteAuditor
from iris.agents.curriculum_extractor import (
    CurriculumExtractorAgent,
    get_curriculum_extractor,
)
from iris.agents.orchestrator import (
    AuditAttemptTrace,
    MultiAgentMaterialRequest,
    MultiAgentMaterialResponse,
    MultiAgentOrchestrator,
    QuestionMultiAgentTrace,
    run_multiagent_adaptation,
)
from iris.agents.strategist_agent import StrategistAgent, get_strategist_agent

__all__ = [
    "AdapterAgent",
    "AgenteAuditor",
    "AuditAttemptTrace",
    "CicloComAuditor",
    "CurriculumExtractorAgent",
    "MultiAgentMaterialRequest",
    "MultiAgentMaterialResponse",
    "MultiAgentOrchestrator",
    "QuestionMultiAgentTrace",
    "StrategistAgent",
    "get_adapter_agent",
    "get_curriculum_extractor",
    "get_strategist_agent",
    "run_multiagent_adaptation",
]
