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
from iris.parsers.prose_organizer import organize_prose_structure
from iris.parsers.structural_decomposer import decompose_material

__all__ = [
    "ALLOWED_EXTENSIONS",
    "DocumentParsingError",
    "UnsupportedFileFormatError",
    "decompose_material",
    "extract_text_from_docx",
    "extract_text_from_file",
    "extract_text_from_pdf",
    "extract_text_from_txt",
    "normalize_extracted_text",
    "organize_prose_structure",
]


