"""Exportação do material adaptado em PDF econômico e DOCX editável (História 2.2.3, RF-14)."""
from __future__ import annotations

import ast
import builtins
import importlib.util
import io
import re
import socket
import unicodedata
from pathlib import Path

import pytest

import iris.api.routes.exportacao_material as rota_material
import iris.exportacao.material as modulo
from iris.exportacao.material import (
    ExportacaoMaterialError,
    LINHA_ALUNO,
    TITULO_PADRAO,
    exportar_material,
    verificar_material,
)

TEXTO = (
    "1) Leia o texto sobre o ciclo da água e responda.\n"
    "O vapor sobe, esfria e vira nuvem.\n\n"
    "2) Explique a evaporação com suas palavras.\n\n"
    "3) Desenhe as etapas do ciclo."
)
MATERIAL = {"titulo": "Ciências - Ciclo da água", "texto": TEXTO}


def _pymupdf():
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    return pymupdf


def _pdf(conteudo: bytes):
    return _pymupdf().open(stream=conteudo, filetype="pdf")


def _texto_pdf(conteudo: bytes) -> str:
    bruto = "\n".join(p.get_text() for p in _pdf(conteudo))
    return unicodedata.normalize("NFKC", bruto)  # ligaduras (ﬁ, ﬂ) viram letras


def _docx(conteudo: bytes):
    from docx import Document

    return Document(io.BytesIO(conteudo))


def _pixels(pagina, dpi: int = 50) -> bytes:
    return pagina.get_pixmap(dpi=dpi, colorspace=_pymupdf().csRGB, alpha=False).samples


# ------------------------------------------------------------------ PDF: A4, cinza, sem serifa
def test_pdf_e_um_pdf_a4_com_o_conteudo():
    arq = exportar_material(MATERIAL, "pdf")
    assert arq.media_type == "application/pdf" and arq.nome == "atividade-adaptada.pdf"
    assert arq.conteudo.startswith(b"%PDF")
    pag = _pdf(arq.conteudo)[0]
    assert (round(pag.rect.width), round(pag.rect.height)) == (595, 842)  # A4
    texto = _texto_pdf(arq.conteudo)
    for esperado in ("Ciências - Ciclo da água", "Leia o texto sobre o ciclo da água", "Desenhe as etapas do ciclo."):
        assert esperado in texto


def test_pdf_usa_so_fonte_sem_serifa():
    fontes = {f[3] for pag in _pdf(exportar_material(MATERIAL, "pdf").conteudo) for f in pag.get_fonts()}
    assert fontes, "o PDF precisa ter fonte embutida"
    for nome in fontes:
        assert re.search(r"sans|arial|helvet|verdana|calibri", nome, re.I), nome
        assert not re.search(r"times|serif(?!.*sans)|georgia|garamond|palatino|courier|mono", nome, re.I), nome


def test_pdf_e_so_em_tons_de_cinza():
    px = _pixels(_pdf(exportar_material(MATERIAL, "pdf").conteudo)[0])
    assert px[0::3] == px[1::3] == px[2::3], "há pixel colorido: gasta tinta colorida na impressão"


def test_pdf_nao_tem_blocos_densos_de_tinta_escura():
    notas = "\n\n".join(f"{i}) " + "Responda com atenção ao enunciado completo. " * 6 for i in range(1, 16))
    pag = _pdf(exportar_material({"texto": notas}, "pdf").conteudo)[0]
    px = _pixels(pag)[0::3]
    escuros = sum(1 for v in px if v < 100) / len(px)
    assert escuros < 0.12, f"{escuros:.1%} da página é tinta escura"
    # nenhum bloco 40x40 (a 50 dpi) totalmente escuro: não há tarja, fundo nem caixa preenchida
    larg = pag.get_pixmap(dpi=50, alpha=False).width
    linhas = [px[i : i + larg] for i in range(0, len(px), larg)]
    for y in range(0, len(linhas) - 40, 20):
        for x in range(0, larg - 40, 20):
            assert max(max(l[x : x + 40]) for l in linhas[y : y + 40]) > 150


