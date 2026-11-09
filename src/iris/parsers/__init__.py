"""Extratores de documentos (.pdf, .docx, .txt) e decompositor estrutural de questões."""
from iris.parsers.document_extractor import (
    ALLOWED_EXTENSIONS,
    DocumentParsingError,
    UnsupportedFileFormatError,
    extract_text_from_docx,
    extract_text_from_file,
    extract_text_from_pdf,
    extract_text_from_txt,
    normalize_extracted_text,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "DocumentParsingError",
    "UnsupportedFileFormatError",
    "extract_text_from_docx",
    "extract_text_from_file",
    "extract_text_from_pdf",
    "extract_text_from_txt",
    "normalize_extracted_text",
]

