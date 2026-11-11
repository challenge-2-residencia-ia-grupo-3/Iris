import json

import pytest

from iris.agents.auditor import (
    AgenteAuditor,
    Caracteristica,
    caracteristicas_nao_selecionadas,
    montar_prompt_juiz,
    trechos_novos,
    parsear_veredito,
    sinais_resolucao_deterministicos,
)

ORIG = (
    "Uma loja vendeu 12 camisetas a R$ 25 cada e 8 bonés a R$ 15 cada. "
    "Qual o total arrecadado? Assinale a alternativa correta.\n"
    "A) R$ 300\nB) R$ 420\nC) R$ 500\nD) R$ 120"
)
TRAVAS = ["12 camisetas", "R$ 25", "8 bonés", "R$ 15", "total arrecadado"]
BOA = (
    "Uma loja vendeu 12 camisetas a R$ 25 cada.\nVendeu também 8 bonés a R$ 15 cada.\n"
    "Qual o total arrecadado? Assinale a alternativa correta.\n"
    "A) R$ 300\nB) R$ 420\nC) R$ 500\nD) R$ 120"
)
NAO_SEL = [Caracteristica("impulsividade_leitura_superficial_negacoes", "pressa e leitura rasa")]
OK = json.dumps({"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []})


class Juiz:
    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), 0

    def generate(self, prompt, temperature=0.0, max_tokens=1500):
        self.chamadas += 1
        r = self.respostas[min(self.chamadas - 1, len(self.respostas) - 1)]
        return r


def test_minuta_boa_aprovada():
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, BOA, TRAVAS, NAO_SEL)
    assert r.aprovado and r.trcc.trcc == 1.0 and not r.motivos


def test_trcc_baixa_reprova_e_feedback_cita_conceitos():
    adap = BOA.replace("R$ 25", "alguns reais").replace("8 bonés", "bonés")
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, adap, TRAVAS)
    assert not r.aprovado and r.trcc.trcc == pytest.approx(0.6)
    assert "R$ 25" in r.feedback() and "8 bonés" in r.feedback()


def test_trava_vazia_nao_aprova():
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, BOA, [])
    assert not r.aprovado and any("sem Trava" in m for m in r.motivos)


def test_assinale_alternativa_correta_do_original_nao_e_vazamento():
    assert sinais_resolucao_deterministicos(ORIG, BOA) == []


def test_marca_de_gabarito_nova_e_resolucao():
    adap = BOA + "\nGabarito: B"
    assert sinais_resolucao_deterministicos(ORIG, adap)
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, adap, TRAVAS)
    assert r.resolucao_indevida and not r.aprovado


def test_alternativas_eliminadas_ate_sobrar_uma():
    adap = BOA.split("A)")[0] + "B) R$ 420"
    assert any("eliminadas" in m for m in sinais_resolucao_deterministicos(ORIG, adap))


def test_juiz_detecta_resolucao_sutil():
    j = json.dumps({"resolveu_questao": True, "evidencia_resolucao": "Vendeu também 8 bonés a R$ 15 cada", "modificacoes_intrusivas": []})
    r = AgenteAuditor(Juiz(j)).auditar(ORIG, BOA, TRAVAS)
    assert r.resolucao_indevida and not r.aprovado


def test_juiz_detecta_intrusao_e_ignora_id_inventado():
    j = json.dumps({"resolveu_questao": False, "modificacoes_intrusivas": [
        {"caracteristica": "impulsividade_leitura_superficial_negacoes", "evidencia": "Vendeu também 8 bonés a R$ 15 cada"},
        {"caracteristica": "id_inexistente", "evidencia": "x"}]})
    r = AgenteAuditor(Juiz(j)).auditar(ORIG, BOA, TRAVAS, NAO_SEL)
    assert r.intrusoes == ("impulsividade_leitura_superficial_negacoes",) and not r.aprovado


def test_json_com_cerca_markdown_e_texto_em_volta():
    v = parsear_veredito("Claro!\n```json\n" + OK + "\n```", set())
    assert v.valido and not v.resolveu


