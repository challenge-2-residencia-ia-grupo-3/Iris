"""Análise heurística de poluição visual de uma prova digitalizada (História 1.1.3).

Mede o que concorre com o texto pela atenção do aluno: densidade de bordas, áreas coloridas e blocos da página
ocupados por traço. É uma heurística explicável, sem modelo de visão: o indicador é um AVISO ao professor (a Íris
adapta o layout na saída) e nunca bloqueia a leitura. Os limiares foram calibrados com páginas sintéticas, e ainda
não com provas reais; ver docs/ocr_materiais.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from iris.ocr.validacao import cinza_reduzido

GRADE = 8  # a página é dividida em GRADE x GRADE blocos
LIMIAR_BORDA = 0.12  # gradiente (0..1) a partir do qual um pixel conta como borda
BLOCO_OCUPADO = 0.02  # fração de borda a partir da qual um bloco conta como ocupado
SATURACAO_COLORIDA = 0.35  # saturação (0..1) a partir da qual o pixel conta como colorido

# Níveis: "alta" emite o indicador de poluição visual.
LIMIAR_ALTA = 0.55
LIMIAR_MEDIA = 0.25

# Peso de cada medida no escore 0..1. Cada medida é normalizada entre um valor "calmo" e um "carregado".
_FAIXAS = {
    "densidade_bordas": (0.12, 0.26, 0.40),  # (calmo, carregado, peso)
    "proporcao_colorida": (0.03, 0.22, 0.45),
    "cobertura_blocos": (0.85, 1.00, 0.15),
}


@dataclass(frozen=True)
class AnaliseVisual:
    densidade_bordas: float
    proporcao_colorida: float
    cobertura_blocos: float
    contraste: float
    escore: float
    nivel: str  # "baixa" | "media" | "alta"
    indicador_poluicao: bool
    motivos: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "nivel": self.nivel,
            "indicador_poluicao": self.indicador_poluicao,
            "escore": round(self.escore, 3),
            "densidade_bordas": round(self.densidade_bordas, 4),
            "proporcao_colorida": round(self.proporcao_colorida, 4),
            "cobertura_blocos": round(self.cobertura_blocos, 3),
            "contraste": round(self.contraste, 3),
            "motivos": list(self.motivos),
        }


def _normalizar(valor: float, calmo: float, carregado: float) -> float:
    if carregado <= calmo:
        return 0.0
    return float(min(1.0, max(0.0, (valor - calmo) / (carregado - calmo))))


def _bordas(cinza: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(cinza, axis=1))[:-1, :]
    gy = np.abs(np.diff(cinza, axis=0))[:, :-1]
    return np.maximum(gx, gy) > LIMIAR_BORDA


def _proporcao_colorida(im: Image.Image) -> float:
    hsv = np.asarray(im.convert("HSV").resize(_tamanho_reduzido(im)), dtype=np.float32) / 255.0
    s, v = hsv[..., 1], hsv[..., 2]
    return float(np.mean((s >= SATURACAO_COLORIDA) & (v >= 0.25)))


def _tamanho_reduzido(im: Image.Image, lado: int = 600) -> tuple[int, int]:
    fator = min(1.0, lado / max(im.size))
    return max(1, round(im.width * fator)), max(1, round(im.height * fator))


def _cobertura_blocos(bordas: np.ndarray) -> float:
    alt, larg = bordas.shape
    ocupados = 0
    for i in range(GRADE):
        for j in range(GRADE):
            bloco = bordas[i * alt // GRADE : (i + 1) * alt // GRADE, j * larg // GRADE : (j + 1) * larg // GRADE]
            if bloco.size and float(bloco.mean()) >= BLOCO_OCUPADO:
                ocupados += 1
    return ocupados / (GRADE * GRADE)


def analisar_poluicao_visual(im: Image.Image) -> AnaliseVisual:
    cinza = cinza_reduzido(im, 900)
    bordas = _bordas(cinza)
    densidade = float(bordas.mean())
    colorida = _proporcao_colorida(im)
    cobertura = _cobertura_blocos(bordas)
    contraste = float(np.percentile(cinza, 95) - np.percentile(cinza, 5))
    medidas = {"densidade_bordas": densidade, "proporcao_colorida": colorida, "cobertura_blocos": cobertura}
    escore = sum(_normalizar(medidas[k], f[0], f[1]) * f[2] for k, f in _FAIXAS.items())
    nivel = "alta" if escore >= LIMIAR_ALTA else "media" if escore >= LIMIAR_MEDIA else "baixa"
    motivos: list[str] = []
    if _normalizar(densidade, *_FAIXAS["densidade_bordas"][:2]) >= 0.7:
        motivos.append("muitos traços, bordas e detalhes competindo com o texto")
    if _normalizar(colorida, *_FAIXAS["proporcao_colorida"][:2]) >= 0.7:
        motivos.append("áreas coloridas extensas")
    if _normalizar(cobertura, *_FAIXAS["cobertura_blocos"][:2]) >= 0.9 and nivel != "baixa":
        motivos.append("elementos espalhados por quase toda a página")
    return AnaliseVisual(densidade, colorida, cobertura, contraste, escore, nivel, nivel == "alta", tuple(motivos))
