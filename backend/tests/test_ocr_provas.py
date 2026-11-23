"""História 1.1.3 (RF-03): OCR de provas digitalizadas e indicador de poluição visual."""
from __future__ import annotations

import io
import random
import shutil

import pytest
from iris.ocr.erros import OcrError
from iris.ocr.motor import (
    MotorTesseract,
    ResultadoOcr,
    definir_motor,
    interpretar_tsv,
    preparar_para_ocr,
)
from iris.ocr.servico import (
    CONFIANCA_MINIMA,
    CONFIANCA_REVISAR,
    extrair_texto_da_imagem,
)
from iris.ocr.validacao import MAX_BYTES, detectar_formato, validar_imagem
from iris.ocr.visual import analisar_poluicao_visual
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEM_TESSERACT = shutil.which("tesseract") is not None

PROVA = [
    "QUESTAO 12",
    "Um instituto de pesquisa constatou que, nos ultimos dez anos, o crescimento",
    "populacional de uma cidade foi de 135,25 por cento. Qual e a representacao",
    "decimal da taxa percentual desse crescimento populacional?",
    "A) 13 525,0",
    "B) 135,25",
    "C) 13,525",
    "D) 1,3525",
    "E) 0,13525",
]


def _pagina(largura: int = 1240, altura: int = 1754, linhas: list[str] | None = None) -> Image.Image:
    """Folha com a prova repetida 3 vezes; a letra acompanha a largura (a mesma folha em outra resolução)."""
    escala = largura / 1240
    fonte = ImageFont.load_default(size=max(8, round(30 * escala)))
    im = Image.new("RGB", (largura, altura), "white")
    d = ImageDraw.Draw(im)
    y = 100 * escala
    for linha in (linhas or PROVA) * 3:
        d.text((90 * escala, y), linha, fill="black", font=fonte)
        y += 58 * escala
    return im


def _carregada(semente: int = 1) -> Image.Image:
    """Página com texto, caixas coloridas, borda e fotos: a prova 'poluída' do caso de teste."""
    rnd = random.Random(semente)
    im = _pagina()
    d = ImageDraw.Draw(im)
    d.rectangle((30, 30, 1210, 1724), outline="black", width=4)
    for _ in range(12):
        x, y = rnd.randint(0, 900), rnd.randint(0, 1500)
        d.rectangle((x, y, x + rnd.randint(150, 400), y + rnd.randint(80, 300)),
                    fill=rnd.choice(["#ffd54f", "#4fc3f7", "#ef5350", "#81c784", "#ba68c8"]), outline="black", width=3)
    for _ in range(6):
        x, y = rnd.randint(0, 800), rnd.randint(0, 1450)
        tamanho = (rnd.randint(200, 420), 220)
        im.paste(Image.merge("RGB", [Image.effect_noise(tamanho, 90) for _ in range(3)]), (x, y))
    return im


def _bytes(im: Image.Image, formato: str = "PNG", **kw) -> bytes:
    saida = io.BytesIO()
    im.save(saida, format=formato, **kw)
    return saida.getvalue()


def _tsv(*linhas: tuple[int, int, int, float, str]) -> str:
    cab = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    corpo = [f"5\t1\t{b}\t{p}\t{ln}\t1\t0\t0\t10\t10\t{conf}\t{t}" for b, p, ln, conf, t in linhas]
    return "\n".join([cab, *corpo])


class MotorFalso:
    def __init__(self, texto: str, confianca: float = 90.0, palavras: int | None = None) -> None:
        self.resultado = ResultadoOcr(texto, confianca, palavras if palavras is not None else len(texto.split()))
        self.chamadas = 0

    def reconhecer(self, imagem, idioma):
        self.chamadas += 1
        return self.resultado


TEXTO_PROVA = " ".join(PROVA)


@pytest.fixture(autouse=True)
def _restaura_motor():
    yield
    definir_motor(None)


# ---------- validação da imagem ----------

def test_formato_pelos_bytes_e_nao_pelo_nome():
    assert detectar_formato(_bytes(_pagina())) == "png"
    assert detectar_formato(_bytes(_pagina(), "JPEG")) == "jpeg"
    assert detectar_formato(b"%PDF-1.7 ...") is None
    assert detectar_formato(b"GIF89a....") is None


def test_imagem_valida_png_e_jpeg():
    for formato in ("PNG", "JPEG"):
        v = validar_imagem(_bytes(_pagina(), formato))
        assert (v.largura, v.altura) == (1240, 1754)
        assert v.imagem.mode == "RGB"


