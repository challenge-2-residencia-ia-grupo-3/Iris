"""Exportação do Perfil Pedagógico Portátil em .json e .pdf (História 3.2.1, RF-15, RNF-01)."""
from __future__ import annotations

import ast
import builtins
import importlib.util
import json
import socket
import unicodedata
from pathlib import Path

import pytest

import iris.api.routes.perfil as rota_perfil
import iris.exportacao.perfil as exportacao
from iris.exportacao.perfil import FormatoInvalidoError, exportar_perfil
from iris.schemas.portable_profile import PerfilInvalidoError, criar_perfil, validar_perfil

ID = "sobrecarga_memoria_trabalho_comandos_multiplos"

# Forma exata do arquivo que o frontend baixa (frontend/src/services/portableProfile.ts).
JSON_DO_FRONT = {
    "versao_schema": "1.0",
    "codigo_anonimo": "aluno-8f7a2c1b",
    "criado_em": "2026-11-13T12:00:00.000Z",
    "caracteristicas_selecionadas": [ID],
    "barreiras_observadas": [],
    "historico_estrategias": [],
    "anotacoes_pedagogicas": [],
}


def _pdf_texto(conteudo: bytes) -> str:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    doc = pymupdf.open(stream=conteudo, filetype="pdf")
    bruto = "\n".join(p.get_text() for p in doc)
    return unicodedata.normalize("NFKC", bruto)  # o PDF usa ligaduras (ﬁ, ﬂ); normaliza para comparar


def _n_paginas(conteudo: bytes) -> int:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    return pymupdf.open(stream=conteudo, filetype="pdf").page_count


# ------------------------------------------------------------------ JSON validado pelo schema oficial
def test_json_exportado_valida_contra_o_schema_oficial():
    arq = exportar_perfil(JSON_DO_FRONT, "json")
    assert arq.media_type == "application/json" and arq.nome == "perfil-aluno-8f7a2c1b.json"
    perfil = validar_perfil(arq.conteudo)  # reimporta os bytes baixados
    assert perfil.codigo_anonimo == "aluno-8f7a2c1b"
    assert perfil.caracteristicas_selecionadas == [ID]


def test_json_do_perfil_criado_pelo_servico_tambem_passa():
    dados = criar_perfil([ID]).para_json()
    assert validar_perfil(exportar_perfil(dados, "json").conteudo).caracteristicas_selecionadas == [ID]


def test_json_preserva_acentos_e_e_utf8():
    dados = {**JSON_DO_FRONT, "anotacoes_pedagogicas": ["Responde bem a explicações visuais."]}
    bruto = exportar_perfil(dados, "json").conteudo
    assert "explicações" in bruto.decode("utf-8")


# ------------------------------------------------------------------ perfil inválido nunca vira arquivo
@pytest.mark.parametrize("formato", ["json", "pdf"])
@pytest.mark.parametrize("dados", [
    {**JSON_DO_FRONT, "anotacoes_pedagogicas": ["Tem laudo de TDAH, CID F90."]},
    {**JSON_DO_FRONT, "laudo_tdah_f90": "x"},
    {**JSON_DO_FRONT, "codigo_anonimo": "joao-silva"},
    {**JSON_DO_FRONT, "nome": "Joao"},
    {**JSON_DO_FRONT, "criado_em": "2026-11-13T12:00:00"},  # sem fuso
    {**JSON_DO_FRONT, "caracteristicas_selecionadas": [ID, ID]},
])
def test_perfil_invalido_nao_gera_arquivo(dados, formato):
    with pytest.raises(PerfilInvalidoError):
        exportar_perfil(dados, formato)


@pytest.mark.parametrize("bruto", ["isso nao e json", "[1, 2]", "42"])
def test_corpo_que_nao_e_objeto_json_e_recusado(bruto):
    with pytest.raises(PerfilInvalidoError):
        exportar_perfil(bruto, "pdf")


def test_formato_desconhecido_e_recusado():
    for ruim in ("docx", "", "PDF", None):
        with pytest.raises(FormatoInvalidoError):
            exportar_perfil(JSON_DO_FRONT, ruim)  # type: ignore[arg-type]


