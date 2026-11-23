"""Testes unitários para o processador, classificador e renderizador de PDFs (História 1.1.3 - Etapa 4.A).

Cobre os 16 cenários obrigatórios especificados:
1. PDF exclusivamente textual.
2. PDF digitalizado com imagem ocupando a página.
3. PDF misto com texto nativo e imagem.
4. PDF multipágina com tipos diferentes de página.
5. Preservação da ordem e numeração das páginas.
6. Extração do texto nativo sem duplicação.
7. Identificação dos blocos e regiões de imagem (bbox).
8. Renderização de página e região visual.
9. PDF vazio ou sem páginas.
10. PDF corrompido.
11. PDF acima de 25 MB.
12. PDF textual acima de 10 MB.
13. PDF escaneado entre 10 MB e 25 MB.
14. Falha de renderização.
15. Fechamento do documento e liberação dos recursos em sucesso e falha.
16. Garantia de que o módulo não cria arquivos temporários no disco.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from unittest import mock

import fitz  # PyMuPDF
from PIL import Image

from iris.parsers.pdf_processor import (
    DEFAULT_RENDER_DPI,
    ImageRegion,
    PdfCorruptedError,
    PdfEmptyFileError,
    PdfFileSizeError,
    PdfInvalidPageError,
    PdfNoPagesError,
    PdfPageInfo,
    PdfPageType,
    PdfProcessingError,
    PdfRenderError,
    inspect_and_classify_pdf,
    iter_render_pdf_pages,
    render_pdf_page_image,
    render_pdf_region_image,
)
from iris.schemas.materials import (
    MAX_FILE_SIZE_BYTES,
    MAX_OCR_FILE_SIZE_BYTES,
    MaterialSourceType,
)


def _create_synthetic_textual_pdf(
    text: str = (
        "Avaliação de Ciências - 6º Ano\n"
        "Questão 1. A fotossíntese é o processo biológico responsável pela síntese de carboidratos nas folhas.\n"
        "Questão 2. Explique o papel dos cloroplastos na conversão de energia luminosa em energia química."
    ),
    pages_count: int = 1,
) -> bytes:
    """Cria um PDF sintético puramente textual em memória."""
    doc = fitz.open()
    for _ in range(pages_count):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((50, 72), text, fontsize=12)
    b = doc.tobytes()
    doc.close()
    return b


def _create_synthetic_scanned_pdf(pages_count: int = 1) -> bytes:
    """Cria um PDF sintético digitalizado (imagem cobrindo a página inteira, sem texto nativo)."""
    doc = fitz.open()
    for _ in range(pages_count):
        page = doc.new_page(width=595, height=842)
        # Imagem cobrindo 90% da página
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 600), False)
        pix.clear_with(200)
        page.insert_image(fitz.Rect(50, 50, 545, 792), pixmap=pix)
    b = doc.tobytes()
    doc.close()
    return b


def _create_synthetic_mixed_pdf() -> bytes:
    """Cria um PDF sintético misto (texto nativo e imagem ocupando região relevante)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # 1. Enunciado nativo
    enunciado = (
        "Prova de Geografia - Questão 1:\n"
        "Observe atentamente o gráfico meteorológico abaixo e responda à alternativa correta.\n"
        "O gráfico apresenta a variação da precipitação pluviométrica ao longo dos últimos doze meses."
    )
    page.insert_text((50, 60), enunciado, fontsize=12)

    # 2. Imagem da questão (ocupando ~30% da página)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 200), False)
    pix.clear_with(180)
    page.insert_image(fitz.Rect(50, 160, 450, 460), pixmap=pix, keep_proportion=False)

    b = doc.tobytes()
    doc.close()
    return b


