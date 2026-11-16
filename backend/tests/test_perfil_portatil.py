import ast
import builtins
import inspect
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest

from iris.schemas import portable_profile as pp
from iris.schemas.portable_profile import (
    PerfilInvalidoError,
    PerfilPedagogico,
    criar_perfil,
    gerar_codigo_anonimo,
    validar_perfil,
)

IDS = ["atencao_sustentada_textos_longos", "sobrecarga_memoria_trabalho_comandos_multiplos"]


# ---------- gerador de identificador anônimo ----------
def test_codigo_tem_o_formato_do_exemplo():
    assert re.fullmatch(r"aluno-[0-9a-f]{8}", gerar_codigo_anonimo())


def test_codigos_sao_aleatorios_e_unicos():
    assert gerar_codigo_anonimo() != gerar_codigo_anonimo()
    assert len({gerar_codigo_anonimo(16) for _ in range(2000)}) == 2000


def test_n_hex_fora_do_intervalo():
    for n in (4, 33):
        with pytest.raises(ValueError):
            gerar_codigo_anonimo(n)


def test_gerador_nao_recebe_dado_do_estudante():
    assert list(inspect.signature(gerar_codigo_anonimo).parameters) == ["n_hex"]
    assert list(inspect.signature(criar_perfil).parameters) == ["caracteristicas_selecionadas", "ids_validos"]


# ---------- criação em memória ----------
def test_criar_perfil_tem_codigo_data_e_caracteristicas():
    antes = datetime.now(timezone.utc)
    p = criar_perfil(IDS)
    assert isinstance(p, PerfilPedagogico)
    assert re.fullmatch(r"aluno-[0-9a-f]{8}", p.codigo_anonimo)
    assert antes <= p.criado_em <= datetime.now(timezone.utc) and p.criado_em.tzinfo is not None
    assert p.caracteristicas_selecionadas == IDS


def test_dois_perfis_tem_codigos_diferentes():
    assert criar_perfil(IDS).codigo_anonimo != criar_perfil(IDS).codigo_anonimo


def test_ids_repetidos_sao_unificados_e_ids_do_catalogo_sao_checados():
    assert criar_perfil([IDS[0], IDS[0]]).caracteristicas_selecionadas == [IDS[0]]
    assert criar_perfil(IDS, ids_validos=set(IDS))
    with pytest.raises(PerfilInvalidoError, match="não encontrada"):
        criar_perfil(["nao_existe_no_catalogo"], ids_validos=set(IDS))


def test_formato_invalido_de_id_e_rejeitado():
    with pytest.raises(PerfilInvalidoError):
        criar_perfil(["Atenção Sustentada!"])


def test_ida_e_volta_em_json():
    p = criar_perfil(IDS)
    txt = json.dumps(p.para_json())
    assert validar_perfil(txt) == p
    assert p.para_json()["criado_em"].endswith(("Z", "+00:00"))


# ---------- anonimato: o código não pode carregar nome ----------
@pytest.mark.parametrize("codigo", ["joao-silva", "aluno-joao", "ALU-0042", "aluno-8F7A2C1B", "aluno-8f7a", "12345678901"])
def test_codigo_que_nao_e_o_aleatorio_oficial_e_rejeitado(codigo):
    with pytest.raises(PerfilInvalidoError):
        validar_perfil({"codigo_anonimo": codigo})


@pytest.mark.parametrize("campo", ["nome", "nome_aluno", "cpf", "escola", "email"])
def test_dado_pessoal_nao_tem_campo_no_perfil(campo):
    with pytest.raises(PerfilInvalidoError):
        validar_perfil({"codigo_anonimo": "aluno-8f7a2c1b", campo: "qualquer"})


def test_data_sem_fuso_e_rejeitada():
    with pytest.raises(PerfilInvalidoError):
        validar_perfil({"codigo_anonimo": "aluno-8f7a2c1b", "criado_em": "2026-11-11T10:00:00"})


def test_bloqueio_clinico_continua_valendo_em_caracteristicas():
    with pytest.raises(PerfilInvalidoError) as e:
        validar_perfil({"codigo_anonimo": "aluno-8f7a2c1b", "caracteristicas_selecionadas": ["tdah_formal"]})
    assert e.value.codigo == "CLINICAL_DATA_BLOCKED"


# ---------- ausência de persistência (inspeção de código + execução) ----------
BANCOS = {"sqlite3", "sqlalchemy", "psycopg", "psycopg2", "pymongo", "redis", "shelve", "dbm", "pickle",
          "mysql", "peewee", "sqlmodel", "tinydb", "requests", "httpx", "urllib", "socket", "boto3", "tempfile"}
ESCRITA = {"open", "write_text", "write_bytes", "write", "dump", "to_sql", "commit", "execute", "mkdir", "touch"}


def _arvore():
    return ast.parse(Path(inspect.getsourcefile(pp)).read_text(encoding="utf-8"))


def test_codigo_nao_importa_banco_arquivo_ou_rede():
    importados = set()
    for n in ast.walk(_arvore()):
        if isinstance(n, ast.Import):
            importados |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            importados.add(n.module.split(".")[0])
    assert not importados & BANCOS, importados & BANCOS


def test_codigo_nao_chama_funcao_de_escrita():
    chamadas = set()
    for n in ast.walk(_arvore()):
        if isinstance(n, ast.Call):
            f = n.func
            chamadas.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    assert not chamadas & ESCRITA, chamadas & ESCRITA


def test_criar_perfil_nao_escreve_arquivo_nem_abre_rede(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    abrir = builtins.open

    def open_so_leitura(arquivo, modo="r", *a, **k):
        assert not set(str(modo)) & set("wax+"), f"tentou gravar {arquivo!r}"
        return abrir(arquivo, modo, *a, **k)

    def sem_rede(*a, **k):
        raise AssertionError("tentou abrir conexão de rede")

    monkeypatch.setattr(builtins, "open", open_so_leitura)
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    p = criar_perfil(IDS)
    validar_perfil(json.dumps(p.para_json()))
    assert list(tmp_path.iterdir()) == []
