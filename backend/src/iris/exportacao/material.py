"""Exportação do material adaptado em PDF econômico e DOCX editável (História 2.2.3, RF-14).

O documento é feito para ser impresso e aplicado em sala:
- A4, só tons de cinza (nada de cor nem fundo escuro) e fonte sem serifa (Arial no DOCX, Helvetica-like no PDF);
- corpo em 12 pt, espaçamento 1,5 entre linhas e margens de 2,5 cm; sem caixas, tarjas nem imagens;
- cabeçalho genérico com campos em branco para o aluno preencher (nome e data). O servidor NUNCA escreve
  nome, rótulo clínico nem dado pessoal no cabeçalho: o título digitado passa pelo bloqueio clínico (#28)
  e pelo `sanitize_pii`, e é recusado se contiver qualquer um dos dois.

Sem estado (RNF-01): recebe o texto já aprovado, monta o arquivo em memória e devolve os bytes. Não grava
disco, banco nem cache. O corpo do texto NÃO é alterado: ele é o que o professor homologou. O que o servidor
faz com ele é apenas avisar (`verificar_material`) quando parece haver dado pessoal ou termo clínico.
"""
from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass
from typing import Any, Mapping

from iris.schemas.portable_profile import detectar_conteudo_clinico
from iris.security.pii_scrubber import sanitize_pii

FORMATOS = ("pdf", "docx")
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
TITULO_PADRAO = "Atividade adaptada"
MAX_TITULO = 120
MAX_TEXTO = 60_000
CAMPOS_ACEITOS = frozenset({"titulo", "texto"})
LINHA_ALUNO = "Nome: ______________________________________   Data: ____ / ____ / ________"


class ExportacaoMaterialError(ValueError):
    def __init__(self, mensagem: str, code: str, field: str) -> None:
        super().__init__(mensagem)
        self.code, self.field = code, field

    def to_dict(self) -> dict[str, str]:
        return {"detail": str(self), "code": self.code, "field": self.field}


@dataclass(frozen=True)
class MaterialValidado:
    titulo: str
    texto: str


@dataclass(frozen=True)
class ArquivoMaterial:
    nome: str
    media_type: str
    conteudo: bytes


# ---------------------------------------------------------------- validação
def validar_material(dados: Any) -> MaterialValidado:
    if not isinstance(dados, Mapping):
        raise ExportacaoMaterialError("O corpo deve ser um objeto com 'titulo' e 'texto'.", "INVALID_BODY", "corpo")
    extras = sorted(set(dados) - CAMPOS_ACEITOS)
    if extras:
        # Não ecoa o nome do campo: ele pode ser o próprio dado indevido.
        raise ExportacaoMaterialError(
            "Só 'titulo' e 'texto' são aceitos; outros campos não entram no documento.", "EXTRA_FIELD", "corpo"
        )

    texto = dados.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        raise ExportacaoMaterialError("O texto da atividade é obrigatório.", "EMPTY_TEXT", "texto")
    if len(texto) > MAX_TEXTO:
        raise ExportacaoMaterialError(f"O texto passa de {MAX_TEXTO} caracteres.", "TEXT_TOO_LONG", "texto")

    titulo = dados.get("titulo")
    if titulo is None or (isinstance(titulo, str) and not titulo.strip()):
        titulo = TITULO_PADRAO
    if not isinstance(titulo, str):
        raise ExportacaoMaterialError("O título deve ser um texto.", "INVALID_TITLE", "titulo")
    titulo = " ".join(titulo.split())
    if len(titulo) > MAX_TITULO:
        raise ExportacaoMaterialError(f"O título passa de {MAX_TITULO} caracteres.", "TITLE_TOO_LONG", "titulo")
    if detectar_conteudo_clinico(titulo, "titulo"):
        raise ExportacaoMaterialError(
            "O título não pode conter laudo, CID, diagnóstico ou medicação: o documento é entregue ao aluno.",
            "CLINICAL_LABEL_IN_HEADER",
            "titulo",
        )
    if sanitize_pii(titulo)[1] > 0:
        raise ExportacaoMaterialError(
            "O título não pode conter nome de aluno, escola, documento ou contato.", "PII_IN_HEADER", "titulo"
        )
    return MaterialValidado(titulo=titulo, texto=texto)


