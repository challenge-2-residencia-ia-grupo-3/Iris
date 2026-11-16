"""Testes da revisão docente em memória e da trava de exportação (História 2.2.2, RF-13/RNF-09)."""
from __future__ import annotations

import ast
import builtins
import importlib.util
import socket
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

import iris.sessao.revisao as revisao
from iris.sessao.revisao import RepositorioSessoes, SessaoError

QUESTOES = [
    {"id": "q1", "original": "Explique a evaporação da água.", "adaptado": "1) Leia. 2) Explique a evaporação."},
    {"id": "q2", "original": "Descreva a condensação.", "adaptado": "1) Releia. 2) Descreva a condensação."},
]


@pytest.fixture()
def repo() -> RepositorioSessoes:
    return RepositorioSessoes()


@pytest.fixture()
def sid(repo: RepositorioSessoes) -> str:
    return repo.criar({"titulo": "Ciências - Ciclo da água", "questoes": QUESTOES})["id"]


def aprovar_tudo(repo, sid):
    return repo.revisar(sid, {"questoes": [{"id": "q1", "aprovada": True}, {"id": "q2", "aprovada": True}]})


def texto_pdf(dados: bytes) -> str:
    try:
        import pymupdf as fitz
    except ImportError:  # versões antigas
        import fitz

    with fitz.open(stream=dados, filetype="pdf") as doc:
        return unicodedata.normalize("NFKC", " ".join(p.get_text() for p in doc))


# ---- criação e leitura ------------------------------------------------------------------------
def test_criar_devolve_estado_inicial_bloqueado(repo):
    s = repo.criar({"titulo": "Aula", "questoes": QUESTOES})
    assert s["homologada"] is False and s["pode_exportar"] is False and s["pode_homologar"] is False
    assert [q["aprovada"] for q in s["questoes"]] == [False, False]
    assert s["versao_final"] == "1) Leia. 2) Explique a evaporação.\n\n1) Releia. 2) Descreva a condensação."
    assert len(s["id"]) >= 16


def test_ids_de_sessao_nao_se_repetem(repo):
    ids = {repo.criar({"questoes": QUESTOES})["id"] for _ in range(50)}
    assert len(ids) == 50


@pytest.mark.parametrize(
    "dados,code",
    [
        ([], "INVALID_BODY"),
        ({"questoes": []}, "NO_QUESTIONS"),
        ({"questoes": "x"}, "NO_QUESTIONS"),
        ({"questoes": [{"adaptado": "  "}]}, "EMPTY_FIELD"),
        ({"questoes": [{"adaptado": 5}]}, "INVALID_FIELD"),
        ({"questoes": [{"id": "a", "adaptado": "x"}, {"id": "a", "adaptado": "y"}]}, "DUPLICATE_QUESTION"),
        ({"questoes": [{"adaptado": "x", "aprovada": True}]}, "UNKNOWN_FIELD"),
        ({"questoes": [{"adaptado": "x"}], "homologada": True}, "UNKNOWN_FIELD"),
        ({"titulo": "t" * 500, "questoes": [{"adaptado": "x"}]}, "FIELD_TOO_LONG"),
        ({"questoes": [{"adaptado": "x" * 6000}]}, "FIELD_TOO_LONG"),
    ],
)
def test_criar_recusa_entradas_invalidas(repo, dados, code):
    with pytest.raises(SessaoError) as e:
        repo.criar(dados)
    assert e.value.code == code and e.value.status == 422


def test_sessao_inexistente_vira_404(repo):
    for acao in (repo.ler, repo.descartar, repo.verificar):
        with pytest.raises(SessaoError) as e:
            acao("nao-existe")
        assert e.value.status == 404 and e.value.code == "SESSION_NOT_FOUND"


# ---- edição e aprovação -----------------------------------------------------------------------
def test_edicao_atualiza_a_versao_final_na_hora(repo, sid):
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "Explique a evaporação em 2 linhas."}]})
    assert s["questoes"][0]["adaptado"] == "Explique a evaporação em 2 linhas."
    assert s["questoes"][0]["editada"] is True
    assert s["versao_final"].startswith("Explique a evaporação em 2 linhas.")
    assert repo.ler(sid)["versao_final"] == s["versao_final"]
    assert s["revisao"] == 1


