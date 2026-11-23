"""Importação e restauração do Perfil Pedagógico Portátil a partir do .json (História 3.2.2, Issue #31, RF-15)."""
from __future__ import annotations

import json

import iris.api.routes.perfil as rota_perfil
import pytest
from iris.api.routes.perfil import MAX_BYTES_ARQUIVO, importar_perfil_service
from iris.exportacao.perfil import exportar_perfil
from iris.schemas.portable_profile import PerfilInvalidoError

ID_A = "atencao_sustentada_textos_longos"
ID_B = "sobrecarga_memoria_trabalho_comandos_multiplos"

# Forma exata do arquivo que o frontend baixa (frontend/src/services/portableProfile.ts).
PERFIL = {
    "versao_schema": "1.0",
    "codigo_anonimo": "aluno-8f7a2c1b",
    "criado_em": "2026-11-13T12:00:00.000Z",
    "caracteristicas_selecionadas": [ID_A, ID_B],
    "barreiras_observadas": [],
    "historico_estrategias": [],
    "anotacoes_pedagogicas": [],
}

COM_HISTORICO = {
    **PERFIL,
    "historico_intervencoes": [
        {
            "estrategia": "Checklist com andaime nível 2",
            "id_caracteristica": ID_A,
            "eficacia": "alta",
            "observacao": None,
            "registrado_em": "2026-11-20T12:00:00Z",
        }
    ],
}


def texto(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=2)


def importar(conteudo: str) -> dict:
    return importar_perfil_service({"arquivo": conteudo})


# ------------------------------------------------------------------ critério de aceitação: arquivo válido
def test_arquivo_valido_volta_normalizado_com_as_caracteristicas():
    r = importar(texto(PERFIL))
    assert r["perfil"]["codigo_anonimo"] == "aluno-8f7a2c1b"
    assert r["perfil"]["caracteristicas_selecionadas"] == [ID_A, ID_B]
    assert r["resumo_eficacia"] == {}


def test_historico_de_eficacia_volta_resumido_por_caracteristica():
    r = importar(texto(COM_HISTORICO))
    assert r["resumo_eficacia"][ID_A] == {"alta": 1, "media": 0, "baixa": 0, "total": 1, "ultima": "alta"}
    assert r["perfil"]["historico_intervencoes"][0]["eficacia"] == "alta"


def test_arquivo_exportado_pela_propria_plataforma_pode_ser_reimportado():
    exportado = exportar_perfil(COM_HISTORICO, "json")
    r = importar(exportado.conteudo.decode("utf-8"))
    assert r["perfil"]["caracteristicas_selecionadas"] == [ID_A, ID_B]
    assert len(r["perfil"]["historico_intervencoes"]) == 1


def test_arquivo_com_bom_utf8_e_aceito():
    assert importar("﻿" + texto(PERFIL))["perfil"]["codigo_anonimo"] == "aluno-8f7a2c1b"


# ------------------------------------------------------------------ critério: arquivo corrompido ou fora do padrão
@pytest.mark.parametrize(
    "conteudo,codigo",
    [
        ("isto não é json", "INVALID_JSON"),
        ('{"versao_schema": "1.0", "codigo_anonimo": ', "INVALID_JSON"),  # truncado
        ("[1, 2, 3]", "INVALID_STRUCTURE"),
        ('"texto solto"', "INVALID_STRUCTURE"),
        ("{}", "INVALID_STRUCTURE"),
        ("", "EMPTY_FILE"),
        ("   \n  ", "EMPTY_FILE"),
    ],
)
def test_arquivo_corrompido_vira_erro_com_mensagem_clara(conteudo, codigo):
    with pytest.raises(PerfilInvalidoError) as e:
        importar(conteudo)
    assert e.value.codigo == codigo
    assert str(e.value)  # a mensagem existe e é legível


@pytest.mark.parametrize(
    "mudanca",
    [
        {"versao_schema": "2.0"},
        {"codigo_anonimo": "Maria da Silva"},
        {"codigo_anonimo": "aluno-xyz"},
        {"criado_em": "ontem"},
        {"caracteristicas_selecionadas": "memoria"},
        {"caracteristicas_selecionadas": [ID_A, ID_A]},
        {"caracteristicas_selecionadas": ["Id Inválido!"]},
        {"nome": "Maria"},
        {"historico_intervencoes": [{"estrategia": "x", "id_caracteristica": ID_A, "eficacia": "ótima"}]},
    ],
)
def test_arquivo_fora_do_padrao_e_recusado(mudanca):
    with pytest.raises(PerfilInvalidoError):
        importar(texto({**PERFIL, **mudanca}))


def test_perfil_com_dado_clinico_e_bloqueado_sem_ecoar_o_trecho():
    sujo = {**PERFIL, "anotacoes_pedagogicas": ["Aluno com laudo de TDAH CID F90 em uso de metilfenidato 10 mg"]}
    with pytest.raises(PerfilInvalidoError) as e:
        importar(texto(sujo))
    assert e.value.codigo == "CLINICAL_DATA_BLOCKED"
    resposta = json.dumps(e.value.to_dict(incluir_trecho=False), ensure_ascii=False)
    for trecho in ("metilfenidato", "F90", "10 mg"):
        assert trecho not in resposta


@pytest.mark.parametrize("payload", [None, [], "texto", {}, {"arquivo": 123}, {"arquivo": "{}", "extra": 1}])
def test_requisicao_mal_formada_e_recusada(payload):
    with pytest.raises(PerfilInvalidoError) as e:
        importar_perfil_service(payload)
    assert e.value.codigo == "INVALID_STRUCTURE"