def test_juiz_invalido_falha_fechado_com_uma_nova_tentativa():
    j = Juiz("não sei", "continua inválido")
    r = AgenteAuditor(j).auditar(ORIG, BOA, TRAVAS)
    assert j.chamadas == 2 and not r.juiz_valido and not r.aprovado


def test_juiz_se_recupera_na_segunda_tentativa():
    j = Juiz("lixo", OK)
    assert AgenteAuditor(j).auditar(ORIG, BOA, TRAVAS).aprovado and j.chamadas == 2


def test_resposta_do_juiz_como_objeto_com_text():
    class R:
        text = OK
    assert AgenteAuditor(Juiz(R())).auditar(ORIG, BOA, TRAVAS).aprovado


def test_prompt_so_lista_caracteristicas_nao_selecionadas():
    p = montar_prompt_juiz(ORIG, BOA, NAO_SEL)
    assert "impulsividade_leitura_superficial_negacoes" in p
    assert "NÃO SELECIONADAS" not in montar_prompt_juiz(ORIG, BOA, [])


def test_ciclo_corrige_na_segunda_tentativa():
    ruim = BOA.replace("R$ 25", "alguns reais")
    chamadas = []

    def adaptar(fb, anterior):
        chamadas.append((fb, anterior))
        return ruim if fb is None else BOA

    rel = AgenteAuditor(Juiz(OK)).executar_ciclo(ORIG, TRAVAS, adaptar)
    assert rel.aprovado and len(rel.tentativas) == 2 and rel.texto_final == BOA
    assert chamadas[0] == (None, None) and "R$ 25" in chamadas[1][0] and chamadas[1][1] == ruim
    assert not rel.requer_revisao_humana


def test_ciclo_esgotado_pede_revisao_humana():
    ruim = BOA.replace("R$ 25", "alguns reais")
    rel = AgenteAuditor(Juiz(OK)).executar_ciclo(ORIG, TRAVAS, lambda fb, ant: ruim, max_tentativas=3)
    assert not rel.aprovado and len(rel.tentativas) == 3 and rel.requer_revisao_humana


def test_ciclo_aprovado_de_primeira_nao_repete():
    rel = AgenteAuditor(Juiz(OK)).executar_ciclo(ORIG, TRAVAS, lambda fb, ant: BOA)
    assert rel.aprovado and len(rel.tentativas) == 1


def test_max_tentativas_invalido():
    with pytest.raises(ValueError):
        AgenteAuditor(Juiz(OK)).executar_ciclo(ORIG, TRAVAS, lambda f, a: BOA, max_tentativas=0)


# ---- ligação com o catálogo (objetos falsos no formato de load_all_catalogs) ----
from types import SimpleNamespace as NS  # noqa: E402


def _catalogos():
    def c(i):
        return NS(id_caracteristica=i, nome=f"Nome {i}", descricao_observavel=f"desc {i}")
    return {"tdah": NS(caracteristicas=[c("a_aaaaaa"), c("b_bbbbbb"), c("c_cccccc")]),
            "outro": NS(caracteristicas=[c("c_cccccc"), c("d_dddddd")])}


def test_nao_selecionadas_exclui_as_escolhidas_e_deduplica():
    r = caracteristicas_nao_selecionadas(["a_aaaaaa", "d_dddddd", "a_aaaaaa"], _catalogos())
    assert [x.id for x in r] == ["b_bbbbbb", "c_cccccc"]
    assert r[0].descricao == "Nome b_bbbbbb. desc b_bbbbbb"


def test_nao_selecionadas_id_inexistente_e_erro():
    with pytest.raises(KeyError, match="x_inexistente"):
        caracteristicas_nao_selecionadas(["a_aaaaaa", "x_inexistente"], _catalogos())


def test_nao_selecionadas_sem_selecao_devolve_todas():
    assert len(caracteristicas_nao_selecionadas([], _catalogos())) == 4


