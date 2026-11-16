#!/usr/bin/env python3
"""Mapa estatico do codigo do Iris (repositorio do grupo) para o painel.

Le o clone do grupo SOMENTE para leitura (ast + regex, biblioteca padrao) e grava:

  27-mapa-codigo.json  dado estruturado (modulos, funcoes, arestas, testes, etapas do pipeline)
  27-mapa-codigo.txt   resumo legivel
  27-mapa-codigo.mmd   dois diagramas Mermaid: dependencias entre pastas e etapas do pipeline

Uso:
  python3 mapa_codigo.py --repo /caminho/iris-grupo --saida outputs

A analise e estatica e aproximada: ver README.md ao lado.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PREFIXO = "27-mapa-codigo"
SRC = Path("backend/src")
TESTES = Path("backend/tests")
RAG_PACOTE = Path("rag/iris-rag/pacote")
FRONT = Path("frontend/src")
SCRIPTS = Path("scripts")
NOMES_LLM = {"HybridLLMClient", "get_llm_client", "llm_client"}
LIBS_LLM = {"anthropic", "openai", "groq", "ollama"}


# ---------------------------------------------------------------------------
# utilidades


def git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def primeira_linha(doc: str | None) -> str:
    if not doc:
        return ""
    for linha in doc.strip().splitlines():
        if linha.strip():
            return linha.strip()
    return ""


def eh_type_checking(no: ast.If) -> bool:
    t = no.test
    return (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
        isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"
    )


def walk_sem_type_checking(arvore: ast.AST):
    """ast.walk que pula blocos `if TYPE_CHECKING:` (importacao so para tipo, nao roda)."""
    pilha = [arvore]
    while pilha:
        no = pilha.pop()
        yield no
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, ast.If) and eh_type_checking(filho):
                pilha.extend(filho.orelse)
                continue
            pilha.append(filho)


RE_TOPO = re.compile(r"^(?P<ind>(?:    )?)(?P<kw>async def|def|class)\s+(?P<nome>\w+)")


def esqueleto_por_regex(texto: str) -> str:
    """Reconstroi um modulo minimo e parseavel com imports de topo, funcoes, classes e metodos."""
    linhas = texto.splitlines()
    out: list[str] = []
    i = 0
    em_classe = False
    while i < len(linhas):
        ln = linhas[i]
        if ln.startswith(("import ", "from ")):
            bloco = [ln]
            while "(" in ln and ")" not in "".join(bloco) and i + 1 < len(linhas):
                i += 1
                bloco.append(linhas[i])
            out.append(" ".join(x.strip() for x in bloco))
            em_classe = False
        else:
            m = RE_TOPO.match(ln)
            if m and not m.group("ind"):
                em_classe = m.group("kw") == "class"
                out.append(f"{m.group('kw')} {m.group('nome')}" + (":" if em_classe else "(*a, **k):\n    pass"))
            elif m and em_classe and m.group("kw") != "class":
                out.append(f"    {m.group('kw')} {m.group('nome')}(*a, **k):\n        pass")
            elif ln and not ln[0].isspace() and not ln.startswith(("#", ")", "@")):
                em_classe = False
        i += 1
    texto_out = []
    for j, ln in enumerate(out):
        texto_out.append(ln)
        if ln.startswith("class ") and (j + 1 >= len(out) or not out[j + 1].startswith("    ")):
            texto_out.append("    pass")
    return "\n".join(texto_out) + "\n"


# ---------------------------------------------------------------------------
# descoberta de modulos Python


class ModPy:
    def __init__(self, mid: str, caminho: str, pasta: str, arvore: ast.Module, texto: str, pacote: bool):
        self.id = mid
        self.caminho = caminho
        self.pasta = pasta
        self.arvore = arvore
        self.linhas = texto.count("\n") + (0 if texto.endswith("\n") or not texto else 1)
        self.pacote = pacote  # __init__.py
        self.aliases: dict[str, tuple[str, str | None]] = {}  # nome local -> (modulo, atributo|None)
        self.imports_brutos: set[str] = set()  # nomes de modulo absolutos (internos ou nao)
        self.defs: set[str] = set()  # funcoes e classes de topo


def id_iris(rel: Path) -> str:
    partes = list(rel.relative_to(SRC).with_suffix("").parts)
    pacote = partes[-1] == "__init__"
    if pacote:
        partes = partes[:-1]
    return ".".join(partes)


def pasta_iris(rel: Path) -> str:
    partes = rel.relative_to(SRC / "iris").parts
    return partes[0] if len(partes) > 1 else "raiz"


def carregar_python(repo: Path) -> tuple[dict[str, ModPy], list[str]]:
    mods: dict[str, ModPy] = {}
    falhas: list[str] = []

    def add(mid: str, rel: Path, pasta: str, pacote: bool) -> None:
        texto = (repo / rel).read_text(encoding="utf-8", errors="replace")
        try:
            arvore = ast.parse(texto, filename=str(rel))
        except SyntaxError as e:
            # Ex.: f-string com barra invertida (sintaxe do Python 3.12) lida pelo 3.11.
            # Cai para um esqueleto por regex: imports, defs e classes, sem docstring nem chamadas.
            arvore = ast.parse(esqueleto_por_regex(texto))
            falhas.append(f"{rel}: {e.msg} (linha {e.lineno}); analisado por regex, sem chamadas/docstrings")
        mods[mid] = ModPy(mid, rel.as_posix(), pasta, arvore, texto, pacote)

    for p in sorted((repo / SRC / "iris").rglob("*.py")):
        rel = p.relative_to(repo)
        add(id_iris(rel), rel, pasta_iris(rel), p.name == "__init__.py")
    # pacote do RAG: modulos soltos importados por nome curto (sys.path aponta para a pasta)
    for p in sorted((repo / RAG_PACOTE).rglob("*.py")):
        rel = p.relative_to(repo)
        sub = p.relative_to(repo / RAG_PACOTE).with_suffix("").parts
        mid = "rag_pacote." + ".".join(sub)
        add(mid, rel, "rag_pacote" if len(sub) == 1 else "rag_pacote/" + "/".join(sub[:-1]), False)
    return mods, falhas


def resolver_relativo(mod: ModPy, nivel: int, modulo: str | None) -> str:
    base = mod.id.split(".")
    if not mod.pacote:
        base = base[:-1]
    if nivel > 1:
        base = base[: len(base) - (nivel - 1)]
    return ".".join(base + ([modulo] if modulo else []))


def coletar_imports(mods: dict[str, ModPy]) -> None:
    nomes_pacote_rag = {m.split(".", 1)[1]: m for m in mods if m.startswith("rag_pacote.")}

    def canon(nome: str) -> str:
        # `import consultar` dentro do pacote RAG (ou via bridge) -> rag_pacote.consultar
        if nome in nomes_pacote_rag:
            return nomes_pacote_rag[nome]
        return nome

    for mod in mods.values():
        for no in walk_sem_type_checking(mod.arvore):
            if isinstance(no, ast.Import):
                for a in no.names:
                    alvo = canon(a.name)
                    mod.imports_brutos.add(alvo)
                    local = a.asname or a.name.split(".")[0]
                    mod.aliases[local] = (alvo if a.asname else canon(a.name.split(".")[0]), None)
                    if a.asname is None and "." in a.name:
                        mod.aliases[a.name] = (alvo, None)
            elif isinstance(no, ast.ImportFrom):
                origem = resolver_relativo(mod, no.level, no.module) if no.level else (no.module or "")
                origem = canon(origem)
                for a in no.names:
                    if a.name == "*":
                        mod.imports_brutos.add(origem)
                        continue
                    sub = f"{origem}.{a.name}"
                    if sub in mods:  # `from iris.api.routes import materials`
                        mod.imports_brutos.add(sub)
                        mod.aliases[a.asname or a.name] = (sub, None)
                    else:
                        mod.imports_brutos.add(origem)
                        mod.aliases[a.asname or a.name] = (origem, a.name)
        for no in mod.arvore.body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                mod.defs.add(no.name)


def modulo_interno(nome: str, mods: dict[str, ModPy]) -> str | None:
    """Mapeia `iris.x.y` (ou prefixo) para o id de modulo interno existente."""
    partes = nome.split(".")
    while partes:
        cand = ".".join(partes)
        if cand in mods:
            return cand
        partes.pop()
    return None


def resolver_simbolo(mid: str, nome: str, mods: dict[str, ModPy], visitados=None) -> tuple[str, str] | None:
    """Segue reexportacoes de __init__ ate o modulo que define `nome`."""
    visitados = visitados or set()
    if (mid, nome) in visitados or mid not in mods:
        return None
    visitados.add((mid, nome))
    m = mods[mid]
    if nome in m.defs:
        return mid, nome
    if nome in m.aliases:
        orig, attr = m.aliases[nome]
        alvo = modulo_interno(orig, mods)
        if alvo and attr:
            return resolver_simbolo(alvo, attr, mods, visitados) or (alvo, attr)
    return None


# ---------------------------------------------------------------------------
# funcoes, classes e chamadas


def info_funcao(no) -> dict:
    return {
        "nome": no.name,
        "linha": no.lineno,
        "publica": not no.name.startswith("_"),
        "docstring": primeira_linha(ast.get_docstring(no)),
    }


def estrutura(mod: ModPy) -> tuple[list[dict], list[dict]]:
    funcs, classes = [], []
    for no in mod.arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(info_funcao(no))
        elif isinstance(no, ast.ClassDef):
            metodos = [info_funcao(n) for n in no.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({"nome": no.name, "linha": no.lineno, "metodos": metodos})
    return funcs, classes


def unidades(mod: ModPy):
    """Gera (nome_qualificado, no) para funcoes de topo e metodos; corpo do modulo vira '<modulo>'."""
    corpo_modulo = []
    for no in mod.arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield no.name, no, None
        elif isinstance(no, ast.ClassDef):
            for n in no.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{no.name}.{n.name}", n, no.name
            corpo_modulo.append(no)  # bases, decoradores, atributos de classe
        else:
            corpo_modulo.append(no)
    yield "<modulo>", ast.Module(body=corpo_modulo, type_ignores=[]), None


def chamadas(mods: dict[str, ModPy]) -> dict[str, set[str]]:
    """Grafo aproximado de chamadas: 'mod:qualnome' -> {'mod:qualnome'}."""
    grafo: dict[str, set[str]] = defaultdict(set)
    for mod in mods.values():
        classes_locais = {n.name: n for n in mod.arvore.body if isinstance(n, ast.ClassDef)}
        for qual, no, classe in unidades(mod):
            origem = f"{mod.id}:{qual}"
            for sub in walk_sem_type_checking(no):
                if not isinstance(sub, ast.Call):
                    continue
                f = sub.func
                alvo = None
                if isinstance(f, ast.Name):
                    if f.id in mod.defs:
                        alvo = (mod.id, f.id)
                    elif f.id in mod.aliases:
                        orig, attr = mod.aliases[f.id]
                        im = modulo_interno(orig, mods)
                        if im and attr:
                            alvo = resolver_simbolo(im, attr, mods) or (im, attr)
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    base = f.value.id
                    if base in ("self", "cls") and classe:
                        alvo = (mod.id, f"{classe}.{f.attr}")
                    elif base in classes_locais:
                        alvo = (mod.id, f"{base}.{f.attr}")
                    elif base in mod.aliases:
                        orig, attr = mod.aliases[base]
                        im = modulo_interno(orig, mods)
                        if im and attr is None and mods[im].id == im:
                            alvo = resolver_simbolo(im, f.attr, mods) or (im, f.attr)
                        elif im and attr:  # Classe.metodo() de classe importada
                            dono = resolver_simbolo(im, attr, mods)
                            if dono:
                                alvo = (dono[0], f"{dono[1]}.{f.attr}")
                if alvo:
                    grafo[origem].add(f"{alvo[0]}:{alvo[1]}")
        # instanciar/usar uma classe alcanca seus metodos (aproximacao)
        for cname, cno in classes_locais.items():
            for n in cno.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    grafo[f"{mod.id}:{cname}"].add(f"{mod.id}:{cname}.{n.name}")
    return grafo


def alcancaveis(grafo: dict[str, set[str]], inicio: set[str]) -> set[str]:
    vistos, pilha = set(), list(inicio)
    while pilha:
        n = pilha.pop()
        if n in vistos:
            continue
        vistos.add(n)
        pilha.extend(grafo.get(n, ()))
    return vistos


# ---------------------------------------------------------------------------
# frontend TypeScript (regex simples)

RE_TS_IMPORT = re.compile(r"""^\s*import\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']""", re.M)
RE_TS_FUNC = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)|^(?:export\s+)?const\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>",
    re.M,
)
RE_TS_FETCH = re.compile(r"fetch\(\s*`[^`]*?(/api/v1/[\w/\-]+)`")


