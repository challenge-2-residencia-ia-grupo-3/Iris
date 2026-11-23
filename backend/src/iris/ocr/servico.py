"""Orquestra a leitura de uma prova digitalizada (História 1.1.3, RF-03).

Ordem fixa: valida a imagem, mede a poluição visual, lê o texto (OCR local), sanitiza PII (RNF-02) e valida o texto
como qualquer outro material. A imagem e o texto bruto vivem só nas variáveis desta chamada: nada vai a disco,
banco ou log (RNF-01).

Contrato de ingestão (DEP-OC-01): o OCR só extrai texto bruto. Cabeçalho, enunciados e listas continuam por conta do
decompositor estrutural (#5/#53), que recebe este texto como recebe o de um .txt.
"""
from __future__ import annotations

from typing import Any

from iris.ocr.erros import OcrError
from iris.ocr.motor import IDIOMA_PADRAO, MotorOcr, obter_motor
from iris.ocr.validacao import validar_imagem
from iris.ocr.visual import AnaliseVisual, analisar_poluicao_visual
from iris.schemas.materials import (
    MIN_MATERIAL_CHARS,
    MaterialMetadata,
    MaterialResponse,
    MaterialSourceType,
    MaterialValidationError,
    validate_material_content,
)
from iris.security.operational_logger import sentinel_context
from iris.security.pii_scrubber import sanitize_pii

CONFIANCA_MINIMA = 45.0  # abaixo disso o texto lido é lixo: a imagem é recusada
CONFIANCA_REVISAR = 70.0  # abaixo disso o professor é avisado para conferir com a prova na mão
MIN_PALAVRAS = 5

AVISO_REVISAR = (
    "Algumas palavras podem ter sido lidas errado. Confira o texto com a prova na mão antes de prosseguir."
)


def _mensagem_visual(analise: AnaliseVisual) -> str | None:
    if not analise.indicador_poluicao:
        return None
    motivo = f" ({'; '.join(analise.motivos)})" if analise.motivos else ""
    return (
        f"Esta prova tem muitos elementos visuais concorrentes{motivo}. Isso pode competir com a leitura do texto: "
        "confira o layout ao revisar a adaptação."
    )


def extrair_texto_da_imagem(dados: bytes, motor: MotorOcr | None = None, idioma: str = IDIOMA_PADRAO) -> dict[str, Any]:
    imagem = validar_imagem(dados)
    analise = analisar_poluicao_visual(imagem.imagem)
    resultado = (motor or obter_motor()).reconhecer(imagem.imagem, idioma)
    if not resultado.texto.strip() or resultado.palavras < MIN_PALAVRAS:
        raise OcrError(
            "Não foi possível reconhecer texto nesta imagem. Confira se a foto mostra a prova de frente, inteira e "
            "sem sombras, ou digite o texto.",
            "NO_TEXT_DETECTED",
            422,
        )
    if resultado.confianca_media < CONFIANCA_MINIMA:
        raise OcrError(
            "O texto da imagem está ilegível para a leitura automática (letras muito pequenas, manchadas ou "
            "inclinadas). Tire a foto de novo, mais de perto e com a folha reta, ou digite o texto.",
            "ILLEGIBLE_TEXT",
            422,
        )
    avisos: list[dict[str, str]] = []
    if resultado.confianca_media < CONFIANCA_REVISAR:
        avisos.append({"code": "LOW_CONFIDENCE", "detail": AVISO_REVISAR})
    with sentinel_context(resultado.texto):
        sanitizado, pii = sanitize_pii(resultado.texto)
        try:
            caracteres, palavras = validate_material_content(sanitizado)
        except MaterialValidationError as err:
            if err.code == "TEXT_TOO_SHORT" or len(sanitizado.strip()) < MIN_MATERIAL_CHARS:
                raise OcrError(
                    f"O texto lido na imagem é curto demais ({len(sanitizado.strip())} caracteres; o mínimo é "
                    f"{MIN_MATERIAL_CHARS}). Envie a página inteira da prova ou digite o texto.",
                    "TEXT_TOO_SHORT",
                    422,
                ) from err
            raise OcrError(err.message, err.code, 422) from err
    resposta = MaterialResponse(
        status="success",
        message="Imagem lida em memória: confira o texto extraído antes de prosseguir.",
        raw_text=sanitizado,
        metadata=MaterialMetadata(
            source_type=MaterialSourceType.IMAGE.value,
            char_count=caracteres,
            word_count=palavras,
            sanitized=pii > 0,
            pii_removed_count=pii,
            filename=None,
        ),
    ).model_dump()
    resposta["ocr"] = {
        "confianca_media": round(resultado.confianca_media, 1),
        "palavras_reconhecidas": resultado.palavras,
        "avisos": avisos,
    }
    resposta["analise_visual"] = analise.to_dict() | {"mensagem": _mensagem_visual(analise)}
    resposta["imagem"] = {"formato": imagem.formato, "largura": imagem.largura, "altura": imagem.altura}
    return resposta