def test_pdf_longo_quebra_em_varias_paginas_sem_perder_texto():
    paragrafos = [f"Questão {i}: " + "texto de apoio para o aluno " * 14 for i in range(80)]
    arq = exportar_material({"texto": "\n\n".join(paragrafos)}, "pdf")
    assert len(_pdf(arq.conteudo)) >= 2
    assert "Questão 79:" in _texto_pdf(arq.conteudo)


def test_pdf_preserva_quebras_de_linha_e_escapa_html():
    texto = "a) primeira opção\nb) segunda opção\n\nUsa <b>negrito</b> & <i>itálico</i> no enunciado."
    txt = _texto_pdf(exportar_material({"texto": texto}, "pdf").conteudo)
    assert "a) primeira opção" in txt and "b) segunda opção" in txt
    assert "<b>negrito</b>" in txt and "<i>itálico</i>" in txt


# ------------------------------------------------------------------ DOCX editável
def test_docx_abre_editavel_em_a4_com_arial_e_espacamento():
    arq = exportar_material(MATERIAL, "docx")
    assert arq.media_type.endswith("wordprocessingml.document") and arq.nome == "atividade-adaptada.docx"
    doc = _docx(arq.conteudo)  # abre normalmente: é editável
    sec = doc.sections[0]
    assert (round(sec.page_width.mm), round(sec.page_height.mm)) == (210, 297)
    normal = doc.styles["Normal"]
    assert normal.font.name == "Arial" and normal.font.size.pt == 12
    assert normal.paragraph_format.line_spacing_rule is not None
    assert str(normal.paragraph_format.line_spacing_rule).startswith("ONE_POINT_FIVE")
    assert "Leia o texto sobre o ciclo da água" in "\n".join(p.text for p in doc.paragraphs)


def test_docx_e_preto_sem_cor_nem_serifa():
    doc = _docx(exportar_material(MATERIAL, "docx").conteudo)
    for p in doc.paragraphs:
        for r in p.runs:
            if r.font.color is not None and r.font.color.rgb is not None:
                assert str(r.font.color.rgb) == "000000"
            assert r.font.name in (None, "Arial")


def test_docx_nao_deixa_metadado_de_autor():
    props = _docx(exportar_material(MATERIAL, "docx").conteudo).core_properties
    assert props.author == "" and props.last_modified_by == ""


# ------------------------------------------------------------------ cabeçalho sem rótulo clínico nem dado pessoal
@pytest.mark.parametrize("formato", ["pdf", "docx"])
def test_cabecalho_e_generico_com_campos_em_branco(formato):
    arq = exportar_material({"texto": TEXTO}, formato)
    if formato == "pdf":
        linhas = [l for l in _texto_pdf(arq.conteudo).splitlines() if l.strip()]
    else:
        linhas = [p.text for p in _docx(arq.conteudo).paragraphs if p.text.strip()]
    assert linhas[0] == TITULO_PADRAO
    assert "Nome:" in linhas[1] and "_____" in linhas[1]  # o aluno preenche; o servidor não escreve nome


@pytest.mark.parametrize("titulo", [
    "Atividade para aluno com TDAH", "Adaptada - laudo F90", "Prova (CID F84)", "Para quem toma ritalina",
    "Atividade de autismo", "Diagnóstico médico: TEA",
])
def test_titulo_com_rotulo_clinico_e_recusado(titulo):
    for formato in ("pdf", "docx"):
        with pytest.raises(ExportacaoMaterialError) as e:
            exportar_material({"titulo": titulo, "texto": TEXTO}, formato)
        assert e.value.code == "CLINICAL_LABEL_IN_HEADER" and e.value.field == "titulo"
    assert not any(t in str(e.value).lower() for t in ("tdah", "f90", "ritalina"))  # não ecoa o que foi digitado


@pytest.mark.parametrize("titulo", ["Aluno: João da Silva", "Escola: Municipal Paulo Freire", "Contato 123.456.789-09", "joao@escola.com"])
def test_titulo_com_dado_pessoal_e_recusado(titulo):
    with pytest.raises(ExportacaoMaterialError) as e:
        exportar_material({"titulo": titulo, "texto": TEXTO}, "pdf")
    assert e.value.code == "PII_IN_HEADER"


