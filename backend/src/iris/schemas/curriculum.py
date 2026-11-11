"""Contratos Pydantic de Invariantes Curriculares e Travas Pedagógicas (História 2.1.2 / Issue #17)."""
from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class CurriculumInvariants(BaseModel):
    """Contrato estruturado dos invariantes curriculares inegociáveis de uma atividade pedagógica.
    
    Produzido pelo Agente Extrator Curricular (RF-08, RF-11) e validado pelo docente na Etapa 3.
    Serve como restrição rígida mandatória para o Agente Adaptador e para o Agente Auditor (TRCC).
    """

    conceitos_obrigatorios: list[str] = Field(
        default_factory=list,
        description="Lista de conceitos centrais inegociáveis que devem permanecer na questão adaptada (TRCC >= 95%).",
        min_length=1,
    )
    termos_tecnicos_intocaveis: list[str] = Field(
        default_factory=list,
        description="Vocabulário técnico ou acadêmico próprio da disciplina que não deve ser substituído por gírias ou infantilizado.",
    )
    verbo_comando_bncc: str = Field(
        ...,
        description="Verbo taxonômico indicativo da operação cognitiva exigida pela questão (ex: 'calcular', 'inferir', 'identificar').",
        min_length=2,
    )
    operacao_cognitiva: str = Field(
        ...,
        description="Descrição sucinta da ação cognitiva esperada do estudante para resolver a questão.",
        min_length=5,
    )
    habilidade_bncc_sugerida: Optional[str] = Field(
        default=None,
        description="Código alfanumérico da habilidade BNCC inferida (ex: 'EF06CI05', 'EF08MA03'), quando aplicável.",
    )
    alerta_anti_muleta: Optional[str] = Field(
        default=None,
        description="Diretriz explícita do que o Adaptador NÃO deve fazer para não entregar a resposta ou eliminar o desafio cognitivo.",
    )
    justificativa_preservacao: str = Field(
        default="Preservação necessária para assegurar a validade pedagógica e evitar subexposição cognitiva (efeito muleta).",
        description="Fundamentação pedagógica da trava curricular à luz do DUA e das diretrizes do Challenge 2.",
    )

    @field_validator("conceitos_obrigatorios", mode="before")
    @classmethod
    def _sanitizar_conceitos(cls, v: object) -> list[str]:
        if isinstance(v, str):
            itens = re.split(r"[;\n,]", v)
        elif isinstance(v, (list, tuple, set)):
            itens = list(v)
        else:
            return []
        # Remove vazios e duplicatas preservando ordem
        vistos: set[str] = set()
        resultado: list[str] = []
        for item in itens:
            limpo = str(item).strip()
            if limpo and limpo.lower() not in vistos:
                vistos.add(limpo.lower())
                resultado.append(limpo)
        if not resultado:
            resultado = ["conceito_geral"]
        return resultado

    @field_validator("verbo_comando_bncc", mode="before")
    @classmethod
    def _normalizar_verbo(cls, v: object) -> str:
        if not v or not isinstance(v, str):
            return "identificar"
        v_limpo = v.strip().lower()
        correcoes = {
            "resolvar": "resolver",
            "leer": "ler",
            "leia": "ler",
            "calcule": "calcular",
            "explique": "explicar",
            "identifique": "identificar",
            "responda": "responder",
        }
        return correcoes.get(v_limpo, v_limpo)


class ExtractionRequest(BaseModel):
    """Payload de entrada para o Agente Extrator Curricular."""

    enunciado: str = Field(..., min_length=15, description="Texto original da questão ou enunciado da atividade.")
    contexto_apoio: Optional[str] = Field(default=None, description="Texto-base, poema, tabela ou contextualização de apoio.")
    disciplina: Optional[str] = Field(default=None, description="Componente curricular (ex: Português, Matemática, Ciências).")
    ano_escolar: Optional[str] = Field(default=None, description="Ano ou etapa escolar (ex: '6º ano', 'Ensino Médio').")
    trava_manual_docente: Optional[list[str]] = Field(default=None, description="Travas pré-existentes fornecidas pelo professor.")


def classificar_faixa_etaria(ano_escolar: Optional[str]) -> str:
    """Mapeia o ano escolar informado para uma faixa etária/etapa pedagógica padronizada."""
    if not ano_escolar or not ano_escolar.strip():
        return "Não informado"
    norm = ano_escolar.strip().lower()
    if any(k in norm for k in ("médio", "medio", "em", "1ª série", "2ª série", "3ª série")):
        return "Ensino Médio (15-17 anos)"
    if any(k in norm for k in ("4º", "4°", "4o", "5º", "5°", "5o")):
        return "Fund. I (9-10 anos)"
    if any(k in norm for k in ("6º", "6°", "6o", "7º", "7°", "7o")):
        return "Fund. II Inicial (11-12 anos)"
    if any(k in norm for k in ("8º", "8°", "8o", "9º", "9°", "9o")):
        return "Fund. II Final (13-14 anos)"
    return "Outro"


class ExtractionTelemetry(BaseModel):
    """Métricas operacionais anônimas da execução do Agente Extrator (Zero-PII / LGPD)."""

    question_id: Optional[str] = None
    disciplina: str = "Não informada"
    ano_escolar: str = "Não informado"
    faixa_etaria: str = "Não informado"
    tema: str = "Não informado"
    comando_conjugado: Optional[bool] = None
    tamanho_enunciado_chars: int = 0
    provider: str = "unknown"
    model: str = "unknown"
    used_fallback: bool = False
    json_valido_direto: bool = True
    total_ms: float = 0.0
    load_ms: float = 0.0
    prompt_eval_ms: float = 0.0
    eval_ms: float = 0.0
    inference_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_per_sec: float = 0.0
    trava_recall: Optional[float] = None
    timestamp_utc: str = ""


class ExtractionResult(BaseModel):
    """Retorno completo do Agente Extrator: invariantes curriculares + telemetria operacional."""

    invariants: CurriculumInvariants
    telemetry: ExtractionTelemetry
