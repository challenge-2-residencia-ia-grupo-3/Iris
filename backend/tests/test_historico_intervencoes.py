"""Histórico de eficácia das intervenções no Perfil Portátil (História 3.1.2, Issue #27, RF-15)."""
from __future__ import annotations

import copy
import importlib.util
import json
import unicodedata
from datetime import datetime, timedelta, timezone

import pytest

from iris.exportacao.perfil import exportar_perfil
from iris.schemas.portable_profile import (
    PerfilInvalidoError,
    PerfilPedagogico,
    registrar_intervencao,
    resumo_eficacia,
    validar_perfil,
)

ID_A = "atencao_sustentada_textos_longos"
ID_B = "sobrecarga_memoria_trabalho_comandos_multiplos"
T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

PERFIL = {
    "versao_schema": "1.0",
    "codigo_anonimo": "aluno-8f7a2c1b",
    "criado_em": "2026-11-01T12:00:00Z",
    "caracteristicas_selecionadas": [ID_A, ID_B],
    "barreiras_observadas": [],
    "historico_estrategias": [],
    "anotacoes_pedagogicas": [],
}


def novo(**kw) -> PerfilPedagogico:
    return validar_perfil({**PERFIL, **kw})


# ------------------------------------------------------------------ critério de aceitação
def test_anexa_o_registro_ao_historico_do_perfil():
    p = registrar_intervencao(novo(), "Fragmentação em checklist", ID_A, "alta", "Terminou a prova inteira.", agora=T0)
    assert len(p.historico_intervencoes) == 1
    r = p.historico_intervencoes[0]
    assert (r.estrategia, r.id_caracteristica, r.eficacia) == ("Fragmentação em checklist", ID_A, "alta")
    assert r.observacao == "Terminou a prova inteira." and r.registrado_em == T0


@pytest.mark.parametrize("entrada,esperado", [
    ("alta", "alta"), ("média", "media"), ("Média", "media"), ("MEDIA", "media"), (" baixa ", "baixa"),
])
def test_aceita_alta_media_baixa_com_ou_sem_acento(entrada, esperado):
    p = registrar_intervencao(novo(), "Checklist", ID_A, entrada, agora=T0)
    assert p.historico_intervencoes[0].eficacia == esperado


@pytest.mark.parametrize("ruim", ["", "ótima", "eficaz", "ineficaz", "média alta", "1", None, 3])
def test_eficacia_fora_de_alta_media_baixa_e_recusada(ruim):
    with pytest.raises(PerfilInvalidoError):
        registrar_intervencao(novo(), "Checklist", ID_A, ruim, agora=T0)  # type: ignore[arg-type]


def test_observacao_e_opcional():
    p = registrar_intervencao(novo(), "Checklist", ID_A, "baixa", agora=T0)
    assert p.historico_intervencoes[0].observacao is None
    p = registrar_intervencao(novo(), "Checklist", ID_A, "baixa", "", agora=T0)
    assert p.historico_intervencoes[0].observacao is None


# ------------------------------------------------------------------ histórico ordenado
def test_historico_fica_em_ordem_cronologica_de_registro():
    p = novo()
    for i, (est, ef) in enumerate([("Checklist", "alta"), ("Tempo extra", "media"), ("Enunciado em etapas", "baixa")]):
        p = registrar_intervencao(p, est, ID_A, ef, agora=T0 + timedelta(minutes=i))
    assert [r.estrategia for r in p.historico_intervencoes] == ["Checklist", "Tempo extra", "Enunciado em etapas"]
    assert [r.eficacia for r in p.historico_intervencoes] == ["alta", "media", "baixa"]


def test_perfil_importado_fora_de_ordem_e_reordenado_por_data():
    dados = {**PERFIL, "historico_intervencoes": [
        {"estrategia": "Segunda", "id_caracteristica": ID_A, "eficacia": "media", "registrado_em": "2026-11-12T10:00:00Z"},
        {"estrategia": "Primeira", "id_caracteristica": ID_A, "eficacia": "alta", "registrado_em": "2026-11-11T10:00:00Z"},
        {"estrategia": "Terceira", "id_caracteristica": ID_B, "eficacia": "baixa", "registrado_em": "2026-11-13T10:00:00Z"},
    ]}
    assert [r.estrategia for r in validar_perfil(dados).historico_intervencoes] == ["Primeira", "Segunda", "Terceira"]


def test_mesmo_instante_mantem_a_ordem_de_entrada():
    p = novo()
    for est in ("Um", "Dois", "Três"):
        p = registrar_intervencao(p, f"{est} passos", ID_A, "alta", agora=T0)
    assert [r.estrategia for r in p.historico_intervencoes] == ["Um passos", "Dois passos", "Três passos"]


