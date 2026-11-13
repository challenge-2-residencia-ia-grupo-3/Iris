"""Peças comuns da calibração do juiz (só biblioteca padrão do Python).

Ideia em uma frase: antes de confiar num "corretor automático" (o juiz por modelo),
a gente confere quantas vezes ele concorda com uma pessoa corrigindo as mesmas frases.

Unidade de medida = uma FRASE de uma resposta (pergunta Qnn + texto da frase).
Cada juiz deu a ela um voto: "sim" (sustentada pelos trechos), "parcial" ou "nao".
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # .../iris-rag
OUT = RAIZ / "pacote" / "outputs"
REPORTS = RAIZ / "pacote" / "reports"
AQUI = Path(__file__).resolve().parent
ROTULOS = AQUI / "rotulos-humanos.jsonl"
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("onde", Path(__file__).resolve().parents[1] / "onde.py")
_onde = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_onde)
GRUPO = _onde.grupo()

CLASSES = ["sim", "parcial", "nao"]                  # ordem: da mais "aprovadora" à mais rígida
SEMENTE = 20261112
N_BOOT = 2000

# Arquivos de voto já gravados. "familia" = quem fez o modelo (mesma empresa/linha de treino).
# Rodada 2 do mesmo modelo serve para medir se o juiz concorda consigo mesmo.
JUIZES = {
    "haiku-r1":        {"arq": "17-juiz-haiku.jsonl",       "modelo": "claude-haiku-5-5",    "familia": "anthropic"},
    "haiku-r2":        {"arq": "17-juiz-haiku-r2.jsonl",    "modelo": "claude-haiku-5-5",    "familia": "anthropic"},
    "gpt-oss-20b":     {"arq": "17-juiz-local.jsonl",       "modelo": "gpt-oss:20b",         "familia": "openai-gpt-oss"},
    "gpt-oss-120b-r1": {"arq": "17-juiz-r1.jsonl",          "modelo": "openai/gpt-oss-120b", "familia": "openai-gpt-oss"},
    "gpt-oss-120b-r2": {"arq": "17-juiz-r2.jsonl",          "modelo": "openai/gpt-oss-120b", "familia": "openai-gpt-oss"},
}
# Juízes "principais" = os três modelos diferentes que julgaram as 35 respostas do prompt v1.
PRINCIPAIS = ["haiku-r1", "gpt-oss-20b", "gpt-oss-120b-r1"]
# 17-juiz-v2-busca-nova-r1.jsonl julga OUTRAS respostas (v2), com 4 perguntas: fica fora,
# porque não há outro juiz votando nas mesmas frases (não dá para comparar).


def norm(frase: str) -> str:
    """Tira as marcas [T1] e a pontuação, para casar a mesma frase entre juízes
    (o haiku recebeu a frase com [T1], o gpt-oss-20b sem)."""
    return re.sub(r"\W+", " ", re.sub(r"\[T\d+\]", "", frase or "")).strip().lower()


def uid(qid: str, frase: str) -> str:
    """Identificador estável e curto da frase (não carrega texto)."""
    return qid + "-" + hashlib.sha1(f"{qid}|{norm(frase)}".encode()).hexdigest()[:10]


def voto(v: str | None) -> str | None:
    v = (v or "").strip().lower().replace("ã", "a")
    return v if v in CLASSES else None


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def carregar_votos() -> tuple[dict[str, dict[str, str]], dict[str, dict]]:
    """Devolve votos[juiz][uid] = classe, e info[uid] = {id, frase, refs}.
    Respostas em que o sistema se absteve não têm frase para julgar."""
    absteve = {r["id"] for r in jl(OUT / "17-respostas.jsonl") if r["conferencia"]["absteve"]}
    votos: dict[str, dict[str, str]] = {}
    info: dict[str, dict] = {}
    for nome, cfg in JUIZES.items():
        votos[nome] = {}
        for r in jl(OUT / cfg["arq"]):
            if r["id"] in absteve:
                continue
            for f in ((r.get("veredito") or {}).get("frases") or []):
                c = voto(f.get("sustentada"))
                if not c or not norm(f.get("frase", "")):
                    continue
                u = uid(r["id"], f["frase"])
                votos[nome][u] = c
                i = info.setdefault(u, {"id": r["id"], "frase": re.sub(r"\s*(\[T\d+\])+", "", f["frase"]).strip(),
                                        "refs": []})
                for ref in re.findall(r"T\d+", f["frase"]):
                    if ref not in i["refs"]:
                        i["refs"].append(ref)
    return votos, info


def carregar_rotulos() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Lê rotulos-humanos.jsonl. Se mais de uma pessoa rotulou a mesma frase, usa a maioria;
    em empate, fica com o rótulo mais rígido (nao < parcial < sim), para não aprovar demais."""
    por_pessoa: dict[str, dict[str, str]] = defaultdict(dict)
    if ROTULOS.exists():
        for r in jl(ROTULOS):
            c = voto(r.get("rotulo"))
            if c:
                por_pessoa[r.get("avaliador") or "anonimo"][r["uid"]] = c   # a última gravação vale
    juntos: dict[str, list[str]] = defaultdict(list)
    for p, d in por_pessoa.items():
        for u, c in d.items():
            juntos[u].append(c)
    final = {}
    for u, cs in juntos.items():
        cont = Counter(cs)
        topo = max(cont.values())
        final[u] = max((c for c in cont if cont[c] == topo), key=CLASSES.index)
    return final, dict(por_pessoa)


