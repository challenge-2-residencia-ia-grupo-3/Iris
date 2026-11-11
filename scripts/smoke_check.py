#!/usr/bin/env python3
"""Smoke-check completo do ambiente, dependências e endpoints da Íris (`make check`).

Valida em poucos segundos se todas as peças já implementadas (Base, Catálogo, PII,
Upload/Texto, RAG, Métricas, Agente Extrator e Analytics) estão íntegras antes dos
testes manuais no navegador ou CLI.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "rag" / "iris-rag" / "pacote"))


def _ok(nome: str, detalhe: str = "") -> None:
    suf = f" — {detalhe}" if detalhe else ""
    print(f"  [OK]   {nome}{suf}")


def _warn(nome: str, detalhe: str = "") -> None:
    suf = f" — {detalhe}" if detalhe else ""
    print(f"  [AVISO] {nome}{suf}")


def _fail(nome: str, detalhe: str = "") -> None:
    suf = f" — {detalhe}" if detalhe else ""
    print(f"  [ERRO] {nome}{suf}")


def main() -> int:
    print("\n" + "=" * 78)
    print("  ÍRIS — SMOKE CHECK DO AMBIENTE E ISSUES IMPLEMENTADAS (`make check`)")
    print("=" * 78)

    erros: list[str] = []

    # 1. Dependências Python & Ferramentas
    print("\n1. Verificação de Ambiente & Dependências:")
    mods = ["fastapi", "uvicorn", "pydantic", "pymupdf", "docx", "rank_bm25"]
    faltando = []
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            faltando.append(m)
    if faltando:
        _fail("Dependências Python", f"ausentes: {faltando}")
        erros.append(f"Módulos Python ausentes: {faltando}")
    else:
        _ok("Dependências Python", f"{len(mods)} pacotes críticos disponíveis ({sys.executable})")

    node_ok = shutil.which("node") and shutil.which("npm")
    nm_ok = (REPO_ROOT / "frontend" / "node_modules").is_dir()
    if node_ok and nm_ok:
        _ok("Frontend Next.js", "node/npm e frontend/node_modules prontos")
    elif node_ok:
        _warn("Frontend Next.js", "node/npm ok, mas frontend/node_modules ausente (make up/front instala)")
    else:
        _warn("Frontend Next.js", "node/npm não detectados no PATH")

    from iris.core.llm_client import get_llm_client

    llm_st = get_llm_client().status()
    if llm_st.get("ollama_online"):
        _ok("Ollama Local", f"ONLINE com modelos {llm_st.get('ollama_installed_models')}")
    else:
        _warn("Ollama Local", "OFFLINE no momento (sistema usará fallback determinístico onde aplicável)")

    # 2. Dados, Catálogo e Golden Benchmark
    print("\n2. Verificação de Dados, Catálogo (#39) e Golden Benchmark (#45):")
    try:
        from iris.schemas.catalog import load_all_catalogs

        cats = load_all_catalogs()
        total_items = sum(len(c.caracteristicas) for c in cats.values())
        _ok("Catálogos Funcionais", f"{len(cats)} arquivo(s), {total_items} características carregadas")
    except Exception as exc:
        _fail("Catálogos Funcionais", str(exc))
        erros.append(f"Catálogos: {exc}")

    chunks_path = REPO_ROOT / "rag" / "iris-rag" / "pacote" / "chunks.jsonl"
    if chunks_path.exists() and chunks_path.stat().st_size > 0:
        n_chunks = sum(1 for ln in chunks_path.read_text(encoding="utf-8").splitlines() if ln.strip())
        _ok("Base RAG (chunks.jsonl)", f"{n_chunks} trechos indexáveis prontos")
    else:
        _warn("Base RAG (chunks.jsonl)", "arquivo não encontrado (execute './rag/setup_rag.sh --padrao')")

    try:
        from iris.eval.benchmark import carregar_golden_benchmark

        qs = carregar_golden_benchmark()
        assert len(qs) >= 30
        _ok("Golden Benchmark (#45)", f"{len(qs)} questões escolares com trava_curricular")
    except Exception as exc:
        _fail("Golden Benchmark (#45)", str(exc))
        erros.append(f"Benchmark: {exc}")

    # 3. Smoke Check dos Endpoints REST FastAPI (TestClient)
    print("\n3. Verificação da API FastAPI (#4, #16, #17, #34, #42, #43):")
    try:
        from fastapi.testclient import TestClient
        from iris.main import app

        client = TestClient(app)

        r_health = client.get("/api/v1/health")
        assert r_health.status_code == 200 and r_health.json().get("zero_student_database") is True
        _ok("GET /api/v1/health", "stateless Zero-Database confirmado")

        r_cat = client.get("/api/v1/catalog")
        assert r_cat.status_code == 200 and len(r_cat.json().get("caracteristicas", [])) > 0
        _ok("GET /api/v1/catalog", f"{len(r_cat.json()['caracteristicas'])} características servidas")

        payload_pii = {
            "text": (
                "Aluno: Gabriel Costa\n"
                "CPF: 123.456.789-00\n"
                "Questão 1: Explique como funciona o ciclo da água e identifique suas principais etapas."
            )
        }
        r_mat = client.post("/api/v1/materials/text", json=payload_pii)
        assert r_mat.status_code == 200
        body_mat = r_mat.json()
        raw_txt = body_mat["raw_text"]
        pii_count = body_mat["metadata"]["pii_removed_count"]
        assert "[ESTUDANTE]" in raw_txt
        assert "[CPF]" in raw_txt
        assert "Gabriel Costa" not in raw_txt
        assert pii_count >= 2
        _ok(
            "POST /api/v1/materials/text (#4 + #34)",
            f"PII descartado ({pii_count} substituições)",
        )

        r_curto = client.post("/api/v1/materials/text", json={"text": "Texto curto"})
        assert r_curto.status_code == 422
        _ok("Validação < 50 chars (#4)", "HTTP 422 retornado conforme critério")

        r_rag = client.post("/api/v1/rag/search", json={"pergunta": "comandos multiplos tdah", "metodo": "bm25", "k": 3})
        assert r_rag.status_code == 200 and len(r_rag.json().get("trechos_rag", [])) > 0
        _ok("POST /api/v1/rag/search (#16/#42)", f"{len(r_rag.json()['trechos_rag'])} trechos recuperados")

        r_met = client.get("/api/v1/eval/metrics")
        assert r_met.status_code == 200 and "metricas_relatorio_iris" in r_met.json()
        _ok("GET /api/v1/eval/metrics (#42/#43)", "12 métricas RAG/RAGAS disponíveis")

        r_ext_an = client.get("/api/v1/eval/extractor-analytics")
        assert r_ext_an.status_code == 200 and "resumo_geral" in r_ext_an.json()
        _ok(
            "GET /api/v1/eval/extractor-analytics (#17)",
            f"{r_ext_an.json()['resumo_geral']['total_execucoes']} registro(s) no log",
        )
    except Exception as exc:
        _fail("API FastAPI", repr(exc))
        erros.append(f"API FastAPI: {exc}")

    # 4. Avaliação (TRCC / Flesch) e Agente Extrator (#17, #52)
    print("\n4. Verificação do Motor de Métricas (#52) e Agente Extrator (#17):")
    try:
        from iris.agents.curriculum_extractor import get_curriculum_extractor
        from iris.eval.readability import analyze_question
        from iris.eval.trcc import avaliar_trcc

        trcc_res = avaliar_trcc(["cachorro", "encontrou|achou", "Pedro"], "Pedro achou o cachorro.")
        assert trcc_res.aprovado() and trcc_res.trcc == 1.0
        _ok("TRCC Determinístico (#52)", f"score={trcc_res.trcc:.2f} aprovado={trcc_res.aprovado()}")

        read_res = analyze_question("Q01", "Leia o texto e responda quem encontrou o cachorro.")
        assert read_res.flesch is not None
        _ok("Flesch PT-BR (#40/#45)", f"flesch={read_res.flesch:.1f}, conjugado={read_res.has_conjugated_command}")

        ext = get_curriculum_extractor(llm_client=get_llm_client(provider="extractive"))
        ext_res = ext.extract_with_telemetry(
            "Calcule a área de um triângulo com base 8 cm e altura 5 cm.",
            disciplina="Matemática",
            ano_escolar="6º ano",
        )
        assert ext_res.invariants.verbo_comando_bncc
        assert ext_res.telemetry.faixa_etaria == "Fund. II Inicial (11-12 anos)"
        _ok(
            "Agente Extrator Curricular (#17)",
            f"verbo={ext_res.invariants.verbo_comando_bncc}, faixa={ext_res.telemetry.faixa_etaria}",
        )
    except Exception as exc:
        _fail("Métricas/Extrator", repr(exc))
        erros.append(f"Métricas/Extrator: {exc}")

    print("\n" + "=" * 78)
    if erros:
        print(f"  RESULTADO: FALHOU ({len(erros)} erro(s))")
        for err in erros:
            print(f"   - {err}")
        print("=" * 78 + "\n")
        return 1
    print("  RESULTADO: TUDO ÍNTEGRO E PRONTO PARA TESTE MANUAL!")
    print("=" * 78 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
