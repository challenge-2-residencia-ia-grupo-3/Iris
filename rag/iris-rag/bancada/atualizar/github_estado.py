"""github_estado.py: retrato do GitHub do grupo (PRs e issues abertos, últimas execuções do CI) para o painel.

SÓ LEITURA: usa `gh pr list`, `gh issue list` e `gh api .../actions/runs` (GET). Nunca comenta, nunca cria nada.

Uso:  python3 github_estado.py --saida ../../pacote/outputs [--repo dono/repo]
Gera: <saida>/30-github.json com o contrato:
  {"gerado_em", "repo",
   "prs":    [{numero, titulo, autor, criado_em, idade_dias, branch, base, sha(7), rascunho, revisao, arquivos,
               ci: sucesso|falha|pendente|sem_check, issues, url}],
   "issues": [{numero, titulo, tipo, donos, rotulos, criado_em, idade_dias, prs, url}],
   "ci_historico": [{sha(7), branch, evento, conclusao, tentativa, criado_em, workflow}],
   "instaveis":    [{sha, branch, conclusoes}],   # mesmo sha com sucesso E falha (teste instável ou re-run)
   "erro": null | mensagem}

Se o gh falhar (sem rede, sem login), grava o arquivo com listas vazias e 'erro' preenchido e sai com código 0:
o painel mostra o estado vazio em vez de quebrar a rodada.

Observação: `gh run list` não expõe o número da tentativa (run_attempt); por isso o histórico do CI vem da API REST
(`repos/<repo>/actions/runs?per_page=100`), que traz `run_attempt`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = "challenge-2-residencia-ia-grupo-3/Iris"
TIPOS = ("story", "epic", "theme", "bug")
# "Refs #19", "Closes #9", "fixes: #12", "Resolves #3, #4" (só a primeira referência após o verbo conta, mais as listadas com vírgula)
RE_VERBO = re.compile(r"\b(?:refs?|closes?|closed|fix(?:es|ed)?|resolves?|resolved)\b\s*:?\s*((?:#\d+[\s,e&]*)+)", re.I)
RE_TITULO = re.compile(r"\(#(\d+)\)")


def gh(*args: str, timeout: int = 90):
    env = {**os.environ, "HOME": os.environ.get("HOME") or str(Path.home()), "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} falhou ({r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}")
    return json.loads(r.stdout or "null")


def idade_dias(iso: str | None, agora: datetime) -> float | None:
    if not iso:
        return None
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return round((agora - t).total_seconds() / 86400, 1)


def issues_citadas(titulo: str, corpo: str) -> list[int]:
    nums = set()
    for m in RE_VERBO.finditer(corpo or ""):
        nums.update(int(n) for n in re.findall(r"#(\d+)", m.group(1)))
    nums.update(int(n) for n in RE_TITULO.findall(titulo or ""))
    return sorted(nums)


def ci_do_pr(rollup: list[dict]) -> str:
    """Resume o statusCheckRollup: CheckRun (status/conclusion) e StatusContext (state)."""
    if not rollup:
        return "sem_check"
    estados = []
    for c in rollup:
        if c.get("__typename") == "StatusContext" or "state" in c and "status" not in c:
            s = (c.get("state") or "").upper()
            estados.append("pendente" if s in ("PENDING", "EXPECTED") else "sucesso" if s == "SUCCESS" else "falha")
        else:
            if (c.get("status") or "").upper() != "COMPLETED":
                estados.append("pendente")
            else:
                conc = (c.get("conclusion") or "").upper()
                estados.append("sucesso" if conc in ("SUCCESS", "SKIPPED", "NEUTRAL") else "falha")
    if "falha" in estados:
        return "falha"
    if "pendente" in estados:
        return "pendente"
    return "sucesso"


def coletar(repo: str) -> dict:
    agora = datetime.now(timezone.utc)
    prs_raw = gh("pr", "list", "-R", repo, "--state", "open", "--limit", "100", "--json",
                 "number,title,author,createdAt,headRefName,baseRefName,headRefOid,isDraft,reviewDecision,body,files,"
                 "statusCheckRollup,url")
    iss_raw = gh("issue", "list", "-R", repo, "--state", "open", "--limit", "200", "--json",
                 "number,title,author,createdAt,labels,assignees,url")
    runs_raw = gh("api", f"repos/{repo}/actions/runs?per_page=100")
    prs = []
    for p in sorted(prs_raw, key=lambda x: x["number"], reverse=True):
        prs.append({
            "numero": p["number"], "titulo": p["title"], "autor": (p.get("author") or {}).get("login"),
            "criado_em": p["createdAt"], "idade_dias": idade_dias(p["createdAt"], agora),
            "branch": p["headRefName"], "base": p["baseRefName"], "sha": (p["headRefOid"] or "")[:7],
            "rascunho": bool(p.get("isDraft")), "revisao": p.get("reviewDecision") or None,
            "arquivos": [f["path"] for f in (p.get("files") or [])], "ci": ci_do_pr(p.get("statusCheckRollup") or []),
            "issues": issues_citadas(p["title"], p.get("body") or ""), "url": p["url"],
        })
    citadas: dict[int, list[int]] = {}
    for p in prs:
        for n in p["issues"]:
            citadas.setdefault(n, []).append(p["numero"])
    issues = []
    for i in sorted(iss_raw, key=lambda x: x["number"]):
        rot = [l["name"] for l in i.get("labels") or []]
        tipo = next((r.split(":", 1)[1].strip() for r in rot
                     if r.lower().startswith("type:") and r.split(":", 1)[1].strip().lower() in TIPOS), None)
        issues.append({
            "numero": i["number"], "titulo": i["title"], "tipo": tipo,
            "donos": [a["login"] for a in i.get("assignees") or []], "rotulos": rot,
            "criado_em": i["createdAt"], "idade_dias": idade_dias(i["createdAt"], agora),
            "prs": sorted(citadas.get(i["number"], [])), "url": i["url"],
        })
    hist = []
    for r in (runs_raw or {}).get("workflow_runs", [])[:100]:
        hist.append({"sha": (r.get("head_sha") or "")[:7], "branch": r.get("head_branch"), "evento": r.get("event"),
                     "conclusao": r.get("conclusion") or r.get("status"), "tentativa": r.get("run_attempt"),
                     "criado_em": r.get("created_at"), "workflow": r.get("name")})
    # instável: o mesmo sha (e workflow) teve sucesso e falha; re-run com conclusões diferentes cai aqui
    por_sha: dict[tuple, list[str]] = {}
    for h in hist:
        por_sha.setdefault((h["sha"], h["branch"], h["workflow"]), []).append(h["conclusao"])
    instaveis = [{"sha": s, "branch": b, "conclusoes": c} for (s, b, _w), c in por_sha.items()
                 if "success" in c and "failure" in c]
    return {"gerado_em": agora.astimezone().isoformat(timespec="seconds"), "repo": repo, "prs": prs,
            "issues": issues, "ci_historico": hist, "instaveis": instaveis, "erro": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--saida", required=True, help="pasta onde gravar 30-github.json")
    ap.add_argument("--repo", default=REPO)
    a = ap.parse_args()
    try:
        dado = coletar(a.repo)
    except Exception as e:                              # sem rede/sem login: estado vazio, painel não quebra
        dado = {"gerado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "repo": a.repo,
                "prs": [], "issues": [], "ci_historico": [], "instaveis": [], "erro": str(e)[-500:]}
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    tmp = saida / ".30-github.json.novo"
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, saida / "30-github.json")
    print(f"30-github.json: {len(dado['prs'])} PRs, {len(dado['issues'])} issues, {len(dado['ci_historico'])} execuções "
          f"de CI, {len(dado['instaveis'])} sha instáveis" + (f"; ERRO: {dado['erro']}" if dado["erro"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
