"""Rotas e serviços de processamento de materiais didáticos (História 1.1.1 - Issue #4).

Endpoints:
- POST /api/v1/materials/text: entrada direta via texto digitado/colado pelo docente.
- POST /api/v1/materials/upload: upload de arquivos .txt, .pdf e .docx (multipart/form-data).
"""
from __future__ import annotations

from typing import Any

from iris.parsers.document_extractor import (
    DocumentParsingError,
    UnsupportedFileFormatError,
    extract_text_from_file,
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
    ProseStructure,
    validate_file_size_limit,
    validate_material_content,
)
from iris.security.pii_scrubber import sanitize_pii



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


def process_material_file_service(filename: str, content: bytes) -> MaterialResponse:
    """Executa o pipeline completo em memória para upload de documentos:

    1. Controle de tamanho máximo do arquivo em memória.
    2. Validação de formato e extração textual em memória (.txt, .pdf, .docx).
    3. Sanitização preventiva de PII (Zero-Retention / RNF-02).
    4. Validação de regras de negócio (mínimo 50 caracteres e janela de contexto da IA / RF-01).
    5. Construção do envelope de resposta padronizado.
    """
    if not filename:
        raise UnsupportedFileFormatError(
            message="Nome de arquivo ausente ou inválido.",
            code="MISSING_FILENAME",
        )

    # 1. Validar limite de tamanho binário do arquivo
    validate_file_size_limit(content)

    # 2. Extração em memória
    extracted_text, detected_format = extract_text_from_file(filename, content)

    # 2. Sanitizar PII
    sanitized_text, pii_count = sanitize_pii(extracted_text)

    # 3. Validar limites de negócio
    char_count, word_count = validate_material_content(sanitized_text)

    # 4. Retornar resposta
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
                detail={"detail": f"Erro interno ao processar texto: {err}", "code": "INTERNAL_ERROR"},
            ) from err

    @router.post(
        "/upload",
        response_model=dict[str, Any],
        summary="Entrada de material didático via upload de arquivos (.pdf, .docx, .txt)",
        description="Recebe arquivos em multipart/form-data, extrai o texto em memória, sanitiza PII e valida limites.",
    )
    async def upload_material_file(file: UploadFile = File(...)) -> dict[str, Any]:
        filename = file.filename or "desconhecido"
        try:
            # Leitura direta em memória (Zero-Database)
            content = await file.read()
            response = process_material_file_service(filename, content)
            return response.model_dump()
        except UnsupportedFileFormatError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
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
                detail={"detail": f"Erro interno ao processar arquivo: {err}", "code": "INTERNAL_ERROR"},
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
                detail={"detail": f"Erro interno ao decompor material: {err}", "code": "INTERNAL_ERROR"},
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
                detail={"detail": f"Erro interno ao organizar texto corrido: {err}", "code": "INTERNAL_ERROR"},
            ) from err


except ImportError:
    # Router stub quando FastAPI não estiver instalado no ambiente local
    router = None  # type: ignore

