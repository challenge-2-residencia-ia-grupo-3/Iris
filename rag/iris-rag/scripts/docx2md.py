# uso: uv run --with python-docx python scripts/docx2md.py entrada.docx saida.md
# Converte .docx em markdown simples, na ordem do documento (paragrafos e tabelas intercalados).
# Titulos: estilos Heading N viram '#'; no texto completo CAST DUA 3.0 PT-BR (tudo estilo Normal)
# detecta por padrao: PRINCÍPIO -> '#', 'Diretriz N' -> '##', 'Ponto de verificação N.N:' -> '###'
# (so quando o paragrafo e estilo Normal; os da lista-resumo ficam como '- ').
# DOCX nao tem pagina fisica: nao ha marcador '=== p. N ==='; a citacao usa secao (diretriz/ponto).
import sys, re, json
import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

src, dst = sys.argv[1], sys.argv[2]
d = docx.Document(src)
out = []
vistos_pv = set()
for el in d.element.body.iterchildren():
    tag = el.tag.split('}')[1]
    if tag == 'tbl':
        t = Table(el, d)
        for row in t.rows:
            cells = []
            for c in row.cells:
                ct = re.sub(r"\s+", " ", c.text).strip()
                if ct and (not cells or cells[-1] != ct):   # celulas mescladas repetem texto
                    cells.append(ct)
            if cells:
                out.append("| " + " | ".join(cells) + " |")
        out.append("")
        continue
    if tag != 'p':
        continue
    p = Paragraph(el, d)
    t = re.sub(r"\s+", " ", p.text).strip()
    if not t:
        continue
    st = p.style.name if p.style is not None else ""
    m = re.match(r"Heading (\d)", st)
    if m:
        out.append("\n" + "#" * int(m.group(1)) + " " + t); continue
    if st == "Normal":
        if re.match(r"PRINC[ÍI]PIO\b", t):
            out.append("\n# " + t); continue
        if re.match(r"Diretriz \d+\b", t) and len(t) < 200:
            out.append("\n## " + t); continue
        if re.match(r"Ponto (?:de )?verifica[cç][aã]o (?:o )?\d+\.\d+", t) and len(t) < 250:
            out.append("\n### " + t); continue
        if t.isupper() and len(t) < 120:
            out.append("\n# " + t); continue
        out.append(t)
    else:
        out.append("- " + t)
txt = "\n".join(out)
txt = re.sub(r"\n{3,}", "\n\n", txt).strip() + "\n"
open(dst, "w", encoding="utf-8").write(txt)
print(json.dumps({"chars": len(txt), "titulos": sum(1 for l in txt.splitlines() if l.startswith("#")),
                  "tabelas": len(d.tables)}, ensure_ascii=False))
