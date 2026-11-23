"""Testes unitários e de integração para o wrapper de OCR (História 1.1.3 - Etapa 3).

Cobre:
- Validação e imutabilidade dos contratos (OcrConfig, OcrPageResult, OcrEnvironmentStatus).
- Hierarquia e códigos das exceções de domínio.
- Diagnóstico de ambiente local com e sem binário/idioma.
- Validação de entrada: tipos, dimensões, formato, bytes vazios, tamanho excessivo, imagens corrompidas.
- Tolerância a imagens de baixa resolução (emissão de low_resolution_warning sem descarte).
- Reconstrução hierárquica em passo único (blocos, parágrafos, linhas) sem descarte de termos com baixa confiança.
- Apuração estatística de confiança (heurística, separação de contagens, None para ausência de dados válidos).
- Mapeamento defensivo de exceções de subprocesso (EngineNotFound, Timeout, Language, etc.).
- Testes reais condicionais à presença do binário do Tesseract no host.
"""
from __future__ import annotations

import io
import sys
from types import MappingProxyType
from unittest import TestCase, mock

try:
    import pydantic
except ImportError:
    if "pydantic" not in sys.modules:
        sys.modules["pydantic"] = mock.MagicMock()

import pytesseract
from PIL import Image

from iris.parsers.ocr_extractor import (
    MAX_IMAGE_PIXELS,
    OcrConfig,
    OcrDependencyError,
    OcrEngineNotFoundError,
    OcrEnvironmentStatus,
    OcrError,
    OcrImageError,
    OcrLanguageError,
    OcrPageResult,
    OcrTimeoutError,
    check_ocr_environment,
    extract_text_from_page_image,
)
from iris.schemas.materials import MAX_OCR_FILE_SIZE_BYTES


