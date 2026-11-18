"""Testes da observação por voz (História 1.2.3, RF-03/RF-05, RNF-01/02/03).

A transcrição real (faster-whisper) precisa de modelo baixado e não roda no CI: os testes usam um transcritor
de mentira que devolve relatos docentes em português, e áudios sintetizados (tons) para exercitar a validação.
Os testes de WebM/Ogg/MP4 precisam do PyAV (`pip install av`, vem com o faster-whisper) e são pulados sem ele.
"""
from __future__ import annotations

import ast
import builtins
import io
import math
import socket
import struct
import sys
import types
import wave
from pathlib import Path

import pytest

import iris.audio as pacote_audio
from iris.audio.erros import AudioError
from iris.audio.mapeador import LEXICO, LIMITE_SUGESTOES, normalizar, sugerir_caracteristicas
from iris.audio.servico import sugerir_de_texto, transcrever_observacao
from iris.audio.transcricao import FasterWhisperTranscritor, definir_transcritor
from iris.audio.validacao import MAX_BYTES, detectar_formato, validar_audio
from iris.schemas.catalog import load_official_tdah_catalog

CATALOGO = load_official_tdah_catalog()
IDS = [c.id_caracteristica for c in CATALOGO.caracteristicas]


# ---- áudios simulados ----------------------------------------------------------------------------
def wav(segundos: float, taxa: int = 16000, canais: int = 1) -> bytes:
    n = int(segundos * taxa)
    quadros = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / taxa))) * canais for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(canais), w.setsampwidth(2), w.setframerate(taxa)
        w.writeframes(quadros)
    return buf.getvalue()


def container(formato: str, segundos: float) -> bytes:
    av = pytest.importorskip("av")
    import numpy as np

    codec, nome, taxa = {"webm": ("libopus", "webm", 48000), "ogg": ("libopus", "ogg", 48000), "mp4": ("aac", "mp4", 44100)}[formato]
    buf = io.BytesIO()
    try:
        with av.open(buf, "w", format=nome) as c:
            st = c.add_stream(codec, rate=taxa)
            st.layout = "mono"
            quadro = 1024 if codec == "aac" else 960
            total, feito = int(segundos * taxa), 0
            while feito < total:
                n = min(quadro, total - feito)
                t = (np.arange(feito, feito + n) / taxa)
                dados = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16).reshape(1, -1)
                f = av.AudioFrame.from_ndarray(dados, format="s16", layout="mono")
                f.sample_rate, f.pts = taxa, feito
                for p in st.encode(f):
                    c.mux(p)
                feito += n
            for p in st.encode(None):
                c.mux(p)
    except Exception as err:  # encoder indisponível nesta build do PyAV
        pytest.skip(f"sem encoder {codec}: {err}")
    return buf.getvalue()


class TranscritorFalso:
    def __init__(self, texto: str) -> None:
        self.texto, self.recebido = texto, None

    def transcrever(self, audio: bytes, idioma: str = "pt") -> str:
        self.recebido = (len(audio), idioma)
        return self.texto


@pytest.fixture(autouse=True)
def _restaura_transcritor():
    yield
    definir_transcritor(None)


# ---- validação do áudio --------------------------------------------------------------------------
def test_formato_pelo_conteudo_e_nao_pelo_nome():
    assert detectar_formato(wav(1)) == "wav"
    assert detectar_formato(b"\x1a\x45\xdf\xa3" + b"\0" * 20) == "webm"
    assert detectar_formato(b"OggS" + b"\0" * 20) == "ogg"
    assert detectar_formato(b"\0\0\0\x18ftypM4A " + b"\0" * 20) == "mp4"
    assert detectar_formato(b"%PDF-1.7 ...") is None
    assert detectar_formato(b"") is None


@pytest.mark.parametrize("segundos", [1, 30, 60])
def test_aceita_ate_60_segundos(segundos):
    meta = validar_audio(wav(segundos))
    assert meta.formato == "wav" and abs(meta.duracao_segundos - segundos) < 0.1


def test_aceita_a_folga_do_gravador_do_navegador():
    assert validar_audio(wav(60.6)).duracao_segundos > 60


@pytest.mark.parametrize("segundos", [62.5, 90])
def test_recusa_mais_de_60_segundos(segundos):
    with pytest.raises(AudioError) as e:
        validar_audio(wav(segundos))
    assert e.value.code == "AUDIO_TOO_LONG" and e.value.status == 422