@pytest.mark.parametrize(
    "dados,code,status",
    [
        (b"", "EMPTY_IMAGE", 422),
        (b"%PDF-1.7 nao e imagem", "UNSUPPORTED_IMAGE_FORMAT", 415),
        (b"\x89PNG\r\n\x1a\n" + b"lixo" * 50, "CORRUPT_IMAGE", 422),
        (b"\xff\xd8\xff" + b"\x00" * 64, "CORRUPT_IMAGE", 422),
    ],
)
def test_recusas_de_arquivo(dados, code, status):
    with pytest.raises(OcrError) as e:
        validar_imagem(dados)
    assert (e.value.code, e.value.status) == (code, status)


def test_png_truncado_e_recusado_como_corrompido():
    png = _bytes(_pagina())
    with pytest.raises(OcrError) as e:
        validar_imagem(png[: len(png) // 2])
    assert e.value.code == "CORRUPT_IMAGE"


def test_imagem_acima_de_10mb():
    with pytest.raises(OcrError) as e:
        validar_imagem(b"\x89PNG\r\n\x1a\n" + b"0" * MAX_BYTES)
    assert (e.value.code, e.value.status) == ("IMAGE_TOO_LARGE", 413)


def test_imagem_com_pixels_demais_e_recusada_antes_de_decodificar():
    gigante = Image.new("L", (8000, 7000), 255)  # 56 megapixels, mas comprime a quase nada
    with pytest.raises(OcrError) as e:
        validar_imagem(_bytes(gigante))
    assert e.value.code == "IMAGE_TOO_LARGE"


def test_resolucao_insuficiente_diz_o_tamanho_e_o_minimo():
    with pytest.raises(OcrError) as e:
        validar_imagem(_bytes(_pagina(320, 240)))
    assert e.value.code == "IMAGE_RESOLUTION_TOO_LOW"
    assert "320×240" in str(e.value) and "400" in str(e.value)


def test_imagem_em_branco_sem_contraste():
    with pytest.raises(OcrError) as e:
        validar_imagem(_bytes(Image.new("RGB", (1000, 1400), "white")))
    assert e.value.code == "IMAGE_NO_CONTRAST"


def test_imagem_escura_demais():
    with pytest.raises(OcrError) as e:
        validar_imagem(_bytes(Image.new("RGB", (1000, 1400), (5, 5, 5))))
    assert e.value.code == "IMAGE_TOO_DARK"


def test_imagem_desfocada_e_recusada_e_a_nitida_passa():
    validar_imagem(_bytes(_pagina()))
    with pytest.raises(OcrError) as e:
        validar_imagem(_bytes(_pagina().filter(ImageFilter.GaussianBlur(4))))
    assert e.value.code == "IMAGE_TOO_BLURRY"


def test_foto_de_celular_girada_pelo_exif_e_endireitada():
    im = _pagina(1240, 900)
    exif = Image.Exif()
    exif[0x0112] = 6  # gire 90° para exibir: a imagem guardada é "deitada"
    v = validar_imagem(_bytes(im, "JPEG", exif=exif))
    assert (v.largura, v.altura) == (900, 1240)


def test_metadados_nao_passam_adiante():
    exif = Image.Exif()
    exif[0x010F] = "FabricanteSecreto"
    v = validar_imagem(_bytes(_pagina(), "JPEG", exif=exif))
    assert not v.imagem.getexif()
    assert "exif" not in v.imagem.info


def test_png_com_transparencia_vira_fundo_branco():
    rgba = _pagina().convert("RGBA")
    assert validar_imagem(_bytes(rgba)).imagem.getpixel((5, 5)) == (255, 255, 255)


# ---------- poluição visual ----------

def test_pagina_de_texto_nao_emite_indicador():
    a = analisar_poluicao_visual(_pagina())
    assert a.nivel == "baixa" and a.indicador_poluicao is False


def test_pagina_carregada_emite_indicador_com_motivo():
    a = analisar_poluicao_visual(_carregada())
    assert a.nivel == "alta" and a.indicador_poluicao is True
    assert a.motivos


def test_o_escore_cresce_com_a_carga_visual():
    limpa = analisar_poluicao_visual(_pagina()).escore
    d = ImageDraw.Draw(im := _pagina())
    for i in range(6):
        d.rectangle((60 + i * 190, 1200, 200 + i * 190, 1500), fill="#ef5350", outline="black", width=3)
    media = analisar_poluicao_visual(im).escore
    assert limpa < media < analisar_poluicao_visual(_carregada()).escore


def test_analise_nao_depende_do_tamanho_da_foto():
    grande = analisar_poluicao_visual(_carregada())
    pequena = analisar_poluicao_visual(_carregada().resize((620, 877)))
    assert grande.nivel == pequena.nivel == "alta"


# ---------- motor ----------

def test_interpretar_tsv_remonta_linhas_paragrafos_e_confianca():
    r = interpretar_tsv(_tsv((1, 1, 1, 96, "Questão"), (1, 1, 1, 94, "12"), (1, 1, 2, 90, "Leia"),
                             (1, 2, 1, 80, "A)"), (1, 2, 1, 70, "dez"), (1, 2, 1, -1, "")))
    assert r.texto == "Questão 12\nLeia\n\nA) dez"
    assert r.palavras == 5
    assert round(r.confianca_media, 1) == 86.0


def test_interpretar_tsv_sem_palavras():
    r = interpretar_tsv(_tsv())
    assert (r.texto, r.palavras, r.confianca_media) == ("", 0, 0.0)


def test_preparar_para_ocr_amplia_foto_pequena_e_reduz_gigante():
    pequena = Image.open(io.BytesIO(preparar_para_ocr(_pagina(800, 1000))))
    assert pequena.mode == "L" and max(pequena.size) == 2000
    gigante = Image.open(io.BytesIO(preparar_para_ocr(Image.new("RGB", (6000, 4000), "white"))))
    assert max(gigante.size) == 4000


def test_sem_tesseract_instalado_o_erro_diz_o_que_fazer():
    with pytest.raises(OcrError) as e:
        MotorTesseract(executavel="tesseract-que-nao-existe").reconhecer(_pagina())
    assert (e.value.code, e.value.status) == ("OCR_ENGINE_UNAVAILABLE", 503)
    assert "digite" in str(e.value).lower()


# ---------- serviço ----------

def test_servico_devolve_o_formato_do_upload_mais_ocr_e_analise_visual():
    r = extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso(TEXTO_PROVA))
    assert r["status"] == "success"
    assert r["raw_text"] == TEXTO_PROVA
    assert r["metadata"]["source_type"] == "image"
    assert r["metadata"]["char_count"] == len(TEXTO_PROVA)
    assert r["ocr"] == {"confianca_media": 90.0, "palavras_reconhecidas": len(TEXTO_PROVA.split()), "avisos": []}
    assert r["analise_visual"]["indicador_poluicao"] is False
    assert r["analise_visual"]["mensagem"] is None
    assert r["imagem"] == {"formato": "png", "largura": 1240, "altura": 1754}


def test_dados_pessoais_lidos_na_imagem_saem_como_marcador():
    texto = TEXTO_PROVA + " Aluno: Pedro, CPF 123.456.789-09, telefone (61) 99999-1234, mae maria@escola.example"
    r = extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso(texto))
    for bruto in ("123.456.789-09", "99999-1234", "maria@escola.example"):
        assert bruto not in r["raw_text"]
    assert r["metadata"]["sanitized"] is True and r["metadata"]["pii_removed_count"] >= 3


