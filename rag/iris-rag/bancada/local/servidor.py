#!/usr/bin/env python3
"""Modo local da Bancada do Íris: um servidor pequeno que roda SÓ na sua máquina.

O que ele faz
-------------
Serve o painel (pacote/reports/bancada.html) e deixa rodar cada comando `make` da bancada
por botões na página, mostrando a saída ao vivo. Só biblioteca padrão do Python.

Como rodar
----------
    cd pacote
    make painel GRUPO=/caminho/do/clone/do/Iris
ou, sem make (Windows):
    python ..\\bancada\\local\\servidor.py --grupo C:\\caminho\\do\\Iris

Segurança (por que dá para deixar ligado)
-----------------------------------------
- Liga SEMPRE em 127.0.0.1: só a própria máquina acessa. Nunca 0.0.0.0, nem com opção.
- Recusa (403) requisição cujo cabeçalho Host não seja 127.0.0.1 ou localhost: impede que
  um site malicioso use "DNS rebinding" para conversar com o servidor pelo seu navegador.
- Recusa (403) POST sem o cabeçalho `X-Bancada: 1` (e com Origin de outro site): um
  formulário de outro site não consegue mandar esse cabeçalho, então não dispara comandos.
- Só roda alvos que estão no Makefile (lista fechada). Nada que o navegador manda vira
  linha de shell: o comando é uma lista de argumentos, shell=False, cwd=pacote/.
- Um comando por vez.

CONTRATO DA API (o painel usa isto para detectar o modo local)
--------------------------------------------------------------
GET  /                 -> o painel (pacote/reports/bancada.html; gera se não existir)
GET  /status.json      -> pacote/reports/status.json se existir; senão 404
GET  /api/ping         -> 200 {"local": true,
                               "alvos": [{"alvo": "custo", "descricao": "...", "pesado": false}, ...],
                               "grupo": "/caminho/do/clone", "grupo_commit": "abc1234",
                               "python": "3.12.1", "rodando": null | "<id>"}
                          A lista vem das linhas do Makefile com '## ' (menos linha-de-base,
                          que muda a régua e fica só na linha de comando).
                          pesado=true: rastro-pipeline, adversarial, ablacao, pipeline-tudo,
                          gitnexus, tudo (demoram e usam mais memória).
POST /api/rodar        -> corpo JSON {"alvo": "custo"} ou {"alvo": "rastro", "q": "Q07"}
                          cabeçalho obrigatório: X-Bancada: 1
                          200 {"id": "<id>"} | 400 alvo/q inválido | 403 sem cabeçalho
                          | 409 {"erro": ..., "id": "<id do que está rodando>"} se já tem um rodando
                          "q" só vale para rastro e precisa casar com ^Q\\d{2}$.
GET  /api/saida/<id>   -> text/event-stream (Server-Sent Events). Pode reconectar: manda tudo
                          desde o começo. Eventos, nesta ordem:
                            (sem nome, "message")  data: uma linha da saída (stdout+stderr juntos)
                            event: fim     data: {"codigo": 0, "segundos": 1.23}
                            event: painel  data: {"ok": true}   só se codigo == 0: o painel foi
                                           regenerado (python3 bancada.py html); recarregue a página
                            event: fechado data: {}             último evento; feche o EventSource
                          404 se o id não existe.

Exemplo no navegador:
    const r = await fetch('/api/rodar', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Bancada': '1'},
        body: JSON.stringify({alvo: 'custo'})});
    const {id} = await r.json();
    const es = new EventSource('/api/saida/' + id);
    es.onmessage = e => console.log(e.data);
    es.addEventListener('painel', () => location.reload());
    es.addEventListener('fechado', () => es.close());
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent                      # iris-rag/
PACOTE = RAIZ / "pacote"
MAKEFILE = PACOTE / "Makefile"
PAINEL = PACOTE / "reports" / "bancada.html"
STATUS = PACOTE / "reports" / "status.json"

HOST = "127.0.0.1"                             # fixo de propósito: só a própria máquina
FORA_DO_PAINEL = {"linha-de-base", "painel"}   # linha-de-base muda a régua; painel é este servidor
PESADOS = {"rastro-pipeline", "adversarial", "ablacao", "pipeline-tudo", "gitnexus", "tudo"}
RE_Q = re.compile(r"^Q\d{2}$")


# ---------------------------------------------------------------- Makefile

ATUALIZAR = {"alvo": "atualizar", "pesado": True,
             "descricao": "traz do GitHub o código novo do grupo e da bancada (só avança, nunca apaga trabalho seu) "
                          "e roda de novo as verificações que dependem do código"}
# o que roda depois do git, se algo mudou: as verificações que leem o código do grupo (sem modelo, sem API)
DEPOIS_DE_ATUALIZAR = ["pipeline-tudo", "mapa", "etapas", "bancada"]


def ler_alvos() -> list[dict]:
    """Alvos do Makefile com '## descrição', na ordem em que aparecem; 'atualizar' (do servidor) vem primeiro."""
    alvos = [dict(ATUALIZAR)]
    for linha in MAKEFILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-z][a-z-]*):.*?##\s*(.+)$", linha)
        if m and m.group(1) not in FORA_DO_PAINEL:
            alvos.append({"alvo": m.group(1), "descricao": m.group(2).strip(),
                          "pesado": m.group(1) in PESADOS})
    return alvos


def passos_sem_make(alvo: str, cfg: dict, q: str) -> list[tuple[Path, list[str]]]:
    """Equivalente de cada alvo para quem não tem `make` (Windows).

    Espelha o Makefile; se um alvo mudar lá, mude aqui também.
    Cada passo é (pasta, lista de argumentos). Sem `nice` (não existe no Windows).
    """
    py, pyb, grupo, prov = cfg["py"], cfg["pyb"], cfg["grupo"], cfg["prov"]
    pip = RAIZ / "bancada" / "pipeline"
    mapa = RAIZ / "bancada" / "mapa"
    P = PACOTE
    conferir_py = ("import hashlib,os,sys\n"
                   "if not os.path.exists('chunks.jsonl'): print('falta chunks.jsonl (ver RODAR-NO-PC.md)'); sys.exit(1)\n"
                   "if not os.path.exists('outputs/17-respostas.jsonl'): print('aviso: sem outputs/17-respostas.jsonl (rastro sem respostas)')\n"
                   "h=hashlib.sha256(open('chunks.jsonl','rb').read()).hexdigest()[:16]\n"
                   "print('chunks.jsonl',h,'ok' if h=='1b517d249bef1873' else 'DIFERENTE do congelado')")
    t = {
        "registrar": [(P, [py, "bancada.py", "registrar"])],
        "html": [(P, [py, "bancada.py", "html"])],
        "rastro": [(P, [py, "bancada.py", "rastro", q])],
        "conferir": [(P, [py, "-c", conferir_py])],
        "regressao": [(P, [py, "bancada.py", "registrar"]), (P, [py, "bancada_checks.py", "regressao"])],
        "repetir": [(P, [py, "bancada_checks.py", "repetir"])],
        "custo": [(P, [py, "bancada_checks.py", "custo"])],
        "revisao": [(P, [py, "bancada_checks.py", "divergencias"])],
        "rastro-pipeline": [(pip, [pyb, "rastro_pipeline.py", "--provedor", prov])],
        "adversarial": [(pip, [pyb, "adversarial.py", "--provedor", prov])],
        "ablacao": [(pip, [pyb, "ablacao.py", "--provedor", prov])],
        "mapa": [(P, [py, str(mapa / "mapa_codigo.py"), "--repo", grupo, "--saida", "outputs"])],
        "gitnexus": [(P, [py, str(mapa / "gitnexus_exportar.py"), "--repo", grupo, "--ref", "HEAD", "--saida", "outputs"])],
        "github": [(P, [py, str(RAIZ / "bancada" / "atualizar" / "github_estado.py"), "--saida", "outputs"])],
        "etapas": [(P, [py, str(pip / "etapas_explicadas.py"), "--grupo", grupo])],
    }
    t["bancada"] = t["registrar"] + t["html"]
    t["pipeline-tudo"] = t["rastro-pipeline"] + t["adversarial"] + t["ablacao"]
    t["tudo"] = (t["repetir"] + t["custo"] + t["revisao"] + t["pipeline-tudo"]
                 + t["mapa"] + t["gitnexus"] + t["etapas"] + t["bancada"])
    t["help"] = []
    return t[alvo]


def montar_passos(alvo: str, cfg: dict, q: str) -> list[tuple[Path, list[str]]]:
    if alvo == "atualizar":
        passos = [(AQUI, [cfg["py"], str(AQUI / "atualizar_git.py"), "--grupo", cfg["grupo"]])]
        for a in DEPOIS_DE_ATUALIZAR:
            passos += montar_passos(a, cfg, q)
        return passos
    if cfg["make"]:
        args = [cfg["make"], "--no-print-directory", alvo,
                f"PY={cfg['py']}", f"PYB={cfg['pyb']}", f"GRUPO={cfg['grupo']}", f"PROV={cfg['prov']}"]
        if alvo == "rastro":
            args.append(f"Q={q}")
        return [(PACOTE, args)]
    return passos_sem_make(alvo, cfg, q)


# ---------------------------------------------------------------- jobs

class Job:
    def __init__(self, alvo: str, passos):
        self.id = uuid.uuid4().hex[:12]
        self.alvo = alvo
        self.passos = passos
        self.eventos: list[tuple[str | None, str]] = []   # (nome do evento, dado)
        self.terminou = False
        self.cond = threading.Condition()
        self.proc: subprocess.Popen | None = None

    def emitir(self, nome, dado):
        with self.cond:
            self.eventos.append((nome, dado))
            self.cond.notify_all()


TRAVA = threading.Lock()
NOVOS: dict = {"cache": None, "em": 0.0}      # resultado de /api/novidades (consulta o GitHub no máx. a cada 5 min)


def commit_de(repo: str) -> str:
    try:
        return subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


def novidades(cfg: dict) -> dict:
    """Quantos commits o GitHub tem a mais que o seu computador (só fetch; não muda arquivos)."""
    if NOVOS["cache"] is not None and time.time() - NOVOS["em"] < 120:
        return NOVOS["cache"]
    try:
        out = subprocess.run([cfg["py"], str(AQUI / "atualizar_git.py"), "--grupo", cfg["grupo"], "--so-checar", "--json"],
                             capture_output=True, text=True, timeout=90, env=ambiente()).stdout
        d = json.loads(out.strip().splitlines()[-1])
        res = {"grupo": d["código do grupo"].get("atras", 0), "bancada": d["bancada"].get("atras", 0),
               "erro": d["código do grupo"].get("erro") or d["bancada"].get("erro")}
    except Exception as e:
        res = {"grupo": 0, "bancada": 0, "erro": f"não consegui checar: {e}"}
    NOVOS.update(cache=res, em=time.time())
    return res


JOBS: dict[str, Job] = {}
ATUAL: dict[str, Job | None] = {"job": None}


def ambiente() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"     # não deixa __pycache__ no clone do grupo
    env["PYTHONUNBUFFERED"] = "1"            # saída aparece na hora, não no fim
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def rodar_passo(job: Job, pasta: Path, args: list[str]) -> int:
    job.emitir(None, "$ " + " ".join(args) if len(" ".join(args)) < 300 else "$ " + args[0] + " ...")
    extra = {"start_new_session": True} if os.name != "nt" else {}
    job.proc = subprocess.Popen(args, cwd=str(pasta), shell=False, env=ambiente(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, **extra)
    for bruto in job.proc.stdout:
        job.emitir(None, bruto.decode("utf-8", "replace").rstrip("\r\n"))
    return job.proc.wait()


def executar(job: Job, cfg: dict):
    t0 = time.time()
    codigo = 0
    try:
        for pasta, args in job.passos:
            codigo = rodar_passo(job, pasta, args)
            if codigo != 0:
                break
    except Exception as e:                    # ex.: python/make não encontrado
        job.emitir(None, f"erro ao rodar: {e}")
        codigo = 127
    if job.alvo == "atualizar":
        cfg["grupo_commit"] = commit_de(cfg["grupo"])
        NOVOS["cache"] = None
    job.emitir("fim", json.dumps({"codigo": codigo, "segundos": round(time.time() - t0, 2)}))
    if codigo == 0:
        if job.alvo not in ("html", "bancada", "tudo", "atualizar"):
            try:
                c = rodar_passo(job, PACOTE, [cfg["py"], "bancada.py", "html"])
            except Exception as e:
                job.emitir(None, f"erro ao regenerar o painel: {e}")
                c = 1
        else:
            c = 0
        if c == 0:
            job.emitir("painel", json.dumps({"ok": True}))
    with TRAVA:
        ATUAL["job"] = None
    with job.cond:
        job.terminou = True
        job.emitir("fechado", "{}")


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "BancadaLocal/1"
    cfg: dict = {}

    def log_message(self, fmt, *a):          # log curto no terminal
        sys.stderr.write("  %s %s\n" % (self.command, self.path))

    # ---- respostas
    def responder(self, codigo: int, corpo: bytes, tipo="application/json; charset=utf-8"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def json(self, codigo: int, obj):
        self.responder(codigo, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    # ---- proteções
    def host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        nome = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        porta = host.rsplit(":", 1)[1] if host.count(":") == 1 else ""
        return nome in ("127.0.0.1", "localhost") and porta in ("", str(self.cfg["porta"]))

    def origem_ok(self) -> bool:
        origem = self.headers.get("Origin")
        if not origem:
            return True
        p = self.cfg["porta"]
        return origem in (f"http://127.0.0.1:{p}", f"http://localhost:{p}")

    # ---- GET
    def do_GET(self):
        if not self.host_ok():
            return self.json(403, {"erro": "Host não permitido; use http://127.0.0.1:%d" % self.cfg["porta"]})
        caminho = self.path.split("?", 1)[0]
        if caminho in ("/", "/index.html", "/bancada.html"):
            return self.servir_painel()
        if caminho == "/status.json":
            if STATUS.is_file():
                return self.responder(200, STATUS.read_bytes())
            return self.json(404, {"erro": "sem status.json (só existe na cópia publicada pelo vigia)"})
        if caminho == "/api/ping":
            atual = ATUAL["job"]
            novo = commit_de(self.cfg["grupo"])           # a pessoa pode ter dado git pull/switch no terminal
            if novo != self.cfg["grupo_commit"]:
                self.cfg["grupo_commit"], NOVOS["cache"] = novo, None
            return self.json(200, {"local": True, "alvos": self.cfg["alvos"], "grupo": self.cfg["grupo"],
                                   "grupo_commit": self.cfg["grupo_commit"],
                                   "python": platform.python_version(),
                                   "rodando": atual.id if atual else None})
        if caminho == "/api/novidades":
            return self.json(200, novidades(self.cfg))
        m = re.fullmatch(r"/api/saida/([0-9a-f]{12})", caminho)
        if m:
            return self.sse(m.group(1))
        return self.json(404, {"erro": "não encontrado"})

    do_HEAD = do_GET

    def servir_painel(self):
        if not PAINEL.is_file():
            subprocess.run([self.cfg["py"], "bancada.py", "html"], cwd=str(PACOTE), env=ambiente())
        if not PAINEL.is_file():
            return self.json(500, {"erro": "não consegui gerar reports/bancada.html; rode 'make html' em pacote/"})
        self.responder(200, PAINEL.read_bytes(), "text/html; charset=utf-8")

    def sse(self, jid: str):
        job = JOBS.get(jid)
        if not job:
            return self.json(404, {"erro": "id desconhecido"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        i = 0
        try:
            while True:
                with job.cond:
                    if i >= len(job.eventos) and not job.terminou:
                        job.cond.wait(timeout=15)
                    novos = job.eventos[i:]
                    acabou = job.terminou
                i += len(novos)
                if not novos:
                    if acabou:
                        break
                    self.wfile.write(b": ainda rodando\n\n")       # mantém a conexão viva
                for nome, dado in novos:
                    bloco = (f"event: {nome}\n" if nome else "") + f"data: {dado}\n\n"
                    self.wfile.write(bloco.encode("utf-8"))
                self.wfile.flush()
                if acabou and i >= len(job.eventos):
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass   # a página fechou; o comando continua rodando

    # ---- POST
    def do_POST(self):
        if not self.host_ok():
            return self.json(403, {"erro": "Host não permitido"})
        if self.headers.get("X-Bancada") != "1":
            return self.json(403, {"erro": "falta o cabeçalho X-Bancada: 1 (proteção contra outros sites)"})
        if not self.origem_ok():
            return self.json(403, {"erro": "pedido vindo de outro site (Origin) recusado"})
        if self.path.split("?", 1)[0] != "/api/rodar":
            return self.json(404, {"erro": "não encontrado"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 10_000:
                return self.json(413, {"erro": "corpo grande demais"})
            pedido = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(pedido, dict):
                raise ValueError
        except ValueError:
            return self.json(400, {"erro": "corpo precisa ser JSON, ex.: {\"alvo\": \"custo\"}"})
        alvo = pedido.get("alvo")
        validos = {a["alvo"] for a in self.cfg["alvos"]}
        if not isinstance(alvo, str) or alvo not in validos:
            return self.json(400, {"erro": "alvo inválido", "validos": sorted(validos)})
        q = pedido.get("q") or "Q07"
        if not isinstance(q, str) or not RE_Q.match(q):
            return self.json(400, {"erro": "q inválido: use Q01..Q99, ex.: Q07"})
        with TRAVA:
            if ATUAL["job"] is not None:
                return self.json(409, {"erro": "já tem um comando rodando; espere terminar",
                                       "id": ATUAL["job"].id, "alvo": ATUAL["job"].alvo})
            job = Job(alvo, montar_passos(alvo, self.cfg, q))
            JOBS[job.id] = job
            ATUAL["job"] = job
            for velho in list(JOBS)[:-20]:           # guarda só os 20 últimos
                JOBS.pop(velho, None)
        threading.Thread(target=executar, args=(job, self.cfg), daemon=True).start()
        print(f"  rodando: make {alvo}" + (f" Q={q}" if alvo == "rastro" else ""), flush=True)
        self.json(200, {"id": job.id})


# ---------------------------------------------------------------- partida

def resolver_python(valor: str | None, nome: str) -> str:
    """Caminho do python: argumento, variável de ambiente, ou o python que está rodando este arquivo."""
    if not valor:
        return sys.executable
    achado = shutil.which(valor) or (valor if Path(valor).is_file() else None)
    if achado:
        # absolute() e NÃO resolve(): o python de um venv é um atalho; seguir o atalho
        # cairia no python do sistema, sem as dependências do venv
        return str(Path(achado).absolute())
    print(f"aviso: {nome}={valor} não existe nesta máquina; usando {sys.executable}")
    return sys.executable


def explicar_grupo(grupo: str | None):
    print("\nFalta o clone do repositório do grupo (o código do Íris).")
    if grupo:
        print(f"  a pasta informada não existe: {grupo}")
    print("Clone uma vez, em qualquer pasta (só leitura, a bancada não altera nada lá):")
    print("  git clone https://github.com/challenge-2-residencia-ia-grupo-3/Iris.git")
    print("e rode de novo indicando onde ficou:")
    print("  make painel GRUPO=/caminho/para/Iris")
    print("  (sem make)  python ../bancada/local/servidor.py --grupo /caminho/para/Iris")
    print("Guia completo: rag/iris-rag/bancada/README.md\n")


def main():
    ap = argparse.ArgumentParser(description="Painel local da bancada (só 127.0.0.1).")
    ap.add_argument("--porta", type=int, default=int(os.environ.get("PORTA", 8777)))
    ap.add_argument("--grupo", default=os.environ.get("GRUPO"), help="clone do repositório do grupo (Iris)")
    ap.add_argument("--py", default=os.environ.get("PY"), help="python da bancada (padrão: este)")
    ap.add_argument("--pyb", default=os.environ.get("PYB"), help="python do venv com as dependências (padrão: --py)")
    ap.add_argument("--prov", default=os.environ.get("PROV", "eco"), help="eco (sem modelo) ou ollama")
    ap.add_argument("--sem-make", action="store_true", help="roda os passos direto, sem chamar make")
    a = ap.parse_args()

    if not a.grupo or not Path(a.grupo).is_dir():
        explicar_grupo(a.grupo)
        sys.exit(2)
    if a.prov not in ("eco", "ollama"):
        sys.exit("--prov precisa ser eco ou ollama")
    grupo = str(Path(a.grupo).resolve())
    py = resolver_python(a.py, "PY")
    pyb = resolver_python(a.pyb, "PYB") if a.pyb else py
    commit = commit_de(grupo)
    # no Windows o Makefile usa comandos de Linux (grep, test, nice); lá rodamos os passos direto
    make = None if (a.sem_make or os.name == "nt") else shutil.which("make")

    Handler.cfg = {"porta": a.porta, "grupo": grupo, "grupo_commit": commit, "py": py, "pyb": pyb,
                   "prov": a.prov, "make": make, "alvos": ler_alvos()}
    try:
        srv = ThreadingHTTPServer((HOST, a.porta), Handler)
    except OSError as e:
        sys.exit(f"não consegui abrir a porta {a.porta} ({e}). Já tem outro painel aberto? Tente --porta 8778")
    srv.daemon_threads = True

    print("\nBancada do Íris, modo local")
    print(f"  abra no navegador:  http://127.0.0.1:{a.porta}")
    print("  só esta máquina acessa (ligado em 127.0.0.1, não aparece na rede)")
    print(f"  grupo:  {grupo} @ {commit}")
    print(f"  python: {py}" + (f"   venv (PYB): {pyb}" if pyb != py else ""))
    print("  comandos via: " + (make if make else "python direto (sem make)"))
    print("  para desligar: Ctrl+C\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndesligando...")
        job = ATUAL["job"]
        if job and job.proc and job.proc.poll() is None:
            job.proc.terminate()
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
