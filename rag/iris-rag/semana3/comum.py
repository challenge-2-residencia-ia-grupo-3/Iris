"""comum.py: caminhos, prompts e funções usadas por todos os scripts da semana 3.

Só biblioteca padrão do Python (roda na VPS e no PC sem instalar nada).
Os prompts do teste C vêm de pacote/gerar.py (não há cópia aqui). O prompt do teste A está aqui e foi
escrito para ser equivalente ao do C, sem trechos (ver PREREG.md).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent            # .../iris-rag/semana3
IRIS_RAG = AQUI.parent
PACOTE = IRIS_RAG / "pacote"
SAIDAS = AQUI / "saidas"
JUIZ = AQUI / "juiz"
GABARITO = IRIS_RAG / "gabarito" / "gabarito_rascunho_v0.json"

TRECHOS_BUSCA = SAIDAS / "trechos_busca.jsonl"     # busca feita uma vez (40 perguntas, top-10, 5 com texto)
PROMPTS_AC = SAIDAS / "prompts_ac.jsonl"           # os prompts exatos de A e C (o PC usa este arquivo)
SEMENTE = 20261112
REPETICOES = 3
TEMPERATURA = 0

# Modelos do estudo (ver PREREG.md): apelido curto -> (provedor, id do modelo no provedor)
MODELOS = {
    "qwen3.8-27b": ("groq", "qwen/qwen3.8-27b"),
    "llama3.1-8b": ("ollama", "llama3.1:8b"),      # modelo de produção do Íris: a decisão usa este
    "gpt-oss-20b": ("ollama", "gpt-oss:20b"),      # modelo aberto maior, local: mede se o tamanho muda a decisão (H4)
}
# Preço público do Groq para o Qwen 3.8 27B (US$ por milhão de tokens; console.groq.com, consultado em 12/11/2026).
# O Llama roda local (Ollama): custo em dólar zero.
PRECOS = {"qwen3.8-27b": {"entrada": 0.80, "saida": 4.00}, "llama3.1-8b": {"entrada": 0.0, "saida": 0.0},
          "gpt-oss-20b": {"entrada": 0.0, "saida": 0.0}}

FRASE_NAO_SEI = "Não sei responder a isso com segurança."

PROMPT_A = f"""Você é o Agente Estrategista do Íris, que apoia professores a adaptar atividades para alunos
com TDAH sem reduzir a habilidade avaliada. Responda em português do Brasil.

Regras:
1. Responda com o que você sabe sobre o assunto.
2. Se não souber responder com segurança, responda exatamente: "{FRASE_NAO_SEI}"
   e nada mais. É melhor não responder do que inventar.
