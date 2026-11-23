"""Motor de OCR local (História 1.1.3). O padrão é o Tesseract, chamado como processo filho.

Zero-retention (RNF-01): a imagem entra pela entrada padrão e o texto sai pela saída padrão, sem arquivo temporário
e sem serviço externo. O motor é trocável (`definir_motor`), como o transcritor de áudio.

O Tesseract é um programa do sistema, não um pacote Python:
    macOS:   brew install tesseract tesseract-lang
    Ubuntu:  sudo apt-get install tesseract-ocr tesseract-ocr-por
Variáveis: IRIS_OCR_BIN (caminho do executável), IRIS_OCR_LANG (padrão "por"), IRIS_OCR_TIMEOUT (segundos, padrão 90).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from iris.ocr.erros import OcrError

IDIOMA_PADRAO = "por"
TIMEOUT_PADRAO = 90.0
LADO_IDEAL = 2000  # o Tesseract lê melhor com letras de ~30 px; fotos pequenas são ampliadas até aqui
LADO_MAXIMO = 4000  # fotos maiores são reduzidas: mais pixels só deixam o OCR lento


@dataclass(frozen=True)
class ResultadoOcr:
    texto: str
    confianca_media: float  # 0..100, média das palavras reconhecidas; 0 quando não há palavra
    palavras: int


class MotorOcr(Protocol):
    def reconhecer(self, imagem: Image.Image, idioma: str) -> ResultadoOcr: ...


def preparar_para_ocr(imagem: Image.Image) -> bytes:
    """Escala de cinza, contraste automático e tamanho adequado, devolvido como PNG em memória."""
    from PIL import ImageOps

    g = ImageOps.autocontrast(imagem.convert("L"), cutoff=1)
    maior = max(g.size)
    if maior < LADO_IDEAL:
        fator = min(2.0, LADO_IDEAL / maior)
    elif maior > LADO_MAXIMO:
        fator = LADO_MAXIMO / maior
    else:
        fator = 1.0
    if abs(fator - 1.0) > 0.01:
        g = g.resize((round(g.width * fator), round(g.height * fator)), Image.LANCZOS)
    saida = io.BytesIO()
    g.save(saida, format="PNG")
    return saida.getvalue()


def interpretar_tsv(tsv: str) -> ResultadoOcr:
    """Reconstrói o texto (linhas e parágrafos) e a confiança média a partir da saída `tsv` do Tesseract."""
    linhas: dict[tuple[int, int, int], list[str]] = {}
    ordem: list[tuple[int, int, int]] = []
    confs: list[float] = []
    for registro in tsv.splitlines()[1:]:
        c = registro.split("\t")
        if len(c) < 12 or c[0] != "5":  # nível 5 = palavra
            continue
        texto = c[11].strip()
        try:
            conf = float(c[10])
            chave = (int(c[2]), int(c[3]), int(c[4]))
        except ValueError:
            continue
        if not texto or conf < 0:
            continue
        if chave not in linhas:
            linhas[chave] = []
            ordem.append(chave)
        linhas[chave].append(texto)
        confs.append(conf)
    saida: list[str] = []
    anterior: tuple[int, int] | None = None
    for chave in ordem:
        bloco_par = chave[:2]
        if anterior is not None and bloco_par != anterior:
            saida.append("")  # parágrafo novo
        saida.append(" ".join(linhas[chave]))
        anterior = bloco_par
    media = sum(confs) / len(confs) if confs else 0.0
    return ResultadoOcr("\n".join(saida).strip(), media, len(confs))


class MotorTesseract:
    def __init__(self, executavel: str | None = None, timeout: float | None = None) -> None:
        self._executavel = executavel or os.environ.get("IRIS_OCR_BIN") or "tesseract"
        self._timeout = timeout if timeout is not None else float(os.environ.get("IRIS_OCR_TIMEOUT", TIMEOUT_PADRAO))

    def _caminho(self) -> str:
        caminho = shutil.which(self._executavel)
        if caminho is None:
            raise OcrError(
                "O reconhecimento de texto em imagens não está instalado neste servidor (falta o Tesseract). "
                "Digite ou cole o texto da prova, ou envie um arquivo .pdf, .docx ou .txt.",
                "OCR_ENGINE_UNAVAILABLE",
                503,
            )
        return caminho

    def reconhecer(self, imagem: Image.Image, idioma: str = IDIOMA_PADRAO) -> ResultadoOcr:
        idioma = os.environ.get("IRIS_OCR_LANG") or idioma
        png = preparar_para_ocr(imagem)
        try:
            proc = subprocess.run(
                [self._caminho(), "stdin", "stdout", "-l", idioma, "--psm", "3", "tsv"],
                input=png,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise OcrError(
                "A leitura da imagem demorou mais que o esperado. Tente uma imagem menor ou uma página por vez.",
                "OCR_TIMEOUT",
                504,
            ) from err
        if proc.returncode != 0:
            erro = proc.stderr.decode("utf-8", "replace")
            if "Failed loading language" in erro or "Error opening data file" in erro:
                raise OcrError(
                    f"O idioma '{idioma}' do Tesseract não está instalado (no macOS: brew install tesseract-lang).",
                    "OCR_LANGUAGE_UNAVAILABLE",
                    503,
                )
            raise OcrError("Não foi possível ler o texto desta imagem.", "OCR_FAILED", 422)
        return interpretar_tsv(proc.stdout.decode("utf-8", "replace"))


_motor: MotorOcr | None = None


def definir_motor(motor: MotorOcr | None) -> None:
    """Troca o motor (outro OCR, ou um falso nos testes). `None` volta ao Tesseract."""
    global _motor
    _motor = motor


def obter_motor() -> MotorOcr:
    return _motor or MotorTesseract()
