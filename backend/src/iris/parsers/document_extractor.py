"""Serviço de extração textual de documentos pedagógicos em memória (.pdf, .docx, .txt).

Atende:
- RF-01: Inserção de conteúdo por upload de arquivos .pdf, .docx e .txt.
- RNF-01: Operação estritamente em memória (Zero-Database / sem arquivos em disco).
- Preservação de acentuação e caracteres em língua portuguesa (UTF-8 com fallback).
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Final

ALLOWED_EXTENSIONS: Final[set[str]] = {".txt", ".pdf", ".docx"}


class DocumentParsingError(ValueError):
    """Erro lançado quando um documento não pode ser decodificado ou não contém texto legível."""

    def __init__(self, message: str, code: str = "DOCUMENT_PARSING_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class UnsupportedFileFormatError(ValueError):
    """Erro lançado quando o formato do arquivo não é suportado pelo sistema."""

    def __init__(self, message: str, code: str = "UNSUPPORTED_FORMAT") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_extracted_text(text: str) -> str:
    """Normaliza o texto extraído, padronizando quebras de linha e espaçamentos redundantes.

    Preserva a estrutura de parágrafos e caracteres da língua portuguesa.
    """
    if not text:
        return ""

    # Normalizar quebras de linha Windows e Mac antigo para padrão Unix (\n)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    # Substituir espaços sem quebra (non-breaking space) por espaço padrão
    normalized = normalized.replace("\xa0", " ")

    # Remover espaços em branco no fim de cada linha
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))

    # Colapsar excessos de linhas vazias consecutivas (máximo de 2 quebras seguidas)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()


def extract_text_from_txt(content: bytes) -> str:
    """Extrai texto de arquivo .txt em memória garantindo decodificação correta.

    Tenta primariamente UTF-8; caso falhe, aplica fallback para Latin-1 (ISO-8859-1 / CP1252).
    """
    if not content:
        raise DocumentParsingError("O arquivo de texto (.txt) está vazio.", code="EMPTY_FILE")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback comum para arquivos criados no bloco de notas em ambiente Windows brasileiro
        try:
            text = content.decode("latin-1")
        except Exception as err:
            raise DocumentParsingError(
                f"Não foi possível decodificar o arquivo .txt em UTF-8 nem Latin-1: {err}",
                code="DECODE_ERROR",
            ) from err

    normalized = normalize_extracted_text(text)
    if not normalized:
        raise DocumentParsingError("O arquivo .txt não contém conteúdo textual legível.", code="NO_READABLE_TEXT")

    return normalized


def extract_text_from_pdf(content: bytes) -> str:
    """Extrai texto de arquivo .pdf a partir de fluxo de bytes em memória utilizando PyMuPDF.

    Lança DocumentParsingError caso o PDF não possua camada de texto (ex.: digitalização de imagem).
    """
    if not content:
        raise DocumentParsingError("O arquivo PDF (.pdf) está vazio.", code="EMPTY_FILE")

    try:
        import fitz  # PyMuPDF
    except ImportError as err:
        raise DocumentParsingError(
            "A biblioteca PyMuPDF (fitz) não está disponível no ambiente para processamento de PDF.",
            code="LIBRARY_NOT_AVAILABLE",
        ) from err

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as err:
        raise DocumentParsingError(
            f"O arquivo PDF enviado está corrompido ou possui formato inválido: {err}",
            code="CORRUPTED_PDF",
        ) from err

    pages_text: list[str] = []
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            extracted = page.get_text()
            if extracted and extracted.strip():
                pages_text.append(extracted.strip())
    finally:
        doc.close()

    full_text = "\n\n".join(pages_text)
    normalized = normalize_extracted_text(full_text)

    if not normalized:
        raise DocumentParsingError(
            "O arquivo PDF não possui texto selecionável. Pode se tratar de uma imagem digitalizada "
            "(o módulo multimodal com OCR será integrado na Semana 5).",
            code="NO_READABLE_TEXT",
        )

    return normalized


def extract_text_from_docx(content: bytes) -> str:
    """Extrai texto de arquivo .docx em memória utilizando python-docx.

    Processa sequencialmente parágrafos e células de tabelas para manter a integridade da prova.
    """
    if not content:
        raise DocumentParsingError("O arquivo Word (.docx) está vazio.", code="EMPTY_FILE")

    try:
        import docx
    except ImportError as err:
        raise DocumentParsingError(
            "A biblioteca python-docx não está disponível no ambiente para processamento de DOCX.",
            code="LIBRARY_NOT_AVAILABLE",
        ) from err

    try:
        doc = docx.Document(io.BytesIO(content))
    except Exception as err:
        raise DocumentParsingError(
            f"O arquivo .docx enviado está corrompido ou possui formato inválido: {err}",
            code="CORRUPTED_DOCX",
        ) from err

    text_blocks: list[str] = []

    # 1. Extrair parágrafos
    for paragraph in doc.paragraphs:
        t = paragraph.text.strip()
        if t:
            text_blocks.append(t)

    # 2. Extrair tabelas (questões com dados tabulares)
    for table in doc.tables:
        for row in table.rows:
            # Deduplica células mescladas consecutivas
            cells_content: list[str] = []
            for cell in row.cells:
                ct = cell.text.strip()
                if ct and (not cells_content or cells_content[-1] != ct):
                    cells_content.append(ct)
            if cells_content:
                text_blocks.append(" | ".join(cells_content))

    full_text = "\n\n".join(text_blocks)
    normalized = normalize_extracted_text(full_text)

    if not normalized:
        raise DocumentParsingError(
            "O arquivo .docx está vazio ou sem conteúdo textual legível.",
            code="NO_READABLE_TEXT",
        )

    return normalized


def extract_text_from_file(filename: str, content: bytes) -> tuple[str, str]:
    """Despachante central para extração de texto conforme a extensão do arquivo.

    Args:
        filename: Nome original do arquivo (com extensão).
        content: Conteúdo binário bruto do arquivo.

    Returns:
        tuple[str, str]: (texto_normalizado_extraido, formato_identificado)

    Raises:
        UnsupportedFileFormatError: se a extensão não for suportada.
        DocumentParsingError: se a extração falhar ou o arquivo estiver ilegível.
    """
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileFormatError(
            f"Formato de arquivo '{suffix}' não suportado. "
            f"Os formatos aceitos pela plataforma são: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
            code="UNSUPPORTED_FORMAT",
        )

    if suffix == ".txt":
        return extract_text_from_txt(content), "txt"
    elif suffix == ".pdf":
        return extract_text_from_pdf(content), "pdf"
    elif suffix == ".docx":
        return extract_text_from_docx(content), "docx"
    else:
        raise UnsupportedFileFormatError(f"Formato '{suffix}' não implementado.")