def test_nao_altera_o_perfil_recebido_e_devolve_um_novo():
    original = novo()
    antes = copy.deepcopy(original.para_json())
    novo_perfil = registrar_intervencao(original, "Checklist", ID_A, "alta", agora=T0)
    assert original.para_json() == antes and original.historico_intervencoes == []
    assert novo_perfil is not original and novo_perfil.codigo_anonimo == original.codigo_anonimo


def test_aceita_o_perfil_como_dicionario_vindo_do_navegador():
    p = registrar_intervencao(PERFIL, "Checklist", ID_A, "alta", agora=T0)
    assert p.historico_intervencoes[0].estrategia == "Checklist"


# ------------------------------------------------------------------ regras
def test_perfil_antigo_sem_o_campo_continua_valido():
    assert validar_perfil(PERFIL).historico_intervencoes == []


def test_historico_de_estrategias_da_28_continua_funcionando():
    p = novo(historico_estrategias=[{"estrategia": "Dividir em passos", "resultado": "eficaz"}])
    p = registrar_intervencao(p, "Checklist", ID_A, "alta", agora=T0)
    assert len(p.historico_estrategias) == 1 and len(p.historico_intervencoes) == 1


def test_caracteristica_fora_do_perfil_e_recusada():
    with pytest.raises(PerfilInvalidoError) as e:
        registrar_intervencao(novo(), "Checklist", "caracteristica_que_nao_foi_marcada", "alta", agora=T0)
    assert e.value.codigo == "CHARACTERISTIC_NOT_IN_PROFILE"


@pytest.mark.parametrize("campo,valor", [
    ("estrategia", "ab"), ("estrategia", "x" * 301), ("observacao", "y" * 501), ("id_caracteristica", "Maiuscula Ruim"),
])
def test_limites_dos_campos(campo, valor):
    args = {"estrategia": "Checklist", "id_caracteristica": ID_A, "eficacia": "alta", "observacao": None, campo: valor}
    with pytest.raises(PerfilInvalidoError):
        registrar_intervencao(novo(), args["estrategia"], args["id_caracteristica"], args["eficacia"], args["observacao"], agora=T0)


def test_limite_de_200_registros():
    p = novo()
    dados = p.para_json()
    dados["historico_intervencoes"] = [
        {"estrategia": f"Estratégia {i}", "id_caracteristica": ID_A, "eficacia": "alta",
         "registrado_em": (T0 + timedelta(seconds=i)).isoformat()} for i in range(200)
    ]
    cheio = validar_perfil(dados)
    with pytest.raises(PerfilInvalidoError):
        registrar_intervencao(cheio, "Mais uma", ID_A, "alta", agora=T0 + timedelta(days=1))


def test_campo_nao_declarado_no_registro_e_rejeitado():
    dados = {**PERFIL, "historico_intervencoes": [
        {"estrategia": "Checklist", "id_caracteristica": ID_A, "eficacia": "alta", "nome_aluno": "João"}]}
    with pytest.raises(PerfilInvalidoError):
        validar_perfil(dados)


def test_data_sem_fuso_e_recusada():
    dados = {**PERFIL, "historico_intervencoes": [
        {"estrategia": "Checklist", "id_caracteristica": ID_A, "eficacia": "alta", "registrado_em": "2026-11-10T12:00:00"}]}
    with pytest.raises(PerfilInvalidoError):
        validar_perfil(dados)


# ------------------------------------------------------------------ RNF-03: nada clínico
@pytest.mark.parametrize("estrategia,observacao", [
    ("Seguir o laudo médico", None),
    ("Checklist", "Funciona melhor depois da Ritalina"),
    ("Checklist", "Aluno com TDAH, CID F90.0"),
    ("Checklist", "diagnosticado com dislexia"),
])
def test_bloqueia_conteudo_clinico_no_registro(estrategia, observacao):
    with pytest.raises(PerfilInvalidoError) as e:
        registrar_intervencao(novo(), estrategia, ID_A, "alta", observacao, agora=T0)
    assert e.value.codigo == "CLINICAL_DATA_BLOCKED"
    # a mensagem de erro não repete o que foi digitado
    for trecho in ("ritalina", "f90.0", "tdah", "dislexia"):
        assert trecho not in str(e.value).lower()


def test_observacao_pedagogica_comum_passa():
    p = registrar_intervencao(novo(), "Checklist de 5 passos", ID_A, "alta",
                              "Ficou mais calmo e terminou antes do fim do tempo.", agora=T0)
    assert p.historico_intervencoes


# ------------------------------------------------------------------ resumo
def test_resumo_de_eficacia_por_caracteristica():
    p = novo()
    for i, (cid, ef) in enumerate([(ID_A, "alta"), (ID_A, "baixa"), (ID_B, "media"), (ID_A, "media")]):
        p = registrar_intervencao(p, f"Estratégia {i}", cid, ef, agora=T0 + timedelta(minutes=i))
    r = resumo_eficacia(p)
    assert r[ID_A] == {"alta": 1, "media": 1, "baixa": 1, "total": 3, "ultima": "media"}
    assert r[ID_B] == {"alta": 0, "media": 1, "baixa": 0, "total": 1, "ultima": "media"}
    assert resumo_eficacia(novo()) == {}


