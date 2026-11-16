"""Rotas da sessão de revisão docente (História 2.2.2, RF-13).

POST   /api/v1/sessions                     cria a sessão em memória com as questões original/adaptada
GET    /api/v1/sessions/{id}                lê o estado (versão final em memória, aprovações, homologação)
PUT    /api/v1/sessions/{id}/review         grava edições, aprovações por questão e a homologação
POST   /api/v1/sessions/{id}/export         gera PDF/DOCX; 409 EXPORT_BLOCKED até a homologação
POST   /api/v1/sessions/{id}/verify-export  avisos de dado pessoal/termo clínico antes de exportar
DELETE /api/v1/sessions/{id}                descarta a sessão
"""
from __future__ import annotations

from typing import Any

from iris.sessao.revisao import REPOSITORIO, RepositorioSessoes, SessaoError

try:
    from fastapi import APIRouter, Body, HTTPException, Query, Response, status

    router = APIRouter(prefix="/sessions", tags=["sessao-revisao"])

    def _http(err: SessaoError) -> HTTPException:
        return HTTPException(err.status, detail=err.to_dict())

    def repo() -> RepositorioSessoes:
        return REPOSITORIO

    @router.post("", status_code=status.HTTP_201_CREATED, summary="Abre a sessão de revisão (em memória)")
    async def criar(payload: Any = Body(...)) -> dict[str, Any]:
        try:
            return repo().criar(payload)
        except SessaoError as err:
            raise _http(err) from err

    @router.get("/{session_id}", summary="Estado atual da sessão")
    async def ler(session_id: str) -> dict[str, Any]:
        try:
            return repo().ler(session_id)
        except SessaoError as err:
            raise _http(err) from err

    @router.put("/{session_id}/review", summary="Persiste em memória as edições e aprovações do professor")
    async def revisar(session_id: str, payload: Any = Body(...)) -> dict[str, Any]:
        try:
            return repo().revisar(session_id, payload)
        except SessaoError as err:
            raise _http(err) from err

    @router.post("/{session_id}/verify-export", summary="Avisos antes de exportar")
    async def verificar(session_id: str) -> dict[str, Any]:
        try:
            return repo().verificar(session_id)
        except SessaoError as err:
            raise _http(err) from err

    @router.post("/{session_id}/export", summary="Exporta a atividade homologada em PDF ou DOCX", response_class=Response)
    async def exportar(session_id: str, formato: str = Query("pdf", description="pdf ou docx")) -> Response:
        try:
            arquivo = repo().exportar(session_id, formato)
        except SessaoError as err:
            raise _http(err) from err
        return Response(
            content=arquivo.conteudo,
            media_type=arquivo.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{arquivo.nome}"',
                "Cache-Control": "no-store",
            },
        )

    @router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Descarta a sessão")
    async def descartar(session_id: str) -> Response:
        try:
            repo().descartar(session_id)
        except SessaoError as err:
            raise _http(err) from err
        return Response(status_code=status.HTTP_204_NO_CONTENT)
except ImportError:  # FastAPI ausente: o repositório continua utilizável
    router = None  # type: ignore[assignment]
