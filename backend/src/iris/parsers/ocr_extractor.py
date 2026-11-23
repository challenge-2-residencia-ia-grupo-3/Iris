"""Módulo wrapper de OCR e extração de texto para materiais pedagógicos (História 1.1.3 - RF-03).

Atende:
- RF-03: Extração multimodal de provas digitalizadas via OCR local e análise visual.
- RNF-01: Processamento estritamente em memória volátil (Zero-Database).
- Apoio à revisão docente (HITL): a transcrição gerada pelo OCR é heurística e probabilística,
  devendo ser apresentada ao professor para validação e edição antes de qualquer geração de andaimes.
  A pontuação de confiança ('conf') do Tesseract é uma estimativa heurística interna e NÃO uma
  probabilidade estatisticamente calibrada; palavras com baixa pontuação NUNCA são descartadas.
"""
from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Optional

from iris.schemas.materials import MAX_OCR_FILE_SIZE_BYTES

# Formatos de imagem estritamente aceitos pela História 1.1.3 (RF-03)
OFFICIAL_SUPPORTED_IMAGE_FORMATS: Final[set[str]] = {"PNG", "JPEG", "JPG"}

# Limite defensivo para mitigar DoS / Decompression Bomb ao processar imagens
# Alinhado rigorosamente a VisualClutterConfig.max_total_pixels de image_analyzer.py (25 MPixels)
MAX_IMAGE_PIXELS: Final[int] = 25_000_000

# Importação defensiva do Pillow
try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    _HAS_PIL = False

# Importação defensiva do pytesseract
try:
    import pytesseract
    _HAS_PYTESSERACT = True
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]
    _HAS_PYTESSERACT = False


# ==============================================================================
# Exceções de Domínio de OCR
# ==============================================================================

class OcrError(Exception):
    """Exceção base para falhas do mecanismo de OCR."""

    def __init__(self, message: str, code: str = "OCR_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class OcrDependencyError(OcrError):
    """Lançado quando uma dependência de software necessária não está instalada no ambiente."""

    def __init__(
        self,
        message: str = (
            "A biblioteca Python 'pytesseract' não está instalada no ambiente. "
            "Adicione 'pytesseract>=0.3.10' às dependências para habilitar a extração OCR."
        ),
        code: str = "OCR_DEPENDENCY_ERROR",
    ) -> None:
        super().__init__(message, code=code)


class OcrEngineNotFoundError(OcrError):
    """Lançado quando o executável local do Tesseract OCR não foi encontrado no sistema ou PATH."""

    def __init__(
        self,
        message: str = (
            "O executável do Tesseract OCR não foi localizado no sistema. "
            "Certifique-se de que o Tesseract esteja instalado localmente e configurado no PATH."
        ),
        code: str = "OCR_ENGINE_NOT_FOUND",
    ) -> None:
        super().__init__(message, code=code)


class OcrLanguageError(OcrError):
    """Lançado quando o modelo de idioma solicitado (ex.: 'por') não está disponível no Tesseract."""

    def __init__(
        self,
        message: str = (
            "O modelo de idioma solicitado não foi localizado nos dados de treinamento do Tesseract (tessdata)."
        ),
        code: str = "OCR_LANGUAGE_NOT_FOUND",
    ) -> None:
        super().__init__(message, code=code)


class OcrTimeoutError(OcrError):
    """Lançado quando a execução do OCR ultrapassa o tempo limite configurado."""

    def __init__(
        self,
        message: str = "O tempo limite para extração de OCR da página foi excedido.",
        code: str = "OCR_TIMEOUT",
    ) -> None:
        super().__init__(message, code=code)


class OcrImageError(OcrError):
    """Lançado quando a imagem de entrada é inválida, corrompida, vazia ou excede limites técnicos."""

    def __init__(self, message: str, code: str = "OCR_IMAGE_ERROR") -> None:
        super().__init__(message, code=code)


# ==============================================================================
# Contratos de Dados de OCR
# ==============================================================================

@dataclass(frozen=True)
class OcrConfig:
    """Configuração técnica para execução do Tesseract OCR local.

    Centraliza parâmetros operacionais, caminhos, limites temporais e heurísticas
    de pontuação sem dispersão de números mágicos.
    """

    lang: str = "por"
    tesseract_cmd: str | None = None
    timeout_seconds: float = 30.0
    min_confidence: float = 60.0
    psm: int = 3
    oem: int = 3
    tessdata_dir: str | None = None


@dataclass(frozen=True)
class OcrEnvironmentStatus:
    """Diagnóstico do ambiente de execução do Tesseract OCR local."""

    is_available: bool
    tesseract_version: str | None
    available_languages: tuple[str, ...]
    has_portuguese: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class OcrPageResult:
    """Resultado imutável da extração de texto por OCR em uma página pedagógica.

    Observações essenciais sobre governança e HITL:
    1. A pontuação 'confidence' é calculada exclusivamente sobre palavras com
       pontuações válidas (conf >= 0). Caso nenhuma palavra válida possua pontuação,
       o valor retornado é None, evitando confundir ausência de dados com confiança zero.
    2. O OCR é um mecanismo heurístico e probabilístico; 'confidence' não é probabilidade
       calibrada de acerto e nunca comprova fidedignidade textual nem fidelidade gramatical.
    3. Palavras com pontuação inferior a 'min_confidence' são contabilizadas em
       'low_confidence_word_count', mas NUNCA são descartadas do 'raw_text'.
    4. O resultado final deve ser submetido à revisão do professor antes de gerar andaimes.
    """

    page_number: int
    raw_text: str
    confidence: float | None
    word_count: int
    valid_confidence_count: int
    low_confidence_word_count: int
    has_text: bool
    language: str = "por"
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.page_number, int) or self.page_number < 1:
            raise ValueError("page_number must be an integer >= 1")
        if not isinstance(self.metadata, MappingProxyType):
            meta_dict = dict(self.metadata) if isinstance(self.metadata, Mapping) else {}
            object.__setattr__(self, "metadata", MappingProxyType(meta_dict))


