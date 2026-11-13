"""Contratos Pydantic do Agente Adaptador Pedagógico (História 2.1.3 / Issue #18)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from iris.schemas.curriculum import CurriculumInvariants

# RNF-07: tempo total tolerável por nível de adaptação, em milissegundos.
LIMITE_LATENCIA_MS = {1: 15_000.0, 2: 40_000.0, 3: 40_000.0}


class AdaptationRequest(BaseModel):
    """Payload de entrada do Agente Adaptador.

    A diretiva psicopedagógica é produzida pelo Agente Estrategista RAG. Ela é opcional: sem ela,
    o Adaptador trabalha só com as diretrizes de andaime do catálogo para a característica e o nível.
    """

    enunciado: str = Field(..., min_length=15, description="Texto original da questão.")
    id_caracteristica: str = Field(..., description="Característica funcional selecionada pelo docente.")
    nivel: int = Field(default=2, ge=1, le=3, description="Nível de andaime (1, 2 ou 3).")
    invariantes: CurriculumInvariants = Field(..., description="Travas curriculares do Agente Extrator.")
    diretiva_psicopedagogica: Optional[str] = Field(
        default=None, description="Diretiva do Agente Estrategista RAG, em texto."
    )
    # Preenchidos só no ciclo de auto-correção do Agente Auditor (História 2.1.4 / Issue #19).
    feedback_auditor: Optional[str] = Field(
        default=None, description="Correção pedida pelo Agente Auditor ao reprovar a tentativa anterior."
    )
    minuta_anterior: Optional[str] = Field(
        default=None, description="Minuta reprovada pelo Agente Auditor na tentativa anterior."
    )
    question_id: Optional[str] = None


class ScopeReport(BaseModel):
    """Laudo determinístico do isolamento de escopo de uma adaptação (sem LLM)."""

    aprovado: bool
    # False quando a característica não tem regra de acréscimo definida: só a trava curricular decide.
    regra_aplicada: bool
    palavras_perdidas: list[str] = Field(default_factory=list)
    palavras_novas: list[str] = Field(default_factory=list)
    conectivos_removidos: int = 0
    conceitos_perdidos: list[str] = Field(default_factory=list)
    ordem_alterada: bool = False
    estrutura_alterada: bool = False
    violacoes: list[str] = Field(default_factory=list)


class AdaptationTelemetry(BaseModel):
    """Métricas operacionais anônimas de uma chamada do Agente Adaptador (Zero-PII / LGPD)."""

    question_id: Optional[str] = None
    id_caracteristica: str = ""
    nivel: int = 2
    tentativa: int = 1
    tamanho_enunciado_chars: int = 0
    provider: str = "unknown"
    model: str = "unknown"
    used_fallback: bool = False
    motivo_fallback: Optional[str] = None
    json_valido_direto: bool = True
    total_ms: float = 0.0
    load_ms: float = 0.0
    prompt_eval_ms: float = 0.0
    eval_ms: float = 0.0
    inference_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tokens_per_sec: float = 0.0
    limite_ms: float = 0.0
    dentro_do_limite: bool = True
    escopo_aprovado: bool = True
    timestamp_utc: str = ""


class AdaptationResult(BaseModel):
    """Retorno do Agente Adaptador: minuta adaptada, justificativas, laudo de escopo e telemetria."""

    texto_adaptado: str
    justificativas: list[str] = Field(default_factory=list)
    # False quando o texto devolvido é o original (nenhuma ação do nível se aplicava ou pôde ser garantida).
    adaptacao_aplicada: bool
    escopo: ScopeReport
    telemetry: AdaptationTelemetry
