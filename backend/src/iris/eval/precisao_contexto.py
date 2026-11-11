"""Context Precision (RAGAS) da recuperação do RAG contra o gabarito de trechos (Issue #16).

Pergunta que responde: dos 5 trechos que a busca entrega ao gerador, quantos são trechos que o
gabarito marcou como certos para aquela pergunta, e em que posição eles aparecem?

Duas medidas, as duas sem LLM juiz (mesma entrada, mesmo número):

  * ``precisao_ragas``: ``ragas.metrics.IDBasedContextPrecision``. Fração dos trechos recuperados
    cujo identificador está na lista de trechos certos. Não olha a posição.
  * ``precisao_posicao``: precisão média até a posição 5 (AP@5), a fórmula do Context Precision@K
    do RAGAS aplicada ao veredito do gabarito (``rag_metrics.calcular_average_precision_at_k``).
    Vale mais quando o trecho certo vem em 1º do que em 5º.

Por que por identificador e não com juiz: o gabarito já diz quais trechos respondem cada pergunta,
então a conta é determinística e roda em qualquer máquina, sem chave de API. A versão com juiz
(``ContextPrecisionWithoutReference``) fica para quando houver provedor configurado.

Limites que acompanham o número:
  * o gabarito (``rag/iris-rag/gabarito/gabarito_rascunho_v0.json``) foi marcado por um modelo,
    sem conferência humana; trecho certo que o marcador não viu conta como erro da busca;
  * o teto de ``precisao_ragas`` não é 1: uma pergunta com 2 trechos certos alcança no máximo 2/5.
    O teto de cada pergunta é calculado e relatado ao lado;
  * o gabarito cita trechos de documentos sem licença aberta, ausentes de uma base regenerada só
    com os textos versionados. ``conferir_universo`` acusa isso em vez de medir numa base parcial.

Expectativa escrita antes de rodar (11/11/2026), 38 perguntas com resposta, k=5:

  | método          | precisao_ragas | precisao_posicao |
  |-----------------|----------------|------------------|
  | bm25 (régua)    | 0,10 a 0,20    | 0,25 a 0,40      |
  | qwen3+rerank50  | 0,20 a 0,35    | 0,45 a 0,65      |

  De onde vêm as faixas: recall@5 já medido (bm25 0,20; padrão 0,42) e MRR (0,32; 0,56 no
  qwen3+rerank). O que mudaria a leitura: a diferença pareada entre o padrão e o BM25 ter
  intervalo de confiança passando pelo zero, ou o padrão ficar abaixo da faixa.

Uso:
    uv run python -m iris.eval.precisao_contexto                       # bm25 e o método padrão
    uv run python -m iris.eval.precisao_contexto --metodos bm25        # só a régua, sem banco

Grava ``reports/rag_precisao_contexto.json`` e ``reports/rag_precisao_contexto.txt``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from iris.config import RAG_BASE_DIR, REPO_ROOT
from iris.eval.rag_metrics import calcular_average_precision_at_k

GABARITO_PADRAO = RAG_BASE_DIR / "gabarito" / "gabarito_rascunho_v0.json"
SAIDA_JSON = REPO_ROOT / "reports" / "rag_precisao_contexto.json"
SAIDA_TXT = REPO_ROOT / "reports" / "rag_precisao_contexto.txt"
N_BOOT, SEMENTE = 2000, 20261105  # os mesmos do avaliar.py do pacote, para os intervalos conversarem

# (pergunta, método, n) -> identificadores dos trechos, do melhor para o pior
Ranqueador = Callable[[str, str, int], list[str]]


def carregar_gabarito(caminho: str | Path | None = None) -> list[dict]:
    """Lê as perguntas do gabarito que têm pelo menos um trecho certo."""
    dados = json.loads(Path(caminho or GABARITO_PADRAO).read_text(encoding="utf-8"))
    return [i for i in dados["itens"] if i["trechos_relevantes"]]


def conferir_universo(itens: list[dict], ids_base: set[str]) -> list[str]:
    """Devolve os trechos certos do gabarito que não existem na base carregada (vazio = base completa)."""
    citados = {cid for i in itens for cid in i["trechos_relevantes"]}
    return sorted(citados - ids_base)


def pontuar_ragas_por_id(recuperados: list[str], referencia: list[str]) -> float:
    """Context Precision do RAGAS por identificador: fração dos recuperados que está na referência."""
    if not recuperados:
        return 0.0

    from ragas import SingleTurnSample
    from ragas.metrics import IDBasedContextPrecision

    amostra = SingleTurnSample(
        retrieved_context_ids=list(recuperados),
        reference_context_ids=list(referencia),
    )

    async def _pontuar() -> float:
        return float(await IDBasedContextPrecision().single_turn_ascore(amostra))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_pontuar())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _pontuar()).result()


def ranqueador_do_pacote() -> Ranqueador:
    """Ranqueador real: ``consultar.ranking`` do pacote RAG (consulta o PostgreSQL com pgvector indicado em RAG_PG_DSN)."""
    from iris.rag.bridge import carregar_modulos_rag

    _, consultar, _ = carregar_modulos_rag()
    return lambda pergunta, metodo, n: [cid for cid, _ in consultar.ranking(pergunta, metodo, n)]


def ic_bootstrap(valores: list[float], rnd: random.Random) -> tuple[float, float]:
    """Intervalo de 95% da média, reamostrando as perguntas com reposição."""
    if not valores:
        return 0.0, 0.0
    m = len(valores)
    medias = sorted(sum(rnd.choice(valores) for _ in range(m)) / m for _ in range(N_BOOT))
    return medias[int(0.025 * N_BOOT)], medias[int(0.975 * N_BOOT) - 1]


def ic_bootstrap_pareado(a: list[float], b: list[float], rnd: random.Random) -> tuple[float, float, float]:
    """Diferença média a - b, pergunta a pergunta, e o intervalo de 95% dessa diferença."""
    d = [x - y for x, y in zip(a, b)]
    if not d:
        return 0.0, 0.0, 0.0
    m = len(d)
    medias = sorted(sum(d[rnd.randrange(m)] for _ in range(m)) / m for _ in range(N_BOOT))
    return sum(d) / m, medias[int(0.025 * N_BOOT)], medias[int(0.975 * N_BOOT) - 1]


def medir(itens: list[dict], metodo: str, ranquear: Ranqueador, k: int = 5) -> dict:
    """Mede as duas precisões de um método em todas as perguntas do gabarito."""
    por_pergunta = []
    for item in itens:
        certos = list(item["trechos_relevantes"])
        recuperados = ranquear(item["pergunta"], metodo, k)[:k]
        por_pergunta.append(
            {
                "id": item["id"],
                "n_certos": len(certos),
                "acertos": len(set(recuperados) & set(certos)),
                "precisao_ragas": pontuar_ragas_por_id(recuperados, certos),
                "precisao_posicao": calcular_average_precision_at_k(recuperados, set(certos), k=k),
                "teto_precisao_ragas": min(len(certos), k) / k,
                "recuperados": recuperados,
            }
        )
    rnd = random.Random(SEMENTE)
    resumo: dict = {}
    for nome in ("precisao_ragas", "precisao_posicao"):
        valores = [p[nome] for p in por_pergunta]
        baixo, alto = ic_bootstrap(valores, rnd)
        media = (sum(valores) / len(valores)) if valores else 0.0
        resumo[nome] = {"media": media, "ic95": [baixo, alto]}
    resumo["teto_precisao_ragas"] = (
        (sum(p["teto_precisao_ragas"] for p in por_pergunta) / len(por_pergunta)) if por_pergunta else 0.0
    )
    resumo["perguntas_sem_acerto"] = sum(1 for p in por_pergunta if p["acertos"] == 0)
    return {"metodo": metodo, "k": k, "n_perguntas": len(por_pergunta), "resumo": resumo, "por_pergunta": por_pergunta}


def acaso(itens: list[dict], n_base: int) -> float:
    """Precisão esperada de 5 trechos sorteados da base: a média de (trechos certos / trechos da base)."""
    if not itens or n_base <= 0:
        return 0.0
    return sum(len(i["trechos_relevantes"]) for i in itens) / len(itens) / n_base


def _texto(resultados: list[dict], piso: float, n_base: int, comparacao: dict | None) -> str:
    n = resultados[0]["n_perguntas"]
    linhas = [
        f"CONTEXT PRECISION (RAGAS) DA BUSCA: {n} perguntas do gabarito v0, k={resultados[0]['k']}, base de {n_base} trechos.",
        "Sem LLM juiz e sem modelo treinado: contagem de identificadores contra o gabarito (marcado por modelo,",
        f"sem conferência humana). IC 95% por bootstrap ({N_BOOT} reamostras, semente {SEMENTE}).",
        (
            f"Acaso (5 trechos sorteados, por fórmula): {piso:.4f}. "
            f"Teto da precisão por identificador neste gabarito: {resultados[0]['resumo']['teto_precisao_ragas']:.2f}."
        ),
        "",
        f"{'método':18s}{'precisão RAGAS (id)':>24s}{'precisão c/ posição (AP@5)':>30s}{'sem nenhum acerto':>20s}",
    ]
    for r in resultados:
        s = r["resumo"]
        a, b = s["precisao_ragas"], s["precisao_posicao"]
        linhas.append(
            f"{r['metodo']:18s}{a['media']:>10.2f} [{a['ic95'][0]:.2f}-{a['ic95'][1]:.2f}]"
            f"{b['media']:>16.2f} [{b['ic95'][0]:.2f}-{b['ic95'][1]:.2f}]"
            f"{s['perguntas_sem_acerto']:>14d} de {n}"
        )
    if comparacao:
        linhas.append("")
        for nome, (dif, baixo, alto) in comparacao["diferencas"].items():
            leitura = "IC exclui o zero" if baixo > 0 or alto < 0 else "IC passa pelo zero"
            linhas.append(f"{comparacao['a']} - {comparacao['b']}  {nome:18s} {dif:+.2f} [{baixo:+.2f} a {alto:+.2f}]  {leitura}")
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> None:
    from iris.config import get_settings
    from iris.rag.bridge import obter_trechos_base

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metodos", nargs="+", default=["bm25", get_settings().rag_metodo])
    ap.add_argument("--gabarito", default=None)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args(argv)

    itens = carregar_gabarito(args.gabarito)
    ids_base = {c["chunk_id"] for c in obter_trechos_base()}
    faltando = conferir_universo(itens, ids_base)
    if faltando:
        raise SystemExit(
            f"{len(faltando)} trechos do gabarito não existem na base carregada ({len(ids_base)} trechos), "
            f"por exemplo {faltando[:3]}. A base precisa dos 38 documentos; ver rag/iris-rag/pacote/README.md."
        )

    ranquear = ranqueador_do_pacote()
    resultados = [medir(itens, m, ranquear, args.k) for m in args.metodos]

    comparacao = None
    if len(resultados) >= 2:
        regua, alvo = resultados[0], resultados[-1]
        rnd = random.Random(SEMENTE)
        comparacao = {
            "a": alvo["metodo"],
            "b": regua["metodo"],
            "diferencas": {
                nome: ic_bootstrap_pareado(
                    [p[nome] for p in alvo["por_pergunta"]], [p[nome] for p in regua["por_pergunta"]], rnd
                )
                for nome in ("precisao_ragas", "precisao_posicao")
            },
        }

    piso = acaso(itens, len(ids_base))
    texto = _texto(resultados, piso, len(ids_base), comparacao)
    SAIDA_TXT.parent.mkdir(parents=True, exist_ok=True)
    SAIDA_TXT.write_text(texto, encoding="utf-8")
    SAIDA_JSON.write_text(
        json.dumps({"acaso": piso, "n_base": len(ids_base), "comparacao": comparacao, "metodos": resultados},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(texto)


if __name__ == "__main__":
    main()
