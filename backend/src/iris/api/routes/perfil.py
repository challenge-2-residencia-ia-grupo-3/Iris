"""Rota de exportação do Perfil Pedagógico Portátil (História 3.2.1, RF-15, RNF-01).

POST /api/v1/perfil/exportar?formato=json|pdf
Recebe o perfil no corpo, valida pelo schema oficial e devolve o arquivo para download.
Sem estado: nada é gravado e a resposta proíbe cache (`Cache-Control: no-store`).

POST /api/v1/perfil/intervencoes (História 3.1.2, Issue #27)
Recebe `{perfil, intervencao}`, valida e devolve o perfil com o registro de eficácia anexado ao
`historico_intervencoes`. Também sem estado: o servidor não guarda o perfil nem o registro.

POST /api/v1/perfil/importar (História 3.2.2, Issue #31)
Recebe `{arquivo}` (o texto do `.json` lido no navegador), valida pelo schema oficial e devolve o perfil
normalizado com o resumo de eficácia. Sem estado: nada é gravado e a resposta proíbe cache.
"""
from __future__ import annotations

from typing import Any

from iris.exportacao.perfil import ArquivoExportado, FormatoInvalidoError, exportar_perfil
from iris.schemas.portable_profile import (
    CODIGO_ESTRUTURA,
    PerfilInvalidoError,
    registrar_intervencao,
    resumo_eficacia,
    validar_perfil,
)

CAMPOS_INTERVENCAO = frozenset({"estrategia", "id_caracteristica", "eficacia", "observacao"})
#: Um perfil no limite do schema (200 intervenções de 500 caracteres) cabe em bem menos que isto.
MAX_BYTES_ARQUIVO = 1024 * 1024


def importar_perfil_service(payload: Any) -> dict[str, Any]:
    """Valida o texto do `.json` importado e devolve `{perfil, resumo_eficacia}`. Levanta `PerfilInvalidoError`.

    Arquivo corrompido, fora do schema ou com conteúdo clínico vira erro com mensagem clara; nada é gravado.
    """
    if not isinstance(payload, dict) or set(payload) != {"arquivo"} or not isinstance(payload["arquivo"], str):
        raise PerfilInvalidoError(CODIGO_ESTRUTURA, ["Envie o conteúdo do arquivo .json no campo 'arquivo'."])
    texto = payload["arquivo"]
    if len(texto.encode("utf-8")) > MAX_BYTES_ARQUIVO:
        raise PerfilInvalidoError(
            "FILE_TOO_LARGE", ["O arquivo é grande demais para ser um Perfil Pedagógico Portátil (máximo 1 MB)."]
        )
    if not texto.strip():
        raise PerfilInvalidoError("EMPTY_FILE", ["O arquivo está vazio."])
    perfil = validar_perfil(texto.lstrip("\ufeff"))
    return {"perfil": perfil.para_json(), "resumo_eficacia": resumo_eficacia(perfil)}


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
        "/importar",
        summary="Valida o .json do perfil pedagógico portátil para restaurar a sessão (sem armazenar nada)",
    )
    async def importar(payload: Any = Body(...)) -> JSONResponse:
        try:
            resultado = importar_perfil_service(payload)
        except PerfilInvalidoError as err:
            # Sem o trecho digitado: a resposta de erro também não pode ecoar dado clínico.
            status_http = (
                413 if err.codigo == "FILE_TOO_LARGE" else status.HTTP_422_UNPROCESSABLE_ENTITY
            )
            raise HTTPException(status_http, detail=err.to_dict(incluir_trecho=False)) from err
        return JSONResponse(resultado, headers={"Cache-Control": "no-store"})

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
