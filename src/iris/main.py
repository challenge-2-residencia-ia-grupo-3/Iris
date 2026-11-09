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

    app = FastAPI(
        title="Íris — Adaptação Inteligente de Materiais Pedagógicos",
        description=(
            "Plataforma copiloto docente para adaptação cirúrgica de materiais didáticos "
            "baseada em evidências (DUA/MEC) e arquitetura Zero-Database (LGPD)."
        ),
        version=__version__,
    )

    @app.get("/api/v1/health", tags=["infra"])
    def health_check() -> dict[str, Any]:
        return get_health_status()

    return app