def test_o_original_nunca_muda(repo, sid):
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "novo texto"}]})
    assert s["questoes"][0]["original"] == QUESTOES[0]["original"]


def test_aprovar_por_questao(repo, sid):
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "aprovada": True}]})
    assert [q["aprovada"] for q in s["questoes"]] == [True, False]
    assert s["pode_homologar"] is False


def test_editar_e_aprovar_na_mesma_chamada_aprova_a_versao_nova(repo, sid):
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "novo", "aprovada": True}]})
    assert s["questoes"][0]["adaptado"] == "novo" and s["questoes"][0]["aprovada"] is True


def test_editar_questao_aprovada_tira_a_aprovacao(repo, sid):
    aprovar_tudo(repo, sid)
    s = repo.revisar(sid, {"questoes": [{"id": "q2", "adaptado": "Descreva a condensação com um exemplo."}]})
    assert [q["aprovada"] for q in s["questoes"]] == [True, False]
    assert s["pode_homologar"] is False


def test_reenviar_o_mesmo_texto_nao_conta_como_edicao(repo, sid):
    aprovar_tudo(repo, sid)
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": QUESTOES[0]["adaptado"]}]})
    assert s["questoes"][0]["aprovada"] is True and s["questoes"][0]["editada"] is False


def test_revisao_e_tudo_ou_nada(repo, sid):
    with pytest.raises(SessaoError) as e:
        repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "mudou"}, {"id": "zzz", "aprovada": True}]})
    assert e.value.code == "UNKNOWN_QUESTION"
    assert repo.ler(sid)["questoes"][0]["adaptado"] == QUESTOES[0]["adaptado"]


@pytest.mark.parametrize(
    "dados,code",
    [
        ({"questoes": [{"id": "q1", "adaptado": "  "}]}, "EMPTY_FIELD"),
        ({"questoes": [{"id": "q1", "aprovada": "sim"}]}, "INVALID_FIELD"),
        ({"questoes": "x"}, "INVALID_FIELD"),
        ({"homologar": "sim"}, "INVALID_FIELD"),
        ({"questoes": [{"id": "q1", "extra": 1}]}, "UNKNOWN_FIELD"),
        ({"exportar": True}, "UNKNOWN_FIELD"),
        ({"questoes": [{"id": "q1", "adaptado": "x" * 6000}]}, "FIELD_TOO_LONG"),
    ],
)
def test_revisao_recusa_entradas_invalidas(repo, sid, dados, code):
    with pytest.raises(SessaoError) as e:
        repo.revisar(sid, dados)
    assert e.value.code == code


# ---- Human-in-the-Loop: homologação e trava da exportação -------------------------------------
@pytest.mark.parametrize("formato", ["pdf", "docx"])
def test_exportacao_bloqueada_sem_homologacao(repo, sid, formato):
    with pytest.raises(SessaoError) as e:
        repo.exportar(sid, formato)
    assert e.value.status == 409 and e.value.code == "EXPORT_BLOCKED"


def test_aprovar_todas_as_questoes_nao_libera_a_exportacao(repo, sid):
    s = aprovar_tudo(repo, sid)
    assert s["pode_homologar"] is True and s["pode_exportar"] is False
    with pytest.raises(SessaoError) as e:
        repo.exportar(sid, "pdf")
    assert e.value.code == "EXPORT_BLOCKED"


def test_homologar_sem_aprovar_tudo_e_recusado(repo, sid):
    repo.revisar(sid, {"questoes": [{"id": "q1", "aprovada": True}]})
    with pytest.raises(SessaoError) as e:
        repo.revisar(sid, {"homologar": True})
    assert e.value.status == 409 and e.value.code == "NOT_ALL_APPROVED"
    assert repo.ler(sid)["homologada"] is False


def test_nao_da_para_aprovar_e_homologar_com_questao_pendente(repo, sid):
    with pytest.raises(SessaoError) as e:
        repo.revisar(sid, {"questoes": [{"id": "q1", "aprovada": True}], "homologar": True})
    assert e.value.code == "NOT_ALL_APPROVED"


