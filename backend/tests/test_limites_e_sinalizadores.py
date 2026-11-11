"""Limites de entrada e sinalizadores de metadados (História 1.1.1 / RF-01 e RNF-02).

Cada regra é testada nos dois lados da fronteira: o último valor aceito e o primeiro
valor recusado. Um teste com valor muito abaixo ou muito acima do limite continua
passando se o limite for alterado por engano; o teste na fronteira não.

Regras cobertas:
- tamanho máximo do arquivo (10 MB);
- mínimo de 50 caracteres e máximo da janela de contexto (100.000 caracteres);
- estimativa de tokens dos metadados;
- sinalizador `sanitized` e contagem `pii_removed_count`;
- texto vazio ou só com espaços.
"""
from __future__ import annotations

import unittest

from iris.api.routes.materials import (
    decompose_material_service,
    process_material_file_service,
    process_material_text_service,
)
from iris.schemas.materials import (
    MAX_FILE_SIZE_BYTES,
    MAX_SAFE_CONTEXT_CHARS,
    MIN_MATERIAL_CHARS,
    MaterialMetadata,
    MaterialTextInput,
    MaterialValidationError,
    validate_file_size_limit,
    validate_material_content,
)

SEM_DADO_PESSOAL = "Explique com suas palavras como a água evapora e forma as nuvens no céu."
COM_DADO_PESSOAL = SEM_DADO_PESSOAL + " Dúvidas: prof@escola.com ou CPF 123.456.789-09."


class TestLimitesDocumentados(unittest.TestCase):
    def test_valores_do_requisito(self) -> None:
        """RF-01: 10 MB por arquivo, mínimo de 50 e máximo de 100.000 caracteres."""
        self.assertEqual(MAX_FILE_SIZE_BYTES, 10 * 1024 * 1024)
        self.assertEqual(MIN_MATERIAL_CHARS, 50)
        self.assertEqual(MAX_SAFE_CONTEXT_CHARS, 100_000)


class TestLimiteDeTamanhoDoArquivo(unittest.TestCase):
    def test_arquivo_exatamente_no_limite_e_aceito(self) -> None:
        self.assertEqual(validate_file_size_limit(b"a" * MAX_FILE_SIZE_BYTES), MAX_FILE_SIZE_BYTES)

    def test_um_byte_acima_do_limite_e_recusado(self) -> None:
        with self.assertRaises(MaterialValidationError) as ctx:
            validate_file_size_limit(b"a" * (MAX_FILE_SIZE_BYTES + 1))
        self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")
        self.assertEqual(ctx.exception.field, "file")

    def test_conteudo_ausente_tem_tamanho_zero(self) -> None:
        self.assertEqual(validate_file_size_limit(b""), 0)


class TestLimitesDeTamanhoDoTexto(unittest.TestCase):
    def test_exatamente_50_caracteres_e_aceito(self) -> None:
        chars, palavras = validate_material_content("a" * 50)
        self.assertEqual((chars, palavras), (50, 1))

    def test_49_caracteres_e_recusado(self) -> None:
        with self.assertRaises(MaterialValidationError) as ctx:
            validate_material_content("a" * 49)
        self.assertEqual(ctx.exception.code, "TEXT_TOO_SHORT")

    def test_espacos_nas_bordas_nao_contam_para_o_minimo(self) -> None:
        with self.assertRaises(MaterialValidationError):
            validate_material_content(" " * 30 + "a" * 49 + " " * 30)

    def test_exatamente_na_janela_de_contexto_e_aceito(self) -> None:
        chars, _ = validate_material_content("a" * MAX_SAFE_CONTEXT_CHARS)
        self.assertEqual(chars, MAX_SAFE_CONTEXT_CHARS)

    def test_um_caractere_acima_da_janela_e_recusado(self) -> None:
        with self.assertRaises(MaterialValidationError) as ctx:
            validate_material_content("a" * (MAX_SAFE_CONTEXT_CHARS + 1))
        self.assertEqual(ctx.exception.code, "CONTEXT_WINDOW_EXCEEDED")


