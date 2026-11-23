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

def _classify_page(
    char_count: int,
    images_area_ratio: float,
    has_relevant_images: bool,
) -> PdfPageType:
    """Classifica uma página individual com base em múltiplos sinais objetivos.

    Critérios Heurísticos:
    1. SCANNED: Pouquíssimo ou nenhum texto nativo (< 50 caracteres) E cobertura de imagem expressiva (>= 60%).
    2. MIXED: Texto nativo relevante (>= 50 caracteres) E presença de imagens expressivas (cobertura >= 10% ou imagem relevante).
    3. TEXTUAL: Texto nativo suficiente e ausência de imagens de grande porte que sugiram questões digitalizadas anexas.
       Pequenos ícones, logos de cabeçalho ou separadores gráficos (< 5% de área) não tornam a página mista.
    """
    has_sufficient_text = char_count >= MIN_TEXT_CHARS_THRESHOLD

    if not has_sufficient_text and images_area_ratio >= SCANNED_COVERAGE_THRESHOLD:
        return PdfPageType.SCANNED

    if has_sufficient_text and (images_area_ratio >= MIXED_COVERAGE_THRESHOLD or has_relevant_images):
        return PdfPageType.MIXED

    # Caso em que há pouco texto e pouca imagem (ex: página de rosto esparsa ou em branco)
    if not has_sufficient_text and images_area_ratio > 0.20:
        return PdfPageType.SCANNED

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
        raise PdfCorruptedError(
            f"Não foi possível abrir o documento PDF em memória: {exc}",
            code="CORRUPTED_PDF",
        ) from exc

    try:
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

                # 2. Mapeamento de imagens e cálculo de área
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
                        w = float(r.width)
                        h = float(r.height)
                        img_area = w * h
                        area_ratio = min(1.0, max(0.0, img_area / page_area))
                        total_image_area += img_area

                        if area_ratio >= MIN_RELEVANT_IMAGE_AREA_RATIO:
                            has_relevant_individual_image = True

                        image_regions_list.append(
                            ImageRegion(
                                bbox=(float(r.x0), float(r.y0), float(r.x1), float(r.y1)),
                                width=w,
                                height=h,
                                area_ratio=round(area_ratio, 4),
                                xref=xref,
                                image_index=img_idx_counter,
                            )
                        )
                        img_idx_counter += 1

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

    Garantias de segurança e memória:
    - O documento PyMuPDF é aberto e fechado estritamente no escopo da chamada (try...finally).
    - O pixmap intermediário do C/C++ é convertido diretamente para bytes PNG ou PIL.Image.Image.
    - O pixmap é explicitamente desalocado logo após a extração dos bytes.

    Parâmetros:
        pdf_bytes: Bytes do documento PDF.
        page_number: Número da página a renderizar (1-indexed, de 1 a N).
        dpi: Resolução de renderização em pontos por polegada (padrão 150 DPI).
        as_pil: Se True, retorna PIL.Image.Image; se False, retorna bytes codificados em PNG.

    Retorna:
        PIL.Image.Image ou bytes da imagem PNG renderizada.

    Lança:
        PdfInvalidPageError: Se page_number < 1 ou maior que o total de páginas.
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
            pixmap = page.get_pixmap(dpi=dpi)
            png_bytes = pixmap.tobytes("png")
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
            clip_rect = fitz.Rect(*bbox)
            pixmap = page.get_pixmap(dpi=dpi, clip=clip_rect)
            png_bytes = pixmap.tobytes("png")
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