# ------------------------------------------------------------------ PDF
def test_pdf_tem_cabecalho_valido_e_o_conteudo_do_perfil():
    arq = exportar_perfil(JSON_DO_FRONT, "pdf")
    assert arq.media_type == "application/pdf" and arq.nome == "perfil-aluno-8f7a2c1b.pdf"
    assert arq.conteudo.startswith(b"%PDF")
    texto = _pdf_texto(arq.conteudo)
    assert "aluno-8f7a2c1b" in texto
    assert "Perfil" in texto and "Portátil" in texto
    assert "13/11/2026" in texto
    assert "Múltiplos comandos na mesma questão" in texto  # nome legível vindo do catálogo oficial


def test_pdf_usa_o_proprio_id_quando_a_caracteristica_nao_esta_no_catalogo():
    dados = {**JSON_DO_FRONT, "caracteristicas_selecionadas": ["caracteristica_fora_do_catalogo"]}
    assert "caracteristica_fora_do_catalogo" in _pdf_texto(exportar_perfil(dados, "pdf").conteudo)


def test_pdf_inclui_secoes_opcionais_quando_existem():
    dados = {
        **JSON_DO_FRONT,
        "barreiras_observadas": [{"id_caracteristica": ID, "observacao": "Perde o fio em provas longas."}],
        "historico_estrategias": [{"estrategia": "Dividir o enunciado em passos", "resultado": "eficaz"}],
        "anotacoes_pedagogicas": ["Prefere esquemas visuais."],
    }
    texto = _pdf_texto(exportar_perfil(dados, "pdf").conteudo)
    for esperado in ("Barreiras observadas", "Perde o fio", "Estratégias já utilizadas", "Dividir o enunciado", "Prefere esquemas visuais."):
        assert esperado in texto


def test_pdf_escapa_html_do_conteudo():
    dados = {**JSON_DO_FRONT, "anotacoes_pedagogicas": ["Usa <b>negrito</b> & <i>itálico</i> nas notas."]}
    texto = _pdf_texto(exportar_perfil(dados, "pdf").conteudo)
    assert "<b>negrito</b>" in texto and "<i>itálico</i>" in texto


def test_pdf_longo_quebra_em_varias_paginas():
    notas = [f"Anotação pedagógica número {i}: " + "texto de apoio " * 12 for i in range(60)]
    dados = {**JSON_DO_FRONT, "anotacoes_pedagogicas": notas}
    arq = exportar_perfil(dados, "pdf")
    assert _n_paginas(arq.conteudo) >= 2
    assert "número 59" in _pdf_texto(arq.conteudo)


def test_pdf_nao_carrega_dado_pessoal():
    texto = _pdf_texto(exportar_perfil(JSON_DO_FRONT, "pdf").conteudo).lower()
    assert "nome de pessoa não é detectado automaticamente" in " ".join(texto.split())  # o rodapé quebra de linha
    for campo in ("cpf", "e-mail", "telefone"):
        assert campo not in texto


# ------------------------------------------------------------------ sem estado e sem persistência no servidor
_MODULOS = (Path(exportacao.__file__), Path(rota_perfil.__file__))
_IMPORTS_PROIBIDOS = {"sqlite3", "sqlalchemy", "pickle", "shelve", "dbm", "tempfile", "socket", "requests", "httpx", "urllib", "redis", "shutil"}
_CHAMADAS_PROIBIDAS = {"open", "write_text", "write_bytes", "dump", "mkdtemp", "mkstemp", "NamedTemporaryFile", "save", "tobytes_to_file"}


@pytest.mark.parametrize("caminho", _MODULOS, ids=lambda p: p.name)
def test_codigo_nao_importa_nem_chama_nada_de_persistencia(caminho):
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    importados = set()
    chamadas = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
        elif isinstance(no, ast.Call):
            f = no.func
            chamadas.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    assert not (importados & _IMPORTS_PROIBIDOS), importados & _IMPORTS_PROIBIDOS
    assert not (chamadas & _CHAMADAS_PROIBIDAS), chamadas & _CHAMADAS_PROIBIDAS


