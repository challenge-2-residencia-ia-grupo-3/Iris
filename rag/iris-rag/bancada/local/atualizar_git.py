"""atualizar_git.py: traz do GitHub o que é novo, sem nunca apagar trabalho local.

Usado pelo botão "atualizar do GitHub" do modo local (servidor.py) e também direto no terminal:

    python atualizar_git.py --grupo C:\\Users\\voce\\Iris            # atualiza o clone do grupo e a bancada
    python atualizar_git.py --grupo ~/code/Iris --so-checar --json   # só conta os commits novos (não muda nada)

Regras (para nunca estragar o computador de ninguém):
  * só `git fetch` e `git merge --ff-only`: avança a branch quando o GitHub está à frente e você não tem commit
    local que o GitHub não tenha. Nada de reset, stash, rebase ou push.
  * se a pasta tem arquivo modificado, ou se a sua branch e a do GitHub divergiram, NÃO mexe e explica o que fazer.
  * no clone do grupo, se você estiver noutra branch (ex.: a do seu PR), atualiza essa branch; o painel mostra o
    código que está no seu computador.
Sai com código 0 mesmo quando pula um repositório (o painel continua com a versão que já está aí);
código 1 só se o git não existir ou a pasta não for um repositório.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BANCADA = AQUI.parent.parent          # .../iris-rag (dentro do repositório da bancada)


def git(repo: Path, *args: str, timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, f"git {' '.join(args)}: demorou demais (rede?)"
    return r.returncode, (r.stdout + r.stderr).strip()


def situacao(repo: Path, buscar: bool) -> dict:
    """branch, upstream, quantos commits atrás/à frente, se tem arquivo modificado."""
    s = {"pasta": str(repo), "branch": None, "upstream": None, "atras": 0, "frente": 0, "sujo": False,
         "commit": None, "erro": None}
    code, raiz = git(repo, "rev-parse", "--show-toplevel")
    if code != 0:
        s["erro"] = "não é um repositório git"
        return s
    s["pasta"] = raiz
    if buscar:
        code, out = git(repo, "fetch", "--quiet", "origin")
        if code != 0:
            s["erro"] = "não consegui falar com o GitHub: " + out[-200:]
    s["commit"] = git(repo, "rev-parse", "--short", "HEAD")[1]
    code, br = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    s["branch"] = br if code == 0 else None
    code, up = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    s["upstream"] = up if code == 0 else None
    if s["upstream"]:
        code, cont = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}")
        if code == 0 and len(cont.split()) == 2:
            s["frente"], s["atras"] = (int(x) for x in cont.split())
    s["sujo"] = bool(git(repo, "status", "--porcelain", "--untracked-files=no")[1])
    return s


def atualizar(nome: str, repo: Path) -> dict:
    s = situacao(repo, buscar=True)
    print(f"\n== {nome}: {s['pasta']}")
    if s["erro"] == "não é um repositório git":
        print("   não é um repositório git; nada feito")
        return s
    if s["erro"]:
        print("   " + s["erro"])
        return s
    print(f"   branch {s['branch'] or '(nenhuma: commit solto)'} @ {s['commit']}"
          + (f", acompanha {s['upstream']}" if s["upstream"] else ""))
    if not s["branch"] or not s["upstream"]:
        print("   esta branch não acompanha nenhuma do GitHub; nada a atualizar.")
        print("   (para voltar ao principal do grupo: git switch dev)")
        s["acao"] = "pulado"
        return s
    if s["atras"] == 0:
        print("   já está em dia com o GitHub." + (f" Você tem {s['frente']} commit(s) seu(s) ainda não enviado(s)." if s["frente"] else ""))
        s["acao"] = "em dia"
        return s
    if s["sujo"]:
        print(f"   o GitHub tem {s['atras']} commit(s) novo(s), mas há arquivos modificados nesta pasta.")
        print("   Não mexi para não apagar o seu trabalho. Salve (commit) ou desfaça as mudanças e clique de novo.")
        print("   Para ver o que mudou: git status")
        s["acao"] = "pulado: arquivos modificados"
        return s
    if s["frente"]:
        print(f"   a sua branch e a do GitHub divergiram ({s['frente']} commit(s) só seus, {s['atras']} só do GitHub).")
        print("   Não mexi. Resolva no terminal (git pull) quando quiser.")
        s["acao"] = "pulado: divergiu"
        return s
    code, out = git(repo, "merge", "--ff-only", "--quiet", "@{u}")
    if code != 0:
        print("   não consegui avançar: " + out[-300:])
        s["acao"] = "falhou"
        return s
    novo = git(repo, "rev-parse", "--short", "HEAD")[1]
    print(f"   atualizado: {s['commit']} -> {novo} ({s['atras']} commit(s) novo(s))")
    code, log = git(repo, "log", "--format=%h %an: %s", f"{s['commit']}..{novo}", "-n", "8")
    for linha in log.splitlines():
        print("     " + linha)
    s.update({"acao": "atualizado", "commit": novo, "atras": 0})
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="Atualiza do GitHub o clone do grupo e a bancada (só avança, nunca apaga).")
    ap.add_argument("--grupo", required=True, help="clone do repositório do grupo (Iris)")
    ap.add_argument("--bancada", default=str(BANCADA), help="pasta da bancada (padrão: esta)")
    ap.add_argument("--so-checar", action="store_true", help="só busca e conta os commits novos; não muda nada")
    ap.add_argument("--json", action="store_true", help="saída em JSON (para o servidor local)")
    a = ap.parse_args()
    if not shutil.which("git"):
        print("o git não está instalado nesta máquina")
        return 1
    alvos = [("código do grupo", Path(a.grupo).expanduser()), ("bancada", Path(a.bancada).expanduser())]
    if a.so_checar:
        res = {nome: situacao(p, buscar=True) for nome, p in alvos}
        if a.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            for nome, s in res.items():
                print(f"{nome}: {s['atras']} commit(s) novo(s) no GitHub" + (f" ({s['erro']})" if s["erro"] else ""))
        return 0
    res = {nome: atualizar(nome, p) for nome, p in alvos}
    ruim = [n for n, s in res.items() if s.get("erro") == "não é um repositório git"]
    print("\nresumo: " + "; ".join(f"{n}: {s.get('acao') or s.get('erro')}" for n, s in res.items()))
    return 1 if ruim else 0


if __name__ == "__main__":
    sys.exit(main())
