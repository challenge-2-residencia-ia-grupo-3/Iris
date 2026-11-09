"""Testes unitários e de integração da História 1.1.1 (Issue #4).

Cobre:
- RF-01: Inserção de conteúdo por digitação direta e upload de documentos (.pdf, .docx, .txt).
- RNF-02: Sanitização preventiva de PII (Zero-Retention Scrubber).
- RNF-08: Orçamento de tokens e validação de tamanho (mínimo 50 caracteres e limite seguro de 2.000 palavras).
- Preservação da acentuação da língua portuguesa (UTF-8).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris.api.routes.materials import (
    process_material_file_service,
    process_material_text_service,
)
from iris.parsers.document_extractor import (
    DocumentParsingError,
    UnsupportedFileFormatError,
    extract_text_from_docx,
    extract_text_from_file,
    extract_text_from_pdf,
    extract_text_from_txt,
    normalize_extracted_text,
)
from iris.schemas.materials import (
    MAX_FILE_SIZE_BYTES,
    MAX_SAFE_CONTEXT_CHARS,
    MIN_MATERIAL_CHARS,
    MaterialResponse,
    MaterialSourceType,
    MaterialValidationError,
    validate_file_size_limit,
    validate_material_content,
)
from iris.security.pii_scrubber import sanitize_pii


class TestMaterialParsersAndValidation(unittest.TestCase):
    """Bateria de testes para parsers de documentos e validações da História 1.1.1."""

    def test_normalize_extracted_text(self) -> None:
        """Deve normalizar quebras de linha Windows/Mac e colapsar linhas vazias redundantes."""
        raw = "Linha 1\r\n\r\n\r\n\r\nLinha 2\rLinha 3 com espaço\xa0não-quebrável   "
        expected = "Linha 1\n\nLinha 2\nLinha 3 com espaço não-quebrável"
        self.assertEqual(normalize_extracted_text(raw), expected)
        self.assertEqual(normalize_extracted_text(""), "")

    def test_extract_text_from_txt_utf8_with_portuguese_accents(self) -> None:
        """A extração de .txt em UTF-8 deve preservar acentos e cedilhas perfeitamente."""
        conteudo = (
            "Avaliação Bimestral de História e Geografia.\n"
            "Questão 1: Explique a importância da preservação das bacias hidrográficas "
            "e das matas ciliares para o equilíbrio ecológico da região Centro-Oeste."
        ).encode("utf-8")

        texto = extract_text_from_txt(conteudo)
        self.assertIn("Avaliação Bimestral", texto)
        self.assertIn("hidrográficas", texto)
        self.assertIn("Centro-Oeste", texto)

    def test_extract_text_from_txt_latin1_fallback(self) -> None:
        """Arquivos .txt criados no Windows brasileiro (Latin-1 / CP1252) devem sofrer fallback seguro."""
        conteudo = "Questão de Biologia: Ação das enzimas na digestão e absorção celular.".encode("latin-1")
        texto = extract_text_from_txt(conteudo)
        self.assertIn("Ação das enzimas", texto)
        self.assertIn("digestão e absorção", texto)

    def test_extract_text_from_txt_empty(self) -> None:
        """Arquivo .txt vazio deve lançar DocumentParsingError."""
        with self.assertRaises(DocumentParsingError) as ctx:
            extract_text_from_txt(b"")
        self.assertEqual(ctx.exception.code, "EMPTY_FILE")

    def test_extract_text_from_txt_only_whitespace(self) -> None:
        """Arquivo .txt apenas com espaços/quebras deve lançar DocumentParsingError."""
        with self.assertRaises(DocumentParsingError) as ctx:
            extract_text_from_txt(b"   \n\n  \t  \r\n ")
        self.assertEqual(ctx.exception.code, "NO_READABLE_TEXT")

    @patch("iris.parsers.document_extractor.fitz", create=True)
    def test_extract_text_from_pdf_success(self, mock_fitz: MagicMock) -> None:
        """Deve extrair texto de todas as páginas de um PDF utilizando PyMuPDF."""
        mock_doc = MagicMock()
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Página 1: Prova de Matemática - Ensino Fundamental II."
        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Página 2: Questão 5 sobre teorema de Pitágoras e trigonometria."
        mock_doc.__len__.return_value = 2
        mock_doc.__getitem__.side_effect = [mock_page1, mock_page2]
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            texto = extract_text_from_pdf(b"%PDF-1.4 dummy binary content")
            self.assertIn("Prova de Matemática", texto)
            self.assertIn("teorema de Pitágoras", texto)
            mock_doc.close.assert_called_once()

    @patch("iris.parsers.document_extractor.fitz", create=True)
    def test_extract_text_from_pdf_scanned_without_selectable_text(self, mock_fitz: MagicMock) -> None:
        """PDF sem camada de texto (imagem escaneada) deve lançar erro informativo sem acionar OCR."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "    "
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            with self.assertRaises(DocumentParsingError) as ctx:
                extract_text_from_pdf(b"%PDF-1.4 scanned content")
            self.assertEqual(ctx.exception.code, "NO_READABLE_TEXT")
            self.assertIn("texto selecionável", ctx.exception.message)

    @patch("iris.parsers.document_extractor.docx", create=True)
    def test_extract_text_from_docx_paragraphs_and_tables(self, mock_docx: MagicMock) -> None:
        """Deve extrair texto sequencialmente de parágrafos e células de tabelas em DOCX."""
        mock_doc = MagicMock()

        p1 = MagicMock()
        p1.text = "Atividade de Língua Portuguesa - 8º Ano."
        p2 = MagicMock()
        p2.text = "Leia a tirinha e responda às questões a seguir:"
        mock_doc.paragraphs = [p1, p2]

        cell1 = MagicMock()
        cell1.text = "Personagem A"
        cell2 = MagicMock()
        cell2.text = "Fala da personagem"
        row1 = MagicMock()
        row1.cells = [cell1, cell2]

        table1 = MagicMock()
        table1.rows = [row1]
        mock_doc.tables = [table1]

        mock_docx.Document.return_value = mock_doc

        with patch.dict("sys.modules", {"docx": mock_docx}):
            texto = extract_text_from_docx(b"PK dummy docx bytes")
            self.assertIn("Atividade de Língua Portuguesa", texto)
            self.assertIn("Personagem A | Fala da personagem", texto)

    def test_extract_text_from_file_unsupported_extension(self) -> None:
        """Formatos não suportados (.xlsx, .exe, .png) devem lançar UnsupportedFileFormatError."""
        with self.assertRaises(UnsupportedFileFormatError) as ctx:
            extract_text_from_file("prova.png", b"fake image bytes")
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_FORMAT")
        self.assertIn(".png", ctx.exception.message)