@pytest.mark.parametrize("titulo", [None, "", "   "])
def test_titulo_vazio_usa_o_padrao(titulo):
    assert TITULO_PADRAO in _texto_pdf(exportar_material({"titulo": titulo, "texto": TEXTO}, "pdf").conteudo)


def test_titulo_comum_de_escola_nao_e_bloqueado():
    for t in ("Matemática - Frações", "História: Brasil Colônia", "Geografia - Relevo e hidrografia", "Língua Portuguesa: interpretação"):
        exportar_material({"titulo": t, "texto": TEXTO}, "pdf")


# ------------------------------------------------------------------ o texto aprovado não é alterado; só há aviso
def test_corpo_nao_e_alterado_mesmo_com_dado_pessoal_ou_termo_clinico():
    texto = "Fale com a mãe pelo 123.456.789-09.\nO texto explica a síndrome de Down na Biologia."
    arq = exportar_material({"texto": texto}, "pdf")
    saida = _texto_pdf(arq.conteudo)
    assert "123.456.789-09" in saida and "síndrome de Down" in saida  # o que o professor aprovou sai como está


def test_verificar_avisa_sem_recusar():
    r = verificar_material({"titulo": "Biologia", "texto": "Contato: 123.456.789-09. A síndrome de Down é genética."})
    assert r["pode_exportar"] is True
    assert r["possiveis_dados_pessoais"] >= 1
    assert "diagnostico" in r["categorias_clinicas_no_texto"]


def test_verificar_sem_avisos_para_texto_limpo():
    r = verificar_material(MATERIAL)
    assert r["possiveis_dados_pessoais"] == 0 and r["categorias_clinicas_no_texto"] == []


# ------------------------------------------------------------------ entrada inválida
@pytest.mark.parametrize("dados,codigo", [
    ({"titulo": "x"}, "EMPTY_TEXT"),
    ({"texto": "   \n "}, "EMPTY_TEXT"),
    ({"texto": 42}, "EMPTY_TEXT"),
    ({"texto": TEXTO, "titulo": 7}, "INVALID_TITLE"),
    ({"texto": TEXTO, "titulo": "a" * 121}, "TITLE_TOO_LONG"),
    ({"texto": "a" * 60_001}, "TEXT_TOO_LONG"),
    ({"texto": TEXTO, "nome_aluno": "Joao"}, "EXTRA_FIELD"),
    ([1, 2], "INVALID_BODY"),
    ("texto solto", "INVALID_BODY"),
])
def test_entradas_invalidas(dados, codigo):
    with pytest.raises(ExportacaoMaterialError) as e:
        exportar_material(dados, "pdf")
    assert e.value.code == codigo


def test_campo_extra_nao_e_ecoado():
    with pytest.raises(ExportacaoMaterialError) as e:
        exportar_material({"texto": TEXTO, "laudo_tdah": "x"}, "pdf")
    assert "tdah" not in str(e.value).lower() and "laudo" not in str(e.value).lower()


@pytest.mark.parametrize("formato", ["odt", "", "PDF", None])
def test_formato_desconhecido(formato):
    with pytest.raises(ExportacaoMaterialError) as e:
        exportar_material(MATERIAL, formato)  # type: ignore[arg-type]
    assert e.value.code == "UNSUPPORTED_EXPORT_FORMAT"


# ------------------------------------------------------------------ sem estado e sem persistência
_MODULOS = (Path(modulo.__file__), Path(rota_material.__file__))
_IMPORTS_PROIBIDOS = {"sqlite3", "sqlalchemy", "pickle", "shelve", "dbm", "tempfile", "socket", "requests", "httpx", "urllib", "redis", "shutil"}
_CHAMADAS_PROIBIDAS = {"open", "write_text", "write_bytes", "dump", "mkdtemp", "mkstemp", "NamedTemporaryFile"}


