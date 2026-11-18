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

# Corpo multipart aceito: o áudio (até MAX_BYTES) mais o envelope do formulário.
MAX_CORPO = MAX_BYTES + 64 * 1024

try:
    from fastapi import APIRouter, Body, HTTPException, Request, Response
    from starlette.concurrency import run_in_threadpool
    from starlette.formparsers import MultiPartException, MultiPartParser

    router = APIRouter(prefix="/audio", tags=["audio"])

    class _MultipartEmMemoria(MultiPartParser):
        """O `UploadFile` padrão grava em arquivo temporário tudo que passa de 1 MB (60 s de WAV têm ~1,9 MB).
        Aqui o limite de memória é o próprio teto do corpo, que `_corpo_limitado` impõe: o áudio nunca vai a disco."""

        spool_max_size = MAX_CORPO + 1

    async def _corpo_limitado(fluxo):
        lidos = 0
        async for pedaco in fluxo:
            lidos += len(pedaco)
            if lidos > MAX_CORPO:
                raise AudioError(
                    f"O arquivo passa de {MAX_BYTES // (1024 * 1024)} MB. O limite é de 60 segundos de áudio.",
                    "AUDIO_TOO_LARGE",
                    413,
                )
            yield pedaco

    def _http(err: AudioError) -> HTTPException:
        return HTTPException(err.status, detail=err.to_dict(), headers={"Cache-Control": "no-store"})

    @router.post("/transcribe", summary="Transcreve a observação por voz e sugere características funcionais")
    async def transcrever(request: Request, response: Response, id_catalogo: str | None = None) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        formulario = None
        try:
            if int(request.headers.get("content-length") or 0) > MAX_CORPO:
                raise AudioError(
                    f"O arquivo passa de {MAX_BYTES // (1024 * 1024)} MB. O limite é de 60 segundos de áudio.",
                    "AUDIO_TOO_LARGE",
                    413,
                )
            if not request.headers.get("content-type", "").startswith("multipart/form-data"):
                raise AudioError("Envie o áudio como formulário (multipart), no campo 'file'.", "INVALID_BODY", 422, "file")
            try:
                formulario = await _MultipartEmMemoria(request.headers, _corpo_limitado(request.stream())).parse()
            except MultiPartException as err:
                raise AudioError("Envie o áudio como formulário (multipart), no campo 'file'.", "INVALID_BODY", 422, "file") from err
            arquivo = formulario.get("file")
            if arquivo is None or isinstance(arquivo, str):
                raise AudioError("Envie o áudio no campo 'file'.", "EMPTY_AUDIO", 422, "file")
            dados = await arquivo.read(MAX_BYTES + 1)  # acima do limite, a validação recusa com 413
            # A transcrição é pesada: roda em thread para não travar o servidor.
            return await run_in_threadpool(transcrever_observacao, dados, id_catalogo=id_catalogo)
        except AudioError as err:
            raise _http(err) from err
        finally:
            if formulario is not None:
                await formulario.close()

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
