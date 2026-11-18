"""Testes de regressão dos pontos levantados na revisão do PR #110 (observação pedagógica por voz)."""
from __future__ import annotations

import io
import math
import struct
import tempfile
import unittest
import wave
from unittest import mock

from fastapi.testclient import TestClient

from iris.audio import transcricao
from iris.main import create_app


class _Falso:
    def transcrever(self, audio: bytes, idioma: str = "pt") -> str:
        return "Ele responde só a primeira parte da pergunta."


def _wav(segundos: float, taxa: int = 16000) -> bytes:
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 10))) for i in range(int(segundos * taxa))))
    return saida.getvalue()


class TestAudioNuncaVaiADisco(unittest.TestCase):
    def setUp(self) -> None:
        transcricao.definir_transcritor(_Falso())
        self.cliente = TestClient(create_app())

    def tearDown(self) -> None:
        transcricao.definir_transcritor(None)

    def test_wav_de_59_segundos_fica_em_memoria(self):
        dados = _wav(59)  # ~1,9 MB: o UploadFile padrão gravaria em arquivo temporário (limite de 1 MB)
        self.assertGreater(len(dados), 1024 * 1024)
        original = tempfile.SpooledTemporaryFile.rollover
        with mock.patch.object(tempfile.SpooledTemporaryFile, "rollover", autospec=True, side_effect=original) as gravou:
            r = self.cliente.post("/api/v1/audio/transcribe", files={"file": ("o.wav", dados, "audio/wav")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(gravou.call_count, 0, "o áudio foi gravado em arquivo temporário")
        self.assertIn("sobrecarga_memoria_trabalho_comandos_multiplos", [s["id_caracteristica"] for s in r.json()["sugestoes"]])

    def test_corpo_acima_do_limite_e_recusado_sem_ir_a_disco(self):
        enorme = b"RIFF" + b"\x00" * (13 * 1024 * 1024)
        original = tempfile.SpooledTemporaryFile.rollover
        with mock.patch.object(tempfile.SpooledTemporaryFile, "rollover", autospec=True, side_effect=original) as gravou:
            r = self.cliente.post("/api/v1/audio/transcribe", files={"file": ("o.wav", enorme, "audio/wav")})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["detail"]["code"], "AUDIO_TOO_LARGE")
        self.assertEqual(gravou.call_count, 0)

    def test_sem_campo_file_e_recusado(self):
        r = self.cliente.post("/api/v1/audio/transcribe", files={"outro": ("o.wav", _wav(2), "audio/wav")})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_corpo_que_nao_e_formulario_e_recusado(self):
        r = self.cliente.post("/api/v1/audio/transcribe", content=b"abc", headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.cliente.post("/api/v1/audio/transcribe").status_code, 422)  # sem corpo e sem tipo


if __name__ == "__main__":
    unittest.main()
