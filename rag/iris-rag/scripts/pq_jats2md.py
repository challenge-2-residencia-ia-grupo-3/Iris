# uso: uv run --with beautifulsoup4 --with lxml python scripts/pq_jats2md.py entrada.xml saida.md
# Converte XML JATS (Europe PMC fullTextXML) em markdown: titulo, resumo, secoes (#), paragrafos, tabelas.
# Referencias bibliograficas sao omitidas (ruido para o RAG); legendas de figura/tabela mantidas.
import sys, re, json
from bs4 import BeautifulSoup

src, dst = sys.argv[1], sys.argv[2]
soup = BeautifulSoup(open(src, "rb").read(), "xml")
out = []
t = soup.find("article-title")
out.append("# " + re.sub(r"\s+", " ", t.get_text(" ", strip=True)) if t else "# (sem titulo)")
lic = soup.find("license")
if lic:
    out.append("Licença: " + re.sub(r"\s+", " ", lic.get_text(" ", strip=True)))
for ab in soup.find_all("abstract"):
    out.append("\n## Abstract")
    for p in ab.find_all("p"):
        out.append(re.sub(r"\s+", " ", p.get_text(" ", strip=True)))

body = soup.find("body")

def walk(el, depth):
    for ch in el.find_all(recursive=False):
        n = ch.name
        if n == "sec":
            ti = ch.find("title", recursive=False)
            if ti:
                out.append("\n" + "#" * min(depth, 6) + " " + re.sub(r"\s+", " ", ti.get_text(" ", strip=True)))
            walk(ch, depth + 1)
        elif n == "p":
            out.append(re.sub(r"\s+", " ", ch.get_text(" ", strip=True)))
        elif n in ("list",):
            for li in ch.find_all("list-item"):
                out.append("- " + re.sub(r"\s+", " ", li.get_text(" ", strip=True)))
        elif n in ("table-wrap", "fig"):
            cap = ch.find("caption")
            lab = ch.find("label")
            out.append("\n[" + (lab.get_text(strip=True) if lab else n) + "] " + (re.sub(r"\s+", " ", cap.get_text(" ", strip=True)) if cap else ""))
            for tr in ch.find_all("tr"):
                cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
                if any(cells):
                    out.append("| " + " | ".join(cells) + " |")
        elif n in ("disp-quote", "boxed-text"):
            walk(ch, depth)
        elif n == "title":
            continue
        else:
            txt = re.sub(r"\s+", " ", ch.get_text(" ", strip=True))
            if txt:
                out.append(txt)

if body:
    walk(body, 2)
txt = "\n".join(out)
txt = re.sub(r"\n{3,}", "\n\n", txt)
open(dst, "w", encoding="utf-8").write(txt)
print(json.dumps({"chars": len(txt), "secoes": txt.count("\n#"), "tem_body": body is not None}))
