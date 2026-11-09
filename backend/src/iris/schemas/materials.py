"""Schemas e contratos de validação para entrada de materiais didáticos (História 1.1.1 - Issue #4).

Atende:
- RF-01: Inserção de conteúdo por digitação direta ou upload de documentos (.pdf, .docx, .txt).
- RNF-02: Garantia de metadados de sanitização (Zero-Retention Scrubber).
- RNF-08 / Regra de Negócio: Limite mínimo de 50 caracteres e limite seguro de 2.000 palavras.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional

MIN_MATERIAL_CHARS = 50
# Ausência de limite funcional fixo de palavras na interface (Issue 1.1.1).
# Limites técnicos de segurança para processamento em memória e janela de contexto da IA:
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB para upload em memória
MAX_SAFE_CONTEXT_CHARS = 100_000  # ~25.000 tokens (capacidade segura da janela de contexto da IA)


class MaterialSourceType(str, Enum):
    """Formatos de origem aceitos para materiais didáticos."""

    TEXT = "text"
    TXT = "txt"
    PDF = "pdf"
    DOCX = "docx"


class MaterialValidationError(ValueError):
    """Erro de validação de regras de negócio de materiais didáticos."""

    def __init__(self, message: str, code: str, field: str = "text") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field

    def to_dict(self) -> dict[str, str]:
        return {"detail": self.message, "code": self.code, "field": self.field}


def validate_file_size_limit(content: bytes, max_bytes: int = MAX_FILE_SIZE_BYTES) -> int:
    """Valida se o tamanho binário do arquivo respeita o limite técnico de processamento em memória."""
    size = len(content) if content else 0
    if size > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        raise MaterialValidationError(
            message=(
                f"O arquivo enviado ({size / (1024 * 1024):.1f} MB) excede o limite técnico seguro de "
                f"processamento em memória ({max_mb:.0f} MB). Reduza o tamanho do arquivo ou divida o documento."
            ),
            code="FILE_TOO_LARGE",
            field="file",
        )
    return size


def validate_material_content(text: str, max_context_chars: int = MAX_SAFE_CONTEXT_CHARS) -> tuple[int, int]:
    """Valida se o texto atende às restrições da História 1.1.1.

    Regras:
    1. Mínimo de 50 caracteres (após remoção de espaços em branco externos).
    2. Sem limite máximo funcional fixo de palavras na interface.
    3. Respeito à capacidade segura de processamento da janela de contexto da IA (`MAX_SAFE_CONTEXT_CHARS`).

    Retorna:
        tuple[int, int]: (quantidade_caracteres, quantidade_palavras)

    Lança:
        MaterialValidationError: caso alguma das regras seja violada.
    """
    if not isinstance(text, str):
        raise MaterialValidationError(
            message="O conteúdo do material deve ser uma sequência de texto válida.",
            code="INVALID_TEXT_TYPE",
            field="text",
        )

    cleaned = text.strip()
    char_count = len(cleaned)

    if char_count < MIN_MATERIAL_CHARS:
        raise MaterialValidationError(
            message=(
                f"O material deve conter no mínimo {MIN_MATERIAL_CHARS} caracteres para permitir a análise pedagógica. "
                f"Quantidade atual: {char_count} caracter(es)."
            ),
            code="TEXT_TOO_SHORT",
            field="text",
        )

    if char_count > max_context_chars:
        raise MaterialValidationError(
            message=(
                "O conteúdo ultrapassa a capacidade segura de processamento da janela de contexto da IA "
                f"({max_context_chars:,} caracteres). Divida o material em partes menores para garantir a qualidade da adaptação."
            ),
            code="CONTEXT_WINDOW_EXCEEDED",
            field="text",
        )

    words = cleaned.split()
    word_count = len(words)

    return char_count, word_count


# Modelo de Metadados
@dataclass
class MaterialMetadata:
    """Metadados estruturados sobre o material extraído e processado."""

    source_type: str
    char_count: int
    word_count: int
    sanitized: bool
    pii_removed_count: int
    filename: Optional[str] = None
    estimated_tokens: int = 0

    def __post_init__(self) -> None:
        if self.estimated_tokens == 0 and self.char_count > 0:
            self.estimated_tokens = max(1, round(self.char_count / 4))

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


# Modelo de Resposta
@dataclass
class MaterialResponse:
    """Resposta estruturada para a conferência imediata docente do material."""

    status: str
    message: str
    raw_text: str
    metadata: MaterialMetadata

    def model_dump(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "raw_text": self.raw_text,
            "metadata": self.metadata.model_dump(),
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


# ==============================================================================
# Modelos de Decomposição Estrutural (História 1.1.2 - Issue #5 / RF-02)
# ==============================================================================


@dataclass
class AlternativeItem:
    """Alternativa individual de resposta em questões de múltipla escolha."""

    letter: str  # ex.: "A", "B", "C", "D", "E" ou "a", "b", "c"...
    text: str  # Texto da alternativa

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class QuestionItem:
    """Bloco estruturado independente de uma questão de atividade pedagógica."""

    id: str  # Identificador interno sequencial (ex.: "q_1", "q_2")
    original_number: str  # Numeração original do material (ex.: "1", "Questão 01", "2)", "3.")
    statement: str  # Comando ou enunciado da questão
    question_type: str  # "multipla_escolha", "dissertativa" ou "mista"
    options: Optional[list[AlternativeItem]] = None  # Lista de alternativas quando existente
    answer_space: Optional[str] = None  # Espaço ou linhas destinados à resposta (linhas pontilhadas/sublinhadas)
    context_refs: Optional[list[str]] = None  # IDs dos ContextBlocks vinculados
    raw_text: str = ""  # Conteúdo integral bruto do bloco da questão

    def __post_init__(self) -> None:
        if self.context_refs is None:
            self.context_refs = []
        if self.options is None:
            self.options = []

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_number": self.original_number,
            "statement": self.statement,
            "question_type": self.question_type,
            "options": [opt.model_dump() if hasattr(opt, "model_dump") else opt for opt in self.options],
            "answer_space": self.answer_space,
            "context_refs": list(self.context_refs),
            "raw_text": self.raw_text,
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class ContextBlock:
    """Bloco de texto de apoio, leitura obrigatória ou contextualização compartilhada."""

    id: str  # Identificador interno (ex.: "ctx_1")
    text: str  # Conteúdo integral do texto de apoio
    title: Optional[str] = None  # Título identificado (ex.: "Texto 1: A Era Vargas")
    instruction: Optional[str] = None  # Diretiva (ex.: "Leia o texto a seguir para responder às questões 1 e 2")
    target_questions: list[str] = None  # type: ignore[assignment]  # Numerações originais ou IDs das questões vinculadas

    def __post_init__(self) -> None:
        if self.target_questions is None:
            self.target_questions = []

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "instruction": self.instruction,
            "target_questions": list(self.target_questions),
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class MaterialStructure:
    """Estrutura decomposta completa do material pedagógico (História 1.1.2 - RF-02)."""

    header: Optional[str]  # Cabeçalho institucional e contexto inicial
    instructions: Optional[str]  # Instruções gerais da prova
    context_blocks: list[ContextBlock]  # Textos de apoio e leituras compartilhadas
    questions: list[QuestionItem]  # Lista sequencial ordenada de questões
    unclassified_blocks: list[str]  # Conteúdos não classificados (garantia de zero-loss)
    total_questions: int  # Total de questões identificadas
    has_shared_contexts: bool  # Indicador se há textos compartilhados entre múltiplas questões

    def model_dump(self) -> dict[str, Any]:
        return {
            "header": self.header,
            "instructions": self.instructions,
            "context_blocks": [cb.model_dump() if hasattr(cb, "model_dump") else cb for cb in self.context_blocks],
            "questions": [q.model_dump() if hasattr(q, "model_dump") else q for q in self.questions],
            "unclassified_blocks": list(self.unclassified_blocks),
            "total_questions": self.total_questions,
            "has_shared_contexts": self.has_shared_contexts,
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()



# Integração transparente com Pydantic v2 quando disponível
try:
    from pydantic import BaseModel, Field, field_validator

    class MaterialTextInput(BaseModel):
        """Contrato de entrada para inserção direta de texto pelo professor."""

        text: str = Field(
            ...,
            description="Conteúdo textual do material didático (avaliação, enunciado ou texto-base)",
            examples=["Leia o texto a seguir e responda às questões sobre a Revolução Industrial..."],
        )

        @field_validator("text")
        @classmethod
        def check_text_not_empty(cls, v: str) -> str:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("O campo 'text' não pode ser vazio ou conter apenas espaços.")
            return v

except ImportError:
    # Fallback compatível para execução com standard library sem pydantic instalado
    class MaterialTextInput:  # type: ignore
        """Contrato de entrada compatível quando Pydantic não estiver instalado."""

        def __init__(self, text: str) -> None:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("O campo 'text' não pode ser vazio ou conter apenas espaços.")
            self.text = text

        def model_dump(self) -> dict[str, Any]:
            return {"text": self.text}

        def dict(self) -> dict[str, Any]:
            return self.model_dump()

