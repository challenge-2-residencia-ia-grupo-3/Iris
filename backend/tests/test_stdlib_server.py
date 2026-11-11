"""Testes do servidor HTTP de reserva (`run_stdlib_server`), usado quando FastAPI/uvicorn não estão ativos."""
import contextlib
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest.mock import patch

from iris import main

TEXTO_VALIDO = (
    "Prova de Ciências do 6º ano\n"
    "1. Explique o que é fotossíntese.\n"
    "2. Cite dois exemplos de seres produtores."
)


class TestServidorDeReserva(unittest.TestCase):
    """Sobe o handler do servidor de reserva em porta local livre e envia requisições reais."""

    @classmethod
    def setUpClass(cls) -> None:
        capturado = {}

        class ServidorCapturado:
            def __init__(self, endereco, handler):
                capturado["handler"] = handler

            def serve_forever(self) -> None:
                return None

        with patch("http.server.HTTPServer", ServidorCapturado), contextlib.redirect_stdout(io.StringIO()):
            main.run_stdlib_server()

        handler = capturado["handler"]
        handler.log_message = lambda *args, **kwargs: None
        cls.servidor = HTTPServer(("127.0.0.1", 0), handler)
        cls.base = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        cls.thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.thread.join(timeout=5)

    def _post(self, caminho: str, corpo: bytes) -> tuple[int, dict]:
        req = urllib.request.Request(
            self.base + caminho, data=corpo, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def test_corpo_que_nao_e_json_devolve_400(self) -> None:
        for caminho in ("/api/v1/materials/text", "/api/v1/materials/decompose", "/api/v1/materials/organize-prose"):
            with self.subTest(caminho=caminho):
                status, corpo = self._post(caminho, b"isto nao e json")
                self.assertEqual(status, 400)
                self.assertEqual(corpo["detail"]["code"], "INVALID_JSON")
                self.assertEqual(corpo["detail"]["field"], "body")

    def test_json_que_nao_e_objeto_devolve_400(self) -> None:
        status, corpo = self._post("/api/v1/materials/text", b'["texto"]')
        self.assertEqual(status, 400)
        self.assertEqual(corpo["detail"]["code"], "INVALID_JSON")

    def test_bytes_fora_do_utf8_devolvem_400(self) -> None:
        status, corpo = self._post("/api/v1/materials/text", b"\xff\xfe\xfa")
        self.assertEqual(status, 400)
        self.assertEqual(corpo["detail"]["code"], "INVALID_JSON")

    def test_servidor_continua_respondendo_apos_corpo_invalido(self) -> None:
        self._post("/api/v1/materials/text", b"{")
        status, corpo = self._post(
            "/api/v1/materials/text", json.dumps({"text": TEXTO_VALIDO}).encode("utf-8")
        )
        self.assertEqual(status, 200)
        self.assertEqual(corpo["raw_text"], TEXTO_VALIDO)

    def test_texto_curto_continua_devolvendo_422(self) -> None:
        status, corpo = self._post("/api/v1/materials/text", json.dumps({"text": "Muito curto."}).encode("utf-8"))
        self.assertEqual(status, 422)
        self.assertEqual(corpo["detail"]["code"], "TEXT_TOO_SHORT")


    def _upload(self, nome: str | None, conteudo: bytes, campo: str = "file") -> tuple[int, dict]:
        limite = "----limite-do-teste"
        arquivo = f'; filename="{nome}"' if nome is not None else ""
        corpo = (
            f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"{arquivo}\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + conteudo + f"\r\n--{limite}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            self.base + "/api/v1/materials/upload",
            data=corpo,
            headers={"Content-Type": f"multipart/form-data; boundary={limite}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def test_upload_de_txt_por_multipart(self) -> None:
        status, corpo = self._upload("prova.txt", TEXTO_VALIDO.encode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(corpo["raw_text"], TEXTO_VALIDO)
        self.assertEqual(corpo["metadata"]["filename"], "prova.txt")
        self.assertEqual(corpo["metadata"]["source_type"], "txt")

    def test_upload_entrega_os_bytes_do_arquivo_sem_alteracao(self) -> None:
        enviado = bytes(range(256)) * 3 + b"\r\n--\r\n\n\r" + bytes(range(255, -1, -1))
        recebido = {}

        def servico(nome, conteudo):
            recebido["nome"], recebido["conteudo"] = nome, conteudo
            raise RuntimeError("interrompido pelo teste")

        with patch("iris.api.routes.materials.process_material_file_service", side_effect=servico):
            status, corpo = self._upload("binario.pdf", enviado)

        self.assertEqual(recebido["nome"], "binario.pdf")
        self.assertEqual(recebido["conteudo"], enviado)
        self.assertEqual(status, 500)
        self.assertEqual(corpo["detail"]["code"], "INTERNAL_ERROR")

    def test_upload_de_formato_nao_suportado_devolve_400(self) -> None:
        status, corpo = self._upload("virus.exe", b"MZ")
        self.assertEqual(status, 400)
        self.assertEqual(corpo["detail"]["code"], "UNSUPPORTED_FORMAT")
        self.assertEqual(corpo["detail"]["field"], "file")

    def test_upload_de_arquivo_vazio_e_de_texto_curto_devolvem_422(self) -> None:
        for conteudo, codigo in ((b"", "EMPTY_FILE"), (b"Muito curto.", "TEXT_TOO_SHORT")):
            with self.subTest(codigo=codigo):
                status, corpo = self._upload("prova.txt", conteudo)
                self.assertEqual(status, 422)
                self.assertEqual(corpo["detail"]["code"], codigo)

    def test_upload_sem_o_campo_file_devolve_422(self) -> None:
        status, corpo = self._upload("prova.txt", TEXTO_VALIDO.encode("utf-8"), campo="outro")
        self.assertEqual(status, 422)
        self.assertEqual(corpo["detail"]["code"], "MISSING_FILE")

    def test_upload_com_corpo_que_nao_e_multipart_devolve_422(self) -> None:
        status, corpo = self._post("/api/v1/materials/upload", json.dumps({"text": TEXTO_VALIDO}).encode("utf-8"))
        self.assertEqual(status, 422)
        self.assertEqual(corpo["detail"]["code"], "MISSING_FILE")

    def test_servidor_continua_respondendo_apos_upload(self) -> None:
        self._upload("virus.exe", b"MZ")
        status, _ = self._post("/api/v1/materials/text", json.dumps({"text": TEXTO_VALIDO}).encode("utf-8"))
        self.assertEqual(status, 200)

if __name__ == "__main__":
    unittest.main()
