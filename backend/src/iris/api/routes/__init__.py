"""Rotas da API v1 (materiais, catálogos, sessões de adaptação e exportação)."""
from iris.api.routes.materials import (
    decompose_material_service,
    process_material_file_service,
    process_material_text_service,
    router as materials_router,
)

__all__ = [
    "decompose_material_service",
    "materials_router",
    "process_material_file_service",
    "process_material_text_service",
]