# ==============================================================================
# Funções Principais de OCR
# ==============================================================================

def check_ocr_environment(config: OcrConfig | None = None) -> OcrEnvironmentStatus:
    """Verifica a disponibilidade do ambiente de execução do Tesseract OCR local.

    Inspeciona dinamicamente:
    - Se a biblioteca pytesseract está importável.
    - Se o binário do Tesseract responde no PATH (ou tesseract_cmd).
    - Se os modelos de idioma estão instalados, verificando especificamente o português ('por').

    Não utiliza cache global mutável, viabilizando execução segura em ambientes concorrentes
    e diagnósticos confiáveis em testes automatizados.
    """
    cfg = config or OcrConfig()
    issues: list[str] = []

    if not _HAS_PYTESSERACT or pytesseract is None:
        return OcrEnvironmentStatus(
            is_available=False,
            tesseract_version=None,
            available_languages=(),
            has_portuguese=False,
            issues=("A biblioteca Python 'pytesseract' não está instalada no ambiente.",),
        )

    original_cmd = pytesseract.pytesseract.tesseract_cmd
    if cfg.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd

    try:
        try:
            version_str = str(pytesseract.get_tesseract_version())
        except Exception as exc:
            issues.append(f"Tesseract OCR binary not found or not executable: {exc}")
            return OcrEnvironmentStatus(
                is_available=False,
                tesseract_version=None,
                available_languages=(),
                has_portuguese=False,
                issues=tuple(issues),
            )

        extra_config = f'--tessdata-dir "{cfg.tessdata_dir}"' if cfg.tessdata_dir else ""
        try:
            langs = tuple(pytesseract.get_languages(config=extra_config))
        except Exception as exc:
            langs = ()
            issues.append(f"Failed to query available Tesseract languages: {exc}")

        has_por = cfg.lang in langs
        if not has_por:
            issues.append(f"Requested language '{cfg.lang}' is not installed in Tesseract tessdata.")

        is_avail = len(issues) == 0
        return OcrEnvironmentStatus(
            is_available=is_avail,
            tesseract_version=version_str,
            available_languages=langs,
            has_portuguese=has_por,
            issues=tuple(issues),
        )
    finally:
        if cfg.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = original_cmd


