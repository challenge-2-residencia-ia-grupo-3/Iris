#!/usr/bin/env python3
"""Demonstração e Menu Interativo do Sistema Multiagentes (Semana 4 — Issues #15, #16, #17, #18 e #19).

Executa o fluxo completo mostrando os 4 agentes colaborando passo a passo:
  1. Agente Extrator Curricular (#17)
  2. Agente Estrategista RAG (#16)
  3. Agente Adaptador Pedagógico (#18)
  4. Agente Auditor de Integridade e Auto-Correção (#19)

Uso:
    make multiagentes
    PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 scripts/demo_multiagentes.py --demo
    PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 scripts/demo_multiagentes.py --demo --provider extractive
    PYTHONPATH=backend/src:rag/iris-rag/pacote .venv/bin/python3 scripts/demo_multiagentes.py --question Q18 --nivel 2 --simular-autocorrecao
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "rag" / "iris-rag" / "pacote"))

from iris.agents.orchestrator import (
    MultiAgentMaterialRequest,
    MultiAgentMaterialResponse,
    run_multiagent_adaptation,
)
from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS
from iris.schemas.catalog import load_official_tdah_catalog


def _separador(titulo: str, char: str = "=") -> None:
    print(f"\n{char * 78}")
    print(f"  {titulo}")
    print(f"{char * 78}")


def imprimir_fluxo(res: MultiAgentMaterialResponse, rotulo: str) -> None:
    """Imprime de forma legível a colaboração entre os 4 agentes em cada questão."""
    _separador(rotulo)
    print(f"Provedor/Modelo : {res.provider} / {res.model}")
    print(f"Nível de Andaime: {res.nivel} | Características: {res.selected_ids}")
    print(f"PII Sanitizados : {res.pii_substituicoes} | Latência Total: {res.total_ms:.1f} ms | Tokens: {res.total_tokens}")

    for idx, qt in enumerate(res.questoes_trace, start=1):
        print(f"\n--- Questão {idx} (Ref. {qt.numero_original}) ---")
        print(f"Original:\n  {qt.original.replace(chr(10), chr(10) + '  ')}")

        # 1. Agente Extrator Curricular
        inv = qt.extrator.invariants
        print("\n[1] Agente Extrator Curricular (#17 — Analysis Agent)")
        print(f"    Verbo BNCC       : {inv.verbo_comando_bncc}")
        print(f"    Operação         : {inv.operacao_cognitiva}")
        print(f"    Conceitos Trava  : {inv.conceitos_obrigatorios}")
        print(f"    Termos Intocáveis: {inv.termos_tecnicos_intocaveis}")
        if inv.alerta_anti_muleta:
            print(f"    Alerta AntiMuleta: {inv.alerta_anti_muleta}")
        print(f"    Telemetria       : {qt.extrator.telemetry.total_ms:.1f} ms (fallback={qt.extrator.telemetry.used_fallback})")

        # 2. Agente Estrategista RAG
        est = qt.estrategista
        print("\n[2] Agente Estrategista RAG (#16 — Research Agent)")
        print(f"    Busca RAG        : método={est.telemetry.metodo_efetivo} | fontes={len(est.fontes)} | fora_filtro={len(est.trechos_fora_do_filtro)}")
        if est.diretiva:
            for linha in est.diretiva.splitlines():
                print(f"    Diretiva         : {linha}")
        for fonte in est.fontes[:3]:
            print(f"    Fonte [{fonte.rotulo}]     : {fonte.referencia}")

        # 3 & 4. Loop Agente Adaptador <-> Agente Auditor
        print("\n[3 & 4] Loop Agente Adaptador (#18) <-> Agente Auditor (#19)")
        for t in qt.tentativas:
            trcc_txt = f"{t.trcc * 100:.0f}%" if t.trcc is not None else "N/A"
            status_txt = "APROVADA" if t.aprovado_auditor else "REPROVADA"
            print(
                f"  -> Tentativa {t.tentativa}: {status_txt} | TRCC={trcc_txt} | "
                f"Escopo={'OK' if t.escopo_aprovado else 'VIOLADO'} | "
                f"ResoluçãoIndevida={t.resolucao_indevida}"
            )
            if not t.aprovado_auditor:
                print(f"     Minuta reprovada : {t.texto_minuta.replace(chr(10), ' / ')}")
                if t.motivos_auditor:
                    print(f"     Motivo Auditor   : {'; '.join(t.motivos_auditor)}")
                if t.feedback_gerado:
                    print(f"     Feedback -> Adapt: {t.feedback_gerado}")

        print("\n[Saída Final Entregue]")
        for linha in qt.adaptado.splitlines():
            print(f"  {linha}")
        if qt.justificativas:
            print(f"Justificativas DUA : {qt.justificativas}")
        resumo = qt.ciclo_resumo
        print(
            f"Status Auditoria   : aprovado={qt.aprovado_final} | requer_revisao_humana={qt.requer_revisao_humana} | "
            f"ciclo={resumo.get('total_ms', 0):.1f} ms (limite RNF-07={resumo.get('limite_ms', 0):.0f} ms)"
        )


def executar_demo(provider: str = "auto", model: Optional[str] = None) -> int:
    """Executa os dois cenários oficiais de demonstração da Semana 4."""
    questoes = carregar_golden_benchmark()
    q13 = next((q for q in questoes if q.id == "Q13"), questoes[0])
    q18 = next((q for q in questoes if q.id == "Q18"), questoes[-1])

    res1 = run_multiagent_adaptation(
        MultiAgentMaterialRequest(
            text=q13.enunciado,
            titulo=f"Demonstração 1 — {q13.id} ({q13.disciplina})",
            selected_ids=[ID_COMANDOS_MULTIPLOS],
            nivel=2,
            disciplina=q13.disciplina,
            ano_escolar=q13.ano,
            trava_manual_docente=None,
            provider=provider,
            model=model,
            simular_autocorrecao=False,
        )
    )
    imprimir_fluxo(res1, f"CENÁRIO 1: FLUXO COMPLETO DOS 4 AGENTES ({q13.id} — Aprovação Direta)")

    res2 = run_multiagent_adaptation(
        MultiAgentMaterialRequest(
            text=q18.enunciado,
            titulo=f"Demonstração 2 — {q18.id} ({q18.disciplina})",
            selected_ids=[ID_COMANDOS_MULTIPLOS],
            nivel=3,
            disciplina=q18.disciplina,
            ano_escolar=q18.ano,
            trava_manual_docente=["plantas", "fotossíntese", "luz"],
            provider=provider,
            model=model,
            simular_autocorrecao=True,
        )
    )
    imprimir_fluxo(res2, f"CENÁRIO 2: COLABORAÇÃO & AUTO-CORREÇÃO AUDITOR <-> ADAPTADOR ({q18.id})")
    return 0


def menu_interativo(provider_inicial: str, model: Optional[str]) -> int:
    provider = provider_inicial
    catalogo = load_official_tdah_catalog()
    carac_ids = [c.id_caracteristica for c in catalogo.caracteristicas]

    while True:
        _separador(f"CENTRAL DO SISTEMA MULTIAGENTES ÍRIS (Provedor: {provider})")
        print("  [1] Executar Demonstração Oficial da Semana 4 (Fluxo Completo + Auto-Correção)")
        print("  [2] Testar questão do Golden Benchmark (Q01..Q30)")
        print("  [3] Testar texto/questão livre")
        print("  [4] Alternar provedor LLM (auto / anthropic / ollama / groq / extractive)")
        print("  [0] Sair")
        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == "0":
            return 0
        if escolha == "1":
            executar_demo(provider=provider, model=model)
        elif escolha == "2":
            questoes = carregar_golden_benchmark()
            for q in questoes[:10]:
                print(f"  {q.id} | {q.disciplina:<10} | {q.enunciado.splitlines()[0][:55]}...")
            qid = input("Informe o ID da questão (ex.: Q01, Q13, Q18): ").strip().upper()
            alvo = next((q for q in questoes if q.id.upper() == qid), None)
            if not alvo:
                print(f"Questão '{qid}' não encontrada.")
                continue
            nivel_raw = input("Nível de andaime (1, 2 ou 3) [2]: ").strip() or "2"
            sim_raw = input("Simular auto-correção Auditor <-> Adaptador? (s/N): ").strip().lower()
            res = run_multiagent_adaptation(
                MultiAgentMaterialRequest(
                    text=alvo.enunciado,
                    titulo=f"Golden Benchmark {alvo.id}",
                    selected_ids=[ID_COMANDOS_MULTIPLOS],
                    nivel=int(nivel_raw) if nivel_raw in {"1", "2", "3"} else 2,
                    disciplina=alvo.disciplina,
                    ano_escolar=alvo.ano,
                    provider=provider,
                    model=model,
                    simular_autocorrecao=sim_raw.startswith("s"),
                )
            )
            imprimir_fluxo(res, f"GOLDEN BENCHMARK {alvo.id}")
        elif escolha == "3":
            texto = input("Cole o enunciado ou atividade (mín. 15 caracteres): ").strip()
            if len(texto) < 15:
                print("Texto muito curto (mínimo 15 caracteres).")
                continue
            print("Características disponíveis:")
            for i, cid in enumerate(carac_ids, start=1):
                print(f"  {i:2d}. {cid}")
            idx_raw = input("Número da característica [1]: ").strip() or "1"
            try:
                cid = carac_ids[int(idx_raw) - 1]
            except Exception:
                cid = ID_COMANDOS_MULTIPLOS
            nivel_raw = input("Nível (1, 2 ou 3) [2]: ").strip() or "2"
            trava_raw = input("Trava manual opcional (separada por vírgula, Enter para pular): ").strip()
            sim_raw = input("Simular auto-correção? (s/N): ").strip().lower()
            res = run_multiagent_adaptation(
                MultiAgentMaterialRequest(
                    text=texto,
                    selected_ids=[cid],
                    nivel=int(nivel_raw) if nivel_raw in {"1", "2", "3"} else 2,
                    trava_manual_docente=trava_raw or None,
                    provider=provider,
                    model=model,
                    simular_autocorrecao=sim_raw.startswith("s"),
                )
            )
            imprimir_fluxo(res, "EXECUÇÃO PERSONALIZADA")
        elif escolha == "4":
            novo = input("Novo provedor (auto / anthropic / claude / ollama / groq / extractive): ").strip().lower()
            if novo in {"auto", "anthropic", "claude", "sonnet", "extractive", "ollama", "groq"}:
                provider = novo
            else:
                print("Provedor inválido.")
        else:
            print("Opção inválida.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true", help="Roda os 2 cenários demonstrativos e sai")
    parser.add_argument("--menu", action="store_true", help="Abre o menu interativo no terminal")
    parser.add_argument("--question", type=str, default=None, help="ID do Golden Benchmark (ex.: Q13)")
    parser.add_argument("--text", type=str, default=None, help="Texto/enunciado livre para testar")
    parser.add_argument("--nivel", type=int, default=2, choices=[1, 2, 3])
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=["auto", "anthropic", "claude", "sonnet", "extractive", "ollama", "groq"],
    )
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--simular-autocorrecao", action="store_true")
    args = parser.parse_args()

    if args.menu:
        return menu_interativo(args.provider, args.model)

    if args.question:
        questoes = carregar_golden_benchmark()
        alvo = next((q for q in questoes if q.id.upper() == args.question.strip().upper()), None)
        if not alvo:
            print(f"Questão '{args.question}' não encontrada.", file=sys.stderr)
            return 1
        res = run_multiagent_adaptation(
            MultiAgentMaterialRequest(
                text=alvo.enunciado,
                titulo=f"{alvo.id} — {alvo.disciplina}",
                selected_ids=[ID_COMANDOS_MULTIPLOS],
                nivel=args.nivel,
                disciplina=alvo.disciplina,
                ano_escolar=alvo.ano,
                provider=args.provider,
                model=args.model,
                simular_autocorrecao=args.simular_autocorrecao,
            )
        )
        imprimir_fluxo(res, f"FLUXO MULTIAGENTES — {alvo.id}")
        return 0

    if args.text:
        res = run_multiagent_adaptation(
            MultiAgentMaterialRequest(
                text=args.text,
                selected_ids=[ID_COMANDOS_MULTIPLOS],
                nivel=args.nivel,
                provider=args.provider,
                model=args.model,
                simular_autocorrecao=args.simular_autocorrecao,
            )
        )
        imprimir_fluxo(res, "FLUXO MULTIAGENTES — TEXTO LIVRE")
        return 0

    return executar_demo(provider=args.provider, model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
