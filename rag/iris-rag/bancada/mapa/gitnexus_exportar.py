"""gitnexus_exportar.py: grafo de funções do código do grupo, gerado com o GitNexus, para a camada 'funções' do painel.

O GitNexus (github.com/abhigyanpatwari/GitNexus, licença PolyForm Noncommercial 1.0.0) indexa um repositório num grafo
de conhecimento: símbolos (funções, métodos, classes), chamadas, comunidades (agrupamento por coesão) e fluxos
(caminhos de execução a partir de pontos de entrada). Aqui ele é só uma FERRAMENTA para gerar dados: nenhum código dele
entra no repositório, e o painel lê apenas o JSON produzido por este script. Uso não comercial (residência): ok pela
licença.

Cuidados (o `analyze` escreve AGENTS.md/CLAUDE.md, skills e hooks no repositório analisado):
  - nunca roda no clone do grupo nem no worktree privado: copia o commit pedido para uma pasta descartável sob ~;
  - usa --index-only --skip-agents-md --skip-skills e guarda o índice fora da cópia (GITNEXUS_STORAGE_PATH).

Uso:  python gitnexus_exportar.py --repo /caminho/clone-do-grupo [--ref origin/dev] --saida ../../pacote/outputs
Gera: <saida>/29-gitnexus.json  (só nomes, caminhos e linhas; nenhum trecho de código)
Precisa de Node >= 20 e rede para o `npx` baixar o pacote na primeira vez. Não é portão do vigia (é lento e externo).
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
ROTULOS = ("Function", "Method", "Class")
IGNORAR = ("docs/", "notebooks/", ".github/", ".agents/")


def sh(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 1500) -> str:
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])}… falhou ({r.returncode}): {(r.stdout + r.stderr)[-600:]}")
    return r.stdout


def tabela(md: str) -> list[list[str]]:
    """O `gitnexus cypher` devolve {"markdown": "| a | b |\\n| --- |..."}: converte em linhas."""
    linhas = [l for l in md.splitlines() if l.startswith("|")][2:]
    return [[c.strip() for c in l.strip().strip("|").split(" | ")] for l in linhas]


class Grafo:
    def __init__(self, copia: Path, indice: Path):
        self.copia, self.env = copia, {"GITNEXUS_STORAGE_PATH": str(indice), "HOME": os.environ.get("HOME", str(Path.home()))}

    def analisar(self) -> str:
        return sh(["npx", "-y", f"gitnexus@{VERSAO}", "analyze", "--index-only", "--skip-agents-md", "--skip-skills"],
                  cwd=self.copia, env={**self.env, "GITNEXUS_WORKER_POOL_SIZE": "2"})

    def q(self, cypher: str) -> list[list[str]]:
        # a CLI encerra o processo antes de esvaziar um pipe grande (corta em 64 KB): a saída vai para um arquivo
        arq = self.copia.parent / "cypher.json"
        with arq.open("w", encoding="utf-8") as f:
            r = subprocess.run(["npx", "-y", f"gitnexus@{VERSAO}", "cypher", "-l", "100000", cypher], cwd=self.copia,
                               env={**os.environ, **self.env}, stdout=f, stderr=subprocess.PIPE, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"gitnexus cypher falhou: {r.stderr[-400:]}")
        out = arq.read_text(encoding="utf-8")
        corpo = out[out.index("{"):out.rindex("}") + 1]
        return tabela(json.loads(corpo).get("markdown", ""))


def exportar(repo: Path, ref: str, saida: Path) -> dict:
    base = Path(tempfile.mkdtemp(prefix="gitnexus-", dir=Path.home()))      # o Chromium/snap e o earlyoom preferem ~
    try:
        copia, indice = base / "repo", base / "indice"
        sha = sh(["git", "-C", str(repo), "rev-parse", ref]).strip()
        sh(["git", "clone", "-q", "--no-hardlinks", str(repo), str(copia)])
        sh(["git", "-C", str(copia), "checkout", "-q", sha])
        g = Grafo(copia, indice)
        resumo = [l.strip() for l in g.analisar().splitlines() if "nodes" in l or "indexed" in l]
        simb = g.q("MATCH (n) WHERE label(n) IN ['Function','Method','Class'] "
                   "RETURN n.id, label(n), n.name, n.filePath, n.startLine, n.endLine")
        membro = g.q("MATCH (a)-[r:CodeRelation]->(c:Community) WHERE r.type='MEMBER_OF' RETURN a.id, c.id")
        comun = g.q("MATCH (c:Community) RETURN c.id, c.label, c.cohesion, c.symbolCount")
        chamadas = g.q("MATCH (a)-[r:CodeRelation]->(b) WHERE r.type='CALLS' AND label(a) IN ['Function','Method','Class'] "
                       "AND label(b) IN ['Function','Method','Class'] RETURN a.id, b.id, r.confidence")
        proc = g.q("MATCH (p:Process) RETURN p.id, p.label, p.processType, p.stepCount")
        passos = g.q("MATCH (a)-[r:CodeRelation]->(p:Process) WHERE r.type='STEP_IN_PROCESS' RETURN a.id, p.id, r.step")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    simbolos, idx = [], {}
    for sid, rot, nome, arq, ini, fim in simb:
        if arq.startswith(IGNORAR):
            continue
        idx[sid] = len(simbolos)
        teste = "/tests/" in arq or Path(arq).name.startswith("test_")
        simbolos.append({"nome": nome.split(".")[-1] if rot == "Method" else nome, "qual": sid.split(":", 2)[-1].split("#")[0],
                         "tipo": {"Function": "função", "Method": "método", "Class": "classe"}[rot], "arquivo": arq,
                         "linha": int(ini) if ini.isdigit() else None, "linhas": (int(fim) - int(ini) + 1) if ini.isdigit() and fim.isdigit() else None,
                         "teste": teste, "comunidade": None})
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
    processos = [{"nome": nome, "tipo": tipo, "passos": [i for _, i in sorted(por_proc[pid])]}
                 for pid, nome, tipo, _ in proc if len(por_proc.get(pid, [])) >= 2]
    processos.sort(key=lambda p: -len(p["passos"]))
    dado = {"ferramenta": f"GitNexus {VERSAO} (PolyForm Noncommercial 1.0.0; usado só para gerar estes dados)",
            "commit_grupo": sha[:7], "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resumo_gitnexus": resumo, "simbolos": simbolos, "chamadas": arestas,
            "comunidades": sorted([c for c in comunidades.values() if c["n"]], key=lambda c: -c["n"]),
            "processos": processos[:80],
            "metricas": {"simbolos": len(simbolos), "chamadas": len(arestas),
                         "comunidades": sum(1 for c in comunidades.values() if c["n"]), "processos": len(processos)}}
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "29-gitnexus.json").write_text(json.dumps(dado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return dado["metricas"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--ref", default="origin/dev")
    ap.add_argument("--saida", required=True, type=Path)
    a = ap.parse_args()
    print("29-gitnexus.json:", exportar(a.repo, a.ref, a.saida))
