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
    MAX_RENDER_PIXELS,
    ImageRegion,
    PdfCorruptedError,
    PdfEmptyFileError,
    PdfFileSizeError,
    PdfInvalidBBoxError,
    PdfInvalidPageError,
    PdfNoPagesError,
    PdfPageInfo,
    PdfPageType,
    PdfProcessingError,
    PdfRenderError,
    PdfRenderPixelLimitError,
    inspect_and_classify_pdf,
    iter_render_pdf_pages,
    render_pdf_page_image,
    render_pdf_region_image,
    validate_and_calculate_render_dimensions,
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

    def test_7b_imagens_com_sangria_sao_recortadas_e_fora_da_pagina_ignoradas(self) -> None:
        """Correção 3: Imagens ultrapassando as bordas da página sofrem clipping seguro sem INVALID_BBOX."""
        from iris.parsers.pdf_processor import clip_bbox_to_page

        page_rect = fitz.Rect(0, 0, 595, 842)
        self.assertIsNone(clip_bbox_to_page(fitz.Rect(-100, -100, -10, -10), page_rect))
        self.assertIsNone(clip_bbox_to_page(fitz.Rect(600, 10, 700, 100), page_rect))
        self.assertIsNone(clip_bbox_to_page(fitz.Rect(10, float("nan"), 100, 100), page_rect))

        clipped = clip_bbox_to_page(fitz.Rect(-25.0, -10.0, 620.0, 860.0), page_rect)
        self.assertIsNotNone(clipped)
        self.assertEqual((clipped.x0, clipped.y0, clipped.x1, clipped.y1), (0.0, 0.0, 595.0, 842.0))

        # PDF com imagem com sangria nos quatro lados
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text(
            (50, 80),
            "Prova de História com diagrama sangrado até as bordas da folha impressa.",
            fontsize=12,
        )
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False)
        pix.clear_with(210)
        p.insert_image(fitz.Rect(-20, -15, 615, 420), pixmap=pix, keep_proportion=False)
        pdf_bytes = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(pdf_bytes)
        self.assertEqual(result.doc_type, MaterialSourceType.MIXED_PDF)
        reg = result.pages[0].image_regions[0]
        self.assertGreaterEqual(reg.bbox[0], 0.0)
        self.assertGreaterEqual(reg.bbox[1], 0.0)
        self.assertLessEqual(reg.bbox[2], 595.0)
        self.assertLessEqual(reg.bbox[3], 842.0)

        # Garante que a renderização da região recortada funciona sem PdfInvalidBBoxError
        region_img = render_pdf_region_image(pdf_bytes, page_number=1, bbox=reg.bbox, dpi=72)
        self.assertIsNotNone(region_img)
        region_img.close()

    def test_10b_pdf_criptografado_mensagem_clara(self) -> None:
        """PDF protegido por senha retorna code='ENCRYPTED_PDF' com mensagem clara em português."""
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text((50, 72), "Conteúdo protegido por senha escolar para o teste.", fontsize=12)
        encrypted_bytes = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="segredo123",
            owner_pw="dono123",
        )
        doc.close()

        with self.assertRaises(PdfCorruptedError) as ctx:
            inspect_and_classify_pdf(encrypted_bytes)
        self.assertEqual(ctx.exception.code, "ENCRYPTED_PDF")
        self.assertIn("senha", ctx.exception.message.lower())


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


