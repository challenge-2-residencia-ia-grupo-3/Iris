"""Rotas da API v1 (materiais, catálogos, sessões de adaptação e exportação)."""
from iris.api.routes.materials import (
    process_material_file_service,
    process_material_text_service,
    router as materials_router,
)

__all__ = [
    "materials_router",
    "process_material_file_service",
    "process_material_text_service",
]