def test_homologar_libera_a_exportacao_e_o_arquivo_traz_a_versao_do_professor(repo, sid):
    repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "Explique a evaporação com suas palavras."}]})
    aprovar_tudo(repo, sid)
    s = repo.revisar(sid, {"homologar": True})
    assert s["homologada"] is True and s["pode_exportar"] is True
    pdf = repo.exportar(sid, "pdf")
    assert pdf.conteudo.startswith(b"%PDF")
    assert "Explique a evaporação com suas palavras." in texto_pdf(pdf.conteudo)
    docx = repo.exportar(sid, "docx")
    assert docx.conteudo[:2] == b"PK"


def test_editar_depois_de_homologar_revoga_a_homologacao_e_bloqueia_de_novo(repo, sid):
    aprovar_tudo(repo, sid)
    repo.revisar(sid, {"homologar": True})
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "Texto mudou depois."}]})
    assert s["homologada"] is False and s["pode_exportar"] is False
    with pytest.raises(SessaoError) as e:
        repo.exportar(sid, "pdf")
    assert e.value.code == "EXPORT_BLOCKED"


def test_desaprovar_depois_de_homologar_revoga(repo, sid):
    aprovar_tudo(repo, sid)
    repo.revisar(sid, {"homologar": True})
    s = repo.revisar(sid, {"questoes": [{"id": "q1", "aprovada": False}]})
    assert s["homologada"] is False
    with pytest.raises(SessaoError):
        repo.exportar(sid, "pdf")


def test_professor_pode_retirar_a_homologacao(repo, sid):
    aprovar_tudo(repo, sid)
    repo.revisar(sid, {"homologar": True})
    assert repo.revisar(sid, {"homologar": False})["pode_exportar"] is False


def test_homologar_de_novo_apos_mudanca_exige_nova_confirmacao(repo, sid):
    aprovar_tudo(repo, sid)
    repo.revisar(sid, {"homologar": True})
    repo.revisar(sid, {"questoes": [{"id": "q1", "adaptado": "outra versão", "aprovada": True}]})
    assert repo.ler(sid)["pode_exportar"] is False
    assert repo.revisar(sid, {"homologar": True})["pode_exportar"] is True


def test_a_exportacao_nao_tem_atalho_para_pular_a_homologacao(repo, sid):
    import inspect

    assert list(inspect.signature(repo.exportar).parameters) == ["sid", "formato"]
    with pytest.raises(TypeError):
        repo.exportar(sid, "pdf", forcar=True)  # type: ignore[call-arg]


def test_titulo_clinico_na_sessao_e_recusado_so_na_exportacao(repo):
    sid = repo.criar({"titulo": "Atividade para aluno com TDAH", "questoes": QUESTOES})["id"]
    aprovar_tudo(repo, sid)
    repo.revisar(sid, {"homologar": True})
    with pytest.raises(SessaoError) as e:
        repo.exportar(sid, "pdf")
    assert e.value.code == "CLINICAL_LABEL_IN_HEADER"


def test_verificar_avisa_sobre_dado_pessoal_no_corpo(repo):
    sid = repo.criar({"questoes": [{"adaptado": "Escreva a conta de joao@escola.com.br e explique."}]})["id"]
    assert repo.verificar(sid)["possiveis_dados_pessoais"] >= 1


# ---- memória: validade, teto e descarte -------------------------------------------------------
def test_sessao_expira_por_inatividade():
    t = [0.0]
    r = RepositorioSessoes(ttl=60, relogio=lambda: t[0])
    sid = r.criar({"questoes": QUESTOES})["id"]
    t[0] = 59
    assert r.ler(sid)["id"] == sid
    t[0] = 59 + 61
    with pytest.raises(SessaoError) as e:
        r.ler(sid)
    assert e.value.status == 404


def test_teto_de_sessoes_simultaneas():
    r = RepositorioSessoes(maximo=2)
    r.criar({"questoes": QUESTOES}); r.criar({"questoes": QUESTOES})
    with pytest.raises(SessaoError) as e:
        r.criar({"questoes": QUESTOES})
    assert e.value.code == "TOO_MANY_SESSIONS" and e.value.status == 409