class TestPdfClassificationEtapa4B1(unittest.TestCase):
    """Bateria de testes obrigatórios da Etapa 4.B1 (Classificação e Preservação de Texto Nativo).

    Utiliza exclusivamente PDFs sintéticos em memória com dimensões e áreas controladas.
    """

    @staticmethod
    def _create_synthetic_image_bytes(width: int, height: int, color: tuple[int, int, int] = (100, 150, 200)) -> bytes:
        """Gera bytes de imagem PNG sintética com dimensões exatas."""
        img = Image.new("RGB", (width, height), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_1_texto_curto_com_imagem_15_porcento_classifica_como_misto(self) -> None:
        """Regra 1 e 2: Texto curto (< 50 chars) com imagem relevante (15%) deve ser MIXED e preservar texto."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)  # A4: 500.990 pt²
        # Texto curto: 34 caracteres
        enunciado_curto = "Questão 1: Observe o mapa ao lado."
        page.insert_text((50, 60), enunciado_curto, fontsize=12)

        # Imagem ocupando ~15% da página (300 x 250 = 75.000 pt² / 500.990 ≈ 14.97%)
        img_bytes = self._create_synthetic_image_bytes(300, 250)
        page.insert_image(fitz.Rect(50, 100, 350, 350), stream=img_bytes, keep_proportion=False)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertEqual(result.doc_type, MaterialSourceType.MIXED_PDF)
        self.assertTrue(result.requires_visual_processing)
        self.assertEqual(len(result.pages), 1)

        p = result.pages[0]
        # Não pode ser classificado como puramente textual (falso negativo corrigido)
        self.assertEqual(p.page_type, PdfPageType.MIXED)
        self.assertLess(p.char_count, 50)
        self.assertGreater(p.char_count, 0)
        # O texto nativo curto deve ser rigorosamente preservado
        self.assertEqual(p.native_text, enunciado_curto)
        self.assertIn(enunciado_curto, result.consolidated_native_text)

    def test_2_pagina_sem_texto_nativo_com_imagem_18_porcento_classifica_como_scanned(self) -> None:
        """Regra 3: Página sem texto nativo e com imagem relevante (18%) deve ser SCANNED."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

        # Sem texto inserido (char_count == 0)
        # Imagem ocupando ~18% da página (300 x 300 = 90.000 pt² / 500.990 ≈ 17.96%)
        img_bytes = self._create_synthetic_image_bytes(300, 300)
        page.insert_image(fitz.Rect(50, 100, 350, 400), stream=img_bytes, keep_proportion=False)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertEqual(result.doc_type, MaterialSourceType.SCANNED_PDF)
        self.assertTrue(result.requires_visual_processing)
        self.assertEqual(len(result.pages), 1)

        p = result.pages[0]
        # Não pode ser confundida com textual
        self.assertEqual(p.page_type, PdfPageType.SCANNED)
        self.assertEqual(p.char_count, 0)
        self.assertEqual(p.native_text, "")

    def test_3_texto_nativo_longo_com_imagem_grande_65_porcento_classifica_como_misto(self) -> None:
        """Regra 5: Imagem grande (65%) com texto nativo longo deve ser MIXED e NUNCA exclusivamente SCANNED."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

        texto_longo = (
            "Capítulo 4 - Biomas Brasileiros e Biodiversidade.\n"
            "O Cerrado é considerado a savana com maior biodiversidade do planeta Terra, abrigando milhares "
            "de espécies endêmicas de flora e fauna. Suas árvores possuem troncos tortuosos e raízes profundas "
            "que funcionam como esponjas hídricas essenciais para as grandes bacias hidrográficas nacionais.\n"
            "Analise a fotografia abaixo que ilustra o estrato vegetal típico durante o período de estiagem."
        )
        page.insert_text((50, 50), texto_longo, fontsize=11)

        # Imagem grande ocupando ~65% da página (500 x 650 = 325.000 pt² / 500.990 ≈ 64.87%)
        img_bytes = self._create_synthetic_image_bytes(500, 650)
        page.insert_image(fitz.Rect(50, 160, 550, 810), stream=img_bytes, keep_proportion=False)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertEqual(result.doc_type, MaterialSourceType.MIXED_PDF)

        p = result.pages[0]
        # Não pode ser rebaixada para exclusivamente escaneada porque contém texto nativo
        self.assertEqual(p.page_type, PdfPageType.MIXED)
        self.assertGreater(p.char_count, 200)
        self.assertIn("Cerrado é considerado a savana", p.native_text)
        self.assertIn("período de estiagem", p.native_text)
        self.assertIn("Biomas Brasileiros", result.consolidated_native_text)

    def test_4_pagina_textual_sem_imagens_continua_textual(self) -> None:
        """Regra 4: Página textual sem imagens continua classificada como TEXTUAL."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        texto = "Este é um documento puramente textual de história para o 7º ano do ensino fundamental."
        page.insert_text((50, 70), texto, fontsize=12)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertEqual(result.doc_type, MaterialSourceType.PDF)
        self.assertFalse(result.requires_visual_processing)

        p = result.pages[0]
        self.assertEqual(p.page_type, PdfPageType.TEXTUAL)
        self.assertEqual(p.image_count, 0)
        self.assertEqual(p.images_area_ratio, 0.0)

    def test_5_pagina_sem_texto_e_sem_imagem_nao_e_confundida_com_escaneada(self) -> None:
        """Regra 4 e Caso Limítrofe: Página em branco (sem texto e sem imagem) permanece TEXTUAL."""
        doc = fitz.open()
        doc.new_page(width=595, height=842)  # Página vazia

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertEqual(result.doc_type, MaterialSourceType.PDF)
        self.assertFalse(result.requires_visual_processing)

        p = result.pages[0]
        self.assertEqual(p.page_type, PdfPageType.TEXTUAL)
        self.assertEqual(p.char_count, 0)
        self.assertEqual(p.image_count, 0)

    def test_6_documento_com_paginas_textual_mista_escaneada_mantem_classificacao_e_ordem(self) -> None:
        """Regra 8: Preserva classificação individual por página e ordem em documento heterogêneo."""
        doc = fitz.open()

        # Página 1: Textual
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text((50, 70), "Página 1: Introdução teórica completa ao tema da física moderna.", fontsize=12)

        # Página 2: Mista (enunciado curto + figura de 15%)
        p2 = doc.new_page(width=595, height=842)
        p2.insert_text((50, 60), "Questão 2: Observe o diagrama óptico.", fontsize=12)
        img_bytes_15 = self._create_synthetic_image_bytes(300, 250)
        p2.insert_image(fitz.Rect(50, 100, 350, 350), stream=img_bytes_15, keep_proportion=False)

        # Página 3: Escaneada (0 texto + imagem de 80%)
        p3 = doc.new_page(width=595, height=842)
        img_bytes_80 = self._create_synthetic_image_bytes(500, 700)
        p3.insert_image(fitz.Rect(40, 50, 540, 750), stream=img_bytes_80, keep_proportion=False)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        self.assertEqual(result.total_pages, 3)
        self.assertEqual(result.doc_type, MaterialSourceType.MIXED_PDF)
        self.assertEqual(result.textual_pages_count, 1)
        self.assertEqual(result.mixed_pages_count, 1)
        self.assertEqual(result.scanned_pages_count, 1)

        # Ordem estrita 1..N preservada
        self.assertEqual(result.pages[0].page_number, 1)
        self.assertEqual(result.pages[0].page_type, PdfPageType.TEXTUAL)

        self.assertEqual(result.pages[1].page_number, 2)
        self.assertEqual(result.pages[1].page_type, PdfPageType.MIXED)
        self.assertEqual(result.pages[1].native_text, "Questão 2: Observe o diagrama óptico.")

        self.assertEqual(result.pages[2].page_number, 3)
        self.assertEqual(result.pages[2].page_type, PdfPageType.SCANNED)
        self.assertEqual(result.pages[2].native_text, "")

        # Texto consolidado reúne páginas com texto na ordem exata
        self.assertIn("Página 1: Introdução", result.consolidated_native_text)
        self.assertIn("Questão 2: Observe o diagrama", result.consolidated_native_text)

    def test_7_confirmar_preservacao_integral_native_text_em_pagina_mista(self) -> None:
        """Regra 1: Garante que caracteres, acentos e termos não sejam truncados em páginas mistas."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

        texto_original = (
            "Instruções Pedagógicas Adaptadas — Avaliação Diagnóstica:\n"
            "1. Leia a questão com atenção antes de responder.\n"
            "2. Identifique os conceitos-chave: fotossíntese, clorofila e glicose.\n"
            "3. Se necessitar de apoio para interpretação visual, consulte o mediador escolar."
        )
        page.insert_text((50, 60), texto_original, fontsize=11)

        img_bytes = self._create_synthetic_image_bytes(300, 200)
        page.insert_image(fitz.Rect(50, 200, 350, 400), stream=img_bytes, keep_proportion=False)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        p = result.pages[0]

        self.assertEqual(p.page_type, PdfPageType.MIXED)
        self.assertIn("fotossíntese, clorofila e glicose", p.native_text)
        self.assertIn("mediador escolar", p.native_text)
        self.assertEqual(p.char_count, len(p.native_text))

    def test_8_imagem_decorativa_minuscula_mantem_pagina_textual(self) -> None:
        """Regra 4 e 6: Pequeno ícone/bullet (< 5%) não classifica a página indevidamente como mista."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        texto = "Texto principal da página explicativa sobre gramática normativa com mais de 80 caracteres úteis."
        page.insert_text((50, 70), texto, fontsize=12)

        # Ícone minúsculo de rodapé (40 x 30 = 1.200 pt² / 500.990 ≈ 0.24% da página)
        img_bytes_tiny = self._create_synthetic_image_bytes(40, 30)
        page.insert_image(fitz.Rect(50, 800, 90, 830), stream=img_bytes_tiny, keep_proportion=False)

        b = doc.tobytes()
        doc.close()

        result = inspect_and_classify_pdf(b)
        p = result.pages[0]

        self.assertEqual(p.page_type, PdfPageType.TEXTUAL)
        self.assertEqual(result.doc_type, MaterialSourceType.PDF)
        self.assertFalse(result.requires_visual_processing)


class TestPdfMemoryAndBBoxGuardsEtapa4B2(unittest.TestCase):
    """Testes obrigatórios da Etapa 4.B2: Travas de Megapixels e Validação Estrita de Bounding Box.

    Garante que renderizações extremas e bboxes corrompidas sejam interceptadas antes de get_pixmap().
    """

    @staticmethod
    def _create_synthetic_pdf(width: float, height: float, pages: int = 1) -> bytes:
        """Gera bytes de um PDF sintético em memória com dimensões de página controladas."""
        doc = fitz.open()
        for _ in range(pages):
            doc.new_page(width=width, height=height)
        b = doc.tobytes()
        doc.close()
        return b

    # ==========================================================================
    # 1. Limite de Megapixels (Cenários 1 a 7)
    # ==========================================================================

    def test_1_renderizacao_abaixo_limite_pixels_aceita(self) -> None:
        """Cenário 1: Página com dimensões normais (A4 a 150 DPI ≈ 2.17M pixels) deve ser renderizada com sucesso."""
        pdf_bytes = self._create_synthetic_pdf(595, 842)
        img = render_pdf_page_image(pdf_bytes, page_number=1, dpi=150)
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (1240, 1755))
        self.assertLess(img.size[0] * img.size[1], MAX_RENDER_PIXELS)

    def test_2_renderizacao_exatamente_no_limite_25m_aceita(self) -> None:
        """Cenário 2: Página exatamente no limite de 25M pixels (5000x5000 pt a 72 DPI = 25.000.000 px) é aceita."""
        pdf_bytes = self._create_synthetic_pdf(5000, 5000)
        png_bytes = render_pdf_page_image(pdf_bytes, page_number=1, dpi=72, as_pil=False)
        self.assertIsInstance(png_bytes, bytes)
        self.assertGreater(len(png_bytes), 0)

    def test_3_renderizacao_acima_limite_25m_rejeitada(self) -> None:
        """Cenário 3: Página que projeta 25.005.000 pixels (5000x5001 pt a 72 DPI) é rejeitada com PdfRenderPixelLimitError."""
        pdf_bytes = self._create_synthetic_pdf(5000, 5001)
        with self.assertRaises(PdfRenderPixelLimitError) as ctx:
            render_pdf_page_image(pdf_bytes, page_number=1, dpi=72)
        self.assertEqual(ctx.exception.code, "PIXEL_LIMIT_EXCEEDED")
        self.assertIn("25,005,000 pixels", str(ctx.exception))

    def test_4_pdf_dimensoes_fisicas_extremas_rejeitado(self) -> None:
        """Cenário 4: Página de 4000x4000 pt a 150 DPI projeta ~69.4M pixels e deve ser rejeitada."""
        pdf_bytes = self._create_synthetic_pdf(4000, 4000)
        with self.assertRaises(PdfRenderPixelLimitError) as ctx:
            render_pdf_page_image(pdf_bytes, page_number=1, dpi=150)
        self.assertEqual(ctx.exception.code, "PIXEL_LIMIT_EXCEEDED")

    def test_5_mock_comprova_que_get_pixmap_nao_e_chamado_ao_estourar_pixels(self) -> None:
        """Cenário 5: Confirma via mock que get_pixmap NÃO é invocado quando o limite de pixels é excedido."""
        pdf_bytes = self._create_synthetic_pdf(5000, 5001)
        with mock.patch.object(fitz.Page, "get_pixmap") as mock_get_pixmap:
            with self.assertRaises(PdfRenderPixelLimitError):
                render_pdf_page_image(pdf_bytes, page_number=1, dpi=72)
            mock_get_pixmap.assert_not_called()

    def test_6_calculo_considera_dpi_solicitado(self) -> None:
        """Cenário 6: Página de 1000x1000 pt é aceita a 72 DPI (1M px) mas rejeitada a 600 DPI (~69.4M px)."""
        pdf_bytes = self._create_synthetic_pdf(1000, 1000)

        # 72 DPI -> 1M pixels (aceita)
        img_72 = render_pdf_page_image(pdf_bytes, page_number=1, dpi=72)
        self.assertEqual(img_72.size, (1000, 1000))

        # 600 DPI -> ~69.4M pixels (rejeitada)
        with self.assertRaises(PdfRenderPixelLimitError) as ctx:
            render_pdf_page_image(pdf_bytes, page_number=1, dpi=600)
        self.assertEqual(ctx.exception.code, "PIXEL_LIMIT_EXCEEDED")

    def test_7_iterador_iter_render_pdf_pages_respeita_limite_pixels(self) -> None:
        """Cenário 7: O gerador iter_render_pdf_pages também valida pixels e lança PdfRenderPixelLimitError."""
        pdf_bytes = self._create_synthetic_pdf(5000, 5001)
        gen = iter_render_pdf_pages(pdf_bytes, dpi=72)
        with self.assertRaises(PdfRenderPixelLimitError):
            next(gen)

    # ==========================================================================
    # 2. Validação Estrita de Bounding Box (Cenários 8 a 16)
    # ==========================================================================

    def test_8_bbox_valida_aceita(self) -> None:
        """Cenário 8: Bbox válida contida nos limites da página deve ser renderizada com sucesso."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)
        img = render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 50, 200, 200), dpi=72)
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (150, 150))

    def test_9_bbox_largura_zero_rejeitada(self) -> None:
        """Cenário 9: Bbox com largura zero (x0 == x1) deve ser rejeitada com PdfInvalidBBoxError."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)
        with self.assertRaises(PdfInvalidBBoxError) as ctx:
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 50, 50, 200))
        self.assertEqual(ctx.exception.code, "INVALID_BBOX")
        self.assertIn("largura > 0", str(ctx.exception))

    def test_10_bbox_altura_zero_rejeitada(self) -> None:
        """Cenário 10: Bbox com altura zero (y0 == y1) deve ser rejeitada com PdfInvalidBBoxError."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)
        with self.assertRaises(PdfInvalidBBoxError) as ctx:
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 50, 200, 50))
        self.assertEqual(ctx.exception.code, "INVALID_BBOX")
        self.assertIn("altura > 0", str(ctx.exception))

    def test_11_bbox_coordenadas_invertidas_rejeitada(self) -> None:
        """Cenário 11: Bbox com coordenadas invertidas (x0 > x1 ou y0 > y1) é rejeitada."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)

        # Invertido em X
        with self.assertRaises(PdfInvalidBBoxError):
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(200, 50, 50, 200))

        # Invertido em Y
        with self.assertRaises(PdfInvalidBBoxError):
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 200, 200, 50))

    def test_12_bbox_com_nan_rejeitada(self) -> None:
        """Cenário 12: Bbox contendo valor NaN deve ser rejeitada antes de fitz.Rect."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)
        with self.assertRaises(PdfInvalidBBoxError) as ctx:
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(float("nan"), 50, 200, 200))
        self.assertEqual(ctx.exception.code, "INVALID_BBOX")
        self.assertIn("NaN ou infinito", str(ctx.exception))

    def test_13_bbox_com_infinito_rejeitada(self) -> None:
        """Cenário 13: Bbox contendo valor infinito deve ser rejeitada antes de fitz.Rect."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)
        with self.assertRaises(PdfInvalidBBoxError) as ctx:
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 50, float("inf"), 200))
        self.assertEqual(ctx.exception.code, "INVALID_BBOX")
        self.assertIn("NaN ou infinito", str(ctx.exception))

    def test_14_bbox_parcialmente_fora_da_pagina_rejeitada(self) -> None:
        """Cenário 14: Bbox que extrapola parcialmente a página (x1 > width) é rejeitada sem clamp silencioso."""
        pdf_bytes = self._create_synthetic_pdf(300, 300)
        # x1 = 350 > 300
        with self.assertRaises(PdfInvalidBBoxError) as ctx:
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(50, 50, 350, 200))
        self.assertEqual(ctx.exception.code, "INVALID_BBOX")
        self.assertIn("extrapola os limites", str(ctx.exception))

    def test_15_bbox_totalmente_fora_da_pagina_rejeitada(self) -> None:
        """Cenário 15: Bbox com coordenadas negativas ou totalmente fora da página é rejeitada."""
        pdf_bytes = self._create_synthetic_pdf(300, 300)

        # Coordenadas negativas
        with self.assertRaises(PdfInvalidBBoxError):
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(-100, -100, -20, -20))

        # Coordenadas além do limite
        with self.assertRaises(PdfInvalidBBoxError):
            render_pdf_region_image(pdf_bytes, page_number=1, bbox=(400, 400, 500, 500))

    def test_16_mock_comprova_que_get_pixmap_nao_e_chamado_com_bbox_invalida(self) -> None:
        """Cenário 16: Confirma via mock que get_pixmap NÃO é invocado em casos de bbox inválida."""
        pdf_bytes = self._create_synthetic_pdf(300, 300)
        with mock.patch.object(fitz.Page, "get_pixmap") as mock_get_pixmap:
            with self.assertRaises(PdfInvalidBBoxError):
                render_pdf_region_image(pdf_bytes, page_number=1, bbox=(200, 50, 50, 200))
            mock_get_pixmap.assert_not_called()

    def test_17_dpi_invalido_zero_negativo_nan_inf_rejeitado_sem_get_pixmap(self) -> None:
        """Auditoria complementar: DPI zero, negativo, NaN e infinito devem ser rejeitados com code='INVALID_DPI'."""
        pdf_bytes = self._create_synthetic_pdf(300, 300)
        casos_dpi = [0, -72, float("nan"), float("inf")]

        for dpi_invalido in casos_dpi:
            with self.subTest(dpi=dpi_invalido):
                with mock.patch.object(fitz.Page, "get_pixmap") as mock_get_pixmap:
                    with self.assertRaises(PdfRenderError) as ctx:
                        render_pdf_page_image(pdf_bytes, page_number=1, dpi=dpi_invalido)
                    self.assertEqual(ctx.exception.code, "INVALID_DPI")
                    mock_get_pixmap.assert_not_called()

    def test_18_max_pixels_invalido_rejeitado(self) -> None:
        """Auditoria complementar: max_pixels zero, negativo, NaN, inf e booleano devem ser rejeitados."""
        rect = fitz.Rect(0, 0, 100, 100)
        casos_max = [0, -1000, float("nan"), float("inf"), True, False]

        for max_invalido in casos_max:
            with self.subTest(max_pixels=max_invalido):
                with self.assertRaises(PdfRenderError) as ctx:
                    validate_and_calculate_render_dimensions(rect, dpi=72, max_pixels=max_invalido)
                self.assertEqual(ctx.exception.code, "INVALID_MAX_PIXELS")

    def test_19_bbox_tipos_inesperados_rejeitados_sem_get_pixmap(self) -> None:
        """Auditoria complementar: Tipos inválidos (string, sequência curta, bool, None) são rejeitados antes de get_pixmap."""
        pdf_bytes = self._create_synthetic_pdf(300, 300)
        casos_bbox = [
            "bbox_invalida",
            (10, 20, 30),
            (10, 20, 30, "40"),
            (10, 20, True, 40),
            (10, 20, None, 40),
            [10, 20, 30],
        ]

        for bbox_invalida in casos_bbox:
            with self.subTest(bbox=bbox_invalida):
                with mock.patch.object(fitz.Page, "get_pixmap") as mock_get_pixmap:
                    with self.assertRaises(PdfInvalidBBoxError) as ctx:
                        render_pdf_region_image(pdf_bytes, page_number=1, bbox=bbox_invalida)  # type: ignore[arg-type]
                    self.assertEqual(ctx.exception.code, "INVALID_BBOX")
                    mock_get_pixmap.assert_not_called()

    def test_20_dpi_astronomico_rejeitado_sem_overflow_ou_get_pixmap(self) -> None:
        """Ajustes finais 4.B2: DPIs extremos (10**100, 10**400, 1e300, >10.000) devem ser rejeitados com INVALID_DPI sem OverflowError."""
        pdf_bytes = self._create_synthetic_pdf(300, 300)
        casos_dpi_astronomicos = [10**100, 10**400, 1e300, 15_000, 50_000]

        for dpi_extremo in casos_dpi_astronomicos:
            with self.subTest(dpi=dpi_extremo):
                with mock.patch.object(fitz.Page, "get_pixmap") as mock_get_pixmap:
                    with self.assertRaises(PdfRenderError) as ctx:
                        render_pdf_page_image(pdf_bytes, page_number=1, dpi=dpi_extremo)
                    self.assertEqual(ctx.exception.code, "INVALID_DPI")
                    mock_get_pixmap.assert_not_called()

    def test_21_max_pixels_astronomico_rejeitado_sem_overflow(self) -> None:
        """Ajustes finais 4.B2: max_pixels astronômico (10**100, 10**400, 1e300, >1Gpx) deve ser rejeitado com INVALID_MAX_PIXELS."""
        rect = fitz.Rect(0, 0, 100, 100)
        casos_max_astronomicos = [10**100, 10**400, 1e300, 2_000_000_000]

        for max_extremo in casos_max_astronomicos:
            with self.subTest(max_pixels=max_extremo):
                with self.assertRaises(PdfRenderError) as ctx:
                    validate_and_calculate_render_dimensions(rect, dpi=72, max_pixels=max_extremo)
                self.assertEqual(ctx.exception.code, "INVALID_MAX_PIXELS")

    def test_22_bbox_tolerancia_geometrica_fronteiras(self) -> None:
        """Ajustes finais 4.B2: Validação da tolerância geométrica (tol = 1e-4 pt) em todas as fronteiras da página."""
        pdf_bytes = self._create_synthetic_pdf(500, 500)

        # 1. Imediatamente dentro e exatamente sobre os limites nominais (devem ser aceitos)
        casos_aceitos = [
            (50, 50, 500.0 - 1e-5, 200),  # x1 imediatamente dentro
            (50, 50, 500.0, 200),         # x1 exatamente sobre
            (50, 50, 200, 500.0 - 1e-5),  # y1 imediatamente dentro
            (50, 50, 200, 500.0),         # y1 exatamente sobre
            (1e-5, 50, 200, 200),         # x0 imediatamente dentro
            (0.0, 50, 200, 200),          # x0 exatamente sobre
            (50, 1e-5, 200, 200),         # y0 imediatamente dentro
            (50, 0.0, 200, 200),          # y0 exatamente sobre
        ]
        for bbox in casos_aceitos:
            with self.subTest(cenario="aceito_nominal", bbox=bbox):
                img = render_pdf_region_image(pdf_bytes, page_number=1, bbox=bbox, dpi=72)
                self.assertIsNotNone(img)

        # 2. Na faixa da tolerância float (desvio < 1e-4 pt de precisão IEEE-754: devem ser aceitos)
        casos_tolerancia_aceitos = [
            (50, 50, 500.0 + 5e-5, 200),  # x1 ligeiramente acima pela precisão float
            (-5e-5, 50, 200, 200),         # x0 ligeiramente abaixo de zero pela precisão float
            (50, -5e-5, 200, 200),         # y0 ligeiramente abaixo de zero pela precisão float
            (50, 50, 200, 500.0 + 5e-5),  # y1 ligeiramente acima pela precisão float
        ]
        for bbox in casos_tolerancia_aceitos:
            with self.subTest(cenario="aceito_tolerancia_float", bbox=bbox):
                img = render_pdf_region_image(pdf_bytes, page_number=1, bbox=bbox, dpi=72)
                self.assertIsNotNone(img)

        # 3. Fora da faixa da tolerância (desvio >= 1e-3 pt: devem ser estritamente rejeitados)
        casos_rejeitados = [
            (50, 50, 500.0 + 1e-3, 200),  # x1 fora da tolerância
            (-1e-3, 50, 200, 200),         # x0 fora da tolerância
            (50, -1e-3, 200, 200),         # y0 fora da tolerância
            (50, 50, 200, 500.0 + 1e-3),  # y1 fora da tolerância
        ]
        for bbox in casos_rejeitados:
            with self.subTest(cenario="rejeitado_alem_tolerancia", bbox=bbox):
                with mock.patch.object(fitz.Page, "get_pixmap") as mock_get_pixmap:
                    with self.assertRaises(PdfInvalidBBoxError) as ctx:
                        render_pdf_region_image(pdf_bytes, page_number=1, bbox=bbox, dpi=72)
                    self.assertEqual(ctx.exception.code, "INVALID_BBOX")
                    mock_get_pixmap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
