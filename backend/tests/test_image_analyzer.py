"""Testes unitários do módulo de análise visual por página (image_analyzer.py).

História 1.1.3 - RF-03 (Etapa 2).

Valida:
1. Validações de segurança, limites de tamanho e entradas vazias.
2. Comportamento defensivo quando Pillow não está instalado (ImageDependencyError).
3. Testes reais com imagens sintéticas geradas em memória (via Pillow):
   - Página predominantemente branca (respiro alto, densidade baixa).
   - Página com texto distribuído (respiro e densidade moderados).
   - Página com alta concentração de elementos gráficos (alta densidade, respiro baixo).
   - Página com contraste reduzido (faixa dinâmica interpercentil baixa, sem rotulagem indevida de ilegibilidade).
   - Limitações de whitespace_ratio (fundo colorido/acinzentado vazio vs. texto distribuído).
   - Imagens corrompidas ou malformadas (CorruptedImageError).
   - Imagens com dimensões abaixo do mínimo técnico (low_resolution).
   - Imagens grandes com redimensionamento defensivo preservando dimensões originais.
   - Imagens excedendo o total de pixels defensivo (ImageTooLargeError).
   - Consistência matemática das métricas no intervalo [0.0, 1.0].
   - Compatibilidade de schema com PageVisualAnalysis e VisualAnalysisReport.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Isolamento defensivo para pydantic (schemas/adaptation) em ambientes sem o pacote instalado
if "pydantic" not in sys.modules:
    sys.modules["pydantic"] = MagicMock()

TEST_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEST_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Verificação da disponibilidade real do Pillow no ambiente
try:
    from PIL import Image, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]

from iris.parsers.image_analyzer import (
    CorruptedImageError,
    EmptyImageError,
    ImageAnalysisError,
    ImageDependencyError,
    ImageTooLargeError,
    InvalidImageDimensionsError,
    UnsupportedImageFormatError,
    VisualClutterConfig,
    analyze_page_image,
    calculate_contrast_ratio,
    calculate_edge_density,
    calculate_whitespace_ratio,
    classify_clutter,
    consolidate_visual_report,
    determine_legibility_status,
)
from iris.schemas.materials import PageVisualAnalysis, VisualAnalysisReport


class TestImageAnalyzer(unittest.TestCase):
    """Bateria de testes unitários para o analisador visual de páginas didáticas."""

    # ==========================================================================
    # 1. Testes de Validação e Limites (Executam independentemente do Pillow)
    # ==========================================================================

    def test_analise_imagem_none_lanca_empty_image_error(self) -> None:
        """Fornecer None deve lançar EmptyImageError."""
        with self.assertRaises(EmptyImageError) as ctx:
            analyze_page_image(None)
        self.assertEqual(ctx.exception.code, "EMPTY_IMAGE")

    def test_analise_imagem_vazia_bytes_lanca_empty_image_error(self) -> None:
        """Fornecer b'' (0 bytes) deve lançar EmptyImageError."""
        with self.assertRaises(EmptyImageError) as ctx:
            analyze_page_image(b"")
        self.assertEqual(ctx.exception.code, "EMPTY_IMAGE")

    def test_analise_imagem_excede_limite_bytes_lanca_image_too_large(self) -> None:
        """Arquivo com tamanho binário superior a max_bytes deve lançar ImageTooLargeError."""
        config_restrito = VisualClutterConfig(max_bytes=1024)  # 1 KB
        bytes_grandes = b"x" * 2048

        with self.assertRaises(ImageTooLargeError) as ctx:
            analyze_page_image(bytes_grandes, config=config_restrito)
        self.assertEqual(ctx.exception.code, "IMAGE_TOO_LARGE")

    def test_visual_clutter_config_valores_padrao_e_imutabilidade(self) -> None:
        """VisualClutterConfig deve ser imutável (frozen) e possuir valores coerentes."""
        cfg = VisualClutterConfig()
        self.assertEqual(cfg.max_bytes, 25 * 1024 * 1024)
        self.assertEqual(cfg.min_dimension_px, 150)
        self.assertEqual(cfg.max_dimension_px, 10_000)
        self.assertEqual(cfg.max_total_pixels, 25_000_000)
        self.assertEqual(cfg.downscale_max_dimension, 2_000)
        self.assertAlmostEqual(cfg.edge_density_low, 0.08)
        self.assertAlmostEqual(cfg.edge_density_high, 0.22)
        self.assertAlmostEqual(cfg.whitespace_min_ok, 0.45)

        # Imutabilidade estrita
        with self.assertRaises(Exception):
            cfg.max_bytes = 100  # type: ignore[misc]

    def test_determine_legibility_status_logica_tecnica(self) -> None:
        """determine_legibility_status deve sinalizar low_resolution e alertar contraste sem concluir unreadable."""
        cfg = VisualClutterConfig(min_dimension_px=150, contrast_low_threshold=0.25)

        # 1. Dimensão abaixo do mínimo técnico -> low_resolution
        status, reason = determine_legibility_status(100, 200, 0.80, cfg)
        self.assertEqual(status, "low_resolution")
        self.assertIsNotNone(reason)
        self.assertIn("inferiores ao limite mínimo", reason or "")

        # 2. Dimensões válidas e contraste alto -> ok sem rejection_reason
        status_ok, reason_ok = determine_legibility_status(800, 1000, 0.85, cfg)
        self.assertEqual(status_ok, "ok")
        self.assertIsNone(reason_ok)

        # 3. Dimensões válidas e contraste baixo -> ok, com rejection_reason=None (baixo contraste não é rejeição de processamento)
        status_contraste, reason_contraste = determine_legibility_status(800, 1000, 0.15, cfg)
        self.assertEqual(status_contraste, "ok")
        self.assertIsNone(reason_contraste)

    def test_classify_clutter_heuristica_preliminar(self) -> None:
        """classify_clutter deve retornar níveis baixa, moderada e alta de forma estritamente indicativa."""
        cfg = VisualClutterConfig()

        # Baixa densidade com bom respiro de pixels claros
        level_baixa, possible_baixa = classify_clutter(0.04, 0.85, cfg)
        self.assertEqual(level_baixa, "baixa")
        self.assertFalse(possible_baixa)

        # Moderada
        level_mod, possible_mod = classify_clutter(0.12, 0.65, cfg)
        self.assertEqual(level_mod, "moderada")
        self.assertFalse(possible_mod)

        # Alta por densidade de bordas extrema
        level_alta, possible_alta = classify_clutter(0.28, 0.50, cfg)
        self.assertEqual(level_alta, "alta")
        self.assertFalse(possible_alta)  # respiro ainda ok (>= 0.45)

        # Alta com indicativo de possível poluição visual (alta densidade + baixo respiro de pixels claros)
        level_clutter, possible_clutter = classify_clutter(0.25, 0.30, cfg)
        self.assertEqual(level_clutter, "alta")
        self.assertTrue(possible_clutter)

    def test_consolidate_visual_report_sem_paginas(self) -> None:
        """consolidate_visual_report com lista vazia deve retornar relatório zerado."""
        report = consolidate_visual_report([])
        self.assertEqual(report.total_pages_analyzed, 0)
        self.assertEqual(report.overall_clutter_level, "baixa")
        self.assertFalse(report.has_high_clutter)
        self.assertEqual(report.flagged_pages, [])
        self.assertIn("Nenhuma página", report.notes or "")

    def test_consolidate_visual_report_com_paginas(self) -> None:
        """consolidate_visual_report deve consolidar níveis e sinalizar páginas com densidade alta."""
        p1 = PageVisualAnalysis(
            page_number=1,
            page_type="scanned",
            width=1000,
            height=1400,
            edge_density=0.06,
            whitespace_ratio=0.82,
            contrast_ratio=0.80,
            clutter_level="baixa",
            possible_visual_clutter=False,
            legibility_status="ok",
        )
        p2 = PageVisualAnalysis(
            page_number=2,
            page_type="scanned",
            width=1000,
            height=1400,
            edge_density=0.26,
            whitespace_ratio=0.38,
            contrast_ratio=0.18,
            clutter_level="alta",
            possible_visual_clutter=True,
            legibility_status="ok",
        )

        report = consolidate_visual_report([p1, p2])
        self.assertEqual(report.total_pages_analyzed, 2)
        self.assertEqual(report.overall_clutter_level, "alta")
        self.assertTrue(report.has_high_clutter)
        self.assertEqual(report.flagged_pages, [2])
        self.assertIn("alta concentração", report.notes or "")

        # 1. Página com contraste reduzido permanece com legibility_status="ok"
        self.assertEqual(p2.legibility_status, "ok")

        # 2. rejection_reason permanece rigorosamente None (não é falha de processamento)
        self.assertIsNone(p2.rejection_reason)

        # 3. Observação orientativa sobre contraste reduzido gerada no relatório
        self.assertIn("contraste global reduzido: [2]", report.notes or "")
        self.assertIn("conferência visual docente sobre nitidez do texto", report.notes or "")

        # 4. A observação NÃO afirma que a página é ilegível
        self.assertNotIn("ilegível", (report.notes or "").lower())
        self.assertNotIn("unreadable", (report.notes or "").lower())

    def test_analise_sem_pillow_lanca_image_dependency_error(self) -> None:
        """Quando o Pillow não está disponível, deve lançar ImageDependencyError."""
        if not HAS_PILLOW:
            with self.assertRaises(ImageDependencyError) as ctx:
                analyze_page_image(b"conteudo_qualquer_sem_pillow")
            self.assertEqual(ctx.exception.code, "LIBRARY_NOT_AVAILABLE")

    # ==========================================================================
    # 2. Testes de Processamento Real com Imagens Sintéticas (Exigem Pillow)
    # ==========================================================================

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_pagina_predominantemente_branca(self) -> None:
        """Página branca sintética deve apresentar alto whitespace_ratio e baixíssima densidade de bordas."""
        img = Image.new("RGB", (400, 600), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Poucas linhas representando um cabeçalho simples
        draw.line([(50, 50), (350, 50)], fill=(0, 0, 0), width=2)
        draw.line([(50, 70), (250, 70)], fill=(0, 0, 0), width=2)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        analysis = analyze_page_image(image_bytes, page_number=1, page_type="scanned")

        self.assertEqual(analysis.page_number, 1)
        self.assertEqual(analysis.width, 400)
        self.assertEqual(analysis.height, 600)
        self.assertGreaterEqual(analysis.whitespace_ratio, 0.90)
        self.assertLess(analysis.edge_density, 0.05)
        self.assertEqual(analysis.clutter_level, "baixa")
        self.assertFalse(analysis.possible_visual_clutter)
        self.assertEqual(analysis.legibility_status, "ok")

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_pagina_com_texto_distribuido(self) -> None:
        """Página com texto distribuído regular deve apresentar respiro e densidade moderados."""
        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Desenha 25 linhas horizontais simulando parágrafos didáticos regulares
        for y in range(60, 740, 26):
            draw.line([(50, y), (550, y)], fill=(20, 20, 20), width=4)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        analysis = analyze_page_image(image_bytes, page_number=1)

        self.assertGreater(analysis.whitespace_ratio, 0.60)
        self.assertLess(analysis.whitespace_ratio, 0.95)
        self.assertLess(analysis.edge_density, 0.20)
        self.assertIn(analysis.clutter_level, ("baixa", "moderada"))
        self.assertFalse(analysis.possible_visual_clutter)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_pagina_alta_concentracao_elementos_graficos(self) -> None:
        """Página densamente preenchida por padrões gráficos deve apresentar alta densidade de bordas."""
        img = Image.new("RGB", (400, 400), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Grade muito densa de linhas cruzadas (alta frequência espacial e baixa proporção de claros)
        for i in range(0, 400, 6):
            draw.line([(i, 0), (i, 400)], fill=(0, 0, 0), width=3)
            draw.line([(0, i), (400, i)], fill=(0, 0, 0), width=3)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        analysis = analyze_page_image(image_bytes, page_number=1)

        self.assertGreater(analysis.edge_density, 0.20)
        self.assertLess(analysis.whitespace_ratio, 0.45)
        self.assertEqual(analysis.clutter_level, "alta")
        self.assertTrue(analysis.possible_visual_clutter)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_pagina_com_contraste_reduzido(self) -> None:
        """Página com baixo contraste deve registrar contrast_ratio reduzido sem rotular como unreadable nem rejeitar."""
        # Imagem com tons estreitos de cinza (120 a 140)
        img = Image.new("RGB", (300, 300), color=(130, 130, 130))
        draw = ImageDraw.Draw(img)
        for y in range(40, 260, 20):
            draw.line([(40, y), (260, y)], fill=(120, 120, 120), width=2)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        analysis = analyze_page_image(image_bytes, page_number=1)

        # 1. Amplitude interpercentil muito baixa detectada quantitativamente
        self.assertLess(analysis.contrast_ratio, 0.20)

        # 2. Conforme Item 3 da Auditoria: status permanece 'ok' e rejection_reason é estritamente None
        self.assertEqual(analysis.legibility_status, "ok")
        self.assertIsNone(analysis.rejection_reason)

        # 3. A observação orientativa sobre o contraste é consolidada no VisualAnalysisReport.notes
        report = consolidate_visual_report([analysis])
        self.assertIsNotNone(report.notes)
        self.assertIn("contraste global reduzido: [1]", report.notes or "")

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_limitacoes_whitespace_ratio_fundo_colorido_e_ilustracao(self) -> None:
        """Evidencia limitações do whitespace_ratio: fundo cinza claro vazio gera whitespace_ratio=0.0."""
        # Imagem completamente vazia/espaçosa, mas com fundo cinza (luminância 220, abaixo de 240)
        img_fundo_cinza = Image.new("RGB", (300, 300), color=(220, 220, 220))
        buf = io.BytesIO()
        img_fundo_cinza.save(buf, format="PNG")

        analysis = analyze_page_image(buf.getvalue(), page_number=1)

        # A página está vazia, mas como os pixels não atingem 240, whitespace_ratio é 0.0
        self.assertEqual(analysis.whitespace_ratio, 0.0)
        # A densidade de bordas no interior é 0.0 (apenas transição mínima na margem externa se houver)
        self.assertLessEqual(analysis.edge_density, 0.02)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_imagem_corrompida_lanca_corrupted_image_error(self) -> None:
        """Bytes que não representam imagem válida devem lançar CorruptedImageError."""
        bytes_corrompidos = b"NAO_E_UMA_IMAGEM_VALIDA_HEADER_CORROMPIDO_123456789"
        with self.assertRaises(CorruptedImageError) as ctx:
            analyze_page_image(bytes_corrompidos)
        self.assertEqual(ctx.exception.code, "CORRUPTED_IMAGE")

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_imagem_formatos_oficiais_e_rejeicao_de_formatos_nao_suportados(self) -> None:
        """Deve aceitar os formatos oficiais (PNG, JPEG/JPG) e rejeitar outros formatos como BMP, GIF e WEBP."""
        # 1. PNG suportado
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        buf_png = io.BytesIO()
        img.save(buf_png, format="PNG")
        res_png = analyze_page_image(buf_png.getvalue())
        self.assertEqual(res_png.width, 200)

        # 2. JPEG suportado
        buf_jpg = io.BytesIO()
        img.save(buf_jpg, format="JPEG")
        res_jpg = analyze_page_image(buf_jpg.getvalue())
        self.assertEqual(res_jpg.width, 200)

        # 3. Formato decodificável pelo Pillow mas fora do contrato da história (BMP) deve ser rejeitado
        buf_bmp = io.BytesIO()
        img.save(buf_bmp, format="BMP")
        with self.assertRaises(UnsupportedImageFormatError) as ctx:
            analyze_page_image(buf_bmp.getvalue())
        self.assertIn("BMP", str(ctx.exception))
        self.assertIn("JPEG, JPG, PNG", str(ctx.exception))

        # 4. Formato arbitrário / desconhecido
        img_mock = Image.new("RGB", (200, 200), color=(255, 255, 255))
        img_mock.format = "XYZ_DESCONHECIDO"
        with self.assertRaises(UnsupportedImageFormatError):
            analyze_page_image(img_mock)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_imagem_baixa_resolucao_status_low_resolution(self) -> None:
        """Imagem com largura ou altura abaixo de min_dimension_px deve receber status low_resolution."""
        img_pequena = Image.new("RGB", (100, 120), color=(255, 255, 255))
        buf = io.BytesIO()
        img_pequena.save(buf, format="PNG")

        analysis = analyze_page_image(buf.getvalue(), page_number=1)

        self.assertEqual(analysis.legibility_status, "low_resolution")
        self.assertIsNotNone(analysis.rejection_reason)
        self.assertIn("inferiores ao limite mínimo", analysis.rejection_reason or "")

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_imagem_grande_redimensionamento_preserva_dimensoes_originais(self) -> None:
        """Imagem com dimensão acima do limite de redimensionamento deve manter dimensões originais no resultado."""
        # Cria imagem 2200x2400 (acima do downscale_max_dimension de 2000px)
        img_grande = Image.new("RGB", (2200, 2400), color=(255, 255, 255))
        draw = ImageDraw.Draw(img_grande)
        draw.line([(100, 100), (2100, 100)], fill=(0, 0, 0), width=5)

        buf = io.BytesIO()
        img_grande.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        analysis = analyze_page_image(image_bytes, page_number=1)

        # As dimensões reportadas DEVEM ser as originais da imagem (2200x2400)
        self.assertEqual(analysis.width, 2200)
        self.assertEqual(analysis.height, 2400)
        self.assertGreaterEqual(analysis.whitespace_ratio, 0.90)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_imagem_excede_max_pixels_lanca_image_too_large(self) -> None:
        """Imagem cujo produto largura x altura exceda max_total_pixels deve lançar ImageTooLargeError."""
        cfg_pixels = VisualClutterConfig(max_total_pixels=100_000)  # Limite de 100k pixels
        img = Image.new("RGB", (400, 400), color=(255, 255, 255))  # 160k pixels

        with self.assertRaises(ImageTooLargeError) as ctx:
            analyze_page_image(img, config=cfg_pixels)
        self.assertIn("Total de pixels da imagem", str(ctx.exception))

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_consistencia_escalas_todas_metricas_em_intervalo_zero_um(self) -> None:
        """Todas as métricas contínuas devem flutuar estritamente no intervalo [0.0, 1.0]."""
        img = Image.new("RGB", (300, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(50, 50), (150, 150)], fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="PNG")

        analysis = analyze_page_image(buf.getvalue(), page_number=1)

        self.assertGreaterEqual(analysis.edge_density, 0.0)
        self.assertLessEqual(analysis.edge_density, 1.0)

        self.assertGreaterEqual(analysis.whitespace_ratio, 0.0)
        self.assertLessEqual(analysis.whitespace_ratio, 1.0)

        self.assertGreaterEqual(analysis.contrast_ratio, 0.0)
        self.assertLessEqual(analysis.contrast_ratio, 1.0)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_compatibilidade_page_visual_analysis_model_dump(self) -> None:
        """O resultado de analyze_page_image deve ser 100% serializável via model_dump() e dict()."""
        img = Image.new("RGB", (200, 300), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        analysis = analyze_page_image(buf.getvalue(), page_number=3, page_type="mixed")

        dump = analysis.model_dump()
        self.assertEqual(dump["page_number"], 3)
        self.assertEqual(dump["page_type"], "mixed")
        self.assertEqual(dump["width"], 200)
        self.assertEqual(dump["height"], 300)
        self.assertIn("edge_density", dump)
        self.assertIn("whitespace_ratio", dump)
        self.assertIn("contrast_ratio", dump)
        self.assertIn("clutter_level", dump)
        self.assertIn("possible_visual_clutter", dump)
        self.assertIn("legibility_status", dump)

    @unittest.skipUnless(HAS_PILLOW, "Requer a biblioteca Pillow (PIL) instalada no ambiente")
    def test_exif_transpose_preserva_dimensoes_reais(self) -> None:
        """Fotos verticais com tag EXIF Orientation=6 devem ter width/height ajustados na análise visual."""
        img = Image.new("RGB", (600, 300), color=(255, 255, 255))
        exif = img.getexif()
        exif[274] = 6  # Rotacionar 90 graus CW
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif.tobytes())

        analysis = analyze_page_image(buf.getvalue(), page_number=1, page_type="image")
        self.assertEqual(analysis.width, 300)
        self.assertEqual(analysis.height, 600)


if __name__ == "__main__":
    unittest.main()
