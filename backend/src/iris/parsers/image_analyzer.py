"""Módulo de análise visual de páginas e imagens pedagógicas (História 1.1.3 - RF-03).

Atende:
- RF-03: Extração multimodal de provas digitalizadas via OCR e análise visual.
- RNF-01: Processamento estritamente em memória volátil (Zero-Database).
- Apoio à revisão docente (HITL): fornece indicadores heurísticos de concentração visual
  e respiro sem produzir conclusões pedagógicas definitivas ou rótulos automáticos
  de inadequação do material.

Métricas e Fórmulas:
1. edge_density (Densidade de Bordas):
   - Proporção de pixels com transição de gradiente superior ao limiar configurado
     após aplicação do filtro ImageFilter.FIND_EDGES sobre a imagem em tons de cinza.
   - Fórmula: soma(gradiente >= edge_gradient_threshold) / total_pixels.
   - Escala: 0.0 a 1.0.
   - Limitação técnica: avalia transições espaciais de alta frequência; não distingue
     semântica de texto pedagógico, ilustrações úteis e ruído de escaneamento.

2. whitespace_ratio (Proporção de Pixels Claros):
   - Proporção de pixels com luminância superior ao limiar configurado (fundo claro).
   - Fórmula: soma(luminancia >= white_pixel_threshold) / total_pixels.
   - Escala: 0.0 a 1.0.
   - Limitação técnica: mede a claridade dos pixels da imagem, NÃO o espaço visual livre
     ou respiro semântico. Páginas com fundos coloridos, papel reciclado, molduras ou
     ilustrações amplas apresentam whitespace_ratio reduzido mesmo com boa diagramação.

3. contrast_ratio (Faixa Dinâmica Interpercentil):
   - Amplitude de luminância calculada pela diferença entre o percentil 95 (P95)
     e o percentil 5 (P5) normalizada por 255.
   - Fórmula: (P95 - P5) / 255.0.
   - Escala: 0.0 a 1.0.
   - Limitação técnica: robusto contra ruídos isolados (hot pixels/poeira), mas pode
     registrar valor moderado em páginas com fundos coloridos homogêneos e texto escuro.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Final, Optional

from iris.schemas.materials import PageVisualAnalysis, VisualAnalysisReport

# Formatos de imagem estritamente aceitos pela História 1.1.3 (RF-03)
OFFICIAL_SUPPORTED_IMAGE_FORMATS: Final[set[str]] = {"PNG", "JPEG", "JPG"}

# Importação defensiva do Pillow para ambientes com ou sem a biblioteca instalada
try:
    from PIL import Image, ImageFilter
    _HAS_PILLOW = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]
    _HAS_PILLOW = False


# ==============================================================================
# Exceções de Domínio de Análise Visual
# ==============================================================================

class ImageAnalysisError(ValueError):
    """Exceção base para falhas de análise de imagens pedagógicas."""

    def __init__(self, message: str, code: str = "IMAGE_ANALYSIS_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class EmptyImageError(ImageAnalysisError):
    """Lançado quando o conteúdo binário da imagem está vazio (0 bytes)."""

    def __init__(self, message: str = "O conteúdo binário da imagem está vazio (0 bytes).") -> None:
        super().__init__(message, code="EMPTY_IMAGE")


class ImageTooLargeError(ImageAnalysisError):
    """Lançado quando o tamanho em bytes ou o total de pixels excede os limites de segurança."""

    def __init__(self, message: str, code: str = "IMAGE_TOO_LARGE") -> None:
        super().__init__(message, code=code)


class CorruptedImageError(ImageAnalysisError):
    """Lançado quando o arquivo de imagem está corrompido ou possui dados ilegíveis."""

    def __init__(self, message: str, code: str = "CORRUPTED_IMAGE") -> None:
        super().__init__(message, code=code)


class InvalidImageDimensionsError(ImageAnalysisError):
    """Lançado quando a imagem possui dimensões zeradas ou negativas."""

    def __init__(self, message: str, code: str = "INVALID_DIMENSIONS") -> None:
        super().__init__(message, code=code)


class UnsupportedImageFormatError(ImageAnalysisError):
    """Lançado quando o formato da imagem não é suportado pela plataforma."""

    def __init__(self, message: str, code: str = "UNSUPPORTED_IMAGE_FORMAT") -> None:
        super().__init__(message, code=code)


class ImageDependencyError(ImageAnalysisError):
    """Lançado quando a biblioteca Pillow (PIL) não está instalada no ambiente."""

    def __init__(
        self,
        message: str = (
            "A biblioteca Pillow (PIL) não está instalada no ambiente. "
            "Adicione 'pillow>=10.0.0' às dependências para habilitar a análise visual."
        ),
        code: str = "LIBRARY_NOT_AVAILABLE",
    ) -> None:
        super().__init__(message, code=code)


# ==============================================================================
# Configuração Centralizada de Limiares e Segurança
# ==============================================================================

@dataclass(frozen=True)
class VisualClutterConfig:
    """Configurações e limiares heurísticos para análise visual de páginas didáticas.

    Centraliza todos os limites de processamento, mitigação de sobrecarga e limiares
    experimentais de classificação. Não contém números mágicos dispersos.
    """

    # Limites defensivos de segurança (DoS / Decompression Bomb mitigation)
    max_bytes: int = 25 * 1024 * 1024  # 25 MB (limite técnico de upload OCR)
    max_dimension_px: int = 10_000      # Dimensão máxima permitida em pixels (largura ou altura)
    min_dimension_px: int = 150         # Dimensão mínima segura para análise de página
    max_total_pixels: int = 25_000_000  # Máximo de pixels (ex.: 5.000 x 5.000)
    downscale_max_dimension: int = 2_000  # Redimensionamento defensivo para processamento em memória

    # Limiares de Densidade de Bordas (edge_density)
    edge_density_low: float = 0.08       # Concentração baixa de elementos gráficos
    edge_density_high: float = 0.22      # Concentração elevada de elementos visuais
    edge_gradient_threshold: int = 30    # Limiar de corte na escala 0..255 para binarização de borda

    # Limiares de Proporção de Pixels Claros (whitespace_ratio)
    white_pixel_threshold: int = 240     # Luminância mínima considerada fundo claro (0..255)
    whitespace_min_ok: float = 0.45      # Menos de 45% de pixels claros indica alta ocupação da página
    whitespace_high: float = 0.80        # Mais de 80% indica página predominantemente arejada

    # Limiares de Contraste e Legibilidade
    contrast_low_threshold: float = 0.25  # Faixa dinâmica interpercentil inferior a 25% de 255


# ==============================================================================
# Funções de Cálculo Matemático das Métricas
# ==============================================================================

def calculate_edge_density(gray_image: Any, config: VisualClutterConfig) -> float:
    """Calcula a densidade normalizada de bordas da imagem em tons de cinza.

    Retorna valor em [0.0, 1.0].
    """
    if _HAS_PILLOW and ImageFilter is not None:
        edge_img = gray_image.filter(ImageFilter.FIND_EDGES)
        hist = edge_img.histogram()
        edge_pixels = sum(hist[config.edge_gradient_threshold:])
        total_pixels = gray_image.width * gray_image.height
        if total_pixels <= 0:
            return 0.0
        return round(min(1.0, max(0.0, edge_pixels / total_pixels)), 4)
    raise ImageDependencyError()


def calculate_whitespace_ratio(gray_image: Any, config: VisualClutterConfig) -> float:
    """Calcula a proporção de pixels claros (luminância >= white_pixel_threshold).

    NOTA: Esta métrica avalia a proporção de pixels claros, servindo como aproximação
    computacional de fundo claro, e não como medida semântica absoluta de respiro visual.
    Retorna valor em [0.0, 1.0].
    """
    if _HAS_PILLOW:
        hist = gray_image.histogram()
        white_pixels = sum(hist[config.white_pixel_threshold:])
        total_pixels = gray_image.width * gray_image.height
        if total_pixels <= 0:
            return 0.0
        return round(min(1.0, max(0.0, white_pixels / total_pixels)), 4)
    raise ImageDependencyError()


def calculate_contrast_ratio(gray_image: Any) -> float:
    """Calcula a amplitude dinâmica interpercentil robusta (P95 - P5) / 255.0.

    Retorna valor em [0.0, 1.0].
    """
    if _HAS_PILLOW:
        hist = gray_image.histogram()
        total_pixels = gray_image.width * gray_image.height
        if total_pixels <= 0:
            return 0.0

        p5_target = 0.05 * total_pixels
        p95_target = 0.95 * total_pixels

        cumulative = 0
        p5 = 0
        p95 = 255

        for val, count in enumerate(hist):
            cumulative += count
            if cumulative >= p5_target and p5 == 0:
                p5 = val
            if cumulative >= p95_target:
                p95 = val
                break

        contrast = (p95 - p5) / 255.0
        return round(min(1.0, max(0.0, contrast)), 4)
    raise ImageDependencyError()


def classify_clutter(
    edge_density: float,
    whitespace_ratio: float,
    config: VisualClutterConfig,
) -> tuple[str, bool]:
    """Classifica heurísticamente a densidade visual da página.

    Esta classificação é estritamente indicativa para o docente, não rotulando
    o material pedagógico como 'inadequado' ou 'confuso'.

    Retorna:
        tuple[str, bool]: (clutter_level, possible_visual_clutter)
    """
    if edge_density > config.edge_density_high or (
        edge_density > 0.15 and whitespace_ratio < config.whitespace_min_ok
    ):
        level = "alta"
    elif edge_density < config.edge_density_low and whitespace_ratio >= 0.60:
        level = "baixa"
    else:
        level = "moderada"

    possible_clutter = level == "alta" and whitespace_ratio < config.whitespace_min_ok
    return level, possible_clutter


def determine_legibility_status(
    width: int,
    height: int,
    contrast_ratio: float,
    config: VisualClutterConfig,
) -> tuple[str, Optional[str]]:
    """Avalia indicadores técnicos básicos de legibilidade da página.

    Regras de Governança dos Campos (RNF-02 / RF-03):
    - 'low_resolution': quando as dimensões estiverem abaixo de min_dimension_px.
      Nesse caso de rejeição dimensional, rejection_reason registra a explicação técnica.
    - 'ok': quando os limites técnicos mínimos foram observados.
      Nesse caso, rejection_reason é rigorosamente None, pois não houve rejeição ou falha.
      NOTA: 'ok' significa unicamente que os indicadores técnicos básicos não detectaram
      uma limitação evidente, NÃO comprovando a legibilidade semântica ou pedagógica.
    - Contraste reduzido: registrado exclusivamente na métrica contrast_ratio e consolidado
      como observação orientativa em VisualAnalysisReport.notes, sem contaminar rejection_reason
      quando a página foi processada com sucesso.

    Retorna:
        tuple[str, Optional[str]]: (legibility_status, rejection_reason)
    """
    if width < config.min_dimension_px or height < config.min_dimension_px:
        return "low_resolution", (
            f"Dimensões da imagem ({width}x{height} px) inferiores ao limite mínimo técnico "
            f"recomendado ({config.min_dimension_px} px)."
        )

    # Quando status é 'ok', rejection_reason deve ser rigorosamente None
    return "ok", None


# ==============================================================================
# Função Principal de Análise de Página
# ==============================================================================

def analyze_page_image(
    image_input: bytes | Any,
    page_number: int = 1,
    page_type: str = "image",
    config: Optional[VisualClutterConfig] = None,
) -> PageVisualAnalysis:
    """Executa a análise visual por página de um documento pedagógico (História 1.1.3).

    Garante:
    1. Validação defensiva de entrada (bytes vazios, limites de tamanho e dimensões).
    2. Mitigação de vulnerabilidades de processamento (tamanho máximo de buffer e total de pixels).
    3. Preservação estrita das dimensões originais nos metadados retornados.
    4. Cálculo das métricas de densidade de bordas, proporção de pixels claros e amplitude de contraste.
    5. Produção de schema estruturado estritamente compatível com PageVisualAnalysis.

    Args:
        image_input: Fluxo de bytes da imagem ou instância compatível com PIL.Image.
        page_number: Número da página analisada (iniciando em 1).
        page_type: Tipo da página ("image", "scanned", "mixed" ou "textual").
        config: Configuração opcional de limiares técnicos.

    Returns:
        PageVisualAnalysis: Objeto estruturado com as métricas e indicadores heurísticos.

    Raises:
        EmptyImageError: Se o fluxo de bytes estiver vazio.
        ImageTooLargeError: Se o arquivo ou total de pixels exceder os limites configurados.
        CorruptedImageError: Se a imagem estiver corrompida ou não puder ser aberta.
        InvalidImageDimensionsError: Se a imagem possuir dimensões zeradas ou negativas.
        UnsupportedImageFormatError: Se o formato não for suportado.
        ImageDependencyError: Se o Pillow não estiver instalado.
    """
    cfg = config or VisualClutterConfig()

    # 1. Validação inicial de entrada vazia
    if image_input is None:
        raise EmptyImageError("Conteúdo da imagem não fornecido (None).")

    if isinstance(image_input, bytes):
        if len(image_input) == 0:
            raise EmptyImageError("O conteúdo binário da imagem está vazio (0 bytes).")
        if len(image_input) > cfg.max_bytes:
            raise ImageTooLargeError(
                f"O arquivo de imagem ({len(image_input) / (1024 * 1024):.1f} MB) excede o limite "
                f"máximo permitido de processamento ({cfg.max_bytes / (1024 * 1024):.0f} MB)."
            )

    # 2. Verificação de dependência Pillow
    if not _HAS_PILLOW or Image is None:
        raise ImageDependencyError()

    # 3. Abertura segura da imagem
    if isinstance(image_input, bytes):
        try:
            img = Image.open(io.BytesIO(image_input))
        except Exception as err:
            raise CorruptedImageError(f"Arquivo de imagem corrompido ou formato ilegível: {err}") from err

        # Validação estrita dos formatos oficiais da História 1.1.3 (PNG, JPG, JPEG)
        fmt = (img.format or "").upper()
        if fmt and fmt not in OFFICIAL_SUPPORTED_IMAGE_FORMATS:
            raise UnsupportedImageFormatError(
                f"Formato de imagem '{img.format}' não suportado. "
                f"Formatos oficiais aceitos: {', '.join(sorted(OFFICIAL_SUPPORTED_IMAGE_FORMATS))}."
            )
    else:
        # Caller forneceu instância compatível com PIL.Image
        img = image_input
        fmt = getattr(img, "format", None)
        if fmt and fmt.upper() not in OFFICIAL_SUPPORTED_IMAGE_FORMATS:
            raise UnsupportedImageFormatError(
                f"Formato de imagem '{fmt}' não suportado. "
                f"Formatos oficiais aceitos: {', '.join(sorted(OFFICIAL_SUPPORTED_IMAGE_FORMATS))}."
            )

    # 4. Validação de dimensões e total de pixels
    orig_width = int(img.width)
    orig_height = int(img.height)

    if orig_width <= 0 or orig_height <= 0:
        raise InvalidImageDimensionsError(
            f"Dimensões da imagem inválidas: {orig_width}x{orig_height} pixels."
        )

    if orig_width > cfg.max_dimension_px or orig_height > cfg.max_dimension_px:
        raise ImageTooLargeError(
            f"Dimensão da imagem ({max(orig_width, orig_height)} px) excede o limite máximo "
            f"permitido ({cfg.max_dimension_px} px)."
        )

    total_pixels = orig_width * orig_height
    if total_pixels > cfg.max_total_pixels:
        raise ImageTooLargeError(
            f"Total de pixels da imagem ({total_pixels}) excede o limite defensivo "
            f"de segurança ({cfg.max_total_pixels})."
        )

    # 5. Redimensionamento defensivo em cópia de processamento (preservando dimensões originais)
    if orig_width > cfg.downscale_max_dimension or orig_height > cfg.downscale_max_dimension:
        scale = min(
            cfg.downscale_max_dimension / orig_width,
            cfg.downscale_max_dimension / orig_height,
        )
        target_w = max(1, int(orig_width * scale))
        target_h = max(1, int(orig_height * scale))
        resample_filter = getattr(Image, "Resampling", Image).BILINEAR
        proc_img = img.resize((target_w, target_h), resample_filter)
    else:
        proc_img = img

    # 6. Conversão para escala de cinza e cálculo das métricas
    gray_img = proc_img.convert("L")
    edge_density = calculate_edge_density(gray_img, cfg)
    whitespace_ratio = calculate_whitespace_ratio(gray_img, cfg)
    contrast_ratio = calculate_contrast_ratio(gray_img)

    # 7. Classificação preliminar e status de legibilidade
    clutter_level, possible_clutter = classify_clutter(edge_density, whitespace_ratio, cfg)
    legibility_status, rejection_reason = determine_legibility_status(
        orig_width, orig_height, contrast_ratio, cfg
    )

    # 8. Emissão do contrato estruturado com dimensões originais preservadas
    return PageVisualAnalysis(
        page_number=page_number,
        page_type=page_type,
        width=orig_width,
        height=orig_height,
        edge_density=edge_density,
        whitespace_ratio=whitespace_ratio,
        contrast_ratio=contrast_ratio,
        clutter_level=clutter_level,
        possible_visual_clutter=possible_clutter,
        legibility_status=legibility_status,
        rejection_reason=rejection_reason,
    )


def consolidate_visual_report(
    analyses: list[PageVisualAnalysis],
    notes: Optional[str] = None,
    config: Optional[VisualClutterConfig] = None,
) -> VisualAnalysisReport:
    """Consolida uma lista de análises individuais por página em um VisualAnalysisReport.

    Args:
        analyses: Lista contendo o resultado PageVisualAnalysis de cada página analisada.
        notes: Observações adicionais opcionais para a interface docente.
        config: Configuração opcional contendo os limiares técnicos de referência.

    Returns:
        VisualAnalysisReport: Relatório consolidado com nível geral de complexidade e páginas sinalizadas.
    """
    if not analyses:
        return VisualAnalysisReport(
            overall_clutter_level="baixa",
            has_high_clutter=False,
            total_pages_analyzed=0,
            flagged_pages=[],
            pages=[],
            notes=notes or "Nenhuma página submetida para análise visual.",
        )

    cfg = config or VisualClutterConfig()
    has_high = any(p.clutter_level == "alta" for p in analyses)
    has_mod = any(p.clutter_level == "moderada" for p in analyses)
    overall_level = "alta" if has_high else ("moderada" if has_mod else "baixa")
    flagged = [p.page_number for p in analyses if p.possible_visual_clutter]

    auto_notes: list[str] = []
    if notes:
        auto_notes.append(notes)
    if has_high:
        auto_notes.append("Identificadas páginas com alta concentração de elementos visuais concorrentes.")

    low_contrast_pages = [p.page_number for p in analyses if p.contrast_ratio < cfg.contrast_low_threshold]
    if low_contrast_pages:
        auto_notes.append(
            f"Páginas com contraste global reduzido: {low_contrast_pages}. "
            f"Recomenda-se conferência visual docente sobre nitidez do texto."
        )

    consolidated_notes = " ".join(auto_notes) if auto_notes else None

    return VisualAnalysisReport(
        overall_clutter_level=overall_level,
        has_high_clutter=has_high,
        total_pages_analyzed=len(analyses),
        flagged_pages=flagged,
        pages=analyses,
        notes=consolidated_notes,
    )
