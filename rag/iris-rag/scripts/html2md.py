# uso: uv run --with beautifulsoup4 --with lxml python scripts/html2md.py entrada.html saida.md [seletor_css]
# Extrai o conteudo principal de paginas gov.br / Planalto / SBP para markdown simples.
import sys, re, json
from bs4 import BeautifulSoup

src, dst = sys.argv[1], sys.argv[2]
sel = sys.argv[3] if len(sys.argv) > 3 else None
raw = open(src, "rb").read()
for enc in ("utf-8", "cp1252", "latin-1"):
    try:
        html = raw.decode(enc); break
    except UnicodeDecodeError:
        continue
soup = BeautifulSoup(html, "lxml")
for t in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "iframe", "svg"]):
    t.decompose()
root = None
if sel:
    root = soup.select_one(sel)
if root is None:
    for s in ["#content-core", "#content", "article", "main", "#parent-fieldname-text", "body"]:
        root = soup.select_one(s)
        if root is not None and len(root.get_text(strip=True)) > 300:
            break
for s in root.select("strike, s, del"):   # Planalto: texto revogado vem riscado
    s.decompose()
out = []
for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "blockquote"]):
    if el.find_parent(["li", "tr"]) is not None and el.name in ("p", "li"):
        continue   # evita duplicar texto de listas aninhadas
    if el.name == "tr":
        cells = [c.get_text(" ", strip=True) for c in el.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            out.append("| " + " | ".join(cells) + " |")
        continue
    if el.find(["p", "li", "tr"]) is not None and el.name in ("blockquote",):
        continue
    t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
    if not t:
        continue
    if el.name.startswith("h"):
        out.append("\n" + "#" * int(el.name[1]) + " " + t)
    elif el.name == "li":
        out.append("- " + t)
    else:
        out.append(t)
title = soup.title.get_text(strip=True) if soup.title else ""
txt = f"# {title}\n\n" + "\n".join(out)
txt = re.sub(r"\n{3,}", "\n\n", txt)
open(dst, "w", encoding="utf-8").write(txt)
print(json.dumps({"chars": len(txt), "titulo": title}, ensure_ascii=False))