def test_descartar_remove_a_sessao(repo, sid):
    repo.descartar(sid)
    assert len(repo) == 0
    with pytest.raises(SessaoError):
        repo.ler(sid)


# ---- não persiste (RNF-01) --------------------------------------------------------------------
def test_modulo_nao_importa_nem_chama_nada_de_persistencia():
    src = Path(revisao.__file__).read_text(encoding="utf-8")
    arvore = ast.parse(src)
    proibidos = {"sqlite3", "pickle", "shelve", "requests", "httpx", "urllib", "socket", "tempfile", "shutil", "logging"}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            assert not proibidos & {a.name.split(".")[0] for a in no.names}
        if isinstance(no, ast.ImportFrom):
            assert (no.module or "").split(".")[0] not in proibidos
        if isinstance(no, ast.Call):
            nome = getattr(no.func, "id", getattr(no.func, "attr", ""))
            assert nome not in {"open", "print", "write_text", "write_bytes", "dump", "dumps"}


def test_operacoes_nao_gravam_arquivo_nem_abrem_rede(repo, monkeypatch):
    abrir = builtins.open

    def vigiar(arq, modo="r", *a, **k):
        assert not any(c in str(modo) for c in "wax+"), f"escrita proibida em {arq}"
        return abrir(arq, modo, *a, **k)

    def sem_rede(*a, **k):
        raise AssertionError("rede proibida")

    monkeypatch.setattr(builtins, "open", vigiar)
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    s = repo.criar({"titulo": "Aula", "questoes": QUESTOES})["id"]
    aprovar_tudo(repo, s)
    repo.revisar(s, {"homologar": True})
    assert repo.exportar(s, "pdf").conteudo.startswith(b"%PDF")
    assert repo.exportar(s, "docx").conteudo[:2] == b"PK"