# ------------------------------------------------------------------ estatística
def matriz(a: list[str], b: list[str], pesos: list[float] | None = None) -> list[list[float]]:
    """Matriz de confusão 3x3: linha = a (referência), coluna = b."""
    m = [[0.0] * 3 for _ in CLASSES]
    for i, (x, y) in enumerate(zip(a, b)):
        m[CLASSES.index(x)][CLASSES.index(y)] += pesos[i] if pesos else 1.0
    return m


def kappa_de_matriz(m: list[list[float]]) -> tuple[float, float, float]:
    """Kappa de Cohen: concordância observada descontada da que viria por sorte.
    Devolve (kappa, po, pe). Sem variação nenhuma (todos iguais), kappa fica indefinido -> nan."""
    n = sum(map(sum, m))
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    po = sum(m[i][i] for i in range(3)) / n
    lin = [sum(m[i]) / n for i in range(3)]
    col = [sum(m[i][j] for i in range(3)) / n for j in range(3)]
    pe = sum(lin[i] * col[i] for i in range(3))
    if pe >= 1 - 1e-12:
        return float("nan"), po, pe
    return (po - pe) / (1 - pe), po, pe


def kappa(a, b, pesos=None):
    return kappa_de_matriz(matriz(a, b, pesos))[0]


def bootstrap_por_pergunta(uids: list[str], estat, n_boot: int = N_BOOT, semente: int = SEMENTE):
    """IC 95% por bootstrap sorteando PERGUNTAS inteiras (com reposição), não frases soltas:
    as frases da mesma resposta não são independentes (mesmos trechos, mesmo erro), e sortear
    frase por frase daria um intervalo estreito demais."""
    grupos: dict[str, list[str]] = defaultdict(list)
    for u in uids:
        grupos[u.split("-")[0]].append(u)
    chaves = sorted(grupos)
    rng = random.Random(semente)
    vals = []
    for _ in range(n_boot):
        amostra = [u for k in (rng.choice(chaves) for _ in chaves) for u in grupos[k]]
        v = estat(amostra)
        if v == v:  # descarta nan
            vals.append(v)
    if len(vals) < n_boot * 0.5:
        return None
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals)) - 1], 3)]


def wilson(k: int, n: int, z: float = 1.96):
    """IC 95% de Wilson para uma proporção k/n (funciona bem com n pequeno)."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def n_para_meia_largura(kappa_alvo: float, pe: float, meia: float = 0.15, deff: float = 1.0, z: float = 1.96) -> int:
    """Quantas frases rotuladas para o IC 95% do kappa ter meia-largura ~meia.
    Aproximação de amostra grande: Var(kappa) ~ po(1-po) / (n (1-pe)^2), com po = kappa(1-pe)+pe.
    deff (efeito de desenho) corrige por frases da mesma resposta andarem juntas."""
    po = kappa_alvo * (1 - pe) + pe
    n = (z ** 2) * po * (1 - po) / (((1 - pe) ** 2) * meia ** 2)
    return int(math.ceil(n * deff))


def rel(p: Path) -> str:
    """Caminho relativo à raiz da bancada, quando der (para não gravar /home/... no JSON)."""
    try:
        return str(p.resolve().relative_to(RAIZ))
    except ValueError:
        return str(p)


def commit(caminho: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(caminho), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None
