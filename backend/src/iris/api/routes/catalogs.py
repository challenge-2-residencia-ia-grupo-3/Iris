"""Rotas e serviços de catálogo e seleção cirúrgica de características funcionais (História 1.2.1 - Issue #8).

Atende:
- RF-04: Seleção Cirúrgica de Características Neurodivergentes Específicas (Pilar 1: Características Singulares > Pacote Clínico).
- RF-06: Extensibilidade de Catálogos de Perfis via arquivos modulares JSON.
- RNF-03 / RNF-10: Desacoplamento de rótulo clínico (sem exigir laudo médico) e suporte à Etapa 2 do fluxo guiado.

Endpoints:
- GET  /api/v1/catalogs/characteristics        -> Retorna o catálogo oficial de barreiras funcionais atômicas.
- POST /api/v1/catalogs/characteristics/select -> Valida e isola o vetor cirúrgico de características ativadas vs. bloqueadas.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from iris.config import CATALOGS_DIR
from iris.schemas.catalog import (
    CatalogValidationError,
    CharacteristicCatalog,
    CharacteristicSelectionError,
    SurgicalCharacteristicSelection,
    load_all_catalogs,
    load_official_tdah_catalog,
    validate_surgical_characteristic_selection,
)

ALLOWED_SELECTION_PAYLOAD_FIELDS = {"selected_ids", "id_catalogo"}


def _resolve_catalog(id_catalogo: str | None = None, directory: Path = CATALOGS_DIR) -> CharacteristicCatalog:
    """Resolve o catálogo solicitado pelo ID ou retorna o catálogo oficial de TDAH por padrão."""
    if id_catalogo and id_catalogo.strip():
        requested_id = id_catalogo.strip()
        all_catalogs = load_all_catalogs(directory=directory)
        if requested_id not in all_catalogs:
            raise CharacteristicSelectionError(
                message=f"Catálogo funcional '{requested_id}' não encontrado.",
                code="CATALOG_NOT_FOUND",
                field="id_catalogo",
            )
        return all_catalogs[requested_id]
    return load_official_tdah_catalog(directory=directory)


def get_characteristics_catalog_service(
    id_catalogo: str | None = None,
    directory: Path = CATALOGS_DIR,
) -> dict[str, Any]:
    """Carrega e retorna o catálogo oficial de características funcionais atômicas para a Etapa 2.

    Enriquece a resposta com metadados explícitos de conformidade ética (ausência de exigência de
    laudo clínico) e listas únicas de barreiras e princípios DUA para filtros de interface.
    """
    catalog = _resolve_catalog(id_catalogo=id_catalogo, directory=directory)
    data = catalog.to_dict()

    barreiras = sorted({c.barreira_rag_associada for c in catalog.caracteristicas})
    principios_dua = sorted({c.principio_dua_primario for c in catalog.caracteristicas})

    data["total_caracteristicas"] = len(catalog.caracteristicas)
    data["exige_laudo_medico"] = False
    data["barreiras_disponiveis"] = barreiras
    data["principios_dua_disponiveis"] = principios_dua
    return data


def select_surgical_characteristics_service(
    payload: dict[str, Any],
    directory: Path = CATALOGS_DIR,
) -> SurgicalCharacteristicSelection:
    """Valida o payload da Etapa 2 e registra o vetor cirúrgico de características ativadas (RF-04).

    Garante:
    1. Proibição de envio de rótulos clínicos, CIDs ou campos extras (`extra = 'forbid'`).
    2. Seleção mínima de 1 característica funcional atômica.
    3. Isolamento estrito entre `selected_ids` (escopo permitido) e `blocked_ids` (escopo bloqueado).
    """
    if not isinstance(payload, dict):
        raise CharacteristicSelectionError(
            message="O corpo da requisição deve ser um objeto JSON válido.",
            code="INVALID_PAYLOAD",
            field="body",
        )

    extra_fields = set(payload.keys()) - ALLOWED_SELECTION_PAYLOAD_FIELDS
    if extra_fields:
        sorted_extras = ", ".join(sorted(extra_fields))
        raise CharacteristicSelectionError(
            message=(
                f"Campos extras ou clínicos não permitidos na seleção funcional ({sorted_extras}). "
                "A plataforma Íris opera exclusivamente com características funcionais observáveis, sem laudo médico ou CID."
            ),
            code="CLINICAL_OR_EXTRA_FIELD_FORBIDDEN",
            field=sorted(extra_fields)[0],
        )

    id_catalogo = payload.get("id_catalogo")
    if id_catalogo is not None and not isinstance(id_catalogo, str):
        raise CharacteristicSelectionError(
            message="O campo 'id_catalogo' deve ser uma string válida.",
            code="INVALID_CATALOG_ID_TYPE",
            field="id_catalogo",
        )

    catalog = _resolve_catalog(id_catalogo=id_catalogo, directory=directory)
    selected_ids = payload.get("selected_ids")
    return validate_surgical_characteristic_selection(
        selected_ids=selected_ids,
        catalog=catalog,
        directory=directory,
    )


# Roteamento FastAPI (quando FastAPI estiver disponível no ambiente)
try:
    from fastapi import APIRouter, Body, HTTPException, Query, status

    router = APIRouter(prefix="/catalogs", tags=["catalogs"])

    @router.get(
        "/characteristics",
        response_model=dict[str, Any],
        summary="Catálogo oficial de características funcionais atômicas (Etapa 2)",
        description=(
            "Retorna o catálogo modular de barreiras funcionais observáveis em sala de aula, "
            "desacoplado de rótulos clínicos ou exigência de laudo médico (História 1.2.1 - Issue #8)."
        ),
    )
    async def get_characteristics_catalog(
        id_catalogo: str | None = Query(
            default=None,
            description="Identificador opcional do catálogo funcional (padrão: tdah_funcoes_executivas_v1).",
        ),
    ) -> dict[str, Any]:
        try:
            return get_characteristics_catalog_service(id_catalogo=id_catalogo)
        except CharacteristicSelectionError as err:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=err.to_dict(),
            ) from err
        except CatalogValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": str(err), "code": "CATALOG_SCHEMA_ERROR", "field": "catalog"},
            ) from err

    @router.post(
        "/characteristics/select",
        response_model=dict[str, Any],
        summary="Seleção cirúrgica de características funcionais observadas (Etapa 2)",
        description=(
            "Registra exclusivamente as características marcadas como escopo permitido de adaptação "
            "e bloqueia todas as demais características não assinaladas (RF-04 / História 1.2.1)."
        ),
    )
    async def select_characteristics(
        payload: dict[str, Any] = Body(
            ...,
            examples=[
                {
                    "selected_ids": [
                        "sobrecarga_memoria_trabalho_comandos_multiplos",
                    ]
                }
            ],
        ),
    ) -> dict[str, Any]:
        try:
            result = select_surgical_characteristics_service(payload=payload)
            return result.model_dump()
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

except ImportError:
    router = None  # type: ignore