def id_ts(rel: Path) -> str:
    partes = list(rel.relative_to(FRONT).with_suffix("").parts)
    return "frontend." + ".".join(partes)


def carregar_ts(repo: Path) -> list[dict]:
    saida = []
    base = repo / FRONT
    arquivos = sorted(p for p in base.rglob("*") if p.suffix in (".ts", ".tsx") and "node_modules" not in p.parts)
    ids = {p.relative_to(repo).with_suffix("").as_posix(): id_ts(p.relative_to(repo)) for p in arquivos}
    for p in arquivos:
        rel = p.relative_to(repo)
        texto = p.read_text(encoding="utf-8", errors="replace")
        importa = []
        for spec in RE_TS_IMPORT.findall(texto):
            if spec.startswith("@/"):
                alvo = (FRONT / spec[2:]).as_posix()
            elif spec.startswith("."):
                alvo = (rel.parent / spec).as_posix()
                alvo = str(Path(alvo)).replace("\\", "/")
                alvo = "/".join(_normaliza(alvo.split("/")))
            else:
                continue
            alvo = re.sub(r"\.(tsx?|js)$", "", alvo)
            for cand in (alvo, alvo + "/index"):
                if cand in ids:
                    importa.append(ids[cand])
                    break
        funcs = []
        for m in RE_TS_FUNC.finditer(texto):
            nome = m.group(1) or m.group(2)
            linha = texto.count("\n", 0, m.start()) + 1
            funcs.append({"nome": nome, "linha": linha, "publica": m.group(0).startswith("export"), "docstring": ""})
        sub = rel.relative_to(FRONT).parts
        saida.append(
            {
                "id": id_ts(rel),
                "caminho": rel.as_posix(),
                "pasta": "frontend/" + (sub[0] if len(sub) > 1 else "raiz"),
                "linhas": texto.count("\n") + (0 if texto.endswith("\n") or not texto else 1),
                "funcoes": funcs,
                "classes": [],
                "importa": sorted(set(importa)),
                "importado_por": [],
                "testado_por": [],
                "usa_llm": False,
                "tipo": "typescript",
                "_endpoints": sorted(set(RE_TS_FETCH.findall(texto))),
            }
        )
    return saida


