"""Medição do Agente Adaptador com modelo gerador (História 2.1.3 / Issue #18, RF-04, RF-11 e RNF-07).

Duas perguntas, nas 30 questões do Golden Benchmark e nos 3 níveis (90 chamadas):

  1. Quantas saídas do modelo passam no verificador de isolamento de escopo, e por que as demais
     reprovam (palavra perdida, palavra nova, ordem, estrutura do nível 1, conceito da trava)?
  2. Quanto tempo leva cada adaptação, comparado ao limite do RNF-07 (15 s no nível 1, 40 s nos
     níveis 2 e 3)?

Base de comparação: a saída de reserva (regras, sem modelo), aprovada em 90 de 90 saídas em
``adaptador_isolamento_escopo``. O modelo só acrescenta valor nas saídas em que passa no laudo.

Expectativa escrita antes de rodar (llama3.1:8b local, temperatura 0, Mac com 24 GB):

  - aprovadas no escopo: nível 1 de 40% a 80%; nível 2 de 20% a 60%; nível 3 de 10% a 50%. O nível 3
    é o mais restrito (vocabulário do andaime fechado) e o modelo tende a escrever "Etapa" ou
    instruções próprias.
  - quedas na saída de reserva no total: de 40% a 80% das 90 chamadas.
  - JSON válido: de 85% a 100% (o pedido usa ``json_mode``).
  - latência por chamada, sem o carregamento inicial: mediana de 5 a 12 s no nível 1 e de 8 a 18 s
    nos níveis 2 e 3; carregamento do modelo na primeira chamada de 3 a 10 s.

O que mudaria a leitura: aprovação abaixo de 20% em todos os níveis indica que, com este verificador,
quem adapta é a saída de reserva e o modelo só acrescenta latência; mediana do nível 1 acima de 15 s
indica que o RNF-07 não se cumpre com este modelo nesta máquina, antes mesmo de somar o Extrator.

Limitações: mede só o Adaptador (o RNF-07 vale para o ciclo inteiro); a latência é desta máquina;
o verificador compara palavras e não avalia se a adaptação ajuda o estudante.

Uso:
    uv run python -m iris.eval.adaptador_com_modelo
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from iris.agents.adapter_agent import AdapterAgent
from iris.core.llm_client import HybridLLMClient, LLMResponse
from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS, verificar_escopo
from iris.schemas.adaptation import LIMITE_LATENCIA_MS, AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants

RELATORIOS_PADRAO = Path("reports")
NOME_BASE = "adaptador_com_modelo"
NIVEIS = (1, 2, 3)

# Desfechos de cada chamada, na ordem em que aparecem na tabela e na figura.
DESFECHOS = (
    "aprovada e adaptou",
    "aprovada sem adaptar",
    "reprovada no escopo",
    "falha do modelo",
)

# Motivo de reprovação, pela ordem de prioridade com que é contado (uma saída conta uma vez).
MOTIVOS = (
    ("conceito da trava", lambda e: bool(e.conceitos_perdidos)),
    ("palavra perdida", lambda e: bool(e.palavras_perdidas)),
    ("palavra nova", lambda e: bool(e.palavras_novas)),
    ("ordem alterada", lambda e: e.ordem_alterada),
    ("texto do nível 1 alterado", lambda e: e.estrutura_alterada),
)


class _Gravador:
    """Repassa as chamadas ao cliente real e guarda a última resposta, para laudar o texto do modelo."""

    def __init__(self, cliente: HybridLLMClient) -> None:
        self.cliente = cliente
        self.provider_name = cliente.provider_name
        self.ultima: LLMResponse | None = None

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        self.ultima = None
        self.ultima = self.cliente.generate(prompt=prompt, **kwargs)
        return self.ultima


def _pedido(q: GoldenQuestion, nivel: int) -> AdaptationRequest:
    return AdaptationRequest(
        enunciado=q.enunciado,
        id_caracteristica=ID_COMANDOS_MULTIPLOS,
        nivel=nivel,
        invariantes=CurriculumInvariants(
            conceitos_obrigatorios=list(q.trava_curricular),
            verbo_comando_bncc="identificar",
            operacao_cognitiva="Medição do Adaptador com modelo, com a trava do gabarito.",
        ),
        question_id=q.id,
    )


def _percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p
    i = int(k)
    j = min(i + 1, len(ordenados) - 1)
    return ordenados[i] + (ordenados[j] - ordenados[i]) * (k - i)


def medir(questoes: list[GoldenQuestion], cliente: HybridLLMClient | None = None) -> dict:
    """Roda o Adaptador com o modelo em cada questão e nível; devolve o resumo e os registros."""
    gravador = _Gravador(cliente or HybridLLMClient())
    agente = AdapterAgent(llm_client=gravador)

    # Chamada de aquecimento, fora da contagem: carrega o modelo na memória e mede esse custo à parte.
    aquecimento = agente.adapt(_pedido(questoes[0], 1)).telemetry

    registros: list[dict] = []
    for q in questoes:
        trava = list(q.trava_curricular)
        for nivel in NIVEIS:
            resultado = agente.adapt(_pedido(q, nivel))
            t = resultado.telemetry
            texto_modelo, laudo_modelo = None, None
            if gravador.ultima is not None:
                try:
                    texto_modelo, _, _ = AdapterAgent._parse_json_response(gravador.ultima.text)
                    laudo_modelo = verificar_escopo(q.enunciado, texto_modelo, ID_COMANDOS_MULTIPLOS, nivel, trava)
                except Exception:
                    texto_modelo = None

            if laudo_modelo is None:
                desfecho, motivo = "falha do modelo", t.motivo_fallback
            elif laudo_modelo.aprovado:
                adaptou = texto_modelo.strip() != q.enunciado.strip()
                desfecho, motivo = ("aprovada e adaptou" if adaptou else "aprovada sem adaptar"), None
            else:
                desfecho = "reprovada no escopo"
                motivo = next(nome for nome, teste in MOTIVOS if teste(laudo_modelo))
            print(f"{q.id} nível {nivel}: {desfecho}{f' ({motivo})' if motivo else ''}, "
                  f"{t.total_ms / 1000:.1f} s", flush=True)

            registros.append(
                {
                    "id": q.id,
                    "nivel": nivel,
                    "desfecho": desfecho,
                    "motivo": motivo,
                    "violacoes": laudo_modelo.violacoes if laudo_modelo else [],
                    "json_valido_direto": t.json_valido_direto,
                    "used_fallback": t.used_fallback,
                    "total_ms": t.total_ms,
                    "load_ms": t.load_ms,
                    "inference_ms": t.inference_ms,
                    "prompt_tokens": t.prompt_tokens,
                    "completion_tokens": t.completion_tokens,
                    "tokens_per_sec": t.tokens_per_sec,
                    "limite_ms": t.limite_ms,
                    "dentro_do_limite": t.dentro_do_limite,
                    "texto_modelo": texto_modelo,
                    "texto_entregue": resultado.texto_adaptado,
                }
            )

    por_nivel = {}
    for nivel in NIVEIS:
        rs = [r for r in registros if r["nivel"] == nivel]
        ms = [r["total_ms"] for r in rs]
        por_nivel[nivel] = {
            "chamadas": len(rs),
            "desfechos": {d: sum(r["desfecho"] == d for r in rs) for d in DESFECHOS},
            "motivos": {m: sum(r["motivo"] == m for r in rs) for m, _ in MOTIVOS},
            "json_valido": sum(r["texto_modelo"] is not None for r in rs),
            "saida_de_reserva": sum(r["used_fallback"] for r in rs),
            "latencia_mediana_ms": round(statistics.median(ms), 1),
            "latencia_p90_ms": round(_percentil(ms, 0.9), 1),
            "latencia_max_ms": round(max(ms), 1),
            "limite_ms": LIMITE_LATENCIA_MS[nivel],
            "dentro_do_limite": sum(r["dentro_do_limite"] for r in rs),
            "tokens_saida_mediana": statistics.median(r["completion_tokens"] for r in rs),
            "tokens_por_segundo_mediana": round(statistics.median(r["tokens_per_sec"] for r in rs), 1),
        }

    resumo = {
        "questoes": len(questoes),
        "chamadas": len(registros),
        "provedor": aquecimento.provider,
        "modelo": aquecimento.model,
        "aquecimento": {"total_ms": aquecimento.total_ms, "load_ms": aquecimento.load_ms},
        "por_nivel": por_nivel,
        "saida_de_reserva_total": sum(r["used_fallback"] for r in registros),
    }
    return {"resumo": resumo, "registros": registros}


def _texto(resumo: dict, registros: list[dict]) -> str:
    n = resumo["chamadas"]
    L = [
        "AGENTE ADAPTADOR COM MODELO GERADOR (História 2.1.3 / Issue #18)",
        f"Modelo: {resumo['provedor']} / {resumo['modelo']}, temperatura 0. Característica: comandos múltiplos.",
        f"Base: {resumo['questoes']} questões do Golden Benchmark x 3 níveis = {n} chamadas, uma por questão e nível.",
        "Técnica: o texto do modelo passa pelo verificar_escopo (contagem de palavras, ordem e trava, sem LLM);",
        "a latência é o tempo de relógio de cada chamada ao Adaptador, medido nesta máquina.",
        "Base de comparação: a saída de reserva (regras, sem modelo) foi aprovada em 90 de 90 saídas.",
        "",
        "1. DESFECHO DO TEXTO DO MODELO, POR NÍVEL",
        f"{'nível':<7}" + "".join(f"{d:>23}" for d in DESFECHOS) + f"{'foi p/ reserva':>16}",
    ]
    for nivel, c in resumo["por_nivel"].items():
        L.append(
            f"{nivel:<7}" + "".join(f"{c['desfechos'][d]:>23}" for d in DESFECHOS) + f"{c['saida_de_reserva']:>16}"
        )
    L += [
        "\"aprovada sem adaptar\": o modelo devolveu o enunciado igual; passa no laudo, mas não ajuda.",
        "\"foi p/ reserva\": o agente entregou a saída de reserva no lugar do texto do modelo.",
        "",
        "2. MOTIVO DA REPROVAÇÃO (cada saída conta uma vez, pelo primeiro motivo da lista)",
        f"{'motivo':<28}{'nível 1':>10}{'nível 2':>10}{'nível 3':>10}",
    ]
    for m, _ in MOTIVOS:
        L.append(f"{m:<28}" + "".join(f"{c['motivos'][m]:>10}" for c in resumo["por_nivel"].values()))
    L += [
        "",
        "3. LATÊNCIA POR CHAMADA, CONTRA O RNF-07 (só o Adaptador; o ciclo soma o Extrator)",
        f"{'nível':<7}{'limite':>9}{'mediana':>10}{'p90':>10}{'máximo':>10}{'dentro':>9}{'tokens saída':>14}{'tokens/s':>10}",
    ]
    for nivel, c in resumo["por_nivel"].items():
        L.append(
            f"{nivel:<7}{c['limite_ms'] / 1000:>8.0f}s{c['latencia_mediana_ms'] / 1000:>9.1f}s"
            f"{c['latencia_p90_ms'] / 1000:>9.1f}s{c['latencia_max_ms'] / 1000:>9.1f}s"
            f"{c['dentro_do_limite']:>5} de {c['chamadas']}"
            f"{c['tokens_saida_mediana']:>11.0f}{c['tokens_por_segundo_mediana']:>10.1f}"
        )
    a = resumo["aquecimento"]
    L += [
        f"Aquecimento (fora da contagem): {a['total_ms'] / 1000:.1f} s, dos quais {a['load_ms'] / 1000:.1f} s de "
        "carregamento do modelo.",
        "",
        "4. EXEMPLOS DE REPROVAÇÃO (primeira de cada motivo)",
    ]
    vistos = set()
    for r in registros:
        if r["motivo"] in vistos or r["desfecho"] != "reprovada no escopo":
            continue
        vistos.add(r["motivo"])
        L.append(f"[{r['id']}, nível {r['nivel']}] {r['motivo']}: {'; '.join(r['violacoes'])}")
        L += ["    " + linha for linha in (r["texto_modelo"] or "").splitlines()]
    return "\n".join(L) + "\n"


def _figura(resumo: dict, caminho: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cores = {
        "aprovada e adaptou": "#2a6f97",
        "aprovada sem adaptar": "#a9c5d6",
        "reprovada no escopo": "#c1121f",
        "falha do modelo": "#6c757d",
    }
    niveis = list(resumo["por_nivel"])
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    base = [0] * len(niveis)
    for d in DESFECHOS:
        valores = [resumo["por_nivel"][n]["desfechos"][d] for n in niveis]
        ax1.bar([f"nível {n}" for n in niveis], valores, bottom=base, color=cores[d], label=d)
        for i, v in enumerate(valores):
            if v:
                ax1.text(i, base[i] + v / 2, str(v), ha="center", va="center", fontsize=10,
                         color="white" if d != "aprovada sem adaptar" else "#333333")
        base = [b + v for b, v in zip(base, valores)]
    ax1.set_ylabel("chamadas (de 30 por nível)")
    ax1.set_title("O texto do modelo passou no verificador de escopo?\n(régua: a saída de reserva passa em 30 de 30)",
                  fontsize=11)
    ax1.legend(fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    for lado in ("top", "right"):
        ax1.spines[lado].set_visible(False)

    registros = resumo["_registros"]
    for i, n in enumerate(niveis):
        segundos = [r["total_ms"] / 1000 for r in registros if r["nivel"] == n]
        ax2.scatter([i + 1 + (k % 7 - 3) * 0.03 for k in range(len(segundos))], segundos, s=14,
                    color="#2a6f97", alpha=0.7)
        limite = resumo["por_nivel"][n]["limite_ms"] / 1000
        ax2.hlines(limite, i + 0.65, i + 1.35, color="#c1121f", linewidth=2)
        ax2.text(i + 1, limite + 0.8, f"limite {limite:.0f} s", ha="center", va="bottom", fontsize=9, color="#c1121f")
        mediana = resumo["por_nivel"][n]["latencia_mediana_ms"] / 1000
        ax2.hlines(mediana, i + 0.75, i + 1.25, color="#333333", linewidth=1.5)
    ax2.set_xticks([1, 2, 3], [f"nível {n}" for n in niveis])
    ax2.set_xlim(0.5, 3.5)
    ax2.set_ylim(0, max(resumo["por_nivel"][n]["limite_ms"] for n in niveis) / 1000 * 1.15)
    ax2.set_ylabel("segundos por chamada")
    ax2.set_title("Latência de cada chamada contra o RNF-07\n(traço preto: mediana; vermelho: limite)", fontsize=11)
    for lado in ("top", "right"):
        ax2.spines[lado].set_visible(False)

    fig.suptitle(f"Agente Adaptador com {resumo['modelo']}: {resumo['questoes']} questões x 3 níveis, nesta máquina",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def gerar_relatorio(pasta: str | Path = RELATORIOS_PADRAO, caminho_benchmark: str | Path | None = None,
                    limite_questoes: int | None = None) -> dict:
    """Mede e grava ``adaptador_com_modelo`` (.txt, .json e .png) em ``pasta``."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    questoes = carregar_golden_benchmark(caminho_benchmark)[:limite_questoes]
    medicao = medir(questoes)
    resumo, registros = medicao["resumo"], medicao["registros"]
    (pasta / f"{NOME_BASE}.txt").write_text(_texto(resumo, registros), encoding="utf-8")
    (pasta / f"{NOME_BASE}.json").write_text(
        json.dumps({"resumo": resumo, "registros": registros}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _figura({**resumo, "_registros": registros}, pasta / f"{NOME_BASE}.png")
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