@pytest.mark.parametrize("formato", ["json", "pdf"])
def test_exportar_nao_grava_arquivo_nem_abre_rede_e_nao_guarda_estado(monkeypatch, formato):
    abertura_original = builtins.open

    def open_somente_leitura(arq, modo="r", *a, **k):
        if any(c in str(modo) for c in "wax+"):
            raise AssertionError(f"escrita em disco durante a exportação: {arq!r} ({modo})")
        return abertura_original(arq, modo, *a, **k)

    def sem_rede(*a, **k):
        raise AssertionError("conexão de rede durante a exportação")

    monkeypatch.setattr(builtins, "open", open_somente_leitura)
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    antes = {k: id(v) for k, v in vars(exportacao).items() if not k.startswith("__")}
    arq = exportar_perfil(JSON_DO_FRONT, formato)
    depois = {k: id(v) for k, v in vars(exportacao).items() if not k.startswith("__")}
    assert arq.conteudo
    assert antes == depois  # nenhuma variável de módulo (cache/sessão) foi criada ou trocada


def test_duas_exportacoes_seguidas_sao_independentes():
    a = exportar_perfil({**JSON_DO_FRONT, "codigo_anonimo": "aluno-11111111"}, "pdf")
    b = exportar_perfil({**JSON_DO_FRONT, "codigo_anonimo": "aluno-22222222"}, "pdf")
    assert "aluno-22222222" not in _pdf_texto(a.conteudo)
    assert "aluno-11111111" not in _pdf_texto(b.conteudo)


# ------------------------------------------------------------------ rota HTTP
HTTPX = importlib.util.find_spec("httpx") is not None
pytestmark_http = pytest.mark.skipif(
    not HTTPX or rota_perfil.router is None, reason="requer FastAPI e httpx"
)


@pytest.fixture()
def cliente():
    from fastapi.testclient import TestClient
    from iris.main import create_app

    return TestClient(create_app())


@pytestmark_http
def test_rota_json_devolve_download_validavel(cliente):
    r = cliente.post("/api/v1/perfil/exportar?formato=json", json=JSON_DO_FRONT)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert 'attachment; filename="perfil-aluno-8f7a2c1b.json"' == r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    assert validar_perfil(r.content).codigo_anonimo == "aluno-8f7a2c1b"


@pytestmark_http
def test_rota_pdf_devolve_pdf(cliente):
    r = cliente.post("/api/v1/perfil/exportar?formato=pdf", json=JSON_DO_FRONT)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store"
    assert "aluno-8f7a2c1b" in _pdf_texto(r.content)


@pytestmark_http
def test_rota_usa_json_por_padrao(cliente):
    assert cliente.post("/api/v1/perfil/exportar", json=JSON_DO_FRONT).headers["content-type"].startswith("application/json")


@pytestmark_http
def test_rota_recusa_conteudo_clinico_sem_repetir_o_que_foi_digitado(cliente):
    dados = {**JSON_DO_FRONT, "anotacoes_pedagogicas": ["Aluno com laudo de TDAH, toma ritalina."]}
    for formato in ("json", "pdf"):
        r = cliente.post(f"/api/v1/perfil/exportar?formato={formato}", json=dados)
        assert r.status_code == 422
        corpo = r.text.lower()
        assert "ritalina" not in corpo and "tdah" not in corpo
        assert r.headers["content-type"].startswith("application/json")  # erro, nunca um arquivo


@pytestmark_http
def test_rota_recusa_formato_e_corpo_invalidos(cliente):
    assert cliente.post("/api/v1/perfil/exportar?formato=docx", json=JSON_DO_FRONT).status_code == 422
    assert cliente.post("/api/v1/perfil/exportar", json=[1, 2]).status_code == 422
    assert cliente.post("/api/v1/perfil/exportar", json={**JSON_DO_FRONT, "codigo_anonimo": "joao"}).status_code == 422


@pytestmark_http
def test_rota_so_aceita_post(cliente):
    assert cliente.get("/api/v1/perfil/exportar").status_code == 405
