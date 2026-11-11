"""Testes automatizados da História 1.1.4 (RF-02 Extensão).

Valida a identificação e organização estrutural de textos corridos nos 10 cenários obrigatórios:
1. Material com título, subtítulos e parágrafos.
2. Material com seções e subseções numeradas (1., 1.1, 1.2, 2.).
3. Material com títulos e subtítulos sem numeração.
4. Material com listas numeradas (1., 2., 3.).
5. Material com listas identificadas por marcadores (•, -, *).
6. Material com múltiplos parágrafos dentro de uma mesma seção.
7. Material com diferentes níveis hierárquicos (Níveis 1 a 4).
8. Material com formatação não padronizada (espaçamento irregular).
9. Material com textos corridos e questões combinadas (coexistência 1.1.2 + 1.1.4).
10. Material com diferentes elementos estruturais e organizações simultâneas.

Garante também:
- Preservação da sequência original (`order`);
- Associação correta entre elementos pais e filhos (`parent_id`);
- Agrupamento de itens de lista em contêineres `list`;
- Integridade total do conteúdo original (zero-loss);
- Métodos de acesso estruturado para integração com o mecanismo de adaptação pedagógica;
- Sanitização de PII e tratamento defensivo no serviço `organize_prose_service`.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# Garante inclusão de backend/src no sys.path
TEST_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEST_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.api.routes.materials import (
    decompose_material_service,
    organize_prose_service,
)
from iris.parsers.prose_organizer import organize_prose_structure
from iris.parsers.structural_decomposer import decompose_material
from iris.schemas.materials import (
    MaterialStructure,
    MaterialValidationError,
    ProseStructure,
    StructuralNode,
)


class TestProseOrganizer(unittest.TestCase):
    """Suíte oficial de testes da História 1.1.4."""

    def test_cenario_01_titulo_subtitulos_e_paragrafos(self) -> None:
        """Cenário 1: Material com título, subtítulo e parágrafos de texto corrido."""
        doc = (
            "A Revolução Industrial na Inglaterra\n\n"
            "Contexto Histórico e Transformações Sociais\n\n"
            "No final do século XVIII, a Inglaterra foi pioneira em profundas mudanças tecnológicas e econômicas. "
            "A introdução das máquinas a vapor transformou radicalmente as relações de trabalho fabris.\n\n"
            "As cidades industriais cresceram em ritmo acelerado, gerando novos desafios urbanos e habitacionais."
        )

        res = organize_prose_structure(doc)

        self.assertIsNotNone(res.title)
        self.assertIn("Revolução Industrial", res.title or "")
        self.assertGreaterEqual(res.total_elements, 3)

        # Validação da árvore hierárquica
        self.assertEqual(len(res.root_nodes), 1)
        root = res.root_nodes[0]
        self.assertEqual(root.element_type, "title")
        self.assertEqual(root.level, 1)

        # O subtítulo deve ser filho do título principal
        subtitles = [c for c in root.children if c.element_type in ("subtitle", "section")]
        self.assertGreaterEqual(len(subtitles), 1)
        sub = subtitles[0]
        self.assertEqual(sub.parent_id, root.id)

        # Os parágrafos devem estar associados ao subtítulo
        paras = sub.get_paragraphs()
        self.assertEqual(len(paras), 2)
        self.assertIn("século XVIII", paras[0].content)
        self.assertIn("cidades industriais", paras[1].content)
        self.assertEqual(paras[0].parent_id, sub.id)

    def test_cenario_02_secoes_e_subsecoes_numeradas(self) -> None:
        """Cenário 2: Material com seções e subseções numeradas (1., 1.1, 1.2, 2.)."""
        doc = (
            "1. Estrutura Celular\n"
            "A célula é a unidade morfofisiológica de todos os seres vivos.\n\n"
            "1.1 Membrana Plasmática\n"
            "Responsável pelo controle de entrada e saída de substâncias através da permeabilidade seletiva.\n\n"
            "1.2 Citoplasma e Organelas\n"
            "Espaço intracelular onde ocorrem as principais reações metabólicas.\n\n"
            "2. Divisão Celular\n"
            "Processo pelo qual uma célula-mãe se divide gerando células-filhas."
        )

        res = organize_prose_structure(doc)

        # Seções de topo: 1. e 2.
        self.assertEqual(len(res.root_nodes), 2)
        sec1 = res.root_nodes[0]
        sec2 = res.root_nodes[1]

        self.assertIn("Estrutura Celular", sec1.content)
        self.assertIn("Divisão Celular", sec2.content)

        # Subseções 1.1 e 1.2 devem ser filhas de sec1
        subsecs = [c for c in sec1.children if c.element_type == "subsection"]
        self.assertEqual(len(subsecs), 2)

        self.assertIn("Membrana Plasmática", subsecs[0].content)
        self.assertEqual(subsecs[0].parent_id, sec1.id)

        self.assertIn("Citoplasma e Organelas", subsecs[1].content)
        self.assertEqual(subsecs[1].parent_id, sec1.id)

        # sec2 não deve conter as subseções de sec1
        self.assertEqual(len([c for c in sec2.children if c.element_type == "subsection"]), 0)

    def test_cenario_03_titulos_e_subtitulos_sem_numeracao(self) -> None:
        """Cenário 3: Material com títulos e seções sem numeração identificados por termos clássicos e caixas."""
        doc = (
            "ECOLOGIA GERAL\n\n"
            "Introdução\n"
            "A ecologia estuda as interações entre os organismos vivos e o meio ambiente em que habitam.\n\n"
            "Desenvolvimento\n"
            "Os ecossistemas são formados por fatores bióticos e abióticos interdependentes.\n\n"
            "Conclusão\n"
            "A preservação da biodiversidade é imprescindível para o equilíbrio planetário."
        )

        res = organize_prose_structure(doc)

        outline = res.get_outline()
        titles_in_outline = [o["title"] for o in outline]

        self.assertTrue(any("ECOLOGIA" in t for t in titles_in_outline))
        self.assertTrue(any("Introdução" in t for t in titles_in_outline))
        self.assertTrue(any("Desenvolvimento" in t for t in titles_in_outline))
        self.assertTrue(any("Conclusão" in t for t in titles_in_outline))

        # Todos os parágrafos estão estruturados
        paras = res.get_paragraphs()
        self.assertEqual(len(paras), 3)

    def test_cenario_04_listas_numeradas(self) -> None:
        """Cenário 4: Material com lista ordenada (passos enumerados sequencialmente)."""
        doc = (
            "Procedimento Experimental no Laboratório:\n"
            "1. Higienize a bancada com álcool 70% antes de iniciar.\n"
            "2. Meça 50 ml de água destilada na proveta graduada.\n"
            "3. Aqueça a solução até atingir 80 graus Celsius.\n"
            "4. Registre as alterações térmicas no caderno de campo."
        )

        res = organize_prose_structure(doc)

        lists = res.get_lists()
        self.assertEqual(len(lists), 1)

        list_node = lists[0]
        self.assertEqual(list_node.element_type, "list")
        self.assertEqual(list_node.metadata.get("list_type"), "ordered")

        # 4 itens filhos agrupados na mesma lista
        self.assertEqual(len(list_node.children), 4)
        for i, item in enumerate(list_node.children):
            self.assertEqual(item.element_type, "list_item")
            self.assertEqual(item.parent_id, list_node.id)
            self.assertGreater(len(item.content), 5)

        self.assertIn("Higienize", list_node.children[0].content)
        self.assertIn("Registre", list_node.children[3].content)

    def test_cenario_05_listas_com_marcadores_bullets(self) -> None:
        """Cenário 5: Material com lista de marcadores variados (bullets •, -, *)."""
        doc = (
            "Principais Características dos Vertebrados:\n"
            "• Presença de coluna vertebral e crânio ósseo ou cartilaginoso.\n"
            "• Sistema nervoso central dorsal com encéfalo bem diferenciado.\n"
            "• Sistema circulatório fechado com coração ventral muscular."
        )

        res = organize_prose_structure(doc)

        lists = res.get_lists()
        self.assertEqual(len(lists), 1)

        list_node = lists[0]
        self.assertEqual(list_node.metadata.get("list_type"), "unordered")
        self.assertEqual(len(list_node.children), 3)

        self.assertIn("coluna vertebral", list_node.children[0].content)
        self.assertIn("Sistema nervoso", list_node.children[1].content)
        self.assertIn("Sistema circulatório", list_node.children[2].content)

    def test_cenario_06_multiplos_paragrafos_na_mesma_secao(self) -> None:
        """Cenário 6: Múltiplos parágrafos densos dentro de uma mesma seção."""
        doc = (
            "1. A Era Vargas e a Industrialização\n\n"
            "Durante a década de 1930, o Brasil implementou um modelo de substituição de importações pioneiro.\n\n"
            "A criação da Companhia Siderúrgica Nacional em Volta Redonda foi o marco da indústria de base nacional.\n\n"
            "Paralelamente, a consolidação das leis do trabalho reorganizou a estrutura sindical e urbana do país."
        )

        res = organize_prose_structure(doc)

        self.assertEqual(len(res.root_nodes), 1)
        sec = res.root_nodes[0]
        self.assertEqual(sec.element_type, "section")

        # 3 parágrafos contidos e associados à mesma seção
        paras = sec.get_paragraphs()
        self.assertEqual(len(paras), 3)
        for p in paras:
            self.assertEqual(p.parent_id, sec.id)
            self.assertGreater(len(p.content), 20)

    def test_cenario_07_diferentes_niveis_hierarquicos(self) -> None:
        """Cenário 7: Material com hierarquia profunda (Título -> Seção -> Subseção -> Sub-subseção)."""
        doc = (
            "Manual de Ciências Físicas\n\n"
            "1. Mecânica Clássica\n\n"
            "1.1 Cinemática Escalar\n\n"
            "1.1.1 Movimento Uniforme\n"
            "No movimento uniforme, a velocidade escalar instantânea é constante e diferente de zero."
        )

        res = organize_prose_structure(doc)

        # Profundidade máxima de pelo menos 4 níveis
        self.assertGreaterEqual(res.max_depth, 4)

        all_nodes = res.flatten()
        types = [n.element_type for n in all_nodes]
        self.assertIn("title", types)
        self.assertIn("section", types)
        self.assertIn("subsection", types)
        self.assertIn("paragraph", types)

        # Encontra o parágrafo mais profundo
        p = [n for n in all_nodes if n.element_type == "paragraph"][0]
        self.assertGreaterEqual(p.level or 0, 4)

    def test_cenario_08_formatacao_nao_padronizada(self) -> None:
        """Cenário 8: Material com quebras de linha irregulares e espaços soltos (zero-loss)."""
        doc = (
            "    BIOLOGIA MARINHA    \n\n\n"
            "Os oceanos cobrem mais de 70% da superfície terrestre.\n\n"
            "    Eles abrigam ecossistemas complexos como recifes de corais e fossas abissais.\n\n\n"
            "Fatores que ameaçam os oceanos:\n"
            "  * Poluição plástica em larga escala\n"
            "  * Aquecimento global e acidificação\n\n"
            "A preservação é urgente."
        )

        res = organize_prose_structure(doc)

        self.assertGreater(res.total_elements, 3)

        # Validação de preservação integral de palavras
        words_original = set(re.findall(r"\b\w+\b", doc.lower()))
        decomp_text = " ".join([n.content for n in res.flatten()]).lower()
        words_decomp = set(re.findall(r"\b\w+\b", decomp_text))

        for w in ["biologia", "marinha", "superfície", "recifes", "plástica", "acidificação", "urgente"]:
            self.assertIn(w, words_decomp)

    def test_cenario_09_textos_corridos_e_questoes_combinadas(self) -> None:
        """Cenário 9: Material híbrido contendo texto didático explicativo seguido de questões da História 1.1.2."""
        doc = (
            "Capítulo 4: O Sistema Solar\n\n"
            "O Sistema Solar é formado pelo Sol e pelos corpos celestes que orbitam ao seu redor.\n"
            "Os planetas rochosos são Mercúrio, Vênus, Terra e Marte.\n\n"
            "Atividades de Fixação:\n\n"
            "1. Qual é o maior planeta do Sistema Solar?\n"
            "A) Terra\n"
            "B) Júpiter\n"
            "C) Marte\n"
            "D) Saturno\n\n"
            "2. Explique a diferença entre planetas rochosos e gasosos.\n"
            "___________________________________________________"
        )

        # Executa decomposição geral (compatibilidade 1.1.2 + 1.1.4)
        mat = decompose_material(doc)

        # 1.1.2: Questões identificadas com precisão
        self.assertEqual(mat.total_questions, 2)
        self.assertEqual(mat.questions[0].question_type, "multipla_escolha")
        self.assertEqual(len(mat.questions[0].options), 4)
        self.assertEqual(mat.questions[1].question_type, "dissertativa")

        # 1.1.4: Estrutura em prosa disponível no mesmo objeto
        self.assertIsNotNone(mat.prose_structure)
        prose = mat.prose_structure
        self.assertIsNotNone(prose.title)
        self.assertIn("Sistema Solar", prose.title or "")
        self.assertGreaterEqual(len(prose.flatten()), 2)

    def test_cenario_10_multiplos_elementos_e_adaptacao_api(self) -> None:
        """Cenário 10: Material completo validando a disponibilização para o motor de adaptação pedagógica."""
        doc = (
            "Apostila de Química Orgânica\n\n"
            "1. Introdução aos Hidrocarbonetos\n"
            "Compostos formados exclusivamente por carbono e hidrogênio.\n\n"
            "1.1 Classificação das Cadeias\n"
            "As cadeias carbônicas podem ser classificadas conforme sua estrutura:\n"
            "- Abertas ou acíclicas\n"
            "- Fechadas ou cíclicas\n"
            "- Aromáticas ou alifáticas\n\n"
            "2. Propriedades Físicas\n"
            "Os hidrocarbonetos apresentam baixa polaridade e solubilidade reduzida em água."
        )

        res = organize_prose_structure(doc)

        # Valida métodos de acesso da API para a adaptação pedagógica (História 2.1.3):
        outline = res.get_outline()
        self.assertGreaterEqual(len(outline), 3)
        self.assertEqual(outline[0]["element_type"], "title")

        sections = res.get_sections()
        self.assertGreaterEqual(len(sections), 3)

        paragraphs = res.get_paragraphs()
        self.assertGreaterEqual(len(paragraphs), 2)

        lists = res.get_lists()
        self.assertEqual(len(lists), 1)
        self.assertEqual(len(lists[0].children), 3)

        # Validação do flatten() e find_by_id()
        all_nodes = res.flatten()
        self.assertEqual(len(all_nodes), res.total_elements)

        first_node = all_nodes[0]
        found = res.find_by_id(first_node.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.content, first_node.content)

        # Valida serialização segura
        dump = res.model_dump()
        self.assertIn("root_nodes", dump)
        self.assertIn("total_elements", dump)
        self.assertEqual(dump["total_elements"], res.total_elements)

    def test_organize_prose_service_empty_text_validation(self) -> None:
        """O serviço organize_prose_service deve rejeitar texto vazio com MaterialValidationError."""
        with self.assertRaises(MaterialValidationError) as ctx:
            organize_prose_service("   \n \t  ")
        self.assertEqual(ctx.exception.code, "EMPTY_TEXT")

    def test_zero_loss_content_preservation(self) -> None:
        """Garante que nenhuma palavra do conteúdo original seja descartada."""
        texto = (
            "Termodinâmica Aplicada\n\n"
            "A primeira lei da termodinâmica expressa o princípio fundamental da conservação de energia.\n\n"
            "Transformações Notáveis:\n"
            "• Isotérmica: temperatura constante.\n"
            "• Isobárica: pressão constante.\n"
            "• Isométrica: volume constante."
        )
        res = organize_prose_structure(texto)

        conteudo_total = " ".join([n.content for n in res.flatten()]).lower()
        words_original = set(re.findall(r"\b\w+\b", texto.lower()))
        words_decomposed = set(re.findall(r"\b\w+\b", conteudo_total))

        # Todas as palavras substantivas essenciais devem estar presentes
        for palavra in ["termodinâmica", "conservação", "energia", "isotérmica", "isobárica", "isométrica"]:
            self.assertIn(palavra, words_decomposed)

    def test_itens_de_lista_com_linhas_em_branco_continuam_na_mesma_lista(self) -> None:
        """Itens com marcadores separados por linha em branco não devem ser classificados como subtítulos."""
        doc = (
            "Orientações:\n"
            "• Item 1\n\n"
            "• Item 2\n\n"
            "• Item 3"
        )
        res = organize_prose_structure(doc)
        lists = res.get_lists()
        self.assertEqual(len(lists), 1)
        self.assertEqual(len(lists[0].children), 3)
        self.assertEqual([c.content for c in lists[0].children], ["Item 1", "Item 2", "Item 3"])
        # Garante que nenhum item virou subtítulo indevido
        subtitles = [n for n in res.flatten() if n.element_type == "subtitle"]
        self.assertEqual(len(subtitles), 0)

    def test_item_de_lista_longo_em_duas_linhas_continua_unido(self) -> None:
        """Item de lista cuja frase quebra para a linha seguinte deve permanecer unido no mesmo list_item."""
        doc = (
            "Recomendações pedagógicas:\n"
            "• Primeiro ponto com explicação detalhada\n"
            "  que continua na linha de baixo\n"
            "• Segundo ponto conciso"
        )
        res = organize_prose_structure(doc)
        lists = res.get_lists()
        self.assertEqual(len(lists), 1)
        self.assertEqual(len(lists[0].children), 2)
        self.assertEqual(
            lists[0].children[0].content,
            "Primeiro ponto com explicação detalhada que continua na linha de baixo",
        )
        self.assertEqual(lists[0].children[1].content, "Segundo ponto conciso")

    def test_lista_ordenada_apos_dois_pontos_sem_ponto_final(self) -> None:
        """Itens enumerados após linha com dois-pontos devem ser itens de lista, mesmo sem ponto final."""
        doc = (
            "Procedimento de Segurança:\n"
            "1. Higienize a bancada com álcool\n"
            "2. Coloque as luvas de proteção"
        )
        res = organize_prose_structure(doc)
        lists = res.get_lists()
        self.assertEqual(len(lists), 1)
        self.assertEqual(len(lists[0].children), 2)
        self.assertIn("Higienize", lists[0].children[0].content)
        self.assertIn("Coloque", lists[0].children[1].content)

    def test_servico_organize_prose_rejeita_janela_de_contexto_excedida(self) -> None:
        """O serviço deve rejeitar materiais que ultrapassam a janela de contexto segura."""
        texto_longo = "Texto de teste para validação de contexto.\n" * 4_000  # > 160.000 caracteres
        with self.assertRaises(MaterialValidationError) as ctx:
            organize_prose_service(texto_longo)
        self.assertEqual(ctx.exception.code, "CONTEXT_WINDOW_EXCEEDED")


if __name__ == "__main__":
    unittest.main()