class TestPdfProcessorClassification(unittest.TestCase):
    """Testa classificação estruturada de páginas e documentos PDF."""

    def test_1_pdf_exclusivamente_textual(self) -> None:
        """Cenário 1: PDF exclusivamente textual classificado como MaterialSourceType.PDF."""
        pdf_bytes = _create_synthetic_textual_pdf()
        result = inspect_and_classify_pdf(pdf_bytes)

        self.assertEqual(result.doc_type, MaterialSourceType.PDF)
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(result.textual_pages_count, 1)
        self.assertEqual(result.scanned_pages_count, 0)
        self.assertEqual(result.mixed_pages_count, 0)
        self.assertFalse(result.requires_visual_processing)
        self.assertFalse(result.has_mixed_content)
        self.assertIn("fotossíntese", result.consolidated_native_text)

        page = result.pages[0]
        self.assertEqual(page.page_type, PdfPageType.TEXTUAL)
        self.assertGreater(page.char_count, 50)
        self.assertEqual(page.image_count, 0)

    def test_2_pdf_digitalizado_com_imagem_ocupando_pagina(self) -> None:
        """Cenário 2: PDF escaneado classificado como MaterialSourceType.SCANNED_PDF."""
        pdf_bytes = _create_synthetic_scanned_pdf()
        result = inspect_and_classify_pdf(pdf_bytes)

        self.assertEqual(result.doc_type, MaterialSourceType.SCANNED_PDF)
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(result.scanned_pages_count, 1)
        self.assertEqual(result.textual_pages_count, 0)
        self.assertTrue(result.requires_visual_processing)

        page = result.pages[0]
        self.assertEqual(page.page_type, PdfPageType.SCANNED)
        self.assertEqual(page.char_count, 0)
        self.assertGreaterEqual(page.images_area_ratio, 0.60)
        self.assertEqual(page.image_count, 1)

    def test_3_pdf_misto_com_texto_nativo_e_imagem(self) -> None:
        """Cenário 3: PDF misto classificado como MaterialSourceType.MIXED_PDF."""
        pdf_bytes = _create_synthetic_mixed_pdf()
        result = inspect_and_classify_pdf(pdf_bytes)

        self.assertEqual(result.doc_type, MaterialSourceType.MIXED_PDF)
        self.assertEqual(result.mixed_pages_count, 1)
        self.assertTrue(result.has_mixed_content)
        self.assertTrue(result.requires_visual_processing)

        page = result.pages[0]
        self.assertEqual(page.page_type, PdfPageType.MIXED)
        self.assertGreater(page.char_count, 50)
        self.assertIn("precipitação pluviométrica", page.native_text)
        self.assertEqual(page.image_count, 1)
        self.assertGreater(page.images_area_ratio, 0.10)

    def test_4_pdf_multipagina_com_tipos_diferentes_de_pagina(self) -> None:
        """Cenário 4: PDF multipágina contendo páginas textual, escaneada e mista."""
        doc = fitz.open()

        # Página 1: Textual
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text((50, 72), "Página 1 com texto nativo extenso " * 5, fontsize=12)

        # Página 2: Escaneada (imagem cobrindo 90%)
        p2 = doc.new_page(width=595, height=842)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 400), False)
        p2.insert_image(fitz.Rect(50, 50, 545, 792), pixmap=pix)

        # Página 3: Mista (texto + imagem)
        p3 = doc.new_page(width=595, height=842)
        p3.insert_text((50, 60), "Página 3 com texto nativo sobre o mapa " * 3, fontsize=12)
        p3.insert_image(fitz.Rect(50, 150, 400, 400), pixmap=pix)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)

        self.assertEqual(result.doc_type, MaterialSourceType.MIXED_PDF)
        self.assertEqual(result.total_pages, 3)
        self.assertEqual(result.textual_pages_count, 1)
        self.assertEqual(result.scanned_pages_count, 1)
        self.assertEqual(result.mixed_pages_count, 1)

        self.assertEqual(result.pages[0].page_type, PdfPageType.TEXTUAL)
        self.assertEqual(result.pages[1].page_type, PdfPageType.SCANNED)
        self.assertEqual(result.pages[2].page_type, PdfPageType.MIXED)

    def test_5_preservacao_da_ordem_e_numeracao_das_paginas(self) -> None:
        """Cenário 5: Numeração e ordem estrita das páginas (1-indexed)."""
        pdf_bytes = _create_synthetic_textual_pdf(pages_count=4)
        result = inspect_and_classify_pdf(pdf_bytes)

        self.assertEqual(len(result.pages), 4)
        for idx, page_info in enumerate(result.pages):
            self.assertEqual(page_info.page_number, idx + 1)

    def test_6_extracao_do_texto_nativo_sem_duplicacao(self) -> None:
        """Cenário 6: O texto nativo consolidado não duplica sentenças de páginas distintas."""
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((50, 72), "Texto único da primeira página.", fontsize=12)
        p2 = doc.new_page()
        p2.insert_text((50, 72), "Texto único da segunda página.", fontsize=12)
        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertIn("primeira página", result.pages[0].native_text)
        self.assertNotIn("segunda página", result.pages[0].native_text)
        self.assertIn("segunda página", result.pages[1].native_text)
        self.assertNotIn("primeira página", result.pages[1].native_text)

        # O texto consolidado contém ambos exatamente uma vez
        self.assertEqual(result.consolidated_native_text.count("Texto único da primeira página."), 1)
        self.assertEqual(result.consolidated_native_text.count("Texto único da segunda página."), 1)

    def test_7_identificacao_dos_blocos_e_regioes_de_imagem(self) -> None:
        """Cenário 7: Coordenadas bbox e metadados espaciais de blocos de imagem."""
        pdf_bytes = _create_synthetic_mixed_pdf()
        result = inspect_and_classify_pdf(pdf_bytes)

        page = result.pages[0]
        self.assertEqual(len(page.image_regions), 1)
        reg = page.image_regions[0]
        self.assertIsInstance(reg, ImageRegion)
        self.assertEqual(len(reg.bbox), 4)
        self.assertAlmostEqual(reg.bbox[0], 50.0, places=1)
        self.assertAlmostEqual(reg.bbox[1], 160.0, places=1)
        self.assertAlmostEqual(reg.bbox[2], 450.0, places=1)
        self.assertAlmostEqual(reg.bbox[3], 460.0, places=1)
        self.assertAlmostEqual(reg.width, 400.0, places=1)
        self.assertAlmostEqual(reg.height, 300.0, places=1)
        self.assertGreater(reg.area_ratio, 0.15)


