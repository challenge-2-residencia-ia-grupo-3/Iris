#!/usr/bin/env python3
"""CLI e Menu Interativo do Agente Extrator Curricular (História 2.1.2 / Issue #17).

Permite rodar casos demonstrativos, testar questões do Golden Benchmark, enviar
questões livres, executar o benchmark completo (Zero-Hint) e consultar Analytics
Dinâmico por disciplina, faixa etária e tipo de comando.

Uso:
    make extrator
    .venv/bin/python3 scripts/test_curriculum_extractor_cli.py --menu
    .venv/bin/python3 scripts/test_curriculum_extractor_cli.py --golden Q01
    .venv/bin/python3 scripts/test_curriculum_extractor_cli.py --benchmark
    .venv/bin/python3 scripts/test_curriculum_extractor_cli.py --analytics --disciplina Matemática
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "rag" / "iris-rag" / "pacote"))

from iris.agents.curriculum_extractor import get_curriculum_extractor
from iris.core.llm_client import get_llm_client
from iris.eval.benchmark import carregar_golden_benchmark
from iris.eval.extractor_analytics import (
    carregar_telemetria,
    executar_benchmark_extrator,
    formatar_relatorio_terminal,
    gerar_analytics,
    registrar_telemetria,
)


def formatar_resultado(res, registrar: bool = True) -> None:
    inv = res.invariants
    tel = res.telemetry
    if registrar:
        registrar_telemetria(tel)

    print("\n" + "=" * 72)
    print(" INVARIANTES CURRICULARES EXTRAÍDOS (ISSUE #17)")
    print("=" * 72)
    print(f" Verbo de Comando BNCC : \033[1;32m{inv.verbo_comando_bncc}\033[0m")
    print(f" Conceitos Obrigatórios: {inv.conceitos_obrigatorios}")
    print(f" Termos Intocáveis     : {inv.termos_tecnicos_intocaveis}")
    print(f" Operação Cognitiva    : {inv.operacao_cognitiva}")
    if inv.habilidade_bncc_sugerida:
        print(f" Habilidade BNCC       : \033[1;34m{inv.habilidade_bncc_sugerida}\033[0m")
    print(f" Alerta Anti-Muleta    : \033[1;31m{inv.alerta_anti_muleta}\033[0m")
    print(f" Justificativa         : {inv.justificativa_preservacao}")
    print("-" * 72)
    rec = f" | Recall Trava: {tel.trava_recall * 100:.0f}%" if tel.trava_recall is not None else ""
    fb = " | [FALLBACK OFFLINE]" if tel.used_fallback else ""
    print(
        f" Telemetria: total={tel.total_ms:.0f}ms | inferência={tel.inference_ms:.0f}ms "
        f"(cold_load={tel.load_ms:.0f}ms) | {tel.tokens_per_sec:.1f} tok/s "
        f"| tokens={tel.prompt_tokens}+{tel.completion_tokens}{rec}{fb}"
    )
    print("=" * 72)


def rodar_casos_padrao(extractor) -> None:
    amostras = [
        {
            "disciplina": "Ciências",
            "ano": "6º ano",
            "enunciado": (
                "Explique como os cloroplastos realizam a fotossíntese utilizando luz solar, "
                "água e gás carbônico para produzir glicose e liberar oxigênio."
            ),
        },
        {
            "disciplina": "Matemática",
            "ano": "7º ano",
            "enunciado": "Resolva a equação de primeiro grau 3x + 12 = 30 e determine o valor da incógnita x.",
        },
    ]
    print("\nExecutando bateria demonstrativa padrão (2 questões):")
    for i, item in enumerate(amostras, 1):
        print(f"\n--- [Caso {i}] {item['disciplina']} ({item['ano']}) ---")
        print(f"Enunciado: {item['enunciado']}")
        res = extractor.extract_with_telemetry(
            request=item["enunciado"],
            disciplina=item["disciplina"],
            ano_escolar=item["ano"],
            question_id=f"DEMO-{i:02d}",
        )
        formatar_resultado(res)


def rodar_questao_golden(extractor, qid: str) -> None:
    questoes = carregar_golden_benchmark()
    alvo = next((q for q in questoes if q.id.upper() == qid.strip().upper()), None)
    if not alvo:
        print(f"\nErro: Questão '{qid}' não encontrada no Golden Benchmark (disponíveis: Q01..Q{len(questoes):02d}).")
        return
    print(f"\n[Golden Benchmark {alvo.id}] {alvo.disciplina} ({alvo.ano}) | Tema: {alvo.tema} | Conjugado: {alvo.comando_conjugado_esperado}")
    print(f"Enunciado Original:\n{alvo.enunciado}")
    if alvo.trava_curricular:
        print(f"Trava de Referência no Benchmark: {alvo.trava_curricular}")
    res = extractor.extract_golden_with_telemetry(alvo, include_trava_hint=False)
    formatar_resultado(res)


def listar_resumo_golden() -> None:
    questoes = carregar_golden_benchmark()
    print("\nQuestões disponíveis no Golden Benchmark (30 questões):")
    for q in questoes:
        conj = "Conjugado" if q.comando_conjugado_esperado else "Simples  "
        resumo = q.enunciado.replace("\n", " ")[:60]
        print(f"  {q.id} | {q.disciplina:<10} | {q.ano:<3} | {conj} | {resumo}...")


def menu_interativo(provider: str, model: str) -> None:
    estado = {"provider": provider, "model": model}

    def construir_agente():
        llm = get_llm_client(
            provider=estado["provider"],
            model=estado["model"],
            allow_fallback_to_extractive=True,
        )
        return llm, get_curriculum_extractor(llm_client=llm)

    llm, extractor = construir_agente()

    while True:
        st = llm.status()
        online = "ONLINE" if st.get("primary_available") else "OFFLINE (usará fallback)"
        print("\n" + "=" * 78)
        print("  ÍRIS — CENTRAL DO AGENTE EXTRATOR CURRICULAR (ISSUE #17)")
        print(f"  Provedor ativo: {estado['provider']}:{estado['model']} [{online}]")
        print("=" * 78)
        print("  1) Rodar casos demonstrativos padrão (Ciências e Matemática)")
        print("  2) Testar uma questão do Golden Benchmark (ex.: Q01, Q06, Q15)")
        print("  3) Testar uma questão personalizada livre (digite o enunciado)")
        print("  4) Rodar Benchmark em lote no Golden Benchmark (Zero-Hint + Telemetria)")
        print("  5) Ver Analytics Dinâmico (filtrar por disciplina, faixa etária e comando)")
        print("  6) Executar testes unitários do Agente Extrator e Analytics")
        print("  7) Trocar provedor / modelo da sessão (ollama / groq / extractive)")
        print("  0) Sair")
        print("=" * 78)

        try:
            opcao = input("Escolha uma opção [0-7]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando menu.")
            break

        if opcao == "0":
            break
        elif opcao == "1":
            rodar_casos_padrao(extractor)
        elif opcao == "2":
            ver = input("Deseja listar as 30 questões antes? [s/N]: ").strip().lower()
            if ver == "s":
                listar_resumo_golden()
            qid = input("Digite o ID da questão (ex.: Q01, Q06, Q15): ").strip()
            if qid:
                rodar_questao_golden(extractor, qid)
        elif opcao == "3":
            enunciado = input("\nDigite o enunciado da questão: ").strip()
            if len(enunciado) < 15:
                print("Enunciado muito curto (mínimo 15 caracteres).")
                continue
            disc = input("Disciplina (Enter para omitir): ").strip() or None
            ano = input("Ano escolar (ex.: 6º ano, 1º EM — Enter para omitir): ").strip() or None
            res = extractor.extract_with_telemetry(
                request=enunciado,
                disciplina=disc,
                ano_escolar=ano,
                question_id="MANUAL-LIVRE",
            )
            formatar_resultado(res)
        elif opcao == "4":
            lim_str = input("Quantas questões rodar? (Enter para todas as 30): ").strip()
            limite = int(lim_str) if lim_str.isdigit() and int(lim_str) > 0 else None
            ref_str = input("Limpar histórico de telemetria anterior? [s/N]: ").strip().lower()
            questoes = carregar_golden_benchmark()
            analytics = executar_benchmark_extrator(
                extractor,
                questoes,
                refazer=(ref_str == "s"),
                limite=limite,
                warmup=True,
            )
            print(formatar_relatorio_terminal(analytics))
        elif opcao == "5":
            registros = carregar_telemetria()
            if not registros:
                print("\nNenhum dado gravado ainda em reports/extractor_telemetry.jsonl. Rode a opção 1, 2 ou 4 primeiro.")
                continue
            disc = input("Filtrar por disciplina (ex.: Matemática — Enter para todas): ").strip() or None
            faixa = input("Filtrar por faixa etária/etapa (ex.: Fund. I, 11-12, 13-14, Médio — Enter para todas): ").strip() or None
            cmd_in = input("Filtrar por comando conjugado? [s/n/Enter para todos]: ").strip().lower()
            cmd_bool: Optional[bool] = True if cmd_in == "s" else (False if cmd_in == "n" else None)
            analytics = gerar_analytics(
                registros,
                disciplina=disc,
                faixa_etaria=faixa,
                comando_conjugado=cmd_bool,
            )
            print(formatar_relatorio_terminal(analytics))
        elif opcao == "6":
            env = dict(os.environ)
            env["PYTHONPATH"] = f"{REPO_ROOT / 'backend' / 'src'}:{REPO_ROOT / 'rag' / 'iris-rag' / 'pacote'}"
            env_cmd = [sys.executable, "-m", "unittest", "backend/tests/test_curriculum_extractor.py", "-v"]
            subprocess.run(env_cmd, cwd=str(REPO_ROOT), env=env, check=False)
        elif opcao == "7":
            novo_prov = input(f"Provedor [ollama / groq / extractive] (atual: {estado['provider']}): ").strip()
            novo_mod = input(f"Modelo (atual: {estado['model']} — Enter mantém): ").strip()
            if novo_prov:
                estado["provider"] = novo_prov
            if novo_mod:
                estado["model"] = novo_mod
            llm, extractor = construir_agente()
            print(f"Atualizado para {estado['provider']}:{estado['model']}.")
        else:
            print("Opção inválida.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste manual e Analytics do Agente Extrator (Issue #17)")
    parser.add_argument("--menu", action="store_true", help="Abre o menu interativo completo")
    parser.add_argument("--questao", type=str, default=None, help="Texto da questão a ser avaliada")
    parser.add_argument("--disciplina", type=str, default=None, help="Disciplina da questão ou filtro de analytics")
    parser.add_argument("--ano", type=str, default=None, help="Ano escolar")
    parser.add_argument("--golden", type=str, default=None, help="ID da questão do Golden Benchmark (ex: Q01, Q06)")
    parser.add_argument("--benchmark", action="store_true", help="Roda benchmark no Golden Benchmark")
    parser.add_argument("--analytics", action="store_true", help="Exibe painel analítico dos logs gravados")
    parser.add_argument("--limite", type=int, default=None, help="Limita número de questões no benchmark")
    parser.add_argument("--refazer", action="store_true", help="Reinicia o arquivo de telemetria no benchmark")
    parser.add_argument("--no-warmup", action="store_true", help="Pula pré-aquecimento do modelo no benchmark")
    parser.add_argument("--faixa-etaria", type=str, default=None, help="Filtro de faixa etária no analytics")
    parser.add_argument("--comando-conjugado", choices=["sim", "nao"], default=None, help="Filtro de comando conjugado")
    parser.add_argument("--provider", type=str, default="ollama", help="Provedor LLM: 'ollama', 'groq' ou 'extractive'")
    parser.add_argument("--model", type=str, default="llama3:latest", help="Nome do modelo no Ollama/Groq")
    args = parser.parse_args()

    if args.menu:
        menu_interativo(provider=args.provider, model=args.model)
        return

    if args.analytics:
        cmd_bool: Optional[bool] = None
        if args.comando_conjugado == "sim":
            cmd_bool = True
        elif args.comando_conjugado == "nao":
            cmd_bool = False
        registros = carregar_telemetria()
        analytics = gerar_analytics(
            registros,
            disciplina=args.disciplina,
            faixa_etaria=args.faixa_etaria,
            comando_conjugado=cmd_bool,
        )
        print(formatar_relatorio_terminal(analytics))
        return

    llm = get_llm_client(provider=args.provider, model=args.model, allow_fallback_to_extractive=True)
    extractor = get_curriculum_extractor(llm_client=llm)

    if args.benchmark:
        questoes = carregar_golden_benchmark()
        analytics = executar_benchmark_extrator(
            extractor,
            questoes,
            refazer=args.refazer,
            limite=args.limite,
            warmup=not args.no_warmup,
        )
        print(formatar_relatorio_terminal(analytics))
        return

    status = llm.status()
    print(f"\nProvedor: {status.get('configured_provider')} | Ollama Online: {status.get('ollama_online')} | Modelo: {args.model}")

    if args.golden:
        rodar_questao_golden(extractor, args.golden)
        return

    if args.questao:
        print(f"\nEnunciado Informado:\n{args.questao}")
        res = extractor.extract_with_telemetry(
            request=args.questao,
            disciplina=args.disciplina,
            ano_escolar=args.ano,
            question_id="CLI-LIVRE",
        )
        formatar_resultado(res)
        return

    rodar_casos_padrao(extractor)


if __name__ == "__main__":
    main()
