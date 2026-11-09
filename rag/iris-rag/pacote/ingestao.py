"""ingestao.py: do texto extraído (curadoria) aos trechos (chunks) prontos para indexar. Base do Íris.

Cada função é um passo do pipeline, na ordem em que roda:
    carregar_catalogo -> ler_texto -> limpar -> cortar -> gerar_metadados -> salvar_chunks

Entrada: ../fontes.json e ../texto/ (curadoria A-D; os PDFs têm o marcador '=== p. N ===';
         HTML, DOCX e PMC viraram markdown com títulos '#'; leis do Planalto têm um 'Art.' por linha).
Saída:   chunks.jsonl (um trecho por linha) e outputs/01-chunking.txt (relatório).

Rodar:  uv run --with numpy python ingestao.py
Nada aqui chama modelo nem internet.
"""
from __future__ import annotations

import json
import os
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BASE = Path(os.environ.get("RAG_BASE", AQUI.parent))      # pasta iris-rag (fontes.json, texto/)
SAIDA_CHUNKS = AQUI / "chunks.jsonl"
SAIDA_RELATORIO = AQUI / "outputs" / "01-chunking.txt"

# ---------------------------------------------------------------- parâmetros do chunking
MAX_PALAVRAS = 350      # seção maior que isso é dividida por parágrafo
MIN_PALAVRAS = 40       # pedaço menor que isso é juntado ao vizinho
SOBREPOSICAO_MAX = 60   # a sobreposição é o último parágrafo do trecho anterior, até ~15% de 350
SEMENTE = 42

# Documentos com quadros que o PyMuPDF lineariza célula por célula: a página com "Quadro N"
# (ou quase só linhas curtas) vira 1 trecho inteiro, para não separar a linha da coluna.
DOCS_PAGINA_INTEIRA: set[str] = set()
DOCS_QUADRO_POR_PAGINA = {"MS-PCDT-TDAH-2022", "MEC-PNEEI-CADERNO-4-PRATICAS-INCLUSIVAS-2026"}
# Recorte por página: o PCDT tem 199 páginas, mas as p. 19-199 são apêndices de metodologia e
# tabelas de evidência de remédio (GRADE). Para o Íris interessa o protocolo (p. 1-18), que
# inclui o tratamento não medicamentoso e o papel da escola.
PAGINA_MAXIMA = {"MS-PCDT-TDAH-2022": 18}

# Avisos de uso: o trecho continua na busca, mas o agente não deve usá-lo para este fim.
NAO_USAR_PARA = {
    "ABDA-GUIA-PROFESSORES-2012": ["evidencia_de_eficacia"],
    "RBEE-SEBASTIAN-HEREDERO-2020-DIRETRIZES-DUA": ["numeracao_dua_3_0"],
    "MEC-POLITICA-PEEI-2008": ["norma_vigente"],
    "RES-CNE-CEB-4-2009-AEE": ["norma_vigente_em_conflito"],
}
# Seções que não respondem pergunta de professor (artigos científicos): descartadas e contadas.
RE_SECAO_DESCARTAVEL = re.compile(
    r"^\W*(\d+\.?\s*)?(refer[êe]ncias?( bibliogr[áa]ficas)?|references?|bibliograph(y|ie)|literature cited|"
    r"acknowledg(e)?ments?|agradecimentos|funding|financiamento|conflicts? of interest|competing interests|"
    r"conflito de interesses?|author contributions?|contribui[çc][ãa]o dos autores|data availability( statement)?|"
    r"supplementary (material|information)|footnotes|associated data|publisher'?s note|declaration of interest)\W*$",
    re.I)

# Pedaços de cabeçalho que a extração repete e não servem para busca (créditos, ficha técnica).
RE_FICHA = re.compile(r"Ficha Catalogr[áa]fica|ISBN\s*[\d-]|Tiragem:|Catalogação na fonte", re.I)
RE_PESSOA_UF = re.compile(r"\((?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\)\s*$")
RE_CARGO = re.compile(r"^(MEMBROS|COORDENA[ÇC][ÃA]O|PRESIDENTE|VICE-PRESIDENTE|SECRET[ÁA]RI[OA]S?|DIRETORIA|"
                      r"DIRETOR[A]?|COORDENADOR[A]?|RELATOR[A]?|AUTORES?|CONSELHO FISCAL)\b[^a-z]{0,60}:?$")
# referência bibliográfica: "SOBRENOME, A." ou "SOBRENOME, A. B.; OUTRO"
RE_REFERENCIA = re.compile(r"^[A-ZÀ-Ú][A-ZÀ-Ú'\- ]{2,}, ?[A-ZÀ-Ú]\.|et al\.|Disponível em:|doi:|Acesso em:|^_{3,}|^BRASIL\. ", re.I)
RE_REFERENCIA_FORTE = re.compile(r"^[A-ZÀ-Ú][A-ZÀ-Ú'\- ]{2,}, ?[A-ZÀ-Ú]\.|"
                                 r"^\d{1,3}\.\s+[A-ZÀ-Ú][a-zà-ú'\-]+,? [A-Z]{1,3}[.,]|\d{4};\s?\d+|"
                                 r"^[A-ZÀ-Ú][A-Za-zà-ú'\-]+,\s[A-Z]\.(\s?[A-Z]\.)*.{0,200}\((19|20)\d{2}[a-z]?\)|"
                                 r"doi\.org/10\.|\bdoi:\s?10\.")