# ---- HTTP -------------------------------------------------------------------------------------
@pytest.fixture()
def cliente(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import iris.api.routes.sessoes as rotas

    novo = RepositorioSessoes()
    monkeypatch.setattr(rotas, "REPOSITORIO", novo)
    app = FastAPI()
    app.include_router(rotas.router, prefix="/api/v1")
    return TestClient(app)


def test_http_fluxo_completo_com_trava(cliente):
    r = cliente.post("/api/v1/sessions", json={"titulo": "Aula", "questoes": QUESTOES})
    assert r.status_code == 201
    sid = r.json()["id"]
    base = f"/api/v1/sessions/{sid}"

    bloqueado = cliente.post(f"{base}/export?formato=pdf")
    assert bloqueado.status_code == 409 and bloqueado.json()["detail"]["code"] == "EXPORT_BLOCKED"

    r = cliente.put(f"{base}/review", json={"questoes": [{"id": "q1", "adaptado": "Texto do professor.", "aprovada": True}]})
    assert r.status_code == 200 and r.json()["versao_final"].startswith("Texto do professor.")
    assert cliente.get(base).json()["versao_final"].startswith("Texto do professor.")

    r = cliente.put(f"{base}/review", json={"homologar": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOT_ALL_APPROVED"

    cliente.put(f"{base}/review", json={"questoes": [{"id": "q2", "aprovada": True}]})
    assert cliente.put(f"{base}/review", json={"homologar": True}).json()["pode_exportar"] is True

    for formato, magico in (("pdf", b"%PDF"), ("docx", b"PK")):
        ok = cliente.post(f"{base}/export?formato={formato}")
        assert ok.status_code == 200 and ok.content.startswith(magico)
        assert ok.headers["cache-control"] == "no-store"
        assert ok.headers["content-disposition"] == f'attachment; filename="atividade-adaptada.{formato}"'

    assert cliente.delete(base).status_code == 204
    assert cliente.get(base).status_code == 404


def test_http_erros(cliente):
    assert cliente.get("/api/v1/sessions/xxx").status_code == 404
    assert cliente.put("/api/v1/sessions/xxx/review", json={}).status_code == 404
    assert cliente.post("/api/v1/sessions", json={"questoes": []}).status_code == 422
    sid = cliente.post("/api/v1/sessions", json={"questoes": QUESTOES}).json()["id"]
    assert cliente.put(f"/api/v1/sessions/{sid}/review", json={"homologar": "sim"}).status_code == 422
    assert cliente.put(f"/api/v1/sessions/{sid}/review", json=[1]).status_code == 422


def test_http_formato_invalido_so_depois_de_homologar(cliente):
    sid = cliente.post("/api/v1/sessions", json={"questoes": QUESTOES}).json()["id"]
    base = f"/api/v1/sessions/{sid}"
    cliente.put(f"{base}/review", json={"questoes": [{"id": "q1", "aprovada": True}, {"id": "q2", "aprovada": True}], "homologar": True})
    assert cliente.post(f"{base}/export?formato=exe").status_code == 422


_FASTAPI_HTTPX = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None


class TestSessaoRevisaoUnittest(unittest.TestCase):
    """Permite coleta e execução no `unittest discover` do CI mantendo os testes pytest."""

    def test_criacao_edicao_e_aprovacao(self) -> None:
        r = RepositorioSessoes()
        test_criar_devolve_estado_inicial_bloqueado(r)
        test_ids_de_sessao_nao_se_repetem(r)
        test_sessao_inexistente_vira_404(r)
        for fn in (
            test_edicao_atualiza_a_versao_final_na_hora,
            test_o_original_nunca_muda,
            test_aprovar_por_questao,
            test_editar_e_aprovar_na_mesma_chamada_aprova_a_versao_nova,
            test_editar_questao_aprovada_tira_a_aprovacao,
            test_reenviar_o_mesmo_texto_nao_conta_como_edicao,
            test_revisao_e_tudo_ou_nada,
        ):
            repo_item = RepositorioSessoes()
            sid_item = repo_item.criar({"titulo": "Ciências - Ciclo da água", "questoes": QUESTOES})["id"]
            fn(repo_item, sid_item)

    def test_homologacao_e_trava_de_exportacao(self) -> None:
        for formato in ("pdf", "docx"):
            r = RepositorioSessoes()
            test_exportacao_bloqueada_sem_homologacao(r, r.criar({"questoes": QUESTOES})["id"], formato)
        for fn in (
            test_aprovar_todas_as_questoes_nao_libera_a_exportacao,
            test_homologar_sem_aprovar_tudo_e_recusado,
            test_nao_da_para_aprovar_e_homologar_com_questao_pendente,
            test_homologar_libera_a_exportacao_e_o_arquivo_traz_a_versao_do_professor,
            test_editar_depois_de_homologar_revoga_a_homologacao_e_bloqueia_de_novo,
            test_desaprovar_depois_de_homologar_revoga,
            test_professor_pode_retirar_a_homologacao,
            test_homologar_de_novo_apos_mudanca_exige_nova_confirmacao,
            test_a_exportacao_nao_tem_atalho_para_pular_a_homologacao,
        ):
            r = RepositorioSessoes()
            fn(r, r.criar({"titulo": "Ciências - Ciclo da água", "questoes": QUESTOES})["id"])
        test_titulo_clinico_na_sessao_e_recusado_so_na_exportacao(RepositorioSessoes())
        test_verificar_avisa_sobre_dado_pessoal_no_corpo(RepositorioSessoes())

    def test_memoria_ttl_teto_e_ast(self) -> None:
        test_sessao_expira_por_inatividade()
        test_teto_de_sessoes_simultaneas()
        r = RepositorioSessoes()
        test_descartar_remove_a_sessao(r, r.criar({"questoes": QUESTOES})["id"])
        test_modulo_nao_importa_nem_chama_nada_de_persistencia()

    @unittest.skipUnless(_FASTAPI_HTTPX, "requer FastAPI e httpx")
    def test_rotas_http_revisao_e_exportacao(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import iris.api.routes.sessoes as rotas

        app = FastAPI()
        app.include_router(rotas.router, prefix="/api/v1")
        with patch.object(rotas, "REPOSITORIO", RepositorioSessoes()):
            client = TestClient(app)
            test_http_fluxo_completo_com_trava(client)
            test_http_erros(client)
            test_http_formato_invalido_so_depois_de_homologar(client)
