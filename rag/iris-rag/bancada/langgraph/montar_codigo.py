"""montar_codigo.py: monta uma cópia do código do grupo com os agentes que ainda estão em PR.

Pense numa fotocópia: tiramos uma cópia do ramo dev e colamos por cima só as páginas novas dos PRs
(Estrategista, Auditor e a ligação Auditor -> Adaptador). O clone do grupo só é LIDO (git archive e
git show); nada é escrito nele.

Regras:
  * arquivo novo do PR (não existe no dev) entra sempre;
  * arquivo que já existe no dev só é trocado pela versão do PR se o dev não mexeu nele desde que o
    PR saiu do dev (o blob do dev é igual ao da base do PR); senão fica o do dev e vira limitação;
  * __init__.py que dois PRs mudam de jeitos diferentes fica como no dev (os módulos são importados
    pelo caminho completo, então não faz falta).

Uso:
    python montar_codigo.py [--destino PASTA]
Grava MONTAGEM.json no destino com os shas usados.
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
import os
from pathlib import Path

sys.dont_write_bytecode = True

GRUPO = Path(os.environ.get("GRUPO", "../Iris")).expanduser()  # clone do repositório do grupo; passe GRUPO=caminho
DESTINO_PADRAO = Path(os.environ.get("IRIS_MONTADO") or (Path(__file__).resolve().parent / ".montado"))

# (ref do PR, rótulo, arquivos que entram)
SOBREPOSICOES = [
    ("origin/pr/81", "PR #81", ["backend/src/iris/agents/strategist_agent.py", "backend/src/iris/schemas/strategy.py"]),
    ("origin/pr/74", "PR #74", ["backend/src/iris/agents/auditor.py"]),
    ("origin/pr/80", "PR #80", ["backend/src/iris/agents/adapter_agent.py", "backend/src/iris/schemas/adaptation.py"]),
]
# mudanças dos PRs deixadas de fora de propósito (conflitam entre si e não fazem falta ao protótipo)
DEIXADOS_DE_FORA = [
    ("PR #80 e PR #81", "backend/src/iris/agents/__init__.py",
     "os dois PRs mudam o mesmo __init__ de jeitos diferentes; ficou o do dev (importamos os módulos pelo nome completo)"),
    ("PR #81", "backend/src/iris/schemas/__init__.py",
     "só acrescenta reexportações de strategy; ficou o do dev"),
]


def git(*args: str, binario: bool = False):
    r = subprocess.run(["git", "-C", str(GRUPO), *args], capture_output=True, check=True, timeout=120)
    return r.stdout if binario else r.stdout.decode().strip()


def existe(ref: str, caminho: str) -> bool:
    r = subprocess.run(["git", "-C", str(GRUPO), "cat-file", "-e", f"{ref}:{caminho}"], capture_output=True)
    return r.returncode == 0


def montar(destino: Path = DESTINO_PADRAO) -> dict:
    destino = destino.expanduser().resolve()
    if GRUPO.resolve() in (destino, *destino.parents):
        raise SystemExit("o destino não pode ficar dentro do clone do grupo")
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)

    dev = git("rev-parse", "--short=7", "origin/dev")
    with tarfile.open(fileobj=io.BytesIO(git("archive", "origin/dev", binario=True))) as tar:
        tar.extractall(destino, filter="data")

    montagem = {"dev": dev, "sobreposto": [], "limitacoes": [], "deixados_de_fora": []}
    for ref, rotulo, arquivos in SOBREPOSICOES:
        sha = git("rev-parse", "--short=7", ref)
        base = git("merge-base", "origin/dev", ref)[:7]
        for arq in arquivos:
            if not existe(ref, arq):
                montagem["limitacoes"].append(f"{rotulo}: {arq} não existe em {ref}")
                continue
            if existe("origin/dev", arq):
                blob_dev = git("rev-parse", f"origin/dev:{arq}")
                blob_base = git("rev-parse", f"{base}:{arq}") if existe(base, arq) else None
                if blob_dev != blob_base:
                    montagem["limitacoes"].append(
                        f"{rotulo}: {arq} mudou no dev depois que o PR saiu; ficou a versão do dev")
                    continue
                modo = "substitui (o dev não mexeu no arquivo desde a base do PR)"
            else:
                modo = "arquivo novo"
            (destino / arq).parent.mkdir(parents=True, exist_ok=True)
            (destino / arq).write_bytes(git("show", f"{ref}:{arq}", binario=True))
            montagem["sobreposto"].append({"pr": rotulo, "sha": sha, "base": base, "arquivo": arq, "modo": modo})
    for rotulo, arq, motivo in DEIXADOS_DE_FORA:
        montagem["deixados_de_fora"].append({"pr": rotulo, "arquivo": arq, "motivo": motivo})
    (destino / "MONTAGEM.json").write_text(json.dumps(montagem, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return montagem


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--destino", default=str(DESTINO_PADRAO))
    a = ap.parse_args()
    print(json.dumps(montar(Path(a.destino)), ensure_ascii=False, indent=2))