class TestPdfProcessorRenderingAndMemory(unittest.TestCase):
    """Testa renderização sequencial de páginas inteiras e recortes (clips) em memória."""

    def test_8_renderizacao_de_pagina_e_regiao_visual(self) -> None:
        """Cenário 8: Renderização de página completa e região com retorno em PIL.Image e bytes."""
        pdf_bytes = _create_synthetic_mixed_pdf()

        # 8.a: Página completa como PIL Image
        img_page = render_pdf_page_image(pdf_bytes, page_number=1, dpi=150, as_pil=True)
        self.assertIsInstance(img_page, Image.Image)
        self.assertGreater(img_page.width, 500)
        self.assertGreater(img_page.height, 700)

        # 8.b: Página completa como bytes PNG
        png_bytes = render_pdf_page_image(pdf_bytes, page_number=1, dpi=150, as_pil=False)
        self.assertIsInstance(png_bytes, bytes)
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))

        # 8.c: Região visual delimitada (clip)
        bbox = (50.0, 160.0, 450.0, 460.0)
        img_region = render_pdf_region_image(pdf_bytes, page_number=1, bbox=bbox, dpi=150, as_pil=True)
        self.assertIsInstance(img_region, Image.Image)
        # 400 pt de largura a 150 DPI = ~833 px
        self.assertAlmostEqual(img_region.width, 833, delta=5)

        # 8.d: Gerador sequencial de páginas sob demanda
        rendered_pages = list(iter_render_pdf_pages(pdf_bytes, dpi=100, as_pil=True))
        self.assertEqual(len(rendered_pages), 1)
        p_num, p_img = rendered_pages[0]
        self.assertEqual(p_num, 1)
        self.assertIsInstance(p_img, Image.Image)

    def test_14_falha_de_renderizacao(self) -> None:
        """Cenário 14: Lançamento de PdfRenderError quando a rasterização falha."""
        pdf_bytes = _create_synthetic_textual_pdf()
        with mock.patch("fitz.Page.get_pixmap", side_effect=RuntimeError("GPL Ghostscript error")):
            with self.assertRaises(PdfRenderError) as ctx:
                render_pdf_page_image(pdf_bytes, page_number=1)
            self.assertEqual(ctx.exception.code, "PDF_RENDER_ERROR")

    def test_15_fechamento_do_documento_e_liberacao_em_sucesso_e_falha(self) -> None:
        """Cenário 15: O documento PyMuPDF é fechado (doc.close) em sucesso e em falha."""
        pdf_bytes = _create_synthetic_textual_pdf()

        # Sucesso: espiona a chamada a doc.close()
        real_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        with mock.patch("fitz.open", return_value=real_doc):
            with mock.patch.object(real_doc, "close", wraps=real_doc.close) as mock_close:
                result = inspect_and_classify_pdf(pdf_bytes)
                mock_close.assert_called_once()
                self.assertTrue(real_doc.is_closed)

        # Falha durante leitura de página: garante fechamento no bloco finally
        real_doc_err = fitz.open(stream=pdf_bytes, filetype="pdf")
        with mock.patch("fitz.open", return_value=real_doc_err):
            with mock.patch.object(real_doc_err, "close", wraps=real_doc_err.close) as mock_close_err:
                with mock.patch("fitz.Page.get_text", side_effect=RuntimeError("Simulated read error")):
                    result = inspect_and_classify_pdf(pdf_bytes)
                    mock_close_err.assert_called_once()
                    self.assertTrue(real_doc_err.is_closed)

    def test_16_garantia_de_que_nao_cria_arquivos_temporarios(self) -> None:
        """Cenário 16: Zero escrita de arquivos em disco durante inspeção e renderização."""
        temp_dir = tempfile.gettempdir()
        initial_files = set(os.listdir(temp_dir))

        pdf_bytes = _create_synthetic_mixed_pdf()
        inspect_and_classify_pdf(pdf_bytes)
        render_pdf_page_image(pdf_bytes, page_number=1)
        render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 50, 200, 200))

        current_files = set(os.listdir(temp_dir))
        new_files = current_files - initial_files
        self.assertEqual(len(new_files), 0, f"Arquivos temporários detectados no disco: {new_files}")


