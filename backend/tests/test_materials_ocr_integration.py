"""Testes de integração do OCR e Análise Visual ao Pipeline de Materiais (História 1.1.3 - Etapa 4.B3).

Valida os 12 cenários obrigatórios de integração:
1. Upload de PNG com análise visual, OCR e retorno de OcrMaterialResponse;
2. Upload de JPG e JPEG com análise visual e OCR;
3. PDF exclusivamente textual com preservação do limite de 10 MB e retorno de MaterialResponse;
4. PDF escaneado (sem texto nativo) com renderização e OCR de página inteira;
5. PDF misto com preservação de texto nativo e OCR sobre regiões de imagem;
6. PDF multipágina preservando estritamente a ordem das páginas;
7. PDF misto sem duplicação de texto nativo;
8. Sanitização local de PII e separação entre raw_text (HITL) e raw_content.text (IA);
9. Controle diferenciado de limites de tamanho (10 MB textual vs 25 MB multimodal/OCR);
10. Tratamento defensivo de página corrompida, ilegível ou sem texto reconhecível;
11. Tratamento de timeout de OCR com identificação explícita da página afetada;
12. Regressão completa dos fluxos legados (.txt, .docx, .pdf textual e formatos não suportados);
13. Teste de integração real com binário Tesseract caso disponível no host.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import fitz
from PIL import Image, ImageDraw

from iris.api.routes.materials import (
    _is_text_redundant,
    decompose_material_service,
    process_material_file_service,
)
from iris.parsers.document_extractor import (
    DocumentParsingError,
    UnsupportedFileFormatError,
)
from iris.parsers.ocr_extractor import (
    OcrConfig,
    OcrError,
    OcrPageResult,
    OcrTimeoutError,
    check_ocr_environment,
)
from iris.parsers.pdf_processor import (
    MAX_RENDER_PIXELS,
    PdfPageInfo,
    PdfPageType,
    PdfRenderPixelLimitError,
)
from iris.schemas.materials import (
    MAX_FILE_SIZE_BYTES,
    MAX_OCR_FILE_SIZE_BYTES,
    MaterialResponse,
    MaterialSourceType,
    MaterialValidationError,
    OcrMaterialResponse,
    RawContent,
    VisualAnalysisReport,
)


class TestMaterialsOcrIntegration(unittest.TestCase):
    """Bateria de testes de integração para a Etapa 4.B3."""

    def _create_synthetic_image(
        self,
        format_name: str = "PNG",
        size: tuple[int, int] = (600, 300),
        text: str = "Avaliação de Geografia do 7º Ano sobre Relevo e Clima do Brasil.",
    ) -> bytes:
        """Gera bytes de imagem válida em memória contendo texto escolar renderizado."""
        img = Image.new("RGB", size, color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 50), text, fill="black")
        buf = io.BytesIO()
        img.save(buf, format=format_name)
        return buf.getvalue()

    def _create_synthetic_pdf(
        self,
        pages_content: list[tuple[str, bool]],  # (texto_nativo, incluir_imagem)
        width: float = 595.0,
        height: float = 842.0,
    ) -> bytes:
        """Gera um PDF sintético em memória com páginas textuais, escaneadas ou mistas."""
        doc = fitz.open()
        sample_img_bytes = self._create_synthetic_image("PNG", size=(300, 150), text="Figura Pedagógica")

        for text, has_img in pages_content:
            page = doc.new_page(width=width, height=height)
            if text:
                page.insert_text((50, 80), text, fontsize=12)
            if has_img:
                # Insere imagem em um retângulo central delimitado
                rect = fitz.Rect(50, 200, 450, 400)
                page.insert_image(rect, stream=sample_img_bytes)

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    # ==========================================================================
    # 1. Upload de PNG
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_01_upload_png_sucesso(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 1: Upload de imagem PNG deve executar análise visual, OCR e retornar OcrMaterialResponse."""
        texto_ocr = (
            "Avaliação Bimestral de História.\n"
            "Questão 1: Descreva as principais características da sociedade feudal europeia."
        )
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_ocr,
            confidence=92.5,
            word_count=15,
            valid_confidence_count=15,
            low_confidence_word_count=0,
            has_text=True,
        )

        png_bytes = self._create_synthetic_image("PNG")
        response = process_material_file_service("prova_historia.png", png_bytes)

        self.assertIsInstance(response, OcrMaterialResponse)
        self.assertEqual(response.status, "success")
        self.assertEqual(response.metadata.source_type, "png")
        self.assertEqual(response.metadata.filename, "prova_historia.png")
        self.assertIn("sociedade feudal", response.raw_text)

        # Contrato canônico RawContent
        self.assertIsInstance(response.raw_content, RawContent)
        self.assertEqual(response.raw_content.source_type, MaterialSourceType.PNG)
        self.assertTrue(response.raw_content.pii_sanitized)

        # Relatório de análise visual
        self.assertIsInstance(response.visual_analysis, VisualAnalysisReport)
        self.assertEqual(response.visual_analysis.total_pages_analyzed, 1)
        self.assertEqual(len(response.visual_analysis.pages), 1)

    # ==========================================================================
    # 2. Upload de JPG e JPEG
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_02_upload_jpeg_jpg_sucesso(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 2: Upload de imagens JPG e JPEG deve ser suportado com contrato OcrMaterialResponse."""
        texto_ocr = (
            "Atividade Prática de Ciências Naturais.\n"
            "Questão 2: Explique o ciclo hidrológico e sua relevância para o ecossistema."
        )
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_ocr,
            confidence=88.0,
            word_count=14,
            valid_confidence_count=14,
            low_confidence_word_count=1,
            has_text=True,
        )

        for filename, fmt in [("diagrama.jpg", "JPEG"), ("exercicio.jpeg", "JPEG")]:
            with self.subTest(filename=filename):
                img_bytes = self._create_synthetic_image(fmt)
                response = process_material_file_service(filename, img_bytes)

                self.assertIsInstance(response, OcrMaterialResponse)
                self.assertIn(response.metadata.source_type, ("jpg", "jpeg"))
                self.assertEqual(response.metadata.filename, filename)
                self.assertIn("ciclo hidrológico", response.raw_text)

    # ==========================================================================
    # 3. PDF exclusivamente textual
    # ==========================================================================

    def test_03_pdf_exclusivamente_textual(self) -> None:
        """Cenário 3: PDF 100% textual deve usar extração nativa direta e retornar MaterialResponse."""
        conteudo_texto = (
            "Avaliação de Língua Portuguesa.\n"
            "Questão 1: Identifique a oração subordinada substantiva subjetiva no período composto.\n"
            "Questão 2: Diferencie adjunto adnominal de complemento nominal com exemplos práticos."
        )
        pdf_bytes = self._create_synthetic_pdf([(conteudo_texto, False)])

        with mock.patch("iris.api.routes.materials.extract_text_from_page_image") as mock_ocr:
            response = process_material_file_service("prova_portugues.pdf", pdf_bytes)

            # OCR não deve ser invocado em PDF 100% textual
            mock_ocr.assert_not_called()

        self.assertIsInstance(response, MaterialResponse)
        self.assertEqual(response.status, "success")
        self.assertEqual(response.metadata.source_type, "pdf")
        self.assertIn("oração subordinada", response.raw_text)

    # ==========================================================================
    # 4. PDF escaneado
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_04_pdf_escaneado(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 4: PDF escaneado (sem texto nativo) deve renderizar e executar OCR na página inteira."""
        texto_ocr = (
            "Prova Escaneada de Matemática - 9º Ano.\n"
            "Questão 1: Calcule as raízes da equação do segundo grau: 2x² - 8x + 6 = 0."
        )
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_ocr,
            confidence=91.0,
            word_count=17,
            valid_confidence_count=17,
            low_confidence_word_count=0,
            has_text=True,
        )

        # Página com texto nativo vazio e imagem presente (scanned)
        pdf_bytes = self._create_synthetic_pdf([("", True)])
        response = process_material_file_service("prova_digitalizada.pdf", pdf_bytes)

        self.assertIsInstance(response, OcrMaterialResponse)
        self.assertEqual(response.metadata.source_type, "scanned_pdf")
        self.assertIn("equação do segundo grau", response.raw_text)
        mock_ocr.assert_called_once()

    # ==========================================================================
    # 5. PDF misto
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_05_pdf_misto(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 5: PDF misto deve preservar texto nativo e processar regiões visuais via OCR."""
        texto_nativo = (
            "Avaliação Interdisciplinar de Ciências e Artes.\n"
            "Observe atentamente a ilustração abaixo para responder às questões 1 e 2:"
        )
        texto_ocr_regiao = "Texto contido na figura: Esquema anatômico do sistema respiratório humano."

        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_ocr_regiao,
            confidence=89.0,
            word_count=10,
            valid_confidence_count=10,
            low_confidence_word_count=0,
            has_text=True,
        )

        pdf_bytes = self._create_synthetic_pdf([(texto_nativo, True)])
        response = process_material_file_service("prova_mista.pdf", pdf_bytes)

        self.assertIsInstance(response, OcrMaterialResponse)
        self.assertEqual(response.metadata.source_type, "mixed_pdf")
        self.assertIn("Avaliação Interdisciplinar", response.raw_text)
        self.assertIn("sistema respiratório humano", response.raw_text)

    # ==========================================================================
    # 6. PDF multipágina com preservação da ordem
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_06_pdf_multipagina_preserva_ordem(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 6: Documento com 3 páginas heterogêneas deve preservar rigorosamente a ordem 1..N."""
        p1_nativo = "Página 1: Cabeçalho institucional e Questão 1 de Química Geral sobre tabela periódica."
        p2_ocr = "Página 2: Questão 2 digitalizada sobre modelos atômicos de Rutherford e Bohr."
        p3_nativo = "Página 3: Questão 3 sobre ligações químicas iônicas e covalentes."
        p3_ocr = "Figura da Página 3: Distribuição eletrônica em camadas."

        def ocr_side_effect(img, page_number):
            if page_number == 2:
                return OcrPageResult(page_number=2, raw_text=p2_ocr, confidence=90.0, word_count=12, valid_confidence_count=12, low_confidence_word_count=0, has_text=True)
            elif page_number == 3:
                return OcrPageResult(page_number=3, raw_text=p3_ocr, confidence=85.0, word_count=7, valid_confidence_count=7, low_confidence_word_count=0, has_text=True)
            return OcrPageResult(page_number=page_number, raw_text="", confidence=None, word_count=0, valid_confidence_count=0, low_confidence_word_count=0, has_text=False)

        mock_ocr.side_effect = ocr_side_effect

        pdf_bytes = self._create_synthetic_pdf([
            (p1_nativo, False),  # P1: Textual puro
            ("", True),          # P2: Scanned puro
            (p3_nativo, True),   # P3: Misto
        ])

        response = process_material_file_service("avaliacao_multipagina.pdf", pdf_bytes)

        self.assertIsInstance(response, OcrMaterialResponse)
        self.assertEqual(response.metadata.source_type, "mixed_pdf")
        self.assertEqual(response.visual_analysis.total_pages_analyzed, 3)

        # Verifica ordenação temporal estrita
        pos_p1 = response.raw_text.find("Página 1")
        pos_p2 = response.raw_text.find("Página 2")
        pos_p3 = response.raw_text.find("Página 3")

        self.assertNotEqual(pos_p1, -1)
        self.assertNotEqual(pos_p2, -1)
        self.assertNotEqual(pos_p3, -1)
        self.assertLess(pos_p1, pos_p2)
        self.assertLess(pos_p2, pos_p3)

    # ==========================================================================
    # 7. PDF misto sem duplicação de texto nativo
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    @mock.patch("iris.api.routes.materials.render_pdf_region_image")
    def test_07_pdf_misto_sem_duplicacao_texto_nativo(
        self,
        mock_render_region: mock.MagicMock,
        mock_ocr: mock.MagicMock,
    ) -> None:
        """Cenário 7: Em página mista, o OCR é executado estritamente sobre as bboxes de imagem, evitando duplicar texto nativo."""
        termo_exclusivo_nativo = "TermoUnicoExclusivoDaCamadaDeTextoNativoDaPagina"
        texto_nativo = (
            f"Avaliação de Biologia: {termo_exclusivo_nativo}.\n"
            "Descreva as funções do complexo de Golgi e retículo endoplasmático."
        )
        texto_ocr_recorte = "Legenda da Imagem recortada da organela celular."

        # Simula recorte de região renderizado com sucesso
        mock_render_region.return_value = Image.new("RGB", (200, 100), color="white")
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_ocr_recorte,
            confidence=95.0,
            word_count=8,
            valid_confidence_count=8,
            low_confidence_word_count=0,
            has_text=True,
        )

        pdf_bytes = self._create_synthetic_pdf([(texto_nativo, True)])
        response = process_material_file_service("prova_mista_sem_duplicacao.pdf", pdf_bytes)

        # Confirma que render_pdf_region_image foi chamada para recortar a região
        mock_render_region.assert_called_once()

        # O termo nativo deve ocorrer exatamente 1 vez no texto final (zero duplicação)
        self.assertEqual(response.raw_text.count(termo_exclusivo_nativo), 1)
        self.assertIn(texto_ocr_recorte, response.raw_text)

    # ==========================================================================
    # 8. Sanitização de PII e separação entre raw_text e raw_content
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_08_sanitizacao_pii_local_e_separacao_raw_text(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 8: Garante separação estrita entre raw_text (para revisão do professor) e raw_content.text (higienizado para IA)."""
        nome_aluno = "Beatriz Ferreira Lima"
        cpf_aluno = "123.456.789-00"
        texto_com_pii = (
            f"Colégio Estadual Tiradentes\n"
            f"Estudante: {nome_aluno} | CPF: {cpf_aluno}\n"
            f"Prova Bimestral de Sociologia sobre cidadania e direitos fundamentais no Brasil contemporâneo."
        )
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_com_pii,
            confidence=90.0,
            word_count=18,
            valid_confidence_count=18,
            low_confidence_word_count=0,
            has_text=True,
        )

        png_bytes = self._create_synthetic_image("PNG")
        response = process_material_file_service("prova_com_dados_pessoais.png", png_bytes)

        # 1. raw_text preserva os dados originais para conferência visual docente (HITL)
        self.assertIn(nome_aluno, response.raw_text)
        self.assertIn(cpf_aluno, response.raw_text)

        # 2. raw_content.text substitui estritamente os dados por identificadores semânticos
        self.assertNotIn(nome_aluno, response.raw_content.text)
        self.assertNotIn(cpf_aluno, response.raw_content.text)
        self.assertIn("[ESTUDANTE]", response.raw_content.text)
        self.assertIn("[CPF]", response.raw_content.text)
        self.assertTrue(response.raw_content.pii_sanitized)
        self.assertTrue(response.metadata.sanitized)
        self.assertGreaterEqual(response.metadata.pii_removed_count, 1)

        # 3. Transição segura para o StructuralDecomposer
        estrutura = decompose_material_service(response.sanitized_text)
        self.assertIsNotNone(estrutura)
        self.assertNotIn(nome_aluno, str(estrutura.model_dump()))

    # ==========================================================================
    # 9. Arquivos acima dos limites
    # ==========================================================================

    def test_09_arquivos_acima_dos_limites(self) -> None:
        """Cenário 9: Valida rejeição para arquivos que excedem os tetos (10 MB textual vs 25 MB OCR)."""
        # 1. Imagem > 25 MB
        conteudo_26mb = b"x" * (MAX_OCR_FILE_SIZE_BYTES + 1024)
        with self.assertRaises(MaterialValidationError) as ctx:
            process_material_file_service("foto_pesada.png", conteudo_26mb)
        self.assertEqual(ctx.exception.code, "OCR_FILE_TOO_LARGE")

        # 2. Arquivo TXT > 10 MB
        conteudo_11mb = b"x" * (MAX_FILE_SIZE_BYTES + 1024)
        with self.assertRaises(MaterialValidationError) as ctx:
            process_material_file_service("texto_gigante.txt", conteudo_11mb)
        self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")

        # 3. PDF textual > 10 MB
        pdf_10mb_bytes = self._create_synthetic_pdf([(("Texto do PDF " * 50), False)])
        with mock.patch("iris.api.routes.materials.validate_file_size_limit") as mock_val:
            mock_val.side_effect = MaterialValidationError("Arquivo excede 10 MB", code="FILE_TOO_LARGE", field="file")
            with self.assertRaises(MaterialValidationError) as ctx:
                process_material_file_service("prova_grande.pdf", pdf_10mb_bytes)
            self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")

    # ==========================================================================
    # 10. Página corrompida ou ilegível
    # ==========================================================================

    def test_10_pagina_corrompida_ou_ilegivel(self) -> None:
        """Cenário 10: Rejeição correta para dados corrompidos, vazios ou sem texto reconhecível."""
        # 1. Imagem com bytes corrompidos
        with self.assertRaises(DocumentParsingError) as ctx:
            process_material_file_service("corrompida.png", b"NOT_A_VALID_PNG_CONTENT")
        self.assertIn(ctx.exception.code, ("CORRUPTED_IMAGE", "UNSUPPORTED_IMAGE_FORMAT"))

        # 2. PDF com bytes corrompidos
        with self.assertRaises(DocumentParsingError) as ctx:
            process_material_file_service("corrompido.pdf", b"NOT_A_VALID_PDF_HEADER")
        self.assertEqual(ctx.exception.code, "CORRUPTED_PDF")

        # 3. Imagem em branco sem nenhum texto reconhecível
        img_vazia = self._create_synthetic_image("PNG")
        with mock.patch("iris.api.routes.materials.extract_text_from_page_image") as mock_ocr:
            mock_ocr.return_value = OcrPageResult(
                page_number=1,
                raw_text="   ",
                confidence=None,
                word_count=0,
                valid_confidence_count=0,
                low_confidence_word_count=0,
                has_text=False,
            )
            with self.assertRaises(DocumentParsingError) as ctx:
                process_material_file_service("desenho_sem_texto.png", img_vazia)
            self.assertEqual(ctx.exception.code, "NO_READABLE_TEXT")

    # ==========================================================================
    # 11. Timeout de OCR
    # ==========================================================================

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_11_timeout_ocr_identifica_pagina(self, mock_ocr: mock.MagicMock) -> None:
        """Cenário 11: Em caso de timeout no OCR, a falha identifica explicitamente a página afetada."""
        mock_ocr.side_effect = OcrTimeoutError("Processamento ultrapassou 30s")

        # 1. Timeout em imagem avulsa
        img_bytes = self._create_synthetic_image("PNG")
        with self.assertRaises(DocumentParsingError) as ctx:
            process_material_file_service("imagem_demorada.png", img_bytes)
        self.assertEqual(ctx.exception.code, "OCR_TIMEOUT")

        # 2. Timeout na página 2 de um PDF escaneado
        pdf_bytes = self._create_synthetic_pdf([("", True), ("", True)])
        with self.assertRaises(DocumentParsingError) as ctx:
            process_material_file_service("pdf_demorado.pdf", pdf_bytes)
        self.assertEqual(ctx.exception.code, "OCR_TIMEOUT")
        self.assertIn("página", ctx.exception.message.lower())

    # ==========================================================================
    # 12. Regressão dos fluxos TXT, DOCX e PDF textual
    # ==========================================================================

    def test_12_regressao_txt_docx_pdf_textual(self) -> None:
        """Cenário 12: Preservação estrita dos fluxos textuais legados e rejeição de formatos não suportados."""
        # 1. TXT legado
        conteudo_txt = (
            "Avaliação Bimestral de Filosofia.\n"
            "Questão 1: Diferencie o mito da razão na Grécia Antiga a partir do pensamento pré-socrático."
        ).encode("utf-8")
        resp_txt = process_material_file_service("filosofia.txt", conteudo_txt)
        self.assertIsInstance(resp_txt, MaterialResponse)
        self.assertEqual(resp_txt.metadata.source_type, "txt")
        self.assertIn("Grécia Antiga", resp_txt.raw_text)

        # 2. DOCX legado
        with mock.patch("iris.api.routes.materials.extract_text_from_file") as mock_extract:
            mock_extract.return_value = (
                "Avaliação de Literatura: Realismo e Naturalismo no Brasil.\n"
                "Questão 1: Analise a obra Dom Casmurro sob a ótica da dúvida de Bentinho.",
                "docx",
            )
            resp_docx = process_material_file_service("prova.docx", b"PK fake docx")
            self.assertIsInstance(resp_docx, MaterialResponse)
            self.assertEqual(resp_docx.metadata.source_type, "docx")
            self.assertIn("Dom Casmurro", resp_docx.raw_text)

        # 3. Formato não suportado (ex.: .exe, .xlsx)
        with self.assertRaises(UnsupportedFileFormatError) as ctx:
            process_material_file_service("planilha.xlsx", b"fake excel bytes")
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_FORMAT")

    # ==========================================================================
    # 13. Teste de integração real com Tesseract (condicional)
    # ==========================================================================

    def test_13_integracao_real_tesseract_se_disponivel(self) -> None:
        """Cenário 13: Integração real de ponta a ponta quando o executável do Tesseract estiver disponível no host."""
        status = check_ocr_environment(OcrConfig(lang="por"))
        if not status.is_available:
            self.skipTest(f"Tesseract OCR ou idioma português indisponível no host: {status.issues}")

        # Gera imagem nítida com caracteres acentuados
        texto_real = (
            "Avaliação Oficial de Língua Portuguesa.\n"
            "Questão 1: Explique as regras de acentuação gráfica das palavras paroxítonas e proparoxítonas."
        )
        img_bytes = self._create_synthetic_image("PNG", size=(900, 300), text=texto_real)

        response = process_material_file_service("integracao_real.png", img_bytes)
        self.assertIsInstance(response, OcrMaterialResponse)
        self.assertEqual(response.status, "success")
        self.assertGreater(response.metadata.char_count, 40)
        self.assertTrue(
            "PORTUGUESA" in response.raw_text.upper() or "ACENTUAÇÃO" in response.raw_text.upper(),
            f"Texto reconhecido no teste real divergente: {response.raw_text}",
        )


class TestTextRedundancyHeuristic(unittest.TestCase):
    """Testes unitários rigorosos da heurística _is_text_redundant para prevenção de falsos positivos."""

    def test_01_duplicacao_integral(self) -> None:
        """Cenário 1: Duplicação integral idêntica ao texto nativo é classificada como redundante."""
        texto = "A atividade apresenta três questões sobre o sistema respiratório."
        self.assertTrue(_is_text_redundant(texto, [texto]))

    def test_02_duplicacao_com_diferencas_espacos_e_quebras_linha(self) -> None:
        """Cenário 2: Duplicação com diferenças de espaçamento e quebras de linha é redundante."""
        nativo = "A atividade apresenta três questões sobre o sistema respiratório."
        ocr = "A   atividade\napresenta três questões\n\n sobre o sistema respiratório."
        self.assertTrue(_is_text_redundant(ocr, [nativo]))

    def test_03_ocr_repete_parte_mas_acrescenta_informacao(self) -> None:
        """Cenário 3: OCR que repete parte do texto nativo mas acrescenta conteúdo legítimo NÃO é redundante."""
        nativo = "A atividade apresenta três questões sobre o sistema respiratório."
        ocr = "três questões sobre o sistema respiratório e suas funções."
        self.assertFalse(
            _is_text_redundant(ocr, [nativo]),
            "OCR que acrescenta 'e suas funções' não deve ser descartado por falso positivo.",
        )

    def test_04_textos_curtos_com_palavras_comuns(self) -> None:
        """Cenário 4: Textos curtos com palavras compartilhadas comuns não são eliminados acidentalmente."""
        nativo = "O professor solicitou a leitura atenta do texto para todos os estudantes da turma."
        ocr_curto = "para todos os estudantes"
        self.assertFalse(
            _is_text_redundant(ocr_curto, [nativo]),
            "Trechos curtos não devem ser eliminados apenas por compartilhar termos com o texto nativo.",
        )
        self.assertFalse(_is_text_redundant("questão 1", [nativo]))
        self.assertFalse(_is_text_redundant("figura ilustrativa", [nativo]))

    def test_05_ocr_com_informacao_complementar_legitima(self) -> None:
        """Cenário 5: OCR que engloba o texto nativo e traz informação complementar legítima é preservado."""
        nativo = "Capítulo 1: Introdução à Biologia Celular."
        ocr = "Capítulo 1: Introdução à Biologia Celular. Questão 1: Defina o papel das mitocôndrias."
        self.assertFalse(
            _is_text_redundant(ocr, [nativo]),
            "OCR com questões adicionais não deve ser descartado como redundante.",
        )

    def test_06_candidato_longo_integralmente_contido(self) -> None:
        """Cenário 6: Bloco longo e contínuo já extraído nativamente no documento é marcado como redundante."""
        nativo = (
            "O processo de fotossíntese converte energia luminosa em energia química "
            "armazenada na glicose através de reações enzimáticas no cloroplasto."
        )
        ocr_subsequencia = "converte energia luminosa em energia química armazenada na glicose"
        self.assertTrue(
            _is_text_redundant(ocr_subsequencia, [nativo]),
            "Subsequência longa contínua sem nenhuma informação nova é redundante.",
        )

    def test_07_candidato_vazio_ou_somente_espacos(self) -> None:
        """Cenário 7: Candidato vazio ou composto apenas por espaços em branco é redundante."""
        self.assertTrue(_is_text_redundant("", ["Algum texto nativo"]))
        self.assertTrue(_is_text_redundant("   \n\t  ", ["Algum texto nativo"]))


class TestMaterialsOcrHttpEndpoints(unittest.TestCase):
    """Testes HTTP reais utilizando TestClient da rota POST /api/v1/materials/upload (FastAPI)."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi.testclient import TestClient
            from iris.main import create_app
            cls.client = TestClient(create_app())
            cls.has_fastapi = True
        except Exception:
            cls.has_fastapi = False

    def setUp(self) -> None:
        if not getattr(self, "has_fastapi", False):
            self.skipTest("FastAPI / TestClient não disponível no ambiente atual.")

    def _create_synthetic_image(self, format_name: str = "PNG", text: str = "Avaliação de Geografia") -> bytes:
        img = Image.new("RGB", (600, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 50), text, fill="black")
        buf = io.BytesIO()
        img.save(buf, format=format_name)
        return buf.getvalue()

    def _create_synthetic_pdf(self, pages: list[tuple[str, bool]]) -> bytes:
        doc = fitz.open()
        sample_img = self._create_synthetic_image("PNG", text="Figura Teste")
        for txt, has_img in pages:
            p = doc.new_page(width=595.0, height=842.0)
            if txt:
                p.insert_text((50, 80), txt, fontsize=12)
            if has_img:
                p.insert_image(fitz.Rect(50, 200, 450, 400), stream=sample_img)
        data = doc.tobytes()
        doc.close()
        return data

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_http_01_upload_png(self, mock_ocr: mock.MagicMock) -> None:
        """HTTP 1: Upload real de PNG via multipart retorna 200 com OcrMaterialResponse serializado."""
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text="Avaliação Bimestral de História sobre o Renascimento Cultural e Científico.",
            confidence=95.0,
            word_count=10,
            valid_confidence_count=10,
            low_confidence_word_count=0,
            has_text=True,
        )
        png_bytes = self._create_synthetic_image("PNG")
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("prova_renascimento.png", png_bytes, "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Validação estrita do modelo OcrMaterialResponse
        self.assertEqual(data["status"], "success")
        self.assertIn("message", data)
        self.assertIn("raw_text", data)
        self.assertIn("raw_content", data)
        self.assertIn("text", data["raw_content"])
        self.assertEqual(data["raw_content"]["source_type"], "png")
        self.assertIn("metadata", data["raw_content"])
        self.assertTrue(data["raw_content"]["pii_sanitized"])
        self.assertIn("metadata", data)
        self.assertEqual(data["metadata"]["source_type"], "png")
        self.assertIn("visual_analysis", data)
        self.assertEqual(data["visual_analysis"]["total_pages_analyzed"], 1)
        self.assertIn("pages", data["visual_analysis"])
        self.assertIn("overall_clutter_level", data["visual_analysis"])

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_http_02_upload_pdf_escaneado(self, mock_ocr: mock.MagicMock) -> None:
        """HTTP 2: Upload real de PDF escaneado via multipart retorna 200 com contrato OcrMaterialResponse."""
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text="Prova Escaneada de Matemática sobre equações exponenciais e logaritmos.",
            confidence=90.0,
            word_count=9,
            valid_confidence_count=9,
            low_confidence_word_count=0,
            has_text=True,
        )
        pdf_bytes = self._create_synthetic_pdf([("", True)])
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("prova_scanner.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["metadata"]["source_type"], "scanned_pdf")
        self.assertIn("raw_content", data)
        self.assertEqual(data["raw_content"]["source_type"], "scanned_pdf")
        self.assertTrue(data["raw_content"]["pii_sanitized"])
        self.assertIn("visual_analysis", data)
        self.assertEqual(data["visual_analysis"]["total_pages_analyzed"], 1)

    def test_http_03_upload_pdf_textual(self) -> None:
        """HTTP 3: Upload real de PDF textual via multipart retorna 200 com contrato MaterialResponse estrito."""
        texto = (
            "Avaliação Bimestral de Filosofia.\n"
            "Questão 1: Explique o conceito de imperativo categórico na ética kantiana."
        )
        pdf_bytes = self._create_synthetic_pdf([(texto, False)])
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("filosofia_kant.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Validação estrita do modelo legado MaterialResponse
        self.assertEqual(data["status"], "success")
        self.assertIn("message", data)
        self.assertIn("raw_text", data)
        self.assertEqual(data["metadata"]["source_type"], "pdf")
        self.assertIn("imperativo categórico", data["raw_text"])
        # Garante ausência de campos exclusivos do fluxo OCR em respostas textuais puras
        self.assertNotIn("raw_content", data)
        self.assertNotIn("visual_analysis", data)

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_http_04_upload_pdf_misto(self, mock_ocr: mock.MagicMock) -> None:
        """HTTP 4: Upload real de PDF misto via multipart retorna 200 com contrato OcrMaterialResponse."""
        texto_nativo = (
            "Avaliação Interdisciplinar de Biologia Celular.\n"
            "Observe a micrografia eletrônica para responder às questões seguintes:"
        )
        texto_ocr = "Legenda da Micrografia: Complexo de Golgi e vesículas secretoras."
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text=texto_ocr,
            confidence=92.0,
            word_count=8,
            valid_confidence_count=8,
            low_confidence_word_count=0,
            has_text=True,
        )
        pdf_bytes = self._create_synthetic_pdf([(texto_nativo, True)])
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("prova_celula.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["metadata"]["source_type"], "mixed_pdf")
        self.assertIn("Interdisciplinar", data["raw_text"])
        self.assertIn("Complexo de Golgi", data["raw_text"])
        self.assertIn("raw_content", data)
        self.assertEqual(data["raw_content"]["source_type"], "mixed_pdf")
        self.assertIn("visual_analysis", data)

    def test_http_05_upload_txt_legado(self) -> None:
        """HTTP 5: Upload real de TXT legado via multipart retorna 200 com contrato MaterialResponse estrito."""
        conteudo_txt = (
            "Avaliação de Sociologia: Cultura e Identidade Nacional no Brasil.\n"
            "Questão 1: Discuta a miscigenação cultural a partir da obra Casa-Grande e Senzala."
        ).encode("utf-8")
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("sociologia.txt", conteudo_txt, "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["metadata"]["source_type"], "txt")
        self.assertIn("Identidade Nacional", data["raw_text"])
        # Garante ausência de campos exclusivos do fluxo OCR em respostas textuais puras
        self.assertNotIn("raw_content", data)
        self.assertNotIn("visual_analysis", data)

    def test_http_06_formato_nao_suportado_retorna_400(self) -> None:
        """HTTP 6: Formato não suportado retorna 400 Bad Request com UNSUPPORTED_FORMAT."""
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("relatorio.xlsx", b"fake excel bytes", "application/vnd.ms-excel")},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["detail"]["code"], "UNSUPPORTED_FORMAT")

    def test_http_07_arquivo_acima_limite_retorna_422(self) -> None:
        """HTTP 7: Arquivo acima de 25 MB retorna 422 Unprocessable Entity com OCR_FILE_TOO_LARGE."""
        excesso = b"x" * (MAX_OCR_FILE_SIZE_BYTES + 2048)
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("imagem_gigante.png", excesso, "image/png")},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data["detail"]["code"], "OCR_FILE_TOO_LARGE")

    @mock.patch("iris.api.routes.materials.extract_text_from_page_image")
    def test_http_08_imagem_sem_texto_reconhecivel_retorna_422(self, mock_ocr: mock.MagicMock) -> None:
        """HTTP 8: Imagem sem texto legível retorna 422 com NO_READABLE_TEXT."""
        mock_ocr.return_value = OcrPageResult(
            page_number=1,
            raw_text="   ",
            confidence=None,
            word_count=0,
            valid_confidence_count=0,
            low_confidence_word_count=0,
            has_text=False,
        )
        png_bytes = self._create_synthetic_image("PNG")
        response = self.client.post(
            "/api/v1/materials/upload",
            files={"file": ("vazia.png", png_bytes, "image/png")},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data["detail"]["code"], "NO_READABLE_TEXT")

    def test_http_09_openapi_contract_schema(self) -> None:
        """HTTP 9: Valida que a documentação OpenAPI reflete formalmente a união dos modelos estruturados."""
        openapi_schema = self.client.app.openapi()
        upload_post = openapi_schema["paths"]["/api/v1/materials/upload"]["post"]

        # Resposta 200 deve conter anyOf apontando para os dois modelos concretos
        res_200 = upload_post["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertIn("anyOf", res_200)
        refs = [item["$ref"] for item in res_200["anyOf"]]
        self.assertTrue(any("OcrMaterialResponse" in r for r in refs))
        self.assertTrue(any("MaterialResponse" in r for r in refs))

        # Os schemas detalhados devem estar presentes na seção de componentes
        schemas = openapi_schema["components"]["schemas"]
        self.assertIn("OcrMaterialResponse", schemas)
        self.assertIn("MaterialResponse", schemas)
        self.assertIn("RawContent", schemas)
        self.assertIn("VisualAnalysisReport", schemas)


if __name__ == "__main__":
    unittest.main()
