"""Ponto de entrada FastAPI stateless (Zero-Database de Alunos) da plataforma Íris."""
from __future__ import annotations

from typing import Any

from iris import __version__
from iris.config import get_settings


def get_health_status() -> dict[str, Any]:
    """Retorna o status operacional e guardrails arquiteturais do serviço."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "iris-pedagogical-adapter",
        "version": __version__,
        "environment": settings.env,
        "zero_student_database": settings.zero_student_database,
        "llm_provider": settings.llm_provider,
        "rag_backend": settings.rag_banco,
    }


def create_app() -> Any:
    """Cria e configura a aplicação FastAPI stateless."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Íris — Adaptação Inteligente de Materiais Pedagógicos",
        description=(
            "Plataforma copiloto docente para adaptação cirúrgica de materiais didáticos "
            "baseada em evidências (DUA/MEC) e arquitetura Zero-Database (LGPD)."
        ),
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", tags=["infra"])
    def health_check() -> dict[str, Any]:
        return get_health_status()

    # Registra rotas de materiais didáticos (História 1.1.1 - Issue #4)
    from iris.api.routes.materials import router as materials_router

    if materials_router is not None:
        app.include_router(materials_router, prefix="/api/v1")

    return app


try:
    app = create_app()
except ImportError:
    app = None  # type: ignore


