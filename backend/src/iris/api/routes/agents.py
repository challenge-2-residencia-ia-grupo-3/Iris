"""Rotas HTTP do Sistema Multiagentes (Etapa 4 — Issues #15, #16, #17, #18 e #19).

Expõe o endpoint stateless ``POST /api/v1/agents/adapt`` que coordena Extrator Curricular,
Estrategista RAG, Adaptador Pedagógico e Agente Auditor sobre um material didático sanitizado.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from iris.agents.orchestrator import (
    MultiAgentMaterialRequest,
    MultiAgentMaterialResponse,
    MultiAgentOrchestrator,
)

logger = logging.getLogger(__name__)


class AgentOrchestrationValidationError(ValueError):
    """Erro de validação do payload multiagentes traduzido para HTTP 422."""

    def __init__(self, detail: str, code: str = "INVALID_ADAPTATION_REQUEST", field: str = "body") -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.field = field

    def to_dict(self) -> dict[str, str]:
        return {
            "status": "error",
            "code": self.code,
            "field": self.field,
            "detail": self.detail,
        }


def adapt_material_multiagent_service(
    payload: dict[str, Any] | MultiAgentMaterialRequest,
    orchestrator: MultiAgentOrchestrator | None = None,
) -> MultiAgentMaterialResponse:
    """Executa o fluxo multiagentes validando entrada e traduzindo erros de domínio."""
    orch = orchestrator or MultiAgentOrchestrator()
    try:
        req = (
            payload
            if isinstance(payload, MultiAgentMaterialRequest)
            else MultiAgentMaterialRequest.model_validate(payload)
        )
        return orch.run(req)
    except ValidationError as err:
        primeiro = err.errors()[0] if err.errors() else {}
        loc = ".".join(str(p) for p in primeiro.get("loc", ())) or "body"
        msg = str(primeiro.get("msg") or "Payload inválido para execução multiagentes.")
        raise AgentOrchestrationValidationError(
            detail=msg,
            code="INVALID_ADAPTATION_REQUEST",
            field=loc,
        ) from err
    except KeyError as err:
        raise AgentOrchestrationValidationError(
            detail=str(err).strip("'\""),
            code="INVALID_ADAPTATION_REQUEST",
            field="selected_ids",
        ) from err
    except ValueError as err:
        raise AgentOrchestrationValidationError(
            detail=str(err),
            code="INVALID_ADAPTATION_REQUEST",
            field="body",
        ) from err


try:
    from fastapi import APIRouter, Body, HTTPException, status

    router = APIRouter(prefix="/agents", tags=["agents"])

    @router.post(
        "/adapt",
        response_model=MultiAgentMaterialResponse,
        summary="Adaptação via Sistema Multiagentes (Etapa 4)",
        description=(
            "Executa em memória o fluxo completo: Sanitização PII -> Decomposição Estrutural -> "
            "Agente Extrator (#17) -> Agente Estrategista RAG (#16) -> Agente Adaptador (#18) <-> "
            "Agente Auditor (#19), retornando trace detalhado e o payload pronto para a Etapa 5."
        ),
    )
    async def adapt_material_multiagent_endpoint(
        payload: dict[str, Any] = Body(...),
    ) -> MultiAgentMaterialResponse:
        try:
            return adapt_material_multiagent_service(payload)
        except AgentOrchestrationValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except Exception as err:  # noqa: BLE001
            logger.error("Erro interno na orquestração multiagentes (%s).", type(err).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "code": "INTERNAL_ERROR",
                    "field": "agents",
                    "detail": f"Erro interno na orquestração multiagentes ({type(err).__name__}).",
                },
            ) from err

except ImportError:  # pragma: no cover
    router = None  # type: ignore
