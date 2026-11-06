# uso: uv run --with pymupdf python scripts/pdf2txt.py entrada.pdf saida.txt
# Extrai texto pagina a pagina com marcador '=== p. N ===' (N = pagina fisica do PDF, 1-based).
# Motor: PyMuPDF (pdftotext nao existe neste host; pypdf modo layout quebrava palavras).
import sys, json, re
import pymupdf

src, dst = sys.argv[1], sys.argv[2]
d = pymupdf.open(src)
parts, vazias, img_pages = [], [], []
for i, pg in enumerate(d, 1):
    t = pg.get_text("text")
    t = re.sub("\u00ad[ \t]*\n[ \t]*", "", t)  # hifen suave no fim da linha: junta a palavra
    t = t.replace("\u00ad", "")
    # hifenizacao comum de fim de linha entre minusculas ("necessá-\nrio" -> "necessário");
    # preserva "deve-\n-se" (hifen real repetido na linha seguinte)
    t = re.sub(r"([a-zà-ú])-\n(?!-)([a-zà-ú])", r"\1\2", t)
    # ligaduras fi/fl extraidas com espaco ("Verifi que" -> "Verifique"); nao existe palavra "fi"/"fl" em pt
    t = re.sub(r"(?<![^\W\d_])((?:[^\W\d_]*)f[il]) (?=[a-zà-ú])", r"\1", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) < 40:
        vazias.append(i)
        if pg.get_images():
            img_pages.append(i)
    parts.append(f"=== p. {i} ===\n{t}\n")
txt = "\n".join(parts)
open(dst, "w", encoding="utf-8").write(txt)
print(json.dumps({"paginas": d.page_count, "chars": len(txt),
                  "paginas_quase_vazias": vazias, "vazias_com_imagem": img_pages}))