def test_nao_selecionadas_alimenta_o_auditor():
    nao = caracteristicas_nao_selecionadas(["a_aaaaaa"], _catalogos())
    assert "b_bbbbbb" in montar_prompt_juiz(ORIG, BOA, nao)


def test_catalogo_real_se_disponivel():
    try:
        from iris.schemas.catalog import load_all_catalogs
        cats = load_all_catalogs()
    except Exception:
        pytest.skip("catálogo real indisponível neste ambiente")
    if not cats:
        pytest.skip("nenhum catálogo em rag/catalogs/")
    ids = [c.id_caracteristica for cat in cats.values() for c in cat.caracteristicas]
    r = caracteristicas_nao_selecionadas(ids[:1])
    assert len(r) == len(set(ids)) - 1 and ids[0] not in {x.id for x in r}


# ---- integração com o Extrator (#17): invariantes no lugar da lista de travas ----
def _inv(**kw):
    base = dict(conceitos_obrigatorios=TRAVAS, termos_tecnicos_intocaveis=["R$ 25"],
                alerta_anti_muleta="Não calcule o total nem aponte a alternativa.")
    return NS(**{**base, **kw})


def test_aceita_invariantes_do_extrator():
    assert AgenteAuditor(Juiz(OK)).auditar(ORIG, BOA, _inv()).aprovado


def test_conceito_generico_do_extrator_e_ignorado():
    inv = _inv(conceitos_obrigatorios=TRAVAS + ["conteudo_curricular"])
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, BOA, inv)
    assert r.aprovado and r.trcc.trcc == 1.0


def test_so_conceito_generico_equivale_a_trava_vazia():
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, BOA, _inv(conceitos_obrigatorios=["conteudo_curricular"]))
    assert not r.aprovado and any("sem Trava" in m for m in r.motivos)


def test_termo_intocavel_ausente_reprova_mesmo_com_trcc_ok():
    termos = [f"termo{i}" for i in range(19)]
    texto = "12 camisetas " + " ".join(termos)  # "R$ 25" ausente: 1 de 20 => TRCC 95%
    inv = _inv(conceitos_obrigatorios=["12 camisetas", "R$ 25"] + termos[:18], termos_tecnicos_intocaveis=["R$ 25"])
    r = AgenteAuditor(Juiz(OK)).auditar(ORIG, texto, inv)
    assert r.trcc.aprovado() and r.intocaveis_ausentes == ("R$ 25",) and not r.aprovado
    assert "R$ 25" in r.feedback()


def test_alerta_anti_muleta_vai_para_o_prompt_do_juiz():
    assert "Não calcule o total" in montar_prompt_juiz(ORIG, BOA, [], "Não calcule o total")
    assert "ANTI-MULETA" not in montar_prompt_juiz(ORIG, BOA, [])


def test_prompt_enviado_ao_juiz_contem_o_alerta():
    visto = []

    class Espia(Juiz):
        def generate(self, prompt, **kw):
            visto.append(prompt)
            return super().generate(prompt, **kw)

    AgenteAuditor(Espia(OK)).auditar(ORIG, BOA, _inv())
    assert "Não calcule o total nem aponte" in visto[0]


def test_ciclo_com_invariantes_do_extrator():
    ruim = BOA.replace("R$ 25", "alguns reais")
    rel = AgenteAuditor(Juiz(OK)).executar_ciclo(ORIG, _inv(), lambda fb, ant: ruim if fb is None else BOA)
    assert rel.aprovado and len(rel.tentativas) == 2


def test_com_curriculum_invariants_real_se_disponivel():
    mod = pytest.importorskip("iris.schemas.curriculum")
    inv = mod.CurriculumInvariants(
        conceitos_obrigatorios=TRAVAS, termos_tecnicos_intocaveis=["R$ 25"], verbo_comando_bncc="calcular",
        operacao_cognitiva="somar os totais de cada produto", habilidade_bncc_sugerida=None,
        alerta_anti_muleta="Não entregue o total.", justificativa_preservacao="Preserva os dados.")
    assert AgenteAuditor(Juiz(OK)).auditar(ORIG, BOA, inv).aprovado


