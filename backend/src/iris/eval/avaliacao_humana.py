"""Avaliação humana das frases das respostas do RAG, uma por vez e às cegas ("Juízes x pessoas").

Pergunta que responde: os juízes-modelo que dão nota de fidelidade concordam com uma pessoa? Sem essa conferência, a
nota do juiz não tem âncora (regra 13 do projeto: rótulo de modelo só vale com âncora humana).

O que entra (tudo versionado, sem modelo e sem rede):
  * ``rag/iris-rag/pacote/respostas_medidas.json``: as respostas de Haiku e Opus às 40 perguntas e a lista de trechos
    que cada gerador recebeu, na ordem [T1]..[T5];
  * ``rag/iris-rag/pacote/chunks.jsonl``: o texto de cada trecho;
  * ``rag/iris-rag/pacote/respostas_vereditos_cruzado.json``: o voto de cada avaliador por frase (A e B: Claude
    Sonnet; X: Codex; O: Claude Opus, só nas frases divididas);
  * ``rag/iris-rag/gabarito/gabarito_rascunho_v0.json``: o texto das perguntas.
As frases são divididas pela mesma função que os juízes usaram (``medir_respostas.frases_da_resposta``). Conferido
em 16/11/2026: 73 de 73 respostas dão o mesmo número de frases que de votos, e 284 de 284 passagens citadas pelos
juízes estão dentro do trecho [Tn] reconstruído aqui.

Amostra fixa e estratificada (semente 20261116), só frases de conteúdo (as que os juízes não trataram como
comentário):
  * todas as divididas (19), todas com dois contra um (17) e todas em que os três dizem "não sustenta" (10): é onde
    a pessoa mais informa;
  * 40 sorteadas das 316 em que os três dizem "sustenta", com peso 316/40, para medir o erro caro (o juiz aprova o
    que a pessoa reprova).

A pessoa vê a pergunta, a frase e os trechos que a frase cita, nunca o voto dos juízes. Cada clique acrescenta uma
linha em ``rag/iris-rag/bancada/calibracao/rotulos-humanos-grupo.jsonl``; nenhum script reescreve esse arquivo
(regra 14). A concordância só aparece a partir de ``MINIMO_PARA_CONCORDANCIA`` frases avaliadas.
"""

from __future__ import annotations

import importlib.util
import json
import random
import re
from collections import Counter
from datetime import datetime
from functools import lru_cache
from typing import Any

from iris.config import RAG_BASE_DIR

PACOTE = RAG_BASE_DIR / "pacote"
MEDIDAS = PACOTE / "respostas_medidas.json"
VEREDITOS = PACOTE / "respostas_vereditos_cruzado.json"
CHUNKS = PACOTE / "chunks.jsonl"
PERGUNTAS = RAG_BASE_DIR / "gabarito" / "gabarito_rascunho_v0.json"
ROTULOS = RAG_BASE_DIR / "bancada" / "calibracao" / "rotulos-humanos-grupo.jsonl"

SEMENTE = 20261116
N_SORTEIO_UNANIMES = 40
MINIMO_PARA_CONCORDANCIA = 20
GERADORES = ("haiku", "opus")
ROTULOS_VALIDOS = {
    "sim": "sustentada: tudo o que a frase afirma está nos trechos que ela cita",
    "parcial": "parcial: parte está nos trechos, parte não, ou a frase exagera",
    "nao": "não sustentada: os trechos citados não dizem isso",
}
AVALIADORES = {"A": "Sonnet A", "B": "Sonnet B", "X": "Codex", "final": "veredito final"}
RE_AVALIADOR = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


def _binario(v: Any) -> int | None:
    """1 = o trecho citado sustenta a frase inteira; 0 = em parte, não sustenta ou prova rejeitada; None = comentário."""
    if v in ("apoiada", "sim"):
        return 1
    if v in ("parcial", "nao_apoiada", "rejeitado", "nao"):
        return 0
    return None