def test_recusa_audio_curto_demais():
    with pytest.raises(AudioError) as e:
        validar_audio(wav(0.1))
    assert e.value.code == "AUDIO_TOO_SHORT"


def test_cabecalho_adulterado_nao_esconde_audio_longo():
    dados = bytearray(wav(90, taxa=8000))
    dados[40:44] = struct.pack("<I", 8000 * 2 * 5)  # o cabeçalho jura que são 5 s
    with pytest.raises(AudioError) as e:
        validar_audio(bytes(dados))
    assert e.value.code == "AUDIO_TOO_LONG"


@pytest.mark.parametrize(
    "dados,code,status",
    [
        (b"", "EMPTY_AUDIO", 422),
        (b"texto qualquer, nao e audio" * 10, "UNSUPPORTED_AUDIO", 415),
        (b"%PDF-1.7\n" + b"x" * 500, "UNSUPPORTED_AUDIO", 415),
        (b"RIFF\x00\x00\x00\x00WAVEjunk" + b"\0" * 20, "CORRUPT_AUDIO", 422),
        (b"\0" * (MAX_BYTES + 1), "AUDIO_TOO_LARGE", 413),
    ],
)
def test_recusa_entradas_invalidas(dados, code, status):
    with pytest.raises(AudioError) as e:
        validar_audio(dados)
    assert (e.value.code, e.value.status) == (code, status)


@pytest.mark.parametrize("formato", ["webm", "ogg", "mp4"])
def test_containers_do_navegador_tem_a_duracao_medida(formato):
    meta = validar_audio(container(formato, 4))
    assert meta.formato == formato and 3.5 < meta.duracao_segundos < 5


@pytest.mark.parametrize("formato", ["webm", "ogg", "mp4"])
def test_containers_acima_de_60_segundos_sao_recusados(formato):
    with pytest.raises(AudioError) as e:
        validar_audio(container(formato, 66))
    assert e.value.code == "AUDIO_TOO_LONG"