def extract_text_from_page_image(
    image_input: bytes | Image.Image,
    *,
    page_number: int = 1,
    config: OcrConfig | None = None,
) -> OcrPageResult:
    """Extrai texto e estatísticas heurísticas de uma página pedagógica via Tesseract OCR local.

    Executa em passo único através de 'image_to_data', reconstruindo hierarquicamente
    parágrafos, linhas e palavras sem descartar nenhum termo reconhecido.

    Parâmetros:
    - image_input: bytes brutos da imagem codificada (PNG, JPEG, JPG) ou instância PIL.Image.Image.
    - page_number: índice da página (inteiro positivo >= 1).
    - config: configuração operacional do OCR (OcrConfig).

    Retorna:
    - OcrPageResult estruturado e imutável.
    """
    if not isinstance(page_number, int) or page_number < 1:
        raise ValueError("page_number must be an integer >= 1")

    if not _HAS_PYTESSERACT or pytesseract is None:
        raise OcrDependencyError()

    if not _HAS_PIL or Image is None:
        raise OcrDependencyError(
            message="A biblioteca Pillow (PIL) não está instalada no ambiente.",
            code="OCR_DEPENDENCY_ERROR",
        )

    cfg = config or OcrConfig()

    pil_img: Image.Image
    is_bytes_input = False

    if isinstance(image_input, bytes):
        is_bytes_input = True
        if len(image_input) == 0:
            raise OcrImageError("O conteúdo da imagem está vazio (0 bytes).", code="OCR_EMPTY_IMAGE")
        if len(image_input) > MAX_OCR_FILE_SIZE_BYTES:
            raise OcrImageError(
                f"O tamanho da imagem ({len(image_input)} bytes) excede o limite máximo permitido ({MAX_OCR_FILE_SIZE_BYTES} bytes).",
                code="OCR_IMAGE_SIZE_EXCEEDED",
            )
        try:
            stream = io.BytesIO(image_input)
            pil_img = Image.open(stream)
            raw_format = (pil_img.format or "").upper()
            if raw_format not in OFFICIAL_SUPPORTED_IMAGE_FORMATS:
                pil_img.close()
                raise OcrImageError(
                    f"Formato de imagem '{raw_format}' não suportado. Formatos aceitos: {sorted(OFFICIAL_SUPPORTED_IMAGE_FORMATS)}",
                    code="OCR_UNSUPPORTED_FORMAT",
                )
            width, height = pil_img.size
            if width <= 0 or height <= 0:
                pil_img.close()
                raise OcrImageError("Dimensões inválidas da imagem (largura e altura devem ser > 0).", code="OCR_INVALID_DIMENSIONS")
            total_pixels = width * height
            if total_pixels > MAX_IMAGE_PIXELS:
                pil_img.close()
                raise OcrImageError(
                    f"Total de pixels ({total_pixels}) excede o limite seguro ({MAX_IMAGE_PIXELS}).",
                    code="OCR_IMAGE_TOO_LARGE",
                )
            pil_img.load()
        except OcrImageError:
            raise
        except Exception as exc:
            raise OcrImageError(f"Arquivo de imagem corrompido ou ilegível: {exc}", code="OCR_CORRUPTED_IMAGE") from exc
    elif isinstance(image_input, Image.Image):
        pil_img = image_input
        width, height = pil_img.size
        if width <= 0 or height <= 0:
            raise OcrImageError("Dimensões inválidas da imagem (largura e altura devem ser > 0).", code="OCR_INVALID_DIMENSIONS")
        total_pixels = width * height
        if total_pixels > MAX_IMAGE_PIXELS:
            raise OcrImageError(
                f"Total de pixels ({total_pixels}) excede o limite seguro ({MAX_IMAGE_PIXELS}).",
                code="OCR_IMAGE_TOO_LARGE",
            )
    else:
        raise TypeError(f"image_input must be bytes or PIL.Image.Image, got {type(image_input).__name__}")

    # Heurística de baixa resolução: não aborta o OCR, mas emite aviso para auditoria pedagógica
    low_resolution_warning = bool(width < 150 or height < 150)

    # Conversão defensiva para escala de cinza ('L') para otimizar detecção de glifos no Tesseract
    gray_img: Image.Image = pil_img.convert("L") if pil_img.mode != "L" else pil_img

    tess_custom_args = f"--psm {cfg.psm} --oem {cfg.oem}"
    if cfg.tessdata_dir:
        tess_custom_args += f' --tessdata-dir "{cfg.tessdata_dir}"'

    original_cmd = pytesseract.pytesseract.tesseract_cmd
    if cfg.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd

    try:
        try:
            ocr_data = pytesseract.image_to_data(
                gray_img,
                lang=cfg.lang,
                config=tess_custom_args,
                timeout=cfg.timeout_seconds,
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrEngineNotFoundError(
                f"Tesseract OCR binary not found or not executable: {exc}",
                code="OCR_ENGINE_NOT_FOUND",
            ) from exc
        except pytesseract.TesseractError as exc:
            err_msg = str(exc)
            if "traineddata" in err_msg or "opening data file" in err_msg or "Failed loading language" in err_msg:
                raise OcrLanguageError(
                    f"Tesseract language model '{cfg.lang}' error: {err_msg}",
                    code="OCR_LANGUAGE_NOT_FOUND",
                ) from exc
            raise OcrError(f"Tesseract execution failed: {err_msg}", code="OCR_EXECUTION_ERROR") from exc
        except Exception as exc:
            exc_name = type(exc).__name__
            err_msg_lower = str(exc).lower()
            if (
                "timeout" in exc_name.lower()
                or isinstance(exc, TimeoutError)
                or "timeout" in err_msg_lower
            ):
                raise OcrTimeoutError(
                    f"OCR process timed out after {cfg.timeout_seconds}s.",
                    code="OCR_TIMEOUT",
                ) from exc
            raise OcrError(f"Erro inesperado durante processamento de OCR: {exc}", code="OCR_ERROR") from exc
    finally:
        if cfg.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = original_cmd
        if gray_img is not pil_img:
            try:
                gray_img.close()
            except Exception:
                pass
        if is_bytes_input:
            try:
                pil_img.close()
            except Exception:
                pass

    # ==============================================================================
    # Reconstrução Hierárquica e Apuração Estatística
    # ==============================================================================
    paragraphs: dict[tuple[int, int], dict[int, list[str]]] = {}
    word_count = 0
    valid_confidence_scores: list[float] = []
    low_confidence_word_count = 0

    raw_words = ocr_data.get("text", [])
    n_items = len(raw_words) if isinstance(raw_words, list) else 0

    for i in range(n_items):
        item_text = raw_words[i]
        token = str(item_text).strip() if item_text is not None else ""
        if not token:
            continue

        word_count += 1

        # Apuração da pontuação heurística de confiança
        conf_list = ocr_data.get("conf", [])
        conf_raw = conf_list[i] if isinstance(conf_list, list) and i < len(conf_list) else None
        conf_val: float | None = None
        try:
            if conf_raw is not None:
                conf_val = float(conf_raw)
        except (ValueError, TypeError):
            conf_val = None

        if conf_val is not None and conf_val >= 0.0:
            valid_confidence_scores.append(conf_val)
            if conf_val < cfg.min_confidence:
                low_confidence_word_count += 1

        # Reconstrução hierárquica por bloco, parágrafo e linha com fallback seguro
        block_list = ocr_data.get("block_num", [])
        par_list = ocr_data.get("par_num", [])
        line_list = ocr_data.get("line_num", [])

        try:
            block_num = int(block_list[i]) if isinstance(block_list, list) and i < len(block_list) else 0
        except (ValueError, TypeError):
            block_num = 0

        try:
            par_num = int(par_list[i]) if isinstance(par_list, list) and i < len(par_list) else 0
        except (ValueError, TypeError):
            par_num = 0

        try:
            line_num = int(line_list[i]) if isinstance(line_list, list) and i < len(line_list) else 0
        except (ValueError, TypeError):
            line_num = 0

        par_key = (block_num, par_num)
        if par_key not in paragraphs:
            paragraphs[par_key] = {}
        if line_num not in paragraphs[par_key]:
            paragraphs[par_key][line_num] = []
        paragraphs[par_key][line_num].append(token)

    # Montagem de texto preservando quebras de linha e separação entre parágrafos
    par_texts: list[str] = []
    for par_key in sorted(paragraphs.keys()):
        lines_dict = paragraphs[par_key]
        lines: list[str] = []
        for line_key in sorted(lines_dict.keys()):
            lines.append(" ".join(lines_dict[line_key]))
        par_texts.append("\n".join(lines))

    raw_text = "\n\n".join(par_texts) if par_texts else ""
    valid_conf_count = len(valid_confidence_scores)
    avg_confidence = (
        round(sum(valid_confidence_scores) / valid_conf_count, 2)
        if valid_conf_count > 0
        else None
    )
    has_text = bool(raw_text and raw_text.strip() and word_count > 0)

    metadata_dict: dict[str, Any] = {
        "width": width,
        "height": height,
        "low_resolution_warning": low_resolution_warning,
        "min_confidence_threshold": cfg.min_confidence,
        "valid_confidence_count": valid_conf_count,
        "low_confidence_word_count": low_confidence_word_count,
        "psm": cfg.psm,
        "oem": cfg.oem,
    }

    return OcrPageResult(
        page_number=page_number,
        raw_text=raw_text,
        confidence=avg_confidence,
        word_count=word_count,
        valid_confidence_count=valid_conf_count,
        low_confidence_word_count=low_confidence_word_count,
        has_text=has_text,
        language=cfg.lang,
        metadata=MappingProxyType(metadata_dict),
    )