# ------------------------------------------------------------------ exportação
def _perfil_com_historico():
    p = registrar_intervencao(novo(), "Fragmentação em checklist", ID_A, "alta", "Terminou a prova.", agora=T0)
    return registrar_intervencao(p, "Tempo extra", ID_B, "média", agora=T0 + timedelta(days=1)).para_json()


def test_json_exportado_carrega_o_historico():
    arq = exportar_perfil(_perfil_com_historico(), "json")
    dados = json.loads(arq.conteudo)
    assert [r["estrategia"] for r in dados["historico_intervencoes"]] == ["Fragmentação em checklist", "Tempo extra"]
    assert dados["historico_intervencoes"][1]["eficacia"] == "media"


def test_pdf_tem_a_secao_do_historico():
    if importlib.util.find_spec("pymupdf") is None and importlib.util.find_spec("fitz") is None:
        pytest.skip("PyMuPDF ausente")
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    arq = exportar_perfil(_perfil_com_historico(), "pdf")
    doc = pymupdf.open(stream=arq.conteudo, filetype="pdf")
    texto = unicodedata.normalize("NFKC", "\n".join(p.get_text() for p in doc))
    for esperado in ("Histórico de eficácia das intervenções", "Fragmentação em checklist", "eficácia alta", "eficácia média"):
        assert esperado in texto


def test_exportacao_troca_dado_pessoal_da_observacao():
    p = registrar_intervencao(novo(), "Checklist", ID_A, "alta", "Mãe ligou: (11) 98765-4321", agora=T0)
    texto = exportar_perfil(p.para_json(), "json").conteudo.decode()
    assert "98765-4321" not in texto


# ------------------------------------------------------------------ rota HTTP
@pytest.fixture()
def cliente():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from iris.main import create_app

    return TestClient(create_app())


CORPO = {"perfil": PERFIL, "intervencao": {"estrategia": "Fragmentação em checklist", "id_caracteristica": ID_A,
                                            "eficacia": "média", "observacao": "Funcionou em provas curtas."}}


def test_rota_devolve_o_perfil_com_o_registro_e_nao_guarda_nada(cliente):
    r = cliente.post("/api/v1/perfil/intervencoes", json=CORPO)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert d["perfil"]["historico_intervencoes"][0]["eficacia"] == "media"
    assert d["perfil"]["historico_intervencoes"][0]["registrado_em"]
    assert d["resumo_eficacia"][ID_A]["total"] == 1
    # segunda chamada com o perfil ORIGINAL: o servidor não lembrou do registro anterior
    r2 = cliente.post("/api/v1/perfil/intervencoes", json=CORPO)
    assert len(r2.json()["perfil"]["historico_intervencoes"]) == 1


def test_rota_encadeia_registros_quando_o_navegador_devolve_o_perfil(cliente):
    p1 = cliente.post("/api/v1/perfil/intervencoes", json=CORPO).json()["perfil"]
    outro = {"perfil": p1, "intervencao": {"estrategia": "Tempo extra", "id_caracteristica": ID_B, "eficacia": "baixa"}}
    p2 = cliente.post("/api/v1/perfil/intervencoes", json=outro).json()["perfil"]
    assert [r["estrategia"] for r in p2["historico_intervencoes"]] == ["Fragmentação em checklist", "Tempo extra"]


@pytest.mark.parametrize("corpo", [
    {}, {"perfil": PERFIL}, {"intervencao": CORPO["intervencao"]}, {"perfil": "x", "intervencao": {}},
    {**CORPO, "extra": 1},
    {"perfil": PERFIL, "intervencao": {**CORPO["intervencao"], "registrado_em": "2020-01-01T00:00:00Z"}},
    {"perfil": PERFIL, "intervencao": {**CORPO["intervencao"], "eficacia": "ótima"}},
    {"perfil": PERFIL, "intervencao": {**CORPO["intervencao"], "id_caracteristica": "caracteristica_fora_do_perfil"}},
    {"perfil": PERFIL, "intervencao": {**CORPO["intervencao"], "estrategia": 5}},
])
def test_rota_recusa_corpo_invalido(cliente, corpo):
    r = cliente.post("/api/v1/perfil/intervencoes", json=corpo)
    assert r.status_code == 422


def test_rota_recusa_clinico_sem_ecoar_o_que_foi_digitado(cliente):
    corpo = {"perfil": PERFIL, "intervencao": {**CORPO["intervencao"], "observacao": "toma Ritalina de manhã"}}
    r = cliente.post("/api/v1/perfil/intervencoes", json=corpo)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "CLINICAL_DATA_BLOCKED"
    assert "ritalina" not in r.text.lower()
