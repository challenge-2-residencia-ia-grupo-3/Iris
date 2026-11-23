"""Validação da imagem de uma prova digitalizada (História 1.1.3).

A imagem é conferida pelos bytes (não pelo nome nem pelo Content-Type), decodificada só em memória e recusada, com o
motivo dito ao professor, quando é pequena demais, está desfocada, em branco ou escura demais para o OCR ler.
Metadados (EXIF, GPS) não passam adiante: o resto do pipeline recebe apenas os pixels.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from iris.ocr.erros import OcrError

MAX_BYTES = 10 * 1024 * 1024  # mesmo teto do upload de documentos (História 1.1.1)
MAX_PIXELS = 50_000_000  # recusa antes de decodificar: evita "bomba de descompressão"
MIN_LADO_MENOR = 400  # px
MIN_PIXELS = 400_000  # 0,4 megapixel

# Limiares do teste de legibilidade, em escala de cinza 0..1 e numa imagem reduzida a no máximo LADO_ANALISE px.
LADO_ANALISE = 1200
MIN_CONTRASTE = 0.06  # desvio-padrão da luminância; abaixo disso a página está em branco ou chapada
MIN_LUMINANCIA_MEDIA = 0.06  # abaixo: escura demais
MIN_NITIDEZ = 0.0008  # variância do laplaciano; abaixo disso as bordas das letras estão borradas

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


@dataclass(frozen=True)
class ImagemValidada:
    imagem: Image.Image  # RGB, orientação corrigida, sem metadados
    formato: str  # "png" | "jpeg"
    largura: int
    altura: int
    tamanho_bytes: int


def detectar_formato(dados: bytes) -> str | None:
    if dados.startswith(_PNG):
        return "png"
    if dados.startswith(_JPEG):
        return "jpeg"
    return None


def _para_rgb(im: Image.Image) -> Image.Image:
    """RGB só com os pixels: transparência vira fundo branco e EXIF/GPS/comentários não acompanham a imagem."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        fundo = Image.new("RGB", im.size, (255, 255, 255))
        fundo.paste(im, mask=im.getchannel("A"))
        im = fundo
    else:
        im = im.convert("RGB")
    return Image.frombytes("RGB", im.size, im.tobytes())


def cinza_reduzido(im: Image.Image, lado: int = LADO_ANALISE) -> np.ndarray:
    """Luminância 0..1 da imagem, reduzida para que as medidas não dependam do tamanho da foto."""
    g = im.convert("L")
    maior = max(g.size)
    if maior > lado:
        fator = lado / maior
        g = g.resize((max(1, round(g.width * fator)), max(1, round(g.height * fator))), Image.BILINEAR)
    return np.asarray(g, dtype=np.float32) / 255.0


def nitidez(cinza: np.ndarray) -> float:
    """Variância do laplaciano (borda das letras): cai quando a foto está tremida ou fora de foco."""
    c = cinza
    if c.shape[0] < 3 or c.shape[1] < 3:
        return 0.0
    lap = -4 * c[1:-1, 1:-1] + c[:-2, 1:-1] + c[2:, 1:-1] + c[1:-1, :-2] + c[1:-1, 2:]
    return float(lap.var())


def validar_imagem(dados: bytes) -> ImagemValidada:
    if not dados:
        raise OcrError("A imagem enviada está vazia (0 bytes). Selecione a foto ou o arquivo da prova.", "EMPTY_IMAGE", 422)
    if len(dados) > MAX_BYTES:
        raise OcrError(
            f"A imagem passa do limite de {MAX_BYTES // (1024 * 1024)} MB. Reduza a resolução da digitalização.",
            "IMAGE_TOO_LARGE",
            413,
        )
    formato = detectar_formato(dados)
    if formato is None:
        raise OcrError("Formato de imagem não aceito. Envie um arquivo .png ou .jpg.", "UNSUPPORTED_IMAGE_FORMAT", 415)
    try:
        im = Image.open(io.BytesIO(dados))
        largura, altura = im.size
        if largura * altura > MAX_PIXELS:
            raise OcrError(
                f"A imagem tem {largura}×{altura} px, acima do limite de {MAX_PIXELS // 1_000_000} megapixels. "
                "Reduza a resolução e envie de novo.",
                "IMAGE_TOO_LARGE",
                413,
            )
        im.load()  # imagem truncada ou corrompida falha aqui
        im = ImageOps.exif_transpose(im)  # foto de celular girada pelo EXIF
    except OcrError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as err:
        raise OcrError(
            "Não foi possível abrir a imagem: o arquivo está corrompido ou incompleto. Tire a foto ou digitalize de novo.",
            "CORRUPT_IMAGE",
            422,
        ) from err
    im = _para_rgb(im)
    largura, altura = im.size
    if min(largura, altura) < MIN_LADO_MENOR or largura * altura < MIN_PIXELS:
        raise OcrError(
            f"A imagem tem só {largura}×{altura} px: é pequena demais para ler o texto. São necessários pelo menos "
            f"{MIN_LADO_MENOR} px no lado menor e {MIN_PIXELS / 1_000_000:.1f} megapixel. Aproxime a câmera da folha "
            "ou digitalize com 200 dpi ou mais.",
            "IMAGE_RESOLUTION_TOO_LOW",
            422,
        )
    cinza = cinza_reduzido(im)
    if float(cinza.mean()) < MIN_LUMINANCIA_MEDIA:
        raise OcrError(
            "A imagem está escura demais para ler o texto. Fotografe com mais luz ou aumente o brilho da digitalização.",
            "IMAGE_TOO_DARK",
            422,
        )
    if float(cinza.std()) < MIN_CONTRASTE:
        raise OcrError(
            "A imagem está em branco ou sem contraste suficiente para distinguir o texto. Confira se a folha aparece "
            "inteira e se a digitalização não saiu apagada.",
            "IMAGE_NO_CONTRAST",
            422,
        )
    if nitidez(cinza) < MIN_NITIDEZ:
        raise OcrError(
            "A imagem está desfocada ou tremida e as letras não ficam legíveis. Tire a foto de novo, com a folha "
            "parada e a câmera focada.",
            "IMAGE_TOO_BLURRY",
            422,
        )
    return ImagemValidada(im, formato, largura, altura, len(dados))