3. Diferencie o que é evidência de pesquisa, o que é norma e o que é orientação prática.
4. No máximo 6 frases. Sem introdução, sem conclusão genérica."""


def montar_prompt_a(pergunta: str) -> str:
    return f"{PROMPT_A}\n\nPERGUNTA: {pergunta}\n\nRESPOSTA:"


# ---------------------------------------------------------------- arquivos
def ler_jsonl(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


def acrescentar_jsonl(caminho: Path, linha: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def escrever_jsonl(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas), encoding="utf-8")


def escrever_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha16(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def commit_atual() -> str:
    """Commit do repositório + '-modificado' se houver mudança não gravada (para o log de proveniência)."""
    try:
        h = subprocess.run(["git", "-C", str(IRIS_RAG), "rev-parse", "--short", "HEAD"], capture_output=True,
                           text=True, timeout=10).stdout.strip()
        sujo = subprocess.run(["git", "-C", str(IRIS_RAG), "status", "--porcelain", "--", "."], capture_output=True,
                              text=True, timeout=10).stdout.strip()
        return (h or "sem-git") + ("-modificado" if sujo else "")
    except (OSError, subprocess.SubprocessError):
        return "sem-git"


# ---------------------------------------------------------------- gabarito e categorias
def itens_gabarito() -> list[dict]:
    """As 40 perguntas com categoria (factual / síntese / fora da base) e documento dominante."""
    itens = json.loads(GABARITO.read_text(encoding="utf-8"))["itens"]
    out = []
    for it in itens:
        docs = [c.split("#")[0] for c in it.get("trechos_relevantes", [])]
        if not docs:
            cat, dom = "fora_da_base", None
        else:
            cat = "factual" if len(set(docs)) == 1 else "sintese"
            cont: dict[str, int] = {}
            for d in docs:
                cont[d] = cont.get(d, 0) + 1
            dom = sorted(cont.items(), key=lambda x: (-x[1], x[0]))[0][0]
        out.append({**it, "categoria": cat, "doc_dominante": dom})
    return out


# ---------------------------------------------------------------- frases
def frases(texto: str) -> list[str]:
    """Divide em frases: fim de frase (. ! ?) seguido de espaço, ou quebra de linha. Mantém as citações [Tn]."""
    partes = []
    for linha in texto.strip().splitlines():
        linha = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", linha).strip()
        if not linha:
            continue
        partes += [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú\"“(\[])", linha) if p.strip()]
    # frase que é só citação ([T1][T2]) gruda na anterior
    junto: list[str] = []
    for p in partes:
        if junto and re.fullmatch(r"(\[T\d+\])+\.?", p):
            junto[-1] += " " + p
        else:
            junto.append(p)
    return junto


# ---------------------------------------------------------------- chamadas aos modelos
def _chave_groq() -> str:
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    for env in (Path.home() / ".env",):
        if env.exists():
            for l in env.read_text().splitlines():
                if l.startswith("GROQ_API_KEY="):
                    return l.split("=", 1)[1].strip().strip('"')
    raise SystemExit("sem GROQ_API_KEY no ambiente")


class LimiteDiario(RuntimeError):
    """O Groq avisou que acabou a cota do dia: parar e retomar depois (os scripts continuam de onde pararam)."""


def chamar_groq(modelo: str, prompt: str, max_tokens: int = 1500) -> dict:
    """Uma mensagem de usuário, temperatura 0 (igual a gerar._chamar_groq). Espera no limite do plano grátis."""
    corpo = json.dumps({"model": modelo, "temperature": TEMPERATURA, "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=corpo,
                                 headers={"Authorization": f"Bearer {_chave_groq()}",
                                          "Content-Type": "application/json", "User-Agent": "iris-rag/0.1"})
    espera_total = 0.0
    for tentativa in range(10):
        t0 = time.time()
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=180).read())
            texto = r["choices"][0]["message"]["content"] or ""
            u = r.get("usage", {})
            return {"texto_bruto": texto, "tokens_entrada": u.get("prompt_tokens"),
                    "tokens_saida": u.get("completion_tokens"), "segundos_geracao": round(time.time() - t0, 2),
                    "segundos_espera_limite": round(espera_total, 1), "modelo_informado": r.get("model"),
                    "fim": r["choices"][0].get("finish_reason")}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and tentativa < 9:
                try:
                    msg = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001 - só para o log
                    msg = ""
                if "per day" in msg or "TPD" in msg or "RPD" in msg:
                    raise LimiteDiario(msg)
                espera = min(float(e.headers.get("retry-after") or 20 * (tentativa + 1)) + 2, 120)
                print(f"   groq {e.code}: esperando {espera:.0f} s ({msg[:160]})", flush=True)
                espera_total += espera
                time.sleep(espera)
                continue
            raise


def chamar_ollama(modelo: str, prompt: str, max_tokens: int = 1500) -> dict:
    """Mesma mensagem, temperatura 0, semente 42 (a mesma do provedor Ollama do grupo), contexto de 8192 tokens."""
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/chat"
    d = {"model": modelo, "stream": False, "keep_alive": "15m",
         "messages": [{"role": "user", "content": prompt}],
         "options": {"temperature": TEMPERATURA, "seed": 42, "num_ctx": 8192, "num_predict": max_tokens}}
    if modelo.startswith("gpt-oss"):
        # o gpt-oss raciocina antes de responder e o raciocínio consome a mesma cota de tokens:
        # esforço "low" e teto maior, senão a resposta sai vazia. O raciocínio não entra na resposta.
        d["think"] = "low"
        d["options"]["num_predict"] = 4000
    corpo = json.dumps(d).encode()
    req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return {"texto_bruto": r["message"]["content"], "tokens_entrada": r.get("prompt_eval_count"),
            "tokens_saida": r.get("eval_count"), "segundos_geracao": round(time.time() - t0, 2),
            "segundos_espera_limite": 0.0, "modelo_informado": r.get("model"),
            "fim": r.get("done_reason")}


def chamar(apelido: str, prompt: str) -> dict:
    provedor, modelo = MODELOS[apelido]
    r = chamar_groq(modelo, prompt) if provedor == "groq" else chamar_ollama(modelo, prompt)
    r["texto"] = re.sub(r"<think>.*?</think>", "", r["texto_bruto"], flags=re.S).strip()  # igual a gerar.gerar
    return r


def custo_usd(apelido: str, tok_in, tok_out) -> float | None:
    if tok_in is None or tok_out is None:
        return None
    p = PRECOS[apelido]
    return round(tok_in / 1e6 * p["entrada"] + tok_out / 1e6 * p["saida"], 6)


def embaralhar(lista: list, semente: int = SEMENTE) -> list:
    out = list(lista)
    random.Random(semente).shuffle(out)
    return out


def adicionar_pacote_ao_path() -> None:
    if str(PACOTE) not in sys.path:
        sys.path.insert(0, str(PACOTE))
