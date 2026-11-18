"""Rotas da API v1 (materiais, catálogos, sessões de adaptação e exportação)."""
from iris.api.routes.agents import (
    adapt_material_multiagent_service,
    router as agents_router,
)
from iris.api.routes.materials import (
    decompose_material_service,
    organize_prose_service,
    process_material_file_service,
    process_material_text_service,
    router as materials_router,
)

__all__ = [
    "adapt_material_multiagent_service",
    "agents_router",
    "decompose_material_service",
    "materials_router",
    "organize_prose_service",
    "process_material_file_service",
    "process_material_text_service",
]