@pytest.mark.parametrize("caminho", _MODULOS, ids=lambda p: p.name)
def test_codigo_nao_importa_nem_chama_nada_de_persistencia(caminho):
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    importados, chamadas = set(), set()
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


@pytest.mark.parametrize("formato", ["pdf", "docx"])
def test_exportar_nao_grava_arquivo_nem_abre_rede_e_nao_guarda_estado(monkeypatch, formato):
    abertura = builtins.open

    def so_leitura(arq, modo="r", *a, **k):
        if any(c in str(modo) for c in "wax+"):
            raise AssertionError(f"escrita em disco durante a exportação: {arq!r} ({modo})")
        return abertura(arq, modo, *a, **k)

    def sem_rede(*a, **k):
        raise AssertionError("conexão de rede durante a exportação")

    monkeypatch.setattr(builtins, "open", so_leitura)
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    antes = {k: id(v) for k, v in vars(modulo).items() if not k.startswith("__")}
    assert exportar_material(MATERIAL, formato).conteudo
    depois = {k: id(v) for k, v in vars(modulo).items() if not k.startswith("__")}
    assert antes == depois


def test_duas_exportacoes_seguidas_sao_independentes():
    a = exportar_material({"texto": "Primeira atividade secreta A"}, "pdf")
    b = exportar_material({"texto": "Segunda atividade B"}, "pdf")
    assert "secreta" not in _texto_pdf(b.conteudo) and "Segunda" not in _texto_pdf(a.conteudo)


# ------------------------------------------------------------------ rota HTTP
HTTPX = importlib.util.find_spec("httpx") is not None
requer_http = pytest.mark.skipif(not HTTPX or rota_material.router is None, reason="requer FastAPI e httpx")


@pytest.fixture()
def cliente():
    from fastapi.testclient import TestClient
    from iris.main import create_app

    return TestClient(create_app())


@requer_http
def test_rota_pdf_e_docx(cliente):
    r = cliente.post("/api/v1/adaptacao/exportar?formato=pdf", json=MATERIAL)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="atividade-adaptada.pdf"'
    assert r.headers["cache-control"] == "no-store"
    d = cliente.post("/api/v1/adaptacao/exportar?formato=docx", json=MATERIAL)
    assert d.status_code == 200 and d.headers["content-type"].endswith("wordprocessingml.document")
    assert d.headers["content-disposition"] == 'attachment; filename="atividade-adaptada.docx"'
    assert _docx(d.content).paragraphs


@requer_http
def test_rota_usa_pdf_por_padrao(cliente):
    assert cliente.post("/api/v1/adaptacao/exportar", json=MATERIAL).headers["content-type"] == "application/pdf"


@requer_http
def test_rota_recusa_titulo_clinico_sem_ecoar(cliente):
    r = cliente.post("/api/v1/adaptacao/exportar?formato=pdf", json={"titulo": "Atividade para aluno com TDAH", "texto": TEXTO})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "CLINICAL_LABEL_IN_HEADER"
    assert "tdah" not in r.text.lower() and r.headers["content-type"].startswith("application/json")


@requer_http
def test_rota_recusa_formato_e_corpo_invalidos(cliente):
    assert cliente.post("/api/v1/adaptacao/exportar?formato=odt", json=MATERIAL).status_code == 422
    assert cliente.post("/api/v1/adaptacao/exportar", json={"texto": ""}).status_code == 422
    assert cliente.post("/api/v1/adaptacao/exportar", json=[1]).status_code == 422


@requer_http
def test_rota_verificar_devolve_avisos(cliente):
    r = cliente.post("/api/v1/adaptacao/verificar-exportacao", json={"texto": "CPF 123.456.789-09 na lista"})
    assert r.status_code == 200 and r.json()["possiveis_dados_pessoais"] >= 1 and r.json()["pode_exportar"] is True
    assert cliente.post("/api/v1/adaptacao/verificar-exportacao", json={"titulo": "Prova de aluno com laudo", "texto": TEXTO}).status_code == 422


@requer_http
def test_rota_so_aceita_post(cliente):
    assert cliente.get("/api/v1/adaptacao/exportar").status_code == 405
