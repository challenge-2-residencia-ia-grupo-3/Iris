"""Schemas e contratos de validação para entrada de materiais didáticos (História 1.1.1 - Issue #4).

Atende:
- RF-01: Inserção de conteúdo por digitação direta ou upload de documentos (.pdf, .docx, .txt).
- RNF-02: Garantia de metadados de sanitização (Zero-Retention Scrubber).
- RNF-08 / Regra de Negócio: Limite mínimo de 50 caracteres e limite seguro de 2.000 palavras.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import Enum
from types import MappingProxyType
from typing import Annotated, Any, Optional

from pydantic import Field, PlainSerializer

MIN_MATERIAL_CHARS = 50
# Ausência de limite funcional fixo de palavras na interface (Issue 1.1.1).
# Limites técnicos de segurança para processamento em memória e janela de contexto da IA:
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB para upload em memória (fluxo textual padrão)
MAX_OCR_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB para upload de imagens e PDFs para OCR (História 1.1.3)
MAX_SAFE_CONTEXT_CHARS = 100_000  # ~25.000 tokens (capacidade segura da janela de contexto da IA)


class MaterialSourceType(str, Enum):
    """Formatos de origem aceitos para materiais didáticos."""

    TEXT = "text"
    TXT = "txt"
    PDF = "pdf"
    DOCX = "docx"
    # Formatos multimodais e digitalizados (História 1.1.3 - RF-03)
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    SCANNED_PDF = "scanned_pdf"
    MIXED_PDF = "mixed_pdf"


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


def validate_ocr_file_size_limit(content: bytes, max_bytes: int = MAX_OCR_FILE_SIZE_BYTES) -> int:
    """Valida se o tamanho binário do arquivo para OCR respeita o limite técnico de 25 MB.

    Aplica-se exclusivamente a imagens (.png, .jpg, .jpeg) e PDFs digitalizados ou mistos
    que necessitam de processamento visual/OCR (História 1.1.3).
    """
    size = len(content) if content else 0
    if size > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        raise MaterialValidationError(
            message=(
                f"O arquivo enviado para OCR ({size / (1024 * 1024):.1f} MB) excede o limite seguro de "
                f"processamento ({max_mb:.0f} MB). Reduza a resolução ou divida o documento."
            ),
            code="OCR_FILE_TOO_LARGE",
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
                f"Quantidade atual: {char_count} {'caractere' if char_count == 1 else 'caracteres'}."
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


# Modelo de Resposta (Fluxo Textual Tradicional)
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
# Contratos Unificados e Modelos de OCR e Análise Visual (História 1.1.3 - RF-03)
# ==============================================================================

# Sentinela privada para prevenção de instanciação acidental direta de RawContent
_RAW_CONTENT_INTERNAL_GUARD = object()

# Tipo anotado para serialização transparente de MappingProxyType via Pydantic/FastAPI
SafeMetadataMapping = Annotated[
    Mapping[str, Any],
    PlainSerializer(
        lambda v: dict(v) if isinstance(v, (MappingProxyType, dict)) else (v if v is not None else {}),
        return_type=dict[str, Any],
    ),
]


@dataclass(frozen=True)
class RawContent:
    """Contrato unificado e imutável de ingestão de materiais didáticos (docs/arquitetura.md).

    Ponto de convergência canônico tanto para o fluxo textual tradicional quanto
    para extração multimodal via OCR (História 1.1.3 / DEP-OC-01).

    Garantia arquitetural de integridade e segurança (RNF-02):
    1. O campo `text` contém o conteúdo textual submetido ao sanitizador local (`sanitize_pii`),
       respeitando os limites das regras de detecção.
    2. Imutabilidade (@dataclass(frozen=True)): impede modificações posteriores em `text`,
       `source_type`, `metadata` e `pii_sanitized` após a construção.
    3. Proteção defensiva de metadados: cópia defensiva na construção e empacotamento em
       `MappingProxyType`, impedindo tanto mutações no dicionário de origem quanto alterações
       posteriores diretamente no objeto.
    4. Prevenção de uso acidental: sentinela interna que desestimula instanciações diretas fora
       da fábrica oficial `create_sanitized_raw_content(...)` ou `RawContent.from_raw_text(...)`.
    """

    text: str  # Conteúdo textual sanitizado (destinado à resposta da API, interface e pipeline pedagógico)
    source_type: MaterialSourceType  # Formato/origem validado estritamente
    metadata: SafeMetadataMapping  # Metadados imutáveis com cópia defensiva e serialização segura
    pii_sanitized: bool  # Confirmação de que a rotina de sanitização foi executada
    _guard: object = Field(default=None, exclude=True)  # Sentinela interna excluída da serialização pública da API

    def __post_init__(self) -> None:
        # 1. Prevenção de uso acidental direto fora do fluxo oficial da fábrica
        if self._guard is not _RAW_CONTENT_INTERNAL_GUARD:
            raise PermissionError(
                "Instanciação direta de RawContent é proibida por governança de segurança (RNF-02). "
                "Utilize a função oficial `create_sanitized_raw_content(...)` "
                "ou a fábrica `RawContent.from_raw_text(...)` para assegurar que a sanitização "
                "preventiva de PII seja executada antes da emissão do contrato."
            )

        # 2. Validação e normalização estrita de source_type em instância congelada
        if isinstance(self.source_type, str):
            try:
                norm_type = MaterialSourceType(self.source_type)
                object.__setattr__(self, "source_type", norm_type)
            except ValueError as err:
                valid_types = ", ".join(t.value for t in MaterialSourceType)
                raise ValueError(
                    f"Tipo de fonte inválido '{self.source_type}'. "
                    f"Os formatos aceitos pela plataforma são: {valid_types}."
                ) from err
        elif not isinstance(self.source_type, MaterialSourceType):
            raise ValueError(
                f"O campo 'source_type' deve ser uma instância de MaterialSourceType ou string correspondente. "
                f"Recebido: {type(self.source_type).__name__}."
            )

        # 3. Validação do sinalizador de sanitização
        if not isinstance(self.pii_sanitized, bool):
            raise ValueError("O campo 'pii_sanitized' deve ser explicitamente booleano.")

        # 4. Cópia defensiva e blindagem imutável de metadados
        if not isinstance(self.metadata, MappingProxyType):
            safe_meta = copy.deepcopy(self.metadata) if self.metadata else {}
            object.__setattr__(self, "metadata", MappingProxyType(safe_meta))

    @classmethod
    def from_raw_text(
        cls,
        raw_text: str,
        source_type: MaterialSourceType | str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RawContent:
        """Fábrica oficial que executa efetivamente sanitize_pii antes de instanciar RawContent.

        Garante que o chamador não possa ignorar a sanitização: o texto original
        é submetido ao sanitizador local e somente o resultado higienizado compõe o contrato.
        """
        _, raw_content = create_sanitized_raw_content(
            raw_text=raw_text,
            source_type=source_type,
            metadata=metadata,
        )
        return raw_content

    def model_dump(self) -> dict[str, Any]:
        st_val = self.source_type.value if isinstance(self.source_type, MaterialSourceType) else str(self.source_type)
        return {
            "text": self.text,
            "source_type": st_val,
            "metadata": dict(self.metadata) if self.metadata else {},
            "pii_sanitized": self.pii_sanitized,
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


def create_sanitized_raw_content(
    raw_text: str,
    source_type: MaterialSourceType | str,
    metadata: Optional[dict[str, Any]] = None,
) -> tuple[str, RawContent]:
    """Fluxo oficial e centralizado de construção segura do contrato canônico RawContent (RNF-02).

    Executa o fluxo de segurança em 5 passos:
    1. Recebe o texto original não-sanitizado (`raw_text`).
    2. Executa a sanitização preventiva local (`sanitize_pii`), substituindo dados pessoais identificados por tags semânticas.
    3. Registra explicitamente nos metadados que a rotina de sanitização foi executada (`sanitization_executed=True`)
       e a contagem de substituições realizadas (`pii_removed_count`), realizando cópia defensiva.
    4. Constrói o contrato canônico imutável `RawContent` (frozen=True, protegido por MappingProxyType).
    5. Preserva o texto original separado, destinado exclusivamente à revisão docente em tela (HITL, em memória volátil).

    Retorna:
        tuple[str, RawContent]: (raw_text_original_para_revisao, raw_content_sanitizado)
    """
    from iris.security.pii_scrubber import sanitize_pii

    # 1 e 2. Executa efetivamente o sanitizador sobre o texto original
    sanitized_text, pii_count = sanitize_pii(raw_text)

    # 3. Cópia defensiva dos metadados com semântica precisa
    meta = copy.deepcopy(metadata) if metadata else {}
    meta["sanitization_executed"] = True
    meta["pii_removed_count"] = pii_count

    # 4. Constrói RawContent imutável com a sentinela interna autorizada
    raw_content = RawContent(
        text=sanitized_text,
        source_type=source_type,  # type: ignore[arg-type]
        metadata=MappingProxyType(meta),
        pii_sanitized=True,
        _guard=_RAW_CONTENT_INTERNAL_GUARD,
    )
    return raw_text, raw_content


@dataclass
class PageVisualAnalysis:
    """Indicadores de análise visual de uma página ou imagem individual (História 1.1.3).

    Representa métricas mensuráveis da página completa (área, respiro, complexidade óptica e contraste).
    Não realiza segmentação por questão individual nem diagnóstico semântico de distratores.
    """

    page_number: int  # Índice da página (1 para imagem avulsa, 1..N para páginas de PDF)
    page_type: str  # "image", "scanned", "mixed", "textual"
    width: int  # Largura em pixels
    height: int  # Altura em pixels
    edge_density: float  # Densidade de transições de gradiente (Pillow FIND_EDGES)
    whitespace_ratio: float  # Proporção de espaço de respiro/fundo claro
    contrast_ratio: float  # Faixa dinâmica de luminância
    clutter_level: str  # Nível de densidade visual: "baixa", "moderada" ou "alta"
    possible_visual_clutter: bool  # Indicador orientativo de possível poluição visual
    legibility_status: str = "ok"  # "ok", "low_resolution", "unreadable"
    rejection_reason: Optional[str] = None  # Mensagem explicativa caso a imagem seja ilegível

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class VisualAnalysisReport:
    """Relatório consolidado de análise visual do material submetido (História 1.1.3).

    Agrega as análises por página e emite indicadores orientativos para apoio docente.
    """

    overall_clutter_level: str  # "baixa", "moderada" ou "alta"
    has_high_clutter: bool  # True se alguma página apresentar nível alto de densidade visual
    total_pages_analyzed: int  # Total de páginas/imagens analisadas visualmente
    flagged_pages: list[int]  # Lista com o número das páginas com possível poluição visual
    pages: list[PageVisualAnalysis]  # Detalhamento por página
    notes: Optional[str] = None  # Observações orientativas para o docente

    def model_dump(self) -> dict[str, Any]:
        return {
            "overall_clutter_level": self.overall_clutter_level,
            "has_high_clutter": self.has_high_clutter,
            "total_pages_analyzed": self.total_pages_analyzed,
            "flagged_pages": list(self.flagged_pages),
            "pages": [p.model_dump() if hasattr(p, "model_dump") else p for p in self.pages],
            "notes": self.notes,
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class OcrMaterialResponse:
    """Resposta estruturada do processamento multimodal e OCR para a interface docente (Etapa 1).

    Responsabilidades estritas de cada campo na API HTTP (RNF-02 / Zero-PII):
    1. `status` / `message`: Metadados operacionais do protocolo HTTP da API.
    2. `raw_text`: Texto extraído e já sanitizado (`raw_content.text`) entregue à interface docente
       para conferência e revisão humana (HITL), garantindo que nenhum dado pessoal original seja
       persistido em `sessionStorage` ou devolvido pela API.
    3. `raw_content`: Entidade canônica de ingestão segura contendo o texto sanitizado (`raw_content.text`,
       livre de PII identificável), metadados e `pii_sanitized=True`. É esta estrutura canônica
       que transita para o `StructuralDecomposer`, motor RAG e serviços de IA.
    4. `metadata`: Métricas quantitativas do texto e indicação fiel de remoção de PII (`sanitized = pii_removed_count > 0`).
    5. `visual_analysis`: Relatório com métricas de qualidade de imagem, resolução, avisos parciais e densidade visual.
    """

    status: str
    message: str
    raw_text: str  # Texto sanitizado retornado pela API para conferência segura em tela (RNF-02)
    raw_content: RawContent  # Contrato unificado seguro com texto sanitizado para processamento e IA
    metadata: MaterialMetadata  # Metadados quantitativos de volume e formato
    visual_analysis: VisualAnalysisReport  # Indicadores de análise visual por página

    @property
    def sanitized_text(self) -> str:
        """Propriedade conveniente que referencia diretamente o texto seguro de `raw_content.text`,
        evitando duplicação redundante de strings em memória e prevenindo divergência de estado."""
        return self.raw_content.text

    def model_dump(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "raw_text": self.raw_text,
            "raw_content": self.raw_content.model_dump(),
            "metadata": self.metadata.model_dump(),
            "visual_analysis": self.visual_analysis.model_dump(),
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


# ==============================================================================
# Modelos de Organização Estrutural de Textos Corridos (História 1.1.4 - RF-02 Extensão)
# ==============================================================================


@dataclass
class StructuralNode:
    """Nó atômico ou composto na árvore hierárquica de textos corridos (História 1.1.4).

    Representa títulos, subtítulos, seções, subseções, parágrafos, listas e itens de lista,
    preservando sequência, hierarquia pai-filho e conteúdo integral.
    """

    id: str  # ex.: "node_1", "sec_1", "p_1", "list_1", "item_1"
    element_type: str  # "title", "subtitle", "section", "subsection", "paragraph", "list", "list_item", "unclassified"
    content: str  # Conteúdo textual integral do elemento
    order: int  # Posição sequencial no documento original (1-based)
    level: Optional[int] = None  # Nível de profundidade hierárquica (1=Título, 2=Seção/Subtítulo, 3=Subseção, etc.)
    parent_id: Optional[str] = None  # ID do elemento pai na hierarquia
    children: Optional[list[StructuralNode]] = None  # Filhos imediatos
    metadata: Optional[dict[str, Any]] = None  # Informações complementares (marcador, tipo de lista, numeração)

    def __post_init__(self) -> None:
        if self.children is None:
            self.children = []
        if self.metadata is None:
            self.metadata = {}

    def get_descendants(self) -> list[StructuralNode]:
        """Retorna todos os nós descendentes em ordem pré-fixada."""
        result: list[StructuralNode] = []
        for child in self.children:
            result.append(child)
            result.extend(child.get_descendants())
        return result

    def get_paragraphs(self) -> list[StructuralNode]:
        """Retorna todos os parágrafos contidos dentro deste nó ou de seus filhos."""
        return [n for n in [self] + self.get_descendants() if n.element_type == "paragraph"]

    def get_lists(self) -> list[StructuralNode]:
        """Retorna todas as listas contidas dentro deste nó ou de seus filhos."""
        return [n for n in [self] + self.get_descendants() if n.element_type == "list"]

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "element_type": self.element_type,
            "content": self.content,
            "order": self.order,
            "level": self.level,
            "parent_id": self.parent_id,
            "children": [c.model_dump() if hasattr(c, "model_dump") else c for c in self.children],
            "metadata": dict(self.metadata) if self.metadata else {},
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class ProseStructure:
    """Estrutura hierárquica de texto corrido pedagógico (História 1.1.4 - RF-02 Extensão).

    Disponibiliza os elementos e suas relações para o mecanismo de adaptação pedagógica (História 2.1.3).
    """

    title: Optional[str]  # Título principal do documento, se identificado
    root_nodes: list[StructuralNode]  # Nós de nível superior da árvore
    total_elements: int  # Contagem total de elementos estruturados
    max_depth: int  # Profundidade máxima da hierarquia identificada

    def flatten(self) -> list[StructuralNode]:
        """Retorna todos os nós em ordem linear original de ocorrência."""
        nodes: list[StructuralNode] = []
        for root in self.root_nodes:
            nodes.append(root)
            nodes.extend(root.get_descendants())
        nodes.sort(key=lambda n: n.order)
        return nodes

    def get_sections(self) -> list[StructuralNode]:
        """Retorna todos os nós do tipo 'section', 'subsection', 'title' ou 'subtitle'."""
        return [n for n in self.flatten() if n.element_type in ("title", "subtitle", "section", "subsection")]

    def get_paragraphs(self) -> list[StructuralNode]:
        """Retorna todos os parágrafos em sequência para análise e intervenção pedagógica."""
        return [n for n in self.flatten() if n.element_type == "paragraph"]

    def get_lists(self) -> list[StructuralNode]:
        """Retorna todas as listas estruturadas."""
        return [n for n in self.flatten() if n.element_type == "list"]

    def find_by_id(self, node_id: str) -> Optional[StructuralNode]:
        """Busca um nó específico por ID."""
        for n in self.flatten():
            if n.id == node_id:
                return n
        return None

    def get_outline(self) -> list[dict[str, Any]]:
        """Retorna um sumário simplificado (outline) para organizadores cognitivos (DUA)."""
        return [
            {
                "id": n.id,
                "title": n.content,
                "level": n.level,
                "element_type": n.element_type,
                "order": n.order,
            }
            for n in self.get_sections()
        ]

    def model_dump(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "root_nodes": [r.model_dump() if hasattr(r, "model_dump") else r for r in self.root_nodes],
            "total_elements": self.total_elements,
            "max_depth": self.max_depth,
        }

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class MaterialStructure:
    """Estrutura decomposta completa do material pedagógico (História 1.1.2 e 1.1.4 - RF-02)."""

    header: Optional[str]  # Cabeçalho institucional e contexto inicial
    instructions: Optional[str]  # Instruções gerais da prova
    context_blocks: list[ContextBlock]  # Textos de apoio e leituras compartilhadas
    questions: list[QuestionItem]  # Lista sequencial ordenada de questões
    unclassified_blocks: list[str]  # Conteúdos não classificados (garantia de zero-loss)
    total_questions: int  # Total de questões identificadas
    has_shared_contexts: bool  # Indicador se há textos compartilhados entre múltiplas questões
    prose_structure: Optional[ProseStructure] = None  # Estrutura hierárquica do texto corrido (História 1.1.4)

    def model_dump(self) -> dict[str, Any]:
        return {
            "header": self.header,
            "instructions": self.instructions,
            "context_blocks": [cb.model_dump() if hasattr(cb, "model_dump") else cb for cb in self.context_blocks],
            "questions": [q.model_dump() if hasattr(q, "model_dump") else q for q in self.questions],
            "unclassified_blocks": list(self.unclassified_blocks),
            "total_questions": self.total_questions,
            "has_shared_contexts": self.has_shared_contexts,
            "prose_structure": (
                self.prose_structure.model_dump()
                if self.prose_structure and hasattr(self.prose_structure, "model_dump")
                else None
            ),
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

