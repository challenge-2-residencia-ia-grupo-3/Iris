"""Aceitação da Semana 3 sobre as saídas REAIS da Íris (reports/saidas/iris.jsonl).

Pulado enquanto as saídas não existem. Quando existirem, falha se TRCC ou Faithfulness
não atingirem a meta (RNF-04/05).
"""

from pathlib import Path

import pytest

from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.relatorio import gerar_relatorio

SAIDAS = Path(__file__).resolve().parents[1] / "reports" / "saidas"

pytestmark = pytest.mark.skipif(not (SAIDAS / "iris.jsonl").exists(), reason="sem saídas reais da Íris")


@pytest.fixture(scope="module")
def rel():
    return gerar_relatorio(carregar_golden_benchmark(), SAIDAS)


def test_nenhum_criterio_obrigatorio_reprovado(rel):
    reprovados = {n: c for n, c in rel["criterios"].items() if c["obrigatorio"] and c["status"] == "reprovado"}
    assert not reprovados, reprovados


def test_trcc_e_faithfulness_medidos(rel):
    assert rel["criterios"]["trcc_micro"]["status"] == "aprovado"
    assert rel["criterios"]["faithfulness"]["status"] in ("aprovado", "nao_medido")