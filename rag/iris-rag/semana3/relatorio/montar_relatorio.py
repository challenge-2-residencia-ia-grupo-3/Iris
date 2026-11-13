"""montar_relatorio.py: gera relatorio.pdf a partir de relatorio.md (entrega da semana 3, 13/11/2026).

Mesmo modelo da entrega de 09/11 (ABNT NBR 10719, sumário com número de página em duas passagens,
impressão pelo Chrome em modo headless). Diferenças: roda no Windows e lê as páginas do PDF com o
PyMuPDF, no lugar do script em Swift.

Uso: python montar_relatorio.py        (precisa de mistune, pymupdf e do Google Chrome)
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import mistune
import pymupdf

AQUI = Path(__file__).resolve().parent
CHROME = os.environ.get("CHROME") or next(
    (c for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") if Path(c).exists()), "chrome")
TITULO = "Íris: LLM x RAG – relatório técnico da semana 3"

CSS = """
@page { size: A4; margin: 30mm 20mm 20mm 30mm; @bottom-right { content: counter(page); font: 9.5pt Helvetica, Arial, sans-serif; color: #374151; } }
@page :first { @bottom-right { content: none; } }
html { font-size: 11pt; }
body { font-family: 'Times New Roman', Times, serif; line-height: 1.38; color: #111827; margin: 0; }
h1, h2, h3 { font-family: 'Times New Roman', Times, serif; color: #000; line-height: 1.3; break-after: avoid; }
h1 { font-size: 12pt; font-weight: bold; margin: 20pt 0 9pt 0; }
h1.pre, h1.pos { text-align: center; }
h1.pre, h1.quebra, h1.pos { break-before: page; margin-top: 0; }
h2 { font-size: 11.5pt; font-weight: bold; margin: 14pt 0 6pt 0; }
h3 { font-size: 11pt; font-weight: normal; font-style: italic; margin: 12pt 0 5pt 0; }
p { margin: 0 0 7pt 0; text-align: justify; orphans: 3; widows: 3; }
p.alinea { margin: 0 0 3pt 14pt; text-indent: -14pt; padding-left: 14pt; }
ol, ul { margin: 0 0 7pt 0; padding-left: 20pt; }
li { margin-bottom: 3pt; text-align: justify; }
p.legenda { text-align: center; font-size: 10pt; margin: 12pt 0 4pt 0; break-after: avoid; }
p.fonte { text-align: left; font-size: 9pt; margin: 3pt 0 12pt 0; break-before: avoid; }
table { border-collapse: collapse; width: 100%; margin: 0; font-size: 9pt; line-height: 1.28; }
th { text-align: left; font-weight: bold; border-top: 1.2px solid #000; border-bottom: 0.8px solid #000; padding: 3.5pt 5pt; }
td { padding: 2.8pt 5pt; vertical-align: top; border-bottom: 0.4px solid #9ca3af; text-align: left; }
tr:last-child td { border-bottom: 1.2px solid #000; }
tr { break-inside: avoid; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.6pt; overflow-wrap: anywhere; }
pre { border: 0.6px solid #9ca3af; padding: 6pt 8pt; font-size: 8.6pt; line-height: 1.4; break-inside: avoid; white-space: pre-wrap; margin: 6pt 0 10pt 0; }
blockquote { margin: 4pt 0 8pt 14pt; padding-left: 8pt; border-left: 1.5px solid #9ca3af; font-size: 10pt; }
blockquote p { text-align: left; margin-bottom: 4pt; }
img { max-width: 100%; display: block; margin: 0 auto; break-inside: avoid; }
.capa { height: 244mm; display: flex; flex-direction: column; align-items: center; text-align: center; break-after: page; }
.capa p { text-align: center; margin: 0; }
.capa .inst { font-size: 12pt; font-weight: bold; line-height: 1.6; }
.capa .parceria { font-size: 11pt; margin-top: 3mm; }
.capa .autor { font-size: 12pt; margin-top: 26mm; }
.capa .titulo { font-size: 14pt; font-weight: bold; margin-top: 46mm; line-height: 1.5; max-width: 135mm; }
.capa .subtitulo { font-size: 12pt; margin-top: 8mm; }
.capa .local { font-size: 12pt; margin-top: auto; line-height: 1.6; }
.sumario { margin: 0; }
.sumario div { display: flex; align-items: baseline; margin: 0 0 4pt 0; font-size: 11pt; }
.sumario div.n2 { padding-left: 14pt; font-size: 10.5pt; }
.sumario .t { flex: 0 1 auto; }
.sumario .pontos { flex: 1 1 auto; border-bottom: 1px dotted #6b7280; margin: 0 4pt; transform: translateY(-3pt); }
.sumario .pg { flex: 0 0 auto; }
.refs p { text-align: left; margin-bottom: 9pt; line-height: 1.3; }
"""


def titulos_do_sumario(html: str) -> list[tuple[int, str]]:
    itens = []
    for nivel, classe, texto in re.findall(r"<h([12])(?: class=\"(\w+)\")?[^>]*>(.*?)</h\1>", html, re.S):
        texto = re.sub(r"<[^>]+>", "", texto).strip()
        if classe == "pre":
            continue
        if classe == "pos" or re.match(r"\d", texto):
            itens.append((int(nivel), texto))
    return itens


def html_do_relatorio(paginas: dict[str, int] | None) -> tuple[str, list[tuple[int, str]]]:
    md = (AQUI / "relatorio.md").read_text(encoding="utf-8")
    md = re.sub(r"(?m)^([a-z]\) .+)$", r"\1\n", md)
    corpo = mistune.create_markdown(escape=False, plugins=["table", "strikethrough"])(md)
    corpo = re.sub(r"<p>([a-z]\) )", r'<p class="alinea">\1', corpo)
    corpo = corpo.replace("<h1>1 INTRODUÇÃO</h1>", '<h1 class="quebra">1 INTRODUÇÃO</h1>')
    titulos = titulos_do_sumario(corpo)
    linhas = "".join(f'<div class="n{n}"><span class="t">{t}</span><span class="pontos"></span>'
                     f'<span class="pg">{(paginas or {}).get(t, "00")}</span></div>' for n, t in titulos)
    corpo = corpo.replace("<!-- SUMARIO -->", f'<div class="sumario">{linhas}</div>')
    html = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f"<title>{TITULO}</title><style>{CSS}</style></head><body>{corpo}</body></html>")
    return html, titulos


def imprimir_pdf(html: str) -> list[str]:
    (AQUI / "relatorio.html").write_text(html, encoding="utf-8")
    pdf = AQUI / "relatorio.pdf"
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    (AQUI / "relatorio.html").as_uri()], check=True, capture_output=True)
    with pymupdf.open(pdf) as doc:
        return [re.sub(r"\s+", "", p.get_text()) for p in doc]


def localizar(titulos: list[tuple[int, str]], paginas: list[str]) -> dict[str, int]:
    inicio = next(i for i, p in enumerate(paginas) if "SUMÁRIO" in p) + 1
    onde, atual = {}, inicio
    for _, t in titulos:
        alvo = re.sub(r"\s+", "", t)
        pagina = next((i for i in range(atual, len(paginas)) if alvo in paginas[i]), None)
        assert pagina is not None, f"título não localizado no PDF: {t}"
        onde[t], atual = pagina + 1, pagina
    return onde


def main() -> None:
    html, titulos = html_do_relatorio(None)
    paginas = localizar(titulos, imprimir_pdf(html))
    html, _ = html_do_relatorio(paginas)
    texto = imprimir_pdf(html)
    assert localizar(titulos, texto) == paginas, "o sumário mudou a paginação: rodar de novo"
    (AQUI / "relatorio.html").unlink()
    print(f"relatorio.pdf: {len(texto)} páginas, {len(titulos)} títulos no sumário")


if __name__ == "__main__":
    main()
