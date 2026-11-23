"""Rota do OCR de provas digitalizadas (História 1.1.3, RF-03).

POST /api/v1/materials/ocr  imagem .png/.jpg de até 10 MB (multipart, campo `file`) -> texto extraído e sanitizado no
                            mesmo formato do upload de documentos, mais `ocr` (confiança e avisos) e `analise_visual`
                            (indicador de poluição visual). Nada é guardado: a imagem vive só em memória.
"""
from __future__ import annotations

from typing import Any

from iris.ocr.erros import OcrError
from iris.ocr.servico import extrair_texto_da_imagem
from iris.ocr.validacao import MAX_BYTES

# Corpo multipart aceito: a imagem (até MAX_BYTES) mais o envelope do formulário.
MAX_CORPO = MAX_BYTES + 64 * 1024

try:
    from fastapi import APIRouter, HTTPException, Request, Response
    from starlette.concurrency import run_in_threadpool
    from starlette.formparsers import MultiPartException, MultiPartParser

    router = APIRouter(prefix="/materials", tags=["materials"])

    class _MultipartEmMemoria(MultiPartParser):
        """O `UploadFile` padrão grava em arquivo temporário tudo que passa de 1 MB, e uma foto de prova passa disso.
        Aqui o limite de memória é o próprio teto do corpo, imposto por `_corpo_limitado`: a imagem nunca vai a disco."""

        spool_max_size = MAX_CORPO + 1

    def _grande_demais() -> OcrError:
        return OcrError(
            f"A imagem passa do limite de {MAX_BYTES // (1024 * 1024)} MB. Reduza a resolução da digitalização.",
            "IMAGE_TOO_LARGE",
            413,
        )

    async def _corpo_limitado(fluxo):
        lidos = 0
        async for pedaco in fluxo:
            lidos += len(pedaco)
            if lidos > MAX_CORPO:
                raise _grande_demais()
            yield pedaco

    def _http(err: OcrError) -> HTTPException:
        return HTTPException(err.status, detail=err.to_dict(), headers={"Cache-Control": "no-store"})

    @router.post("/ocr", summary="Lê o texto de uma prova digitalizada (OCR) e mede a poluição visual")
    async def ler_imagem(request: Request, response: Response) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        formulario = None
        try:
            if int(request.headers.get("content-length") or 0) > MAX_CORPO:
                raise _grande_demais()
            if not request.headers.get("content-type", "").startswith("multipart/form-data"):
                raise OcrError("Envie a imagem como formulário (multipart), no campo 'file'.", "INVALID_BODY", 422)
            try:
                formulario = await _MultipartEmMemoria(request.headers, _corpo_limitado(request.stream())).parse()
            except MultiPartException as err:
                raise OcrError("Envie a imagem como formulário (multipart), no campo 'file'.", "INVALID_BODY", 422) from err
            arquivo = formulario.get("file")
            if arquivo is None or isinstance(arquivo, str):
                raise OcrError("Envie a imagem no campo 'file'.", "EMPTY_IMAGE", 422)
            dados = await arquivo.read(MAX_BYTES + 1)  # acima do limite, a validação recusa com 413
            # O OCR é pesado: roda em thread para não travar o servidor.
            return await run_in_threadpool(extrair_texto_da_imagem, dados)
        except OcrError as err:
            raise _http(err) from err
        finally:
            if formulario is not None:
                await formulario.close()
except ImportError:  # FastAPI ausente: o serviço continua utilizável
    router = None  # type: ignore[assignment]