def test_confianca_baixa_avisa_e_muito_baixa_recusa():
    r = extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso(TEXTO_PROVA, confianca=CONFIANCA_REVISAR - 5))
    assert [a["code"] for a in r["ocr"]["avisos"]] == ["LOW_CONFIDENCE"]
    with pytest.raises(OcrError) as e:
        extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso(TEXTO_PROVA, confianca=CONFIANCA_MINIMA - 5))
    assert (e.value.code, e.value.status) == ("ILLEGIBLE_TEXT", 422)


def test_sem_texto_reconhecido_e_texto_curto_demais():
    with pytest.raises(OcrError) as e:
        extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso("", palavras=0))
    assert e.value.code == "NO_TEXT_DETECTED"
    with pytest.raises(OcrError) as e:
        extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso("Prova de ciencias do oitavo ano"))
    assert e.value.code == "TEXT_TOO_SHORT"


def test_imagem_invalida_nem_chega_ao_motor():
    motor = MotorFalso(TEXTO_PROVA)
    with pytest.raises(OcrError):
        extrair_texto_da_imagem(_bytes(_pagina(300, 300)), motor)
    assert motor.chamadas == 0


def test_prova_poluida_emite_indicador_e_ainda_extrai_o_texto():
    r = extrair_texto_da_imagem(_bytes(_carregada()), MotorFalso(TEXTO_PROVA))
    assert r["analise_visual"]["indicador_poluicao"] is True
    assert "elementos visuais concorrentes" in r["analise_visual"]["mensagem"]
    assert r["raw_text"] == TEXTO_PROVA


def test_texto_da_imagem_alimenta_o_decompositor_estrutural():
    from iris.parsers.structural_decomposer import decompose_material

    prova = (
        "1. Um instituto de pesquisa constatou que o crescimento foi de 135,25 por cento. Qual e a taxa decimal?\n"
        "a) 13 525,0\nb) 135,25\nc) 1,3525\n\n"
        "2. Em quantos metros quadrados a area do campo foi reduzida depois da reforma?\na) 24\nb) 35\nc) 555"
    )
    r = extrair_texto_da_imagem(_bytes(_pagina()), MotorFalso(prova))
    # O OCR só entrega texto bruto; quem acha as questões é o decompositor, igual para um .txt (DEP-OC-01).
    assert len(decompose_material(r["raw_text"]).questions) == 2


