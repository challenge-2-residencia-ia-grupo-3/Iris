"""Validação do áudio docente: formato pelo conteúdo, tamanho e duração máxima de 60 s (RF-03).

Tudo acontece em memória (`bytes`): o áudio nunca vai a disco (RNF-01). O formato é decidido pelos primeiros
bytes do arquivo, não pelo nome nem pelo Content-Type enviados pelo cliente. A duração do WAV vem do cabeçalho
E do tamanho real dos dados (o maior dos dois), para um cabeçalho adulterado não esconder um áudio longo. Para
WebM/Ogg/MP4 a duração é medida percorrendo os pacotes (sem decodificar), pois o WebM gravado pelo navegador
(MediaRecorder) costuma vir sem duração no cabeçalho.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

from iris.audio.erros import AudioError

MAX_SEGUNDOS = 60.0
TOLERANCIA_SEGUNDOS = 1.0  # o gravador do navegador para em 60,0x s; acima de 61 s já é outro áudio
MIN_SEGUNDOS = 0.5
MAX_BYTES = 12 * 1024 * 1024  # 60 s de WAV estéreo a 44,1 kHz ≈ 10,6 MB
FORMATOS = ("wav", "webm", "ogg", "mp4")


@dataclass(frozen=True)
class MetaAudio:
    formato: str
    duracao_segundos: float
    tamanho_bytes: int


def detectar_formato(dados: bytes) -> str | None:
    if len(dados) >= 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WAVE":
        return "wav"
    if dados[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if dados[:4] == b"OggS":
        return "ogg"
    if len(dados) >= 12 and dados[4:8] == b"ftyp":
        return "mp4"
    return None


def _duracao_wav(dados: bytes) -> float:
    try:
        with wave.open(io.BytesIO(dados)) as w:
            taxa, canais, largura, quadros = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    except (wave.Error, EOFError) as err:
        raise AudioError(
            "Não foi possível ler o WAV. Use WAV PCM, WebM, Ogg ou MP4/M4A.", "CORRUPT_AUDIO", 422
        ) from err
    if taxa <= 0 or canais <= 0 or largura <= 0:
        raise AudioError("O cabeçalho do WAV é inválido.", "CORRUPT_AUDIO", 422)
    pelo_cabecalho = quadros / taxa
    pelo_tamanho = max(len(dados) - 44, 0) / (taxa * canais * largura)
    return max(pelo_cabecalho, pelo_tamanho)


def _duracao_container(dados: bytes) -> float:
    try:
        import av  # PyAV: vem junto do faster-whisper
    except ImportError as err:
        raise AudioError(
            "O decodificador de áudio não está instalado neste servidor (instale faster-whisper) "
            "ou envie o áudio em WAV.",
            "DECODER_UNAVAILABLE",
            503,
        ) from err
    try:
        with av.open(io.BytesIO(dados)) as c:
            audio = next((s for s in c.streams if s.type == "audio"), None)
            if audio is None:
                raise AudioError("O arquivo não tem trilha de áudio.", "CORRUPT_AUDIO", 422)
            fim = 0.0
            for pacote in c.demux(audio):
                if pacote.pts is None or pacote.time_base is None:
                    continue
                fim = max(fim, float((pacote.pts + (pacote.duration or 0)) * pacote.time_base))
            return fim
    except AudioError:
        raise
    except Exception as err:  # av.error.FFmpegError e afins: arquivo corrompido ou truncado
        raise AudioError("Não foi possível ler o áudio enviado. Grave de novo ou use outro arquivo.", "CORRUPT_AUDIO", 422) from err


def validar_audio(dados: bytes) -> MetaAudio:
    if not dados:
        raise AudioError("Nenhum áudio foi enviado.", "EMPTY_AUDIO", 422)
    if len(dados) > MAX_BYTES:
        raise AudioError(
            f"O arquivo passa de {MAX_BYTES // (1024 * 1024)} MB. O limite é de {int(MAX_SEGUNDOS)} segundos de áudio.",
            "AUDIO_TOO_LARGE",
            413,
        )
    formato = detectar_formato(dados)
    if formato is None:
        raise AudioError("Formato não aceito. Envie WAV, WebM, Ogg ou MP4/M4A.", "UNSUPPORTED_AUDIO", 415)
    duracao = _duracao_wav(dados) if formato == "wav" else _duracao_container(dados)
    if duracao > MAX_SEGUNDOS + TOLERANCIA_SEGUNDOS:
        raise AudioError(
            f"O áudio tem {duracao:.0f} segundos. O limite é de {int(MAX_SEGUNDOS)} segundos.", "AUDIO_TOO_LONG", 422
        )
    if duracao < MIN_SEGUNDOS:
        raise AudioError("O áudio é curto demais. Grave pelo menos um segundo.", "AUDIO_TOO_SHORT", 422)
    return MetaAudio(formato=formato, duracao_segundos=round(duracao, 2), tamanho_bytes=len(dados))