class TestOcrContractsAndExceptions(TestCase):
    """Testa contratos de dados, imutabilidade e hierarquia de exceções."""

    def test_ocr_config_defaults(self) -> None:
        cfg = OcrConfig()
        self.assertEqual(cfg.lang, "por")
        self.assertIsNone(cfg.tesseract_cmd)
        self.assertEqual(cfg.timeout_seconds, 30.0)
        self.assertEqual(cfg.min_confidence, 60.0)
        self.assertEqual(cfg.psm, 3)
        self.assertEqual(cfg.oem, 3)
        self.assertIsNone(cfg.tessdata_dir)

    def test_ocr_page_result_contract_and_immutability(self) -> None:
        result = OcrPageResult(
            page_number=1,
            raw_text="Questão 1: Calcule a área.",
            confidence=85.5,
            word_count=5,
            valid_confidence_count=5,
            low_confidence_word_count=0,
            has_text=True,
            language="por",
            metadata={"source": "scan"},
        )
        self.assertEqual(result.page_number, 1)
        self.assertEqual(result.raw_text, "Questão 1: Calcule a área.")
        self.assertEqual(result.confidence, 85.5)
        self.assertEqual(result.word_count, 5)
        self.assertEqual(result.valid_confidence_count, 5)
        self.assertEqual(result.low_confidence_word_count, 0)
        self.assertTrue(result.has_text)
        self.assertEqual(result.language, "por")
        self.assertIsInstance(result.metadata, MappingProxyType)
        self.assertEqual(result.metadata["source"], "scan")

        # Imutabilidade de atributos
        with self.assertRaises((AttributeError, TypeError)):
            result.raw_text = "Novo texto"  # type: ignore[misc]

        # Imutabilidade do dicionário de metadados
        with self.assertRaises(TypeError):
            result.metadata["source"] = "outro"  # type: ignore[index]

    def test_ocr_page_result_invalid_page_number(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            OcrPageResult(
                page_number=0,
                raw_text="Texto",
                confidence=None,
                word_count=1,
                valid_confidence_count=0,
                low_confidence_word_count=0,
                has_text=True,
            )
        self.assertIn("page_number must be an integer >= 1", str(ctx.exception))

        with self.assertRaises(ValueError):
            OcrPageResult(
                page_number=-2,
                raw_text="Texto",
                confidence=None,
                word_count=1,
                valid_confidence_count=0,
                low_confidence_word_count=0,
                has_text=True,
            )

    def test_ocr_page_result_confidence_none_when_no_valid_scores(self) -> None:
        result = OcrPageResult(
            page_number=1,
            raw_text="",
            confidence=None,
            word_count=0,
            valid_confidence_count=0,
            low_confidence_word_count=0,
            has_text=False,
        )
        self.assertIsNone(result.confidence)
        self.assertFalse(result.has_text)

    def test_exception_hierarchy_and_codes(self) -> None:
        err = OcrError("Falha genérica", code="GENERIC_OCR")
        self.assertIsInstance(err, Exception)
        self.assertEqual(err.code, "GENERIC_OCR")

        dep_err = OcrDependencyError()
        self.assertIsInstance(dep_err, OcrError)
        self.assertEqual(dep_err.code, "OCR_DEPENDENCY_ERROR")

        eng_err = OcrEngineNotFoundError()
        self.assertIsInstance(eng_err, OcrError)
        self.assertEqual(eng_err.code, "OCR_ENGINE_NOT_FOUND")

        lang_err = OcrLanguageError()
        self.assertIsInstance(lang_err, OcrError)
        self.assertEqual(lang_err.code, "OCR_LANGUAGE_NOT_FOUND")

        timeout_err = OcrTimeoutError()
        self.assertIsInstance(timeout_err, OcrError)
        self.assertEqual(timeout_err.code, "OCR_TIMEOUT")

        img_err = OcrImageError("Imagem inválida", code="OCR_INVALID_DIMENSIONS")
        self.assertIsInstance(img_err, OcrError)
        self.assertEqual(img_err.code, "OCR_INVALID_DIMENSIONS")


class TestCheckOcrEnvironment(TestCase):
    """Testa a função de diagnóstico check_ocr_environment."""

    @mock.patch("iris.parsers.ocr_extractor._HAS_PYTESSERACT", False)
    def test_check_environment_pytesseract_missing(self) -> None:
        status = check_ocr_environment()
        self.assertFalse(status.is_available)
        self.assertIsNone(status.tesseract_version)
        self.assertFalse(status.has_portuguese)
        self.assertTrue(any("não está instalada" in issue for issue in status.issues))

    @mock.patch("pytesseract.get_tesseract_version")
    def test_check_environment_binary_missing(self, mock_version: mock.MagicMock) -> None:
        mock_version.side_effect = Exception("tesseract is not installed")
        status = check_ocr_environment()
        self.assertFalse(status.is_available)
        self.assertIsNone(status.tesseract_version)
        self.assertFalse(status.has_portuguese)
        self.assertTrue(any("binary not found" in issue for issue in status.issues))

    @mock.patch("pytesseract.get_languages")
    @mock.patch("pytesseract.get_tesseract_version")
    def test_check_environment_portuguese_missing(
        self, mock_version: mock.MagicMock, mock_langs: mock.MagicMock
    ) -> None:
        mock_version.return_value = "5.3.0"
        mock_langs.return_value = ["eng", "osd"]
        status = check_ocr_environment(OcrConfig(lang="por"))
        self.assertFalse(status.is_available)
        self.assertEqual(status.tesseract_version, "5.3.0")
        self.assertEqual(status.available_languages, ("eng", "osd"))
        self.assertFalse(status.has_portuguese)
        self.assertTrue(any("not installed" in issue for issue in status.issues))

    @mock.patch("pytesseract.get_languages")
    @mock.patch("pytesseract.get_tesseract_version")
    def test_check_environment_healthy(
        self, mock_version: mock.MagicMock, mock_langs: mock.MagicMock
    ) -> None:
        mock_version.return_value = "5.3.0"
        mock_langs.return_value = ["eng", "por", "osd"]
        status = check_ocr_environment(OcrConfig(lang="por"))
        self.assertTrue(status.is_available)
        self.assertEqual(status.tesseract_version, "5.3.0")
        self.assertEqual(status.available_languages, ("eng", "por", "osd"))
        self.assertTrue(status.has_portuguese)
        self.assertEqual(len(status.issues), 0)


class TestExtractTextValidations(TestCase):
    """Testa validações defensivas de entrada em extract_text_from_page_image."""

    def test_invalid_page_number(self) -> None:
        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(ValueError):
            extract_text_from_page_image(img, page_number=0)
        with self.assertRaises(ValueError):
            extract_text_from_page_image(img, page_number=-1)

    def test_invalid_input_type(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            extract_text_from_page_image("not an image bytes", page_number=1)  # type: ignore[arg-type]
        self.assertIn("must be bytes or PIL.Image.Image", str(ctx.exception))

    def test_empty_bytes_input(self) -> None:
        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(b"", page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_EMPTY_IMAGE")

    def test_bytes_exceeding_max_file_size(self) -> None:
        large_bytes = b"x" * (MAX_OCR_FILE_SIZE_BYTES + 1)
        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(large_bytes, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_IMAGE_SIZE_EXCEEDED")

    def test_corrupted_bytes_input(self) -> None:
        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(b"not a valid image format content", page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_CORRUPTED_IMAGE")

    def test_unsupported_image_format_in_bytes(self) -> None:
        # Criar imagem GIF em memória
        stream = io.BytesIO()
        img = Image.new("P", (200, 200))
        img.save(stream, format="GIF")
        gif_bytes = stream.getvalue()

        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(gif_bytes, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_UNSUPPORTED_FORMAT")

    def test_zero_dimensions_image(self) -> None:
        img = mock.MagicMock(spec=Image.Image)
        img.size = (0, 200)
        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_INVALID_DIMENSIONS")

    def test_excessive_total_pixels(self) -> None:
        img = mock.MagicMock(spec=Image.Image)
        img.size = (5_001, 5_000)  # 25_005_000 pixels > MAX_IMAGE_PIXELS (25_000_000)
        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_IMAGE_TOO_LARGE")
        self.assertIn("Total de pixels (25005000) excede o limite seguro (25000000)", str(ctx.exception))

    @mock.patch("pytesseract.image_to_data")
    def test_exact_max_pixels_accepted(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {"text": [], "conf": []}
        img = mock.MagicMock(spec=Image.Image)
        img.size = (5_000, 5_000)  # Exatamente 25_000_000 pixels
        img.mode = "L"

        result = extract_text_from_page_image(img, page_number=1)
        self.assertEqual(result.page_number, 1)
        self.assertFalse(result.has_text)
        self.assertEqual(result.metadata["width"], 5_000)
        self.assertEqual(result.metadata["height"], 5_000)

    @mock.patch("PIL.Image.open")
    def test_bytes_input_exceeding_max_pixels_rejected_before_load(self, mock_open: mock.MagicMock) -> None:
        mock_img = mock.MagicMock()
        mock_img.format = "PNG"
        mock_img.size = (6_000, 5_000)  # 30_000_000 pixels > 25_000_000
        mock_open.return_value = mock_img

        valid_header_bytes = b"fake-png-bytes"
        with self.assertRaises(OcrImageError) as ctx:
            extract_text_from_page_image(valid_header_bytes, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_IMAGE_TOO_LARGE")
        # Confirma que load() NÃO foi chamado, evitando consumo de memória
        mock_img.load.assert_not_called()
        mock_img.close.assert_called_once()

    @mock.patch("pytesseract.image_to_data")
    @mock.patch("PIL.Image.open")
    def test_bytes_input_within_max_pixels_accepted(
        self, mock_open: mock.MagicMock, mock_to_data: mock.MagicMock
    ) -> None:
        mock_to_data.return_value = {
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "text": ["OK"],
            "conf": ["95.0"],
        }
        mock_img = mock.MagicMock()
        mock_img.format = "PNG"
        mock_img.size = (5_000, 5_000)  # Exatamente 25_000_000 pixels
        mock_img.mode = "L"
        mock_open.return_value = mock_img

        result = extract_text_from_page_image(b"fake-png-bytes", page_number=1)
        self.assertEqual(result.raw_text, "OK")
        mock_img.load.assert_called_once()


class TestHierarchicalReconstructionAndMetrics(TestCase):
    """Testa reconstrução hierárquica e apuração heurística de métricas."""

    @mock.patch("pytesseract.image_to_data")
    def test_hierarchical_reconstruction_multi_paragraph(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "level": [5, 5, 5, 5, 5, 5],
            "block_num": [1, 1, 1, 2, 2, 2],
            "par_num": [1, 1, 1, 1, 1, 1],
            "line_num": [1, 1, 2, 1, 1, 1],
            "word_num": [1, 2, 1, 1, 2, 3],
            "text": ["Questão", "1:", "Enunciado", "Opção", "A)", "Correta"],
            "conf": ["90.5", "85.0", "75.0", "50.0", "95.0", "80.0"],
        }

        img = Image.new("RGB", (600, 800), color="white")
        result = extract_text_from_page_image(img, page_number=1, config=OcrConfig(min_confidence=60.0))

        # Parágrafo 1 tem Linha 1 ("Questão 1:") e Linha 2 ("Enunciado")
        # Parágrafo 2 tem Linha 1 ("Opção A) Correta")
        expected_text = "Questão 1:\nEnunciado\n\nOpção A) Correta"
        self.assertEqual(result.raw_text, expected_text)
        self.assertEqual(result.word_count, 6)
        self.assertEqual(result.valid_confidence_count, 6)
        # "50.0" está abaixo do min_confidence 60.0
        self.assertEqual(result.low_confidence_word_count, 1)
        # Média: (90.5 + 85.0 + 75.0 + 50.0 + 95.0 + 80.0) / 6 = 475.5 / 6 = 79.25
        self.assertEqual(result.confidence, 79.25)
        self.assertTrue(result.has_text)
        self.assertFalse(result.metadata["low_resolution_warning"])

    @mock.patch("pytesseract.image_to_data")
    def test_words_with_low_confidence_are_never_discarded(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
            "text": ["PalavraRuim", "PalavraBoa", "Incerta"],
            "conf": ["10.0", "95.0", "25.0"],
        }
        img = Image.new("RGB", (300, 300), color="white")
        result = extract_text_from_page_image(img, page_number=1, config=OcrConfig(min_confidence=60.0))

        # Todas as palavras permanecem no texto original
        self.assertEqual(result.raw_text, "PalavraRuim PalavraBoa Incerta")
        self.assertEqual(result.word_count, 3)
        self.assertEqual(result.valid_confidence_count, 3)
        self.assertEqual(result.low_confidence_word_count, 2)
        self.assertTrue(result.has_text)

    @mock.patch("pytesseract.image_to_data")
    def test_empty_recognition_returns_none_confidence(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "text": ["   "],  # Apenas espaços vazios
            "conf": ["-1"],
        }
        img = Image.new("RGB", (300, 300), color="white")
        result = extract_text_from_page_image(img, page_number=2)

        self.assertEqual(result.raw_text, "")
        self.assertIsNone(result.confidence)
        self.assertEqual(result.word_count, 0)
        self.assertEqual(result.valid_confidence_count, 0)
        self.assertEqual(result.low_confidence_word_count, 0)
        self.assertFalse(result.has_text)

    @mock.patch("pytesseract.image_to_data")
    def test_negative_or_unparseable_confidence_ignored_in_average(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "text": ["Palavra1", "Palavra2"],
            "conf": ["-1", "invalid_number"],
        }
        img = Image.new("RGB", (300, 300), color="white")
        result = extract_text_from_page_image(img, page_number=1)

        self.assertEqual(result.raw_text, "Palavra1 Palavra2")
        self.assertEqual(result.word_count, 2)
        self.assertEqual(result.valid_confidence_count, 0)
        self.assertIsNone(result.confidence)
        self.assertTrue(result.has_text)

    @mock.patch("pytesseract.image_to_data")
    def test_portuguese_text_with_mathematical_symbols(self, mock_to_data: mock.MagicMock) -> None:
        math_tokens = ["Seja", "f(x)", "=", "2x", "+", "3,", "calcule", "∫f(x)dx", "onde", "x", "∈", "ℝ."]
        confs = ["92.0"] * len(math_tokens)
        mock_to_data.return_value = {
            "block_num": [1] * len(math_tokens),
            "par_num": [1] * len(math_tokens),
            "line_num": [1] * len(math_tokens),
            "text": math_tokens,
            "conf": confs,
        }
        img = Image.new("RGB", (500, 200), color="white")
        result = extract_text_from_page_image(img, page_number=1)

        expected_text = "Seja f(x) = 2x + 3, calcule ∫f(x)dx onde x ∈ ℝ."
        self.assertEqual(result.raw_text, expected_text)
        self.assertEqual(result.word_count, len(math_tokens))
        self.assertEqual(result.confidence, 92.0)
        self.assertTrue(result.has_text)

    @mock.patch("pytesseract.image_to_data")
    def test_noisy_image_does_not_assume_empty_and_preserves_tokens(self, mock_to_data: mock.MagicMock) -> None:
        # Simula ruído de digitalização onde o OCR reconhece apenas fragmentos de artefatos
        noise_tokens = ["~", "^", "...", "·"]
        confs = ["15.0", "12.0", "8.0", "5.0"]
        mock_to_data.return_value = {
            "block_num": [1] * len(noise_tokens),
            "par_num": [1] * len(noise_tokens),
            "line_num": [1] * len(noise_tokens),
            "text": noise_tokens,
            "conf": confs,
        }
        img = Image.new("RGB", (300, 300), color="white")
        result = extract_text_from_page_image(img, page_number=1, config=OcrConfig(min_confidence=60.0))

        # Não assume que ruído é silenciosamente descartado ou que gera string vazia:
        # os fragmentos são mantidos para auditoria docente, com low_confidence_word_count sinalizado.
        self.assertEqual(result.raw_text, "~ ^ ... ·")
        self.assertEqual(result.word_count, 4)
        self.assertEqual(result.low_confidence_word_count, 4)
        self.assertTrue(result.has_text)
        self.assertEqual(result.confidence, 10.0)

    @mock.patch("pytesseract.image_to_data")
    def test_no_artificial_content_generated_on_empty_scan(self, mock_to_data: mock.MagicMock) -> None:
        # Quando verdadeiramente nenhum glifo for detectado, não deve haver texto artificial
        mock_to_data.return_value = {
            "block_num": [],
            "par_num": [],
            "line_num": [],
            "text": [],
            "conf": [],
        }
        img = Image.new("RGB", (300, 300), color="white")
        result = extract_text_from_page_image(img, page_number=1)

        self.assertEqual(result.raw_text, "")
        self.assertIsNone(result.confidence)
        self.assertEqual(result.word_count, 0)
        self.assertFalse(result.has_text)

    @mock.patch("pytesseract.image_to_data")
    def test_low_resolution_warning_emitted_without_error(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "text": ["Recorte"],
            "conf": ["80.0"],
        }
        # Imagem com dimensão menor que 150px
        img = Image.new("RGB", (120, 80), color="white")
        result = extract_text_from_page_image(img, page_number=1)

        self.assertTrue(result.metadata["low_resolution_warning"])
        self.assertEqual(result.raw_text, "Recorte")
        self.assertEqual(result.confidence, 80.0)

    @mock.patch("pytesseract.image_to_data")
    def test_bytes_input_png_success(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "text": ["Teste", "PNG"],
            "conf": ["88.0", "92.0"],
        }
        stream = io.BytesIO()
        img = Image.new("RGB", (200, 200), color="white")
        img.save(stream, format="PNG")
        png_bytes = stream.getvalue()

        result = extract_text_from_page_image(png_bytes, page_number=1)
        self.assertEqual(result.raw_text, "Teste PNG")
        self.assertEqual(result.confidence, 90.0)
        self.assertEqual(result.word_count, 2)
        self.assertTrue(result.has_text)

    @mock.patch("pytesseract.image_to_data")
    def test_in_memory_image_without_format_attribute_succeeds(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.return_value = {
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "text": ["Memória"],
            "conf": ["95.0"],
        }
        # Imagens geradas em memória pelo Pillow possuem format=None
        img = Image.new("RGB", (250, 250), color="white")
        self.assertIsNone(img.format)

        result = extract_text_from_page_image(img, page_number=3)
        self.assertEqual(result.raw_text, "Memória")
        self.assertEqual(result.confidence, 95.0)
        self.assertEqual(result.page_number, 3)


class TestSubprocessAndEngineErrorHandling(TestCase):
    """Testa mapeamento defensivo de falhas de subprocesso e Tesseract."""

    @mock.patch("pytesseract.image_to_data")
    def test_engine_not_found_mapped(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.side_effect = pytesseract.TesseractNotFoundError()
        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrEngineNotFoundError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_ENGINE_NOT_FOUND")

    @mock.patch("pytesseract.image_to_data")
    def test_timeout_mapped_to_ocr_timeout_error(self, mock_to_data: mock.MagicMock) -> None:
        # Simula exceção de timeout do pytesseract
        timeout_exc = getattr(
            pytesseract.pytesseract,
            "TimeoutException",
            TimeoutError,
        )
        orig_exc = timeout_exc("Timeout expired")
        mock_to_data.side_effect = orig_exc

        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrTimeoutError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_TIMEOUT")
        self.assertIs(ctx.exception.__cause__, orig_exc)

    @mock.patch("pytesseract.image_to_data")
    def test_pytesseract_runtime_error_timeout_mapped(self, mock_to_data: mock.MagicMock) -> None:
        """Comprova que RuntimeError('Tesseract process timeout') do pytesseract 0.3.13 é mapeado para OcrTimeoutError."""
        orig_exc = RuntimeError("Tesseract process timeout")
        mock_to_data.side_effect = orig_exc

        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrTimeoutError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_TIMEOUT")
        self.assertIs(ctx.exception.__cause__, orig_exc)

    @mock.patch("pytesseract.image_to_data")
    def test_timeout_case_insensitive_mapped(self, mock_to_data: mock.MagicMock) -> None:
        """Comprova que mensagens de timeout com caixa alta são mapeadas corretamente."""
        orig_exc = RuntimeError("TESSERACT PROCESS TIMEOUT DETECTED")
        mock_to_data.side_effect = orig_exc

        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrTimeoutError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_TIMEOUT")
        self.assertIs(ctx.exception.__cause__, orig_exc)

    @mock.patch("pytesseract.image_to_data")
    def test_runtime_error_without_timeout_mapped_to_generic_ocr_error(
        self, mock_to_data: mock.MagicMock
    ) -> None:
        """Garante que RuntimeError sem menção a timeout NÃO seja classificado como timeout indiscriminadamente."""
        orig_exc = RuntimeError("Memory allocation failure in native layer")
        mock_to_data.side_effect = orig_exc

        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertNotIsInstance(ctx.exception, OcrTimeoutError)
        self.assertEqual(ctx.exception.code, "OCR_ERROR")
        self.assertIs(ctx.exception.__cause__, orig_exc)

    @mock.patch("pytesseract.image_to_data")
    def test_language_traineddata_missing_mapped(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.side_effect = pytesseract.TesseractError(
            status=1,
            message="Error opening data file /usr/share/tessdata/por.traineddata",
        )
        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrLanguageError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_LANGUAGE_NOT_FOUND")

    @mock.patch("pytesseract.image_to_data")
    def test_generic_tesseract_error_mapped(self, mock_to_data: mock.MagicMock) -> None:
        mock_to_data.side_effect = pytesseract.TesseractError(
            status=1,
            message="Segmentation fault or internal failure",
        )
        img = Image.new("RGB", (200, 200), color="white")
        with self.assertRaises(OcrError) as ctx:
            extract_text_from_page_image(img, page_number=1)
        self.assertEqual(ctx.exception.code, "OCR_EXECUTION_ERROR")


class TestRealTesseractIntegration(TestCase):
    """Testa integração real com o binário Tesseract caso esteja disponível no host.

    Totalmente independente de mocks:
    - Verifica a disponibilidade do executável local e do idioma português ('por').
    - Se ausente algum dos componentes, o teste é ignorado informando o diagnóstico preciso.
    - Se disponível, executa OCR real sobre imagem com texto pedagógico em português e acentuação,
      comprovando o pipeline de ponta a ponta sem qualquer simulação sintética.
    """

    def test_real_extraction_if_environment_available(self) -> None:
        status = check_ocr_environment(OcrConfig(lang="por"))
        if not status.is_available:
            self.skipTest(f"Tesseract OCR ou idioma português indisponível no host: {status.issues}")

        from PIL import ImageDraw

        # Gera imagem nítida com texto escolar contendo caracteres acentuados e pontuação
        img = Image.new("RGB", (800, 200), color="white")
        draw = ImageDraw.Draw(img)
        test_phrase = "Avaliação de Português: Acentuação e Interpretação"
        draw.text((30, 80), test_phrase, fill="black")

        result = extract_text_from_page_image(img, page_number=1, config=OcrConfig(lang="por"))
        self.assertIsInstance(result, OcrPageResult)
        self.assertEqual(result.page_number, 1)
        self.assertTrue(result.has_text)
        self.assertIsNotNone(result.confidence)
        self.assertGreater(result.word_count, 0)
        self.assertGreater(result.valid_confidence_count, 0)
        upper_text = result.raw_text.upper()
        self.assertTrue(
            "PORTUGUÊS" in upper_text or "PORTUGUES" in upper_text or "AVALIAÇÃO" in upper_text or "AVALIACAO" in upper_text,
            f"Texto reconhecido não contém termos esperados: {result.raw_text}",
        )
