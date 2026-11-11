"""Latência do ciclo Extrator + Adaptador contra o RNF-07 (História 2.1.3 / Issue #18).

O critério de aceite da história limita o tempo total de processamento (15 s no nível 1, 40 s nos
níveis 2 e 3). Cada ciclo aqui é o caminho de uma adaptação: o Agente Extrator lê o enunciado, sem a
trava do gabarito, e devolve os invariantes curriculares; o Agente Adaptador adapta com esses
invariantes. A soma das duas chamadas vem de ``resumir_ciclo``. São 30 questões do Golden Benchmark x
3 níveis = 90 ciclos, cada um com Extrator e Adaptador chamados de novo.

Também se confere se o texto entregue mantém os conceitos da trava do gabarito (TRCC igual ao do
original), já que no ciclo o Adaptador recebe a trava extraída e não a do gabarito.

Fora do ciclo medido: o Agente Estrategista (plano do RAG, issue #16), que ainda não existe no código,
e o tempo de rede e de interface da API.

Expectativa escrita antes de rodar (llama3.1:8b local, temperatura 0, Mac com 24 GB; o Adaptador
sozinho levou mediana de 5,1 s no nível 1 e 6,8 s no nível 3 em ``adaptador_com_modelo``):

  - Extrator: mediana de 4 a 9 s por chamada; queda na extração por regras em 0% a 10%.
  - ciclo, nível 1: mediana de 9 a 14 s; de 70% a 100% dos 30 ciclos dentro de 15 s.
  - ciclo, níveis 2 e 3: mediana de 9 a 16 s; 100% dentro de 40 s.
  - TRCC do texto entregue igual ao do original em 28 a 30 ciclos por nível.

O que mudaria a leitura: menos de 70% dos ciclos do nível 1 dentro de 15 s indica que o RNF-07 não se
cumpre neste modelo e nesta máquina, e que o nível 1 precisa de outro caminho (por exemplo, a saída por
regras, que leva menos de 1 ms); TRCC menor em mais de 2 ciclos indica que a trava extraída deixa
passar perda de conceito que a trava do gabarito pegaria.

Uso:
    uv run python -m iris.eval.adaptador_ciclo
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from iris.agents.adapter_agent import AdapterAgent, resumir_ciclo
from iris.agents.curriculum_extractor import CurriculumExtractorAgent
from iris.core.llm_client import HybridLLMClient
from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS
from iris.eval.trcc import avaliar_trcc
from iris.schemas.adaptation import LIMITE_LATENCIA_MS, AdaptationRequest

RELATORIOS_PADRAO = Path("reports")
NOME_BASE = "adaptador_ciclo"
NIVEIS = (1, 2, 3)


def _percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p
    i = int(k)
    j = min(i + 1, len(ordenados) - 1)
    return ordenados[i] + (ordenados[j] - ordenados[i]) * (k - i)


def medir(questoes: list[GoldenQuestion], cliente: HybridLLMClient | None = None) -> dict:
    """Roda Extrator e Adaptador em cada questão e nível; devolve o resumo e os registros por ciclo."""
    cliente = cliente or HybridLLMClient()
    extrator = CurriculumExtractorAgent(llm_client=cliente)
    adaptador = AdapterAgent(llm_client=cliente)

    # Aquecimento fora da contagem: carrega o modelo na memória.
    aquecimento = extrator.extract_golden_with_telemetry(questoes[0]).telemetry

    registros: list[dict] = []
    for q in questoes:
        trava_gabarito = list(q.trava_curricular)
        trcc_original = avaliar_trcc(trava_gabarito, q.enunciado).trcc
        for nivel in NIVEIS:
            extracao = extrator.extract_golden_with_telemetry(q)
            resultado = adaptador.adapt(
                AdaptationRequest(
                    enunciado=q.enunciado,
                    id_caracteristica=ID_COMANDOS_MULTIPLOS,
                    nivel=nivel,
                    invariantes=extracao.invariants,
                    question_id=q.id,
                )
            )
            ciclo = resumir_ciclo([extracao.telemetry, resultado.telemetry], nivel)
            registro = {
                "id": q.id,
                "nivel": nivel,
                "extrator_ms": extracao.telemetry.total_ms,
                "adaptador_ms": resultado.telemetry.total_ms,
                "ciclo_ms": ciclo["total_ms"],
                "limite_ms": ciclo["limite_ms"],
                "dentro_do_limite": ciclo["dentro_do_limite"],
                "total_tokens": ciclo["total_tokens"],
                "extrator_fallback": extracao.telemetry.used_fallback,
                "adaptador_fallback": resultado.telemetry.used_fallback,
                "motivo_fallback": resultado.telemetry.motivo_fallback,
                "escopo_aprovado": resultado.escopo.aprovado,
                "trava_extraida": list(extracao.invariants.conceitos_obrigatorios),
                "trcc_original": trcc_original,
                "trcc_entregue": avaliar_trcc(trava_gabarito, resultado.texto_adaptado).trcc,
            }
            registros.append(registro)
            print(
                f"{q.id} nível {nivel}: ciclo {registro['ciclo_ms'] / 1000:.1f} s "
                f"(Extrator {registro['extrator_ms'] / 1000:.1f} s + Adaptador {registro['adaptador_ms'] / 1000:.1f} s)"
                f"{'' if registro['dentro_do_limite'] else ' ACIMA DO LIMITE'}",
                flush=True,
            )

    por_nivel = {}
    for nivel in NIVEIS:
        rs = [r for r in registros if r["nivel"] == nivel]
        ciclos = [r["ciclo_ms"] for r in rs]
        por_nivel[nivel] = {
            "ciclos": len(rs),
            "limite_ms": LIMITE_LATENCIA_MS[nivel],
            "dentro_do_limite": sum(r["dentro_do_limite"] for r in rs),
            "ciclo_mediana_ms": round(statistics.median(ciclos), 1),
            "ciclo_p90_ms": round(_percentil(ciclos, 0.9), 1),
            "ciclo_max_ms": round(max(ciclos), 1),
            "extrator_mediana_ms": round(statistics.median(r["extrator_ms"] for r in rs), 1),
            "adaptador_mediana_ms": round(statistics.median(r["adaptador_ms"] for r in rs), 1),
            "tokens_mediana": statistics.median(r["total_tokens"] for r in rs),
            "extrator_fallback": sum(r["extrator_fallback"] for r in rs),
            "adaptador_fallback": sum(r["adaptador_fallback"] for r in rs),
            "trcc_igual_ao_original": sum(r["trcc_entregue"] == r["trcc_original"] for r in rs),
            "trcc_menor_que_o_original": sum(r["trcc_entregue"] < r["trcc_original"] for r in rs),
        }

    resumo = {
        "questoes": len(questoes),
        "ciclos": len(registros),
        "provedor": aquecimento.provider,
        "modelo": aquecimento.model,
        "aquecimento_ms": aquecimento.total_ms,
        "por_nivel": por_nivel,
    }
    return {"resumo": resumo, "registros": registros}


def _texto(resumo: dict, registros: list[dict]) -> str:
    L = [
        "CICLO EXTRATOR + ADAPTADOR CONTRA O RNF-07 (História 2.1.3 / Issue #18)",
        f"Modelo: {resumo['provedor']} / {resumo['modelo']}, temperatura 0, nos dois agentes. Característica: comandos múltiplos.",
        f"Base: {resumo['questoes']} questões do Golden Benchmark x 3 níveis = {resumo['ciclos']} ciclos.",
        "Técnica: tempo de relógio de cada agente, somado por resumir_ciclo; TRCC do texto entregue com a trava do gabarito.",
        "Fora do ciclo: Agente Estrategista (plano do RAG, issue #16) e tempo de rede e interface da API.",
        "",
        "1. TEMPO DO CICLO, POR NÍVEL",
        f"{'nível':<7}{'limite':>8}{'Extrator':>10}{'Adaptador':>11}{'ciclo':>9}{'p90':>8}{'máximo':>9}{'dentro':>11}{'tokens':>8}",
        f"{'':<7}{'':>8}{'mediana':>10}{'mediana':>11}{'mediana':>9}",
    ]
    for nivel, c in resumo["por_nivel"].items():
        L.append(
            f"{nivel:<7}{c['limite_ms'] / 1000:>7.0f}s{c['extrator_mediana_ms'] / 1000:>9.1f}s"
            f"{c['adaptador_mediana_ms'] / 1000:>10.1f}s{c['ciclo_mediana_ms'] / 1000:>8.1f}s"
            f"{c['ciclo_p90_ms'] / 1000:>7.1f}s{c['ciclo_max_ms'] / 1000:>8.1f}s"
            f"{c['dentro_do_limite']:>5} de {c['ciclos']}{c['tokens_mediana']:>8.0f}"
        )
    L += [
        f"Aquecimento (fora da contagem): {resumo['aquecimento_ms'] / 1000:.1f} s.",
        "",
        "2. QUEDAS NA SAÍDA POR REGRAS E RETENÇÃO DOS CONCEITOS",
        f"{'nível':<7}{'Extrator p/ regras':>20}{'Adaptador p/ regras':>21}{'TRCC igual':>12}{'TRCC menor':>12}",
    ]
    for nivel, c in resumo["por_nivel"].items():
        L.append(
            f"{nivel:<7}{c['extrator_fallback']:>20}{c['adaptador_fallback']:>21}"
            f"{c['trcc_igual_ao_original']:>12}{c['trcc_menor_que_o_original']:>12}"
        )
    L += [
        "TRCC: fração dos conceitos da trava do gabarito presentes no texto; \"igual\" compara entregue e original.",
        "",
        "3. CICLOS ACIMA DO LIMITE",
    ]
    acima = [r for r in registros if not r["dentro_do_limite"]]
    L += [
        f"[{r['id']}, nível {r['nivel']}] {r['ciclo_ms'] / 1000:.1f} s "
        f"(Extrator {r['extrator_ms'] / 1000:.1f} s + Adaptador {r['adaptador_ms'] / 1000:.1f} s)"
        for r in acima
    ] or ["nenhum"]
    return "\n".join(L) + "\n"


def _figura(resumo: dict, registros: list[dict], caminho: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    niveis = [int(n) for n in resumo["por_nivel"]]
    por_nivel = {int(n): c for n, c in resumo["por_nivel"].items()}
    teto = max(c["limite_ms"] for c in por_nivel.values()) / 1000 * 1.15
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    rotulos = [f"nível {n}" for n in niveis]
    extr = [por_nivel[n]["extrator_mediana_ms"] / 1000 for n in niveis]
    adap = [por_nivel[n]["adaptador_mediana_ms"] / 1000 for n in niveis]
    ax1.bar(rotulos, extr, color="#a9c5d6", label="Extrator")
    ax1.bar(rotulos, adap, bottom=extr, color="#2a6f97", label="Adaptador")
    for i, n in enumerate(niveis):
        limite = por_nivel[n]["limite_ms"] / 1000
        ax1.hlines(limite, i - 0.4, i + 0.4, color="#c1121f", linewidth=2)
        ax1.text(i, limite + 0.8, f"limite {limite:.0f} s", ha="center", va="bottom", fontsize=9, color="#c1121f")
        ax1.text(i, extr[i] + adap[i] + 0.5, f"{extr[i] + adap[i]:.1f} s", ha="center", va="bottom", fontsize=10)
    ax1.set_ylim(0, teto)
    ax1.set_ylabel("segundos (mediana)")
    ax1.set_title("Onde o tempo do ciclo é gasto (mediana de 30 ciclos)", fontsize=11)
    ax1.legend(fontsize=9, frameon=False, loc="upper left")
    for lado in ("top", "right"):
        ax1.spines[lado].set_visible(False)

    for i, n in enumerate(niveis):
        rs = [r for r in registros if r["nivel"] == n]
        ax2.scatter([i + 1 + (k % 7 - 3) * 0.03 for k in range(len(rs))], [r["ciclo_ms"] / 1000 for r in rs], s=14,
                    color=["#2a6f97" if r["dentro_do_limite"] else "#c1121f" for r in rs], alpha=0.8)
        limite = por_nivel[n]["limite_ms"] / 1000
        ax2.hlines(limite, i + 0.65, i + 1.35, color="#c1121f", linewidth=2)
        ax2.text(i + 1, limite + 0.8, f"limite {limite:.0f} s", ha="center", va="bottom", fontsize=9, color="#c1121f")
        ax2.hlines(por_nivel[n]["ciclo_mediana_ms"] / 1000, i + 0.75, i + 1.25, color="#333333", linewidth=1.5)
        ax2.text(i + 1, 0.02 * teto, f"{por_nivel[n]['dentro_do_limite']} de {por_nivel[n]['ciclos']} dentro",
                 ha="center", va="bottom", fontsize=9)
    ax2.set_xticks([1, 2, 3], rotulos)
    ax2.set_xlim(0.5, 3.5)
    ax2.set_ylim(0, teto)
    ax2.set_ylabel("segundos por ciclo")
    ax2.set_title("Cada ciclo contra o limite (traço preto: mediana)", fontsize=11)
    for lado in ("top", "right"):
        ax2.spines[lado].set_visible(False)

    fig.suptitle(f"Ciclo Extrator + Adaptador com {resumo['modelo']}: {resumo['ciclos']} ciclos, nesta máquina",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def gerar_relatorio(pasta: str | Path = RELATORIOS_PADRAO, caminho_benchmark: str | Path | None = None,
                    limite_questoes: int | None = None) -> dict:
    """Mede e grava ``adaptador_ciclo`` (.txt, .json e .png) em ``pasta``."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    medicao = medir(carregar_golden_benchmark(caminho_benchmark)[:limite_questoes])
    resumo, registros = medicao["resumo"], medicao["registros"]
    (pasta / f"{NOME_BASE}.txt").write_text(_texto(resumo, registros), encoding="utf-8")
    (pasta / f"{NOME_BASE}.json").write_text(
        json.dumps({"resumo": resumo, "registros": registros}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _figura(resumo, registros, pasta / f"{NOME_BASE}.png")
    return medicao


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pasta", default=str(RELATORIOS_PADRAO))
    parser.add_argument("--benchmark", default=None)
    parser.add_argument("--limite-questoes", type=int, default=None, help="para teste rápido do script")
    args = parser.parse_args()
    gerar_relatorio(args.pasta, args.benchmark, args.limite_questoes)
    print((Path(args.pasta) / f"{NOME_BASE}.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