def _normaliza(partes: list[str]) -> list[str]:
    out: list[str] = []
    for p in partes:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return out


def rotas_api(mods: dict[str, ModPy]) -> dict[str, tuple[str, str]]:
    """'/api/v1/<prefixo><caminho>' -> (modulo, funcao de topo que registra a rota)."""
    rotas = {}
    for mod in mods.values():
        if not mod.id.startswith("iris.api.routes."):
            continue
        prefixo = ""
        for no in ast.walk(mod.arvore):
            if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "APIRouter":
                for kw in no.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefixo = kw.value.value
        for no in ast.walk(mod.arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in no.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.args:
                        a0 = d.args[0]
                        if isinstance(a0, ast.Constant) and isinstance(a0.value, str) and a0.value.startswith("/"):
                            rotas["/api/v1" + str(prefixo) + a0.value] = (mod.id, no.name)
    return rotas


# ---------------------------------------------------------------------------
# testes


def carregar_testes(repo: Path, mods: dict[str, ModPy]) -> tuple[dict[str, set[str]], int, int, dict[str, set[str]]]:
    """Mapa modulo -> arquivos de teste que o importam; total de arquivos e de funcoes test_*;
    e simbolos importados por teste (para evidencia das etapas)."""
    por_mod: dict[str, set[str]] = defaultdict(set)
    simbolos: dict[str, set[str]] = defaultdict(set)  # 'mod:nome' -> arquivos
    n_arq = n_casos = 0
    for p in sorted((repo / TESTES).rglob("*.py")):
        if not p.name.startswith("test_"):
            continue
        rel = p.relative_to(repo).as_posix()
        n_arq += 1
        arvore = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name.startswith("test"):
                n_casos += 1
            nomes: list[tuple[str, str | None]] = []
            if isinstance(no, ast.Import):
                nomes = [(a.name, None) for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes = [(no.module, a.name) for a in no.names]
            # strings em patch("iris.x.y.func") tambem contam como alvo do teste
            elif isinstance(no, ast.Constant) and isinstance(no.value, str) and re.fullmatch(r"iris(\.\w+)+", no.value):
                nomes = [(no.value, None)]
            for modulo, attr in nomes:
                if attr and f"{modulo}.{attr}" in mods:
                    modulo, attr = f"{modulo}.{attr}", None
                im = modulo_interno(modulo, mods)
                if not im or not im.startswith("iris"):
                    continue
                por_mod[im].add(rel)
                if attr:
                    dono = resolver_simbolo(im, attr, mods)
                    if dono:
                        por_mod[dono[0]].add(rel)  # reexportado por __init__ conta para o modulo que define
                        simbolos[f"{dono[0]}:{dono[1]}"].add(rel)
    return por_mod, n_arq, n_casos, simbolos


# ---------------------------------------------------------------------------
# ciclos de import (Tarjan)


def ciclos(arestas: dict[str, set[str]]) -> list[list[str]]:
    indice, low, pilha, na_pilha, comps = {}, {}, [], set(), []
    contador = [0]
    sys.setrecursionlimit(10000)

    def visita(v):
        indice[v] = low[v] = contador[0]
        contador[0] += 1
        pilha.append(v)
        na_pilha.add(v)
        for w in arestas.get(v, ()):
            if w not in indice:
                visita(w)
                low[v] = min(low[v], low[w])
            elif w in na_pilha:
                low[v] = min(low[v], indice[w])
        if low[v] == indice[v]:
            comp = []
            while True:
                w = pilha.pop()
                na_pilha.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in arestas.get(v, ()):
                comps.append(sorted(comp))

    for v in sorted(arestas):
        if v not in indice:
            visita(v)
    return comps


# ---------------------------------------------------------------------------
# etapas do pipeline

# Sequencia lida em README.md, docs/arquitetura.md (secoes 1, 2.3 e 6), docs/roteiro_testes.md (secao 1)
# e docs/backlog_rastreabilidade.md (tabela 2.1). `alvos` sao os pontos de codigo que implementam
# a etapa; `nota` resume o que os documentos dizem e o que falta.
ETAPAS = [
    {
        "etapa": "upload / entrada de material (texto, .pdf, .docx, .txt)",
        "alvos": [("iris.api.routes.materials", "process_material_file_service"),
                  ("iris.api.routes.materials", "process_material_text_service")],
        "nota": "#4 CLOSED; OCR de prova digitalizada (#6) segue OPEN",
    },
    {
        "etapa": "sanitizacao de PII (zero-retention)",
        "alvos": [("iris.security.pii_scrubber", "sanitize_pii")],
        "nota": "#34 CLOSED; cabecalho escolar neutro (#36) OPEN",
    },
    {
        "etapa": "extracao de texto do documento",
        "alvos": [("iris.parsers.document_extractor", "extract_text_from_file")],
        "nota": "pdf/docx/txt em memoria; sem OCR",
    },
    {
        "etapa": "decomposicao estrutural / organizacao de prosa",
        "alvos": [("iris.parsers.structural_decomposer", "decompose_material"),
                  ("iris.parsers.prose_organizer", "organize_prose_structure")],
        "nota": "#5 e #53 CLOSED; endpoints /materials/decompose e /materials/organize-prose",
    },
    {
        "etapa": "extrator curricular (invariantes / trava)",
        "alvos": [("iris.agents.curriculum_extractor", "CurriculumExtractorAgent.extract")],
        "nota": "#17 CLOSED; validacao docente das travas (#13) OPEN",
    },
    {
        "etapa": "catalogo de caracteristicas / perfil funcional",
        "alvos": [("iris.api.routes.catalogs", "select_surgical_characteristics_service"),
                  ("iris.schemas.catalog", "load_official_tdah_catalog"),
                  ("iris.schemas.profile", "validar_perfil")],
        "nota": "#39 e #8 CLOSED; perfil portatil (#26, #30, #31) OPEN",
    },
    {
        "etapa": "RAG estrategista (busca por id_caracteristica + contexto)",
        "alvos": [("iris.rag.bridge", "buscar_por_caracteristica_atomica"),
                  ("iris.rag.contexto", "montar_contexto_estrategista")],
        "nota": "#16 OPEN (PR #68); busca exposta em /api/v1/rag/search",
    },
    {
        "etapa": "adaptador pedagogico (isolamento de escopo)",
        "alvos": [("iris.agents.adapter_agent", "AdapterAgent.adapt"),
                  ("iris.eval.escopo", "verificar_escopo")],
        "nota": "#18 OPEN; adapt() aplica laudo de escopo e saida de reserva",
    },
    {
        "etapa": "auditor de integridade (TRCC + circuit breaker max_retries=2)",
        "alvos": [("iris.eval.trcc", "avaliar_trcc")],
        "requer_simbolo": r"[Aa]uditor|max_retries",
        "nota": "#19 OPEN; so existe a metrica TRCC, sem agente auditor nem laco adaptador<->auditor",
    },
    {
        "etapa": "metricas e avaliacao (RAG, TRCC, legibilidade, benchmark)",
        "alvos": [("iris.eval.rag_metrics", "calcular_similaridade_semantica"),
                  ("iris.eval.executar", "executar_sistema"),
                  ("iris.eval.readability", None)],
        "exige_api": False,
        "nota": "#40/#45 CLOSED; avaliacao e offline por natureza; metricas do RAG servidas em /api/v1/eval/metrics",
    },
]


def existe(mods: dict[str, ModPy], mid: str, func: str | None) -> int | None:
    """Linha da definicao (ou 1 para modulo inteiro); None se ausente."""
    m = mods.get(mid)
    if not m:
        return None
    if func is None:
        return 1
    partes = func.split(".")
    corpo = m.arvore.body
    linha = None
    for parte in partes:
        achou = None
        for no in corpo:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and no.name == parte:
                achou = no
                break
        if not achou:
            return None
        linha, corpo = achou.lineno, getattr(achou, "body", [])
    return linha


def montar_etapas(mods, grafo, alcance_api, simb_testes, consumidores_scripts, todo_texto_src) -> list[dict]:
    saida = []
    for i, e in enumerate(ETAPAS, 1):
        presentes, ausentes, no_fluxo, fora, testados = [], [], [], [], []
        for mid, func in e["alvos"]:
            ref = f"{mid}:{func}" if func else mid
            linha = existe(mods, mid, func)
            if linha is None:
                ausentes.append(ref)
                continue
            presentes.append(f"{ref} (l.{linha})")
            if func is None:
                alc = any(n.startswith(mid + ":") for n in alcance_api)
            else:
                alc = f"{mid}:{func}" in alcance_api
            (no_fluxo if alc else fora).append(ref)
            chave = f"{mid}:{func.split('.')[0]}" if func else None
            if (chave and chave in simb_testes) or (func is None):
                testados.append(ref)
        falta_simbolo = bool(e.get("requer_simbolo")) and not re.search(e["requer_simbolo"], todo_texto_src)
        if not presentes:
            status = "ausente"
        elif ausentes or falta_simbolo or (fora and e.get("exige_api", True)):
            status = "parcial"
        else:
            status = "implementada"
        partes_ev = []
        if no_fluxo:
            partes_ev.append("alcancada pela API (main/api.routes): " + ", ".join(no_fluxo))
        if fora:
            via = []
            for ref in fora:
                quem = sorted(consumidores_scripts.get(ref.split(":")[0], ()))
                via.append(ref + (f" [so via {', '.join(quem)}]" if quem else " [nenhuma rota chama]"))
            rot = "existe mas fora do fluxo da API" if e.get("exige_api", True) else "fora da API (uso offline)"
            partes_ev.append(rot + ": " + ", ".join(via))
        if ausentes:
            partes_ev.append("ausente: " + ", ".join(ausentes))
        if falta_simbolo:
            partes_ev.append("nenhum simbolo casa /" + e["requer_simbolo"] + "/ em backend/src")
        partes_ev.append(e["nota"])
        principal = e["alvos"][0]
        saida.append(
            {
                "ordem": i,
                "etapa": e["etapa"],
                "modulo": principal[0] if presentes else "",
                "funcao": (principal[1] or "") if presentes else "",
                "status": status,
                "evidencia": "; ".join(partes_ev),
            }
        )
    return saida


# ---------------------------------------------------------------------------
# saidas


def mermaid(modulos, arestas, etapas) -> str:
    pasta_de = {m["id"]: m["pasta"] for m in modulos}
    peso: dict[tuple[str, str, str], int] = defaultdict(int)
    for a in arestas:
        pa, pb = pasta_de.get(a["de"]), pasta_de.get(a["para"])
        if pa and pb and pa != pb:
            peso[(pa, pb, a["tipo"])] += 1
    pastas = sorted({m["pasta"] for m in modulos})
    nid = {p: "P_" + re.sub(r"\W", "_", p) for p in pastas}
    n_mod = defaultdict(int)
    for m in modulos:
        n_mod[m["pasta"]] += 1
    linhas = ["%% Dependencias entre pastas (rotulo = numero de arestas modulo->modulo)", "flowchart LR"]
    grupos = {"backend (iris)": [p for p in pastas if not p.startswith(("frontend", "rag_pacote"))],
              "rag/iris-rag/pacote": [p for p in pastas if p.startswith("rag_pacote")],
              "frontend/src": [p for p in pastas if p.startswith("frontend")]}
    for i, (g, ps) in enumerate(grupos.items()):
        if not ps:
            continue
        linhas.append(f'  subgraph G{i}["{g}"]')
        for p in ps:
            linhas.append(f'    {nid[p]}["{p} ({n_mod[p]})"]')
        linhas.append("  end")
    for (pa, pb, tipo), n in sorted(peso.items()):
        if tipo == "import":
            linhas.append(f"  {nid[pa]} -->|{n}| {nid[pb]}")
    for (pa, pb, tipo), n in sorted(peso.items()):
        if tipo == "chamada" and (pa, pb, "import") not in peso:
            linhas.append(f"  {nid[pa]} -.->|HTTP {n}| {nid[pb]}")
    linhas += ["", "%% Etapas do pipeline (status no commit analisado)", "flowchart LR"]
    for e in etapas:
        rot = e["etapa"].split(" (")[0]
        alvo = f"{e['modulo'].replace('iris.', '')}:{e['funcao']}" if e["modulo"] else "sem codigo"
        linhas.append(f'  E{e["ordem"]}["{e["ordem"]}. {rot}<br/>{alvo}<br/>{e["status"]}"]:::{e["status"]}')
    for a, b in zip(etapas, etapas[1:]):
        linhas.append(f"  E{a['ordem']} --> E{b['ordem']}")
    linhas += [
        "  classDef implementada fill:#d8f0d8,stroke:#2e7d32",
        "  classDef parcial fill:#fff3cd,stroke:#b8860b",
        "  classDef ausente fill:#f8d7da,stroke:#a71d2a",
    ]
    return "\n".join(linhas) + "\n"


def texto_resumo(dado, ciclos_imp, n_casos, falhas) -> str:
    L = []
    met = dado["metricas"]
    L.append("MAPA DO CODIGO DO IRIS (analise estatica, ast + regex)")
    L.append(f"commit do grupo: {dado['commit_grupo']}   gerado em: {dado['gerado_em']}")
    L.append(
        f"modulos: {met['modulos']}   funcoes+metodos: {met['funcoes']}   arquivos de teste: {met['testes']} "
        f"({n_casos} funcoes test_*)   modulos sem teste: {met['modulos_sem_teste']}"
    )
    L.append("")
    L.append("1. MODULOS POR PASTA (modulos / linhas / funcoes+metodos)")
    por = defaultdict(list)
    for m in dado["modulos"]:
        por[m["pasta"]].append(m)
    for p in sorted(por):
        ms = por[p]
        nf = sum(len(m["funcoes"]) + sum(len(c["metodos"]) for c in m["classes"]) for m in ms)
        L.append(f"  {p:<24} {len(ms):>3} mod  {sum(m['linhas'] for m in ms):>6} lin  {nf:>4} func")
    L.append("")
    L.append("2. MAIS IMPORTADOS (por quantos modulos internos)")
    top = sorted(dado["modulos"], key=lambda m: (-len(m["importado_por"]), m["id"]))[:12]
    for m in top:
        if m["importado_por"]:
            L.append(f"  {len(m['importado_por']):>3}  {m['id']}")
    L.append("")
    L.append("3. USAM LLM (HybridLLMClient/get_llm_client ou cliente externo)")
    for m in dado["modulos"]:
        if m["usa_llm"]:
            L.append(f"  {m['id']}")
    L.append("")
    L.append("4. SEM TESTE (nenhum arquivo em backend/tests importa o modulo)")
    por_sem = defaultdict(list)
    caminho_de = {m["id"]: m["caminho"] for m in dado["modulos"]}
    for mid in dado["sem_teste"]:
        por_sem[next(m["pasta"] for m in dado["modulos"] if m["id"] == mid)].append(mid)
    for p in sorted(por_sem):
        L.append(f"  [{p}] " + ", ".join(Path(caminho_de[x]).name for x in por_sem[p]))
    L.append("  obs.: rag_pacote e frontend nao tem suite em backend/tests; contam como sem teste.")
    L.append("")
    L.append("5. ETAPAS DO PIPELINE")
    for e in dado["etapas_pipeline"]:
        L.append(f"  {e['ordem']:>2}. [{e['status']:<12}] {e['etapa']}")
        if e["modulo"]:
            L.append(f"      onde: {e['modulo']}:{e['funcao']}")
        L.append(f"      evidencia: {e['evidencia']}")
    L.append("")
    L.append("6. CICLOS DE IMPORT")
    if ciclos_imp:
        for c in ciclos_imp:
            L.append("  " + " <-> ".join(c))
        L.append("  obs.: ciclos envolvendo __init__ costumam ser reexportacao de pacote, nao erro de execucao.")
    else:
        L.append("  nenhum")
    if falhas:
        L.append("")
        L.append("7. ARQUIVOS QUE NAO FORAM PARSEADOS")
        L.extend("  " + f for f in falhas)
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--repo", required=True, type=Path, help="clone do repositorio do grupo (so leitura)")
    ap.add_argument("--saida", required=True, type=Path, help="pasta onde gravar 27-mapa-codigo.*")
    args = ap.parse_args(argv)
    repo = args.repo.resolve()
    if not (repo / SRC / "iris").is_dir():
        ap.error(f"{repo} nao parece o repositorio do Iris (falta backend/src/iris)")

    commit = git(repo, "rev-parse", "HEAD") or "desconhecido"
    mods, falhas = carregar_python(repo)
    coletar_imports(mods)

    # imports internos (modulo -> modulos)
    importa: dict[str, set[str]] = {}
    for m in mods.values():
        alvos = set()
        for nome in m.imports_brutos:
            im = modulo_interno(nome, mods)
            if im and im != m.id:
                alvos.add(im)
        importa[m.id] = alvos

    grafo = chamadas(mods)
    entrada = {n for n in grafo if n.startswith(("iris.main:", "iris.api.routes."))}
    for m in mods.values():
        if m.id == "iris.main" or m.id.startswith("iris.api.routes."):
            for qual, _, _ in unidades(m):
                entrada.add(f"{m.id}:{qual}")
    alcance_api = alcancaveis(grafo, entrada)

    por_teste, n_arq_teste, n_casos, simb_testes = carregar_testes(repo, mods)

    # consumidores fora do pacote (scripts/ na raiz do repositorio) para evidencia
    consumidores: dict[str, set[str]] = defaultdict(set)
    for p in sorted((repo / SCRIPTS).glob("*.py")) if (repo / SCRIPTS).is_dir() else []:
        try:
            arv = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for no in ast.walk(arv):
            if isinstance(no, ast.ImportFrom) and no.module:
                for al in no.names:
                    im = modulo_interno(no.module, mods)
                    if im:
                        dono = resolver_simbolo(im, al.name, mods)
                        consumidores[(dono or (im,))[0]].add(p.relative_to(repo).as_posix())

    todo_texto_src = "\n".join((repo / m.caminho).read_text(encoding="utf-8", errors="replace")
                               for m in mods.values() if m.id.startswith("iris"))

    modulos = []
    for mid in sorted(mods):
        m = mods[mid]
        funcs, classes = estrutura(m)
        usa_llm = mid == "iris.core.llm_client" or any(
            (orig.startswith("iris.core.llm_client") and (attr in NOMES_LLM or attr is None)) or local in NOMES_LLM
            for local, (orig, attr) in m.aliases.items()
        ) or any(n.split(".")[0] in LIBS_LLM for n in m.imports_brutos)
        modulos.append(
            {
                "id": mid,
                "caminho": m.caminho,
                "pasta": m.pasta,
                "linhas": m.linhas,
                "funcoes": funcs,
                "classes": classes,
                "importa": sorted(importa[mid]),
                "importado_por": [],
                "testado_por": sorted(por_teste.get(mid, ())),
                "usa_llm": bool(usa_llm),
                "tipo": "python",
            }
        )
    ts = carregar_ts(repo)
    rotas = rotas_api(mods)

    arestas = []
    vistos = set()
    for mid in sorted(importa):
        for b in sorted(importa[mid]):
            arestas.append({"de": mid, "para": b, "tipo": "import"})
    for t in ts:
        for b in t["importa"]:
            arestas.append({"de": t["id"], "para": b, "tipo": "import"})
    for origem, destinos in sorted(grafo.items()):
        ma = origem.split(":")[0]
        for d in sorted(destinos):
            mb = d.split(":")[0]
            if ma != mb and (ma, mb) not in vistos:
                vistos.add((ma, mb))
                arestas.append({"de": ma, "para": mb, "tipo": "chamada"})
    # frontend -> backend por HTTP (fetch para rota registrada no APIRouter)
    for t in ts:
        for ep in t.pop("_endpoints"):
            if ep in rotas and (t["id"], rotas[ep][0]) not in vistos:
                vistos.add((t["id"], rotas[ep][0]))
                arestas.append({"de": t["id"], "para": rotas[ep][0], "tipo": "chamada"})
    modulos.extend(ts)

    idx = {m["id"]: m for m in modulos}
    for a in arestas:
        if a["tipo"] == "import" and a["de"] in idx and a["para"] in idx:
            if a["de"] not in idx[a["para"]]["importado_por"]:
                idx[a["para"]]["importado_por"].append(a["de"])
    for m in modulos:
        m["importado_por"].sort()

    etapas = montar_etapas(mods, grafo, alcance_api, simb_testes, consumidores, todo_texto_src)
    sem_teste = [m["id"] for m in modulos if not m["testado_por"]]
    n_func = sum(len(m["funcoes"]) + sum(len(c["metodos"]) for c in m["classes"]) for m in modulos)
    dado = {
        "commit_grupo": commit,
        "gerado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "modulos": modulos,
        "arestas": arestas,
        "etapas_pipeline": etapas,
        "sem_teste": sem_teste,
        "metricas": {
            "modulos": len(modulos),
            "funcoes": n_func,
            "testes": n_arq_teste,
            "modulos_sem_teste": len(sem_teste),
        },
    }
    ciclos_imp = ciclos({k: v for k, v in importa.items()})

    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / f"{PREFIXO}.json").write_text(json.dumps(dado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.saida / f"{PREFIXO}.txt").write_text(texto_resumo(dado, ciclos_imp, n_casos, falhas), encoding="utf-8")
    (args.saida / f"{PREFIXO}.mmd").write_text(mermaid(modulos, arestas, etapas), encoding="utf-8")
    print(f"commit {commit[:7]}: {len(modulos)} modulos, {n_func} funcoes, {len(arestas)} arestas, "
          f"{n_arq_teste} arquivos de teste, {len(sem_teste)} modulos sem teste")
    for e in etapas:
        print(f"  {e['ordem']:>2}. {e['status']:<12} {e['etapa']}")
    print(f"gravado em {args.saida}/{PREFIXO}.{{json,txt,mmd}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
