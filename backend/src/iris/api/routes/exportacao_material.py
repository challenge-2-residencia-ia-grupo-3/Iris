"""Rotas de exportação do material adaptado (História 2.2.3, RF-14).

POST /api/v1/adaptacao/exportar?formato=pdf|docx            -> arquivo para download
POST /api/v1/adaptacao/verificar-exportacao                 -> avisos antes de exportar (JSON)

Sem estado: recebe o texto aprovado, devolve o resultado e esquece (`Cache-Control: no-store`).
"""
from __future__ import annotations

from typing import Any

from iris.exportacao.material import ArquivoMaterial, ExportacaoMaterialError, exportar_material, verificar_material


def exportar_material_service(payload: Any, formato: str) -> ArquivoMaterial:
    return exportar_material(payload, formato)


def verificar_exportacao_service(payload: Any) -> dict[str, Any]:
    return verificar_material(payload)


try:
    from fastapi import APIRouter, Body, HTTPException, Query, Response, status

    router = APIRouter(prefix="/adaptacao", tags=["adaptacao"])

    @router.post("/exportar", summary="Exporta a atividade aprovada em PDF econômico ou DOCX editável", response_class=Response)
    async def exportar(
        payload: Any = Body(...),
        formato: str = Query("pdf", description="pdf ou docx"),
    ) -> Response:
        try:
            arquivo = exportar_material_service(payload, formato)
        except ExportacaoMaterialError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err.to_dict()) from err
        return Response(
            content=arquivo.conteudo,
            media_type=arquivo.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{arquivo.nome}"',
                "Cache-Control": "no-store",
            },
        )

    @router.post("/verificar-exportacao", summary="Avisa sobre possível dado pessoal ou termo clínico antes de exportar")
    async def verificar(payload: Any = Body(...)) -> dict[str, Any]:
        try:
            return verificar_exportacao_service(payload)
        except ExportacaoMaterialError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err.to_dict()) from err
except ImportError:  # FastAPI ausente: os serviços continuam utilizáveis
    router = None  # type: ignore[assignment]
