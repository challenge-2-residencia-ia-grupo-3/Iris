"""Rotas e serviços de Calibragem de Nível de Andaime Cognitivo e Travas Curriculares (Histórias 1.3.1 e 1.3.2 — Issues #12 e #13).

Atende:
- RF-07: Calibragem do Nível de Andaime Cognitivo (Scaffolding em 3 Níveis: Leve, Moderado, Intensivo).
- RF-08: Definição Explícita de Travas Curriculares Inegociáveis.
- RF-09: Validador Preventivo de Perda Cognitiva (Alerta Anti-Muleta).
- RNF-10: Carga Cognitiva Reduzida na Interface do Professor (Etapa 3 do fluxo guiado).

Endpoints:
- GET  /api/v1/scaffolding/levels                    -> Retorna os metadados dos 3 níveis e exemplos de travas.
- POST /api/v1/scaffolding/calibrate                 -> Calibra a diretiva de andaime e opcionalmente valida a trava curricular.
- POST /api/v1/scaffolding/curriculum-locks/validate -> Valida explicitamente a Trava Curricular Inegociável e emite alerta anti-muleta.
"""
from __future__ import annotations

from typing import Any

from iris.schemas.catalog import (
    CatalogValidationError,
    CharacteristicCatalog,
    CharacteristicSelectionError,
    load_official_tdah_catalog,
)
from iris.schemas.scaffolding import (
    ScaffoldingCalibrationRequest,
    ScaffoldingCalibrationResponse,
    ScaffoldingValidationError,
    calibrate_scaffolding_service,
    get_scaffolding_levels_metadata,
    validate_curriculum_locks_service,
)


def get_scaffolding_levels_service() -> dict[str, Any]:
    """Retorna os metadados e salvaguardas dos 3 níveis de andaime para a interface."""
    return get_scaffolding_levels_metadata()


def calibrate_scaffolding_session_service(
    payload: dict[str, Any] | ScaffoldingCalibrationRequest,
    catalog: CharacteristicCatalog | None = None,
) -> ScaffoldingCalibrationResponse:
    """Valida e aplica a calibragem de andaime sobre as características selecionadas na Etapa 2."""
    if catalog is None:
        catalog = load_official_tdah_catalog()
    return calibrate_scaffolding_service(payload=payload, catalog=catalog)


def validate_curriculum_locks_session_service(
    payload: dict[str, Any] | ScaffoldingCalibrationRequest,
    catalog: CharacteristicCatalog | None = None,
) -> ScaffoldingCalibrationResponse:
    """Valida obrigatoriamente a Trava Curricular Inegociável e executa o validador preventivo anti-muleta (RF-08, RF-09)."""
    if catalog is None:
        catalog = load_official_tdah_catalog()
    return validate_curriculum_locks_service(payload=payload, catalog=catalog)


# Roteamento FastAPI (quando FastAPI estiver disponível no ambiente)
try:
    from fastapi import APIRouter, Body, HTTPException, status

    router = APIRouter(prefix="/scaffolding", tags=["scaffolding"])

    @router.get(
        "/levels",
        response_model=dict[str, Any],
        summary="Metadados dos 3 níveis de andaime cognitivo e exemplos de travas (Etapa 3)",
        description=(
            "Retorna as especificações estruturais, objetivos psicopedagógicos, salvaguardas "
            "anti-muleta e exemplos de travas curriculares para a Etapa 3."
        ),
    )
    async def get_scaffolding_levels() -> dict[str, Any]:
        return get_scaffolding_levels_service()

    @router.post(
        "/calibrate",
        response_model=ScaffoldingCalibrationResponse,
        summary="Calibragem de andaime cognitivo cirúrgico e trava curricular (Etapa 3)",
        description=(
            "Configura as diretrizes de andaime estrutural estritamente para as características "
            "funcionais selecionadas na Etapa 2, mantendo isolamento de escopo e travas curriculares."
        ),
    )
    async def calibrate_scaffolding(
        payload: dict[str, Any] = Body(...),
    ) -> ScaffoldingCalibrationResponse:
        try:
            return calibrate_scaffolding_session_service(payload=payload)
        except ScaffoldingValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except CharacteristicSelectionError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except CatalogValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": str(err), "code": "CATALOG_SCHEMA_ERROR", "field": "catalog"},
            ) from err

    @router.post(
        "/curriculum-locks/validate",
        response_model=ScaffoldingCalibrationResponse,
        summary="Validação explícita de Travas Curriculares Inegociáveis e Alerta Anti-Muleta (História 1.3.2)",
        description=(
            "Marca os conceitos técnicos e habilidades da BNCC como invariantes obrigatórios para o Agente Auditor "
            "e executa o validador preventivo de perda cognitiva (anti-muleta)."
        ),
    )
    async def validate_curriculum_locks(
        payload: dict[str, Any] = Body(...),
    ) -> ScaffoldingCalibrationResponse:
        try:
            return validate_curriculum_locks_session_service(payload=payload)
        except ScaffoldingValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except CharacteristicSelectionError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.to_dict(),
            ) from err
        except CatalogValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": str(err), "code": "CATALOG_SCHEMA_ERROR", "field": "catalog"},
            ) from err

except ImportError:  # pragma: no cover
    router = None  # type: ignore
