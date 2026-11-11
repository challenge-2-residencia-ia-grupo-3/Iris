"""Testes automatizados da História 1.1.2 (Issue #5 / RF-02).

Cobre os 10 cenários sintéticos obrigatórios de provas e materiais didáticos:
1. Prova com cabeçalho padrão e questões dissertativas simples;
2. Prova de múltipla escolha tradicional com alternativas A a E;
3. Prova com texto de apoio compartilhado explícito (intervalo "de 1 a 3");
4. Prova com texto de apoio dedicado precedente a uma única questão;
5. Prova com estilos heterogêneos de numeração (Questão 01, 2), 3., 04 -, 5º.);
6. Prova densa sem quebras de página com questões consecutivas;
7. Prova com espaços e linhas de resposta (sublinhadas e pontilhadas);
8. Prova mista (dissertativa, múltipla escolha e mista com justificativa);
9. Prova com textos de apoio intercalados ao longo da avaliação;
10. Prova com julgamento e alternativas inline na mesma linha.

Garante também:
- Preservação da sequência e numeração original;
- Zero perda de palavras do texto original;
- Integração com o serviço de API `decompose_material_service`.
"""
from __future__ import annotations

import re
import sys
import unittest
from collections import Counter
from pathlib import Path

# Garante inclusão de backend/src no sys.path
TEST_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEST_DIR.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.api.routes.materials import decompose_material_service
from iris.parsers.structural_decomposer import decompose_material
from iris.schemas.materials import MaterialStructure, MaterialValidationError, QuestionItem


