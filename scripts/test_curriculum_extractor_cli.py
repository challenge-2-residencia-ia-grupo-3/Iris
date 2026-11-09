#!/usr/bin/env python3
"""Script de Teste Manual do Agente Extrator Curricular (História 2.1.2 / Issue #17).

Permite testar manualmente a extração de invariantes curriculares utilizando o modelo local
Llama 3 no Ollama (ou fallback determinístico), medindo tempo de resposta e qualidade da trava.

Uso:
    python scripts/test_curriculum_extractor_cli.py
    python scripts/test_curriculum_extractor_cli.py --questao "Resolva 2x+6=14" --disciplina "Matemática"
    python scripts/test_curriculum_extractor_cli.py --golden Q01
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Garante importação a partir de backend/src e rag/iris-rag/pacote
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "rag" / "iris-rag" / "pacote"))

from iris.agents.curriculum_extractor import get_curriculum_extractor
from iris.core.llm_client import get_llm_client
from iris.eval.benchmark import carregar_golden_benchmark


def formatar_invariantes(invariantes, latencia_ms: float = 0.0) -> None:
    print("\n" + "=" * 65)
    print(" INVARIANTES CURRICULARES EXTRAÍDOS (ISSUE #17)")
    print("=" * 65)
    print(f" Verbo de Comando BNCC : \033[1;32m{invariantes.verbo_comando_bncc}\033[0m")
    print(f" Conceitos Obrigatórios : {invariantes.conceitos_obrigatorios}")
    print(f" Termos Intocáveis      : {invariantes.termos_tecnicos_intocaveis}")
    print(f" Operação Cognitiva     : {invariantes.operacao_cognitiva}")
    if invariantes.habilidade_bncc_sugerida:
        print(f" Habilidade BNCC        : \033[1;34m{invariantes.habilidade_bncc_sugerida}\033[0m")
    print(f" Alerta Anti-Muleta     : \033[1;31m{invariantes.alerta_anti_muleta}\033[0m")
    print(f" Justificativa          : {invariantes.justificativa_preservacao}")
    if latencia_ms > 0:
        print(f" Tempo de Processamento : {latencia_ms:.1f} ms")
    print("=" * 65)


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste manual do Agente Extrator Curricular (Issue #17)")
    parser.add_argument("--questao", type=str, default=None, help="Texto da questão a ser avaliada")
    parser.add_argument("--disciplina", type=str, default=None, help="Disciplina da questão")
    parser.add_argument("--ano", type=str, default=None, help="Ano escolar")
    parser.add_argument("--golden", type=str, default=None, help="ID da questão do Golden Benchmark (ex: Q01, Q06)")
    parser.add_argument("--provider", type=str, default="ollama", help="Provedor LLM: 'ollama' ou 'extractive'")
    parser.add_argument("--model", type=str, default="llama3:latest", help="Nome do modelo no Ollama")
    args = parser.parse_args()

    print("\nInicializando Agente Extrator Curricular...")
    llm = get_llm_client(provider=args.provider, model=args.model, allow_fallback_to_extractive=True)
    extractor = get_curriculum_extractor(llm_client=llm)

    status = llm.status()
    print(f"Provedor: {status.get('configured_provider')} | Ollama Online: {status.get('ollama_online')} | Modelo: {args.model}")

    if args.golden:
        questoes = carregar_golden_benchmark()
        alvo = next((q for q in questoes if q.id.upper() == args.golden.upper()), None)
        if not alvo:
            print(f"Erro: Questão '{args.golden}' não encontrada no Golden Benchmark.")
            sys.exit(1)
        print(f"\n[Golden Benchmark {alvo.id}] Disciplina: {alvo.disciplina} ({alvo.ano})")
        print(f"Enunciado Original:\n{alvo.enunciado}")
        if alvo.trava_curricular:
            print(f"Trava de Referência no Benchmark: {alvo.trava_curricular}")

        t0 = time.perf_counter()
        inv = extractor.extract_from_golden_question(alvo)
        dt = (time.perf_counter() - t0) * 1000
        formatar_invariantes(inv, dt)
        return

    if args.questao:
        enunciado = args.questao
        print(f"\nEnunciado Informado:\n{enunciado}")
        t0 = time.perf_counter()
        inv = extractor.extract(
            request=enunciado,
            disciplina=args.disciplina,
            ano_escolar=args.ano,
        )
        dt = (time.perf_counter() - t0) * 1000
        formatar_invariantes(inv, dt)
        return

    # Demonstração padrão com 2 questões representativas (Ciências e Matemática)
    amostras = [
        {
            "disciplina": "Ciências",
            "ano": "6º ano",
            "enunciado": "Explique como os cloroplastos realizam a fotossíntese utilizando luz solar, água e gás carbônico para produzir glicose e liberar oxigênio.",
        },
        {
            "disciplina": "Matemática",
            "ano": "7º ano",
            "enunciado": "Resolva a equação de primeiro grau 3x + 12 = 30 e determine o valor da incógnita x.",
        },
    ]

    print("\nExecutando bateria de teste padrão com 2 questões representativas:")
    for i, item in enumerate(amostras, 1):
        print(f"\n--- [Caso de Teste {i}] {item['disciplina']} ({item['ano']}) ---")
        print(f"Enunciado: {item['enunciado']}")
        t0 = time.perf_counter()
        inv = extractor.extract(
            request=item["enunciado"],
            disciplina=item["disciplina"],
            ano_escolar=item["ano"],
        )
        dt = (time.perf_counter() - t0) * 1000
        formatar_invariantes(inv, dt)


if __name__ == "__main__":
    main()

