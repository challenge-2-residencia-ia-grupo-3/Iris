import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from iris.agents.auditor import AgenteAuditor, trechos_novos
from iris.eval import juiz_auditor as ja
from iris.eval.trcc import avaliar_trcc


def _caminho():
    aqui = Path(__file__).resolve()
    for c in (ja.CAMINHO_PADRAO, aqui.parents[2] / "data/benchmarks/juiz_auditor_v1.json",
              aqui.parents[1] / "data/benchmarks/juiz_auditor_v1.json"):
        if c.exists():
            return c
    pytest.skip("juiz_auditor_v1.json não encontrado")


CASOS = None


@pytest.fixture(scope="module")
def casos():
    return ja.carregar_casos(_caminho())


def _catalogo(casos):
    ids = {i for c in casos for i in c["selecionadas"]} | {i for c in casos for i in c["esperado_intrusoes"]}
    return {"x": NS(caracteristicas=[NS(id_caracteristica=i, nome=i, descricao_observavel="d") for i in sorted(ids)])}


class Oraculo:
    """Responde o esperado de cada caso, localizando a minuta no prompt."""

    def __init__(self, casos, errar=()):
        self.por_minuta = {c["adaptada"]: c for c in casos}
        self.errar = set(errar)

    def generate(self, prompt, temperature=0.0, max_tokens=1500):
        minuta = prompt.split("MINUTA ADAPTADA:\n", 1)[1].split("\n\n", 1)[0]
        c = self.por_minuta[minuta]
        if c["id"] in self.errar:
            return "isto não é JSON"
        ev = trechos_novos(c["original"], c["adaptada"])[0]  # citação literal, como exige o auditor
        return json.dumps({"resolveu_questao": c["esperado_resolucao"], "evidencia_resolucao": ev,
                           "modificacoes_intrusivas": [{"caracteristica": i, "evidencia": ev} for i in c["esperado_intrusoes"]]})


def test_conjunto_bem_formado(casos):
    assert len(casos) >= 15
    assert {c["tipo"] for c in casos} == {"limpa", "identica", "resolucao", "intrusao"}
    assert any(c["esperado_resolucao"] for c in casos) and any(c["esperado_intrusoes"] for c in casos)


def test_adaptadas_unicas_para_o_oraculo(casos):
    assert len({c["adaptada"] for c in casos}) == len(casos)


def test_todas_as_minutas_preservam_as_travas(casos):
    # Assim, qualquer reprovação medida vem do juiz, não da TRCC.
    for c in casos:
        r = avaliar_trcc(c["travas"], c["adaptada"])
        assert r.trcc == 1.0, (c["id"], r.ausentes)


def test_originais_tem_as_travas(casos):
    for c in casos:
        assert avaliar_trcc(c["travas"], c["original"]).trcc == 1.0, c["id"]


def test_oraculo_acerta_tudo(casos):
    rel = ja.avaliar_juiz(casos, AgenteAuditor(Oraculo(casos)), _catalogo(casos))
    assert rel["erros"] == [] and rel["json_invalido"] == 0
    assert rel["resolucao"]["acuracia"] == 1.0 and rel["intrusao_por_id"]["recall"] == 1.0


def test_juiz_ruim_e_medido(casos):
    class Sempre:
        def generate(self, prompt, *a, **k):
            ev = prompt.split("ALTERADOS:\n- ", 1)[1].split("\n", 1)[0]
            return json.dumps({"resolveu_questao": True, "evidencia_resolucao": ev, "modificacoes_intrusivas": []})

    rel = ja.avaliar_juiz(casos, AgenteAuditor(Sempre()), _catalogo(casos))
    chamados_sem_resolucao = sum(
        1 for c in casos if not c["esperado_resolucao"] and trechos_novos(c["original"], c["adaptada"]))
    assert rel["resolucao"]["recall"] == 1.0 and rel["resolucao"]["fp"] == chamados_sem_resolucao
    assert rel["intrusao_por_id"]["recall"] == 0.0 and rel["erros"]


def test_json_invalido_e_contado_e_listado(casos):
    ruim = casos[0]["id"]
    rel = ja.avaliar_juiz(casos, AgenteAuditor(Oraculo(casos, errar=[ruim])), _catalogo(casos))
    assert rel["json_invalido"] == 1 and rel["erros"][0]["id"] == ruim


def test_deterministico_pega_resolucao_de_alternativa_unica(casos):
    # JUIZ-Q5-resolucao fica marcado como resolução mesmo com um juiz que nunca acusa nada.
    class Nunca:
        def generate(self, *a, **k):
            return json.dumps({"resolveu_questao": False, "modificacoes_intrusivas": []})

    q5 = [c for c in casos if c["id"] == "JUIZ-Q5-resolucao"]
    assert ja.avaliar_juiz(q5, AgenteAuditor(Nunca()), _catalogo(casos))["resolucao"]["tp"] == 1


def test_caso_incompleto_e_rejeitado(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="sem campos"):
        ja.carregar_casos(p)