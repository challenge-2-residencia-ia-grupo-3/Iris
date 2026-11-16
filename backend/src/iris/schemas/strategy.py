"""Contratos Pydantic do Agente Estrategista RAG (História 2.1.1 / Issue #16)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from iris.schemas.curriculum import CurriculumInvariants


class StrategyRequest(BaseModel):
    """Payload de entrada do Agente Estrategista.

    Cada característica ativada gera uma busca filtrada pela sua barreira. O enunciado é opcional e,
    quando informado, entra na consulta para aproximar os trechos do tipo de atividade.
    """

    caracteristicas: list[str] = Field(..., min_length=1, description="Características ativadas pelo docente.")
    nivel: int = Field(default=2, ge=1, le=3, description="Nível de andaime (1, 2 ou 3).")
    invariantes: Optional[CurriculumInvariants] = Field(
        default=None, description="Travas curriculares do Agente Extrator, repassadas ao prompt."
    )
    enunciado: Optional[str] = Field(default=None, description="Texto da questão, usado só na consulta.")
    metodo: Optional[str] = Field(default=None, description="Método de busca; padrão do pacote RAG se ausente.")
    k: int = Field(default=5, ge=1, le=10, description="Trechos recuperados por característica.")
    question_id: Optional[str] = None

    @field_validator("caracteristicas")
    @classmethod
    def _sem_repeticao(cls, valor: list[str]) -> list[str]:
        if len(set(valor)) != len(valor):
            raise ValueError("Característica repetida na lista de ativadas.")
        return valor


class StrategyIntervention(BaseModel):
    """Uma intervenção da diretiva, ligada a uma característica e aos trechos que a sustentam."""

    id_caracteristica: str
    texto: str
    citacoes: list[str] = Field(default_factory=list)
    # "modelo": proposta pelo LLM e aprovada na conferência; "catalogo": ação do catálogo, sem modelo.
    origem: Literal["modelo", "catalogo"]


class StrategySource(BaseModel):
    """Fonte numerada da diretiva. Não leva o texto do trecho (há documentos de licença restrita)."""

    rotulo: str
    chunk_id: str
    doc: str
    titulo: str
    pagina: Optional[str] = None
    url: str
    referencia: str
    caracteristicas: list[str] = Field(default_factory=list)
    aviso_de_uso: Optional[str] = None


class StrategyTelemetry(BaseModel):
    """Métricas operacionais anônimas de uma chamada do Agente Estrategista (Zero-PII / LGPD)."""

    question_id: Optional[str] = None
    caracteristicas: list[str] = Field(default_factory=list)
    nivel: int = 2
    metodo_solicitado: str = ""
    metodo_efetivo: str = ""
    fallback_busca: bool = False
    provider: str = "unknown"
    model: str = "unknown"
    used_fallback: bool = False
    motivo_fallback: Optional[str] = None
    json_valido_direto: bool = True
    # True quando a resposta veio cortada no limite de tokens e as intervenções completas foram aproveitadas
    json_recuperado: bool = False
    busca_ms: float = 0.0
    llm_ms: float = 0.0
    total_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    n_trechos: int = 0
    n_intervencoes_propostas: int = 0
    n_intervencoes_aprovadas: int = 0
    timestamp_utc: str = ""


class StrategyResult(BaseModel):
    """Retorno do Agente Estrategista: diretiva com citações, fontes, conferência e telemetria."""

    # Texto pronto para `AdaptationRequest.diretiva_psicopedagogica`; vazio quando não há evidência.
    diretiva: str
    intervencoes: list[StrategyIntervention] = Field(default_factory=list)
    fontes: list[StrategySource] = Field(default_factory=list)
    caracteristicas_sem_evidencia: list[str] = Field(default_factory=list)
    # Trechos devolvidos pela busca sem a barreira da característica; foram descartados antes do prompt.
    trechos_fora_do_filtro: list[str] = Field(default_factory=list)
    # Intervenções do modelo reprovadas na conferência, com o motivo de cada uma.
    intervencoes_descartadas: list[dict[str, str]] = Field(default_factory=list)
    telemetry: StrategyTelemetry
