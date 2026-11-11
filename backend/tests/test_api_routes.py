"""Testes das rotas HTTP de materiais (Histórias 1.1.1 e 1.1.2).

Os testes de `test_materials.py` e `test_structural_decomposer.py` exercitam os serviços.
Este arquivo exercita a camada acima deles: os handlers FastAPI e a tradução de cada
erro de domínio em código HTTP (400, 422 e 500).

Duas formas de chamada:
1. Handler direto com `asyncio.run`, que não depende de cliente HTTP;
2. `TestClient` sobre `create_app()`, que percorre roteamento, validação do corpo e
   multipart. Depende de `httpx` (grupo `dev`) e é pulado quando ele não está instalado.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import unittest
from unittest.mock import patch

from iris.api.routes import materials as rotas
from iris.schemas.materials import MAX_FILE_SIZE_BYTES, MaterialTextInput

FASTAPI_DISPONIVEL = rotas.router is not None
HTTPX_DISPONIVEL = importlib.util.find_spec("httpx") is not None

TEXTO_VALIDO = (
    "Prova de Ciências do 6º ano\n"
    "1. Explique o que é fotossíntese.\n"
    "2. Cite dois exemplos de seres produtores."
)
TEXTO_CURTO = "Muito curto."


def _arquivo(nome: str | None, conteudo: bytes):
    """Monta o objeto de upload que o FastAPI entrega ao handler."""
    from starlette.datastructures import UploadFile

    return UploadFile(file=io.BytesIO(conteudo), filename=nome)


@unittest.skipUnless(FASTAPI_DISPONIVEL, "FastAPI não instalado")
class TestHandlersDeMateriais(unittest.TestCase):
    """Chama os handlers diretamente e confere resposta e código de erro."""

    def _erro_http(self, corrotina):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(corrotina)
        return ctx.exception

    def test_falha_inesperada_no_texto_vira_500(self) -> None:
        with patch.object(rotas, "process_material_text_service", side_effect=RuntimeError("falha simulada")):
            erro = self._erro_http(rotas.upload_material_text(MaterialTextInput(text=TEXTO_VALIDO)))
        self.assertEqual(erro.status_code, 500)
        self.assertEqual(erro.detail["code"], "INTERNAL_ERROR")

    def test_upload_sem_nome_de_arquivo_vira_400_por_formato(self) -> None:
        erro = self._erro_http(rotas.upload_material_file(_arquivo(None, b"conteudo")))
        self.assertEqual(erro.status_code, 400)
        self.assertEqual(erro.detail["code"], "UNSUPPORTED_FORMAT")

    def test_upload_de_arquivo_vazio_vira_422(self) -> None:
        erro = self._erro_http(rotas.upload_material_file(_arquivo("vazio.txt", b"")))
        self.assertEqual(erro.status_code, 422)
        self.assertEqual(erro.detail["code"], "EMPTY_FILE")

    def test_upload_acima_do_limite_vira_422(self) -> None:
        grande = b"a" * (MAX_FILE_SIZE_BYTES + 1)
        erro = self._erro_http(rotas.upload_material_file(_arquivo("grande.txt", grande)))
        self.assertEqual(erro.status_code, 422)
        self.assertEqual(erro.detail["code"], "FILE_TOO_LARGE")
        self.assertEqual(erro.detail["field"], "file")

    def test_upload_com_texto_curto_vira_422(self) -> None:
        erro = self._erro_http(rotas.upload_material_file(_arquivo("curto.txt", TEXTO_CURTO.encode("utf-8"))))
        self.assertEqual(erro.status_code, 422)
        self.assertEqual(erro.detail["code"], "TEXT_TOO_SHORT")

    def test_falha_inesperada_no_upload_vira_500(self) -> None:
        with patch.object(rotas, "process_material_file_service", side_effect=RuntimeError("falha simulada")):
            erro = self._erro_http(rotas.upload_material_file(_arquivo("prova.txt", TEXTO_VALIDO.encode("utf-8"))))
        self.assertEqual(erro.status_code, 500)
        self.assertEqual(erro.detail["code"], "INTERNAL_ERROR")

    def test_falha_inesperada_na_decomposicao_vira_500(self) -> None:
        with patch.object(rotas, "decompose_material_service", side_effect=RuntimeError("falha simulada")):
            erro = self._erro_http(rotas.decompose_material_endpoint(MaterialTextInput(text=TEXTO_VALIDO)))
        self.assertEqual(erro.status_code, 500)
        self.assertEqual(erro.detail["code"], "INTERNAL_ERROR")


@unittest.skipUnless(FASTAPI_DISPONIVEL and HTTPX_DISPONIVEL, "FastAPI ou httpx não instalado")
class TestRotasPorHTTP(unittest.TestCase):
    """Percorre o caminho completo: URL, corpo JSON ou multipart, código e corpo da resposta."""

    @classmethod
    def setUpClass(cls) -> None:
        import warnings

        from iris.main import create_app

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi.testclient import TestClient

            cls.cliente = TestClient(create_app())

    def test_rotas_de_materiais_estao_publicadas(self) -> None:
        caminhos = self.cliente.app.openapi()["paths"]
        for caminho in ("/api/v1/materials/text", "/api/v1/materials/upload", "/api/v1/materials/decompose"):
            self.assertIn(caminho, caminhos)
            self.assertIn("post", caminhos[caminho])

    def test_post_de_texto_valido(self) -> None:
        r = self.cliente.post("/api/v1/materials/text", json={"text": TEXTO_VALIDO})
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertEqual(corpo["status"], "success")
        self.assertEqual(corpo["raw_text"], TEXTO_VALIDO)
        self.assertEqual(corpo["metadata"]["source_type"], "text")
        self.assertEqual(corpo["metadata"]["char_count"], len(TEXTO_VALIDO))
        self.assertIsNone(corpo["metadata"]["filename"])

    def test_post_de_texto_curto(self) -> None:
        r = self.cliente.post("/api/v1/materials/text", json={"text": TEXTO_CURTO})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "TEXT_TOO_SHORT")

    def test_post_sem_o_campo_text(self) -> None:
        r = self.cliente.post("/api/v1/materials/text", json={})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"][0]["loc"], ["body", "text"])

    def test_post_de_texto_so_com_espacos(self) -> None:
        r = self.cliente.post("/api/v1/materials/text", json={"text": "   \n\t "})
        self.assertEqual(r.status_code, 422)

    def test_upload_de_txt_por_multipart(self) -> None:
        r = self.cliente.post(
            "/api/v1/materials/upload",
            files={"file": ("prova.txt", TEXTO_VALIDO.encode("utf-8"), "text/plain")},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["metadata"]["filename"], "prova.txt")
        self.assertEqual(r.json()["metadata"]["source_type"], "txt")
        self.assertEqual(r.json()["raw_text"], TEXTO_VALIDO)

    def test_upload_de_formato_nao_suportado(self) -> None:
        r = self.cliente.post("/api/v1/materials/upload", files={"file": ("virus.exe", b"MZ")})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "UNSUPPORTED_FORMAT")
        self.assertEqual(r.json()["detail"]["field"], "file")

    def test_upload_sem_arquivo(self) -> None:
        r = self.cliente.post("/api/v1/materials/upload")
        self.assertEqual(r.status_code, 422)

    def test_decomposicao_por_http(self) -> None:
        r = self.cliente.post("/api/v1/materials/decompose", json={"text": TEXTO_VALIDO})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total_questions"], 2)
        self.assertEqual([q["original_number"] for q in r.json()["questions"]], ["1", "2"])
        self.assertIn("fotossíntese", r.json()["questions"][0]["statement"])


if __name__ == "__main__":
    unittest.main()
