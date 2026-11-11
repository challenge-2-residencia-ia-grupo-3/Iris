import json

import pytest
from pydantic import ValidationError

from iris.schemas.profile import (
    BarreiraObservada,
    ConteudoClinicoError,
    PerfilInvalidoError,
    PerfilPedagogico,
    detectar_conteudo_clinico,
    validar_perfil,
    varrer,
)

BASE = {
    "codigo_anonimo": "ALU-0042",
    "barreiras_observadas": [
        {"id_caracteristica": "atencao_sustentada_textos_longos",
         "observacao": "Perde o fio da meada em textos longos; rende melhor com enunciados divididos em etapas."}],
    "historico_estrategias": [
        {"estrategia": "Dividir o comando em passos numerados", "resultado": "eficaz"},
        {"estrategia": "Prova com tempo corrido", "resultado": "ineficaz"}],
    "anotacoes_pedagogicas": ["Trabalhou 20 minutos com foco quando a sala estava mais silenciosa."],
}


def com(**kw):
    return {**BASE, **kw}


def test_perfil_valido_passa():
    p = validar_perfil(BASE)
    assert isinstance(p, PerfilPedagogico) and p.codigo_anonimo == "ALU-0042"


def test_reimportacao_de_json_em_texto():
    assert validar_perfil(json.dumps(BASE)).versao_schema == "1.0"


# ---------- o que DEVE ser bloqueado ----------
@pytest.mark.parametrize("texto,cat", [
    ("CID F90.0", "cid"), ("CID-10: F84", "cid"), ("cid 11 6A02", "cid"), ("F90", "cid"), ("F84.5", "cid"),
    ("6A05", "cid"), ("Classificação Internacional de Doenças", "cid"),
    ("Laudo neuropsicológico anexo", "laudo"), ("segue o laudo do aluno", "laudo"), ("atestado médico", "laudo"),
    ("relatório clínico", "laudo"), ("receita médica", "laudo"), ("prontuário", "laudo"),
    ("diagnosticado com TDAH", "diagnostico"), ("tem TEA", "diagnostico"), ("aluno autista", "diagnostico"),
    ("dislexia", "diagnostico"), ("Transtorno do Espectro Autista", "diagnostico"),
    ("síndrome de Down", "diagnostico"), ("diagnóstico formal", "diagnostico"),
    ("toma Ritalina", "medicacao"), ("metilfenidato", "medicacao"), ("usa medicação", "medicacao"),
    ("10 mg pela manhã", "medicacao"), ("acompanhado por psiquiatra", "medicacao"), ("toma remédio", "medicacao"),
])
def test_bloqueia(texto, cat):
    assert cat in {v.categoria for v in detectar_conteudo_clinico(texto)}, texto


def test_rejeita_clinico_em_observacao_com_mensagem_orientadora():
    d = com(barreiras_observadas=[{"id_caracteristica": "atencao_sustentada_textos_longos",
                                   "observacao": "Aluno com TDAH, CID F90.0"}])
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil(d)
    err = e.value
    assert err.codigo == "CLINICAL_DATA_BLOCKED"
    assert "barreiras_observadas[0].observacao" in str(err) and "Descreva" in str(err)


def test_rejeita_clinico_em_anotacao_e_em_estrategia():
    for d in (com(anotacoes_pedagogicas=["Faz uso de metilfenidato"]),
              com(historico_estrategias=[{"estrategia": "Seguir o laudo médico", "resultado": "eficaz"}])):
        with pytest.raises(PerfilInvalidoError) as e:
            validar_perfil(d)
        assert e.value.codigo == "CLINICAL_DATA_BLOCKED"


@pytest.mark.parametrize("chave", ["cid", "CID", "laudo", "diagnostico", "medicacao", "diagnostico_formal", "receita_medica"])
def test_rejeita_atributo_clinico_pelo_nome(chave):
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil(com(**{chave: "qualquer coisa"}))
    assert e.value.codigo == "CLINICAL_DATA_BLOCKED"


def test_atributo_nao_declarado_e_rejeitado_mesmo_sem_ser_clinico():
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil(com(apelido="Juninho"))
    assert e.value.codigo == "INVALID_STRUCTURE" and "apelido" in str(e.value)


def test_atributo_extra_aninhado_e_rejeitado():
    d = com(barreiras_observadas=[{"id_caracteristica": "atencao_sustentada_textos_longos", "nome_aluno": "x"}])
    with pytest.raises(PerfilInvalidoError):
        validar_perfil(d)


def test_pydantic_direto_tambem_bloqueia():
    with pytest.raises(ValidationError):
        PerfilPedagogico.model_validate(com(anotacoes_pedagogicas=["laudo"]))
    with pytest.raises(ValidationError):
        BarreiraObservada.model_validate({"id_caracteristica": "atencao_sustentada_textos_longos", "observacao": "CID F90"})


def test_json_invalido_e_estrutura_invalida():
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil("{nao é json")
    assert e.value.codigo == "INVALID_JSON"
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil(json.dumps([1, 2]))
    assert e.value.codigo == "INVALID_STRUCTURE"


def test_campos_obrigatorios_e_formato():
    with pytest.raises(PerfilInvalidoError):
        validar_perfil({"barreiras_observadas": []})  # falta codigo_anonimo
    with pytest.raises(PerfilInvalidoError):
        validar_perfil(com(codigo_anonimo="joao.silva@escola.com"))
    with pytest.raises(PerfilInvalidoError):
        validar_perfil(com(historico_estrategias=[{"estrategia": "Dividir em passos", "resultado": "talvez"}]))


# ---------- o que NÃO pode ser bloqueado (falsos positivos) ----------
@pytest.mark.parametrize("texto", [
    "Perde o fio da meada em textos longos; funciona melhor com enunciados divididos em etapas.",
    "Avaliação diagnóstica da turma no início do ano.",
    "Diagnóstico pedagógico: dificuldade em sequenciar passos.",
    "Resolveu a questão Q10 com apoio.", "Imprimir em papel A4 ampliado.", "Ambiente estimulante e silencioso.",
    "Fica ansioso em provas longas.", "Trabalhou 20 minutos com foco.", "Precisa de lápis com grip.",
    "Sentar perto da professora ajuda.", "Atividade sobre receita de bolo.", "Cid sentou na primeira fileira.",
    "Autonomia na leitura de enunciados curtos.", "Usa tabela de 10 linhas.", "Prova de 40 minutos.",
])
def test_nao_bloqueia_texto_pedagogico(texto):
    assert detectar_conteudo_clinico(texto) == [], texto


# ---------- privacidade ----------
def test_str_da_excecao_nao_repete_o_trecho_digitado():
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil(com(anotacoes_pedagogicas=["toma Ritalina de manhã"]))
    assert "Ritalina" not in str(e.value) and "ritalina" not in str(e.value).lower()
    assert any("ritalina" in v["trecho"].lower() for v in e.value.to_dict()["violacoes"])
    assert all("trecho" not in v for v in e.value.to_dict(incluir_trecho=False)["violacoes"])


def test_varrer_percorre_chaves_e_valores_aninhados():
    v = varrer({"a": [{"b": "tudo certo"}, {"c": "laudo"}]})
    assert [x.campo for x in v] == ["a[1].c"]


def test_varrer_nao_quebra_com_tipos_nao_textuais():
    assert varrer({"n": 3, "ok": True, "x": None, "l": [1, 2.5]}) == []


def test_conteudo_clinico_error_e_valueerror():
    assert issubclass(ConteudoClinicoError, ValueError)