@lru_cache(maxsize=1)
def _divisor():
    """A função de dividir frases que os juízes usaram (rag/iris-rag/pacote/medir_respostas.py)."""
    spec = importlib.util.spec_from_file_location("medir_respostas_grupo", PACOTE / "medir_respostas.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.frases_da_resposta


@lru_cache(maxsize=1)
def _dados() -> dict[str, Any]:
    medidas = json.loads(MEDIDAS.read_text(encoding="utf-8"))["geradores"]
    vereditos = json.loads(VEREDITOS.read_text(encoding="utf-8"))
    perguntas = {i["id"]: i["pergunta"] for i in json.loads(PERGUNTAS.read_text(encoding="utf-8"))["itens"]}
    textos: dict[str, dict[str, str]] = {}
    for linha in CHUNKS.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            c = json.loads(linha)
            textos[c["chunk_id"]] = {"texto": c.get("texto", ""), "doc": c.get("doc_id", ""), "aviso": c.get("nota_uso") or ""}
    dividir = _divisor()
    frases: dict[str, dict[str, Any]] = {}
    for g in GERADORES:
        for qid, linhas in (vereditos.get(g) or {}).items():
            r = medidas[g][qid]
            partes = dividir(r["resposta"])
            if len(partes) != len(linhas):  # a mesma divisão que os juízes receberam; se não bater, a frase fica fora
                continue
            for linha, texto in zip(linhas, partes, strict=True):
                if linha.get("final") is None:  # os juízes trataram como comentário
                    continue
                votos = {j: _binario(linha.get(j)) for j in "ABX"}
                conteudo = [v for v in votos.values() if v is not None]
                if linha.get("dividida"):
                    estrato = "dividida"
                elif len(set(conteudo)) > 1:
                    estrato = "dois_contra_um"
                elif conteudo and conteudo[0] == 1:
                    estrato = "unanime_sustenta"
                else:
                    estrato = "unanime_nao"
                uid = f"{g}-{qid}-{linha['n']}"
                frases[uid] = {
                    "uid": uid, "gerador": g, "qid": qid, "n": linha["n"], "texto": texto, "fontes": r.get("fontes") or [],
                    "votos": {**votos, "final": linha.get("final")}, "estrato": estrato,
                }
    return {"frases": frases, "perguntas": perguntas, "textos": textos}


@lru_cache(maxsize=1)
def amostra() -> dict[str, Any]:
    """A amostra fixa: ordem embaralhada com semente, para os estratos se misturarem na fila."""
    frases = _dados()["frases"]
    por_estrato: dict[str, list[str]] = {}
    for uid in sorted(frases):
        por_estrato.setdefault(frases[uid]["estrato"], []).append(uid)
    rng = random.Random(SEMENTE)
    escolhidas: list[str] = []
    pesos: dict[str, float] = {}
    for estrato, uids in sorted(por_estrato.items()):
        if estrato == "unanime_sustenta":
            n = min(N_SORTEIO_UNANIMES, len(uids))
            sel = sorted(rng.sample(uids, n))
        else:
            sel = list(uids)
        escolhidas += sel
        for u in sel:
            pesos[u] = len(uids) / len(sel)
    ordem = list(escolhidas)
    random.Random(SEMENTE + 1).shuffle(ordem)
    return {
        "uids": ordem,
        "pesos": pesos,
        "estratos": {e: {"total": len(u), "na_amostra": sum(1 for x in escolhidas if frases[x]["estrato"] == e)}
                     for e, u in sorted(por_estrato.items())},
    }


def _ler_rotulos() -> list[dict[str, Any]]:
    if not ROTULOS.exists():
        return []
    saida = []
    for linha in ROTULOS.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            try:
                saida.append(json.loads(linha))
            except json.JSONDecodeError:
                continue  # linha estragada não derruba a tela; continua no arquivo, para alguém olhar
    return saida


def _ultimo_por_pessoa(rotulos: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """Se a mesma pessoa avaliou a mesma frase duas vezes, vale a última (o arquivo guarda as duas)."""
    out: dict[tuple[str, str], str] = {}
    for r in rotulos:
        out[(r["avaliador"], r["uid"])] = r["rotulo"]
    return out


def _citacoes(frase: dict[str, Any]) -> list[dict[str, str]]:
    textos = _dados()["textos"]
    saida = []
    for ref in dict.fromkeys(re.findall(r"T(\d+)", frase["texto"])):
        i = int(ref) - 1
        cid = frase["fontes"][i] if 0 <= i < len(frase["fontes"]) else None
        t = textos.get(cid or "", {})
        saida.append({"ref": f"T{ref}", "chunk_id": cid or "", "doc": t.get("doc", ""), "texto": t.get("texto", ""),
                      "aviso": t.get("aviso", "")})
    return saida


def proxima(avaliador: str) -> dict[str, Any]:
    """A próxima frase da amostra que esta pessoa ainda não avaliou, SEM o voto dos juízes."""
    if not RE_AVALIADOR.match(avaliador or ""):
        raise ValueError("código de avaliador: de 1 a 40 letras, números, ponto, hífen ou sublinhado (ex.: prof-A)")
    a = amostra()
    feitos = {u for (p, u) in _ultimo_por_pessoa(_ler_rotulos()) if p == avaliador}
    feitos_na_amostra = sum(1 for u in a["uids"] if u in feitos)
    base = {"avaliador": avaliador, "feitas": feitos_na_amostra, "total": len(a["uids"]), "opcoes": ROTULOS_VALIDOS}
    for uid in a["uids"]:
        if uid not in feitos:
            f = _dados()["frases"][uid]
            return {**base, "acabou": False, "uid": uid, "pergunta": _dados()["perguntas"].get(f["qid"], ""),
                    "frase": f["texto"], "citacoes": _citacoes(f)}
    return {**base, "acabou": True}


def registrar(uid: str, rotulo: str, avaliador: str, motivo: str = "") -> dict[str, Any]:
    """Acrescenta um rótulo no fim do arquivo (nunca reescreve as linhas anteriores)."""
    if not RE_AVALIADOR.match(avaliador or ""):
        raise ValueError("código de avaliador inválido")
    if rotulo not in ROTULOS_VALIDOS:
        raise ValueError(f"rótulo deve ser um de {sorted(ROTULOS_VALIDOS)}")
    if uid not in set(amostra()["uids"]):
        raise KeyError(f"frase {uid!r} não está na amostra")
    ROTULOS.parent.mkdir(parents=True, exist_ok=True)
    linha = {"uid": uid, "rotulo": rotulo, "motivo": (motivo or "").strip()[:500], "avaliador": avaliador,
             "data": datetime.now().astimezone().isoformat(timespec="seconds")}
    with ROTULOS.open("a", encoding="utf-8") as arq:
        arq.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return proxima(avaliador)


def _kappa(pares: list[tuple[int, int]]) -> float | None:
    if not pares:
        return None
    n = len(pares)
    po = sum(a == b for a, b in pares) / n
    p1a = sum(a for a, _ in pares) / n
    p1b = sum(b for _, b in pares) / n
    pe = p1a * p1b + (1 - p1a) * (1 - p1b)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 3)


def resumo() -> dict[str, Any]:
    """Concordância de cada juiz com as pessoas, em "sustenta ou não" (parcial conta como não, como na fidelidade)."""
    a = amostra()
    frases = _dados()["frases"]
    rotulos = _ultimo_por_pessoa(_ler_rotulos())
    por_frase: dict[str, list[int]] = {}
    for (_, uid), r in rotulos.items():
        if uid in frases:
            por_frase.setdefault(uid, []).append(_binario(r))  # type: ignore[arg-type]
    # várias pessoas na mesma frase: maioria; empate vai para "não sustenta" (o lado rígido)
    pessoa = {u: int(sum(v) * 2 > len(v)) for u, v in por_frase.items()}
    n = len(pessoa)
    saida: dict[str, Any] = {
        "avaliadas": n, "pessoas": len({p for p, _ in rotulos}), "total_amostra": len(a["uids"]),
        "minimo": MINIMO_PARA_CONCORDANCIA, "estratos": a["estratos"],
        "classes_da_pessoa": dict(Counter(r for r in rotulos.values())),
    }
    if n < MINIMO_PARA_CONCORDANCIA:
        saida["faltam"] = MINIMO_PARA_CONCORDANCIA - n
        return saida
    juizes = {}
    for j, nome in AVALIADORES.items():
        pares = [(pessoa[u], frases[u]["votos"][j]) for u in pessoa if frases[u]["votos"][j] is not None]
        caro = [u for u in pessoa if pessoa[u] == 0 and frases[u]["votos"][j] == 1]
        reprovadas = sum(1 for u in pessoa if pessoa[u] == 0 and frases[u]["votos"][j] is not None)
        juizes[j] = {
            "nome": nome, "frases": len(pares), "iguais": sum(x == y for x, y in pares), "kappa": _kappa(pares),
            "erro_caro": {"pessoa_reprovou": reprovadas, "juiz_aprovou": len(caro)},
            "matriz": {"ambos_sustenta": sum(1 for x, y in pares if x == 1 and y == 1),
                       "so_pessoa_sustenta": sum(1 for x, y in pares if x == 1 and y == 0),
                       "so_juiz_sustenta": sum(1 for x, y in pares if x == 0 and y == 1),
                       "ambos_nao": sum(1 for x, y in pares if x == 0 and y == 0)},
        }
    saida["juizes"] = juizes
    return saida