class TestPiiScrubber(unittest.TestCase):
    """Validação da sanitização preventiva de PII sob diretriz Zero-Retention (RNF-02)."""

    def test_sanitize_student_headers(self) -> None:
        """Cabeçalhos escolares com nomes de estudantes devem ser substituídos irreversivelmente."""
        entrada = (
            "Escola Estadual Tiradentes\n"
            "Aluno(a): Gabriel Silva de Oliveira\n"
            "Turma: 7º Ano B — Matrícula: 20241088\n"
            "Questão 1: Calcule a área de um círculo com raio de 5 cm."
        )
        sanitizado, total = sanitize_pii(entrada)
        self.assertGreaterEqual(total, 2)
        self.assertNotIn("Gabriel Silva de Oliveira", sanitizado)
        self.assertNotIn("20241088", sanitizado)
        self.assertIn("Aluno(a): [ESTUDANTE]", sanitizado)
        self.assertIn("[IDENTIFICADOR]", sanitizado)
        self.assertIn("Questão 1: Calcule a área", sanitizado)

    def test_sanitize_generic_name_header(self) -> None:
        """Padrão 'Nome: Fulano de Tal' em cabeçalho deve ser substituído por [ESTUDANTE]."""
        entrada = "Nome: Lucas Gabriel dos Santos\nData: 10/05/2024\nProva de Ciências."
        sanitizado, total = sanitize_pii(entrada)
        self.assertGreaterEqual(total, 1)
        self.assertNotIn("Lucas Gabriel dos Santos", sanitizado)
        self.assertIn("Nome: [ESTUDANTE]", sanitizado)

    def test_sanitize_civil_data_and_contacts(self) -> None:
        """CPFs, e-mails e telefones acidentais devem ser removidos."""
        entrada = (
            "Dúvidas entrar em contato com professor@escola.org ou (61) 98765-4321. "
            "CPF para nota: 123.456.789-00."
        )
        sanitizado, total = sanitize_pii(entrada)
        self.assertGreaterEqual(total, 3)
        self.assertNotIn("professor@escola.org", sanitizado)
        self.assertNotIn("98765-4321", sanitizado)
        self.assertNotIn("123.456.789-00", sanitizado)
        self.assertIn("[EMAIL]", sanitizado)
        self.assertIn("[TELEFONE]", sanitizado)
        self.assertIn("[CPF]", sanitizado)

    def test_zero_retention_guarantee(self) -> None:
        """A sanitização não deve retornar nenhum mapa ou dicionário de reidratação."""
        resultado = sanitize_pii("Aluno: Beatriz Ferreira Lima")
        self.assertIsInstance(resultado, tuple)
        self.assertEqual(len(resultado), 2)
        self.assertIsInstance(resultado[0], str)
        self.assertIsInstance(resultado[1], int)
        # Nenhuma estrutura reversível é gerada
        self.assertNotIn("Beatriz Ferreira Lima", resultado[0])


