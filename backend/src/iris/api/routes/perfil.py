"""Rota de exportação do Perfil Pedagógico Portátil (História 3.2.1, RF-15, RNF-01).

POST /api/v1/perfil/exportar?formato=json|pdf
Recebe o perfil no corpo, valida pelo schema oficial e devolve o arquivo para download.
Sem estado: nada é gravado e a resposta proíbe cache (`Cache-Control: no-store`).
"""
from __future__ import annotations

from typing import Any

from iris.exportacao.perfil import ArquivoExportado, FormatoInvalidoError, exportar_perfil
from iris.schemas.portable_profile import PerfilInvalidoError


def exportar_perfil_service(payload: Any, formato: str) -> ArquivoExportado:
    return exportar_perfil(payload, formato)


try:
    from fastapi import APIRouter, Body, HTTPException, Query, Response, status

    router = APIRouter(prefix="/perfil", tags=["perfil"])

    @router.post(
        "/exportar",
        summary="Exporta o perfil pedagógico portátil em .json ou .pdf (sem armazenar nada)",
        response_class=Response,
    )
    async def exportar(
        payload: Any = Body(...),
        formato: str = Query("json", description="json ou pdf"),
    ) -> Response:
        try:
            arquivo = exportar_perfil_service(payload, formato)
        except FormatoInvalidoError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err.to_dict()) from err
        except PerfilInvalidoError as err:
            # Sem o trecho digitado: a resposta de erro também não pode ecoar dado clínico.
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err.to_dict(incluir_trecho=False)
            ) from err
        return Response(
            content=arquivo.conteudo,
            media_type=arquivo.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{arquivo.nome}"',
                "Cache-Control": "no-store",
            },
        )
except ImportError:  # FastAPI ausente: o serviço continua utilizável
    router = None  # type: ignore[assignment]
