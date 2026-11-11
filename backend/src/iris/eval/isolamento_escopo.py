"""Medição do isolamento de escopo do Agente Adaptador (História 2.1.3 / Issue #18).

Duas perguntas, respondidas por contagem, sem LLM:

  1. A saída de reserva do Adaptador (regras, sem modelo), nas 30 questões do Golden Benchmark e
     nos 3 níveis, perde alguma palavra do original ou algum conceito da trava curricular?
  2. O verificador ``verificar_escopo`` acusa uma adaptação estragada de propósito? Cada saída
     recebe seis sabotagens (retirar termo da trava, trocar palavra, inserir resposta, retirar
     comando, inverter duas palavras, inverter duas etapas) e o laudo é contado.

O que esta medição não responde: a qualidade da saída com modelo gerador e a latência do RNF-07.
As saídas íntegras vêm da própria saída de reserva, escrita junto com o verificador; o alarme
falso medido aqui vale para ela, não para o texto de um modelo.

Uso:
    uv run python -m iris.eval.isolamento_escopo
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections.abc import Callable
from pathlib import Path

from iris.agents.adapter_agent import AdapterAgent
from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS, localizar_comandos, palavras, verificar_escopo
from iris.eval.trcc import avaliar_trcc
from iris.schemas.adaptation import AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants

RELATORIOS_PADRAO = Path("reports")
NOME_BASE = "adaptador_isolamento_escopo"
NIVEIS = (1, 2, 3)

# Trocas de palavra por sinônimo ou termo mais simples: o que a regra proíbe.
SINONIMOS = {
    "texto": "escrito", "frase": "sentença", "resultado": "produto", "exemplo": "caso",
    "exemplos": "casos", "equação": "conta", "valor": "número", "área": "tamanho",
    "explique": "esclareça", "calcule": "compute", "resolva": "solucione", "leia": "veja",
    "cite": "aponte", "identifique": "ache", "descreva": "conte", "determine": "descubra",
    "compare": "confronte", "circule": "marque", "assinale": "marque", "reescreva": "refaça",
    "relacione": "ligue", "balas": "doces", "ano": "época", "pontos": "lugares",
}
_RE_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]+")
_RE_ITEM = re.compile(r"^(\d+\. \[ \] )(.*)$")
_RE_PASSO = re.compile(r"^\*\*Passo \d+\*\*$")


class _SemModelo:
    """Cliente sem modelo: leva o agente direto à saída de reserva."""

    provider_name = "offline"


# ------------------------------------------------------------------ sabotagens
# Cada função devolve o texto estragado, ou None quando a sabotagem não se aplica àquele texto.


def retirar_termo_da_trava(texto: str, questao: GoldenQuestion) -> str | None:
    for conceito in questao.trava_curricular:
        for alternativa in conceito.split("|"):
            m = re.search(rf"(?<![0-9A-Za-zÀ-ÿ]){re.escape(alternativa.strip())}(?![0-9A-Za-zÀ-ÿ])", texto, re.I)
            if m:
                return texto[: m.start()] + texto[m.end() :]
    return None


def trocar_palavra(texto: str, questao: GoldenQuestion) -> str | None:
    for m in _RE_PALAVRA.finditer(texto):
        troca = SINONIMOS.get(m.group().lower())
        if troca:
            return texto[: m.start()] + troca + texto[m.end() :]
    return None


def inserir_resposta(texto: str, questao: GoldenQuestion) -> str | None:
    return texto + "\nDica: a resposta é 42."


def retirar_comando(texto: str, questao: GoldenQuestion) -> str | None:
    comandos = localizar_comandos(texto)
    if not comandos:
        return None
    ini, fim = comandos[-1]
    return texto[:ini] + texto[fim:]


def inverter_duas_palavras(texto: str, questao: GoldenQuestion) -> str | None:
    for m in re.finditer(r"([A-Za-zÀ-ÿ]+) ([A-Za-zÀ-ÿ]+)", texto):
        if m.group(1).casefold() != m.group(2).casefold():
            return texto[: m.start()] + f"{m.group(2)} {m.group(1)}" + texto[m.end() :]
    return None


def inverter_duas_etapas(texto: str, questao: GoldenQuestion) -> str | None:
    linhas = texto.splitlines()
    itens = [i for i, linha in enumerate(linhas) if _RE_ITEM.match(linha)]
    if len(itens) >= 2:  # nível 2: troca o conteúdo dos dois primeiros itens, mantendo a numeração
        a, b = itens[0], itens[1]
        ma, mb = _RE_ITEM.match(linhas[a]), _RE_ITEM.match(linhas[b])
        linhas[a], linhas[b] = ma.group(1) + mb.group(2), mb.group(1) + ma.group(2)
        return "\n".join(linhas)
    passos = [i for i, linha in enumerate(linhas) if _RE_PASSO.match(linha)]
    if len(passos) >= 2:  # nível 3: troca o comando do Passo 1 com o do Passo 2
        a, b = passos[0] + 1, passos[1] + 1
        linhas[a], linhas[b] = linhas[b], linhas[a]
        return "\n".join(linhas)
    return None


SABOTAGENS: dict[str, Callable[[str, GoldenQuestion], str | None]] = {
    "retirar termo da trava": retirar_termo_da_trava,
    "trocar palavra por sinônimo": trocar_palavra,
    "inserir resposta": inserir_resposta,
    "retirar comando": retirar_comando,
    "inverter duas palavras": inverter_duas_palavras,
    "inverter duas etapas": inverter_duas_etapas,
}


# ------------------------------------------------------------------ medição


def medir(questoes: list[GoldenQuestion]) -> dict:
    """Roda a saída de reserva e as sabotagens; devolve o resumo e os registros por questão e nível."""
    agente = AdapterAgent(llm_client=_SemModelo())
    registros: list[dict] = []
    latencias: list[float] = []
    for q in questoes:
        trava = list(q.trava_curricular)
        invariantes = CurriculumInvariants(
            conceitos_obrigatorios=trava,
            verbo_comando_bncc="identificar",
            operacao_cognitiva="Medição do isolamento de escopo com a trava do gabarito.",
        )
        trcc_original = avaliar_trcc(trava, q.enunciado).trcc
        for nivel in NIVEIS:
            resultado = agente.adapt(
                AdaptationRequest(
                    enunciado=q.enunciado,
                    id_caracteristica=ID_COMANDOS_MULTIPLOS,
                    nivel=nivel,
                    invariantes=invariantes,
                    question_id=q.id,
                )
            )
            latencias.append(resultado.telemetry.total_ms)
            adaptado = resultado.texto_adaptado
            sabotagens = {}
            for nome, sabotar in SABOTAGENS.items():
                estragado = sabotar(adaptado, q)
                if estragado is None or palavras(estragado) == palavras(adaptado):
                    sabotagens[nome] = None  # não se aplica
                    continue
                laudo = verificar_escopo(q.enunciado, estragado, ID_COMANDOS_MULTIPLOS, nivel, trava)
                sabotagens[nome] = not laudo.aprovado
            registros.append(
                {
                    "id": q.id,
                    "nivel": nivel,
                    "comandos": len(localizar_comandos(q.enunciado)),
                    "adaptacao_aplicada": resultado.adaptacao_aplicada,
                    "aprovado": resultado.escopo.aprovado,
                    "palavras_perdidas": resultado.escopo.palavras_perdidas,
                    "palavras_novas": resultado.escopo.palavras_novas,
                    "conectivos_removidos": resultado.escopo.conectivos_removidos,
                    "trcc_original": trcc_original,
                    "trcc_adaptado": avaliar_trcc(trava, adaptado).trcc,
                    "sabotagem_acusada": sabotagens,
                    "adaptado": adaptado,
                }
            )

    por_nivel = {}
    for nivel in NIVEIS:
        rs = [r for r in registros if r["nivel"] == nivel]
        por_nivel[nivel] = {
            "saidas": len(rs),
            "adaptacao_aplicada": sum(r["adaptacao_aplicada"] for r in rs),
            "com_palavra_perdida": sum(bool(r["palavras_perdidas"]) for r in rs),
            "com_palavra_nova": sum(bool(r["palavras_novas"]) for r in rs),
            "conectivos_removidos": sum(r["conectivos_removidos"] for r in rs),
            "trcc_igual_ao_original": sum(r["trcc_adaptado"] == r["trcc_original"] for r in rs),
            "trcc_menor_que_o_original": sum(r["trcc_adaptado"] < r["trcc_original"] for r in rs),
            "aprovadas": sum(r["aprovado"] for r in rs),
        }

    por_sabotagem = {}
    for nome in SABOTAGENS:
        por_sabotagem[nome] = {}
        for nivel in NIVEIS:
            vs = [r["sabotagem_acusada"][nome] for r in registros if r["nivel"] == nivel]
            aplicadas = [v for v in vs if v is not None]
            por_sabotagem[nome][nivel] = {"aplicadas": len(aplicadas), "acusadas": sum(aplicadas)}

    sabotadas = sum(c["aplicadas"] for s in por_sabotagem.values() for c in s.values())
    acusadas = sum(c["acusadas"] for s in por_sabotagem.values() for c in s.values())
    integras = len(registros)
    integras_aprovadas = sum(r["aprovado"] for r in registros)
    matriz = {
        "integra_aprovada": integras_aprovadas,
        "integra_reprovada": integras - integras_aprovadas,
        "sabotada_aprovada": sabotadas - acusadas,
        "sabotada_reprovada": acusadas,
    }
    resumo = {
        "questoes": len(questoes),
        "saidas": integras,
        "questoes_com_2_ou_mais_comandos": sum(r["comandos"] >= 2 for r in registros if r["nivel"] == 2),
        "por_nivel": por_nivel,
        "por_sabotagem": por_sabotagem,
        "matriz": matriz,
    }
    return {"resumo": resumo, "registros": registros, "latencia_mediana_ms": statistics.median(latencias)}


def _texto(resumo: dict, registros: list[dict]) -> str:
    m = resumo["matriz"]
    L = [
        "ISOLAMENTO DE ESCOPO DO AGENTE ADAPTADOR (História 2.1.3 / Issue #18)",
        "Característica: comandos múltiplos. Técnica: contagem de palavras e de conceitos da trava, sem LLM.",
        "Texto avaliado: saída de reserva do Adaptador (regras, sem modelo gerador).",
        f"Base: {resumo['questoes']} questões do Golden Benchmark x 3 níveis = {resumo['saidas']} saídas.",
        f"Questões com 2 ou mais comandos reconhecidos: {resumo['questoes_com_2_ou_mais_comandos']} de {resumo['questoes']}.",
        "",
        "1. SAÍDA DE RESERVA, POR NÍVEL",
        f"{'nível':<7}{'saídas':>8}{'adaptadas':>11}{'perdeu palavra':>16}{'palavra nova':>14}"
        f"{'\"e\" retirados':>15}{'TRCC igual':>12}{'TRCC menor':>12}{'aprovadas':>11}",
    ]
    for nivel, c in resumo["por_nivel"].items():
        L.append(
            f"{nivel:<7}{c['saidas']:>8}{c['adaptacao_aplicada']:>11}{c['com_palavra_perdida']:>16}"
            f"{c['com_palavra_nova']:>14}{c['conectivos_removidos']:>15}{c['trcc_igual_ao_original']:>12}"
            f"{c['trcc_menor_que_o_original']:>12}{c['aprovadas']:>11}"
        )
    L += [
        "\"adaptadas\": saídas diferentes do original. Nos níveis 2 e 3 a questão de um comando só volta sem alteração.",
        "\"e\" retirados: conectivo entre dois comandos, que a lista de etapas substitui; única retirada tolerada.",
        "",
        "2. SABOTAGENS ACUSADAS PELO VERIFICADOR (acusadas / aplicadas)",
        f"{'sabotagem':<30}{'nível 1':>10}{'nível 2':>10}{'nível 3':>10}{'total':>10}",
    ]
    for nome, niveis in resumo["por_sabotagem"].items():
        celulas = [f"{c['acusadas']}/{c['aplicadas']}" for c in niveis.values()]
        total = f"{sum(c['acusadas'] for c in niveis.values())}/{sum(c['aplicadas'] for c in niveis.values())}"
        L.append(f"{nome:<30}" + "".join(f"{c:>10}" for c in celulas) + f"{total:>10}")
    L += [
        "Uma sabotagem não se aplica quando o texto não tem o que estragar (sem comando, sem etapas, sem a palavra).",
        "",
        "3. MATRIZ DE CONFUSÃO DO VERIFICADOR",
        f"{'':<22}{'aprovou':>10}{'reprovou':>10}",
        f"{'saída íntegra':<22}{m['integra_aprovada']:>10}{m['integra_reprovada']:>10}",
        f"{'saída sabotada':<22}{m['sabotada_aprovada']:>10}{m['sabotada_reprovada']:>10}",
        "Referência: um verificador que aprova tudo acusaria 0 sabotagens; um que só confere a trava (TRCC)",
        "acusa apenas a retirada de termo da trava.",
        "",
        "4. SAÍDAS DO NÍVEL 2 (questões com 2 ou mais comandos)",
    ]
    for r in registros:
        if r["nivel"] == 2 and r["adaptacao_aplicada"]:
            L.append(f"[{r['id']}]")
            L += ["    " + linha for linha in r["adaptado"].splitlines()]
    return "\n".join(L) + "\n"


def _figura(resumo: dict, caminho: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    m = resumo["matriz"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1, 1.5]})

    matriz = [[m["integra_aprovada"], m["integra_reprovada"]], [m["sabotada_aprovada"], m["sabotada_reprovada"]]]
    certo = [[True, False], [False, True]]
    for i in range(2):
        for j in range(2):
            ax1.add_patch(plt.Rectangle((j, 1 - i), 1, 1, color="#2a6f97" if certo[i][j] else "#e9ecef"))
            ax1.text(j + 0.5, 1.5 - i, str(matriz[i][j]), ha="center", va="center", fontsize=20,
                     color="white" if certo[i][j] else "#333333")
    ax1.set_xlim(0, 2)
    ax1.set_ylim(0, 2)
    ax1.set_xticks([0.5, 1.5], ["aprovou", "reprovou"])
    ax1.set_yticks([1.5, 0.5], ["saída íntegra", "saída sabotada"])
    ax1.set_xlabel("laudo do verificador")
    ax1.set_title("Matriz de confusão do verificador", fontsize=11)
    ax1.tick_params(length=0)
    for lado in ax1.spines.values():
        lado.set_visible(False)

    nomes = list(resumo["por_sabotagem"])
    for i, nome in enumerate(nomes):
        for j, c in enumerate(resumo["por_sabotagem"][nome].values()):
            taxa = c["acusadas"] / c["aplicadas"] if c["aplicadas"] else None
            cor = "#f8f9fa" if taxa is None else ("#2a6f97" if taxa == 1 else "#c1121f")
            ax2.add_patch(plt.Rectangle((j, len(nomes) - 1 - i), 1, 1, facecolor=cor, edgecolor="white"))
            rotulo = "não se aplica" if taxa is None else f"{c['acusadas']} de {c['aplicadas']}"
            ax2.text(j + 0.5, len(nomes) - 0.5 - i, rotulo, ha="center", va="center", fontsize=10,
                     color="#666666" if taxa is None else "white")
    ax2.set_xlim(0, 3)
    ax2.set_ylim(0, len(nomes))
    ax2.set_xticks([0.5, 1.5, 2.5], ["nível 1", "nível 2", "nível 3"])
    ax2.set_yticks([len(nomes) - 0.5 - i for i in range(len(nomes))], nomes)
    ax2.set_title("Sabotagens acusadas, por tipo e nível\n(azul: todas; vermelho: alguma passou)", fontsize=11)
    ax2.tick_params(length=0)
    for lado in ax2.spines.values():
        lado.set_visible(False)

    fig.suptitle(
        f"Isolamento de escopo, comandos múltiplos: {resumo['questoes']} questões x 3 níveis, contagem sem LLM",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def gerar_relatorio(pasta: str | Path = RELATORIOS_PADRAO, caminho_benchmark: str | Path | None = None) -> dict:
    """Mede e grava ``adaptador_isolamento_escopo`` (.txt, .json e .png) em ``pasta``."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    medicao = medir(carregar_golden_benchmark(caminho_benchmark))
    resumo, registros = medicao["resumo"], medicao["registros"]
    (pasta / f"{NOME_BASE}.txt").write_text(_texto(resumo, registros), encoding="utf-8")
    (pasta / f"{NOME_BASE}.json").write_text(
        json.dumps({"resumo": resumo, "registros": registros}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _figura(resumo, pasta / f"{NOME_BASE}.png")
    return medicao


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pasta", default=str(RELATORIOS_PADRAO))
    parser.add_argument("--benchmark", default=None)
    args = parser.parse_args()
    medicao = gerar_relatorio(args.pasta, args.benchmark)
    print((Path(args.pasta) / f"{NOME_BASE}.txt").read_text(encoding="utf-8"))
    # A latência varia a cada execução e por isso não entra nos arquivos versionados.
    print(f"Latência mediana da saída de reserva: {medicao['latencia_mediana_ms']:.2f} ms (sem modelo; "
          "não responde ao RNF-07).")


if __name__ == "__main__":
    main()
