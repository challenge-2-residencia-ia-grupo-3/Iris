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

Em qualquer máquina (issue #108): o texto que os juízes leram fica fora do git por licença. Quando a base local não é
a julgada e não há cópia dela, a tela usa a base local trecho a trecho, só onde o texto é idêntico ao julgado: a
prova é a impressão digital (sha256) de cada trecho julgado, versionada em ``trechos_julgados_sha256.json``, sem texto.
Medido em 18/11/2026: os 68 trechos citados pelas 86 frases da amostra têm o mesmo texto na base de 1.881 trechos.

Adaptações (issue #108, parte 2b): 50 adaptações de questões sorteadas por estrato em
``rag/iris-rag/bancada/calibracao/amostra_adaptacoes_v1.json`` (Haiku no esforço baixo e Llama; veredito do Codex de
16/11). A pessoa vê a questão original, o que a adaptação pode e não pode fazer e a adaptação, e responde as mesmas três
perguntas que o juiz respondeu; nunca vê quem escreveu nem o veredito. Respostas em ``rotulos-humanos-adaptacoes.jsonl``,
que também só cresce.
"""

from __future__ import annotations

import importlib.util
import json
import random
import re
import hashlib
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from iris.config import RAG_BASE_DIR

PACOTE = RAG_BASE_DIR / "pacote"
MEDIDAS = PACOTE / "respostas_medidas.json"
VEREDITOS = PACOTE / "respostas_vereditos_cruzado.json"
CHUNKS = PACOTE / "chunks.jsonl"
# Os juízes leram os trechos da base de 1.083 (sha256 começando por cfc1481f449ef361). Se a base for trocada (a nova tem
# 42 desses trechos com texto alterado), a avaliação continua mostrando o texto que o juiz viu: ele fica guardado em
# chunks_julgados.jsonl, fora do git (leva texto sem licença aberta), copiado sozinho enquanto a base ainda é a julgada.
BASE_JULGADA = PACOTE / "chunks_julgados.jsonl"
HASH_BASE_JULGADA = "cfc1481f449ef361"
# Impressão digital (sha256, 16 primeiros caracteres) do texto de cada trecho que os juízes leram: sem o texto, pode ir
# para o git. Serve para usar a base local trecho a trecho quando ela não é a julgada (issue #108).
IMPRESSOES = PACOTE / "trechos_julgados_sha256.json"
PERGUNTAS = RAG_BASE_DIR / "gabarito" / "gabarito_rascunho_v0.json"
ROTULOS = RAG_BASE_DIR / "bancada" / "calibracao" / "rotulos-humanos-grupo.jsonl"
AMOSTRA_ADAPTACOES = RAG_BASE_DIR / "bancada" / "calibracao" / "amostra_adaptacoes_v1.json"
ROTULOS_ADAPTACOES = RAG_BASE_DIR / "bancada" / "calibracao" / "rotulos-humanos-adaptacoes.jsonl"

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


def _hash(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]


def impressao(texto: str) -> str:
    """Impressão digital do texto de um trecho: igual se, e só se, o texto for igual (sha256, 16 caracteres)."""
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()[:16]


def _ler_trechos(caminho: Path) -> dict[str, dict[str, str]]:
    textos: dict[str, dict[str, str]] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            c = json.loads(linha)
            textos[c["chunk_id"]] = {"texto": c.get("texto", ""), "doc": c.get("doc_id", ""), "aviso": c.get("nota_uso") or ""}
    return textos


def arquivo_de_trechos() -> Path:
    """O arquivo com o texto dos trechos como os juízes leram.

    Usa a cópia guardada; se ainda não há cópia e a base atual é a julgada, faz a cópia agora. Se a base já foi trocada
    e não há cópia, para com a explicação: mostrar o texto novo faria a pessoa avaliar um trecho diferente do que o juiz
    viu.
    """
    if BASE_JULGADA.exists():
        return BASE_JULGADA
    if CHUNKS.exists() and _hash(CHUNKS) == HASH_BASE_JULGADA:
        import shutil

        shutil.copyfile(CHUNKS, BASE_JULGADA)
        return BASE_JULGADA
    raise RuntimeError(
        "A base de trechos atual não é a que os juízes leram e não há cópia dela (chunks_julgados.jsonl). "
        f"Volte a base de 1.083 trechos (sha256 {HASH_BASE_JULGADA}...) por um momento para a cópia ser feita."
    )


TEXTO_MUDOU = (
    "O texto deste trecho na sua base não é o que os juízes leram, então não é mostrado. Se a frase depender dele, "
    "avalie pelo que os outros trechos mostram ou passe para a próxima."
)


def textos_julgados() -> dict[str, dict[str, str]]:
    """O texto de cada trecho como os juízes leram, por chunk_id.

    1. Cópia guardada da base julgada, ou a própria base local se ela for a julgada (``arquivo_de_trechos``).
    2. Senão, a base local trecho a trecho: entra o trecho cuja impressão digital é igual à do julgado; o que mudou
       ou sumiu entra sem texto e com aviso, para a pessoa nunca avaliar um texto diferente do que o juiz viu.
    """
    try:
        return _ler_trechos(arquivo_de_trechos())
    except RuntimeError as sem_copia:
        if not (IMPRESSOES.exists() and CHUNKS.exists()):
            raise sem_copia
    esperadas: dict[str, str] = json.loads(IMPRESSOES.read_text(encoding="utf-8"))["trechos"]
    locais = _ler_trechos(CHUNKS)
    saida: dict[str, dict[str, str]] = {}
    for cid, imp in esperadas.items():
        t = locais.get(cid)
        if t is not None and impressao(t["texto"]) == imp:
            saida[cid] = t
        else:
            saida[cid] = {"texto": "", "doc": (t or {}).get("doc", ""), "aviso": TEXTO_MUDOU, "mudou": "sim"}
    return saida


def gravar_impressoes(base_julgada: Path, destino: Path = IMPRESSOES) -> int:
    """Grava a impressão digital dos trechos citados pelas respostas medidas (rodar uma vez, com a base julgada)."""
    if _hash(base_julgada) != HASH_BASE_JULGADA:
        raise ValueError(f"{base_julgada} não é a base julgada (sha256 {HASH_BASE_JULGADA}...)")
    medidas = json.loads(MEDIDAS.read_text(encoding="utf-8"))["geradores"]
    citados = {cid for g in GERADORES for r in medidas[g].values() for cid in (r.get("fontes") or []) if cid}
    textos = _ler_trechos(base_julgada)
    trechos = {cid: impressao(textos[cid]["texto"]) for cid in sorted(citados) if cid in textos}
    destino.write_text(json.dumps({
        "base_julgada_sha256": HASH_BASE_JULGADA,
        "o_que_e": "sha256 (16 caracteres) do texto de cada trecho que os juízes leram; sem o texto, que tem licença restrita",
        "trechos": trechos,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(trechos)


@lru_cache(maxsize=1)
def _dados() -> dict[str, Any]:
    medidas = json.loads(MEDIDAS.read_text(encoding="utf-8"))["geradores"]
    vereditos = json.loads(VEREDITOS.read_text(encoding="utf-8"))
    perguntas = {i["id"]: i["pergunta"] for i in json.loads(PERGUNTAS.read_text(encoding="utf-8"))["itens"]}
    textos = textos_julgados()
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
    fila = fila_avaliavel()
    feitos = {u for (p, u) in _ultimo_por_pessoa(_ler_rotulos()) if p == avaliador}
    feitos_na_amostra = sum(1 for u in fila if u in feitos)
    base = {"avaliador": avaliador, "feitas": feitos_na_amostra, "total": len(fila), "opcoes": ROTULOS_VALIDOS}
    for uid in fila:
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
        "fora_da_fila": {"frases": len(a["uids"]) - len(fila_avaliavel()),
                         "motivo": "todos os trechos citados chegam sem texto (licença restrita); os juízes leram o texto completo"},
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


# ------------------------------------------------------------------ frases que a pessoa não tem como avaliar
AVISO_LICENCA = "(texto não reproduzido por restrição de licença"


def avaliavel(uid: str) -> bool:
    """Falso quando todos os trechos que a frase cita chegam à tela sem texto (licença restrita ou texto mudado).

    Os juízes leram o texto completo desses documentos (em ``respostas_passagens_v2.json`` a prova deles aparece como
    ``restrita``); uma pessoa que só vê o aviso de licença discordaria do juiz por falta do que ler, não por discordar.
    """
    cits = _citacoes(_dados()["frases"][uid])
    return any(c["texto"] and not c["texto"].startswith(AVISO_LICENCA) for c in cits)


@lru_cache(maxsize=1)
def fila_avaliavel() -> tuple[str, ...]:
    return tuple(u for u in amostra()["uids"] if avaliavel(u))


# ------------------------------------------------------------------ adaptações (issue #108, parte 2b)
PERGUNTAS_ADAPTACAO = {
    "aplicou": "A adaptação faz ao menos uma das coisas que ela PODE fazer?",
    "fora": "A adaptação acrescenta algo que ela NÃO pode (dica de conteúdo, exemplo, explicação, fórmula, resposta, "
            "vocabulário simplificado)? Negrito, numeração, caixas e linhas de resposta não contam como acréscimo.",
    "conteudo": "O que a questão pede ao aluno e os dados dela continuam os mesmos do original (nada retirado, nada trocado)?",
}
ESCONDIDO_DA_PESSOA = ("escritor", "juiz", "juiz_boa", "estrato", "peso", "chave")


def boa_adaptacao(r: dict[str, Any]) -> bool:
    """A mesma regra do juiz: aplicou, nada fora e conteúdo igual."""
    return bool(r.get("aplicou")) and not r.get("fora") and bool(r.get("conteudo"))


@lru_cache(maxsize=1)
def adaptacoes() -> dict[str, dict[str, Any]]:
    dados = json.loads(AMOSTRA_ADAPTACOES.read_text(encoding="utf-8"))
    return {i["uid"]: i for i in dados["itens"]}


def _ler_rotulos_adaptacoes() -> list[dict[str, Any]]:
    if not ROTULOS_ADAPTACOES.exists():
        return []
    saida = []
    for linha in ROTULOS_ADAPTACOES.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            try:
                saida.append(json.loads(linha))
            except json.JSONDecodeError:
                continue
    return saida


def _ultima_adaptacao_por_pessoa() -> dict[tuple[str, str], dict[str, bool]]:
    out: dict[tuple[str, str], dict[str, bool]] = {}
    for r in _ler_rotulos_adaptacoes():
        out[(r["avaliador"], r["uid"])] = r["respostas"]
    return out


def proxima_adaptacao(avaliador: str) -> dict[str, Any]:
    """A próxima adaptação que esta pessoa ainda não avaliou, sem quem escreveu e sem o veredito do juiz."""
    if not RE_AVALIADOR.match(avaliador or ""):
        raise ValueError("código de avaliador: de 1 a 40 letras, números, ponto, hífen ou sublinhado (ex.: prof-A)")
    itens = adaptacoes()
    feitos = {u for (p, u) in _ultima_adaptacao_por_pessoa() if p == avaliador}
    base = {"avaliador": avaliador, "feitas": sum(1 for u in itens if u in feitos), "total": len(itens),
            "perguntas": PERGUNTAS_ADAPTACAO}
    for uid, item in itens.items():
        if uid not in feitos:
            visivel = {k: v for k, v in item.items() if k not in ESCONDIDO_DA_PESSOA}
            return {**base, "acabou": False, **visivel}
    return {**base, "acabou": True}


def registrar_adaptacao(uid: str, respostas: dict[str, Any], avaliador: str, motivo: str = "") -> dict[str, Any]:
    """Acrescenta as três respostas da pessoa no fim do arquivo (nunca reescreve as linhas anteriores)."""
    if not RE_AVALIADOR.match(avaliador or ""):
        raise ValueError("código de avaliador inválido")
    if uid not in adaptacoes():
        raise KeyError(f"adaptação {uid!r} não está na amostra")
    if not isinstance(respostas, dict) or set(respostas) != set(PERGUNTAS_ADAPTACAO):
        raise ValueError(f"responda as três perguntas: {sorted(PERGUNTAS_ADAPTACAO)}")
    valores = {}
    for k, v in respostas.items():
        if v not in ("sim", "nao"):
            raise ValueError(f"resposta de {k!r} deve ser 'sim' ou 'nao'")
        valores[k] = v == "sim"
    ROTULOS_ADAPTACOES.parent.mkdir(parents=True, exist_ok=True)
    linha = {"uid": uid, "respostas": valores, "motivo": (motivo or "").strip()[:500], "avaliador": avaliador,
             "data": datetime.now().astimezone().isoformat(timespec="seconds")}
    with ROTULOS_ADAPTACOES.open("a", encoding="utf-8") as arq:
        arq.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return proxima_adaptacao(avaliador)


def resumo_adaptacoes() -> dict[str, Any]:
    """Concordância do juiz com as pessoas: na adaptação boa ou não, e em cada uma das três perguntas."""
    itens = adaptacoes()
    rot = _ultima_adaptacao_por_pessoa()
    por_item: dict[str, list[dict[str, bool]]] = {}
    for (_, uid), r in rot.items():
        if uid in itens:
            por_item.setdefault(uid, []).append(r)
    # várias pessoas no mesmo item: maioria; empate vai para o lado rígido (não boa, não aplicou, fora, conteúdo mudou)
    def maioria(vs: list[bool], rigido: bool) -> bool:
        s = sum(vs)
        return rigido if s * 2 == len(vs) else s * 2 > len(vs)

    pessoa = {}
    for uid, rs in por_item.items():
        pessoa[uid] = {
            "aplicou": maioria([r["aplicou"] for r in rs], False),
            "fora": maioria([r["fora"] for r in rs], True),
            "conteudo": maioria([r["conteudo"] for r in rs], False),
            "boa": maioria([boa_adaptacao(r) for r in rs], False),
        }
    n = len(pessoa)
    saida: dict[str, Any] = {
        "avaliadas": n, "pessoas": len({p for p, _ in rot}), "total_amostra": len(itens),
        "minimo": MINIMO_PARA_CONCORDANCIA,
        "duas_pessoas_ou_mais": sum(1 for rs in por_item.values() if len(rs) >= 2),
    }
    if n < MINIMO_PARA_CONCORDANCIA:
        saida["faltam"] = MINIMO_PARA_CONCORDANCIA - n
        return saida
    medidas = {}
    for campo in ("boa", "aplicou", "fora", "conteudo"):
        pares = []
        for uid, p in pessoa.items():
            juiz = itens[uid]["juiz_boa"] if campo == "boa" else itens[uid]["juiz"][campo]
            pares.append((int(p[campo]), int(juiz)))
        medidas[campo] = {
            "itens": len(pares), "iguais": sum(a == b for a, b in pares), "kappa": _kappa(pares),
            "matriz": {"ambos_sim": sum(1 for a, b in pares if a and b), "so_pessoa_sim": sum(1 for a, b in pares if a and not b),
                       "so_juiz_sim": sum(1 for a, b in pares if b and not a), "ambos_nao": sum(1 for a, b in pares if not a and not b)},
        }
    saida["medidas"] = medidas
    saida["erro_caro"] = {"pessoa_reprovou": sum(1 for p in pessoa.values() if not p["boa"]),
                          "juiz_aprovou": sum(1 for u, p in pessoa.items() if not p["boa"] and itens[u]["juiz_boa"])}
    return saida
