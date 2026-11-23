"""Avaliação reproduzível ponta a ponta do ciclo dos 4 agentes (RNF-04, RNF-05, RNF-07, RNF-08).

Executa o pipeline multiagentes completo sobre as questões do Golden Benchmark:
  1. Agente Extrator Curricular (#17)
  2. Agente Estrategista RAG (#16)
  3. Agente Adaptador Pedagógico (#18)
  4. Agente Auditor de Integridade (#19) em ciclo com o Adaptador (CicloComAuditor)

Aceita provedores determinísticos sem rede (`eco`, `extractive`) para validar encanamento,
contratos, citações, isolamento de escopo e travas em CI/local, além de provedores reais
(`ollama`, `anthropic`, `groq`) para medição comportamental e de latência contra o RNF-07.

Uso:
    PYTHONPATH=backend/src .venv/bin/python3 -m iris.eval.multiagentes_ciclo --provider eco
    PYTHONPATH=backend/src .venv/bin/python3 -m iris.eval.multiagentes_ciclo --provider ollama --limite 5
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from iris.agents.adapter_agent import (
    AdapterAgent,
    CicloComAuditor,
    decompor_em_etapas,
    destacar_comandos,
    resumir_ciclo,
)
from iris.agents.auditor import AgenteAuditor, caracteristicas_nao_selecionadas
from iris.agents.curriculum_extractor import CurriculumExtractorAgent
from iris.agents.strategist_agent import StrategistAgent
from iris.core.llm_client import ExtractiveFallbackLLMProvider, HybridLLMClient, LLMResponse, get_llm_client
from iris.eval.benchmark import GoldenQuestion, carregar_golden_benchmark
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS
from iris.eval.trcc import avaliar_trcc
from iris.rag.contexto import conferir_citacoes
from iris.schemas.adaptation import LIMITE_LATENCIA_MS, AdaptationRequest
from iris.schemas.curriculum import ExtractionRequest
from iris.schemas.strategy import StrategyRequest

RELATORIOS_PADRAO = Path("reports")
NOME_BASE = "multiagentes_ciclo"
NIVEIS_PADRAO = (1, 2, 3)


class _ProvedorEcoCiclo:
    """Provedor stub determinístico que devolve JSON estruturado válido para todos os agentes."""

    provider_name = "eco"
    model = "eco-stub-deterministico"

    def __init__(self) -> None:
        self._extrativo = ExtractiveFallbackLLMProvider()

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        t0 = time.perf_counter()
        sistema = system_prompt or ""
        if "Agente Extrator Curricular" in sistema:
            m = re.search(r"ENUNCIADO:\n(.*?)(?:\nTRAVAS DO PROFESSOR|\Z)", prompt, flags=re.DOTALL)
            enunciado = (m.group(1) if m else prompt).strip()
            req_ext = ExtractionRequest(enunciado=enunciado if len(enunciado) >= 15 else enunciado.ljust(15))
            inv = CurriculumExtractorAgent._extracao_deterministica_fallback(None, req_ext)  # type: ignore[arg-type]
            texto = json.dumps(inv.model_dump(), ensure_ascii=False)
        elif "Agente Estrategista Psicopedagógico" in sistema:
            ids_carac = re.findall(r"^-\s*([a-z0-9_]+)\s*\(", prompt, flags=re.MULTILINE) or [ID_COMANDOS_MULTIPLOS]
            intervencoes = [
                {
                    "id_caracteristica": id_c,
                    "texto": "Organize os comandos da atividade em passos curtos e numerados para apoiar a execução sequencial da tarefa pelo estudante [T1].",
                }
                for id_c in ids_carac
            ]
            texto = json.dumps({"intervencoes": intervencoes}, ensure_ascii=False)
        elif "Agente Adaptador Pedagógico" in sistema:
            m = re.search(r"ENUNCIADO ORIGINAL:\n(.*)\Z", prompt, flags=re.DOTALL)
            enunciado = (m.group(1) if m else "").strip()
            achado = re.search(r"NÍVEL (\d)", prompt)
            nivel = int(achado.group(1)) if achado else 2
            adaptado = (
                destacar_comandos(enunciado)
                if nivel == 1
                else decompor_em_etapas(enunciado, com_registro=(nivel == 3))
            )
            texto = json.dumps(
                {"texto_adaptado": adaptado, "justificativas": ["eco: andaime determinístico para validação"]},
                ensure_ascii=False,
            )
        elif "Você é um auditor pedagógico." in prompt:
            texto = json.dumps(
                {"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []},
                ensure_ascii=False,
            )
        else:
            return self._extrativo.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)

        p = len((sistema + prompt).split())
        c = len(texto.split())
        return LLMResponse(
            text=texto,
            provider=self.provider_name,
            model=self.model,
            prompt_tokens=p,
            completion_tokens=c,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            raw_usage={"prompt_tokens": p, "completion_tokens": c},
        )


class _JuizEcoCiclo:
    """Juiz determinístico utilizado nos modos sem rede (eco/extractive)."""

    provider_name = "eco"
    model = "juiz-eco-deterministico"

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900) -> LLMResponse:
        veredito = json.dumps(
            {"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []},
            ensure_ascii=False,
        )
        return LLMResponse(text=veredito, provider=self.provider_name, model=self.model)


class _JuizResilienteCiclo:
    """Falha fechado se o cliente remoto lançar exceção durante o julgamento."""

    def __init__(self, cliente: Any) -> None:
        self.cliente = cliente

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900) -> Any:
        try:
            return self.cliente.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
        except Exception:  # noqa: BLE001
            return ""


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p
    i = int(k)
    j = min(i + 1, len(ordenados) - 1)
    return ordenados[i] + (ordenados[j] - ordenados[i]) * (k - i)


def _resolver_cliente_e_juiz(provider: str, model: Optional[str], cliente: Optional[Any]) -> tuple[Any, Any]:
    if cliente is not None:
        pname = str(getattr(cliente, "provider_name", "custom")).lower()
        juiz = _JuizEcoCiclo() if pname in ("eco", "extractive", "mock", "offline") else _JuizResilienteCiclo(cliente)
        return cliente, juiz

    prov = provider.strip().lower()
    if prov == "eco":
        return _ProvedorEcoCiclo(), _JuizEcoCiclo()
    if prov == "extractive":
        return HybridLLMClient(provider="extractive"), _JuizEcoCiclo()
    c = get_llm_client(provider=prov, model=model)
    return c, _JuizResilienteCiclo(c)


def _contagem_motivos(valores: Iterable[Optional[str]]) -> dict[str, int]:
    c = Counter(v or "nenhum" for v in valores)
    return dict(sorted(c.items()))


def _citacoes_estao_validas(res_est: Any) -> bool:
    fontes = [f.model_dump() for f in res_est.fontes]
    if not res_est.diretiva or not fontes:
        return False
    conf = conferir_citacoes(res_est.diretiva, fontes)
    return (not conf["citacoes_inexistentes"]) and bool(conf["citados"]) and (not conf["frases_sem_citacao"])


def medir(
    questoes: list[GoldenQuestion],
    provider: str = "eco",
    model: Optional[str] = None,
    niveis: tuple[int, ...] = NIVEIS_PADRAO,
    caracteristica: str = ID_COMANDOS_MULTIPLOS,
    comandos_por_regra: bool = False,
    cliente: Optional[Any] = None,
) -> dict[str, Any]:
    """Executa os 4 agentes em cadeia sobre as questões e níveis especificados."""
    if not questoes:
        raise ValueError("Lista de questões vazia para avaliação multiagentes.")

    llm, juiz = _resolver_cliente_e_juiz(provider, model, cliente)
    extrator = CurriculumExtractorAgent(llm_client=llm)
    estrategista = StrategistAgent(llm_client=llm)
    adaptador = AdapterAgent(llm_client=llm, comandos_por_regra=comandos_por_regra)
    auditor = AgenteAuditor(juiz=juiz, limiar=0.95, intrusao_bloqueia=False)
    nao_selecionadas = caracteristicas_nao_selecionadas([caracteristica])

    provider_real = str(getattr(llm, "provider_name", provider))
    modelo_real = str(getattr(getattr(llm, "_primary", llm), "model", model or "desconhecido"))

    registros: list[dict[str, Any]] = []
    for q in questoes:
        trava_gabarito = list(q.trava_curricular)
        trcc_original = avaliar_trcc(trava_gabarito, q.enunciado).trcc

        for nivel in niveis:
            # 1. Agente Extrator
            ext = extrator.extract_golden_with_telemetry(q)

            # 2. Agente Estrategista RAG
            est = estrategista.strategize(
                StrategyRequest(
                    caracteristicas=[caracteristica],
                    nivel=nivel,
                    invariantes=ext.invariants,
                    enunciado=q.enunciado,
                    metodo="bm25",
                    question_id=q.id,
                )
            )
            cit_validas = _citacoes_estao_validas(est)

            # 3. Adaptador <-> 4. Auditor
            pedido_adapt = AdaptationRequest(
                enunciado=q.enunciado,
                id_caracteristica=caracteristica,
                nivel=nivel,
                invariantes=ext.invariants,
                diretiva_psicopedagogica=est.diretiva or None,
                question_id=q.id,
            )
            ciclo_adapt = CicloComAuditor(adaptador, pedido_adapt)
            t_aud_0 = time.perf_counter()
            relatorio = auditor.executar_ciclo(
                original=q.enunciado,
                travas=ext.invariants,
                adaptar=ciclo_adapt,
                nao_selecionadas=nao_selecionadas,
                max_tentativas=3,
            )
            aud_total_ms = round((time.perf_counter() - t_aud_0) * 1000, 2)
            # Tempo gasto só dentro das verificações do Auditor (exclui o tempo das chamadas do Adaptador)
            adapt_ms = round(sum(t.total_ms for t in ciclo_adapt.telemetrias), 2)
            auditor_ms = round(max(0.0, aud_total_ms - adapt_ms), 2)

            ultimo_adapt = ciclo_adapt.resultados[-1]
            ultima_aud = relatorio.tentativas[-1]
            trcc_entregue = avaliar_trcc(trava_gabarito, relatorio.texto_final).trcc

            resumo_c = resumir_ciclo([ext.telemetry, est.telemetry, *ciclo_adapt.telemetrias], nivel)
            ciclo_ms = round(resumo_c["total_ms"] + auditor_ms, 2)
            limite_ms = LIMITE_LATENCIA_MS[nivel]

            registros.append(
                {
                    "id": q.id,
                    "disciplina": q.disciplina,
                    "nivel": nivel,
                    "caracteristica": caracteristica,
                    # Extrator
                    "extrator_ms": ext.telemetry.total_ms,
                    "extrator_fallback": ext.telemetry.used_fallback,
                    "extrator_motivo_fallback": ext.telemetry.motivo_fallback,
                    "extrator_json_direto": ext.telemetry.json_valido_direto,
                    "extrator_trava_recall": ext.telemetry.trava_recall,
                    # Estrategista
                    "estrategista_ms": est.telemetry.total_ms,
                    "estrategista_fallback": est.telemetry.used_fallback,
                    "estrategista_motivo_fallback": est.telemetry.motivo_fallback,
                    "estrategista_json_direto": est.telemetry.json_valido_direto,
                    "estrategista_n_trechos": est.telemetry.n_trechos,
                    "estrategista_citacoes_validas": cit_validas,
                    # Adaptador
                    "adaptador_ms": adapt_ms,
                    "adaptador_fallback": ultimo_adapt.telemetry.used_fallback,
                    "adaptador_motivo_fallback": ultimo_adapt.telemetry.motivo_fallback,
                    "escopo_aprovado": ultimo_adapt.escopo.aprovado,
                    "adaptacao_aplicada": ultimo_adapt.adaptacao_aplicada,
                    # Auditor
                    "auditor_ms": auditor_ms,
                    "auditor_aprovado": relatorio.aprovado,
                    "requer_revisao_humana": relatorio.requer_revisao_humana,
                    "auditor_tentativas": len(relatorio.tentativas),
                    "resolucao_indevida": ultima_aud.resolucao_indevida,
                    "n_intrusoes": len(ultima_aud.intrusoes),
                    "trcc_original": trcc_original,
                    "trcc_entregue": trcc_entregue,
                    "trcc_extrator": ultima_aud.trcc.trcc,
                    # Ciclo
                    "ciclo_ms": ciclo_ms,
                    "limite_ms": limite_ms,
                    "dentro_do_limite": ciclo_ms <= limite_ms,
                    "total_tokens": resumo_c["total_tokens"],
                }
            )

    n = len(registros)
    recalls = [r["extrator_trava_recall"] for r in registros if r["extrator_trava_recall"] is not None]
    trccs_ent = [r["trcc_entregue"] for r in registros if r["trcc_entregue"] is not None]

    por_agente = {
        "extrator": {
            "mediana_ms": round(statistics.median(r["extrator_ms"] for r in registros), 2),
            "recall_medio": round(sum(recalls) / len(recalls), 4) if recalls else None,
            "json_direto_pct": round(100 * sum(r["extrator_json_direto"] for r in registros) / n, 1),
            "fallback_qtd": sum(r["extrator_fallback"] for r in registros),
            "motivos_fallback": _contagem_motivos(r["extrator_motivo_fallback"] for r in registros),
        },
        "estrategista": {
            "mediana_ms": round(statistics.median(r["estrategista_ms"] for r in registros), 2),
            "trechos_medio": round(statistics.mean(r["estrategista_n_trechos"] for r in registros), 2),
            "citacoes_validas_pct": round(100 * sum(r["estrategista_citacoes_validas"] for r in registros) / n, 1),
            "fallback_qtd": sum(r["estrategista_fallback"] for r in registros),
            "motivos_fallback": _contagem_motivos(r["estrategista_motivo_fallback"] for r in registros),
        },
        "adaptador": {
            "mediana_ms": round(statistics.median(r["adaptador_ms"] for r in registros), 2),
            "escopo_aprovado_pct": round(100 * sum(r["escopo_aprovado"] for r in registros) / n, 1),
            "adaptou_pct": round(100 * sum(r["adaptacao_aplicada"] for r in registros) / n, 1),
            "fallback_qtd": sum(r["adaptador_fallback"] for r in registros),
            "motivos_fallback": _contagem_motivos(r["adaptador_motivo_fallback"] for r in registros),
        },
        "auditor": {
            "mediana_ms": round(statistics.median(r["auditor_ms"] for r in registros), 2),
            "aprovado_pct": round(100 * sum(r["auditor_aprovado"] for r in registros) / n, 1),
            "revisao_humana_qtd": sum(r["requer_revisao_humana"] for r in registros),
            "tentativas_media": round(statistics.mean(r["auditor_tentativas"] for r in registros), 2),
            "tentativas_max": max(r["auditor_tentativas"] for r in registros),
            "autocorrecoes_qtd": sum(1 for r in registros if r["auditor_tentativas"] > 1),
            "resolucao_indevida_qtd": sum(r["resolucao_indevida"] for r in registros),
            "trcc_medio_gabarito": round(sum(trccs_ent) / len(trccs_ent), 4) if trccs_ent else None,
            "trcc_ok_pct": round(100 * sum((r["trcc_entregue"] or 0.0) >= 0.95 for r in registros) / n, 1),
        },
    }

    por_nivel: dict[int, dict[str, Any]] = {}
    for nivel in niveis:
        rs = [r for r in registros if r["nivel"] == nivel]
        ciclos = [r["ciclo_ms"] for r in rs]
        por_nivel[nivel] = {
            "ciclos": len(rs),
            "limite_ms": LIMITE_LATENCIA_MS[nivel],
            "dentro_do_limite": sum(r["dentro_do_limite"] for r in rs),
            "ciclo_mediana_ms": round(statistics.median(ciclos), 2),
            "ciclo_p90_ms": round(_percentil(ciclos, 0.9), 2),
            "ciclo_max_ms": round(max(ciclos), 2),
            "tokens_mediana": round(statistics.median(r["total_tokens"] for r in rs), 1),
            "aprovados_auditor": sum(r["auditor_aprovado"] for r in rs),
            "escopo_aprovado": sum(r["escopo_aprovado"] for r in rs),
        }

    resumo = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "questoes": len(questoes),
        "ciclos": n,
        "provedor": provider_real,
        "modelo": modelo_real,
        "caracteristica": caracteristica,
        "comandos_por_regra": comandos_por_regra,
        "por_agente": por_agente,
        "por_nivel": por_nivel,
    }
    return {"resumo": resumo, "registros": registros}


def _markdown(resumo: dict[str, Any]) -> str:
    ag = resumo["por_agente"]
    linhas = [
        "# Relatório de Observabilidade E2E — Sistema Multiagentes (4 Agentes)",
        "",
        f"- **Gerado em (UTC):** {resumo['gerado_em_utc']}",
        f"- **Provedor / Modelo:** `{resumo['provedor']}` / `{resumo['modelo']}`",
        f"- **Característica:** `{resumo['caracteristica']}` | **comandos_por_regra:** `{resumo['comandos_por_regra']}`",
        f"- **Amostra:** {resumo['questoes']} questão(ões) × {len(resumo['por_nivel'])} nível(is) = {resumo['ciclos']} ciclo(s)",
        "",
        "## 1. Saúde e Guardrails por Agente",
        "",
        "| Agente | Mediana (ms) | Fallbacks | Indicadores-chave | Motivos de Fallback |",
        "|---|---:|---:|---|---|",
        (
            f"| 1. Extrator (#17) | {ag['extrator']['mediana_ms']} | {ag['extrator']['fallback_qtd']} | "
            f"Recall trava: {ag['extrator']['recall_medio']} · JSON direto: {ag['extrator']['json_direto_pct']}% | "
            f"`{ag['extrator']['motivos_fallback']}` |"
        ),
        (
            f"| 2. Estrategista (#16) | {ag['estrategista']['mediana_ms']} | {ag['estrategista']['fallback_qtd']} | "
            f"Trechos médios: {ag['estrategista']['trechos_medio']} · Citações válidas: {ag['estrategista']['citacoes_validas_pct']}% | "
            f"`{ag['estrategista']['motivos_fallback']}` |"
        ),
        (
            f"| 3. Adaptador (#18) | {ag['adaptador']['mediana_ms']} | {ag['adaptador']['fallback_qtd']} | "
            f"Escopo OK: {ag['adaptador']['escopo_aprovado_pct']}% · Adaptou: {ag['adaptador']['adaptou_pct']}% | "
            f"`{ag['adaptador']['motivos_fallback']}` |"
        ),
        (
            f"| 4. Auditor (#19) | {ag['auditor']['mediana_ms']} | - | "
            f"Aprovado: {ag['auditor']['aprovado_pct']}% · TRCC>=0,95: {ag['auditor']['trcc_ok_pct']}% · "
            f"Auto-correções: {ag['auditor']['autocorrecoes_qtd']} · Resoluções indevidas: {ag['auditor']['resolucao_indevida_qtd']} | "
            f"Revisão humana: {ag['auditor']['revisao_humana_qtd']} |"
        ),
        "",
        "## 2. Orçamento RNF-07 / RNF-08 por Nível",
        "",
        "| Nível | Ciclos | Limite (ms) | Dentro do Limite | Mediana (ms) | P90 (ms) | Máximo (ms) | Tokens (mediana) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for nivel, c in sorted(resumo["por_nivel"].items(), key=lambda x: int(x[0])):
        linhas.append(
            f"| {nivel} | {c['ciclos']} | {c['limite_ms']} | {c['dentro_do_limite']}/{c['ciclos']} | "
            f"{c['ciclo_mediana_ms']} | {c['ciclo_p90_ms']} | {c['ciclo_max_ms']} | {c['tokens_mediana']} |"
        )
    return "\n".join(linhas) + "\n"


def gerar_relatorio(
    pasta: str | Path = RELATORIOS_PADRAO,
    caminho_benchmark: Optional[str | Path] = None,
    limite_questoes: Optional[int] = None,
    provider: str = "eco",
    model: Optional[str] = None,
    niveis: tuple[int, ...] = NIVEIS_PADRAO,
    caracteristica: str = ID_COMANDOS_MULTIPLOS,
    comandos_por_regra: bool = False,
) -> dict[str, Any]:
    """Executa a medição completa e grava ``multiagentes_ciclo.{json,md}`` em ``pasta``."""
    out_dir = Path(pasta)
    out_dir.mkdir(parents=True, exist_ok=True)
    questoes = carregar_golden_benchmark(caminho_benchmark)
    if limite_questoes is not None:
        questoes = questoes[:limite_questoes]

    medicao = medir(
        questoes,
        provider=provider,
        model=model,
        niveis=niveis,
        caracteristica=caracteristica,
        comandos_por_regra=comandos_por_regra,
    )
    (out_dir / f"{NOME_BASE}.json").write_text(
        json.dumps(medicao, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / f"{NOME_BASE}.md").write_text(_markdown(medicao["resumo"]), encoding="utf-8")
    return medicao


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Avalia o ciclo completo dos 4 agentes no Golden Benchmark.")
    parser.add_argument("--provider", default="eco", choices=["eco", "extractive", "ollama", "anthropic", "groq"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--limite", type=int, default=None, help="Limita à quantidade N inicial de questões.")
    parser.add_argument("--niveis", default="1,2,3", help="Níveis separados por vírgula (ex.: 1,2,3).")
    parser.add_argument("--caracteristica", default=ID_COMANDOS_MULTIPLOS)
    parser.add_argument("--comandos-por-regra", action="store_true", help="Ativa atalho por regra no Adaptador.")
    parser.add_argument("--pasta", default=str(RELATORIOS_PADRAO))
    args = parser.parse_args(argv)

    niveis = tuple(int(x.strip()) for x in args.niveis.split(",") if x.strip())
    medicao = gerar_relatorio(
        pasta=args.pasta,
        limite_questoes=args.limite,
        provider=args.provider,
        model=args.model,
        niveis=niveis,
        caracteristica=args.caracteristica,
        comandos_por_regra=args.comandos_por_regra,
    )
    print(_markdown(medicao["resumo"]))
    print(f"Relatórios gravados em: {Path(args.pasta) / NOME_BASE}.{{json,md}}")


if __name__ == "__main__":
    main()
