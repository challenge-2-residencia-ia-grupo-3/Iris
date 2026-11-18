"""Transcrição de fala em português (Speech-to-Text) executada LOCALMENTE.

A fala do professor só pode virar texto no próprio servidor: assim o áudio bruto, que ainda não passou pelo
sanitizador de PII (RNF-02), não é transmitido a nenhuma API externa. O motor padrão é o faster-whisper
(dependência opcional, `pip install faster-whisper`); qualquer objeto com `transcrever(audio, idioma)` serve,
o que permite trocar o motor (e testar sem baixar modelo) com `definir_transcritor`.

Variáveis de ambiente do motor padrão: IRIS_STT_MODEL (padrão "small"), IRIS_STT_DEVICE ("cpu"),
IRIS_STT_COMPUTE ("int8") e IRIS_STT_OFFLINE ("1" = só usa o modelo já baixado).
O áudio é decodificado em memória (PyAV) para amostras de 16 kHz mono e entregue ao motor já decodificado:
nenhum arquivo temporário é criado e o motor não depende de como o `faster-whisper` chama o PyAV (que muda
entre versões).
"""
from __future__ import annotations

import io
import os
import threading
from typing import Protocol

from iris.audio.erros import AudioError


def decodificar_para_amostras(audio: bytes):
    """Decodifica WAV/WebM/Ogg/MP4 para `numpy.float32` mono a 16 kHz, só em memória."""
    try:
        import av
        import numpy as np
    except ImportError as err:
        raise AudioError("O decodificador de áudio (PyAV) não está instalado neste servidor.", "DECODER_UNAVAILABLE", 503) from err
    try:
        partes = []
        with av.open(io.BytesIO(audio), mode="r") as container:
            if not container.streams.audio:
                raise AudioError("O arquivo não tem faixa de áudio.", "CORRUPT_AUDIO", 422)
            reamostrador = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for quadro in container.decode(audio=0):
                for saida in reamostrador.resample(quadro):
                    partes.append(saida.to_ndarray().reshape(-1))
            for saida in reamostrador.resample(None):
                partes.append(saida.to_ndarray().reshape(-1))
    except AudioError:
        raise
    except Exception as err:
        raise AudioError("Não foi possível decodificar o áudio. Grave de novo ou use outro arquivo.", "CORRUPT_AUDIO", 422) from err
    if not partes:
        raise AudioError("Não foi possível decodificar o áudio. Grave de novo ou use outro arquivo.", "CORRUPT_AUDIO", 422)
    return np.concatenate(partes).astype(np.float32) / 32768.0


class Transcritor(Protocol):
    def transcrever(self, audio: bytes, idioma: str = "pt") -> str: ...


class FasterWhisperTranscritor:
    def __init__(
        self,
        modelo: str | None = None,
        dispositivo: str | None = None,
        tipo_computacao: str | None = None,
        somente_local: bool | None = None,
    ) -> None:
        env = os.environ
        self.modelo = modelo or env.get("IRIS_STT_MODEL", "small")
        self.dispositivo = dispositivo or env.get("IRIS_STT_DEVICE", "cpu")
        self.tipo_computacao = tipo_computacao or env.get("IRIS_STT_COMPUTE", "int8")
        self.somente_local = env.get("IRIS_STT_OFFLINE", "0") == "1" if somente_local is None else somente_local
        self._whisper = None
        self._trava = threading.Lock()

    def _carregar(self):
        with self._trava:
            if self._whisper is not None:
                return self._whisper
            try:
                from faster_whisper import WhisperModel
            except ImportError as err:
                raise AudioError(
                    "A transcrição por voz não está instalada neste servidor (pip install faster-whisper).",
                    "STT_UNAVAILABLE",
                    503,
                ) from err
            try:
                self._whisper = WhisperModel(
                    self.modelo,
                    device=self.dispositivo,
                    compute_type=self.tipo_computacao,
                    local_files_only=self.somente_local,
                )
            except Exception as err:  # modelo ausente/sem rede para baixar, memória insuficiente etc.
                raise AudioError(
                    f"Não foi possível carregar o modelo de transcrição '{self.modelo}' (confira o download do modelo).",
                    "STT_MODEL_UNAVAILABLE",
                    503,
                ) from err
            return self._whisper

    def transcrever(self, audio: bytes, idioma: str = "pt") -> str:
        modelo = self._carregar()
        amostras = decodificar_para_amostras(audio)
        try:
            segmentos, _info = modelo.transcribe(
                amostras, language=idioma, vad_filter=True, condition_on_previous_text=False
            )
            return " ".join(s.text.strip() for s in segmentos).strip()
        except AudioError:
            raise
        except Exception as err:
            raise AudioError("Falha ao transcrever o áudio. Grave de novo ou use outro arquivo.", "TRANSCRIPTION_FAILED", 422) from err


_padrao: Transcritor | None = None
_trava_padrao = threading.Lock()


def definir_transcritor(transcritor: Transcritor | None) -> None:
    """Troca o motor (testes ou outro STT). `None` volta ao faster-whisper."""
    global _padrao
    with _trava_padrao:
        _padrao = transcritor


def obter_transcritor() -> Transcritor:
    global _padrao
    with _trava_padrao:
        if _padrao is None:
            _padrao = FasterWhisperTranscritor()
        return _padrao
