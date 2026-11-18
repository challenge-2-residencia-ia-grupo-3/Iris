"""Mapa do código do backend, para a aba "Grafo do código" do playground.

Duas camadas:
- Módulos: calculada na hora, lendo o próprio código com `ast` (biblioteca padrão). Diz quem importa quem,
  que módulo não é importado por nenhum teste e que módulo toca o removedor de dado pessoal.
- Funções: lida de `rag/iris-rag/pacote/outputs/29-grafo-funcoes.json`, o grafo próprio das Verificações de qualidade
  (`rag/iris-rag/bancada/mapa/grafo_funcoes.py`: ast do Python e networkx). Sem o arquivo, a camada diz como gerar.

O que este mapa NÃO diz: se um teste é bom. "Tem teste" aqui é só "algum arquivo de teste importa o módulo".
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from iris.config import REPO_ROOT

RAIZ_PACOTE = Path(__file__).resolve().parents[1]  # backend/src/iris
PASTA_TESTES = RAIZ_PACOTE.parents[1] / "tests"  # backend/tests
FUNCOES_PADRAO = REPO_ROOT / "rag" / "iris-rag" / "pacote" / "outputs" / "29-grafo-funcoes.json"
MODULO_PII = "iris.security.pii_scrubber"
MAX_SIMBOLOS = 4000
MAX_COMUNIDADES = 40
MAX_PROCESSOS = 40

NOME_PACOTE = {
    "raiz": "Entrada e configuração",
    "agents": "Agentes",
    "api": "Rotas da API",
    "core": "Cliente de modelo",
    "eval": "Avaliação",
    "parsers": "Leitura de material",
    "rag": "Ponte com o RAG",
    "schemas": "Contratos de dados",
    "security": "Segurança e dado pessoal",
}


def _id_modulo(arquivo: Path, raiz: Path) -> str:
    partes = list(arquivo.relative_to(raiz.parent).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


def _alvos_importados(arvore: ast.AST, modulo: str, e_pacote: bool, conhecidos: set[str]) -> set[str]:
    """Módulos do projeto citados nos `import` do arquivo, com os relativos resolvidos.

    `from pacote import nome`: se `pacote.nome` é um módulo, conta só ele; se é uma função ou classe,
    conta o próprio pacote.
    """
    alvos: set[str] = set()
    pacote = modulo.split(".") if e_pacote else modulo.split(".")[:-1]
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            alvos.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            if no.level:
                base = pacote[: len(pacote) - (no.level - 1)]
                origem = ".".join(base + ([no.module] if no.module else []))
            else:
                origem = no.module or ""
            if origem:
                for a in no.names:
                    sub = f"{origem}.{a.name}"
                    alvos.add(sub if sub in conhecidos else origem)
    return {a for a in alvos if a in conhecidos}


def mapear_modulos(raiz: Path | None = None, pasta_testes: Path | None = None) -> dict[str, Any]:
    """Lê os arquivos `.py` do pacote e dos testes e devolve módulos, importações e contagens."""
    raiz = Path(raiz) if raiz else RAIZ_PACOTE
    pasta_testes = Path(pasta_testes) if pasta_testes else PASTA_TESTES
    nome_raiz = raiz.name

    arvores: dict[str, tuple[Path, ast.AST]] = {}
    erros: list[str] = []
    for arquivo in sorted(raiz.rglob("*.py")):
        try:
            arvores[_id_modulo(arquivo, raiz)] = (arquivo, ast.parse(arquivo.read_text(encoding="utf-8")))
        except (SyntaxError, UnicodeDecodeError) as exc:
            erros.append(f"{arquivo.name}: {type(exc).__name__}")
    conhecidos = set(arvores)

    testado_por: dict[str, set[str]] = {m: set() for m in conhecidos}
    arquivos_de_teste = sorted(pasta_testes.rglob("test_*.py")) if pasta_testes.exists() else []
    for arquivo in arquivos_de_teste:
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            erros.append(f"{arquivo.name}: {type(exc).__name__}")
            continue
        for alvo in _alvos_importados(arvore, arquivo.stem, False, conhecidos):
            testado_por[alvo].add(arquivo.name)

    modulos: list[dict[str, Any]] = []
    importa: dict[str, set[str]] = {}
    for mid, (arquivo, arvore) in arvores.items():
        e_pacote = arquivo.name == "__init__.py"
        importa[mid] = _alvos_importados(arvore, mid, e_pacote, conhecidos) - {mid}
        partes = mid.split(".")
        pacote = partes[1] if len(partes) > 2 or (len(partes) == 2 and e_pacote) else "raiz"
        fonte = arquivo.read_text(encoding="utf-8")
        modulos.append(
            {
                "id": mid,
                "nome": partes[-1] if not e_pacote else f"{partes[-1]} (pacote)",
                "pacote": pacote,
                "arquivo": str(arquivo.relative_to(raiz.parents[2])),  # a partir da raiz do repositório, como no grafo de funções
                "linhas": fonte.count("\n") + 1,
                "funcoes": sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(arvore)),
                "classes": sum(isinstance(n, ast.ClassDef) for n in ast.walk(arvore)),
                "vazio": not any(not isinstance(n, (ast.Expr, ast.Import, ast.ImportFrom)) for n in arvore.body),  # type: ignore[attr-defined]
            }
        )
    importado_por: dict[str, set[str]] = {m: set() for m in conhecidos}
    for origem, destinos in importa.items():
        for destino in destinos:
            importado_por[destino].add(origem)

    for m in modulos:
        mid = m["id"]
        m["importa"] = sorted(importa[mid])
        m["importado_por"] = sorted(importado_por[mid])
        m["testado_por"] = sorted(testado_por[mid])
        m["pii"] = "define" if mid == MODULO_PII else ("usa" if MODULO_PII in importa[mid] else None)

    ordem = [p for p in NOME_PACOTE if any(m["pacote"] == p for m in modulos)]
    ordem += sorted({m["pacote"] for m in modulos} - set(ordem))
    pacotes = [
        {
            "id": p,
            "nome": NOME_PACOTE.get(p, p),
            "modulos": sorted(m["id"] for m in modulos if m["pacote"] == p),
        }
        for p in ordem
    ]
    com_codigo = [m for m in modulos if not m["vazio"]]
    sem_teste = sorted(m["id"] for m in com_codigo if not m["testado_por"])
    return {
        "raiz": nome_raiz,
        "modulos": sorted(modulos, key=lambda m: m["id"]),
        "pacotes": pacotes,
        "sem_teste": sem_teste,
        "metricas": {
            "modulos": len(modulos),
            "modulos_com_codigo": len(com_codigo),
            "importacoes": sum(len(v) for v in importa.values()),
            "arquivos_de_teste": len(arquivos_de_teste),
            "modulos_sem_teste": len(sem_teste),
            "modulos_que_tocam_pii": sum(1 for m in modulos if m["pii"]),
            "linhas": sum(m["linhas"] for m in modulos),
        },
        "erros_de_leitura": erros,
    }


def carregar_funcoes(caminho: str | Path | None = None) -> dict[str, Any]:
    """Lê a camada de funções do grafo próprio; sem o arquivo, diz como gerar."""
    origem = Path(caminho) if caminho else FUNCOES_PADRAO
    como_gerar = "make -C rag/iris-rag/pacote grafo"
    if not origem.exists():
        return {
            "disponivel": False,
            "motivo": "A camada de funções ainda não foi gerada neste computador.",
            "como_gerar": como_gerar,
            "exige": "só o Python do projeto (ast e networkx); leva menos de 1 segundo.",
        }
    try:
        dado = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"disponivel": False, "motivo": f"Arquivo ilegível ({type(exc).__name__}).", "como_gerar": como_gerar}

    simbolos = dado.get("simbolos", [])
    nome_comunidade = {c["id"]: c["nome"] for c in dado.get("comunidades", [])}
    chamado_por = [0] * len(simbolos)
    chama = [0] * len(simbolos)
    for a, b in dado.get("chamadas", []):
        if 0 <= a < len(simbolos) and 0 <= b < len(simbolos):
            chama[a] += 1
            chamado_por[b] += 1

    def rotulo(i: int) -> dict[str, Any]:
        s = simbolos[i]
        return {"nome": s["nome"], "arquivo": s["arquivo"], "linha": s.get("linha")}

    return {
        "disponivel": True,
        "ferramenta": dado.get("ferramenta"),
        "commit": dado.get("commit_grupo"),
        "gerado_em": dado.get("gerado_em"),
        "metricas": dado.get("metricas", {}),
        "comunidades": [
            {"nome": c["nome"], "simbolos": c["n"], "coesao": c.get("coesao")}
            for c in dado.get("comunidades", [])[:MAX_COMUNIDADES]
        ],
        "comunidades_total": len(dado.get("comunidades", [])),
        "processos": [
            {
                "nome": p["nome"],
                "tipo": p.get("tipo"),
                "passos": [rotulo(i) for i in p["passos"] if 0 <= i < len(simbolos)],
            }
            for p in dado.get("processos", [])[:MAX_PROCESSOS]
        ],
        "processos_total": dado.get("metricas", {}).get("processos", len(dado.get("processos", []))),
        "simbolos": [
            {
                "nome": s["nome"],
                "tipo": s["tipo"],
                "arquivo": s["arquivo"],
                "linha": s.get("linha"),
                "teste": bool(s.get("teste")),
                "comunidade": nome_comunidade.get(s.get("comunidade")),
                "chama": chama[i],
                "chamado_por": chamado_por[i],
            }
            for i, s in enumerate(simbolos[:MAX_SIMBOLOS])
        ],
        "simbolos_total": len(simbolos),
    }


def obter_mapa_codigo(caminho_funcoes: str | Path | None = None) -> dict[str, Any]:
    """As duas camadas do mapa: módulos (sempre) e funções (quando o grafo de funções já foi gerado)."""
    return {"modulos": mapear_modulos(), "funcoes": carregar_funcoes(caminho_funcoes)}
