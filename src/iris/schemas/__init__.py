"""Contratos de dados e schemas de validação (Catálogos, Materiais, Travas e Perfil Portátil)."""
from iris.schemas.catalog import (
    BARREIRAS_RAG_VALIDAS,
    PRINCIPIOS_DUA_VALIDOS,
    BibliographicReference,
    CatalogValidationError,
    CharacteristicCatalog,
    CharacteristicItem,
    ScaffoldingLevelGuideline,
    get_characteristic_by_id,
    load_all_catalogs,
    load_catalog_file,
)
from iris.schemas.materials import (
    MAX_MATERIAL_WORDS,
    MIN_MATERIAL_CHARS,
    MaterialMetadata,
    MaterialResponse,
    MaterialSourceType,
    MaterialTextInput,
    MaterialValidationError,
    validate_material_content,
)

__all__ = [
    "BARREIRAS_RAG_VALIDAS",
    "PRINCIPIOS_DUA_VALIDOS",
    "BibliographicReference",
    "CatalogValidationError",
    "CharacteristicCatalog",
    "CharacteristicItem",
    "ScaffoldingLevelGuideline",
    "get_characteristic_by_id",
    "load_all_catalogs",
    "load_catalog_file",
    "MAX_MATERIAL_WORDS",
    "MIN_MATERIAL_CHARS",
    "MaterialMetadata",
    "MaterialResponse",
    "MaterialSourceType",
    "MaterialTextInput",
    "MaterialValidationError",
    "validate_material_content",
]

