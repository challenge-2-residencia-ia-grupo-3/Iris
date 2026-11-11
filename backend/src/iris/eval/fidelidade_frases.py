"""Fidelidade (Faithfulness) das respostas do RAG a partir dos vereditos versionados (Issue #16).

Pergunta que responde: das frases de conteúdo que a resposta escreve, que fração o trecho citado
sustenta por inteiro? É a receita da Faithfulness do RAGAS (afirmações sustentadas pelo contexto /
afirmações da resposta), com duas diferenças:

  * a unidade é a frase da resposta, não a afirmação atômica que o RAGAS extrai com um LLM;
  * a frase tem de estar no trecho que ela cita, não em qualquer um dos cinco recuperados.

Este módulo não chama modelo nem rede. Lê ``rag/iris-rag/pacote/respostas_vereditos_cruzado.json``
(um veredito por frase e por avaliador, gravado por ``medir_fidelidade_cruzada.py``) e refaz a
conta: fidelidade por avaliador e final, intervalo de 95% por bootstrap, concordância (kappa de
Cohen) e a leitura contra ``FAITHFULNESS_MIN``. A versão com juiz ao vivo é ``iris.eval.faithfulness``.

Avaliadores: A e B (Claude Sonnet), X (Codex, da OpenAI), O (Claude Opus, só nas frases divididas).
Veredito final de uma frase: maioria de A, B e X; na frase dividida, o veredito de O.
"Em parte" e prova rejeitada contam como não sustentada. Respostas de recusa ficam fora.

Expectativa escrita antes de rodar (11/11/2026): os mesmos números gravados na medição original
(``rag/outputs/37-fidelidade-juiz-de-outro-fabricante.txt``), porque a fórmula, a semente e os
vereditos são os mesmos: Haiku 0,905 [0,858 a 0,947] e Opus 0,950 [0,922 a 0,978]. Mudaria a
leitura qualquer diferença na terceira casa: os vereditos versionados não bastariam para refazer
a medida.

Uso:
    uv run python -m iris.eval.fidelidade_frases

Grava ``reports/rag_fidelidade.json`` e ``reports/rag_fidelidade.txt``.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from iris.config import RAG_BASE_DIR, REPO_ROOT
from iris.eval.faithfulness import FAITHFULNESS_MIN

VEREDITOS_PADRAO = RAG_BASE_DIR / "pacote" / "respostas_vereditos_cruzado.json"
SAIDA_JSON = REPO_ROOT / "reports" / "rag_fidelidade.json"
SAIDA_TXT = REPO_ROOT / "reports" / "rag_fidelidade.txt"
N_BOOT, SEMENTE = 2000, 20261105  # os mesmos da medição original
CLASSES = ("apoiada", "parcial", "nao_apoiada", "rejeitado")
NOMES = {"A": "Sonnet A", "B": "Sonnet B", "X": "Codex", "final": "maioria dos três + Opus"}

# gerador -> pergunta -> frases; cada frase traz o veredito de A, B, X e O e o veredito final
Vereditos = dict[str, dict[str, list[dict]]]


def carregar_vereditos(caminho: str | Path | None = None) -> Vereditos:
    return json.loads(Path(caminho or VEREDITOS_PADRAO).read_text(encoding="utf-8"))


def binario(veredito: str) -> int | None:
    """1 = sustentada por inteiro; 0 = em parte, não sustentada ou prova rejeitada; None = não é conteúdo."""
    return (1 if veredito == "apoiada" else 0) if veredito in CLASSES else None


def _votos(frases: list[dict], quem: str) -> list[int]:
    votos = [f["final"] if quem == "final" else binario(f[quem]) for f in frases]
    return [v for v in votos if v is not None]


def ic_bootstrap(valores: list[float]) -> tuple[float, float]:
    """Intervalo de 95% da média, reamostrando as respostas com reposição (semente fixa)."""
    rnd = random.Random(SEMENTE)
    m = len(valores)
    medias = sorted(sum(rnd.choice(valores) for _ in range(m)) / m for _ in range(N_BOOT))
    return medias[int(0.025 * N_BOOT)], medias[int(0.975 * N_BOOT) - 1]


def fidelidade(respostas: dict[str, list[dict]], quem: str = "final") -> dict:
    """Média, por resposta, de frases sustentadas / frases de conteúdo, para um avaliador ou para o final."""
    por_resposta, sustentadas, total = [], 0, 0
    for frases in respostas.values():
        votos = _votos(frases, quem)
        if votos:
            por_resposta.append(sum(votos) / len(votos))
            sustentadas, total = sustentadas + sum(votos), total + len(votos)
    baixo, alto = ic_bootstrap(por_resposta)
    return {
        "media": sum(por_resposta) / len(por_resposta),
        "ic95": [baixo, alto],
        "sustentadas": sustentadas,
        "frases_de_conteudo": total,
        "respostas": len(por_resposta),
    }


def kappa(pares: list[tuple[int, int]]) -> float:
    """Kappa de Cohen: concordância entre dois avaliadores, descontada a que viria do acaso."""
    n = len(pares)
    observada = sum(a == b for a, b in pares) / n
    ca, cb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    esperada = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    return (observada - esperada) / (1 - esperada) if esperada < 1 else float("nan")


def concordancia(respostas: dict[str, list[dict]], a: str, b: str) -> dict:
    """Concordância em "sustenta ou não", nas frases que os dois avaliadores tratam como conteúdo."""
    pares = [
        (binario(f[a]), binario(f[b]))
        for frases in respostas.values()
        for f in frases
        if f[a] in CLASSES and f[b] in CLASSES
    ]
    matriz = Counter(pares)
    return {
        "frases": len(pares),
        "iguais": sum(x == y for x, y in pares),
        "kappa": kappa(pares),
        # [[os dois sustentam, só o primeiro], [só o segundo, nenhum]]
        "matriz": [[matriz[(1, 1)], matriz[(1, 0)]], [matriz[(0, 1)], matriz[(0, 0)]]],
    }


def leitura(resultado: dict, meta: float = FAITHFULNESS_MIN) -> str:
    """Compara o intervalo, e não só a média, com a meta."""
    baixo, alto = resultado["ic95"]
    if baixo >= meta:
        return "atinge a meta"
    if alto < meta:
        return "abaixo da meta"
    return "não se distingue da meta"


def medir(vereditos: Vereditos, meta: float = FAITHFULNESS_MIN) -> dict:
    saida = {"meta": meta, "geradores": {}}
    for gerador, respostas in vereditos.items():
        frases = [f for fs in respostas.values() for f in fs]
        final = fidelidade(respostas, "final")
        saida["geradores"][gerador] = {
            "fidelidade": {quem: fidelidade(respostas, quem) for quem in ("A", "B", "X", "final")},
            "leitura": leitura(final, meta),
            "concordancia": {f"{a}x{b}": concordancia(respostas, a, b) for a, b in (("A", "B"), ("A", "X"), ("B", "X"))},
            "frases_divididas": sum(1 for f in frases if f["dividida"]),
            "nao_sustentadas_para_os_tres": sum(1 for f in frases if f["A"] == f["B"] == f["X"] == "nao_apoiada"),
        }
    return saida


def _texto(medida: dict) -> str:
    linhas = [
        "FIDELIDADE (FAITHFULNESS) DAS RESPOSTAS, POR FRASE, A PARTIR DOS VEREDITOS VERSIONADOS.",
        "Fidelidade = frases de conteúdo que o trecho citado sustenta por inteiro / frases de conteúdo, média por resposta.",
        "Avaliadores: dois Claude Sonnet e o Codex (OpenAI), mesma regra; Claude Opus nas frases divididas. Sem conferência humana.",
        f"Nenhum modelo treinado nem chamado aqui: contagem, kappa de Cohen e bootstrap ({N_BOOT} reamostras, semente {SEMENTE}).",
        f"Meta (FAITHFULNESS_MIN): {medida['meta']:.2f}. A leitura compara o intervalo de 95% com a meta.",
    ]
    for gerador, g in medida["geradores"].items():
        linhas += ["", f"=== gerador {gerador}: {g['fidelidade']['final']['respostas']} respostas",
                   f"{'avaliador':26s}{'fidelidade':>12s}{'IC 95%':>18s}{'frases sustentadas':>22s}"]
        for quem, f in g["fidelidade"].items():
            intervalo = f"[{f['ic95'][0]:.3f}-{f['ic95'][1]:.3f}]"
            contagem = f"{f['sustentadas']} de {f['frases_de_conteudo']}"
            linhas.append(f"{NOMES[quem]:26s}{f['media']:>12.3f}{intervalo:>18s}{contagem:>22s}")
        linhas += [f"Leitura contra a meta: {g['leitura']}.", "",
                   f"{'par (sustenta ou não)':26s}{'frases':>8s}{'iguais':>10s}{'kappa':>8s}   matriz [[1,1] [1,0] / [0,1] [0,0]]"]
        for par, c in g["concordancia"].items():
            a, b = par.split("x")
            m = c["matriz"]
            linhas.append(f"{NOMES[a] + ' x ' + NOMES[b]:26s}{c['frases']:>8d}{c['iguais'] / c['frases']:>10.1%}{c['kappa']:>8.2f}"
                          f"   [{m[0][0]} {m[0][1]} / {m[1][0]} {m[1][1]}]")
        linhas.append(f"Frases divididas, decididas pelo Opus: {g['frases_divididas']}. "
                      f"Frases não sustentadas para os três avaliadores: {g['nao_sustentadas_para_os_tres']}.")
    return "\n".join(linhas) + "\n"


def main() -> None:
    medida = medir(carregar_vereditos())
    texto = _texto(medida)
    SAIDA_TXT.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_TXT.write_text(texto, encoding="utf-8")
    SAIDA_JSON.write_text(json.dumps(medida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
