# uso: uv run --with beautifulsoup4 --with lxml python scripts/cast_site2md.py pasta_html saida.md
# Junta as paginas do site CAST UDL Guidelines 3.0 (udlguidelines.cast.org) num markdown so,
# na ordem principio > diretriz > consideracao. Cada pagina vira um titulo com a URL de origem
# (linha 'Fonte: ...') para a etapa de chunking citar a consideracao/URL exata (HTML nao tem pagina).
# Conteudo: so #primaryContent (o organizador grafico repetido em todas as paginas e descartado).
import sys, os, re, json
from bs4 import BeautifulSoup

pasta, dst = sys.argv[1], sys.argv[2]
ORDEM = ["more__udl-goal", "more__about-guidelines-3-0",
         "engagement", "representation", "action-expression", "more__frequently-asked-questions"]
arqs = sorted(f for f in os.listdir(pasta) if f.endswith(".html"))

def chave(f):
    base = f[:-5]
    raiz = base.split("__")[0] if not base.startswith("more__") else base
    i = ORDEM.index(raiz) if raiz in ORDEM else 99
    return (i, base.count("__"), base)

def numero(titulo):
    m = re.search(r"(Guideline|Consideration)\s+(\d+(?:\.\d+)?)", titulo)
    return (m.group(1), m.group(2)) if m else (None, None)

# ordenar por principio e depois pelo numero da diretriz/consideracao
paginas = []
for f in arqs:
    s = BeautifulSoup(open(os.path.join(pasta, f), "rb").read(), "lxml")
    for t in s(["script", "style", "noscript"]):
        t.decompose()
    h1 = s.find("h1")
    titulo = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)) if h1 else f
    pr = s.select_one("#primaryContent")
    if pr is None:
        continue
    linhas = []
    for el in pr.find_all(["h2", "h3", "h4", "p", "li", "tr"]):
        if el.name in ("p", "li") and el.find_parent(["li", "tr"]) is not None:
            continue
        t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if not t:
            continue
        if el.name.startswith("h"):
            linhas.append("\n" + "#" * (int(el.name[1]) + 2) + " " + t)
        elif el.name == "li":
            linhas.append("- " + t)
        elif el.name == "tr":
            linhas.append("| " + " | ".join(c.get_text(" ", strip=True) for c in el.find_all(["td", "th"])) + " |")
        else:
            linhas.append(t)
    url = "https://udlguidelines.cast.org/" + f[:-5].replace("__", "/") + "/"
    tipo, num = numero(titulo)
    k = chave(f)
    numk = tuple(int(x) for x in num.split(".")) if num else (0,)
    paginas.append(((k[0], k[1] if tipo is None else (1 if tipo == "Guideline" else 2), numk, k[2]),
                    tipo, titulo, url, linhas))

def ordem_final(p):
    (i, nivel, numk, base) = p[0]
    # dentro de cada principio: pagina do principio, depois diretriz N seguida de suas consideracoes N.x
    if p[1] is None:
        return (i, 0, 0, 0, base)
    g = numk[0]
    return (i, 1, g, 0 if p[1] == "Guideline" else numk[1], base)

paginas.sort(key=ordem_final)
out = ["# CAST Universal Design for Learning Guidelines version 3.0 (texto do site udlguidelines.cast.org)", ""]
for _, tipo, titulo, url, linhas in paginas:
    nivel = {"Guideline": "###", "Consideration": "####"}.get(tipo, "##")
    out.append(f"\n{nivel} {titulo}")
    out.append(f"Fonte: {url}")
    out.extend(linhas)
txt = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
open(dst, "w", encoding="utf-8").write(txt)
print(json.dumps({"paginas_html": len(paginas), "chars": len(txt)}))
