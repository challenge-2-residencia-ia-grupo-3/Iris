"""Configuração centralizada e caminhos absolutos da plataforma Íris."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Caminhos absolutos independentes do diretório de trabalho (cwd)
PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
BACKEND_DIR = SRC_DIR.parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR

RAG_DIR = REPO_ROOT / "rag"
RAG_BASE_DIR = RAG_DIR / "iris-rag"
RAG_PACOTE_DIR = RAG_BASE_DIR / "pacote"
CATALOGS_DIR = RAG_DIR / "catalogs"
BENCHMARKS_DIR = REPO_ROOT / "data" / "benchmarks"


@dataclass(frozen=True)
class IrisSettings:
    """Parâmetros de ambiente da aplicação stateless Íris."""

    env: str = os.environ.get("IRIS_ENV", "development")
    host: str = os.environ.get("IRIS_HOST", "127.0.0.1")
    port: int = int(os.environ.get("IRIS_PORT", "8000"))
    log_level: str = os.environ.get("IRIS_LOG_LEVEL", "INFO")

    # Provedor de LLM ("ollama" ou "groq")
    llm_provider: str = os.environ.get("IRIS_LLM_PROVIDER", os.environ.get("RAG_LLM", "ollama"))
    llm_model: str = os.environ.get("IRIS_LLM_MODEL", os.environ.get("RAG_LLM_MODELO", "llama3.1:8b"))
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")

    # Parâmetros do RAG
    rag_banco: str = os.environ.get("RAG_BANCO", "pgvector")
    rag_metodo: str = os.environ.get("RAG_METODO", "qwen3+rerank50")
    rag_reranker: str = os.environ.get("RAG_RERANKER", "mminilm")
    rag_pg_dsn: str = os.environ.get("RAG_PG_DSN", "postgresql://iris:iris@127.0.0.1:5433/iris")

    # Guardrail arquitetural inegociável (Pilar 3 - Zero-Database de Alunos)
    zero_student_database: bool = True


def get_settings() -> IrisSettings:
    """Retorna a configuração atual lida das variáveis de ambiente."""
    return IrisSettings()