class TestEstimativaDeTokens(unittest.TestCase):
    def _metadados(self, char_count: int, **extras: int) -> MaterialMetadata:
        return MaterialMetadata(
            source_type="text", char_count=char_count, word_count=1, sanitized=False, pii_removed_count=0, **extras
        )

    def test_um_token_a_cada_quatro_caracteres(self) -> None:
        self.assertEqual(self._metadados(400).estimated_tokens, 100)

    def test_texto_minusculo_estima_ao_menos_um_token(self) -> None:
        self.assertEqual(self._metadados(1).estimated_tokens, 1)

    def test_sem_caracteres_nao_ha_tokens(self) -> None:
        self.assertEqual(self._metadados(0).estimated_tokens, 0)

    def test_valor_informado_nao_e_sobrescrito(self) -> None:
        self.assertEqual(self._metadados(400, estimated_tokens=7).estimated_tokens, 7)


class TestSinalizadorDeDadosPessoais(unittest.TestCase):
    """O campo `sanitized` informa ao docente se algo foi removido do material."""

    def test_texto_sem_dado_pessoal_nao_e_marcado(self) -> None:
        meta = process_material_text_service(SEM_DADO_PESSOAL).metadata
        self.assertFalse(meta.sanitized)
        self.assertEqual(meta.pii_removed_count, 0)

    def test_texto_com_dado_pessoal_e_marcado_e_contado(self) -> None:
        resposta = process_material_text_service(COM_DADO_PESSOAL)
        self.assertTrue(resposta.metadata.sanitized)
        self.assertEqual(resposta.metadata.pii_removed_count, 2)
        self.assertNotIn("prof@escola.com", resposta.raw_text)
        self.assertNotIn("123.456.789-09", resposta.raw_text)

    def test_arquivo_sem_dado_pessoal_nao_e_marcado(self) -> None:
        meta = process_material_file_service("aula.txt", SEM_DADO_PESSOAL.encode("utf-8")).metadata
        self.assertFalse(meta.sanitized)
        self.assertEqual(meta.pii_removed_count, 0)

    def test_arquivo_com_dado_pessoal_e_marcado_e_contado(self) -> None:
        resposta = process_material_file_service("aula.txt", COM_DADO_PESSOAL.encode("utf-8"))
        self.assertTrue(resposta.metadata.sanitized)
        self.assertEqual(resposta.metadata.pii_removed_count, 2)
        self.assertNotIn("prof@escola.com", resposta.raw_text)

    def test_decomposicao_nao_devolve_dado_pessoal(self) -> None:
        estrutura = decompose_material_service("1. " + COM_DADO_PESSOAL)
        self.assertNotIn("123.456.789-09", str(estrutura.model_dump()))


class TestTextoVazio(unittest.TestCase):
    def test_servico_recusa_texto_vazio_e_so_com_espacos(self) -> None:
        for texto in ("", "   \n\t  "):
            with self.subTest(texto=repr(texto)):
                with self.assertRaises(MaterialValidationError) as ctx:
                    process_material_text_service(texto)
                self.assertEqual(ctx.exception.code, "EMPTY_TEXT")

    def test_servico_recusa_valor_que_nao_e_texto(self) -> None:
        with self.assertRaises(MaterialValidationError) as ctx:
            process_material_text_service(None)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.code, "EMPTY_TEXT")

    def test_contrato_de_entrada_recusa_texto_so_com_espacos(self) -> None:
        with self.assertRaises(ValueError):
            MaterialTextInput(text="   \n\t  ")

    def test_arquivo_sem_nome_e_recusado(self) -> None:
        from iris.parsers.document_extractor import UnsupportedFileFormatError

        with self.assertRaises(UnsupportedFileFormatError) as ctx:
            process_material_file_service("", SEM_DADO_PESSOAL.encode("utf-8"))
        self.assertEqual(ctx.exception.code, "MISSING_FILENAME")


if __name__ == "__main__":
    unittest.main()