class TestPdfProcessorLimitsAndErrors(unittest.TestCase):
    """Testa tratamento de erros, segurança e limites técnicos de 10 MB e 25 MB."""

    def test_9_pdf_vazio_ou_sem_paginas(self) -> None:
        """Cenário 9: Rejeição de PDF com 0 bytes ou 0 páginas."""
        with self.assertRaises(PdfEmptyFileError) as ctx:
            inspect_and_classify_pdf(b"")
        self.assertEqual(ctx.exception.code, "EMPTY_FILE")

        # PDF sintético válido com catálogo contendo 0 páginas
        zero_pages_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
            b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n115\n%%EOF"
        )
        with self.assertRaises(PdfNoPagesError) as ctx_pages:
            inspect_and_classify_pdf(zero_pages_pdf)
        self.assertEqual(ctx_pages.exception.code, "NO_PAGES")

    def test_10_pdf_corrompido(self) -> None:
        """Cenário 10: Rejeição de bytes corrompidos com PdfCorruptedError."""
        corrupted_bytes = b"%PDF-1.4\ncorrupted_garbage_header_12345"
        with self.assertRaises(PdfCorruptedError) as ctx:
            inspect_and_classify_pdf(corrupted_bytes)
        self.assertEqual(ctx.exception.code, "CORRUPTED_PDF")

    def test_11_pdf_acima_de_25mb(self) -> None:
        """Cenário 11: Rejeição imediata de arquivos maiores que o limite absoluto de 25 MB."""
        large_bytes = b"%PDF" + b"0" * (26 * 1024 * 1024)
        with self.assertRaises(PdfFileSizeError) as ctx:
            inspect_and_classify_pdf(large_bytes)
        self.assertEqual(ctx.exception.code, "OCR_FILE_TOO_LARGE")

    def test_12_pdf_textual_acima_de_10mb(self) -> None:
        """Cenário 12: Rejeição de PDF puramente textual maior que 10 MB."""
        # Cria um PDF textual válido e adiciona dados de padding no stream sem alterar o conteúdo textual
        base_pdf = _create_synthetic_textual_pdf()
        # Padding de 11 MB mantendo a estrutura do PDF válida
        padded_pdf = base_pdf + b"%%EOF\n" + b"0" * (11 * 1024 * 1024)

        with self.assertRaises(PdfFileSizeError) as ctx:
            inspect_and_classify_pdf(padded_pdf)
        self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")
        self.assertIn("10 MB", str(ctx.exception))

    def test_13_pdf_escaneado_entre_10mb_e_25mb(self) -> None:
        """Cenário 13: Aceitação de PDF escaneado maior que 10 MB e menor que 25 MB."""
        base_pdf = _create_synthetic_scanned_pdf()
        # Padding de 12 MB (total ~12.1 MB)
        padded_pdf = base_pdf + b"%%EOF\n" + b"0" * (12 * 1024 * 1024)

        result = inspect_and_classify_pdf(padded_pdf)
        self.assertEqual(result.doc_type, MaterialSourceType.SCANNED_PDF)
        self.assertGreater(result.total_bytes, MAX_FILE_SIZE_BYTES)
        self.assertLessEqual(result.total_bytes, MAX_OCR_FILE_SIZE_BYTES)

    def test_pagina_invalida_lanca_pdf_invalid_page_error(self) -> None:
        """Verifica tratamento de page_number inválido na renderização."""
        pdf_bytes = _create_synthetic_textual_pdf()
        with self.assertRaises(PdfInvalidPageError):
            render_pdf_page_image(pdf_bytes, page_number=0)
        with self.assertRaises(PdfInvalidPageError):
            render_pdf_page_image(pdf_bytes, page_number=99)


if __name__ == "__main__":
    unittest.main()