# ---- diff determinístico e evidência literal (corrigem o juiz que acusava tudo) ----
def test_trechos_novos_ignora_o_que_ja_existia():
    assert trechos_novos(ORIG, ORIG) == []
    novos = trechos_novos(ORIG, BOA)
    assert "Vendeu também 8 bonés a R$ 15 cada." in novos
    assert not any(n.startswith(("A)", "B)", "C)", "D)")) for n in novos)


def test_minuta_identica_nao_chama_o_juiz():
    j = Juiz("lixo")
    r = AgenteAuditor(j).auditar(ORIG, ORIG, TRAVAS, NAO_SEL)
    assert j.chamadas == 0 and r.aprovado


def test_prompt_mostra_so_os_trechos_novos():
    p = montar_prompt_juiz(ORIG, BOA, NAO_SEL)
    sec = p.split("TRECHOS ACRESCENTADOS OU ALTERADOS:\n", 1)[1].split("\n\n", 1)[0]
    assert "Vendeu também 8 bonés" in sec and "A) R$ 300" not in sec


def test_acusacao_sem_evidencia_literal_e_descartada():
    j = json.dumps({"resolveu_questao": True, "evidencia_resolucao": "texto inventado pelo modelo",
                    "modificacoes_intrusivas": [{"caracteristica": NAO_SEL[0].id, "evidencia": ""}]})
    r = AgenteAuditor(Juiz(j)).auditar(ORIG, BOA, TRAVAS, NAO_SEL)
    assert r.aprovado and not r.resolucao_indevida and not r.intrusoes
    assert any("descartada" in m for m in r.motivos)


def test_evidencia_que_so_existe_no_original_e_descartada():
    j = json.dumps({"resolveu_questao": False, "modificacoes_intrusivas": [
        {"caracteristica": NAO_SEL[0].id, "evidencia": "Qual o total arrecadado?"}]})
    assert AgenteAuditor(Juiz(j)).auditar(ORIG, BOA, TRAVAS, NAO_SEL).aprovado


def test_calculo_resolvido_e_detectado_sem_llm():
    adap = BOA + "\nEtapa 1: 12 × 25 = R$ 300."
    assert any("cálculo" in m for m in sinais_resolucao_deterministicos(ORIG, adap))
    assert not any("cálculo" in m for m in sinais_resolucao_deterministicos(ORIG, BOA))
    assert not sinais_resolucao_deterministicos("Resolva 2x + 6 = 14.", "Resolva 2x + 6 = 14. Passo a passo.")


# ---- nova tentativa do juiz e intrusão só como aviso ----
def test_retentativa_varia_temperatura_e_dobra_tokens():
    chamadas = []

    class Registra(Juiz):
        def generate(self, prompt, temperature=0.0, max_tokens=1500):
            chamadas.append((temperature, max_tokens))
            return super().generate(prompt, temperature, max_tokens)

    AgenteAuditor(Registra("lixo", OK), max_tokens=500).auditar(ORIG, BOA, TRAVAS)
    assert chamadas == [(0.0, 500), (0.3, 1000)]


def _intrusao_json():
    return json.dumps({"resolveu_questao": False, "modificacoes_intrusivas": [
        {"caracteristica": NAO_SEL[0].id, "evidencia": "Vendeu também 8 bonés a R$ 15 cada"}]})


def test_intrusao_como_aviso_nao_reprova_mas_fica_registrada():
    r = AgenteAuditor(Juiz(_intrusao_json()), intrusao_bloqueia=False).auditar(ORIG, BOA, TRAVAS, NAO_SEL)
    assert r.aprovado and r.intrusoes == (NAO_SEL[0].id,)
    assert any("intrusão" in m for m in r.motivos)


def test_intrusao_bloqueia_por_padrao_e_entra_no_feedback():
    r = AgenteAuditor(Juiz(_intrusao_json())).auditar(ORIG, BOA, TRAVAS, NAO_SEL)
    assert not r.aprovado and NAO_SEL[0].id in r.feedback()