def test_arquivo_acima_de_1mb_e_recusado_antes_de_ler():
    with pytest.raises(PerfilInvalidoError) as e:
        importar("x" * (MAX_BYTES_ARQUIVO + 1))
    assert e.value.codigo == "FILE_TOO_LARGE"


# ------------------------------------------------------------------ HTTP
@pytest.fixture
def cliente():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from iris.main import create_app

    return TestClient(create_app())


def test_rota_devolve_o_perfil_e_proibe_cache(cliente):
    r = cliente.post("/api/v1/perfil/importar", json={"arquivo": texto(COM_HISTORICO)})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["perfil"]["codigo_anonimo"] == "aluno-8f7a2c1b"
    assert r.json()["resumo_eficacia"][ID_A]["alta"] == 1


def test_rota_arquivo_corrompido_responde_422_amigavel_e_a_aplicacao_segue_de_pe(cliente):
    r = cliente.post("/api/v1/perfil/importar", json={"arquivo": "{quebrado"})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "INVALID_JSON" and "JSON" in d["detail"]
    assert cliente.post("/api/v1/perfil/importar", json={"arquivo": texto(PERFIL)}).status_code == 200


def test_rota_dado_clinico_nao_volta_na_resposta_de_erro(cliente):
    sujo = {**PERFIL, "anotacoes_pedagogicas": ["laudo de TDAH, CID F90, metilfenidato 10 mg"]}
    r = cliente.post("/api/v1/perfil/importar", json={"arquivo": texto(sujo)})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CLINICAL_DATA_BLOCKED"
    for trecho in ("metilfenidato", "F90"):
        assert trecho not in r.text


def test_rota_arquivo_grande_demais_responde_413(cliente):
    r = cliente.post("/api/v1/perfil/importar", json={"arquivo": "x" * (MAX_BYTES_ARQUIVO + 1)})
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_rota_nao_guarda_nada(cliente, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cliente.post("/api/v1/perfil/importar", json={"arquivo": texto(COM_HISTORICO)})
    assert list(tmp_path.iterdir()) == []


def test_modulo_da_rota_nao_escreve_em_disco():
    import inspect

    fonte = inspect.getsource(rota_perfil.importar_perfil_service)
    for proibido in ("open(", "write_text", "write_bytes", "tempfile", "sqlite", "pickle"):
        assert proibido not in fonte


# ------------------------------------------------------------------ revisão do #138
def _erro(conteudo: str) -> PerfilInvalidoError:
    with pytest.raises(PerfilInvalidoError) as e:
        importar(conteudo)
    return e.value


@pytest.mark.parametrize(
    "campo, valor, trecho",
    [
        ("codigo_anonimo", "aluno-xyz", "código anônimo"),
        ("versao_schema", "2.0", "versão 1.0"),
        ("criado_em", "ontem", "ISO 8601"),
        ("caracteristicas_selecionadas", ["ID Inválido!"], "formato inválido"),
    ],
)
def test_erros_de_estrutura_saem_em_portugues_sem_mensagem_do_pydantic(campo, valor, trecho):
    err = _erro(texto({**PERFIL, campo: valor}))
    assert err.codigo == "INVALID_STRUCTURE"
    msg = str(err)
    assert trecho in msg
    for ingles in ("String should", "Input should", "Field required", "Value error", "valid"):
        assert ingles not in msg


def test_eficacia_invalida_na_intervencao_diz_os_valores_permitidos():
    item = {**COM_HISTORICO["historico_intervencoes"][0], "eficacia": "ótima"}
    msg = str(_erro(texto({**COM_HISTORICO, "historico_intervencoes": [item]})))
    assert "eficácia" in msg and "alta" in msg and "Input should" not in msg


def test_campo_obrigatorio_ausente_em_portugues():
    sem = {k: v for k, v in PERFIL.items() if k != "codigo_anonimo"}
    assert "Falta o campo obrigatório" in str(_erro(texto(sem)))


def test_perfil_sem_caracteristica_tem_mensagem_propria():
    err = _erro(texto({**PERFIL, "caracteristicas_selecionadas": []}))
    assert err.codigo == "EMPTY_PROFILE"
    assert "nenhuma característica" in str(err)


@pytest.mark.parametrize(
    "conteudo",
    [
        "[" * 200000 + "]" * 200000,
        '{"a": ' * 50000 + "1" + "}" * 50000,
        '{"codigo_anonimo": ' + "9" * 20000 + "}",
        '{"codigo_anonimo": "\\ud800"}',
    ],
)
def test_arquivo_hostil_vira_invalid_json_e_nao_derruba_o_servico(conteudo):
    assert _erro(conteudo).codigo in {"INVALID_JSON", "INVALID_STRUCTURE"}


def test_surrogate_isolado_no_texto_nao_levanta_unicode_error():
    err = _erro("\ud800")
    assert err.codigo == "INVALID_JSON"


def test_rota_nao_responde_500_para_arquivos_hostis(cliente):
    corpos = [
        json.dumps({"arquivo": "[" * 200000}),
        json.dumps({"arquivo": '{"a": ' + "9" * 20000 + "}"}),
        '{"arquivo": "\\ud800"}',  # surrogate isolado, escapado como o navegador pode enviar
    ]
    for corpo in corpos:
        r = cliente.post("/api/v1/perfil/importar", content=corpo, headers={"Content-Type": "application/json"})
        assert r.status_code == 422, corpo[:30]
        assert r.json()["detail"]["code"] == "INVALID_JSON"
