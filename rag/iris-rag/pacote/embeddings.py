"""embeddings.py: os três buscadores do Íris.

    BuscaBM25    busca por palavra (rank_bm25), sem modelo
    ModeloDenso  busca por sentido: 'mpnet' ou 'qwen3' (sentence-transformers)
    rrf          junta duas listas pela posição (Reciprocal Rank Fusion, k=60)

Tokenização: minúsculas, sem acento, palavras com 3+ letras,
mais a regra de plural (ver _singular). Os vetores ficam em cache/ (npy) para não recalcular.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("RAG_CACHE", AQUI / "cache"))

MODELOS_DENSOS = {
    # o que o grupo já usava: feito para semelhança de frases (paráfrase), 278 M parâmetros.
    # Foi treinado com textos de até 128 tokens; aqui deixamos ler até 512 para não cortar o trecho.
    "mpnet": {"nome": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
              "prompt_pergunta": None, "max_tokens": 512},
    # feito para busca (pergunta curta -> trecho), multilíngue, 600 M parâmetros.
    # A pergunta recebe a instrução 'query' do próprio modelo; o trecho vai sem instrução.
    "qwen3": {"nome": "Qwen/Qwen3-Embedding-0.6B", "prompt_pergunta": "query", "max_tokens": 1024},
}


def dispositivo() -> str:
    """cuda (PC com RTX), mps (Mac M), ou cpu (VPS)."""
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ---------------------------------------------------------------- tokenização (BM25)
STOPWORDS = set("""
a o e de da do das dos em no na nos nas um uma uns umas que com por para pra pro como mais mas
ou se ao aos as os sua seu suas seus ele ela eles elas isso esse essa este esta ja nao sim ser
sao foi tem ter tá ta to tô estou esta estao quando muito muita pode podem deve devem sobre ate
entre sem tambem meu minha meus minhas qual quais quem onde porque cada outro outra outros outras
""".split())


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _singular(p: str) -> str:
    """Regra de plural simples do português (sem dicionário):
    'mamadeiras' -> 'mamadeira', 'infeccoes' -> 'infeccao', 'paes' -> 'pao',
    'animais' -> 'animal', 'colheres' -> 'colher'. Palavras curtas ficam como estão."""
    if len(p) <= 3:
        return p
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ois", "ol"),
                       ("eses", "es"), ("res", "r"), ("zes", "z"), ("ns", "m")):
        if p.endswith(fim):
            return p[: -len(fim)] + troca
    if p.endswith("s") and not p.endswith(("ss", "us", "is")):
        return p[:-1]
    return p


def palavras(texto: str) -> list[str]:
    """Minúsculas, sem acento, só [a-z0-9], 3+ letras, sem palavra vazia, no singular."""
    return [_singular(p) for p in re.findall(r"[a-z0-9]+", _sem_acento(texto))
            if len(p) > 2 and p not in STOPWORDS]


class BuscaBM25:
    """Nota alta para o trecho que tem as palavras da pergunta, com mais peso para palavra rara."""

    nome = "bm25"

    def __init__(self, textos: list[str], k1: float = 1.5, b: float = 0.75):
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi([palavras(t) for t in textos], k1=k1, b=b)

    def notas(self, pergunta: str):
        return self.bm25.get_scores(palavras(pergunta))


# ---------------------------------------------------------------- vetores (densos)
def _assinatura(textos: list[str], apelido: str) -> str:
    h = hashlib.sha256(apelido.encode())
    for t in textos:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


class ModeloDenso:
    """Carrega o modelo uma vez; transforma trechos (com cache em disco) e perguntas em vetores."""

    def __init__(self, apelido: str, disp: str | None = None):
        import torch
        from sentence_transformers import SentenceTransformer
        cfg = MODELOS_DENSOS[apelido]
        self.apelido = apelido
        self.prompt_pergunta = cfg["prompt_pergunta"]
        self.disp = disp or dispositivo()
        # float32 em cpu/mps (estável); float16 só em cuda
        dtype = torch.float16 if self.disp == "cuda" else torch.float32
        self.modelo = SentenceTransformer(cfg["nome"], device=self.disp,
                                          model_kwargs={"dtype": dtype})
        self.modelo.max_seq_length = cfg["max_tokens"]
        self.ultimo_tempo_s: float | None = None
        self.veio_do_cache = False

    def vetores_trechos(self, textos: list[str], lote: int = 8, mostrar: bool = True):
        """Vetor de cada trecho (normalizado). Usa cache/vetores-<apelido>-<assinatura>.npy."""
        import numpy as np
        CACHE.mkdir(exist_ok=True)
        arq = CACHE / f"vetores-{self.apelido}-{_assinatura(textos, self.apelido)}.npy"
        meta = arq.with_suffix(".json")
        if arq.exists():
            self.veio_do_cache = True
            self.ultimo_tempo_s = json.loads(meta.read_text())["segundos"] if meta.exists() else None
            return np.load(arq)
        # ordena por tamanho: lotes com textos parecidos gastam menos preenchimento (padding).
        # Grava o progresso a cada bloco (arquivo .parcial.npy): se cair no meio, continua de onde parou.
        import numpy as np
        ordem = sorted(range(len(textos)), key=lambda i: -len(textos[i]))
        parcial = arq.with_name(arq.stem + ".parcial.npy")
        parcial_meta = arq.with_name(arq.stem + ".parcial.json")
        feitos: list = []
        seg_antes = 0.0
        if parcial.exists() and parcial_meta.exists():
            feitos = list(np.load(parcial))
            seg_antes = json.loads(parcial_meta.read_text())["segundos"]
            if mostrar:
                print(f"[{self.apelido}] retomando: {len(feitos)} de {len(textos)} já calculados", flush=True)
        t0 = time.time()
        bloco = 64
        for ini in range(len(feitos), len(textos), bloco):
            idx = ordem[ini:ini + bloco]
            v = self.modelo.encode([textos[i] for i in idx], batch_size=lote,
                                   normalize_embeddings=True, show_progress_bar=False,
                                   convert_to_numpy=True)
            feitos.extend(v.astype(np.float32))
            np.save(parcial, np.stack(feitos))
            parcial_meta.write_text(json.dumps({"segundos": seg_antes + time.time() - t0}))
            if mostrar:
                gasto = seg_antes + time.time() - t0
                print(f"[{self.apelido}] {len(feitos)}/{len(textos)} trechos ({gasto / 60:.1f} min)", flush=True)
        v = np.stack(feitos)
        vetores = np.zeros_like(v)
        vetores[ordem] = v
        self.ultimo_tempo_s = seg_antes + time.time() - t0
        self.veio_do_cache = False
        np.save(arq, vetores.astype(np.float32))
        meta.write_text(json.dumps({"segundos": self.ultimo_tempo_s, "n": len(textos),
                                    "dispositivo": self.disp, "modelo": MODELOS_DENSOS[self.apelido]["nome"]}))
        parcial.unlink(missing_ok=True)
        parcial_meta.unlink(missing_ok=True)
        return vetores

    def vetor_pergunta(self, pergunta: str):
        kw = {"prompt_name": self.prompt_pergunta} if self.prompt_pergunta else {}
        return self.modelo.encode([pergunta], normalize_embeddings=True, convert_to_numpy=True, **kw)[0]


# ---------------------------------------------------------------- fusão
def rrf(listas: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: cada lista dá 1/(k + posição) a cada item; soma e ordena.
    Só a posição importa, então não é preciso pôr notas de BM25 e cosseno na mesma escala."""
    soma: dict[str, float] = {}
    for lista in listas:
        for pos, cid in enumerate(lista):
            soma[cid] = soma.get(cid, 0.0) + 1.0 / (k + pos + 1)
    return sorted(soma.items(), key=lambda x: -x[1])