def test_container_cortado_nunca_quebra_com_erro_inesperado():
    pytest.importorskip("av")
    dados = container("webm", 3)
    for corte in (20, 100, len(dados) // 4, len(dados) // 2):
        try:
            meta = validar_audio(dados[:corte])
        except AudioError as err:  # corrompido ou curto demais: recusa limpa
            assert err.code in {"CORRUPT_AUDIO", "AUDIO_TOO_SHORT"}
        else:  # cortado no meio ainda é um áudio válido, só que mais curto
            assert 0 < meta.duracao_segundos <= 3.5


# ---- mapeador de fala -> características ---------------------------------------------------------
RELATOS = {
    "sobrecarga_memoria_trabalho_comandos_multiplos": [
        "Quando a questão pede para identificar, justificar e dar um exemplo, ele responde só a primeira parte e esquece de responder a segunda.",
        "Dou uma atividade com três perguntas juntas e ela só responde a de cima, a instrução tem muitos comandos.",
        "Meu aluno, quando a questão manda ler, comparar e explicar, faz só a primeira coisa e o resto some da cabeça dele.",
    ],
    "retencao_dados_intermediarios_problemas_multietapas": [
        "Nos problemas de várias etapas ele se perde no meio do cálculo e esquece a unidade de medida do primeiro parágrafo.",
        "No problema de física ele monta o raciocínio certo, só que perde os números do enunciado e troca os valores.",
    ],
    "atencao_sustentada_textos_longos": [
        "Em textos longos ele pula direto para as alternativas, não termina de ler.",
        "Quando o texto-base é extenso ele desiste de ler no segundo parágrafo e pula pras alternativas.",
        "Ele não aguenta ler um texto grande, na metade já está olhando pro lado e vai chutar as alternativas.",
    ],
    "distratibilidade_poluicao_visual_layout": [
        "Ela se distrai com as figuras e as caixas laterais, a página fica muito carregada.",
        "Qualquer desenho na prova já chama a atenção dele, ele fica olhando a figura e esquece da pergunta.",
        "Nas provas com muita imagem e caixas coloridas na página ele se distrai com as figuras.",
    ],
    "impulsividade_leitura_superficial_negacoes": [
        "Responde rápido, marca antes de ler até o fim e ignora a palavra NÃO nas questões de exceto.",
        "Ele lê a primeira frase e já responde, nem vê que a questão pedia a alternativa incorreta.",
        "Ele responde afobado, não lê direito o enunciado e erra as questões que pedem a exceção.",
    ],
    "organizacao_sequencial_expressao_escrita": [
        "Sabe explicar oralmente, mas nas questões discursivas escreve de forma desorganizada, sem começo, meio e fim.",
        "Fala muito bem em sala, mas nas respostas discursivas escreve ideias soltas, sem começo, meio e fim.",
    ],
    "fadiga_executiva_autorregulacao_provas_extensas": [
        "Começa bem a prova, mas cansa no meio da avaliação e chuta as últimas questões.",
        "Na primeira metade da prova ele vai super bem, depois vai desanimando e as últimas questões ele deixa em branco.",
        "Provas longas esgotam ele: no final já está cansado e chuta as últimas.",
    ],
    "flexibilidade_cognitiva_alternancia_topicos": [
        "Continua usando a regra da questão anterior quando a prova muda de assunto.",
        "Quando muda de assunto na prova ele continua aplicando a mesma fórmula da questão anterior.",
    ],
    "bloqueio_iniciacao_tarefas_abertas": [
        "Fica parado olhando para a folha em branco, demora muito para começar as questões abertas.",
        "Diante de uma questão aberta ele fica paralisado, não sabe por onde começar e entrega a folha em branco.",
    ],
    "ritmo_processamento_pressao_temporal": [
        "Precisa de mais tempo, trava com frases muito longas e não termina a prova no tempo.",
        "Com a pressão do tempo ele trava, as frases longas do enunciado ele demora para decodificar e precisa de mais tempo.",
    ],
}
CASOS = [(cid, fala) for cid, falas in RELATOS.items() for fala in falas]


@pytest.mark.parametrize("cid,fala", CASOS, ids=[f"{c[:12]}-{i}" for i, (c, _) in enumerate(CASOS)])
def test_relato_sugere_a_caracteristica_certa(cid, fala):
    assert cid in [s.id_caracteristica for s in sugerir_caracteristicas(fala, CATALOGO)]


@pytest.mark.parametrize(
    "fala",
    [
        "A turma está animada com a feira de ciências e o aluno participou bastante.",
        "Preciso entregar as notas até sexta e a direção pediu o relatório do bimestre.",
        "A reunião de pais foi remarcada e a coordenação quer ajustar o calendário de provas.",
        "Ele é muito querido pela turma, adora futebol e sempre ajuda a organizar a sala.",
        "",
        "   ",
    ],
)
def test_fala_sem_dificuldade_nao_sugere_nada(fala):
    assert sugerir_caracteristicas(fala, CATALOGO) == []


@pytest.mark.parametrize("fala", ["O aluno tem TDAH e toma ritalina.", "Ele tem laudo de TDAH, CID F90, e faz uso de medicação."])
def test_diagnostico_e_medicacao_sozinhos_nao_geram_sugestao(fala):
    assert sugerir_caracteristicas(fala, CATALOGO) == []


def test_varias_dificuldades_viram_varias_sugestoes_ordenadas_por_pontuacao():
    fala = (
        "Em textos longos ele pula direto para as alternativas. Nas questões discursivas escreve de forma desorganizada, "
        "sem começo, meio e fim. E fica parado olhando para a folha em branco."
    )
    s = sugerir_caracteristicas(fala, CATALOGO)
    assert {x.id_caracteristica for x in s} >= {
        "atencao_sustentada_textos_longos", "organizacao_sequencial_expressao_escrita", "bloqueio_iniciacao_tarefas_abertas",
    }
    pontos = [x.pontuacao for x in s]
    assert pontos == sorted(pontos, reverse=True)


def test_nunca_passa_do_limite_de_sugestoes():
    fala = " ".join(f for falas in RELATOS.values() for f in falas)
    assert len(sugerir_caracteristicas(fala, CATALOGO)) == LIMITE_SUGESTOES


def test_evidencias_sao_trechos_literais_da_fala():
    fala = "Em Textos Longos, ele PULA direto para as alternativas."
    (s,) = [x for x in sugerir_caracteristicas(fala, CATALOGO) if x.id_caracteristica == "atencao_sustentada_textos_longos"]
    assert s.evidencias and all(e in fala for e in s.evidencias)
    assert s.confianca in {"alta", "media"}


def test_normalizacao_mantem_o_comprimento_para_citar_o_trecho_original():
    texto = "Ação, ÁÉÍÓÚ ç ã — fim!"
    assert len(normalizar(texto)) == len(texto)
    assert normalizar("NÃO") == "nao"


def test_lexico_cobre_todas_as_caracteristicas_do_catalogo_e_so_elas():
    assert set(LEXICO) == set(IDS), "característica nova no catálogo precisa de gatilhos em audio/mapeador.py"


def test_caracteristica_nova_sem_lexico_cai_na_reserva_por_palavras_chave():
    novo = types.SimpleNamespace(
        id_caracteristica="nova_sem_lexico", nome="Nova", palavras_chave_busca=["leitura labial", "ruido de fundo"]
    )
    cat = types.SimpleNamespace(caracteristicas=[novo])
    assert sugerir_caracteristicas("Atrapalha a leitura labial por causa do ruído de fundo.", cat)[0].id_caracteristica == "nova_sem_lexico"
    assert sugerir_caracteristicas("Só falou da leitura labial.", cat) == []  # uma palavra-chave fraca não basta


# ---- serviço: transcrição + PII + sugestões ------------------------------------------------------
RELATO_COM_NOME = (
    "O aluno Gabriel Silva, do 7º ano, em textos longos pula direto para as alternativas e não termina de ler. "
    "Falei com a mãe pelo telefone (11) 98765-4321."
)


def test_servico_devolve_transcricao_sanitizada_e_sugestoes():
    falso = TranscritorFalso(RELATO_COM_NOME)
    r = transcrever_observacao(wav(5), transcritor=falso)
    assert falso.recebido[1] == "pt"
    assert "Gabriel" not in r["transcricao"] and "98765" not in r["transcricao"]
    assert "[ESTUDANTE]" in r["transcricao"]
    assert r["pii_substituicoes"] >= 2
    assert r["duracao_segundos"] == pytest.approx(5, abs=0.1) and r["formato"] == "wav"
    assert [s["id_caracteristica"] for s in r["sugestoes"]] == ["atencao_sustentada_textos_longos"]
    assert r["id_catalogo"] == CATALOGO.id_catalogo and r["avisos"] == []


def test_sugestoes_saem_do_texto_sanitizado():
    r = transcrever_observacao(wav(3), transcritor=TranscritorFalso("O aluno Gabriel Silva ignora a palavra NÃO nas questões."))
    assert all("Gabriel" not in e for s in r["sugestoes"] for e in s["evidencias"])


def test_termo_clinico_gera_aviso_e_nao_vira_sugestao():
    r = transcrever_observacao(wav(3), transcritor=TranscritorFalso("Ele tem TDAH, toma ritalina e fica parado olhando para a folha em branco."))
    assert r["avisos"][0]["code"] == "CLINICAL_TERMS_IGNORED" and r["avisos"][0]["categorias"]
    assert [s["id_caracteristica"] for s in r["sugestoes"]] == ["bloqueio_iniciacao_tarefas_abertas"]


@pytest.mark.parametrize("texto", ["", "   ", "\n"])
def test_fala_nao_entendida(texto):
    with pytest.raises(AudioError) as e:
        transcrever_observacao(wav(3), transcritor=TranscritorFalso(texto))
    assert e.value.code == "NO_SPEECH_DETECTED"


def test_audio_invalido_nem_chega_ao_transcritor():
    falso = TranscritorFalso("qualquer coisa")
    with pytest.raises(AudioError):
        transcrever_observacao(wav(75), transcritor=falso)
    assert falso.recebido is None


def test_erro_do_transcritor_e_propagado():
    class Quebrado:
        def transcrever(self, audio, idioma="pt"):
            raise AudioError("sem modelo", "STT_MODEL_UNAVAILABLE", 503)

    with pytest.raises(AudioError) as e:
        transcrever_observacao(wav(3), transcritor=Quebrado())
    assert e.value.status == 503


def test_catalogo_inexistente():
    with pytest.raises(AudioError) as e:
        transcrever_observacao(wav(3), transcritor=TranscritorFalso("textos longos"), id_catalogo="nao_existe")
    assert e.value.code == "CATALOG_NOT_FOUND"


def test_sugerir_de_texto_digitado():
    r = sugerir_de_texto("Ele esquece de responder a segunda parte e perde o fio da instrução.")
    assert r["sugestoes"][0]["id_caracteristica"] == "sobrecarga_memoria_trabalho_comandos_multiplos"


@pytest.mark.parametrize("texto,code", [("", "EMPTY_TEXT"), ("  ", "EMPTY_TEXT"), (5, "EMPTY_TEXT"), ("x" * 6000, "TEXT_TOO_LONG")])
def test_sugerir_de_texto_invalido(texto, code):
    with pytest.raises(AudioError) as e:
        sugerir_de_texto(texto)
    assert e.value.code == code


# ---- motor de transcrição padrão (faster-whisper, simulado) --------------------------------------
class _ModeloFalso:
    ultimo = None

    def __init__(self, nome, **kw):
        type(self).ultimo = {"nome": nome, **kw}
        self.chamadas = []

    def transcribe(self, audio, **kw):
        self.chamadas.append((audio, kw))
        return iter([types.SimpleNamespace(text=" Em textos longos "), types.SimpleNamespace(text="pula as alternativas. ")]), None


def _com_faster_whisper_falso(monkeypatch):
    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = _ModeloFalso
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_motor_padrao_recebe_amostras_decodificadas_em_portugues_sem_arquivo_temporario(monkeypatch):
    pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    _com_faster_whisper_falso(monkeypatch)
    abrir = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, m="r", *a, **k: (_ for _ in ()).throw(AssertionError("arquivo!")) if any(c in str(m) for c in "wax+") else abrir(f, m, *a, **k))
    t = FasterWhisperTranscritor(modelo="small", somente_local=True)
    assert t.transcrever(wav(2)) == "Em textos longos pula as alternativas."
    audio, kw = t._whisper.chamadas[0]
    # o motor recebe amostras prontas (float32, mono, 16 kHz), não depende de como o faster-whisper chama o PyAV
    assert isinstance(audio, np.ndarray) and audio.dtype == np.float32 and audio.ndim == 1
    assert abs(len(audio) - 2 * 16000) < 400 and float(abs(audio).max()) <= 1.0
    assert kw["language"] == "pt" and kw["vad_filter"] is True
    assert _ModeloFalso.ultimo["local_files_only"] is True and _ModeloFalso.ultimo["compute_type"] == "int8"


