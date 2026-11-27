"""Testes unitários dos contratos e schemas da História 1.1.3 (Etapa 1 - Ajustes Finais de Segurança).

Valida:
1. Bloqueio de instanciação direta/insegura de RawContent (PermissionError).
2. Fluxo oficial create_sanitized_raw_content e fábrica RawContent.from_raw_text executando efetivamente sanitize_pii.
3. Semântica precisa de metadados: sanitization_executed=True mesmo quando pii_removed_count=0.
4. Separação estrita entre raw_text original (revisão docente) e raw_content.text (sanitizado para processamento/IA).
5. Validação estrita de source_type (aceita Enum e strings correspondentes válidas, rejeita strings inválidas).
6. Limites técnicos: MAX_OCR_FILE_SIZE_BYTES (25 MB) e preservação de MAX_FILE_SIZE_BYTES (10 MB).
7. Validador validate_ocr_file_size_limit.
8. Schemas de análise visual: PageVisualAnalysis e VisualAnalysisReport.
9. Schema OcrMaterialResponse (sem duplicidade, propriedade sanitized_text).
10. Reexportação de contratos em iris.schemas.
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock

# Compatibilidade defensiva para execução do teste em ambientes com ou sem pydantic instalado
if "pydantic" not in sys.modules:
    sys.modules["pydantic"] = MagicMock()

TEST_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEST_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.schemas.materials import (
    MAX_FILE_SIZE_BYTES,
    MAX_OCR_FILE_SIZE_BYTES,
    MaterialMetadata,
    MaterialSourceType,
    MaterialValidationError,
    OcrMaterialResponse,
    PageVisualAnalysis,
    RawContent,
    VisualAnalysisReport,
    create_sanitized_raw_content,
    validate_file_size_limit,
    validate_ocr_file_size_limit,
)
from iris.parsers.structural_decomposer import decompose_material


class TestMaterialsSchemasEtapa1(unittest.TestCase):
    """Bateria de testes para os contratos de segurança e schemas da História 1.1.3 (Etapa 1)."""

    def test_constantes_de_limite_preservam_regra_textual_e_adicionam_ocr(self) -> None:
        """Deve preservar 10 MB para fluxo textual e definir 25 MB para OCR."""
        self.assertEqual(MAX_FILE_SIZE_BYTES, 10 * 1024 * 1024)
        self.assertEqual(MAX_OCR_FILE_SIZE_BYTES, 25 * 1024 * 1024)
        self.assertGreater(MAX_OCR_FILE_SIZE_BYTES, MAX_FILE_SIZE_BYTES)

    def test_validate_ocr_file_size_limit_aceita_tamanho_seguro(self) -> None:
        """Deve aceitar arquivos até 25 MB sem lançar erro."""
        conteudo_5mb = b"x" * (5 * 1024 * 1024)
        conteudo_25mb = b"x" * (25 * 1024 * 1024)

        self.assertEqual(validate_ocr_file_size_limit(conteudo_5mb), 5 * 1024 * 1024)
        self.assertEqual(validate_ocr_file_size_limit(conteudo_25mb), 25 * 1024 * 1024)
        self.assertEqual(validate_ocr_file_size_limit(b""), 0)

    def test_validate_ocr_file_size_limit_rejeita_acima_de_25mb(self) -> None:
        """Deve rejeitar arquivos com mais de 25 MB com OCR_FILE_TOO_LARGE."""
        conteudo_excedente = b"x" * (25 * 1024 * 1024 + 1024)

        with self.assertRaises(MaterialValidationError) as ctx:
            validate_ocr_file_size_limit(conteudo_excedente)

        self.assertEqual(ctx.exception.code, "OCR_FILE_TOO_LARGE")
        self.assertEqual(ctx.exception.field, "file")
        self.assertIn("25 MB", ctx.exception.message)

    def test_validate_file_size_limit_preserva_rejeicao_acima_de_10mb(self) -> None:
        """O validador textual padrão deve continuar rejeitando arquivos acima de 10 MB."""
        conteudo_11mb = b"x" * (11 * 1024 * 1024)

        with self.assertRaises(MaterialValidationError) as ctx:
            validate_file_size_limit(conteudo_11mb)

        self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")
        self.assertEqual(ctx.exception.field, "file")

    def test_material_source_type_enum_contem_formatos_novos(self) -> None:
        """MaterialSourceType deve conter todos os formatos textuais e os novos formatos de OCR."""
        # Formatos textuais existentes
        self.assertEqual(MaterialSourceType.TEXT.value, "text")
        self.assertEqual(MaterialSourceType.TXT.value, "txt")
        self.assertEqual(MaterialSourceType.PDF.value, "pdf")
        self.assertEqual(MaterialSourceType.DOCX.value, "docx")

        # Novos formatos de imagem e digitalização (História 1.1.3)
        self.assertEqual(MaterialSourceType.PNG.value, "png")
        self.assertEqual(MaterialSourceType.JPG.value, "jpg")
        self.assertEqual(MaterialSourceType.JPEG.value, "jpeg")
        self.assertEqual(MaterialSourceType.SCANNED_PDF.value, "scanned_pdf")
        self.assertEqual(MaterialSourceType.MIXED_PDF.value, "mixed_pdf")

    def test_instanciacao_direta_raw_content_proibida(self) -> None:
        """Tentativa de instanciar RawContent diretamente sem passar pelo sanitizador deve ser bloqueada."""
        # 1. Instanciação padrão sem sentinela
        with self.assertRaises(PermissionError) as ctx1:
            RawContent(
                text="Texto bruto com Aluno: Lucas Silva",
                source_type=MaterialSourceType.PNG,
                metadata={},
                pii_sanitized=True,  # Tentativa de burlar passando True
            )
        self.assertIn("RNF-02", str(ctx1.exception))
        self.assertIn("proibida", str(ctx1.exception))

        # 2. Tentativa de burlar passando sentinela forjada
        with self.assertRaises(PermissionError) as ctx2:
            RawContent(
                text="Texto bruto com Aluno: Lucas Silva",
                source_type=MaterialSourceType.PNG,
                metadata={},
                pii_sanitized=True,
                _guard=object(),  # Objeto arbitrário não corresponde à sentinela privada
            )
        self.assertIn("proibida", str(ctx2.exception))

        with self.assertRaises(PermissionError):
            RawContent(
                text="Texto bruto",
                source_type=MaterialSourceType.JPG,
                metadata={},
                pii_sanitized=True,
                _guard="qualquer_string",
            )

    def test_fluxo_oficial_create_sanitized_raw_content_executa_sanitize_pii(self) -> None:
        """O fluxo oficial create_sanitized_raw_content deve executar sanitize_pii, separando original de sanitizado."""
        texto_bruto = (
            "Escola Municipal Ayrton Senna\n"
            "Professor(a): Carlos Drummond\n"
            "Aluno(a): Lucas Silva\n"
            "1. Explique as fases da lua."
        )

        original_para_revisao, raw_content = create_sanitized_raw_content(
            raw_text=texto_bruto,
            source_type=MaterialSourceType.PNG,
            metadata={"filename": "avaliacao_ciencias.png"},
        )

        # 1. O texto original é preservado inalterado para revisão docente na tela
        self.assertEqual(original_para_revisao, texto_bruto)
        self.assertIn("Lucas Silva", original_para_revisao)
        self.assertIn("Ayrton Senna", original_para_revisao)

        # 2. sanitize_pii foi efetivamente executado sobre o texto que vai para o RawContent
        self.assertNotIn("Lucas Silva", raw_content.text)
        self.assertNotIn("Carlos Drummond", raw_content.text)
        self.assertIn("[ESTUDANTE]", raw_content.text)
        self.assertIn("[PROFESSOR]", raw_content.text)
        self.assertIn("[ESCOLA]", raw_content.text)

        # 3. Metadados e flags de segurança registradas
        self.assertTrue(raw_content.pii_sanitized)
        self.assertTrue(raw_content.metadata["sanitization_executed"])
        self.assertEqual(raw_content.metadata["pii_removed_count"], 3)
        self.assertEqual(raw_content.source_type, MaterialSourceType.PNG)

    def test_raw_content_fabrica_from_raw_text_executa_sanitizacao(self) -> None:
        """RawContent.from_raw_text deve construir o contrato aplicando sanitize_pii diretamente."""
        texto_com_pii = "Colégio Tiradentes\nAluno: Mariana Souza\nQuestão 1: O que é átomo?"

        raw_content = RawContent.from_raw_text(
            raw_text=texto_com_pii,
            source_type=MaterialSourceType.JPEG,
            metadata={"source": "upload"},
        )

        self.assertNotIn("Mariana Souza", raw_content.text)
        self.assertIn("[ESTUDANTE]", raw_content.text)
        self.assertTrue(raw_content.pii_sanitized)
        self.assertTrue(raw_content.metadata["sanitization_executed"])
        self.assertEqual(raw_content.metadata["pii_removed_count"], 2)
        self.assertEqual(raw_content.source_type, MaterialSourceType.JPEG)

    def test_raw_content_imutabilidade_campos_geram_frozen_instance_error(self) -> None:
        """Modificar qualquer atributo de RawContent após a construção deve lançar FrozenInstanceError."""
        _, raw_content = create_sanitized_raw_content(
            raw_text="Questão de Geografia sobre clima.",
            source_type=MaterialSourceType.PNG,
            metadata={"origem": "camera"},
        )

        # 1. Modificar text deve falhar
        with self.assertRaises(FrozenInstanceError):
            raw_content.text = "Texto alterado indevidamente"  # type: ignore[misc]

        # 2. Modificar source_type deve falhar
        with self.assertRaises(FrozenInstanceError):
            raw_content.source_type = MaterialSourceType.DOCX  # type: ignore[misc]

        # 3. Modificar pii_sanitized deve falhar
        with self.assertRaises(FrozenInstanceError):
            raw_content.pii_sanitized = False  # type: ignore[misc]

        # 4. Modificar metadata deve falhar
        with self.assertRaises(FrozenInstanceError):
            raw_content.metadata = {}  # type: ignore[misc]

    def test_raw_content_protecao_defensiva_metadados_dicionario_original(self) -> None:
        """Alterar o dicionário original fornecido na construção não deve modificar o objeto (cópia defensiva)."""
        dicionario_externo = {
            "disciplina": "História",
            "detalhes": {"ano": 7, "bimestre": 2},
        }

        _, raw_content = create_sanitized_raw_content(
            raw_text="Questão 1 sobre Feudalismo.",
            source_type=MaterialSourceType.JPEG,
            metadata=dicionario_externo,
        )

        # Modifica o dicionário externo original (nível superficial e aninhado)
        dicionario_externo["disciplina"] = "Matemática"
        dicionario_externo["detalhes"]["ano"] = 9
        dicionario_externo["novo_campo"] = "adicionado_depois"

        # O contrato RawContent permanece inalterado
        self.assertEqual(raw_content.metadata["disciplina"], "História")
        self.assertEqual(raw_content.metadata["detalhes"]["ano"], 7)
        self.assertNotIn("novo_campo", raw_content.metadata)

    def test_raw_content_metadados_imutaveis_diretamente_no_objeto(self) -> None:
        """Modificar o mapeamento de metadados diretamente pelo objeto não é permitido (MappingProxyType)."""
        _, raw_content = create_sanitized_raw_content(
            raw_text="Questão sobre fotossíntese.",
            source_type=MaterialSourceType.PNG,
            metadata={"materia": "Biologia"},
        )

        # 1. Inserir nova chave deve lançar TypeError
        with self.assertRaises(TypeError):
            raw_content.metadata["tentativa_mutacao"] = "valor"  # type: ignore[index]

        # 2. Modificar chave existente deve lançar TypeError
        with self.assertRaises(TypeError):
            raw_content.metadata["sanitization_executed"] = False  # type: ignore[index]

        # 3. Deletar chave deve lançar TypeError
        with self.assertRaises(TypeError):
            del raw_content.metadata["pii_removed_count"]  # type: ignore[attr-defined]

    def test_raw_content_model_dump_e_dict_retornam_dicionarios_independentes(self) -> None:
        """model_dump() e dict() devem retornar dicionários independentes sem afetar o contrato."""
        _, raw_content = create_sanitized_raw_content(
            raw_text="Questão 1: O que é átomo?",
            source_type=MaterialSourceType.PNG,
            metadata={"materia": "Química"},
        )

        dump = raw_content.model_dump()
        d = raw_content.dict()

        self.assertIsInstance(dump, dict)
        self.assertIsInstance(dump["metadata"], dict)
        self.assertEqual(dump["metadata"]["materia"], "Química")
        self.assertEqual(d["metadata"]["materia"], "Química")

        # Modificar o dicionário retornado pelo dump não afeta o RawContent
        dump["metadata"]["materia"] = "Física"
        dump["text"] = "Texto modificado no dump"
        self.assertEqual(raw_content.metadata["materia"], "Química")
        self.assertEqual(raw_content.text, "Questão 1: O que é átomo?")

    def test_semantica_metadados_ausencia_pii_registra_sanitizacao_executada(self) -> None:
        """A ausência de PII identificada (pii_removed_count=0) deve manter sanitization_executed=True."""
        texto_sem_pii = "Avaliação sobre a Revolução Industrial.\n1. Explique as principais invenções a vapor."

        original_para_revisao, raw_content = create_sanitized_raw_content(
            raw_text=texto_sem_pii,
            source_type="docx",
        )

        # Confirma que a sanitização foi executada, com 0 remoções necessárias
        self.assertTrue(raw_content.metadata["sanitization_executed"])
        self.assertEqual(raw_content.metadata["pii_removed_count"], 0)
        self.assertTrue(raw_content.pii_sanitized)
        self.assertEqual(raw_content.text, texto_sem_pii)

    def test_source_type_validacao_estrita(self) -> None:
        """source_type deve aceitar enum ou string válida, e rejeitar qualquer string ou tipo inválido."""
        # Enum válido
        raw_enum = RawContent.from_raw_text("Texto 1", MaterialSourceType.SCANNED_PDF)
        self.assertEqual(raw_enum.source_type, MaterialSourceType.SCANNED_PDF)
        self.assertEqual(raw_enum.model_dump()["source_type"], "scanned_pdf")

        # String válida correspondente a membro do Enum
        raw_str = RawContent.from_raw_text("Texto 2", "png")
        self.assertEqual(raw_str.source_type, MaterialSourceType.PNG)
        self.assertEqual(raw_str.model_dump()["source_type"], "png")

        # String inválida deve lançar ValueError informando formatos aceitos
        with self.assertRaises(ValueError) as ctx:
            RawContent.from_raw_text("Texto 3", "formato_invalido_xyz")
        self.assertIn("Tipo de fonte inválido", str(ctx.exception))
        self.assertIn("scanned_pdf", str(ctx.exception))

        # Tipo arbitrário (ex: int) deve lançar ValueError
        with self.assertRaises(ValueError):
            RawContent.from_raw_text("Texto 4", 123)  # type: ignore

    def test_page_visual_analysis_schema_e_metricas(self) -> None:
        """PageVisualAnalysis deve registrar métricas geométricas e indicador de densidade visual."""
        page_analysis = PageVisualAnalysis(
            page_number=1,
            page_type="scanned",
            width=1240,
            height=1754,
            edge_density=0.18,
            whitespace_ratio=0.72,
            contrast_ratio=185.0,
            clutter_level="moderada",
            possible_visual_clutter=False,
            legibility_status="ok",
            rejection_reason=None,
        )

        dump = page_analysis.model_dump()
        self.assertEqual(dump["page_number"], 1)
        self.assertEqual(dump["page_type"], "scanned")
        self.assertEqual(dump["width"], 1240)
        self.assertEqual(dump["height"], 1754)
        self.assertEqual(dump["clutter_level"], "moderada")
        self.assertFalse(dump["possible_visual_clutter"])
        self.assertEqual(dump["legibility_status"], "ok")
        self.assertIsNone(dump["rejection_reason"])

    def test_visual_analysis_report_agregacao(self) -> None:
        """VisualAnalysisReport deve consolidar múltiplas páginas e serializar nós aninhados."""
        p1 = PageVisualAnalysis(
            page_number=1,
            page_type="scanned",
            width=1200,
            height=1600,
            edge_density=0.12,
            whitespace_ratio=0.75,
            contrast_ratio=190.0,
            clutter_level="baixa",
            possible_visual_clutter=False,
        )
        p2 = PageVisualAnalysis(
            page_number=2,
            page_type="mixed",
            width=1200,
            height=1600,
            edge_density=0.32,
            whitespace_ratio=0.42,
            contrast_ratio=170.0,
            clutter_level="alta",
            possible_visual_clutter=True,
        )

        relatorio = VisualAnalysisReport(
            overall_clutter_level="alta",
            has_high_clutter=True,
            total_pages_analyzed=2,
            flagged_pages=[2],
            pages=[p1, p2],
            notes="A página 2 apresenta alta concentração de elementos visuais concorrentes.",
        )

        dump = relatorio.model_dump()
        self.assertEqual(dump["overall_clutter_level"], "alta")
        self.assertTrue(dump["has_high_clutter"])
        self.assertEqual(dump["total_pages_analyzed"], 2)
        self.assertEqual(dump["flagged_pages"], [2])
        self.assertEqual(len(dump["pages"]), 2)
        self.assertEqual(dump["pages"][1]["clutter_level"], "alta")
        self.assertIn("A página 2", dump["notes"])

    def test_ocr_material_response_sem_duplicidade_e_com_separacao_de_responsabilidades(self) -> None:
        """OcrMaterialResponse deve separar raw_text docente de raw_content.text sem redundância de estado."""
        texto_original = "Escola Estadual Santos Dumont\nAluno: João Pedro Silva\n1. Explique a gravidade."

        # Construção através do fluxo oficial seguro
        _, raw_content = create_sanitized_raw_content(
            raw_text=texto_original,
            source_type=MaterialSourceType.PNG,
            metadata={"filename": "foto_prova.png"},
        )

        metadata = MaterialMetadata(
            source_type=MaterialSourceType.PNG.value,
            char_count=len(raw_content.text),
            word_count=len(raw_content.text.split()),
            sanitized=True,
            pii_removed_count=2,
            filename="foto_prova.png",
        )

        p1 = PageVisualAnalysis(
            page_number=1,
            page_type="image",
            width=1080,
            height=1920,
            edge_density=0.14,
            whitespace_ratio=0.70,
            contrast_ratio=180.0,
            clutter_level="baixa",
            possible_visual_clutter=False,
        )
        report = VisualAnalysisReport(
            overall_clutter_level="baixa",
            has_high_clutter=False,
            total_pages_analyzed=1,
            flagged_pages=[],
            pages=[p1],
        )

        response = OcrMaterialResponse(
            status="success",
            message="Imagem processada com OCR e sanitizada com sucesso.",
            raw_text=texto_original,
            raw_content=raw_content,
            metadata=metadata,
            visual_analysis=report,
        )

        # 1. raw_text: preservado para o professor na interface (HITL)
        self.assertIn("João Pedro Silva", response.raw_text)

        # 2. raw_content.text: seguro para IA / pipeline pedagógico
        self.assertNotIn("João Pedro Silva", response.raw_content.text)
        self.assertIn("[ESTUDANTE]", response.raw_content.text)

        # 3. Propriedade sanitized_text referencia diretamente raw_content.text (sem duplicação de string)
        self.assertEqual(response.sanitized_text, response.raw_content.text)

        # 4. Serialização do envelope completo com objetos aninhados
        dump = response.model_dump()
        self.assertEqual(dump["raw_text"], texto_original)
        self.assertEqual(dump["raw_content"]["text"], response.raw_content.text)
        self.assertEqual(dump["raw_content"]["source_type"], "png")
        self.assertTrue(dump["raw_content"]["pii_sanitized"])
        self.assertEqual(dump["metadata"]["filename"], "foto_prova.png")
        self.assertEqual(dump["visual_analysis"]["overall_clutter_level"], "baixa")

    def test_conteudo_encaminhado_ao_processamento_estrutural_e_sanitizado(self) -> None:
        """Comprova que o conteúdo submetido ao StructuralDecomposer é rigorosamente o sanitizado."""
        texto_original_com_dados_pessoais = (
            "Colégio Dom Pedro II\n"
            "Professor: Roberto Freire\n"
            "Aluno: Fernando Henrique\n"
            "Data: 10/11/2026\n\n"
            "1. Qual é a capital do Brasil?\n"
            "a) São Paulo\n"
            "b) Brasília\n"
            "c) Rio de Janeiro\n"
        )

        original_para_revisao, raw_content = create_sanitized_raw_content(
            raw_text=texto_original_com_dados_pessoais,
            source_type=MaterialSourceType.SCANNED_PDF,
        )

        # 1. Confirma que original retém os dados para o professor na tela
        self.assertIn("Roberto Freire", original_para_revisao)
        self.assertIn("Fernando Henrique", original_para_revisao)

        # 2. Decomposição estrutural consome raw_content.text (conteúdo sanitizado)
        estrutura = decompose_material(raw_content.text)

        # 3. O cabeçalho decomposto não deve conter dados pessoais nominais
        self.assertIsNotNone(estrutura.header)
        texto_cabecalho = estrutura.header or ""
        self.assertNotIn("Roberto Freire", texto_cabecalho)
        self.assertNotIn("Fernando Henrique", texto_cabecalho)
        self.assertIn("[PROFESSOR]", texto_cabecalho)
        self.assertIn("[ESTUDANTE]", texto_cabecalho)

        # 4. As questões geradas preservam o conteúdo didático íntegro
        self.assertEqual(len(estrutura.questions), 1)
        self.assertIn("capital do Brasil", estrutura.questions[0].statement)
        self.assertEqual(len(estrutura.questions[0].options), 3)

    def test_reexportacoes_em_iris_schemas(self) -> None:
        """Todos os novos schemas e constantes devem ser reexportados no pacote iris.schemas."""
        import iris.schemas as schemas

        self.assertTrue(hasattr(schemas, "MAX_OCR_FILE_SIZE_BYTES"))
        self.assertTrue(hasattr(schemas, "validate_ocr_file_size_limit"))
        self.assertTrue(hasattr(schemas, "RawContent"))
        self.assertTrue(hasattr(schemas, "create_sanitized_raw_content"))
        self.assertTrue(hasattr(schemas, "PageVisualAnalysis"))
        self.assertTrue(hasattr(schemas, "VisualAnalysisReport"))
        self.assertTrue(hasattr(schemas, "OcrMaterialResponse"))
        self.assertEqual(schemas.MAX_OCR_FILE_SIZE_BYTES, 25 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