MARCA_DIRETORIA = "\x00DIRETORIA\x00"
RE_CABECALHO_GENERICO = re.compile(
    r"^((((O QUE|COMO|QUEM|QUANDO|ONDE|POR QUE)\b[^.!?]{0,22}\?\s*){2,})|((O QUE|COMO|QUEM|QUANDO) [A-ZÇÃÁÉ/]+\?)|"
    r"QUEM FAZ|IMPORTANTE|OBSERVAÇ(ÃO|ÕES)|NOTA|"
    r"SAIBA MAIS|DICAS?|LEMBRE-SE|FIQUE ATENT[OA]|ATENÇÃO|SIM|NÃO|TRATAR|CLASSIFICAR|AVALIAR)\s*$")
RE_MARCADOR_PAGINA = re.compile(r"^=== p\. (\d+) ===\s*$")
RE_ARTIGO = re.compile(r"^Art\.\s*(\d+[º°o]?(?:-[A-Z])?)")
RE_NUMERADO = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ])")
RE_MARCADOR_LISTA = re.compile(r"^\s*([•●▪■◦\-–]|o\s|\d+[\)\.]\s|[a-z]\)\s)")


# ---------------------------------------------------------------- 1. catálogo
def carregar_catalogo(caminho: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Devolve (documentos que entram, documentos que ficam de fora com o motivo).

    Entra: status começando por 'aceito' e SEM quase_duplicata_de.
    Fica de fora: quase duplicata de outro documento e qualquer recusado.
    """
    caminho = caminho or BASE / "fontes.json"
    cat = json.loads(Path(caminho).read_text(encoding="utf-8"))
    entram, fora = [], []
    for d in cat["documentos"]:
        if not str(d.get("status", "")).startswith("aceito"):
            fora.append({"id": d["id"], "motivo": f"status={d.get('status')}"})
        elif d.get("quase_duplicata_de"):
            fora.append({"id": d["id"], "motivo": f"quase duplicata de {d['quase_duplicata_de']}"})
        else:
            entram.append(d)
    return entram, fora


# ---------------------------------------------------------------- 2. leitura
def ler_texto(doc: dict) -> list[tuple[int | None, str]]:
    """Lê o texto da etapa 1. PDF: lista de (página, texto) pelo marcador '=== p. N ==='.
    HTML/markdown: um único item (None, texto), porque não há página."""
    caminho = BASE / doc["arquivo_texto"]
    if not caminho.exists():
        raise SystemExit(f"Texto ausente: {doc['arquivo_texto']} (documento {doc['id']}).\n"
                         "A ingestão requer o texto de todos os documentos do índice. Os textos de documentos sem licença "
                         "aberta não são distribuídos: ver textos_nao_distribuidos.txt e FONTES.md.")
    texto = caminho.read_text(encoding="utf-8")
    if "=== p. " not in texto:
        return [(None, texto)]
    paginas: list[tuple[int | None, str]] = []
    atual, buf = None, []
    for linha in texto.splitlines():
        m = RE_MARCADOR_PAGINA.match(linha)
        if m:
            if atual is not None:
                paginas.append((atual, "\n".join(buf)))
            atual, buf = int(m.group(1)), []
        else:
            buf.append(linha)
    if atual is not None:
        paginas.append((atual, "\n".join(buf)))
    return paginas


# ---------------------------------------------------------------- 3. limpeza
def _chave_repeticao(linha: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", linha.lower())).strip()


def limpar(paginas: list[tuple[int | None, str]]) -> tuple[list[tuple[int | None, list[str]]], dict]:
    """Tira cabeçalho/rodapé repetido, número de página solto, junta palavra hifenizada
    na quebra de linha e normaliza espaços. Devolve (páginas como listas de linhas, estatística)."""
    est = Counter()
    linhas_pag = []
    for p, t in paginas:
        ls = [re.sub(r"[ \t\u00a0]+", " ", x).strip() for x in t.replace("\r", "").split("\n")]
        linhas_pag.append((p, ls))

    # cabeçalho/rodapé: linha (sem números) que aparece no topo ou no pé de >= 30% das páginas
    if len(linhas_pag) >= 4:
        conta = Counter()
        for _, ls in linhas_pag:
            nao_vazias = [x for x in ls if x]
            borda = set(_chave_repeticao(x) for x in nao_vazias[:3] + nao_vazias[-3:])
            conta.update(k for k in borda if len(k) > 3)
        limite = max(3, 0.3 * len(linhas_pag))
        repetidas = {k for k, c in conta.items() if c >= limite}
        # cabeçalho corrido que a extração põe no meio da página (ex.: nome do órgão):
        # linha curta igual em >= 30% das páginas, em qualquer posição
        conta_meio = Counter()
        for _, ls in linhas_pag:
            conta_meio.update(set(_chave_repeticao(x) for x in ls if x and len(x.split()) <= 12))
        repetidas |= {k for k, c in conta_meio.items() if c >= limite and len(k) > 8}
    else:
        repetidas = set()

    # vocabulário do documento, para decidir se o hífen da quebra de linha é de separação
    vocab = Counter(w.lower() for _, ls in linhas_pag for x in ls for w in re.findall(r"\w+", x))

    saida = []
    for p, ls in linhas_pag:
        nao_vazias_idx = [i for i, x in enumerate(ls) if x]
        borda = set(nao_vazias_idx[:3] + nao_vazias_idx[-3:])
        limpas = []
        creditos = 0
        for i, x in enumerate(ls):
            if _chave_repeticao(x) in repetidas and (i in borda or len(x.split()) <= 12):
                est["linhas_cabecalho_rodape"] += 1
                continue
            if i in borda and re.fullmatch(r"\d{1,3}", x):
                est["numeros_de_pagina"] += 1
                continue
            if RE_PESSOA_UF.search(x) or RE_CARGO.match(x):
                est["linhas_de_creditos_da_diretoria"] += 1   # "Fulano de Tal (SP)", "MEMBROS:"
                creditos += 1
                continue
            limpas.append(x)
        if creditos >= 8 and creditos >= 0.3 * max(1, len([x for x in ls if x])):
            saida.append((p, [MARCA_DIRETORIA]))   # página inteira de diretoria/expediente
            continue
        # hifenização: "ali-" + "mentação" -> "alimentação" se a palavra inteira existe no documento
        juntas: list[str] = []
        for x in limpas:
            if juntas and juntas[-1].endswith("-") and x and x[0].islower():
                ant = juntas[-1]
                m1 = re.search(r"(\w+)-$", ant)
                m2 = re.match(r"(\w+)", x)
                if m1 and m2:
                    inteira = (m1.group(1) + m2.group(1)).lower()
                    if vocab.get(inteira, 0) > 0:
                        juntas[-1] = ant[:-1] + x
                        est["hifenizacoes_juntadas"] += 1
                        continue
                    juntas[-1] = ant + x        # hífen de verdade (ex.: licença-maternidade)
                    est["hifens_mantidos"] += 1
                    continue
            juntas.append(x)
        saida.append((p, juntas))
    return saida, dict(est)


# ---------------------------------------------------------------- 4. corte (chunking)
@dataclass
class Bloco:
    """Um parágrafo (ou título) com as páginas onde está."""
    texto: str
    p_ini: int | None
    p_fim: int | None
    titulo: bool = False

    @property
    def n(self) -> int:
        return len(self.texto.split())


@dataclass
class Secao:
    nome: str
    blocos: list[Bloco] = field(default_factory=list)
    pagina_inteira: bool = False       # quadro: não divide nem junta

    @property
    def n(self) -> int:
        return sum(b.n for b in self.blocos)


def _eh_titulo(linha: str) -> bool:
    """Linha curta em MAIÚSCULAS ou numerada ('4.3 INTERVENÇÕES...', '2 Atenção')."""
    if not linha or len(linha.split()) > 12 or linha.endswith((",", ";", ":", "!")):
        return False   # "ATENÇÃO!", "MEMBROS:" são chamadas de caixa, não títulos de seção
    # referência bibliográfica em maiúsculas ("SANTOS; DE SIMONI, 2011).") não é título
    if "http" in linha or "Disponível" in linha or "www." in linha:
        return False   # nota de rodapé numerada ("2 Disponível em: <http...")
    if ";" in linha or re.search(r"(19|20)\d{2}\)?\.?$", linha) or linha.endswith(")."):
        return False
    if RE_MARCADOR_LISTA.match(linha) and not RE_NUMERADO.match(linha):
        return False
    letras = [c for c in linha if c.isalpha()]
    if len(letras) < 4:
        return False
    if RE_CABECALHO_GENERICO.match(linha):
        return False   # cabeçalho de coluna de quadro ("O QUE FAZER? COMO FAZER? QUEM FAZ?")
    if sum(c.isupper() for c in letras) / len(letras) >= 0.85:
        return True
    m = RE_NUMERADO.match(linha)
    return bool(m) and not linha.endswith(".") and "," not in linha and len(linha.split()) <= 10


def _eh_titulo_misto(linha: str, anterior: str, seguinte: str) -> bool:
    """Fallback para PDFs cujos títulos são em caixa mista ('Intervenções escolares'):
    linha de até 6 palavras, sem pontuação final, depois de frase terminada e antes de linha
    que começa com maiúscula."""
    ws = linha.split()
    if not (1 <= len(ws) <= 6) or not linha[0].isupper() or linha[-1] in ".,;:!?-–":
        return False
    if "," in linha or "%" in linha or (len(ws) == 1 and len(linha) < 6):
        return False   # célula de tabela ("Yes", "NR", "P, T", "USA")
    if re.search(r"\d{4}|Nº|gestão|\(|\)", linha) or RE_MARCADOR_LISTA.match(linha):
        return False
    if not seguinte or not (seguinte[0].isupper() or RE_MARCADOR_LISTA.match(seguinte)):
        return False
    return (anterior.endswith((".", "!", "?", ")")) or _eh_titulo(anterior)
            or len(ws) <= 3 and not _parece_nome(linha))


def _parece_nome(linha: str) -> bool:
    """'Tadeu Fernando Fernandes', 'ELZA DANIEL DE MELLO': todas as palavras com inicial maiúscula."""
    ws = [w for w in linha.split() if w.lower() not in ("de", "da", "do", "dos", "das", "e")]
    return (2 <= len(ws) <= 7 and not re.search(r"\d", linha)
            and all(w[0].isupper() and w.isalpha() for w in ws))


def _pagina_creditos(linhas: list[str]) -> str | None:
    """Página de expediente (lista de nomes) ou sumário (linhas com '.....')."""
    if sum("....." in x for x in linhas) >= 5:
        return "página de sumário"
    nomes = sum(_parece_nome(x) for x in linhas)
    if nomes >= 8 and nomes >= 0.5 * len(linhas):
        return "página de diretoria/expediente (lista de nomes)"
    return None


def _pagina_numerica(linhas: list[str]) -> bool:
    """Curva de crescimento / tabela de registro: quase só números soltos."""
    toks = " ".join(linhas).split()
    if len(toks) < 30:
        return False
    num = sum(bool(re.fullmatch(r"[\d,.\-–/%]+", t)) for t in toks)
    palavras = sum(bool(re.fullmatch(r"[A-Za-zÀ-ú]{3,}", t)) for t in toks)
    return num / len(toks) >= 0.4 and palavras < 60


def _pagina_formulario(linhas: list[str]) -> bool:
    """Campos de registro em branco ('Data:___/___', 'Ass.:____'): só lacunas."""
    toks = " ".join(linhas).split()
    return len(toks) >= 30 and sum("__" in t for t in toks) / len(toks) >= 0.25


def _pagina_quadro(linhas: list[str]) -> bool:
    """Quadro do Protocolo 2016: tem 'Quadro N' ou quase só linhas curtas (células)."""
    ne = [x for x in linhas if x]
    if len(" ".join(ne).split()) < 40:
        return False
    if any(re.match(r"^Quadro \d+", x) for x in ne):
        return True
    curtas = sum(len(x.split()) <= 4 for x in ne)
    return len(ne) >= 25 and curtas / len(ne) >= 0.75


def _fim_de_paragrafo(linha: str) -> bool:
    return linha.endswith((".", "!", "?", ":", ";")) or linha.endswith((".”", '."', ".)"))


def _secoes_pdf(doc: dict, paginas: list[tuple[int | None, list[str]]], descartes: Counter
                ) -> list[Secao]:
    secoes: list[Secao] = []
    atual = Secao(nome="(início do documento)")
    para: list[str] = []
    p_ini = p_fim = None
    ultima_secao = atual.nome

    def fecha_paragrafo():
        nonlocal para, p_ini
        if para:
            atual.blocos.append(Bloco(" ".join(para), p_ini, p_fim))
        para, p_ini = [], None

    for pagina, linhas in paginas:
        if pagina and doc["id"] in PAGINA_MAXIMA and pagina > PAGINA_MAXIMA[doc["id"]]:
            descartes["página fora do recorte (apêndice de metodologia/tabelas de remédio)"] += 1
            continue
        ne = [x for x in linhas if x]
        texto_pag = "\n".join(ne)
        if not ne:
            descartes["página vazia (branco/só imagem)"] += 1
            continue
        if ne == [MARCA_DIRETORIA]:
            descartes["página de diretoria/expediente (lista de nomes)"] += 1
            continue
        cred = _pagina_creditos(ne)
        if cred:
            descartes[cred] += 1
            continue
        if _pagina_numerica(ne):
            descartes["página de curva de crescimento / tabela só com números"] += 1
            continue
        if _pagina_formulario(ne):
            descartes["página de formulário de registro em branco"] += 1
            continue
        if RE_FICHA.search(texto_pag):
            descartes["página de ficha técnica / créditos"] += 1
            continue
        if atual.nome == "REFERÊNCIAS":
            # página nova sem cara de referência encerra a lista (o 'Referências' pode ter vindo do sumário)
            pistas = sum(bool(RE_REFERENCIA.search(x) or re.search(r"\b(19|20)\d{2}\b[.;)]", x)) for x in ne)
            if pistas < max(2, 0.1 * len(ne)):
                fecha_paragrafo()
                if atual.blocos:
                    secoes.append(atual)
                atual = Secao(nome=ultima_secao)
        elif atual.nome:
            ultima_secao = atual.nome
        quadro = doc["id"] in DOCS_PAGINA_INTEIRA or (
            doc["id"] in DOCS_QUADRO_POR_PAGINA and _pagina_quadro(ne))
        if quadro:
            fecha_paragrafo()
            if atual.blocos:
                secoes.append(atual)
            tit = next((x for x in ne if re.match(r"^Quadro \d+", x)), None)
            if not tit:
                tits = [x for x in ne[:6] if _eh_titulo(x)]
                tit = " ".join(tits[:2]) if tits else ne[0]
            nome = tit[:120]
            if doc["id"] in DOCS_QUADRO_POR_PAGINA and atual.nome and not tit.startswith(atual.nome):
                nome = f"{atual.nome[:60]} > {tit[:80]}"
            secoes.append(Secao(nome=nome, blocos=[Bloco(" \n".join(ne), pagina, pagina)],
                                pagina_inteira=True))
            atual = Secao(nome=atual.nome)
            continue
        i = 0
        while i < len(ne):
            x = ne[i]
            continua = i + 1 < len(ne) and ne[i + 1][:1].islower()   # frase que segue na linha de baixo
            if RE_SECAO_DESCARTAVEL.match(x):
                fecha_paragrafo()
                if atual.blocos:
                    secoes.append(atual)
                atual = Secao(nome="REFERÊNCIAS", blocos=[Bloco(x, pagina, pagina, titulo=True)])
                i += 1
                continue
            eh_tit = _eh_titulo(x) and not continua
            if not eh_tit and pagina != 1:
                # títulos em caixa mista ("Introduction", "Método"); na p. 1 as linhas curtas
                # costumam ser autores e afiliações, não títulos
                anterior = ne[i - 1] if i > 0 else "."
                eh_tit = _eh_titulo_misto(x, anterior, ne[i + 1] if i + 1 < len(ne) else "")
            if eh_tit and atual.nome == "REFERÊNCIAS":
                # dentro das referências, só um título em MAIÚSCULAS (novo capítulo) encerra a lista
                letras = [c for c in x if c.isalpha()]
                eh_tit = (sum(c.isupper() for c in letras) / max(1, len(letras)) >= 0.85
                          and not RE_REFERENCIA.search(x))
            if eh_tit:
                # títulos em 2-3 linhas seguidas viram um título só
                partes = [x]
                while i + 1 < len(ne) and len(partes) < 3 and _eh_titulo(ne[i + 1]):
                    i += 1
                    partes.append(ne[i])
                fecha_paragrafo()
                if atual.blocos:
                    secoes.append(atual)
                nome = " ".join(partes)
                atual = Secao(nome=nome[:120], blocos=[Bloco(nome, pagina, pagina, titulo=True)])
                i += 1
                continue
            if RE_MARCADOR_LISTA.match(x) and para:
                fecha_paragrafo()
            if p_ini is None:
                p_ini = pagina
            p_fim = pagina
            para.append(x)
            if _fim_de_paragrafo(x):
                fecha_paragrafo()
            i += 1
    fecha_paragrafo()
    if atual.blocos:
        secoes.append(atual)
    return secoes


def _secoes_markdown(doc: dict, linhas: list[str]) -> list[Secao]:
    """HTML/markdown: seção por cabeçalho '#'; nas leis, uma seção por artigo ('Art.')."""
    secoes: list[Secao] = []
    cabecalho = "(início)"
    atual = Secao(nome=cabecalho)
    eh_lei = sum(bool(RE_ARTIGO.match(x)) for x in linhas) >= 3
    if eh_lei:
        # o HTML do Planalto quebra a linha antes de "§" no meio da frase ("previsto no\n§ 2º")
        coladas: list[str] = []
        for x in linhas:
            if coladas and x.startswith("§") and coladas[-1] and not coladas[-1].endswith((".", ";", ":", ")")):
                coladas[-1] = coladas[-1] + " " + x
            else:
                coladas.append(x)
        linhas = coladas
    for x in linhas:
        if not x:
            continue
        if x == "[...]":            # recorte: o que vem depois não pertence à seção anterior
            cabecalho = "(início)"
            continue
        if x.startswith("#"):
            h = x.lstrip("#").strip()
            nivel = len(x) - len(x.lstrip("#"))
            if nivel >= 3 and _parece_nome(re.sub(r"\s*,.*$", "", h)):
                continue          # autor do artigo (PMC: "### Mark L Wolraich , MD, FAAP")
            if h.lower().startswith("fonte:"):
                continue
            if atual.blocos:
                secoes.append(atual)
            if RE_SECAO_DESCARTAVEL.match(h):
                cabecalho = "REFERÊNCIAS"
                atual = Secao(nome="REFERÊNCIAS", blocos=[Bloco(h, None, None, titulo=True)])
                continue
            cabecalho = h[:120]
            atual = Secao(nome=cabecalho, blocos=[Bloco(cabecalho, None, None, titulo=True)])
            continue
        if x.lower().startswith("fonte: http"):
            continue      # linha de proveniência do site do CAST (a URL fica no metadado)
        if eh_lei and re.match(r"^(SEÇÃO|CAPÍTULO|TÍTULO)\b", x):
            if atual.blocos:
                secoes.append(atual)
            cabecalho = re.sub(r"\(?Vigência encerrada\)?", "", x).strip()[:120]
            atual = Secao(nome=cabecalho, blocos=[Bloco(cabecalho, None, None, titulo=True)])
            continue
        m = RE_ARTIGO.match(x) if eh_lei else None
        if m:
            if atual.blocos:
                secoes.append(atual)
            nome = f"Art. {m.group(1)}"
            if cabecalho and cabecalho not in ("(início)",) and not cabecalho.startswith(("DEL", "L1")):
                nome = f"{cabecalho[:70]} | {nome}"
            atual = Secao(nome=nome)
        atual.blocos.append(Bloco(x, None, None))
    if atual.blocos:
        secoes.append(atual)
    return secoes


def _dividir_bloco_grande(b: Bloco, limite: int) -> list[Bloco]:
    """Parágrafo maior que o limite: corta por frase; se nem frase houver (tabela), por palavra."""
    frases = re.split(r"(?<=[.!?;])\s+", b.texto)
    pedacos, buf = [], []
    for f in frases:
        ws = f.split()
        while len(ws) > limite:
            if buf:
                pedacos.append(" ".join(buf)); buf = []
            pedacos.append(" ".join(ws[:limite])); ws = ws[limite:]
        if len(buf) + len(ws) > limite and buf:
            pedacos.append(" ".join(buf)); buf = []
        buf.extend(ws)
    if buf:
        pedacos.append(" ".join(buf))
    return [Bloco(t, b.p_ini, b.p_fim) for t in pedacos]


def _empacotar(blocos: list[Bloco], eh_lei: bool) -> list[list[Bloco]]:
    """Junta parágrafos até ~MAX_PALAVRAS; o trecho seguinte começa repetindo o último
    parágrafo do anterior (sobreposição). Nas leis, a sobreposição é o caput do artigo."""
    unidades: list[Bloco] = []
    for b in blocos:
        unidades.extend(_dividir_bloco_grande(b, MAX_PALAVRAS) if b.n > MAX_PALAVRAS else [b])
    if sum(u.n for u in unidades) <= MAX_PALAVRAS:
        return [unidades]
    caput = unidades[0] if eh_lei else None
    grupos: list[list[Bloco]] = []
    atual: list[Bloco] = []
    for u in unidades:
        if atual and sum(x.n for x in atual) + u.n > MAX_PALAVRAS:
            grupos.append(atual)
            if caput is not None and caput.n <= SOBREPOSICAO_MAX * 2:
                atual = [caput]
            elif atual[-1].n <= SOBREPOSICAO_MAX and len(atual) > 1:
                atual = [atual[-1]]
            else:
                atual = []
        atual.append(u)
    if atual:
        so_repeticao = len(atual) == 1 and grupos and atual[0] is grupos[-1][-1]
        if not so_repeticao:
            grupos.append(atual)
    # último pedaço pequeno demais: junta ao anterior
    if len(grupos) > 1 and sum(x.n for x in grupos[-1]) < MIN_PALAVRAS:
        ult = grupos.pop()
        grupos[-1].extend(x for x in ult if x is not grupos[-1][-1])
    return grupos


def _eh_referencias(blocos: list[Bloco], secao: str) -> bool:
    """Trecho que é lista de referências (metade ou mais dos parágrafos parece citação)."""
    corpo = [b for b in blocos if not b.titulo]
    if not corpo:
        return False
    if re.match(r"^(REFER[ÊE]NCIAS|BIBLIOGRAFIA)", secao, re.I):
        return True
    fortes = sum(bool(RE_REFERENCIA_FORTE.search(b.texto)) for b in corpo)
    fracas = sum(bool(RE_REFERENCIA.search(b.texto)) for b in corpo)
    return fortes >= 2 and (fortes + fracas) / (2 * len(corpo)) >= 0.5


def _eh_tabela_de_dados(texto: str) -> bool:
    """Tabela de estudos/risco de viés linearizada: muitas linhas de 1-2 palavras e muitos
    tokens curtos ou numéricos. Texto corrido e listas de orientação não caem aqui."""
    linhas = [x for x in texto.split("\n") if x.strip()]
    toks = texto.split()
    if len(toks) < 30 or len(linhas) < 10:
        return False
    curtas = sum(len(x.split()) <= 2 for x in linhas) / len(linhas)
    miudos = sum(len(t.strip(".,;:()%")) <= 2 or re.fullmatch(r"[\d.,±\-–/%()=<>]+", t) is not None
                 for t in toks) / len(toks)
    return curtas >= 0.6 and miudos >= 0.35


def _eh_lista_de_nomes(texto: str) -> bool:
    """Créditos corridos: 'Ana Beatriz Silva, Bianca Eloi da Silva, ...' (>= 60% dos pedaços são nomes)."""
    pedacos = [p.strip() for p in re.split(r"[,\n]", texto) if p.strip()]
    if len(pedacos) < 12:
        return False
    return sum(_parece_nome(p) for p in pedacos) / len(pedacos) >= 0.6


def cortar(doc: dict, paginas: list[tuple[int | None, list[str]]]) -> tuple[list[dict], Counter]:
    """Chunking estrutural com fallback. Devolve (trechos sem metadados, descartes)."""
    descartes: Counter = Counter()
    if paginas and paginas[0][0] is None:
        secoes = _secoes_markdown(doc, paginas[0][1])
    else:
        secoes = _secoes_pdf(doc, paginas, descartes)
    eh_lei = any(RE_ARTIGO.search(s.nome) for s in secoes)

    # seção pequena (< MIN_PALAVRAS) junta com a seguinte (ou com a anterior, se for a última)
    juntas: list[Secao] = []
    pendente: Secao | None = None
    for s in secoes:
        if s.pagina_inteira:
            if pendente:
                juntas.append(pendente); pendente = None
            juntas.append(s)
            continue
        if pendente:
            s = Secao(nome=s.nome if s.n >= pendente.n else pendente.nome,
                      blocos=pendente.blocos + s.blocos)
            pendente = None
        if s.n < MIN_PALAVRAS:
            pendente = s
        else:
            juntas.append(s)
    if pendente:
        if juntas and not juntas[-1].pagina_inteira:
            juntas[-1].blocos.extend(pendente.blocos)
        elif pendente.n >= 10:
            juntas.append(pendente)
        else:
            descartes["pedaço final com menos de 10 palavras"] += 1

    trechos = []
    for s in juntas:
        grupos = [s.blocos] if s.pagina_inteira else _empacotar(s.blocos, eh_lei)
        for g in grupos:
            texto = "\n".join(b.texto for b in g).strip()
            if _eh_referencias(g, s.nome):
                descartes["trecho de referências bibliográficas"] += 1
                continue
            if _eh_tabela_de_dados(texto):
                descartes["trecho de tabela de dados (células soltas: Y/N, números, siglas)"] += 1
                continue
            if _eh_lista_de_nomes(texto):
                descartes["trecho de créditos (lista de nomes)"] += 1
                continue
            if len(texto.split()) < 10:
                descartes["trecho com menos de 10 palavras"] += 1
                continue
            pags = [p for b in g for p in (b.p_ini, b.p_fim) if p is not None]
            trechos.append({"secao": s.nome, "texto": texto,
                            "pagina_inicio": min(pags) if pags else None,
                            "pagina_fim": max(pags) if pags else None,
                            "tipo_corte": "pagina_inteira" if s.pagina_inteira else "estrutural"})
    return trechos, descartes


# ---------------------------------------------------------------- 5. metadados
def _ano(doc: dict) -> str:
    m = re.search(r"(19|20)\d{2}", str(doc.get("ano") or doc.get("ano_edicao") or ""))
    return m.group(0) if m else ""


def _avisos(doc: dict, trecho: dict) -> tuple[list[str], str]:
    return list(NAO_USAR_PARA.get(doc["id"], [])), doc.get("nota_uso") or ""


def gerar_metadados(doc: dict, trechos: list[dict]) -> list[dict]:
    """Acrescenta a cada trecho os dados da fonte e o texto com prefixo de contexto.

    Escolha registrada: o texto que vira vetor começa com
    'Documento: <titulo> | Seção: <secao>', para o modelo saber de onde o trecho vem."""
    saida = []
    for i, t in enumerate(trechos):
        nao_usar, nota = _avisos(doc, t)
        texto_indexado = f"Documento: {doc['titulo']} | Seção: {t['secao']}\n{t['texto']}"
        saida.append({
            "chunk_id": f"{doc['id']}#{i:04d}",
            "doc_id": doc["id"],
            "titulo": doc["titulo"],
            "orgao": doc.get("orgao") or doc.get("revista") or "",
            "ano": _ano(doc),
            "url": doc.get("url") or "",
            "licenca": doc.get("licenca") or "",
            "parte": doc.get("parte") or "",
            "idioma": doc.get("idioma") or "",
            "tipo_evidencia": doc.get("tipo_evidencia") or doc.get("vigencia") or "",
            "pagina_inicio": t["pagina_inicio"],
            "pagina_fim": t["pagina_fim"],
            "secao": t["secao"],
            "tema": list(doc.get("tema") or []),
            "barreiras": list(doc.get("barreiras") or []),
            "n_palavras": len(t["texto"].split()),
            "nao_usar_para": nao_usar,
            "nota_uso": nota,
            "tipo_corte": t["tipo_corte"],
            "texto": t["texto"],
            "texto_indexado": texto_indexado,
        })
    return saida


# ---------------------------------------------------------------- 6. tudo junto + relatório
def processar_documento(doc: dict) -> tuple[list[dict], Counter, dict]:
    paginas = ler_texto(doc)
    limpas, est = limpar(paginas)
    trechos, descartes = cortar(doc, limpas)
    return gerar_metadados(doc, trechos), descartes, est


def _quantis(xs: list[int]) -> dict:
    s = sorted(xs)
    q = lambda f: s[min(len(s) - 1, int(round(f * (len(s) - 1))))]
    return {"min": s[0], "p25": q(0.25), "mediana": q(0.5), "p75": q(0.75), "max": s[-1],
            "media": round(sum(s) / len(s), 1)}


def salvar_chunks(chunks: list[dict], caminho: Path = SAIDA_CHUNKS) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def _placeholders_restritos(docs_ausentes: list[dict], ids_existentes: set[str]) -> list[dict]:
    """Gera entradas de metadados para trechos referenciados de documentos com licença restrita."""
    cat_por_id = {d["id"]: d for d in docs_ausentes}
    if not cat_por_id:
        return []
    refs: set[str] = set()
    arq_respostas = AQUI / "respostas_medidas.json"
    if arq_respostas.exists():
        dados = json.loads(arq_respostas.read_text(encoding="utf-8"))
        for qs in dados.get("geradores", {}).values():
            for item in qs.values():
                refs.update(item.get("fontes", []))
    placeholders: list[dict] = []
    txt = "(texto não reproduzido por restrição de licença; consultar o endereço de origem)"
    for cid in sorted(refs - ids_existentes):
        doc_id = cid.split("#")[0]
        d = cat_por_id.get(doc_id)
        if not d:
            continue
        titulo = d.get("titulo", doc_id)
        placeholders.append({
            "chunk_id": cid,
            "doc_id": doc_id,
            "titulo": titulo,
            "orgao": d.get("orgao", ""),
            "ano": d.get("ano", ""),
            "url": d.get("url", ""),
            "licenca": d.get("licenca", "restrita"),
            "parte": d.get("parte", ""),
            "idioma": d.get("idioma", "pt-BR"),
            "tipo_evidencia": d.get("tipo_evidencia", ""),
            "pagina_inicio": None,
            "pagina_fim": None,
            "secao": "Seção sob licença restrita",
            "tema": d.get("tema", ""),
            "barreiras": d.get("barreiras", []),
            "n_palavras": 0,
            "nao_usar_para": NAO_USAR_PARA.get(doc_id, d.get("nao_usar_para", [])),
            "nota_uso": d.get("nota_uso", ""),
            "tipo_corte": "fechado",
            "texto": txt,
            "texto_indexado": f"Documento: {titulo} | Seção: Seção sob licença restrita\n\n{txt}",
        })
    return placeholders


def carregar_chunks(caminho: Path = SAIDA_CHUNKS) -> list[dict]:
    caminho = Path(caminho)
    if not caminho.exists():
        print("[ingestao] chunks.jsonl não encontrado; gerando automaticamente a partir dos textos disponíveis...")
        rodar(salvar=True, verbose=True, permitir_ausentes=True)
    return [json.loads(x) for x in caminho.read_text(encoding="utf-8").splitlines() if x]


def rodar(salvar: bool = True, verbose: bool = True, permitir_ausentes: bool = True) -> tuple[list[dict], dict]:
    docs, fora = carregar_catalogo()
    todos: list[dict] = []
    por_doc: dict[str, dict] = {}
    descartes_total: Counter = Counter()
    limpeza_total: Counter = Counter()
    ausentes: list[dict] = []
    for d in docs:
        if permitir_ausentes and not (BASE / d["arquivo_texto"]).exists():
            ausentes.append(d)
            continue
        cs, desc, est = processar_documento(d)
        todos.extend(cs)
        descartes_total.update(desc)
        limpeza_total.update(est)
        por_doc[d["id"]] = {"n_chunks": len(cs), "descartes": dict(desc),
                            "palavras": sum(c["n_palavras"] for c in cs),
                            "pagina_inteira": sum(c["tipo_corte"] == "pagina_inteira" for c in cs)}
    if ausentes:
        placeholders = _placeholders_restritos(ausentes, {c["chunk_id"] for c in todos})
        todos.extend(placeholders)
        if verbose:
            print(f"[ingestao] {len(ausentes)} documentos com licença restrita ausentes localmente; "
                  f"adicionados {len(placeholders)} metadados de referência.")
    palavras_validas = [c["n_palavras"] for c in todos if c["n_palavras"] > 0] or [0]
    resumo = {"n_docs": len(docs) - len(ausentes), "fora": fora, "n_chunks": len(todos),
              "n_descartados": sum(descartes_total.values()),
              "descartes": dict(descartes_total), "limpeza": dict(limpeza_total),
              "tamanho": _quantis(palavras_validas), "por_doc": por_doc}
    if salvar:
        salvar_chunks(todos)
        if not ausentes:
            escrever_relatorio(todos, resumo)
    if verbose:
        print(f"{resumo['n_docs']} documentos abertos processados -> {resumo['n_chunks']} chunks totais; "
              f"{resumo['n_descartados']} páginas/pedaços descartados")
    return todos, resumo


def escrever_relatorio(chunks: list[dict], resumo: dict, caminho: Path = SAIDA_RELATORIO) -> None:
    caminho.parent.mkdir(exist_ok=True)
    L = []
    L.append("RELATÓRIO DE CHUNKING - Íris: base de conhecimento (semana 2)")
    L.append("Gerado por ingestao.py. Parâmetros: máx. %d palavras por trecho, mín. %d, "
             "sobreposição = último parágrafo do trecho anterior se tiver até %d palavras "
             "(~15%% de %d); nas leis, o caput do artigo." % (MAX_PALAVRAS, MIN_PALAVRAS,
                                                              SOBREPOSICAO_MAX, MAX_PALAVRAS))
    L.append("Prefixo de contexto no texto indexado: 'Documento: <titulo> | Seção: <secao>'.")
    L.append("")
    L.append(f"Documentos indexados: {resumo['n_docs']} (de {resumo['n_docs'] + len(resumo['fora'])} no catálogo)")
    for f in resumo["fora"]:
        L.append(f"  fora: {f['id']} ({f['motivo']})")
    L.append(f"Chunks gerados: {resumo['n_chunks']}")
    t = resumo["tamanho"]
    L.append("Tamanho em palavras (sem o prefixo): min %d | p25 %d | mediana %d | p75 %d | max %d | média %.1f"
             % (t["min"], t["p25"], t["mediana"], t["p75"], t["max"], t["media"]))
    acima = [c for c in chunks if c["n_palavras"] > MAX_PALAVRAS]
    abaixo = sum(c["n_palavras"] < MIN_PALAVRAS for c in chunks)
    acima_pag = sum(c["tipo_corte"] == "pagina_inteira" for c in acima)
    L.append(f"  acima de {MAX_PALAVRAS} palavras: {len(acima)} de {len(chunks)} "
             f"({acima_pag} são páginas inteiras de quadro; {len(acima) - acima_pag} passam do limite "
             f"por causa da sobreposição ou de um parágrafo sem ponto final)")
    L.append(f"  abaixo de {MIN_PALAVRAS} palavras: {abaixo} de {len(chunks)} (documentos curtos inteiros ou fim de seção sem vizinha)")
    L.append(f"  chunks de página inteira (quadros do PCDT e do Caderno 4 do MEC): "
             f"{sum(c['tipo_corte'] == 'pagina_inteira' for c in chunks)} de {len(chunks)}")
    L.append("")
    L.append(f"Descartados: {resumo['n_descartados']} páginas/pedaços")
    for k, v in sorted(resumo["descartes"].items(), key=lambda x: -x[1]):
        L.append(f"  {v:4d}  {k}")
    L.append("Limpeza (linhas afetadas): " + ", ".join(f"{k}={v}" for k, v in sorted(resumo["limpeza"].items())))
    L.append("")
    L.append(f"{'documento':48s} {'chunks':>6s} {'palavras':>8s} {'pág.inteira':>11s}  descartes")
    for d, x in resumo["por_doc"].items():
        desc = "; ".join(f"{k}: {v}" for k, v in x["descartes"].items()) or "-"
        L.append(f"{d:48s} {x['n_chunks']:6d} {x['palavras']:8d} {x['pagina_inteira']:11d}  {desc}")
    L.append("")
    avisos = Counter(a for c in chunks for a in c["nao_usar_para"])
    L.append("Chunks com aviso 'nao_usar_para': " + ", ".join(f"{k}={v}" for k, v in avisos.items()))
    L.append("")
    L.append("5 exemplos aleatórios (semente %d):" % SEMENTE)
    rnd = random.Random(SEMENTE)
    for c in rnd.sample(chunks, 5):
        L.append("-" * 100)
        L.append(f"{c['chunk_id']} | p. {c['pagina_inicio']}-{c['pagina_fim']} | {c['n_palavras']} palavras | {c['tipo_corte']}")
        L.append(c["texto_indexado"][:900] + (" [...]" if len(c["texto_indexado"]) > 900 else ""))
    caminho.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    rodar()
    print(SAIDA_RELATORIO.read_text(encoding="utf-8")[:6000])