def verificar_material(dados: Any) -> dict[str, Any]:
    """Pré-checagem para a interface: valida o título (recusa) e avisa sobre o corpo (sem recusar nem alterar)."""
    material = validar_material(dados)
    clinicos = sorted({v.categoria for v in detectar_conteudo_clinico(material.texto, "texto")})
    return {
        "titulo": material.titulo,
        "possiveis_dados_pessoais": sanitize_pii(material.texto)[1],
        "categorias_clinicas_no_texto": clinicos,
        "pode_exportar": True,
    }


# ---------------------------------------------------------------- PDF econômico
_CSS = """
body { font-family: sans-serif; font-size: 12pt; line-height: 1.5; color: #111111; }
h1 { font-size: 16pt; font-weight: bold; margin: 0 0 10pt 0; }
p { margin: 0 0 8pt 0; }
p.aluno { margin: 0 0 16pt 0; font-size: 11pt; }
"""


def _paragrafos(texto: str) -> list[str]:
    blocos = re.split(r"\n\s*\n", texto.replace("\r\n", "\n").replace("\r", "\n").strip())
    return [b.strip("\n") for b in blocos if b.strip()]


def _html_pdf(material: MaterialValidado) -> str:
    partes = [f"<h1>{html.escape(material.titulo)}</h1>", f'<p class="aluno">{html.escape(LINHA_ALUNO)}</p>']
    for bloco in _paragrafos(material.texto):
        linhas = [html.escape(l.rstrip()) for l in bloco.split("\n")]
        partes.append("<p>" + "<br/>".join(linhas) + "</p>")
    return "".join(partes)


def material_para_pdf_bytes(material: MaterialValidado) -> bytes:
    try:
        import pymupdf
    except ImportError:  # versões antigas expõem apenas `fitz`
        import fitz as pymupdf  # type: ignore[no-redef]

    saida = io.BytesIO()
    story = pymupdf.Story(html=_html_pdf(material), user_css=_CSS)
    writer = pymupdf.DocumentWriter(saida)
    pagina = pymupdf.paper_rect("a4")
    area = pagina + (71, 71, -71, -71)  # margens de 2,5 cm
    mais = 1
    while mais:
        dev = writer.begin_page(pagina)
        mais, _ = story.place(area)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return saida.getvalue()


# ---------------------------------------------------------------- DOCX editável
def material_para_docx_bytes(material: MaterialValidado) -> bytes:
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.oxml.ns import qn
    from docx.shared import Cm, Mm, Pt, RGBColor

    doc = Document()
    secao = doc.sections[0]
    secao.page_width, secao.page_height = Mm(210), Mm(297)  # A4
    secao.left_margin = secao.right_margin = secao.top_margin = secao.bottom_margin = Cm(2.5)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    fmt = normal.paragraph_format
    fmt.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    fmt.space_after = Pt(8)

    titulo = doc.add_paragraph()
    run = titulo.add_run(material.titulo)
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0, 0, 0)

    aluno = doc.add_paragraph()
    aluno.add_run(LINHA_ALUNO).font.size = Pt(11)
    aluno.paragraph_format.space_after = Pt(16)

    for bloco in _paragrafos(material.texto):
        p = doc.add_paragraph()
        for i, linha in enumerate(bloco.split("\n")):
            if i:
                p.add_run().add_break()
            p.add_run(linha.rstrip())

    props = doc.core_properties  # o modelo do python-docx traz um autor próprio: não deixa metadado
    props.author = props.last_modified_by = props.comments = props.keywords = props.subject = ""
    props.title = material.titulo

    saida = io.BytesIO()
    doc.save(saida)
    return saida.getvalue()


def exportar_material(dados: Any, formato: str) -> ArquivoMaterial:
    """Valida o material aprovado e devolve o arquivo em memória."""
    if formato not in FORMATOS:
        raise ExportacaoMaterialError(
            f"Formato de exportação não suportado: use um de {', '.join(FORMATOS)}.", "UNSUPPORTED_EXPORT_FORMAT", "formato"
        )
    material = validar_material(dados)
    conteudo = material_para_pdf_bytes(material) if formato == "pdf" else material_para_docx_bytes(material)
    return ArquivoMaterial(nome=f"atividade-adaptada.{formato}", media_type=MEDIA_TYPES[formato], conteudo=conteudo)
