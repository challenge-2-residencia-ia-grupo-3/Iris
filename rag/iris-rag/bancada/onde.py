"""onde.py: acha o clone do grupo para a bancada rodar em qualquer maquina.

Ordem: IRIS_GRUPO ou BANCADA_GRUPO; senao, o repositorio git que contem a bancada (quando ela mora dentro do Iris);
senao, ../Iris ao lado; senao, um caminho de servidor antigo (compatibilidade).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

AQUI = Path(__file__).resolve().parent
VPS = Path("/home/openclaw/clawd/private/lume/iris-grupo")


def _eh_iris(p: Path) -> bool:
    return (p / "backend" / "src" / "iris").is_dir()


def grupo() -> Path:
    for var in ("IRIS_GRUPO", "BANCADA_GRUPO", "GRUPO"):
        v = os.environ.get(var)
        if v and _eh_iris(Path(v).expanduser()):
            return Path(v).expanduser().resolve()
    try:
        top = subprocess.run(["git", "-C", str(AQUI), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10).stdout.strip()
        if top and _eh_iris(Path(top)):
            return Path(top)
    except (OSError, subprocess.SubprocessError):
        pass
    for p in AQUI.parents:
        if _eh_iris(p / "Iris"):
            return (p / "Iris").resolve()
    return VPS


if __name__ == "__main__":
    print(grupo())