class TestStructuralDecomposer(unittest.TestCase):
    """Bateria de testes cobrindo os 10 cenários sintéticos da História 1.1.2."""

    def test_cenario_01_prova_tradicional_dissertativa(self) -> None:
        """Cenário 1: Cabeçalho institucional completo e questões dissertativas numeradas com ponto."""
        prova = (
            "Escola Municipal Cecília Meireles\n"
            "Disciplina: História - 7º Ano | Professor(a): Carlos\n"
            "Aluno(a): [ESTUDANTE] | Data: 15/06/2024\n"
            "Avaliação sobre a Idade Média na Europa Ocidental.\n\n"
            "1. Descreva as principais características do sistema feudal, destacando a relação de suserania e vassalagem.\n\n"
            "2. Explique a influência da Igreja Católica na sociedade medieval em termos culturais e políticos.\n\n"
            "3. Como o renascimento comercial e urbano a partir do século XI contribuiu para o declínio do feudalismo?"
        )

        res = decompose_material(prova)

        self.assertIsInstance(res, MaterialStructure)
        self.assertIsNotNone(res.header)
        self.assertIn("Cecília Meireles", res.header or "")
        self.assertEqual(res.total_questions, 3)
        self.assertEqual(len(res.questions), 3)

        # Ordem e numeração
        self.assertEqual(res.questions[0].original_number, "1")
        self.assertEqual(res.questions[1].original_number, "2")
        self.assertEqual(res.questions[2].original_number, "3")

        # Tipos
        for q in res.questions:
            self.assertEqual(q.question_type, "dissertativa")
            self.assertEqual(len(q.options), 0)

        # Conteúdo do enunciado
        self.assertIn("sistema feudal", res.questions[0].statement)
        self.assertIn("Igreja Católica", res.questions[1].statement)
        self.assertIn("renascimento comercial", res.questions[2].statement)

    def test_cenario_02_prova_multipla_escolha_a_a_e(self) -> None:
        """Cenário 2: Prova de múltipla escolha tradicional com alternativas A, B, C, D, E em linhas separadas."""
        prova = (
            "Colégio Tiradentes\n"
            "Simulado de Química - Ensino Médio\n\n"
            "Questão 1: Qual é o número atômico de um elemento que possui 12 prótons, 12 nêutrons e 12 elétrons?\n"
            "a) 6\n"
            "b) 12\n"
            "c) 24\n"
            "d) 36\n"
            "e) 48\n\n"
            "Questão 2: Sobre a tabela periódica dos elementos, assinale a opção correta:\n"
            "A) Os metais alcalinos estão localizados no grupo 17.\n"
            "B) Os gases nobres apresentam alta reatividade com a água.\n"
            "C) O raio atômico cresce da esquerda para a direita no mesmo período.\n"
            "D) O hidrogênio é um elemento pertencente à família dos halogênios.\n"
            "E) Os elementos do mesmo grupo possuem número semelhante de elétrons na camada de valência."
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 2)
        q1 = res.questions[0]
        q2 = res.questions[1]

        self.assertEqual(q1.question_type, "multipla_escolha")
        self.assertEqual(len(q1.options), 5)
        self.assertEqual([opt.letter for opt in q1.options], ["A", "B", "C", "D", "E"])
        self.assertEqual(q1.options[1].text, "12")

        self.assertEqual(q2.question_type, "multipla_escolha")
        self.assertEqual(len(q2.options), 5)
        self.assertEqual([opt.letter for opt in q2.options], ["A", "B", "C", "D", "E"])
        self.assertIn("camada de valência", q2.options[4].text)

    def test_cenario_03_texto_apoio_compartilhado_intervalo(self) -> None:
        """Cenário 3: Texto de apoio compartilhado com diretiva explícita de intervalo ('de 1 a 3')."""
        prova = (
            "Avaliação Bimestral de Língua Portuguesa\n\n"
            "Leia o texto a seguir para responder às questões de 1 a 3.\n"
            "Texto 1: A Cidade e a Infância\n"
            "Naquela época, a rua era o palco central das descobertas infantis. O asfalto quente não impedia "
            "as partidas intermináveis de futebol de botão e as brincadeiras de esconde-esconde até o pôr do sol.\n\n"
            "1. Qual é o tema central tratado pelo narrador no Texto 1?\n"
            "A) O perigo do tráfego urbano nas grandes cidades.\n"
            "B) A nostalgia das memórias afetivas da infância nas ruas.\n"
            "C) A história do futebol moderno no Brasil.\n"
            "D) Os impactos ambientais da urbanização acelerada.\n\n"
            "2. No trecho 'a rua era o palco central', a figura de linguagem predominante é:\n"
            "A) Metáfora.\n"
            "B) Metonímia.\n"
            "C) Pleonasmo.\n"
            "D) Hipérbole.\n\n"
            "3. Explique como a percepção do tempo é descrita pelas expressões do narrador.\n\n"
            "4. Reescreva a frase a seguir substituindo os pronomes destacados de acordo com a norma-padrão."
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 4)
        self.assertEqual(len(res.context_blocks), 1)
        cb = res.context_blocks[0]

        # Associação correta do texto compartilhado
        self.assertEqual(cb.target_questions, ["1", "2", "3"])
        self.assertIn("A Cidade e a Infância", cb.title or "")
        self.assertIn("futebol de botão", cb.text)
        self.assertTrue(res.has_shared_contexts)

        # Rastreabilidade cruzada
        self.assertIn(cb.id, res.questions[0].context_refs)
        self.assertIn(cb.id, res.questions[1].context_refs)
        self.assertIn(cb.id, res.questions[2].context_refs)
        self.assertEqual(len(res.questions[3].context_refs), 0)

    def test_cenario_04_texto_apoio_dedicado_individual(self) -> None:
        """Cenário 4: Texto de apoio dedicado precedente a uma única questão específica."""
        prova = (
            "1. Resolva a equação do segundo grau x² - 5x + 6 = 0 utilizando a fórmula de Bhaskara.\n\n"
            "Texto para a questão 2:\n"
            "Um foguete de brinquedo é lançado verticalmente e sua trajetória parabólica é modelada pela função "
            "h(t) = -5t² + 20t, onde h é a altura em metros e t é o tempo em segundos.\n\n"
            "2. Determine a altura máxima atingida pelo foguete e o instante de tempo em que isso ocorre."
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 2)
        self.assertEqual(len(res.context_blocks), 1)
        cb = res.context_blocks[0]

        self.assertEqual(cb.target_questions, ["2"])
        self.assertIn("foguete de brinquedo", cb.text)
        self.assertEqual(len(res.questions[0].context_refs), 0)
        self.assertIn(cb.id, res.questions[1].context_refs)

    def test_cenario_05_padroes_heterogeneos_de_numeracao(self) -> None:
        """Cenário 5: Prova com múltiplos estilos heterogêneos de numeração no mesmo documento."""
        prova = (
            "Lista de Exercícios Multidisciplinar\n\n"
            "Questão 01 - Calcule a média aritmética dos valores 10, 15 e 20.\n\n"
            "2) Qual é a função sintática do termo em destaque na frase?\n\n"
            "3. Explique a lei da gravitação universal de Newton.\n\n"
            "04 - Em relação à divisão celular, cite as etapas da intérfase.\n\n"
            "5º. Identifique a capital do estado de Minas Gerais."
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 5)
        # Preservação exata da ordem sequencial
        expected_numbers = ["01", "2", "3", "04", "5"]
        for idx, q in enumerate(res.questions):
            digits = "".join(filter(str.isdigit, q.original_number))
            self.assertEqual(digits, expected_numbers[idx])
            self.assertGreater(len(q.statement), 10)

    def test_cenario_06_questoes_densas_sem_quebras_de_pagina(self) -> None:
        """Cenário 6: Prova compacta sem linhas em branco entre questões consecutivas."""
        prova = (
            "1. O que é densidade demográfica?\n"
            "2. Qual a diferença entre taxa de natalidade e taxa de fecundidade?\n"
            "3. Explique o conceito de migração pendular.\n"
            "4. O que caracteriza o processo de conurbação urbana?"
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 4)
        self.assertEqual(res.questions[0].original_number, "1")
        self.assertEqual(res.questions[1].original_number, "2")
        self.assertEqual(res.questions[2].original_number, "3")
        self.assertEqual(res.questions[3].original_number, "4")

        self.assertIn("densidade demográfica", res.questions[0].statement)
        self.assertIn("taxa de natalidade", res.questions[1].statement)
        self.assertIn("migração pendular", res.questions[2].statement)
        self.assertIn("conurbação urbana", res.questions[3].statement)

    def test_cenario_07_linhas_e_espacos_de_resposta(self) -> None:
        """Cenário 7: Prova com linhas de resposta pontilhadas e sublinhadas."""
        prova = (
            "Atividade de Geografia\n\n"
            "1. Defina o conceito de bacia hidrográfica e cite dois exemplos no território brasileiro.\n"
            "____________________________________________________________________\n"
            "____________________________________________________________________\n"
            "____________________________________________________________________\n\n"
            "2. Quais são as consequências do desmatamento para o regime de chuvas da Amazônia?\n"
            "....................................................................\n"
            "....................................................................\n"
            "Resposta: __________________________________________________________"
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 2)
        q1 = res.questions[0]
        q2 = res.questions[1]

        self.assertIsNotNone(q1.answer_space)
        self.assertIn("___", q1.answer_space or "")
        self.assertNotIn("___", q1.statement)

        self.assertIsNotNone(q2.answer_space)
        self.assertIn("...", q2.answer_space or "")
        self.assertIn("regime de chuvas", q2.statement)

    def test_cenario_08_prova_mista_multipla_escolha_e_dissertativa(self) -> None:
        """Cenário 8: Prova com questão dissertativa, questão de múltipla escolha e mista com justificativa."""
        prova = (
            "Prova de Ciências da Natureza\n\n"
            "1. Explique a diferença entre calor e temperatura na termologia física.\n"
            "___________________________________________________\n\n"
            "2. A mudança do estado líquido para o gasoso que ocorre de maneira lenta e à temperatura ambiente chama-se:\n"
            "a) Ebulição.\n"
            "b) Evaporação.\n"
            "c) Calefação.\n"
            "d) Sublimação.\n\n"
            "3. O plástico é um material isolante térmico ou condutor? Justifique indicando uma aplicação prática:\n"
            "A) Condutor térmico.\n"
            "B) Isolante térmico.\n"
            "Justificativa: ____________________________________________________"
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 3)
        self.assertEqual(res.questions[0].question_type, "dissertativa")
        self.assertEqual(res.questions[1].question_type, "multipla_escolha")
        self.assertEqual(res.questions[2].question_type, "mista")
        self.assertEqual(len(res.questions[1].options), 4)
        self.assertEqual(len(res.questions[2].options), 2)
        self.assertIsNotNone(res.questions[2].answer_space)

    def test_cenario_09_textos_de_apoio_intercalados(self) -> None:
        """Cenário 9: Prova com múltiplos textos de apoio intercalados entre blocos de questões."""
        prova = (
            "Avaliação Interdisciplinar\n\n"
            "Texto 1: A Revolução Industrial\n"
            "As máquinas a vapor transformaram as relações de trabalho no século XVIII na Inglaterra.\n\n"
            "1. Em qual país teve início a Revolução Industrial?\n\n"
            "2. Como as condições de trabalho nas fábricas afetavam os operários?\n\n"
            "Texto para as questões 3 e 4:\n"
            "A urbanização desordenada gerou graves problemas sanitários nas cidades industriais inglesas.\n\n"
            "3. Quais epidemias eram comuns nas cidades fabris?\n\n"
            "4. Que medidas de saneamento básico foram implantadas posteriormente?"
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 4)
        self.assertEqual(len(res.context_blocks), 2)

        cb1 = res.context_blocks[0]
        cb2 = res.context_blocks[1]

        self.assertIn("máquinas a vapor", cb1.text)
        self.assertIn("urbanização desordenada", cb2.text)

        # Associação de CB2 com questões 3 e 4
        self.assertEqual(cb2.target_questions, ["3", "4"])
        self.assertIn(cb2.id, res.questions[2].context_refs)
        self.assertIn(cb2.id, res.questions[3].context_refs)

    def test_cenario_10_alternativas_inline_na_mesma_linha(self) -> None:
        """Cenário 10: Questão com alternativas compactadas na mesma linha horizontal."""
        prova = (
            "1. Qual é o antônimo da palavra efêmero?\n"
            "(A) Passageiro   (B) Duradouro   (C) Breve   (D) Rápido\n\n"
            "2. Assinale a opção que apresenta um substantivo abstrato:\n"
            "(A) Mesa   (B) Amor   (C) Livro   (D) Cadeira"
        )

        res = decompose_material(prova)

        self.assertEqual(res.total_questions, 2)
        q1 = res.questions[0]
        q2 = res.questions[1]

        self.assertEqual(q1.question_type, "multipla_escolha")
        self.assertEqual(len(q1.options), 4)
        self.assertEqual(q1.options[0].letter, "A")
        self.assertEqual(q1.options[0].text, "Passageiro")
        self.assertEqual(q1.options[1].letter, "B")
        self.assertEqual(q1.options[1].text, "Duradouro")

        self.assertEqual(q2.question_type, "multipla_escolha")
        self.assertEqual(len(q2.options), 4)
        self.assertEqual(q2.options[1].text, "Amor")

    def test_zero_loss_content_preservation(self) -> None:
        """Garante que palavras do texto bruto não sejam perdidas durante a decomposição."""
        texto = (
            "Colégio Central de Brasília\n"
            "1. Explique a teoria da relatividade geral de Einstein.\n"
            "2. O que são ondas gravitacionais?"
        )
        res = decompose_material(texto)

        # Todo conteúdo foi alocado em header, numeração ou enunciado das questões
        conteudo_total_decomposto = (res.header or "") + " "
        for q in res.questions:
            conteudo_total_decomposto += q.original_number + " " + q.statement + " "

        palavras_originais = Counter(re.findall(r"\b\w+\b", texto.lower()))
        palavras_decompostas = Counter(re.findall(r"\b\w+\b", conteudo_total_decomposto.lower()))

        # Nenhuma palavra do original pode faltar, contadas as repetições
        self.assertEqual(dict(palavras_originais - palavras_decompostas), {})

    def test_decompose_material_service_empty_text_validation(self) -> None:
        """O serviço decompose_material_service deve rejeitar texto vazio com MaterialValidationError."""
        with self.assertRaises(MaterialValidationError) as ctx:
            decompose_material_service("   \n \t  ")
        self.assertEqual(ctx.exception.code, "EMPTY_TEXT")

    def test_question_item_defaults(self) -> None:
        """QuestionItem pode ser instanciado sem passar options explicitamente."""
        q = QuestionItem(id="q_1", original_number="1", statement="Pergunta dissertativa", question_type="dissertativa")
        self.assertEqual(q.options, [])
        self.assertEqual(q.context_refs, [])
        self.assertIsNone(q.answer_space)

    def test_context_block_proximity_association(self) -> None:
        """Texto de apoio sem diretiva numérica explícita é associado por proximidade às questões contíguas."""
        texto = (
            "Texto de Apoio: Fotossíntese\n"
            "A fotossíntese converte energia luminosa em energia química armazenada em compostos orgânicos.\n\n"
            "1. Qual organela celular é responsável pela fotossíntese nas plantas?\n\n"
            "2. Quais são os principais reagentes e produtos dessa reação química?"
        )
        res = decompose_material(texto)
        self.assertEqual(len(res.context_blocks), 1)
        cb = res.context_blocks[0]
        self.assertEqual(cb.target_questions, ["1", "2"])
        self.assertIn(cb.id, res.questions[0].context_refs)
        self.assertIn(cb.id, res.questions[1].context_refs)


if __name__ == "__main__":
    unittest.main()
