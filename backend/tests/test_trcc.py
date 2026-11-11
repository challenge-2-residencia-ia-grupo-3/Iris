"""Testes do TRCC determinístico e de aceitação da trava curricular do Golden Benchmark."""

import unittest

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]

from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.metrics import calcular_trcc
from iris.eval.trcc import agregar, avaliar_benchmark, avaliar_trcc, normalizar, parse_trava


# ------------------------------------------------------------------ regras de comparação


def test_normalizar_acento_caixa_e_operadores():
    assert normalizar("Área  do Retângulo") == "area do retangulo"
    assert normalizar("2x + 6 = 14") == normalizar("2x+6=14")
    assert normalizar("x² − 9 = 0") == normalizar("x²-9=0")


def test_palavra_inteira():
    assert avaliar_trcc(["12"], "tinha 120 balas").trcc == 0.0
    assert avaliar_trcc(["12"], "tinha 12 balas").trcc == 1.0
    assert avaliar_trcc(["pi"], "o pipeline roda").trcc == 0.0


def test_ignora_acento_e_caixa():
    assert avaliar_trcc(["área", "João"], "AREA do terreno de joao").trcc == 1.0


def test_alternativas():
    r = avaliar_trcc(["encontrou|achou", "cachorro"], "Pedro achou o cachorro")
    assert r.trcc == 1.0 and not r.ausentes


def test_operador_sem_espacos():
    assert avaliar_trcc(["2x + 6 = 14"], "Resolva 2x+6=14.").trcc == 1.0
    assert avaliar_trcc(["soma|+"], "calcule 345+278").trcc == 1.0


def test_conceito_ausente_e_listado():
    r = avaliar_trcc(["área", "retângulo", "perímetro"], "Calcule a área do retângulo")
    assert abs(r.trcc - (2 / 3)) < 1e-6
    assert r.ausentes == ("perímetro",)
    assert not r.aprovado()


def test_trava_vazia_nao_e_cem_por_cento():
    assert avaliar_trcc([], "qualquer texto").trcc is None
    assert avaliar_trcc(None, "qualquer texto").trcc is None
    assert not avaliar_trcc([], "texto").aprovado()


def test_texto_nao_e_percorrido_letra_a_letra():
    # Erro clássico: tratar "area do retangulo" como lista de caracteres daria ~100% sem medir nada.
    assert len(parse_trava("area do retangulo")) == 1
    assert avaliar_trcc("área; retângulo", "só a área").trcc == 0.5


def test_calcular_trcc_de_metrics_usa_regra_nova_e_recusa_trava_vazia():
    assert calcular_trcc(["encontrou|achou"], "Pedro achou") == 1.0
    try:
        calcular_trcc([], "texto")
        raise AssertionError("Esperado ValueError para trava vazia")
    except ValueError:
        pass


# ------------------------------------------------------------------ agregação


def test_agregar_micro_macro_e_limiar():
    res = avaliar_benchmark(
        {"A": ["a", "b"], "B": ["c", "d", "e", "f"]},
        {"A": "a b", "B": "c d e"},
    )
    resumo = agregar(res)
    assert abs(resumo["trcc_micro"] - (5 / 6)) <= 1e-4
    assert abs(resumo["trcc_macro"] - ((1 + 0.75) / 2)) <= 1e-4
    assert resumo["questoes_abaixo_do_limiar"] == ["B"]
    assert not resumo["aprovado_micro"] and not resumo["aprovado_todas_as_questoes"]


def test_agregar_questao_sem_trava_impede_aprovacao():
    res = avaliar_benchmark({"A": ["a"], "B": []}, {"A": "a", "B": "x"})
    resumo = agregar(res)
    assert resumo["sem_trava"] == ["B"]
    assert not resumo["aprovado_micro"] and not resumo["aprovado_todas_as_questoes"]


def test_avaliar_benchmark_exige_texto_para_todas_as_questoes():
    try:
        avaliar_benchmark({"A": ["a"], "B": ["b"]}, {"A": "a"})
        raise AssertionError("Esperado KeyError")
    except KeyError:
        pass


# ------------------------------------------------------------------ Golden Benchmark


if pytest is not None:
    @pytest.fixture(scope="module")
    def questoes():
        return carregar_golden_benchmark()


def test_toda_questao_tem_trava_curricular(questoes):
    sem = [q.id for q in questoes if not q.trava_curricular]
    assert not sem, f"Questões sem trava_curricular (o TRCC não pode ser medido): {sem}"


def test_trava_esta_no_enunciado_original(questoes):
    # O denominador da fórmula é "conceitos da trava no material ORIGINAL": toda trava
    # precisa aparecer no próprio enunciado, senão a trava está mal escrita.
    fora = {q.id: avaliar_trcc(q.trava_curricular, q.enunciado).ausentes for q in questoes}
    fora = {qid: aus for qid, aus in fora.items() if aus}
    assert not fora, f"Conceitos da trava ausentes do enunciado original: {fora}"


def test_adaptacao_identica_passa_e_texto_vazio_reprova(questoes):
    travas = {q.id: q.trava_curricular for q in questoes}
    ok = agregar(avaliar_benchmark(travas, {q.id: q.enunciado for q in questoes}))
    assert ok["aprovado_micro"] and ok["aprovado_todas_as_questoes"]

    ruim = agregar(avaliar_benchmark(travas, {q.id: "" for q in questoes}))
    assert not ruim["aprovado_micro"] and ruim["trcc_micro"] == 0.0


class TestTrccDeterministico(unittest.TestCase):
    def test_regras_de_comparacao_e_agregacao(self) -> None:
        test_normalizar_acento_caixa_e_operadores()
        test_palavra_inteira()
        test_ignora_acento_e_caixa()
        test_alternativas()
        test_operador_sem_espacos()
        test_conceito_ausente_e_listado()
        test_trava_vazia_nao_e_cem_por_cento()
        test_texto_nao_e_percorrido_letra_a_letra()
        test_calcular_trcc_de_metrics_usa_regra_nova_e_recusa_trava_vazia()
        test_agregar_micro_macro_e_limiar()
        test_agregar_questao_sem_trava_impede_aprovacao()
        test_avaliar_benchmark_exige_texto_para_todas_as_questoes()

    def test_golden_benchmark_travas_curriculares(self) -> None:
        qs = carregar_golden_benchmark()
        test_toda_questao_tem_trava_curricular(qs)
        test_trava_esta_no_enunciado_original(qs)
        test_adaptacao_identica_passa_e_texto_vazio_reprova(qs)


if __name__ == "__main__":
    unittest.main()
