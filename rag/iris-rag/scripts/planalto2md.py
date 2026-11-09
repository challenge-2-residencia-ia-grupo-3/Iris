# uso: uv run --with beautifulsoup4 python scripts/planalto2md.py entrada.html saida.md [ini_regex fim_regex]...
# Texto de lei do Planalto (compilado): remove trechos revogados (<strike> e estilo line-through),
# normaliza quebras de linha e, se pedido, recorta faixas de artigos (pares regex inicio / regex fim exclusivo).
import sys, re, json
from bs4 import BeautifulSoup

src, dst, *faixas = sys.argv[1:]
raw = open(src, "rb").read()
try:
    html = raw.decode("utf-8")
except UnicodeDecodeError:
    html = raw.decode("cp1252")
soup = BeautifulSoup(html, "html.parser")   # html.parser tolera o HTML quebrado do Planalto
for t in soup(["script", "style", "strike", "s", "del"]):
    t.decompose()
for t in soup.find_all(style=re.compile(r"line-through", re.I)):
    t.decompose()
title = soup.title.get_text(strip=True) if soup.title else ""
txt = soup.get_text(" ")
txt = re.sub(r"\s+", " ", txt).strip()
# reconstroi estrutura: quebra antes de dispositivos legais
txt = re.sub(r"\s*\b(Art\. \d+[º°o]?(?:-[A-Z])?\.?)\s", r"\n\n\1 ", txt)
txt = re.sub(r"\s*(§ ?\d+ ?[º°o]?|Parágrafo único)", r"\n\1", txt)
txt = re.sub(r"\s+([IVXL]{1,6} ?[-–] )", r"\n\1", txt)
txt = re.sub(r"\s+([a-z]\) )", r"\n\1", txt)
txt = re.sub(r"\s+(CAPÍTULO|Capítulo|SEÇÃO|Seção|TÍTULO|Título) ", r"\n\n\1 ", txt)
txt = re.sub(r"(\d) o\b", r"\1º", txt)   # 'Art. 1 o' -> 'Art. 1º'
txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
cab = txt[:1500]
if faixas:
    blocos = []
    for ini, fim in zip(faixas[::2], faixas[1::2]):
        m1 = re.search(ini, txt, re.M)
        m2 = re.search(fim, txt[m1.end():], re.M) if m1 else None
        if not m1 or not m2:
            raise SystemExit(f"faixa nao encontrada: {ini} .. {fim}")
        blocos.append(txt[m1.start(): m1.end() + m2.start()].strip())
    corpo = "\n\n[...]\n\n".join(blocos)
    m = re.search(r"(DECRETO-LEI|LEI) N[ºo°][^\n]*?\d{4}\.?", cab)
    head = m.group(0) if m else title
    txt = f"{head}\n(Recorte: somente os artigos abaixo; texto compilado vigente; trechos revogados removidos)\n\n{corpo}"
out = f"# {title}\n\n{txt}\n"
open(dst, "w", encoding="utf-8").write(out)
print(json.dumps({"chars": len(out), "titulo": title}, ensure_ascii=False))
