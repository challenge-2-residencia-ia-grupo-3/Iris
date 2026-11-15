"""Gera a camada de funções da aba "Grafo do código" do playground, com o GitNexus.

O GitNexus (github.com/abhigyanpatwari/GitNexus, licença PolyForm Noncommercial 1.0.0) indexa um repositório
num grafo: símbolos (funções, métodos, classes), chamadas, comunidades (agrupamento por coesão) e fluxos
(caminhos de execução a partir de pontos de entrada). Aqui ele é só uma FERRAMENTA que gera um arquivo: nenhum
código dele entra no repositório, e o painel lê apenas o JSON produzido por este script.

Cuidados (o `analyze` escreve AGENTS.md, CLAUDE.md, skills e hooks no repositório analisado):
  - nunca roda na sua cópia de trabalho: copia o commit pedido para uma pasta descartável e apaga no fim;
  - usa --index-only --skip-agents-md --skip-skills e guarda o índice fora da cópia.

Uso:  python scripts/exportar_gitnexus.py --repo . --ref HEAD --saida reports/gitnexus.json
Gera um JSON só com nomes, caminhos e linhas (nenhum trecho de código).
Precisa de Node >= 20 e de rede para o `npx` baixar o pacote na primeira vez. Leva cerca de 2 minutos.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSAO = "1.6.12"
IGNORAR = ("docs/", "notebooks/", ".github/", ".agents/")
TIPO = {"Function": "função", "Method": "método", "Class": "classe"}


def sh(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 1500) -> str:
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])}… falhou ({r.returncode}): {(r.stdout + r.stderr)[-600:]}")
    return r.stdout


def tabela(md: str) -> list[list[str]]:
    """O `gitnexus cypher` devolve {"markdown": "| a | b |\\n| --- |..."}: converte em linhas."""
    linhas = [linha for linha in md.splitlines() if linha.startswith("|")][2:]
    return [[c.strip() for c in linha.strip().strip("|").split(" | ")] for linha in linhas]


class Grafo:
    def __init__(self, copia: Path, indice: Path) -> None:
        self.copia = copia
        self.env = {"GITNEXUS_STORAGE_PATH": str(indice), "HOME": os.environ.get("HOME", str(Path.home()))}

    def analisar(self) -> str:
        return sh(
            ["npx", "-y", f"gitnexus@{VERSAO}", "analyze", "--index-only", "--skip-agents-md", "--skip-skills"],
            cwd=self.copia,
            env={**self.env, "GITNEXUS_WORKER_POOL_SIZE": "2"},
        )

    def q(self, cypher: str) -> list[list[str]]:
        # a CLI encerra o processo antes de esvaziar um pipe grande (corta em 64 KB): a saída vai para um arquivo
        arq = self.copia.parent / "cypher.json"
        with arq.open("w", encoding="utf-8") as f:
            r = subprocess.run(
                ["npx", "-y", f"gitnexus@{VERSAO}", "cypher", "-l", "100000", cypher],
                cwd=self.copia,
                env={**os.environ, **self.env},
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
            )
        if r.returncode != 0:
            raise RuntimeError(f"gitnexus cypher falhou: {r.stderr[-400:]}")
        out = arq.read_text(encoding="utf-8")
        corpo = out[out.index("{") : out.rindex("}") + 1]
        return tabela(json.loads(corpo).get("markdown", ""))


def montar(simb, membro, comun, chamadas, proc, passos, sha: str, resumo: list[str]) -> dict:
    """Transforma as tabelas do GitNexus no JSON que o painel lê. Separada para poder ser testada sem Node."""
    simbolos, idx = [], {}
    for sid, rot, nome, arq, ini, fim in simb:
        if arq.startswith(IGNORAR) or rot not in TIPO:
            continue
        idx[sid] = len(simbolos)
        simbolos.append(
            {
                "nome": nome.split(".")[-1] if rot == "Method" else nome,
                "tipo": TIPO[rot],
                "arquivo": arq,
                "linha": int(ini) + 1 if ini.isdigit() else None,  # o GitNexus conta a partir de 0
                "linhas": (int(fim) - int(ini) + 1) if ini.isdigit() and fim.isdigit() else None,
                "teste": "/tests/" in arq or Path(arq).name.startswith("test_"),
                "comunidade": None,
            }
        )
    comunidades = {c[0]: {"id": c[0], "nome": c[1], "coesao": round(float(c[2] or 0), 2), "n": 0} for c in comun}
    for a, c in membro:
        if a in idx and c in comunidades:
            simbolos[idx[a]]["comunidade"] = c
            comunidades[c]["n"] += 1
    arestas = sorted({(idx[a], idx[b]) for a, b, _ in chamadas if a in idx and b in idx and a != b})
    por_proc: dict[str, list] = {}
    for a, p, s in passos:
        if a in idx:
            por_proc.setdefault(p, []).append((int(s) if s.isdigit() else 0, idx[a]))
    processos = [
        {"nome": nome, "tipo": tipo, "passos": [i for _, i in sorted(por_proc[pid])]}
        for pid, nome, tipo, _ in proc
        if len(por_proc.get(pid, [])) >= 2
    ]
    processos.sort(key=lambda p: (-len(p["passos"]), p["nome"]))
    return {
        "ferramenta": f"GitNexus {VERSAO} (PolyForm Noncommercial 1.0.0; usado só para gerar estes dados)",
        "commit_grupo": sha[:7],
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resumo_gitnexus": resumo,
        "simbolos": simbolos,
        "chamadas": [list(par) for par in arestas],
        "comunidades": sorted([c for c in comunidades.values() if c["n"]], key=lambda c: (-c["n"], c["id"])),
        "processos": processos[:80],
        "metricas": {
            "simbolos": len(simbolos),
            "chamadas": len(arestas),
            "comunidades": sum(1 for c in comunidades.values() if c["n"]),
            "processos": len(processos),
        },
    }


def exportar(repo: Path, ref: str, saida: Path) -> dict:
    base = Path(tempfile.mkdtemp(prefix="gitnexus-", dir=Path.home()))
    try:
        copia, indice = base / "repo", base / "indice"
        sha = sh(["git", "-C", str(repo), "rev-parse", ref]).strip()
        sh(["git", "clone", "-q", "--no-hardlinks", str(repo), str(copia)])
        sh(["git", "-C", str(copia), "checkout", "-q", sha])
        g = Grafo(copia, indice)
        resumo = [linha.strip() for linha in g.analisar().splitlines() if "nodes" in linha or "indexed" in linha]
        simb = g.q(
            "MATCH (n) WHERE label(n) IN ['Function','Method','Class'] "
            "RETURN n.id, label(n), n.name, n.filePath, n.startLine, n.endLine"
        )
        membro = g.q("MATCH (a)-[r:CodeRelation]->(c:Community) WHERE r.type='MEMBER_OF' RETURN a.id, c.id")
        comun = g.q("MATCH (c:Community) RETURN c.id, c.label, c.cohesion, c.symbolCount")
        chamadas = g.q(
            "MATCH (a)-[r:CodeRelation]->(b) WHERE r.type='CALLS' AND label(a) IN ['Function','Method','Class'] "
            "AND label(b) IN ['Function','Method','Class'] RETURN a.id, b.id, r.confidence"
        )
        proc = g.q("MATCH (p:Process) RETURN p.id, p.label, p.processType, p.stepCount")
        passos = g.q("MATCH (a)-[r:CodeRelation]->(p:Process) WHERE r.type='STEP_IN_PROCESS' RETURN a.id, p.id, r.step")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    dado = montar(simb, membro, comun, chamadas, proc, passos, sha, resumo)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(dado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return dado["metricas"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--saida", required=True, type=Path)
    a = ap.parse_args()
    print(f"{a.saida}:", exportar(a.repo.resolve(), a.ref, a.saida.resolve()))
