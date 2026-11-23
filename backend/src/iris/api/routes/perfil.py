"""Rota de exportação do Perfil Pedagógico Portátil (História 3.2.1, RF-15, RNF-01).

POST /api/v1/perfil/exportar?formato=json|pdf
Recebe o perfil no corpo, valida pelo schema oficial e devolve o arquivo para download.
Sem estado: nada é gravado e a resposta proíbe cache (`Cache-Control: no-store`).

POST /api/v1/perfil/intervencoes (História 3.1.2, Issue #27)
Recebe `{perfil, intervencao}`, valida e devolve o perfil com o registro de eficácia anexado ao
`historico_intervencoes`. Também sem estado: o servidor não guarda o perfil nem o registro.
"""
from __future__ import annotations

from typing import Any

from iris.exportacao.perfil import ArquivoExportado, FormatoInvalidoError, exportar_perfil
from iris.schemas.portable_profile import PerfilInvalidoError, registrar_intervencao, resumo_eficacia

CAMPOS_INTERVENCAO = frozenset({"estrategia", "id_caracteristica", "eficacia", "observacao"})


def registrar_intervencao_service(payload: Any) -> dict[str, Any]:
    """Valida `{perfil, intervencao}` e devolve `{perfil, resumo_eficacia}`. Levanta `PerfilInvalidoError`."""
    if not isinstance(payload, dict) or not isinstance(payload.get("perfil"), dict) or not isinstance(payload.get("intervencao"), dict):
        raise PerfilInvalidoError("INVALID_STRUCTURE", ["Envie o perfil e a intervenção como objetos JSON."])
    extras = sorted(set(payload) - {"perfil", "intervencao"})
    extras_int = sorted(set(payload["intervencao"]) - CAMPOS_INTERVENCAO)
    if extras or extras_int:
        raise PerfilInvalidoError("INVALID_STRUCTURE", ["A requisição tem campos que não fazem parte do registro de intervenção."])
    i = payload["intervencao"]
    if not all(isinstance(i.get(k), str) for k in ("estrategia", "id_caracteristica", "eficacia")) or not isinstance(
        i.get("observacao", ""), (str, type(None))
    ):
        raise PerfilInvalidoError("INVALID_STRUCTURE", ["Estratégia, característica e eficácia devem ser texto."])
    novo = registrar_intervencao(
        payload["perfil"], i["estrategia"], i["id_caracteristica"], i["eficacia"], i.get("observacao")
    )
    return {"perfil": novo.para_json(), "resumo_eficacia": resumo_eficacia(novo)}


def exportar_perfil_service(payload: Any, formato: str) -> ArquivoExportado:
    return exportar_perfil(payload, formato)


try:
    from fastapi import APIRouter, Body, HTTPException, Query, Response, status
    from fastapi.responses import JSONResponse

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

    @router.post(
        "/intervencoes",
        summary="Anexa o registro de eficácia de uma intervenção ao histórico do perfil (sem armazenar nada)",
    )
    async def registrar_intervencao_rota(payload: Any = Body(...)) -> JSONResponse:
        try:
            resultado = registrar_intervencao_service(payload)
        except PerfilInvalidoError as err:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err.to_dict(incluir_trecho=False)
            ) from err
        return JSONResponse(resultado, headers={"Cache-Control": "no-store"})
except ImportError:  # FastAPI ausente: o serviço continua utilizável
    router = None  # type: ignore[assignment]
