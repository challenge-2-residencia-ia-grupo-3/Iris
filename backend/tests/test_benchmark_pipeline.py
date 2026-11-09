"""Testes do pipeline do benchmark (executor, Faithfulness, relatório) com sistemas sintéticos."""

import json
import tempfile
import unittest
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]

from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.executar import adaptador_identidade, executar_sistema, ler_saidas
from iris.eval.faithfulness import medir_faithfulness
from iris.eval.relatorio import gerar_relatorio, para_markdown


if pytest is not None:
    @pytest.fixture(scope="module")
    def questoes():
        return carregar_golden_benchmark()


def _truncar(q):
    """Sistema ruim: guarda só as 3 primeiras palavras (perde a trava)."""
    return {"adaptado": " ".join(q.enunciado.split()[:3]), "contextos": ["trecho"]}


def _com_contexto(q):
    return {"adaptado": q.enunciado, "contextos": ["trecho do corpus"]}


async def _juiz(pergunta, resposta, contextos):
    return 0.95


def test_executor_grava_e_retoma(questoes, tmp_path):
    r1 = executar_sistema(adaptador_identidade, questoes, "x", tmp_path, limite=5, progresso=None)
    assert r1["executadas"] == 5
    r2 = executar_sistema(adaptador_identidade, questoes, "x", tmp_path, progresso=None)
    assert r2["puladas"] == 5 and r2["executadas"] == len(questoes) - 5
    assert len(ler_saidas(tmp_path / "x.jsonl")) == len(questoes)


def test_executor_registra_erro_e_segue(questoes, tmp_path):
    def instavel(q):
        if q.id == questoes[1].id:
            raise RuntimeError("falhou")
        return q.enunciado

    r = executar_sistema(instavel, questoes, "x", tmp_path, progresso=None)
    assert r["falhas"] == 1 and r["executadas"] == len(questoes) - 1
    assert "RuntimeError" in ler_saidas(tmp_path / "x.jsonl")[questoes[1].id]["erro"]
    # a questão com erro é refeita na retomada
    r2 = executar_sistema(adaptador_identidade, questoes, "x", tmp_path, progresso=None)
    assert r2["executadas"] == 1


def test_faithfulness_pula_sem_contexto(questoes, tmp_path):
    executar_sistema(adaptador_identidade, questoes, "puro", tmp_path, progresso=None)
    res = medir_faithfulness(questoes, ler_saidas(tmp_path / "puro.jsonl"), _juiz)
    assert res["scores"] == {} and len(res["sem_contexto"]) == len(questoes)

    executar_sistema(_com_contexto, questoes, "iris", tmp_path, progresso=None)
    res = medir_faithfulness(questoes, ler_saidas(tmp_path / "iris.jsonl"), _juiz)
    assert set(res["scores"].values()) == {0.95}


def test_faithfulness_erro_do_juiz_nao_derruba(questoes, tmp_path):
    executar_sistema(_com_contexto, questoes, "iris", tmp_path, progresso=None)

    async def quebrado(p, r, c):
        raise TimeoutError("sem rede")

    res = medir_faithfulness(questoes, ler_saidas(tmp_path / "iris.jsonl"), quebrado)
    assert len(res["erros"]) == len(questoes) and all(v is None for v in res["scores"].values())


def _montar(questoes, tmp_path, alvo, nota=0.95):
    executar_sistema(alvo, questoes, "iris", tmp_path, progresso=None)
    executar_sistema(_truncar, questoes, "llm_puro", tmp_path, progresso=None)
    if nota is not None:
        async def juiz(p, r, c):
            return nota

        res = medir_faithfulness(questoes, ler_saidas(tmp_path / "iris.jsonl"), juiz)
        res["juiz"] = "teste"
        (tmp_path / "iris.faithfulness.json").write_text(json.dumps(res), encoding="utf-8")


def test_relatorio_aprovado_mas_preliminar_com_rascunho(questoes, tmp_path):
    _montar(questoes, tmp_path, _com_contexto)
    rel = gerar_relatorio(questoes, tmp_path)
    assert rel["criterios"]["trcc_micro"]["status"] == "aprovado"
    assert rel["criterios"]["faithfulness"]["status"] == "aprovado"
    assert rel["criterios"]["hipotese_llm_puro"]["status"] == "aprovado"
    esperado = "PRELIMINAR" if rel["benchmark_rascunho"] else "APROVADO"
    assert rel["veredito"] == esperado
    assert "Veredito" in para_markdown(rel)


def test_relatorio_reprova_por_faithfulness_baixa(questoes, tmp_path):
    _montar(questoes, tmp_path, _com_contexto, nota=0.80)
    assert gerar_relatorio(questoes, tmp_path)["veredito"] == "REPROVADO"


def test_relatorio_reprova_por_trcc(questoes, tmp_path):
    _montar(questoes, tmp_path, _truncar)
    rel = gerar_relatorio(questoes, tmp_path)
    assert rel["criterios"]["trcc_micro"]["status"] == "reprovado" and rel["veredito"] == "REPROVADO"


def test_relatorio_sem_faithfulness_e_incompleto(questoes, tmp_path):
    _montar(questoes, tmp_path, _com_contexto, nota=None)
    rel = gerar_relatorio(questoes, tmp_path)
    assert rel["criterios"]["faithfulness"]["status"] == "nao_medido" and rel["veredito"] == "INCOMPLETO"


def test_relatorio_saida_parcial_nunca_aprova(questoes, tmp_path):
    executar_sistema(_com_contexto, questoes, "iris", tmp_path, limite=10, progresso=None)
    rel = gerar_relatorio(questoes, tmp_path, referencia=None)
    assert rel["criterios"]["completude"]["status"] == "reprovado"
    assert rel["veredito"] == "REPROVADO"


def test_relatorio_sem_saidas_levanta(questoes, tmp_path):
    try:
        gerar_relatorio(questoes, tmp_path)
        raise AssertionError("Esperado FileNotFoundError")
    except FileNotFoundError:
        pass


class TestBenchmarkPipeline(unittest.TestCase):
    def test_executor_faithfulness_e_relatorio(self) -> None:
        qs = carregar_golden_benchmark()
        with tempfile.TemporaryDirectory() as d1:
            test_executor_grava_e_retoma(qs, Path(d1))
        with tempfile.TemporaryDirectory() as d2:
            test_executor_registra_erro_e_segue(qs, Path(d2))
        with tempfile.TemporaryDirectory() as d3:
            test_faithfulness_pula_sem_contexto(qs, Path(d3))
        with tempfile.TemporaryDirectory() as d4:
            test_faithfulness_erro_do_juiz_nao_derruba(qs, Path(d4))
        with tempfile.TemporaryDirectory() as d5:
            test_relatorio_aprovado_mas_preliminar_com_rascunho(qs, Path(d5))
        with tempfile.TemporaryDirectory() as d6:
            test_relatorio_reprova_por_faithfulness_baixa(qs, Path(d6))
        with tempfile.TemporaryDirectory() as d7:
            test_relatorio_reprova_por_trcc(qs, Path(d7))
        with tempfile.TemporaryDirectory() as d8:
            test_relatorio_sem_faithfulness_e_incompleto(qs, Path(d8))
        with tempfile.TemporaryDirectory() as d9:
            test_relatorio_saida_parcial_nunca_aprova(qs, Path(d9))
        with tempfile.TemporaryDirectory() as d10:
            test_relatorio_sem_saidas_levanta(qs, Path(d10))


if __name__ == "__main__":
    unittest.main()