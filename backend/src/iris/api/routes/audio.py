"""Rotas da observação pedagógica por voz (História 1.2.3, RF-03/RF-05).

POST /api/v1/audio/transcribe  áudio WAV/WebM/Ogg/MP4 de até 60 s (multipart, campo `file`) -> transcrição
                               sanitizada + características sugeridas (o professor confirma na tela)
POST /api/v1/audio/suggest     {"texto": "..."} -> as mesmas sugestões a partir de um texto (digitado ou corrigido)
"""
from __future__ import annotations

from typing import Any

from iris.audio.erros import AudioError
from iris.audio.servico import sugerir_de_texto, transcrever_observacao
from iris.audio.validacao import MAX_BYTES

try:
    from fastapi import APIRouter, Body, File, HTTPException, Response, UploadFile

    router = APIRouter(prefix="/audio", tags=["audio"])

    def _http(err: AudioError) -> HTTPException:
        return HTTPException(err.status, detail=err.to_dict(), headers={"Cache-Control": "no-store"})

    @router.post("/transcribe", summary="Transcreve a observação por voz e sugere características funcionais")
    def transcrever(response: Response, file: UploadFile = File(...), id_catalogo: str | None = None) -> dict[str, Any]:
        # `def` (não `async def`): o FastAPI roda em thread e a transcrição não trava o servidor.
        response.headers["Cache-Control"] = "no-store"
        dados = file.file.read(MAX_BYTES + 1)  # lê no máximo o limite + 1 byte: arquivo maior é recusado sem carregar tudo
        try:
            return transcrever_observacao(dados, id_catalogo=id_catalogo)
        except AudioError as err:
            raise _http(err) from err

    @router.post("/suggest", summary="Sugere características funcionais a partir de um texto")
    def sugerir(response: Response, payload: Any = Body(...)) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        try:
            if not isinstance(payload, dict) or set(payload) - {"texto", "id_catalogo"}:
                raise AudioError("Envie apenas 'texto' (e, se quiser, 'id_catalogo').", "INVALID_BODY", 422, "body")
            return sugerir_de_texto(payload.get("texto"), payload.get("id_catalogo"))
        except AudioError as err:
            raise _http(err) from err
except ImportError:  # FastAPI ausente: o serviço continua utilizável
    router = None  # type: ignore[assignment]