# ---------- acurácia com o Tesseract de verdade ----------

def _acuracia(lido: str, esperado: str) -> float:
    import difflib
    import re

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.lower()).strip()

    return difflib.SequenceMatcher(None, norm(lido), norm(esperado)).ratio()


@pytest.mark.skipif(not TEM_TESSERACT, reason="Tesseract não instalado")
@pytest.mark.parametrize("largura,altura,minimo", [(1240, 1754, 0.93), (1000, 1414, 0.90), (700, 990, 0.85)])
def test_acuracia_do_ocr_em_resolucoes_diferentes(largura, altura, minimo):
    r = extrair_texto_da_imagem(_bytes(_pagina(largura, altura)))
    esperado = " ".join(PROVA * 3)
    assert r["ocr"]["confianca_media"] >= CONFIANCA_MINIMA
    assert _acuracia(r["raw_text"], esperado) >= minimo, r["raw_text"][:300]


@pytest.mark.skipif(not TEM_TESSERACT, reason="Tesseract não instalado")
def test_acuracia_com_jpeg_comprimido_e_ruido():
    im = _pagina()
    ruido = Image.effect_noise(im.size, 18).convert("RGB")
    sujo = Image.blend(im, ruido, 0.12)
    r = extrair_texto_da_imagem(_bytes(sujo, "JPEG", quality=55))
    assert _acuracia(r["raw_text"], " ".join(PROVA * 3)) >= 0.85


# ---------- rota ----------

@pytest.fixture()
def cliente():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    pytest.importorskip("multipart")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from iris.api.routes.ocr import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _enviar(cliente, dados: bytes, nome="prova.png", tipo="image/png"):
    return cliente.post("/api/v1/materials/ocr", files={"file": (nome, dados, tipo)})


def test_rota_devolve_texto_analise_e_no_store(cliente):
    definir_motor(MotorFalso(TEXTO_PROVA))
    r = _enviar(cliente, _bytes(_pagina()))
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    corpo = r.json()
    assert corpo["raw_text"] == TEXTO_PROVA and corpo["metadata"]["source_type"] == "image"
    assert corpo["analise_visual"]["nivel"] == "baixa"


@pytest.mark.parametrize(
    "dados,code,status",
    [
        (b"%PDF-1.7 ...", "UNSUPPORTED_IMAGE_FORMAT", 415),
        (b"", "EMPTY_IMAGE", 422),
    ],
)
def test_rota_recusas_com_codigo_e_mensagem(cliente, dados, code, status):
    r = _enviar(cliente, dados)
    assert r.status_code == status
    detalhe = r.json()["detail"]
    assert detalhe["code"] == code and detalhe["detail"]
    assert r.headers["cache-control"] == "no-store"


def test_rota_imagem_ilegivel_diz_o_motivo(cliente):
    r = _enviar(cliente, _bytes(_pagina().filter(ImageFilter.GaussianBlur(4))))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "IMAGE_TOO_BLURRY"
    assert "desfocada" in r.json()["detail"]["detail"]


def test_rota_corpo_acima_do_limite_e_recusado_com_413(cliente):
    r = _enviar(cliente, b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_BYTES + 100_000))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "IMAGE_TOO_LARGE"


def test_rota_sem_campo_file_e_corpo_nao_multipart(cliente):
    assert cliente.post("/api/v1/materials/ocr", files={"outro": ("a.png", b"x", "image/png")}).status_code == 422
    r = cliente.post("/api/v1/materials/ocr", json={"file": "x"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_BODY"


def test_rota_motor_ausente_responde_503(cliente):
    definir_motor(MotorTesseract(executavel="tesseract-que-nao-existe"))
    r = _enviar(cliente, _bytes(_pagina()))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "OCR_ENGINE_UNAVAILABLE"


def test_imagem_de_foto_grande_nao_vai_para_arquivo_temporario(cliente, monkeypatch):
    import tempfile

    def proibido(self, *a, **k):  # o UploadFile padrão gravaria em disco acima de 1 MB
        raise AssertionError("a imagem foi gravada em arquivo temporário")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", proibido)
    definir_motor(MotorFalso(TEXTO_PROVA))
    ruido = Image.effect_noise((1600, 1600), 80).convert("RGB")
    grande = _bytes(ruido)  # PNG de ruído: mais de 1 MB
    assert len(grande) > 1_000_000
    assert _enviar(cliente, grande).status_code in (200, 422)  # lida em memória; pode cair na validação de legibilidade


@pytest.mark.skipif(not TEM_TESSERACT, reason="Tesseract não instalado")
def test_rota_de_ponta_a_ponta_com_tesseract(cliente):
    r = _enviar(cliente, _bytes(_pagina()))
    assert r.status_code == 200
    assert "crescimento" in r.json()["raw_text"].lower()
