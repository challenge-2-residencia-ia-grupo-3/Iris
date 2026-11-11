"""Testes do schema BenchmarkQuestionItem e do dataset questoes_escolares_v1.json."""

import pytest
from pydantic import ValidationError

from iris.schemas.benchmark import (
    CAMINHO_PADRAO,
    CATALOGOS_PADRAO,
    MINIMO_QUESTOES,
    BenchmarkQuestionItem,
    carregar_questoes_escolares,
    ids_caracteristicas,
    validar_conjunto,
)


def item(**kw):
    base = dict(
        id="E01",
        disciplina="Matemática",
        ano_escolar="8º ano EF",
        habilidade_bncc="EF08MA06",
        enunciado_original="Resolva a equação 2x + 6 = 14 e indique o valor de x.",
        conceitos_trava_curricular=["2x + 6 = 14", "valor de x"],
        operacao_cognitiva="aplicar",
        id_caracteristica_alvo="CARAC-01",
    )
    base.update(kw)
    return base


def test_item_valido():
    q = BenchmarkQuestionItem(**item())
    assert q.status == "rascunho" and q.alternativas is None


def test_campos_obrigatorios_e_extras_proibidos():
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**{k: v for k, v in item().items() if k != "habilidade_bncc"})
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**item(campo_inventado=1))


@pytest.mark.parametrize("codigo", ["EF08MA06", "EF67LP28", "EM13MAT101", "EM13LP01"])
def test_bncc_aceita_codigos_reais(codigo):
    assert BenchmarkQuestionItem(**item(habilidade_bncc=codigo))


@pytest.mark.parametrize("codigo", ["MA06", "EF8MA6", "ef08ma06", ""])
def test_bncc_recusa_codigos_invalidos(codigo):
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**item(habilidade_bncc=codigo))


def test_ano_e_operacao_sao_vocabulario_fechado():
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**item(ano_escolar="4º ano EF"))
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**item(operacao_cognitiva="decorar"))


def test_alternativas():
    alts = [{"letra": "A", "texto": "4"}, {"letra": "B", "texto": "8"}]
    q = BenchmarkQuestionItem(**item(alternativas=alts))
    assert "A) 4" in q.texto_completo
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**item(alternativas=[{"letra": "A", "texto": "4"}]))
    with pytest.raises(ValidationError):
        BenchmarkQuestionItem(**item(alternativas=[{"letra": "A", "texto": "4"}, {"letra": "A", "texto": "8"}]))


def test_trava_precisa_estar_no_original_e_pode_estar_nas_alternativas():
    with pytest.raises(ValidationError, match="ausentes"):
        BenchmarkQuestionItem(**item(conceitos_trava_curricular=["equação", "logaritmo"]))
    alts = [{"letra": "A", "texto": "logaritmo"}, {"letra": "B", "texto": "raiz"}]
    assert BenchmarkQuestionItem(**item(conceitos_trava_curricular=["equação", "logaritmo"], alternativas=alts))


def test_trava_vazia_ou_repetida_recusada():
    for trava in ([], [" "], ["equação", "equação"]):
        with pytest.raises(ValidationError):
            BenchmarkQuestionItem(**item(conceitos_trava_curricular=trava))


def test_validar_conjunto():
    itens = [BenchmarkQuestionItem(**item(id=f"E{i:02d}")) for i in range(3)]
    probs = " | ".join(validar_conjunto(itens, minimo=3))
    assert "sem fonte" in probs and "mínimo" not in probs
    assert any("mínimo" in p for p in validar_conjunto(itens, minimo=30, exigir_fonte=False))
    dup = [itens[0], itens[0]]
    assert any("repetidos" in p for p in validar_conjunto(dup, minimo=1, exigir_fonte=False))
    assert any("catálogo" in p for p in validar_conjunto(itens, 1, catalogo_ids={"X"}, exigir_fonte=False))


# ---- dataset real: pulado até o arquivo existir ----

pytestmark_dataset = pytest.mark.skipif(not CAMINHO_PADRAO.exists(), reason="dataset v1 ainda não criado")


@pytestmark_dataset
def test_dataset_v1_valido_e_completo():
    itens = carregar_questoes_escolares()
    ids = ids_caracteristicas() or None
    assert validar_conjunto(itens, MINIMO_QUESTOES, catalogo_ids=ids) == []


def test_ids_do_catalogo_lidos_do_disco(tmp_path):
    (tmp_path / "x.json").write_text('[{"id_caracteristica": "abc_def_ghi"}]', encoding="utf-8")
    assert ids_caracteristicas(tmp_path) == {"abc_def_ghi"}


@pytest.mark.skipif(not CATALOGOS_PADRAO.exists(), reason="sem rag/catalogs")
def test_catalogo_real_tem_ids():
    assert len(ids_caracteristicas()) >= 10