class TestContentValidationAndService(unittest.TestCase):
    """Validação dos critérios de negócio de tamanho (RF-01 / RNF-08) e execução dos serviços."""

    def test_validation_rejects_text_under_50_chars(self) -> None:
        """Texto com menos de 50 caracteres deve ser rejeitado com TEXT_TOO_SHORT."""
        texto_curto = "Enunciado com 27 caracteres."
        with self.assertRaises(MaterialValidationError) as ctx:
            validate_material_content(texto_curto)
        self.assertEqual(ctx.exception.code, "TEXT_TOO_SHORT")
        self.assertEqual(ctx.exception.field, "text")
        self.assertIn("no mínimo 50 caracteres", ctx.exception.message)

    def test_validation_accepts_minimum_valid_text(self) -> None:
        """Texto com 50 caracteres exatos deve ser aceito com sucesso."""
        texto_minimo = "A" * 50
        chars, words = validate_material_content(texto_minimo)
        self.assertEqual(chars, 50)
        self.assertEqual(words, 1)

    def test_validation_has_no_fixed_word_limit(self) -> None:
        """Texto com mais de 2.000 palavras deve ser aceito desde que dentro da janela de contexto segura."""
        texto_longo = "questão " * 2500
        chars, words = validate_material_content(texto_longo)
        self.assertEqual(words, 2500)
        self.assertGreater(chars, MIN_MATERIAL_CHARS)
        self.assertLessEqual(chars, MAX_SAFE_CONTEXT_CHARS)

    def test_validation_rejects_context_window_exceeded(self) -> None:
        """Texto que ultrapassa a capacidade segura da janela de contexto da IA deve ser rejeitado."""
        texto_excessivo = "A" * (MAX_SAFE_CONTEXT_CHARS + 10)
        with self.assertRaises(MaterialValidationError) as ctx:
            validate_material_content(texto_excessivo)
        self.assertEqual(ctx.exception.code, "CONTEXT_WINDOW_EXCEEDED")
        self.assertIn("capacidade segura de processamento", ctx.exception.message)

    def test_validation_rejects_file_too_large(self) -> None:
        """Arquivo que excede MAX_FILE_SIZE_BYTES deve ser rejeitado com FILE_TOO_LARGE."""
        with self.assertRaises(MaterialValidationError) as ctx:
            validate_file_size_limit(b"x" * 1024, max_bytes=512)
        self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")
        self.assertEqual(ctx.exception.field, "file")

    def test_process_material_text_service_success(self) -> None:
        """O serviço process_material_text_service deve sanitizar PII e validar limites com sucesso."""
        texto_original = (
            "Escola Municipal Cecília Meireles\n"
            "Aluno: Pedro Henrique Souza\n"
            "Atividade de Geografia: O processo de urbanização brasileiro no século XX "
            "e a formação das principais regiões metropolitanas do Sudeste e Sul."
        )
        response = process_material_text_service(texto_original)
        self.assertIsInstance(response, MaterialResponse)
        self.assertEqual(response.status, "success")
        self.assertEqual(response.metadata.source_type, MaterialSourceType.TEXT.value)
        self.assertTrue(response.metadata.sanitized)
        self.assertGreaterEqual(response.metadata.pii_removed_count, 1)
        self.assertNotIn("Pedro Henrique Souza", response.raw_text)
        self.assertIn("[ESTUDANTE]", response.raw_text)
        self.assertGreaterEqual(response.metadata.char_count, MIN_MATERIAL_CHARS)
        self.assertGreater(response.metadata.estimated_tokens, 0)

    def test_process_material_file_service_txt_success(self) -> None:
        """O serviço process_material_file_service deve processar arquivo .txt com sanitização e validação."""
        conteudo_txt = (
            "Avaliação Trimestral de Ciências Naturais.\n"
            "Discente: Fernanda Ribeiro Dias\n"
            "Descreva os principais ciclos biogeoquímicos (água, carbono e nitrogênio) "
            "e suas interações com a biosfera e a atmosfera terrestre."
        ).encode("utf-8")

        response = process_material_file_service("prova_ciencias.txt", conteudo_txt)
        self.assertEqual(response.status, "success")
        self.assertEqual(response.metadata.source_type, "txt")
        self.assertEqual(response.metadata.filename, "prova_ciencias.txt")
        self.assertNotIn("Fernanda Ribeiro Dias", response.raw_text)
        self.assertIn("[ESTUDANTE]", response.raw_text)

    def test_process_material_file_service_unsupported_extension(self) -> None:
        """Upload de extensão não autorizada deve lançar UnsupportedFileFormatError."""
        with self.assertRaises(UnsupportedFileFormatError):
            process_material_file_service("roteiro.pdf.exe", b"binario malicioso")

    def test_extract_text_from_file_empty_files(self) -> None:
        """Arquivos vazios de qualquer extensão suportada devem lançar EMPTY_FILE."""
        for ext in [".txt", ".pdf", ".docx"]:
            with self.assertRaises(DocumentParsingError) as ctx:
                extract_text_from_file(f"atividade{ext}", b"")
            self.assertEqual(ctx.exception.code, "EMPTY_FILE")

    def test_pii_scrubber_complete_school_header(self) -> None:
        """Deve sanitizar todos os dados pessoais de um cabeçalho completo de prova escolar."""
        cabecalho = (
            "Colégio Municipal Paulo Freire\n"
            "Nome do Estudante: Juliana Maria de Medeiros\n"
            "Professor(a): Roberto Carlos dos Passos\n"
            "Turma: 9º Ano A | R.A.: 98765432-1\n"
            "Contato da secretaria: secretaria@paulofreire.edu.br ou (11) 98765-4321\n"
            "CPF do responsável: 999.888.777-66\n"
            "Instruções: Leia com atenção todas as 5 questões a seguir antes de responder."
        )
        sanitizado, total = sanitize_pii(cabecalho)
        self.assertGreaterEqual(total, 6)
        self.assertNotIn("Juliana Maria de Medeiros", sanitizado)
        self.assertNotIn("Roberto Carlos dos Passos", sanitizado)
        self.assertNotIn("98765432-1", sanitizado)
        self.assertNotIn("secretaria@paulofreire.edu.br", sanitizado)
        self.assertNotIn("98765-4321", sanitizado)
        self.assertNotIn("999.888.777-66", sanitizado)
        self.assertIn("[ESTUDANTE]", sanitizado)
        self.assertIn("[PROFESSOR]", sanitizado)
        self.assertIn("[IDENTIFICADOR]", sanitizado)
        self.assertIn("[EMAIL]", sanitizado)
        self.assertIn("[TELEFONE]", sanitizado)
        self.assertIn("[CPF]", sanitizado)
        self.assertIn("Instruções: Leia com atenção", sanitizado)

    def test_material_text_input_empty_validation(self) -> None:
        """MaterialTextInput deve rejeitar texto vazio ou somente com espaços."""
        from iris.schemas.materials import MaterialTextInput

        with self.assertRaises(ValueError):
            MaterialTextInput(text="   \n \t ")

    def test_material_validation_error_dict(self) -> None:
        """MaterialValidationError.to_dict deve conter detail, code e field."""
        err = MaterialValidationError(message="Erro de teste", code="TEST_CODE", field="file")
        d = err.to_dict()
        self.assertEqual(d["detail"], "Erro de teste")
        self.assertEqual(d["code"], "TEST_CODE")
        self.assertEqual(d["field"], "file")


if __name__ == "__main__":
    unittest.main()

