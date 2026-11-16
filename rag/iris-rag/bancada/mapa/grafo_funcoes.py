"""Grafo de funções do código do grupo, feito aqui com o Python padrão (ast) e o networkx.

Substitui o GitNexus (licença não comercial) na tela "Grafo do código", com o mesmo formato de dados:
  * simbolos: cada função, método e classe, com arquivo, linha, tamanho, se é teste e a comunidade;
  * chamadas: pares [quem chama, quem é chamado], índices em ``simbolos``;
  * comunidades: grupos de funções que se chamam mais entre si do que com o resto (algoritmo de Louvain, semente fixa);
  * processos: a cadeia de chamadas mais longa a partir de cada ponto de entrada (função que ninguém chama e que chama
    outras), até 10 passos.

O código é lido, nunca executado. Uma chamada só vira ligação quando o nome se resolve pelo próprio módulo: função ou
classe do mesmo arquivo, ``self.metodo`` dentro da classe, nome importado (``from x import f``) ou ``modulo.funcao``
de módulo importado. O que não se resolve (método de objeto de outra biblioteca, por exemplo) fica de fora: o grafo
mostra só ligações certas, não todas as possíveis.

Uso:  python grafo_funcoes.py --repo <raiz do repositório> --saida <pasta>   (grava 29-grafo-funcoes.json)
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx

# (pasta, prefixo do nome do módulo) — como o código é importado em cada parte do repositório
RAIZES = (("backend/src", ""), ("backend/tests", "tests"), ("rag/iris-rag/pacote", ""), ("scripts", "scripts"))
FORA = (".venv", "node_modules", "site-packages", "__pycache__", "reports", "cache")
SEMENTE = 20261116
MAX_PASSOS = 10
MAX_PROCESSOS = 80


def modulos_do_repo(repo: Path) -> dict[str, Path]:
    """Nome do módulo -> arquivo, para cada .py das raízes do grupo."""
    saida: dict[str, Path] = {}
    for pasta, prefixo in RAIZES:
        raiz = repo / pasta
        if not raiz.is_dir():
            continue
        for arq in sorted(raiz.rglob("*.py")):
            if any(p in arq.parts for p in FORA):
                continue
            partes = list(arq.relative_to(raiz).with_suffix("").parts)
            if partes[-1] == "__init__":
                partes = partes[:-1]
            nome = ".".join(([prefixo] if prefixo else []) + partes)
            if nome:
                saida.setdefault(nome, arq)
    return saida


class Leitor(ast.NodeVisitor):
    """Lista os símbolos de um módulo e, depois, as chamadas de cada um."""

    def __init__(self, modulo: str, arquivo: Path, relativo: str) -> None:
        self.modulo, self.arquivo, self.relativo = modulo, arquivo, relativo
        self.simbolos: list[dict] = []
        self.corpos: list[tuple[str, ast.AST, str | None]] = []  # (qual, nó, classe)
        self.nomes: dict[str, str] = {}  # nome no módulo -> qual completo (modulo:nome)
        self.aliases: dict[str, str] = {}  # nome local -> módulo ou símbolo importado

    def ler(self, arvore: ast.Module) -> None:
        for no in arvore.body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._simbolo(no.name, no, "função", None)
            elif isinstance(no, ast.ClassDef):
                self._simbolo(no.name, no, "classe", None)
                for filho in no.body:
                    if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._simbolo(f"{no.name}.{filho.name}", filho, "método", no.name)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for a in no.names:
                    self.aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(no, ast.ImportFrom):
                base = self._absoluto(no.module or "", no.level)
                for a in no.names:
                    if a.name != "*":
                        self.aliases[a.asname or a.name] = f"{base}.{a.name}" if base else a.name

    def _absoluto(self, modulo: str, nivel: int) -> str:
        if not nivel:
            return modulo
        pacote = self.modulo.split(".")
        if self.arquivo.name != "__init__.py":
            pacote = pacote[:-1]
        pacote = pacote[: len(pacote) - (nivel - 1)] if nivel > 1 else pacote
        return ".".join([*pacote, modulo] if modulo else pacote)

    def _simbolo(self, nome: str, no: ast.AST, tipo: str, classe: str | None) -> None:
        qual = f"{self.modulo}:{nome}"
        teste = "tests" in Path(self.relativo).parts or nome.split(".")[-1].startswith("test")
        self.simbolos.append({"nome": nome.split(".")[-1], "qual": nome, "tipo": tipo, "arquivo": self.relativo,
                              "linha": no.lineno, "linhas": (getattr(no, "end_lineno", no.lineno) - no.lineno + 1),
                              "teste": teste, "_qual": qual})
        self.nomes[nome] = qual
        if tipo != "classe":
            self.corpos.append((qual, no, classe))


def resolver(alvo: ast.AST, leitor: Leitor, classe: str | None, todos: dict[str, int], modulos: set[str]) -> str | None:
    """O qual completo (modulo:nome) que a chamada alcança, ou None se não dá para saber."""
    if isinstance(alvo, ast.Name):
        if alvo.id in leitor.nomes:
            return leitor.nomes[alvo.id]
        origem = leitor.aliases.get(alvo.id)
        if origem and "." in origem:
            mod, nome = origem.rsplit(".", 1)
            for cand in (f"{mod}:{nome}",):
                if cand in todos:
                    return cand
        return None
    if isinstance(alvo, ast.Attribute) and isinstance(alvo.value, ast.Name):
        base, attr = alvo.value.id, alvo.attr
        if base in ("self", "cls") and classe:
            cand = f"{leitor.modulo}:{classe}.{attr}"
            return cand if cand in todos else None
        if base in leitor.nomes:  # Classe.metodo do mesmo módulo
            cand = f"{leitor.nomes[base]}.{attr}"
            return cand if cand in todos else None
        origem = leitor.aliases.get(base)
        if origem:
            if origem in modulos:  # modulo.funcao
                cand = f"{origem}:{attr}"
                return cand if cand in todos else None
            if "." in origem:  # ClasseImportada.metodo
                mod, nome = origem.rsplit(".", 1)
                cand = f"{mod}:{nome}.{attr}"
                return cand if cand in todos else None
    return None


def construir(repo: Path) -> dict:
    modulos = modulos_do_repo(repo)
    leitores: list[Leitor] = []
    for nome, arq in modulos.items():
        try:
            arvore = ast.parse(arq.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        lt = Leitor(nome, arq, str(arq.relative_to(repo)))
        lt.ler(arvore)
        leitores.append(lt)
    simbolos = [s for lt in leitores for s in lt.simbolos]
    indice = {s["_qual"]: i for i, s in enumerate(simbolos)}
    nomes_de_modulo = set(modulos)
    arestas: set[tuple[int, int]] = set()
    for lt in leitores:
        for qual, no, classe in lt.corpos:
            origem = indice[qual]
            for sub in ast.walk(no):
                if isinstance(sub, ast.Call):
                    destino = resolver(sub.func, lt, classe, indice, nomes_de_modulo)
                    if destino and destino != qual:
                        arestas.add((origem, indice[destino]))
    chamadas = sorted(arestas)

    g = nx.Graph()
    g.add_edges_from(chamadas)
    comunidades: list[dict] = []
    if g.number_of_edges():
        grupos = sorted(nx.community.louvain_communities(g, seed=SEMENTE), key=lambda c: (-len(c), min(c)))
        for k, membros in enumerate(grupos):
            cid = f"comm_{k}"
            for i in membros:
                simbolos[i]["comunidade"] = cid
            pastas = Counter(Path(simbolos[i]["arquivo"]).parent.name or Path(simbolos[i]["arquivo"]).stem for i in membros)
            nome = pastas.most_common(1)[0][0].replace("_", " ").capitalize()
            dentro = g.subgraph(membros).number_of_edges()
            borda = sum(1 for a, b in g.edges(membros) if (a in membros) != (b in membros))
            comunidades.append({"id": cid, "nome": nome, "coesao": round(dentro / max(1, dentro + borda), 2),
                                "n": len(membros)})

    dg = nx.DiGraph()
    dg.add_edges_from(chamadas)
    processos: list[dict] = []
    # ponto de entrada: função do produto que nenhuma outra função do produto chama (chamada vinda de teste não conta,
    # senão quase toda função testada deixaria de ser entrada) e que chama outras
    def chamada_por_produto(i: int) -> bool:
        return any(not simbolos[j]["teste"] for j in dg.predecessors(i))

    entradas = [i for i in dg.nodes
                if not simbolos[i]["teste"] and dg.out_degree(i) > 0 and not chamada_por_produto(i)]

    def mais_longo(i: int, visto: tuple[int, ...]) -> tuple[int, ...]:
        if len(visto) >= MAX_PASSOS:
            return visto
        melhor = visto
        for j in sorted(dg.successors(i)):
            if j not in visto:
                c = mais_longo(j, (*visto, j))
                if len(c) > len(melhor):
                    melhor = c
        return melhor

    for i in sorted(entradas):
        passos = mais_longo(i, (i,))
        if len(passos) >= 3:
            comms = {simbolos[p].get("comunidade") for p in passos}
            processos.append({"nome": f"{simbolos[passos[0]]['nome']} → {simbolos[passos[-1]]['nome']}",
                              "tipo": "cross_community" if len(comms) > 1 else "intra_community",
                              "passos": list(passos)})
    processos.sort(key=lambda p: (-len(p["passos"]), p["nome"]))
    total_processos = len(processos)
    for s in simbolos:
        s.pop("_qual", None)
    try:
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, check=False).stdout.strip()
    except OSError:
        commit = ""
    return {
        "ferramenta": "grafo próprio: ast do Python (funções e chamadas) e networkx (comunidades, algoritmo de Louvain)",
        "commit_grupo": commit,
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "simbolos": simbolos,
        "chamadas": [list(c) for c in chamadas],
        "comunidades": comunidades,
        "processos": processos[:MAX_PROCESSOS],
        "metricas": {"simbolos": len(simbolos), "chamadas": len(chamadas), "comunidades": len(comunidades),
                     "processos": total_processos,
                     "funcoes_backend": sum(1 for s in simbolos if s["arquivo"].startswith("backend/src") and s["tipo"] != "classe")},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="raiz do repositório do grupo")
    ap.add_argument("--saida", required=True, help="pasta onde gravar 29-grafo-funcoes.json")
    a = ap.parse_args()
    dados = construir(Path(a.repo).resolve())
    destino = Path(a.saida) / "29-grafo-funcoes.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    m = dados["metricas"]
    print(f"commit {dados['commit_grupo']}: {m['simbolos']} símbolos ({m['funcoes_backend']} funções e métodos em "
          f"backend/src), {m['chamadas']} chamadas, {m['comunidades']} comunidades, {m['processos']} fluxos")
    print(f"gravado em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
