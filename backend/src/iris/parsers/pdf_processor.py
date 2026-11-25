"""Processador, classificador e renderizador de documentos PDF em memória.

Atende à História 1.1.3 (OCR e Análise Visual - Etapa 4.A):
- Abertura e inspeção segura de PDFs em memória (Zero-Database / sem arquivos em disco);
- Extração de texto nativo por página sem duplicação;
- Detecção e catalogação de blocos e regiões de imagem com coordenadas (bbox);
- Classificação heurística de páginas em 'textual', 'scanned' e 'mixed';
- Consolidação do tipo de documento (MaterialSourceType.PDF, SCANNED_PDF, MIXED_PDF);
- Validação estrita dos limites de tamanho (10 MB para textual, 25 MB para escaneado/misto);
- Renderização sequencial de páginas inteiras ou recortes visuais (clip) com controle de memória;
- Liberação garantida de recursos e fechamento de documentos PyMuPDF (fitz) em todos os caminhos.

AVISO DE ESCOPO:
Este módulo NÃO executa OCR nem invoca Tesseract. Ele inspeciona, classifica e prepara
regiões visuais para a futura orquestração multimodal.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generator, Optional

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:  # pragma: no cover
    try:
        import pymupdf as fitz  # type: ignore[no-redef]
        _HAS_FITZ = True
    except ImportError:  # pragma: no cover
        fitz = None  # type: ignore[assignment]
        _HAS_FITZ = False

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    _HAS_PIL = False

from iris.parsers.document_extractor import normalize_extracted_text
from iris.schemas.materials import (
    MAX_FILE_SIZE_BYTES,
    MAX_OCR_FILE_SIZE_BYTES,
    MaterialSourceType,
)

# ==============================================================================
# Constantes Heurísticas e Limites Técnicos
# ==============================================================================

# Resolução de renderização padrão em DPI (Dot Per Inch)
# 150 DPI fornece excelente fidelidade para OCR e análise visual sem consumo desmedido de memória
DEFAULT_RENDER_DPI = 150

# Quantidade máxima de pixels suportada na renderização de página inteira ou região (25 Megapixels)
# Proteção estrita contra esgotamento de memória por documentos com dimensões físicas extremas.
# Nota sobre memória: Este teto limita o raster puro de pixels descompactados (~75 MB para RGB a 24 bits
# ou ~100 MB para RGBA a 32 bits). Buffers transitórios de codificação (PNG/JPEG), objetos na heap
# Python (Pillow/BytesIO) e páginas retidas nas arenas do alocador C (malloc/mmap) atuam em conjunto,
# de modo que o consumo de memória do processo deve considerar todas as etapas do ciclo de vida.
MAX_RENDER_PIXELS = 25_000_000

# Limite superior de DPI admissível para operações de renderização (10.000 DPI)
MAX_RENDER_DPI = 10_000

# Teto máximo admissível para parametrização de limites de pixels (1 Gigapixel)
MAX_SAFETY_CEILING_PIXELS = 1_000_000_000

# Mínimo de caracteres de texto nativo para considerar que uma página possui conteúdo textual útil
MIN_TEXT_CHARS_THRESHOLD = 50

# Cobertura de imagem mínima da página para classificar como "scanned" quando houver pouco/nenhum texto
SCANNED_COVERAGE_THRESHOLD = 0.60

# Cobertura de imagem mínima da página para indicar conteúdo visual relevante em página mista
MIXED_COVERAGE_THRESHOLD = 0.10

# Área mínima de uma imagem individual em relação à página para ser considerada relevante (ignora logos/ícones minúsculos)
MIN_RELEVANT_IMAGE_AREA_RATIO = 0.05


# ==============================================================================
# Exceções de Domínio de PDF
# ==============================================================================

class PdfProcessingError(Exception):
    """Exceção base para erros durante o processamento de PDFs."""

    def __init__(self, message: str, code: str = "PDF_PROCESSING_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class PdfEmptyFileError(PdfProcessingError):
    """Lançado quando o payload de bytes do PDF está vazio (0 bytes)."""

    def __init__(self, message: str = "O arquivo PDF enviado está vazio (0 bytes).", code: str = "EMPTY_FILE") -> None:
        super().__init__(message, code=code)


class PdfCorruptedError(PdfProcessingError):
    """Lançado quando o PDF está corrompido ou possui formato inválido."""

    def __init__(
        self,
        message: str = "O arquivo PDF está corrompido ou possui formato inválido.",
        code: str = "CORRUPTED_PDF",
    ) -> None:
        super().__init__(message, code=code)


class PdfNoPagesError(PdfProcessingError):
    """Lançado quando o documento PDF não possui nenhuma página navegável."""

    def __init__(self, message: str = "O documento PDF não contém páginas.", code: str = "NO_PAGES") -> None:
        super().__init__(message, code=code)


class PdfInvalidPageError(PdfProcessingError):
    """Lançado quando o número da página solicitada é inválido ou fora dos limites."""

    def __init__(self, message: str, code: str = "INVALID_PAGE") -> None:
        super().__init__(message, code=code)


class PdfFileSizeError(PdfProcessingError):
    """Lançado quando o PDF excede os limites de tamanho estabelecidos por política."""

    def __init__(self, message: str, code: str = "FILE_TOO_LARGE") -> None:
        super().__init__(message, code=code)


class PdfRenderError(PdfProcessingError):
    """Lançado quando ocorre uma falha na rasterização de uma página ou região do PDF."""

    def __init__(self, message: str, code: str = "PDF_RENDER_ERROR") -> None:
        super().__init__(message, code=code)


class PdfRenderPixelLimitError(PdfRenderError):
    """Lançado quando a dimensão projetada para renderização excede o limite máximo de pixels permitido."""

    def __init__(
        self,
        message: str = "A dimensão projetada para renderização excede o limite máximo de pixels permitido.",
        code: str = "PIXEL_LIMIT_EXCEEDED",
    ) -> None:
        super().__init__(message, code=code)


class PdfInvalidBBoxError(PdfRenderError):
    """Lançado quando as coordenadas da região (bbox) são inválidas, degeneradas ou extrapolam a página."""

    def __init__(
        self,
        message: str = "As coordenadas da região (bbox) são inválidas ou extrapolam os limites da página.",
        code: str = "INVALID_BBOX",
    ) -> None:
        super().__init__(message, code=code)


# ==============================================================================
# Contratos de Dados de Inspeção e Classificação
# ==============================================================================

class PdfPageType(str, Enum):
    """Classificação do tipo de conteúdo predominante em uma página de PDF."""

    TEXTUAL = "textual"  # Conteúdo textual nativo suficiente, sem imagens que demandem OCR
    SCANNED = "scanned"  # Predominantemente rasterizada/digitalizada, sem texto nativo útil
    MIXED = "mixed"      # Combina texto nativo e conteúdo visual relevante com potencial necessidade de OCR


@dataclass(frozen=True)
class ImageRegion:
    """Região retangular ocupada por um bloco de imagem em uma página de PDF.

    Preserva coordenadas espaciais nativas do PDF para permitir renderização recortada (clip)
    e evitar reprocessamento OCR redundante de áreas puramente textuais.
    """

    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) em pontos PDF
    width: float
    height: float
    area_ratio: float  # Proporção da área da imagem em relação à área total da página (0.0 a 1.0)
    xref: Optional[int] = None
    image_index: int = 0


@dataclass(frozen=True)
class PdfPageInfo:
    """Metadados, conteúdo textual nativo e classificação de uma página individual de PDF."""

    page_number: int  # 1-indexed (1..N)
    page_type: PdfPageType  # "textual", "scanned", "mixed"
    native_text: str  # Texto extraído diretamente da camada de texto do PDF
    char_count: int  # Número de caracteres no texto nativo
    word_count: int  # Número de palavras no texto nativo
    image_count: int  # Número de blocos/referências de imagem detectados
    images_area_ratio: float  # Proporção da área da página coberta por imagens (0.0 a 1.0)
    image_regions: tuple[ImageRegion, ...]  # Lista de regiões de imagem identificadas
    page_width: float  # Largura em pontos PDF
    page_height: float  # Altura em pontos PDF
    is_valid: bool = True
    error_message: Optional[str] = None


@dataclass(frozen=True)
class PdfInspectionResult:
    """Resultado consolidado da inspeção, contagem e classificação de um documento PDF."""

    doc_type: MaterialSourceType  # MaterialSourceType.PDF, SCANNED_PDF ou MIXED_PDF
    total_pages: int
    textual_pages_count: int
    scanned_pages_count: int
    mixed_pages_count: int
    pages: tuple[PdfPageInfo, ...]
    total_bytes: int
    has_mixed_content: bool
    requires_visual_processing: bool  # True se houver páginas scanned ou mixed
    consolidated_native_text: str  # Concatenação normalizada do texto nativo de todas as páginas


# ==============================================================================
# Funções de Classificação e Inspeção
# ==============================================================================

def clip_bbox_to_page(rect: fitz.Rect, page_rect: fitz.Rect) -> Optional[fitz.Rect]:
    """Recorta um retângulo de imagem aos limites físicos visíveis da página.

    Útil durante a inspeção de PDFs reais diagramados com imagens com sangria (bleed),
    em que `page.get_image_rects(xref)` retorna coordenadas que ultrapassam a borda da página.

    Retorna None caso a região esteja totalmente fora da página ou possua dimensões degeneradas.
    """
    coords = (rect.x0, rect.y0, rect.x1, rect.y1, page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1)
    if any(math.isnan(float(v)) or math.isinf(float(v)) for v in coords):
        return None

    x0 = max(float(rect.x0), float(page_rect.x0))
    y0 = max(float(rect.y0), float(page_rect.y0))
    x1 = min(float(rect.x1), float(page_rect.x1))
    y1 = min(float(rect.y1), float(page_rect.y1))

    if x0 >= x1 or y0 >= y1:
        return None

    return fitz.Rect(x0, y0, x1, y1)


def _classify_page(
    char_count: int,
    images_area_ratio: float,
    has_relevant_images: bool,
) -> PdfPageType:
    """Classifica uma página individual com base na presença de texto nativo e conteúdo visual.

    Critérios Heurísticos (História 1.1.3 - Etapa 4.B1):
    1. TEXTUAL: Página com texto nativo e sem imagens que demandem OCR (pequenos ícones/logos
       decorativos abaixo do limiar de relevância não alteram a classificação). Páginas em branco
       (sem texto e sem imagem) também permanecem TEXTUAL.
    2. MIXED: Página que contenha texto nativo (curto ou longo) E imagem relevante que demande OCR
       (has_relevant_images=True ou cobertura >= MIXED_COVERAGE_THRESHOLD). Garante que o texto nativo
       nunca seja descartado ou suprimido quando houver imagens associadas.
    3. SCANNED: Página sem nenhum texto nativo (char_count == 0) mas com presença de imagens que
       demandem OCR (cobertura expressiva ou imagem relevante).
    """
    has_any_text = char_count > 0
    demands_visual_processing = has_relevant_images or images_area_ratio >= MIXED_COVERAGE_THRESHOLD

    # 1. Página sem texto nativo algum
    if not has_any_text:
        if demands_visual_processing:
            return PdfPageType.SCANNED
        return PdfPageType.TEXTUAL

    # 2. Página que contém texto nativo (curto ou longo) e imagem que demanda OCR
    if demands_visual_processing:
        return PdfPageType.MIXED

    # 3. Página textual sem imagens ou apenas com ícones decorativos irrelevantes
    return PdfPageType.TEXTUAL


def inspect_and_classify_pdf(
    pdf_bytes: bytes,
    *,
    enforce_size_limits: bool = True,
) -> PdfInspectionResult:
    """Abre, inspeciona e classifica um documento PDF a partir de bytes em memória.

    Operações executadas:
    1. Validação de tamanho absoluto (limite de 25 MB).
    2. Abertura segura em memória via PyMuPDF com garantia de fechamento (try...finally).
    3. Extração estruturada de texto nativo por página.
    4. Mapeamento de blocos e coordenadas (bbox) de todas as imagens embutidas.
    5. Classificação por página em 'textual', 'scanned' e 'mixed'.
    6. Consolidação do tipo de documento (MaterialSourceType.PDF, SCANNED_PDF ou MIXED_PDF).
    7. Validação de tamanho condicional: se o documento for 100% textual e exceder 10 MB, rejeita.

    Parâmetros:
        pdf_bytes: Conteúdo binário completo do PDF.
        enforce_size_limits: Se True, aplica a verificação estrita dos limites de 10 MB / 25 MB.

    Retorna:
        PdfInspectionResult: Metadados consolidados e detalhamento por página.

    Lança:
        PdfEmptyFileError: Se o arquivo estiver vazio (0 bytes).
        PdfFileSizeError: Se o tamanho exceder os limites permitidos.
        PdfCorruptedError: Se o arquivo estiver corrompido ou for inválido.
        PdfNoPagesError: Se o PDF não possuir páginas.
    """
    if not pdf_bytes:
        raise PdfEmptyFileError()

    total_bytes = len(pdf_bytes)

    # Verificação inicial do limite absoluto seguro de 25 MB
    if enforce_size_limits and total_bytes > MAX_OCR_FILE_SIZE_BYTES:
        mb = total_bytes / (1024 * 1024)
        max_mb = MAX_OCR_FILE_SIZE_BYTES / (1024 * 1024)
        raise PdfFileSizeError(
            f"O arquivo PDF enviado ({mb:.1f} MB) excede o limite máximo permitido de {max_mb:.0f} MB.",
            code="OCR_FILE_TOO_LARGE",
        )

    if not _HAS_FITZ or fitz is None:  # pragma: no cover
        raise PdfProcessingError(
            "A biblioteca PyMuPDF (fitz) não está disponível no ambiente.",
            code="LIBRARY_NOT_AVAILABLE",
        )

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        if "encrypted" in str(exc).lower() or "password" in str(exc).lower():
            raise PdfCorruptedError(
                "O arquivo PDF está protegido por senha ou criptografado e não pode ser processado.",
                code="ENCRYPTED_PDF",
            ) from exc
        raise PdfCorruptedError(
            f"Não foi possível abrir o documento PDF em memória: {exc}",
            code="CORRUPTED_PDF",
        ) from exc

    try:
        if getattr(doc, "is_encrypted", False):
            raise PdfCorruptedError(
                "O arquivo PDF está protegido por senha ou criptografado e não pode ser processado.",
                code="ENCRYPTED_PDF",
            )
        total_pages = len(doc)
        if total_pages == 0:
            raise PdfNoPagesError()

        pages_info: list[PdfPageInfo] = []
        full_text_parts: list[str] = []

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            try:
                page = doc[page_idx]
                page_rect = page.rect
                page_width = float(page_rect.width)
                page_height = float(page_rect.height)
                page_area = page_width * page_height if page_width > 0 and page_height > 0 else 1.0

                # 1. Extração de texto nativo
                raw_page_text = page.get_text() or ""
                normalized_text = normalize_extracted_text(raw_page_text)
                char_count = len(normalized_text)
                word_count = len(normalized_text.split()) if char_count > 0 else 0

                if normalized_text:
                    full_text_parts.append(normalized_text)

                # 2. Mapeamento de imagens com clipping seguro aos limites da página
                image_regions_list: list[ImageRegion] = []
                total_image_area = 0.0
                has_relevant_individual_image = False

                # Coleta imagens via get_images e obtém seus bboxes na página
                images_meta = page.get_images(full=True)
                img_idx_counter = 0

                for img_info in images_meta:
                    xref = img_info[0]
                    # Uma imagem com mesmo xref pode ser referenciada em múltiplos pontos da página
                    rects = page.get_image_rects(xref)
                    for r in rects:
                        clipped = clip_bbox_to_page(r, page_rect)
                        if clipped is None:
                            continue

                        w = float(clipped.width)
                        h = float(clipped.height)
                        img_area = w * h
                        area_ratio = min(1.0, max(0.0, img_area / page_area))
                        total_image_area += img_area

                        if area_ratio >= MIN_RELEVANT_IMAGE_AREA_RATIO:
                            has_relevant_individual_image = True

                        image_regions_list.append(
                            ImageRegion(
                                bbox=(
                                    float(clipped.x0),
                                    float(clipped.y0),
                                    float(clipped.x1),
                                    float(clipped.y1),
                                ),
                                width=w,
                                height=h,
                                area_ratio=round(area_ratio, 4),
                                xref=xref,
                                image_index=img_idx_counter,
                            )
                        )
                        img_idx_counter += 1

                image_regions_list.sort(key=lambda reg: (reg.bbox[1], reg.bbox[0]))
                total_coverage_ratio = min(1.0, max(0.0, total_image_area / page_area))

                # 3. Classificação heurística da página
                page_type = _classify_page(
                    char_count=char_count,
                    images_area_ratio=total_coverage_ratio,
                    has_relevant_images=has_relevant_individual_image,
                )

                pages_info.append(
                    PdfPageInfo(
                        page_number=page_num,
                        page_type=page_type,
                        native_text=normalized_text,
                        char_count=char_count,
                        word_count=word_count,
                        image_count=len(image_regions_list),
                        images_area_ratio=round(total_coverage_ratio, 4),
                        image_regions=tuple(image_regions_list),
                        page_width=page_width,
                        page_height=page_height,
                        is_valid=True,
                    )
                )

            except Exception as page_exc:
                # Tolerância a falhas parciais por página: registra erro sem derrubar o documento inteiro
                pages_info.append(
                    PdfPageInfo(
                        page_number=page_num,
                        page_type=PdfPageType.SCANNED,  # Fallback seguro para requerer inspeção
                        native_text="",
                        char_count=0,
                        word_count=0,
                        image_count=0,
                        images_area_ratio=0.0,
                        image_regions=(),
                        page_width=0.0,
                        page_height=0.0,
                        is_valid=False,
                        error_message=f"Erro ao inspecionar página {page_num}: {page_exc}",
                    )
                )

    finally:
        doc.close()

    # 4. Consolidação do Tipo de Documento
    textual_count = sum(1 for p in pages_info if p.page_type == PdfPageType.TEXTUAL)
    scanned_count = sum(1 for p in pages_info if p.page_type == PdfPageType.SCANNED)
    mixed_count = sum(1 for p in pages_info if p.page_type == PdfPageType.MIXED)

    if mixed_count > 0 or (textual_count > 0 and scanned_count > 0):
        consolidated_doc_type = MaterialSourceType.MIXED_PDF
    elif scanned_count == len(pages_info):
        consolidated_doc_type = MaterialSourceType.SCANNED_PDF
    else:
        consolidated_doc_type = MaterialSourceType.PDF

    # 5. Aplicação do limite estrito de 10 MB para PDFs puramente textuais
    if (
        enforce_size_limits
        and consolidated_doc_type == MaterialSourceType.PDF
        and total_bytes > MAX_FILE_SIZE_BYTES
    ):
        mb = total_bytes / (1024 * 1024)
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise PdfFileSizeError(
            f"O arquivo PDF classificado como puramente textual ({mb:.1f} MB) excede o limite "
            f"técnico seguro de {max_mb:.0f} MB para processamento de texto. "
            f"Documentos que exigem até 25 MB devem conter páginas digitalizadas ou mistas.",
            code="FILE_TOO_LARGE",
        )

    requires_visual = consolidated_doc_type in (
        MaterialSourceType.SCANNED_PDF,
        MaterialSourceType.MIXED_PDF,
    )

    return PdfInspectionResult(
        doc_type=consolidated_doc_type,
        total_pages=total_pages,
        textual_pages_count=textual_count,
        scanned_pages_count=scanned_count,
        mixed_pages_count=mixed_count,
        pages=tuple(pages_info),
        total_bytes=total_bytes,
        has_mixed_content=(consolidated_doc_type == MaterialSourceType.MIXED_PDF),
        requires_visual_processing=requires_visual,
        consolidated_native_text="\n\n".join(full_text_parts),
    )


# ==============================================================================
# Funções de Validação de Memória e Bounding Box (Etapa 4.B2)
# ==============================================================================

def validate_and_calculate_render_dimensions(
    rect: fitz.Rect,
    dpi: int,
    *,
    max_pixels: int = MAX_RENDER_PIXELS,
) -> tuple[int, int, int]:
    """Calcula e valida a dimensão projetada em pixels antes de rasterizar via PyMuPDF.

    Utiliza a escala real do PyMuPDF (fitz.Matrix(dpi / 72.0, dpi / 72.0)) e o arredondamento
    de coordenadas inteiras utilizado por get_pixmap(), garantindo que renderizações excessivamente
    grandes sejam rejeitadas antes de qualquer alocação na heap nativa C++.

    Diferenciação de memória:
    - O limite max_pixels (padrão 25.000.000 px) restringe o tamanho do raster descompactado
      (~75 MB em RGB a 24 bits ou ~100 MB em RGBA a 32 bits).
    - Não representa um teto rígido absoluto de RSS do processo, uma vez que buffers transitórios
      de codificação PNG/JPEG, estruturas em heap gerenciada (Pillow/BytesIO) e páginas retidas nas
      arenas de alocação C (malloc do sistema) coexistem durante o ciclo de processamento.

    Retorna:
        tuple[int, int, int]: (largura_px, altura_px, total_pixels)

    Lança:
        PdfRenderError: Se o DPI for inválido (<= 0, NaN, infinito, não numérico ou > MAX_RENDER_DPI)
            ou se max_pixels for inválido (<= 0, NaN, infinito, não numérico ou > MAX_SAFETY_CEILING_PIXELS).
        PdfRenderPixelLimitError: Se a quantidade de pixels projetada ultrapassar max_pixels.
    """
    if not isinstance(dpi, (int, float)) or isinstance(dpi, bool):
        raise PdfRenderError(f"Valor de DPI inválido para renderização: {dpi}", code="INVALID_DPI")

    try:
        if dpi <= 0 or dpi > MAX_RENDER_DPI:
            raise PdfRenderError(
                f"Valor de DPI fora dos limites seguros (1..{MAX_RENDER_DPI}): {dpi}",
                code="INVALID_DPI",
            )
        if math.isnan(dpi) or math.isinf(dpi):
            raise PdfRenderError(f"Valor de DPI inválido para renderização: {dpi}", code="INVALID_DPI")
    except OverflowError:
        raise PdfRenderError(f"Valor de DPI excessivamente grande (overflow): {dpi}", code="INVALID_DPI")

    if not isinstance(max_pixels, (int, float)) or isinstance(max_pixels, bool):
        raise PdfRenderError(
            f"Valor de max_pixels inválido para renderização: {max_pixels}",
            code="INVALID_MAX_PIXELS",
        )

    try:
        if max_pixels <= 0 or max_pixels > MAX_SAFETY_CEILING_PIXELS:
            raise PdfRenderError(
                f"Valor de max_pixels fora dos limites aceitáveis (1..{MAX_SAFETY_CEILING_PIXELS}): {max_pixels}",
                code="INVALID_MAX_PIXELS",
            )
        if math.isnan(max_pixels) or math.isinf(max_pixels):
            raise PdfRenderError(
                f"Valor de max_pixels inválido para renderização: {max_pixels}",
                code="INVALID_MAX_PIXELS",
            )
    except OverflowError:
        raise PdfRenderError(
            f"Valor de max_pixels excessivamente grande (overflow): {max_pixels}",
            code="INVALID_MAX_PIXELS",
        )

    zoom = float(dpi) / 72.0
    mat = fitz.Matrix(zoom, zoom)
    transformed_rect = (rect * mat).round()
    width_px = int(transformed_rect.width)
    height_px = int(transformed_rect.height)
    total_pixels = width_px * height_px

    if total_pixels > max_pixels:
        raise PdfRenderPixelLimitError(
            f"A renderização projetada ({width_px}x{height_px} = {total_pixels:,} pixels a {dpi} DPI) "
            f"excede o limite de segurança de {max_pixels:,} pixels (MAX_RENDER_PIXELS).",
            code="PIXEL_LIMIT_EXCEEDED",
        )

    return width_px, height_px, total_pixels


def validate_pdf_region_bbox(
    bbox: Any,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    """Valida rigorosamente as coordenadas de um bounding box antes da rasterização regional.

    Garantias de segurança e validação geométrica:
    - Bbox deve ser sequência de exatamente 4 coordenadas numéricas (x0, y0, x1, y1);
    - Todas as coordenadas devem ser finitas (rejeita NaN e inf);
    - x0 < x1 e y0 < y1 (largura e altura estritamente positivas);
    - Retângulo deve estar contido dentro dos limites físicos de page_rect;
    - Não aplica clamp silencioso nem normalização arbitrária: regiões que extrapolam os limites
      físicos são rejeitadas com exceção explícita (INVALID_BBOX);
    - Tolerância geométrica (tol = 1e-4 pt ≈ 35 nm): necessária exclusivamente para absorver
      resíduos de precisão de ponto flutuante IEEE-754 originados das transformações de matriz
      (CTM) do PyMuPDF ao extrair image_rects de figuras que tocam as bordas da página
      (ex.: 595.0000000000001 pt). A tolerância de 1e-4 pontos corresponde a ~0.0002 pixels a
      150 DPI, sendo fisicamente incapaz de aceitar regiões reais fora da página e completamente
      absorvida pelo arredondamento da grade inteira de pixels.

    Retorna:
        fitz.Rect: Retângulo validado.

    Lança:
        PdfInvalidBBoxError: Em caso de coordenadas inválidas, degeneradas ou fora da página.
    """
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise PdfInvalidBBoxError(
            f"O parâmetro bbox deve ser uma sequência de 4 coordenadas (x0, y0, x1, y1), recebido: {type(bbox).__name__}.",
            code="INVALID_BBOX",
        )

    for i, val in enumerate(bbox):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise PdfInvalidBBoxError(
                f"Coordenada bbox[{i}] inválida: esperado valor numérico finito, recebido {type(val).__name__}.",
                code="INVALID_BBOX",
            )
        if math.isnan(val) or math.isinf(val):
            raise PdfInvalidBBoxError(
                f"Coordenada bbox[{i}] inválida: valor não pode ser NaN ou infinito.",
                code="INVALID_BBOX",
            )

    x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

    if x0 >= x1:
        raise PdfInvalidBBoxError(
            f"Bounding box inválida: x0 ({x0}) deve ser estritamente menor que x1 ({x1}) com largura > 0.",
            code="INVALID_BBOX",
        )
    if y0 >= y1:
        raise PdfInvalidBBoxError(
            f"Bounding box inválida: y0 ({y0}) deve ser estritamente menor que y1 ({y1}) com altura > 0.",
            code="INVALID_BBOX",
        )

    # Verifica se está integralmente dentro dos limites da página.
    # A tolerância de 1e-4 pt (~35 nm) é adotada estritamente para absorver resíduos
    # de arredondamento de matriz CTM em float IEEE-754 (ex.: 595.0000000000001).
    tol = 1e-4
    if (
        x0 < (page_rect.x0 - tol)
        or y0 < (page_rect.y0 - tol)
        or x1 > (page_rect.x1 + tol)
        or y1 > (page_rect.y1 + tol)
    ):
        raise PdfInvalidBBoxError(
            f"Bounding box ({x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}) extrapola os limites físicos da página "
            f"({page_rect.x0:.1f}, {page_rect.y0:.1f}, {page_rect.x1:.1f}, {page_rect.y1:.1f}).",
            code="INVALID_BBOX",
        )

    return fitz.Rect(x0, y0, x1, y1)


# ==============================================================================
# Funções de Renderização Sequencial em Memória
# ==============================================================================

def render_pdf_page_image(
    pdf_bytes: bytes,
    page_number: int,
    *,
    dpi: int = DEFAULT_RENDER_DPI,
    as_pil: bool = True,
) -> Any:
    """Renderiza uma página inteira de PDF em imagem de alta fidelidade em memória.

    Garantias de segurança e ciclo de vida de memória:
    - O documento PyMuPDF é aberto e fechado estritamente no escopo da chamada (try...finally).
    - Validação prévia contra MAX_RENDER_PIXELS antes de qualquer invocação a get_pixmap().
    - Diferenciação de memória:
      1. Raster puro: O limite de 25M pixels restringe o bitmap nativo C a ~75 MB (RGB) ou ~100 MB (RGBA);
      2. Buffers transitórios: A codificação para PNG aloca temporariamente buffer comprimido intermediário;
      3. Heap Python: O retorno como PIL.Image.Image retém buffer em heap gerenciada pelo runtime;
      4. Arena nativa C: O pixmap C++ é desalocado imediatamente após tobytes(), liberando a memória
         para a arena de alocação do processo (malloc/mmap), cuja devolução física ao sistema operacional
         segue as heurísticas do gerenciador de memória do SO.

    Parâmetros:
        pdf_bytes: Bytes do documento PDF.
        page_number: Número da página a renderizar (1-indexed, de 1 a N).
        dpi: Resolução de renderização em pontos por polegada (padrão 150 DPI).
        as_pil: Se True, retorna PIL.Image.Image; se False, retorna bytes codificados em PNG.

    Retorna:
        PIL.Image.Image ou bytes da imagem PNG renderizada.

    Lança:
        PdfInvalidPageError: Se page_number < 1 ou maior que o total de páginas.
        PdfRenderPixelLimitError: Se a resolução projetada ultrapassar MAX_RENDER_PIXELS.
        PdfRenderError: Se ocorrer erro na rasterização.
    """
    if not pdf_bytes:
        raise PdfEmptyFileError()

    if not _HAS_FITZ or fitz is None:  # pragma: no cover
        raise PdfProcessingError("PyMuPDF não está disponível.", code="LIBRARY_NOT_AVAILABLE")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfCorruptedError(f"Falha ao abrir PDF para renderização: {exc}") from exc

    pixmap = None
    try:
        total_pages = len(doc)
        if total_pages == 0:
            raise PdfNoPagesError()

        if page_number < 1 or page_number > total_pages:
            raise PdfInvalidPageError(
                f"Número de página inválido: {page_number}. O documento contém {total_pages} página(s)."
            )

        try:
            page = doc[page_number - 1]
            validate_and_calculate_render_dimensions(page.rect, dpi)
            pixmap = page.get_pixmap(dpi=dpi)
            png_bytes = pixmap.tobytes("png")
        except PdfProcessingError:
            raise
        except Exception as exc:
            raise PdfRenderError(f"Falha ao rasterizar página {page_number}: {exc}") from exc

    finally:
        pixmap = None
        doc.close()

    if as_pil:
        if not _HAS_PIL or Image is None:  # pragma: no cover
            raise PdfProcessingError("Pillow (PIL) não está disponível.", code="LIBRARY_NOT_AVAILABLE")
        img = Image.open(io.BytesIO(png_bytes))
        img.load()  # Carrega em memória antes de fechar o buffer
        return img

    return png_bytes


def render_pdf_region_image(
    pdf_bytes: bytes,
    page_number: int,
    bbox: tuple[float, float, float, float],
    *,
    dpi: int = DEFAULT_RENDER_DPI,
    as_pil: bool = True,
) -> Any:
    """Renderiza exclusivamente uma região retangular delimitada (clip) de uma página de PDF.

    Essencial para PDFs mistos: renderiza apenas a área de uma imagem/questão digitalizada,
    impedindo que o OCR retranscreva todo o texto nativo já existente na página.

    Garantias de segurança (Etapa 4.B2):
    - Validação geométrica estrita do bbox antes da chamada nativa (sem clamp silencioso);
    - Validação prévia de pixels contra MAX_RENDER_PIXELS antes de get_pixmap().

    Parâmetros:
        pdf_bytes: Bytes do PDF.
        page_number: Página onde a região se localiza (1-indexed).
        bbox: Coordenadas (x0, y0, x1, y1) em pontos PDF.
        dpi: Resolução de renderização (padrão 150 DPI).
        as_pil: Se True retorna PIL.Image.Image; caso contrário, bytes PNG.
    """
    if not pdf_bytes:
        raise PdfEmptyFileError()

    if not _HAS_FITZ or fitz is None:  # pragma: no cover
        raise PdfProcessingError("PyMuPDF não está disponível.", code="LIBRARY_NOT_AVAILABLE")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfCorruptedError(f"Falha ao abrir PDF para renderização de região: {exc}") from exc

    pixmap = None
    try:
        total_pages = len(doc)
        if total_pages == 0:
            raise PdfNoPagesError()

        if page_number < 1 or page_number > total_pages:
            raise PdfInvalidPageError(
                f"Página {page_number} fora do intervalo (total de páginas: {total_pages})."
            )

        try:
            page = doc[page_number - 1]
            clip_rect = validate_pdf_region_bbox(bbox, page.rect)
            validate_and_calculate_render_dimensions(clip_rect, dpi)
            pixmap = page.get_pixmap(dpi=dpi, clip=clip_rect)
            png_bytes = pixmap.tobytes("png")
        except PdfProcessingError:
            raise
        except Exception as exc:
            raise PdfRenderError(f"Falha ao rasterizar região {bbox} na página {page_number}: {exc}") from exc

    finally:
        pixmap = None
        doc.close()

    if as_pil:
        if not _HAS_PIL or Image is None:  # pragma: no cover
            raise PdfProcessingError("Pillow (PIL) não está disponível.", code="LIBRARY_NOT_AVAILABLE")
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
        return img

    return png_bytes


def iter_render_pdf_pages(
    pdf_bytes: bytes,
    *,
    dpi: int = DEFAULT_RENDER_DPI,
    as_pil: bool = True,
) -> Generator[tuple[int, Any], None, None]:
    """Gerador sequencial para renderizar páginas uma a uma sob demanda.

    Garante que nunca haja mais de uma página rasterizada simultaneamente em memória:
    cada imagem é liberada assim que o consumidor conclui sua iteração.

    Garantia de segurança (Etapa 4.B2):
    - Validação de pixels por página contra MAX_RENDER_PIXELS antes de invocar get_pixmap().
    """
    if not pdf_bytes:
        raise PdfEmptyFileError()

    if not _HAS_FITZ or fitz is None:  # pragma: no cover
        raise PdfProcessingError("PyMuPDF não está disponível.", code="LIBRARY_NOT_AVAILABLE")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfCorruptedError(f"Falha ao abrir PDF: {exc}") from exc

    try:
        total = len(doc)
        for page_idx in range(total):
            page_num = page_idx + 1
            page = doc[page_idx]
            validate_and_calculate_render_dimensions(page.rect, dpi)
            pixmap = page.get_pixmap(dpi=dpi)
            png_bytes = pixmap.tobytes("png")
            pixmap = None  # Libera imediatamente a memória nativa C++

            if as_pil:
                img = Image.open(io.BytesIO(png_bytes))
                img.load()
                yield (page_num, img)
            else:
                yield (page_num, png_bytes)
    finally:
        doc.close()
