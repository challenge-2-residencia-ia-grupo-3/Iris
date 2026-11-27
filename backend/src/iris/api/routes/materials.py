"""Rotas e serviços de processamento de materiais didáticos (Histórias 1.1.1 e 1.1.3).

Endpoints:
- POST /api/v1/materials/text: entrada direta via texto digitado/colado pelo docente.
- POST /api/v1/materials/upload: upload de arquivos .txt, .pdf, .docx, .png, .jpg e .jpeg (multipart/form-data).
"""
from __future__ import annotations

import asyncio
import os
import weakref
from pathlib import Path
from typing import Any, Final

try:
    from starlette.concurrency import run_in_threadpool as _run_in_threadpool
except ImportError:  # pragma: no cover
    async def _run_in_threadpool(func: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

from iris.parsers.document_extractor import (
    DocumentParsingError,
    UnsupportedFileFormatError,
    extract_text_from_file,
)
from iris.parsers.image_analyzer import (
    CorruptedImageError,
    EmptyImageError,
    ImageAnalysisError,
    ImageTooLargeError,
    InvalidImageDimensionsError,
    UnsupportedImageFormatError,
    analyze_page_image,
    consolidate_visual_report,
)
from iris.parsers.ocr_extractor import (
    OcrDependencyError,
    OcrEngineNotFoundError,
    OcrError,
    OcrLanguageError,
    OcrTimeoutError,
    extract_text_from_page_image,
)
from iris.parsers.pdf_processor import (
    DEFAULT_RENDER_DPI,
    PdfCorruptedError,
    PdfEmptyFileError,
    PdfFileSizeError,
    PdfInvalidBBoxError,
    PdfNoPagesError,
    PdfPageType,
    PdfProcessingError,
    PdfRenderError,
    PdfRenderPixelLimitError,
    inspect_and_classify_pdf,
    render_pdf_page_image,
    render_pdf_region_image,
)
from iris.parsers.prose_organizer import organize_prose_structure
from iris.parsers.structural_decomposer import decompose_material
from iris.schemas.materials import (
    MaterialMetadata,
    MaterialResponse,
    MaterialSourceType,
    MaterialStructure,
    MaterialTextInput,
    MaterialValidationError,
    OcrMaterialResponse,
    PageVisualAnalysis,
    ProseStructure,
    VisualAnalysisReport,
    create_sanitized_raw_content,
    validate_file_size_limit,
    validate_material_content,
    validate_ocr_file_size_limit,
)
from iris.security.operational_logger import sentinel_context
from iris.security.pii_scrubber import sanitize_pii

SUPPORTED_UPLOAD_EXTENSIONS: Final[set[str]] = {
    ".txt",
    ".pdf",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
}
IMAGE_EXTENSIONS: Final[set[str]] = {".png", ".jpg", ".jpeg"}
DEFAULT_MAX_CONCURRENT_OCR: Final[int] = 2
_OCR_SEMAPHORES: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


class OcrServiceUnavailableError(DocumentParsingError):
    """Lançado quando o serviço local de OCR (Tesseract/idioma) está indisponível (HTTP 503)."""


def _get_max_concurrent_ocr() -> int:
    """Obtém o limite seguro de execuções simultâneas de OCR por worker via ambiente."""
    raw = os.environ.get("IRIS_MAX_CONCURRENT_OCR", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed >= 1:
                return parsed
        except ValueError:
            pass
    return DEFAULT_MAX_CONCURRENT_OCR


def _get_ocr_semaphore() -> asyncio.Semaphore:
    """Retorna o semáforo assíncrono vinculado ao event loop ativo do worker atual."""
    loop = asyncio.get_running_loop()
    sem = _OCR_SEMAPHORES.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(_get_max_concurrent_ocr())
        _OCR_SEMAPHORES[loop] = sem
    return sem



def process_material_text_service(raw_text: str) -> MaterialResponse:
    """Executa o pipeline completo em memória para texto direto:

    1. Sanitização preventiva de PII (Zero-Retention / RNF-02).
    2. Validação de regras de negócio (mínimo 50 caracteres e janela de contexto da IA / RF-01).
    3. Construção do envelope de resposta padronizado.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise MaterialValidationError(
            message="O texto fornecido está vazio ou contém apenas espaços em branco.",
            code="EMPTY_TEXT",
            field="text",
        )

    with sentinel_context(raw_text):
        # 1. Sanitizar PII (irreversível, sem dicionário de retenção)
        sanitized_text, pii_count = sanitize_pii(raw_text)

        # 2. Validar limites de tamanho e janela de contexto
        char_count, word_count = validate_material_content(sanitized_text)

    # 3. Retornar resposta
    return MaterialResponse(
        status="success",
        message="Material textual processado e sanitizado com sucesso.",
        raw_text=sanitized_text,
        metadata=MaterialMetadata(
            source_type=MaterialSourceType.TEXT.value,
            char_count=char_count,
            word_count=word_count,
            sanitized=pii_count > 0,
            pii_removed_count=pii_count,
            filename=None,
        ),
    )


def _process_textual_doc(filename: str, content: bytes) -> MaterialResponse:
    """Processa documentos puramente textuais (.txt, .docx) com limite de 10 MB."""
    # 1. Validar limite de tamanho binário do arquivo (10 MB)
    validate_file_size_limit(content)

    # 2. Extração em memória
    extracted_text, detected_format = extract_text_from_file(filename, content)

    with sentinel_context(extracted_text):
        # 3. Sanitizar PII (irreversível, Zero-Retention)
        sanitized_text, pii_count = sanitize_pii(extracted_text)

        # 4. Validar limites de negócio
        char_count, word_count = validate_material_content(sanitized_text)

    # 5. Retornar resposta
    return MaterialResponse(
        status="success",
        message=f"Arquivo '{filename}' extraído e sanitizado com sucesso.",
        raw_text=sanitized_text,
        metadata=MaterialMetadata(
            source_type=detected_format,
            char_count=char_count,
            word_count=word_count,
            sanitized=pii_count > 0,
            pii_removed_count=pii_count,
            filename=filename,
        ),
    )


def _process_image_upload(filename: str, content: bytes, suffix: str) -> OcrMaterialResponse:
    """Processa upload de imagem (.png, .jpg, .jpeg) com limite de 25 MB, análise visual e OCR."""
    # 1. Validar limite de 25 MB
    validate_ocr_file_size_limit(content)

    if not content:
        raise DocumentParsingError("O arquivo de imagem está vazio (0 bytes).", code="EMPTY_FILE")

    source_type_map = {
        ".png": MaterialSourceType.PNG,
        ".jpg": MaterialSourceType.JPG,
        ".jpeg": MaterialSourceType.JPEG,
    }
    source_type = source_type_map.get(suffix, MaterialSourceType.PNG)

    # 2. Executar análise visual da imagem
    try:
        page_analysis = analyze_page_image(content, page_number=1, page_type="image")
    except EmptyImageError as err:
        raise DocumentParsingError(err.message, code="EMPTY_FILE") from err
    except ImageTooLargeError as err:
        raise MaterialValidationError(err.message, code="OCR_FILE_TOO_LARGE", field="file") from err
    except (CorruptedImageError, InvalidImageDimensionsError, UnsupportedImageFormatError) as err:
        raise DocumentParsingError(f"Arquivo de imagem inválido ou corrompido: {err.message}", code=err.code) from err
    except Exception as err:
        raise DocumentParsingError(f"Erro na análise visual da imagem: {err}", code="IMAGE_ANALYSIS_ERROR") from err

    # 3. Executar OCR em português
    try:
        ocr_result = extract_text_from_page_image(content, page_number=1)
    except OcrTimeoutError as err:
        raise DocumentParsingError(f"Tempo limite excedido durante o processamento OCR: {err.message}", code="OCR_TIMEOUT") from err
    except (OcrDependencyError, OcrEngineNotFoundError, OcrLanguageError) as err:
        raise OcrServiceUnavailableError(
            f"Serviço de OCR indisponível neste ambiente: {err.message}",
            code=err.code,
        ) from err
    except OcrError as err:
        raise DocumentParsingError(f"Falha no mecanismo de OCR: {err.message}", code=err.code) from err
    except Exception as err:
        raise DocumentParsingError(f"Erro inesperado durante OCR: {err}", code="OCR_ERROR") from err

    # 4. Verificar se há texto reconhecido
    raw_extracted_text = ocr_result.raw_text.strip() if ocr_result.raw_text else ""
    if not ocr_result.has_text or not raw_extracted_text:
        raise DocumentParsingError(
            f"A imagem '{filename}' não contém texto legível reconhecido pelo OCR.",
            code="NO_READABLE_TEXT",
        )

    with sentinel_context(raw_extracted_text):
        # 5 e 6. Sanitização preventiva de PII e construção do contrato canônico RawContent
        _, raw_content = create_sanitized_raw_content(
            raw_text=raw_extracted_text,
            source_type=source_type,
            metadata={
                "filename": filename,
                "confidence": ocr_result.confidence,
                "low_confidence_word_count": ocr_result.low_confidence_word_count,
            },
        )

        # 7. Validar limites de negócio (mínimo 50 caracteres e janela de contexto da IA)
        char_count, word_count = validate_material_content(raw_content.text)

    pii_removed_count = int(raw_content.metadata.get("pii_removed_count", 0))

    # 8. Construir relatório consolidado de análise visual
    visual_report = consolidate_visual_report(
        [page_analysis],
        notes=page_analysis.rejection_reason,
    )

    # 9. Retornar resposta multimodal sanitizada (RNF-02 / Zero-PII)
    return OcrMaterialResponse(
        status="success",
        message=f"Arquivo '{filename}' processado via OCR e sanitizado com sucesso.",
        raw_text=raw_content.text,
        raw_content=raw_content,
        metadata=MaterialMetadata(
            source_type=source_type.value,
            char_count=char_count,
            word_count=word_count,
            sanitized=pii_removed_count > 0,
            pii_removed_count=pii_removed_count,
            filename=filename,
        ),
        visual_analysis=visual_report,
    )


def _normalize_text_spacing(text: str) -> str:
    """Normaliza quebras de linha e sequências de espaços múltiplos em espaço simples."""
    return " ".join(text.split()).strip().lower()


def _is_text_redundant(candidate: str, existing_texts: list[str]) -> bool:
    """Verifica se o texto extraído pelo OCR é estritamente redundante em relação ao texto nativo.

    Diretrizes de preservação de conteúdo pedagógico:
    1. Duplicação integral ou variação trivial de espaços/quebras de linha: redundante (True).
    2. Candidato que acrescenta qualquer informação complementar legítima: NÃO redundante (False).
    3. Compartilhamento parcial de palavras ou sobreposição de vocabulário: NÃO redundante (False).
    4. Textos curtos com palavras comuns (ex.: legendas, rótulos): NÃO redundante (False), exceto se
       for duplicação integral exata.
    5. Candidato com extensão significativa (>= 25 caracteres e >= 4 palavras) cuja sequência inteira
       esteja estritamente contida dentro de um dos textos nativos: redundante (True), pois
       todo o seu conteúdo já foi extraído nativamente pelo parser do documento.
    """
    cand_norm = _normalize_text_spacing(candidate)
    if not cand_norm:
        return True

    for ext in existing_texts:
        ext_norm = _normalize_text_spacing(ext)
        if not ext_norm:
            continue

        # 1. Duplicação integral (mesmo conteúdo, tolerando diferenças de espaço/quebra de linha)
        if cand_norm == ext_norm:
            return True

        # 2. Subsequência estritamente contida no texto nativo:
        # Só é considerada redundante se o candidato tiver extensão e quantidade de palavras significativas,
        # impedindo a remoção acidental de termos didáticos curtos e palavras compartilhadas.
        cand_words = cand_norm.split()
        if len(cand_norm) >= 25 and len(cand_words) >= 4:
            if cand_norm in ext_norm:
                return True

    return False


def _process_pdf_upload(filename: str, content: bytes) -> MaterialResponse | OcrMaterialResponse:
    """Processa upload de PDF (textual, escaneado ou misto) com classificação e despache automáticos."""
    # 1. Validação inicial de limite absoluto seguro de 25 MB
    validate_ocr_file_size_limit(content)

    if not content:
        raise DocumentParsingError("O arquivo PDF (.pdf) está vazio.", code="EMPTY_FILE")

    # 2. Inspecionar e classificar o documento PDF
    try:
        inspection = inspect_and_classify_pdf(content, enforce_size_limits=True)
    except PdfEmptyFileError as err:
        raise DocumentParsingError("O arquivo PDF (.pdf) está vazio.", code="EMPTY_FILE") from err
    except PdfFileSizeError as err:
        raise MaterialValidationError(err.message, code=err.code, field="file") from err
    except PdfCorruptedError as err:
        if err.code == "ENCRYPTED_PDF":
            raise DocumentParsingError(err.message, code="ENCRYPTED_PDF") from err
        raise DocumentParsingError(
            f"O arquivo PDF enviado está corrompido ou possui formato inválido: {err.message}",
            code=err.code,
        ) from err
    except PdfNoPagesError as err:
        raise DocumentParsingError("O documento PDF não contém páginas.", code="NO_PAGES") from err
    except PdfProcessingError as err:
        raise DocumentParsingError(f"Falha no processamento do PDF: {err.message}", code=err.code) from err
    except Exception as err:
        raise DocumentParsingError(f"Erro inesperado ao inspecionar PDF: {err}", code="PDF_PROCESSING_ERROR") from err

    # 3. Ramo A: PDF puramente TEXTUAL
    if inspection.doc_type == MaterialSourceType.PDF:
        validate_file_size_limit(content)

        raw_native = inspection.consolidated_native_text.strip()
        if not raw_native:
            raise DocumentParsingError(
                "O arquivo PDF não possui texto selecionável. Pode se tratar de uma imagem digitalizada.",
                code="NO_READABLE_TEXT",
            )

        with sentinel_context(raw_native):
            sanitized_text, pii_count = sanitize_pii(raw_native)
            char_count, word_count = validate_material_content(sanitized_text)

        return MaterialResponse(
            status="success",
            message=f"Arquivo '{filename}' extraído e sanitizado com sucesso.",
            raw_text=sanitized_text,
            metadata=MaterialMetadata(
                source_type=MaterialSourceType.PDF.value,
                char_count=char_count,
                word_count=word_count,
                sanitized=pii_count > 0,
                pii_removed_count=pii_count,
                filename=filename,
            ),
        )

    # 4. Ramo B e C: PDF ESCANEADO ou MISTO (com tolerância a falhas parciais e degradação graciosa)
    pages_analysis: list[PageVisualAnalysis] = []
    page_texts: list[str] = []
    failed_pages: list[int] = []
    unreadable_pages: list[int] = []
    ocr_unavailable_pages: list[int] = []
    processing_warnings: list[str] = []
    ocr_infra_error: OcrError | None = None
    first_timeout_error: tuple[int, str] | None = None
    first_page_error: tuple[str, str] | None = None

    for page_info in inspection.pages:
        page_num = page_info.page_number
        if not page_info.is_valid:
            failed_pages.append(page_num)
            msg = page_info.error_message or f"Não foi possível inspecionar a página {page_num}."
            processing_warnings.append(f"Página {page_num}: falha na leitura ({msg}).")
            if first_page_error is None:
                first_page_error = ("PDF_PROCESSING_ERROR", msg)
            continue

        page_img = None
        page_parts: list[str] = []
        if page_info.native_text and page_info.native_text.strip():
            page_parts.append(page_info.native_text.strip())

        try:
            # 4.1 Renderização da página completa para análise visual
            try:
                page_img = render_pdf_page_image(
                    content,
                    page_number=page_num,
                    dpi=DEFAULT_RENDER_DPI,
                    as_pil=True,
                )
                analysis = analyze_page_image(
                    page_img,
                    page_number=page_num,
                    page_type=page_info.page_type.value,
                )
                pages_analysis.append(analysis)
            except PdfRenderPixelLimitError as err:
                failed_pages.append(page_num)
                msg = f"Falha ao processar página {page_num} do documento: {err.message}"
                processing_warnings.append(f"Página {page_num}: não foi possível renderizar (limite de pixels excedido).")
                if first_page_error is None:
                    first_page_error = ("PIXEL_LIMIT_EXCEEDED", msg)
                if page_parts:
                    page_texts.append("\n\n".join(page_parts))
                continue
            except PdfRenderError as err:
                failed_pages.append(page_num)
                msg = f"Falha ao renderizar página {page_num} do documento: {err.message}"
                processing_warnings.append(f"Página {page_num}: falha ao renderizar página para análise visual/OCR.")
                if first_page_error is None:
                    first_page_error = ("PDF_RENDER_ERROR", msg)
                if page_parts:
                    page_texts.append("\n\n".join(page_parts))
                continue
            except (ImageAnalysisError, Exception) as err:
                failed_pages.append(page_num)
                msg = f"Falha ao processar página {page_num} do documento: {err}"
                processing_warnings.append(f"Página {page_num}: falha na análise visual ({err}).")
                if first_page_error is None:
                    first_page_error = ("IMAGE_ANALYSIS_ERROR", msg)
                if page_parts:
                    page_texts.append("\n\n".join(page_parts))
                continue

            # 4.2 Extração de texto via OCR conforme a classificação específica da página
            if page_info.page_type == PdfPageType.SCANNED:
                try:
                    ocr_res = extract_text_from_page_image(page_img, page_number=page_num)
                    if ocr_res.has_text and ocr_res.raw_text.strip():
                        cand_text = ocr_res.raw_text.strip()
                        if not _is_text_redundant(cand_text, page_parts):
                            page_parts.append(cand_text)
                    else:
                        unreadable_pages.append(page_num)
                        processing_warnings.append(
                            f"Página {page_num}: nenhum texto legível foi reconhecido pelo OCR nesta página digitalizada."
                        )
                except (OcrDependencyError, OcrEngineNotFoundError, OcrLanguageError) as err:
                    ocr_infra_error = ocr_infra_error or err
                    ocr_unavailable_pages.append(page_num)
                    processing_warnings.append(
                        f"Página {page_num}: extração OCR não realizada porque o serviço de OCR não está disponível ({err.message})."
                    )
                except OcrTimeoutError as err:
                    failed_pages.append(page_num)
                    if first_timeout_error is None:
                        first_timeout_error = (page_num, err.message)
                    processing_warnings.append(
                        f"Página {page_num}: tempo limite de OCR excedido ({err.message})."
                    )
                except OcrError as err:
                    failed_pages.append(page_num)
                    if first_page_error is None:
                        first_page_error = (err.code, f"Falha de OCR na página {page_num}: {err.message}")
                    processing_warnings.append(f"Página {page_num}: falha de OCR ({err.message}).")
                except Exception as err:
                    failed_pages.append(page_num)
                    if first_page_error is None:
                        first_page_error = ("OCR_ERROR", f"Erro inesperado no OCR da página {page_num}: {err}")
                    processing_warnings.append(f"Página {page_num}: erro inesperado no OCR ({err}).")

            elif page_info.page_type == PdfPageType.MIXED:
                # Página mista: preserva sempre o texto nativo e aplica OCR nas regiões de imagem
                for idx, region in enumerate(page_info.image_regions, start=1):
                    region_img = None
                    try:
                        region_img = render_pdf_region_image(
                            content,
                            page_number=page_num,
                            bbox=region.bbox,
                            dpi=DEFAULT_RENDER_DPI,
                            as_pil=True,
                        )
                    except (PdfRenderPixelLimitError, PdfRenderError, PdfInvalidBBoxError, Exception) as err:
                        if page_num not in failed_pages:
                            failed_pages.append(page_num)
                        err_code = getattr(err, "code", "PDF_RENDER_ERROR")
                        if first_page_error is None:
                            first_page_error = (
                                err_code,
                                f"Falha ao renderizar região visual {idx} na página {page_num}: {err}",
                            )
                        processing_warnings.append(
                            f"Página {page_num}: falha ao recortar região visual {idx} ({err}); texto nativo preservado."
                        )
                        continue

                    try:
                        reg_ocr = extract_text_from_page_image(region_img, page_number=page_num)
                        if reg_ocr.has_text and reg_ocr.raw_text.strip():
                            cand_text = reg_ocr.raw_text.strip()
                            if not _is_text_redundant(cand_text, page_parts):
                                page_parts.append(cand_text)
                    except (OcrDependencyError, OcrEngineNotFoundError, OcrLanguageError) as err:
                        ocr_infra_error = ocr_infra_error or err
                        if page_num not in ocr_unavailable_pages:
                            ocr_unavailable_pages.append(page_num)
                        processing_warnings.append(
                            f"Página {page_num}: texto nativo extraído, mas a extração de texto das imagens (OCR) "
                            "não foi realizada porque o serviço de OCR não está disponível neste ambiente."
                        )
                        break
                    except OcrTimeoutError as err:
                        if page_num not in failed_pages:
                            failed_pages.append(page_num)
                        if first_timeout_error is None:
                            first_timeout_error = (page_num, err.message)
                        processing_warnings.append(
                            f"Página {page_num}: tempo limite de OCR excedido na imagem {idx}; texto nativo preservado."
                        )
                    except (OcrError, Exception) as err:
                        if page_num not in failed_pages:
                            failed_pages.append(page_num)
                        err_code = getattr(err, "code", "OCR_ERROR")
                        if first_page_error is None:
                            first_page_error = (
                                err_code,
                                f"Falha no OCR da região {idx} na página {page_num}: {err}",
                            )
                        processing_warnings.append(
                            f"Página {page_num}: falha no OCR da imagem {idx} ({err}); texto nativo preservado."
                        )
                    finally:
                        if region_img is not None:
                            try:
                                region_img.close()
                            except Exception:
                                pass
                            region_img = None

            if page_parts:
                page_texts.append("\n\n".join(page_parts))
        finally:
            if page_img is not None:
                try:
                    page_img.close()
                except Exception:
                    pass
                page_img = None

    # 4.3 Consolidação mantendo estritamente a ordem das páginas (1..N)
    full_raw_text = "\n\n".join(page_texts).strip()
    if not full_raw_text:
        if ocr_infra_error is not None:
            raise OcrServiceUnavailableError(
                f"Serviço de OCR indisponível neste ambiente: {ocr_infra_error.message}",
                code=ocr_infra_error.code,
            )
        if first_timeout_error is not None:
            pg, msg = first_timeout_error
            raise DocumentParsingError(
                f"Tempo limite de OCR excedido na página {pg}: {msg}",
                code="OCR_TIMEOUT",
            )
        if first_page_error is not None:
            err_code, msg = first_page_error
            raise DocumentParsingError(msg, code=err_code)
        doc_label = "digitalizado" if inspection.doc_type == MaterialSourceType.SCANNED_PDF else "misto"
        raise DocumentParsingError(
            f"O documento PDF {doc_label} não contém texto legível reconhecido pelo OCR.",
            code="NO_READABLE_TEXT",
        )

    failed_pages = list(dict.fromkeys(failed_pages))
    unreadable_pages = list(dict.fromkeys(unreadable_pages))
    ocr_unavailable_pages = list(dict.fromkeys(ocr_unavailable_pages))
    affected_pages = sorted(set(failed_pages + unreadable_pages + ocr_unavailable_pages))

    with sentinel_context(full_raw_text):
        # 4.4 Sanitização preventiva de PII e construção do contrato unificado RawContent
        _, raw_content = create_sanitized_raw_content(
            raw_text=full_raw_text,
            source_type=inspection.doc_type,
            metadata={
                "filename": filename,
                "total_pages": inspection.total_pages,
                "scanned_pages": inspection.scanned_pages_count,
                "mixed_pages": inspection.mixed_pages_count,
                "textual_pages": inspection.textual_pages_count,
                "partial_extraction": bool(affected_pages),
                "failed_pages": failed_pages,
                "unreadable_pages": unreadable_pages,
                "ocr_unavailable_pages": ocr_unavailable_pages,
            },
        )

        # 4.5 Validação dos limites de negócio
        char_count, word_count = validate_material_content(raw_content.text)

    pii_removed_count = int(raw_content.metadata.get("pii_removed_count", 0))

    # 4.6 Construção do relatório consolidado de análise visual + avisos de páginas afetadas
    rejection_notes = [p.rejection_reason for p in pages_analysis if p.rejection_reason]
    combined_notes = list(dict.fromkeys([*rejection_notes, *processing_warnings]))
    notes_str = "; ".join(combined_notes) if combined_notes else None
    visual_report = consolidate_visual_report(pages_analysis, notes=notes_str)

    if affected_pages:
        pages_label = ", ".join(str(p) for p in affected_pages)
        response_message = (
            f"Arquivo '{filename}' processado parcialmente com avisos nas páginas {pages_label}. "
            "Confira as observações de análise visual antes de avançar."
        )
    else:
        response_message = f"Arquivo '{filename}' processado via OCR e sanitizado com sucesso."

    # 4.7 Retorno do contrato multimodal sanitizado (RNF-02 / Zero-PII)
    return OcrMaterialResponse(
        status="success",
        message=response_message,
        raw_text=raw_content.text,
        raw_content=raw_content,
        metadata=MaterialMetadata(
            source_type=inspection.doc_type.value,
            char_count=char_count,
            word_count=word_count,
            sanitized=pii_removed_count > 0,
            pii_removed_count=pii_removed_count,
            filename=filename,
        ),
        visual_analysis=visual_report,
    )


def process_material_file_service(filename: str, content: bytes) -> MaterialResponse | OcrMaterialResponse:
    """Executa o pipeline completo para upload de documentos e imagens (Histórias 1.1.1 e 1.1.3):

    Suporta:
    - Textuais (.txt, .docx, .pdf textual): limite de 10 MB, extração direta, sanitização preventiva de PII.
    - Multimodais (.png, .jpg, .jpeg, .pdf escaneado ou misto): limite de 25 MB, análise visual, OCR,
      sanitização preventiva de PII em `raw_text` e `raw_content.text` (Zero-PII) e tolerância a falhas parciais.
    """
    if not filename:
        raise UnsupportedFileFormatError(
            message="Nome de arquivo ausente ou inválido.",
            code="MISSING_FILENAME",
        )

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise UnsupportedFileFormatError(
            message=(
                f"Formato de arquivo '{suffix}' não suportado. "
                f"Os formatos aceitos pela plataforma são: {', '.join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))}."
            ),
            code="UNSUPPORTED_FORMAT",
        )

    with sentinel_context(filename):
        if suffix in IMAGE_EXTENSIONS:
            return _process_image_upload(filename, content, suffix)
        elif suffix == ".pdf":
            return _process_pdf_upload(filename, content)
        else:
            return _process_textual_doc(filename, content)


def decompose_material_service(raw_text: str) -> MaterialStructure:
    """Executa a decomposição estrutural automática do material didático (RF-02 / História 1.1.2).

    1. Sanitização preventiva de PII.
    2. Validação básica de presença de conteúdo.
    3. Decomposição estrutural em cabeçalho, textos de apoio e questões independentes.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise MaterialValidationError(
            message="O texto fornecido para decomposição estrutural está vazio.",
            code="EMPTY_TEXT",
            field="text",
        )

    with sentinel_context(raw_text):
        # Garante sanitização de PII antes de decompor
        sanitized, _ = sanitize_pii(raw_text)
        # Mesmos limites de tamanho da entrada de texto (História 1.1.1)
        validate_material_content(sanitized)
        return decompose_material(sanitized)


def organize_prose_service(raw_text: str) -> ProseStructure:
    """Executa a organização estrutural automática de textos corridos (RF-02 Extensão / História 1.1.4).

    1. Sanitização preventiva de PII.
    2. Validação básica de presença de conteúdo.
    3. Construção da árvore hierárquica (títulos, seções, subseções, parágrafos e listas).
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise MaterialValidationError(
            message="O texto fornecido para organização estrutural está vazio.",
            code="EMPTY_TEXT",
            field="text",
        )

    with sentinel_context(raw_text):
        sanitized, _ = sanitize_pii(raw_text)
        # Mesmos limites de tamanho da entrada de texto (História 1.1.1)
        validate_material_content(sanitized)
        return organize_prose_structure(sanitized)


# Roteamento FastAPI (quando FastAPI estiver disponível)
try:
    from fastapi import APIRouter, File, HTTPException, UploadFile, status

    router = APIRouter(prefix="/materials", tags=["materials"])

    @router.post(
        "/text",
        response_model=dict[str, Any],
        summary="Entrada de material didático via texto direto",
        description="Recebe texto digitado ou colado pelo docente, executa sanitização preventiva de PII e validação.",
    )
    async def upload_material_text(payload: MaterialTextInput) -> dict[str, Any]:
        try:
            text_val = payload.text if hasattr(payload, "text") else payload["text"]
            response = process_material_text_service(text_val)
            return response.model_dump()
        except MaterialValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": f"Erro interno ao processar texto ({type(err).__name__}).", "code": "INTERNAL_ERROR"},
            ) from err

    @router.post(
        "/upload",
        response_model=OcrMaterialResponse | MaterialResponse,
        summary="Entrada de material didático via upload de arquivos (.pdf, .docx, .txt, .png, .jpg, .jpeg)",
        description=(
            "Recebe arquivos pedagógicos em multipart/form-data (.pdf, .docx, .txt, .png, .jpg, .jpeg). "
            "Para arquivos puramente textuais (.txt, .docx e .pdf textual), aplica extração direta e valida o limite de 10 MB, "
            "retornando MaterialResponse. Para imagens (.png, .jpg, .jpeg) e PDFs digitalizados ou mistos, executa "
            "análise visual, OCR sequencial em memória (limite de 25 MB e 25M pixels/página), sanitização preventiva "
            "Zero-Retention e constrói o contrato unificado RawContent, retornando OcrMaterialResponse."
        ),
        responses={
            200: {
                "description": "Sucesso no processamento. Retorna MaterialResponse (textual) ou OcrMaterialResponse (multimodal/OCR).",
            },
            400: {
                "description": "Formato de arquivo não suportado pela plataforma.",
            },
            422: {
                "description": "Erro de validação de negócio, arquivo corrompido, limite de tamanho ou falha no processamento visual/OCR.",
            },
            503: {
                "description": "Serviço de OCR (Tesseract/idioma português) indisponível neste ambiente.",
            },
            500: {
                "description": "Erro interno não tratado durante o processamento.",
            },
        },
    )
    async def upload_material_file(file: UploadFile = File(...)) -> OcrMaterialResponse | MaterialResponse:
        filename = file.filename or "desconhecido"
        suffix = Path(filename).suffix.lower()
        try:
            # Leitura direta em memória (Zero-Database) e execução em threadpool fora do event loop
            content = await file.read()
            if suffix in IMAGE_EXTENSIONS or suffix == ".pdf":
                async with _get_ocr_semaphore():
                    return await _run_in_threadpool(process_material_file_service, filename, content)
            return await _run_in_threadpool(process_material_file_service, filename, content)
        except UnsupportedFileFormatError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": err.message, "code": err.code, "field": "file"},
            ) from err
        except OcrServiceUnavailableError as err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"detail": err.message, "code": err.code, "field": "file"},
            ) from err
        except DocumentParsingError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"detail": err.message, "code": err.code, "field": "file"},
            ) from err
        except MaterialValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": f"Erro interno ao processar arquivo ({type(err).__name__}).", "code": "INTERNAL_ERROR"},
            ) from err

    @router.post(
        "/decompose",
        response_model=dict[str, Any],
        summary="Decomposição estrutural automática de material pedagógico (História 1.1.2)",
        description="Segmenta deterministicamente cabeçalho, textos de apoio e lista ordenada de questões independentes.",
    )
    async def decompose_material_endpoint(payload: MaterialTextInput) -> dict[str, Any]:
        try:
            text_val = payload.text if hasattr(payload, "text") else payload["text"]
            structure = decompose_material_service(text_val)
            return structure.model_dump()
        except MaterialValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": f"Erro interno ao decompor material ({type(err).__name__}).", "code": "INTERNAL_ERROR"},
            ) from err

    @router.post(
        "/organize-prose",
        response_model=dict[str, Any],
        summary="Organização estrutural automática de textos corridos (História 1.1.4)",
        description="Identifica e organiza hierarquicamente títulos, subtítulos, seções, subseções, parágrafos e listas.",
    )
    async def organize_prose_endpoint(payload: MaterialTextInput) -> dict[str, Any]:
        try:
            text_val = payload.text if hasattr(payload, "text") else payload["text"]
            structure = organize_prose_service(text_val)
            return structure.model_dump()
        except MaterialValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": f"Erro interno ao organizar texto corrido ({type(err).__name__}).", "code": "INTERNAL_ERROR"},
            ) from err


except ImportError:
    # Router stub quando FastAPI não estiver instalado no ambiente local
    router = None  # type: ignore