def test_decodificar_para_amostras_wav_e_container():
    pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    from iris.audio.transcricao import decodificar_para_amostras

    x = decodificar_para_amostras(wav(1.5))
    assert x.dtype == np.float32 and abs(len(x) - 24000) < 400 and float(abs(x).max()) > 0.05


def test_decodificar_para_amostras_lixo_vira_corrupt_audio():
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    from iris.audio.transcricao import decodificar_para_amostras

    with pytest.raises(AudioError) as e:
        decodificar_para_amostras(b"isto nao e audio" * 50)
    assert (e.value.code, e.value.status) == ("CORRUPT_AUDIO", 422)


def test_sem_decodificador_o_erro_e_503_claro(monkeypatch):
    monkeypatch.setitem(sys.modules, "av", None)  # import levanta ImportError
    from iris.audio.transcricao import decodificar_para_amostras

    with pytest.raises(AudioError) as e:
        decodificar_para_amostras(wav(1))
    assert (e.value.code, e.value.status) == ("DECODER_UNAVAILABLE", 503)


def test_sem_faster_whisper_a_rota_avisa_com_503(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import levanta ImportError
    with pytest.raises(AudioError) as e:
        FasterWhisperTranscritor().transcrever(wav(1))
    assert (e.value.code, e.value.status) == ("STT_UNAVAILABLE", 503)


def test_modelo_que_nao_carrega_vira_503(monkeypatch):
    mod = types.ModuleType("faster_whisper")

    def quebrar(*a, **k):
        raise OSError("sem rede para baixar o modelo")

    mod.WhisperModel = quebrar
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    with pytest.raises(AudioError) as e:
        FasterWhisperTranscritor().transcrever(wav(1))
    assert (e.value.code, e.value.status) == ("STT_MODEL_UNAVAILABLE", 503)
    assert "rede" not in str(e.value)


def test_falha_durante_a_transcricao_vira_422(monkeypatch):
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    mod = types.ModuleType("faster_whisper")

    class Ruim(_ModeloFalso):
        def transcribe(self, audio, **kw):
            raise RuntimeError("decodificação falhou")

    mod.WhisperModel = Ruim
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    with pytest.raises(AudioError) as e:
        FasterWhisperTranscritor().transcrever(wav(1))
    assert e.value.code == "TRANSCRIPTION_FAILED"


# ---- zero retenção (RNF-01) ----------------------------------------------------------------------
def test_modulos_de_audio_nao_importam_nem_chamam_persistencia():
    proibidos = {"sqlite3", "pickle", "shelve", "tempfile", "shutil", "subprocess", "requests", "httpx", "urllib", "socket", "logging"}
    for arq in Path(pacote_audio.__file__).parent.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                assert not proibidos & {a.name.split(".")[0] for a in no.names}, arq.name
            if isinstance(no, ast.ImportFrom):
                assert (no.module or "").split(".")[0] not in proibidos, arq.name
            if isinstance(no, ast.Call):
                # `open(...)` e `print(...)` soltos (built-ins). `wave.open`/`av.open` leem de BytesIO, em memória.
                if isinstance(no.func, ast.Name):
                    assert no.func.id not in {"open", "print"}, (arq.name, no.func.id)
                nome = getattr(no.func, "attr", "")
                assert nome not in {"write_bytes", "write_text", "dump", "dumps", "NamedTemporaryFile"}, (arq.name, nome)


def test_fluxo_completo_nao_grava_arquivo_nem_abre_rede(monkeypatch):
    abrir = builtins.open

    def vigiar(arq, modo="r", *a, **k):
        assert not any(c in str(modo) for c in "wax+"), f"escrita proibida em {arq}"
        return abrir(arq, modo, *a, **k)

    def sem_rede(*a, **k):
        raise AssertionError("rede proibida")

    monkeypatch.setattr(builtins, "open", vigiar)
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    r = transcrever_observacao(wav(5), transcritor=TranscritorFalso(RELATO_COM_NOME))
    assert r["sugestoes"]
    assert sugerir_de_texto("Fica parado olhando para a folha em branco.")["sugestoes"]


# ---- HTTP ----------------------------------------------------------------------------------------
@pytest.fixture()
def cliente():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    pytest.importorskip("multipart")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from iris.api.routes.audio import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def enviar(cliente, dados: bytes, nome="obs.wav", tipo="audio/wav", **params):
    return cliente.post("/api/v1/audio/transcribe", files={"file": (nome, dados, tipo)}, params=params)


def test_http_transcreve_e_sugere(cliente):
    definir_transcritor(TranscritorFalso(RELATO_COM_NOME))
    r = enviar(cliente, wav(6))
    assert r.status_code == 200
    corpo = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert corpo["sugestoes"][0]["id_caracteristica"] == "atencao_sustentada_textos_longos"
    assert "Gabriel" not in r.text and "98765" not in r.text


def test_http_formato_vem_do_conteudo_e_nao_do_nome(cliente):
    definir_transcritor(TranscritorFalso("textos longos, pula direto para as alternativas"))
    assert enviar(cliente, wav(3), nome="relato.txt", tipo="text/plain").status_code == 200
    r = enviar(cliente, b"isto nao e audio" * 50, nome="relato.wav", tipo="audio/wav")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "UNSUPPORTED_AUDIO"


def test_http_limites(cliente):
    definir_transcritor(TranscritorFalso("textos longos"))
    assert enviar(cliente, wav(75)).status_code == 422
    assert enviar(cliente, wav(75)).json()["detail"]["code"] == "AUDIO_TOO_LONG"
    r = enviar(cliente, b"\0" * (MAX_BYTES + 10))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "AUDIO_TOO_LARGE"
    assert enviar(cliente, b"").status_code == 422


def test_http_sem_arquivo_e_motor_indisponivel(cliente):
    assert cliente.post("/api/v1/audio/transcribe").status_code == 422

    class Fora:
        def transcrever(self, audio, idioma="pt"):
            raise AudioError("A transcrição por voz não está instalada.", "STT_UNAVAILABLE", 503)

    definir_transcritor(Fora())
    r = enviar(cliente, wav(3))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "STT_UNAVAILABLE"


def test_http_sugerir_por_texto(cliente):
    r = cliente.post("/api/v1/audio/suggest", json={"texto": "Ele pula direto para as alternativas em textos longos."})
    assert r.status_code == 200 and r.json()["sugestoes"][0]["id_caracteristica"] == "atencao_sustentada_textos_longos"
    assert cliente.post("/api/v1/audio/suggest", json={"texto": ""}).status_code == 422
    assert cliente.post("/api/v1/audio/suggest", json={"texto": "x", "extra": 1}).status_code == 422
    assert cliente.post("/api/v1/audio/suggest", json=["x"]).status_code == 422
