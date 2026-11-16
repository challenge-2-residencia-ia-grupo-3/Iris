"""Configuração centralizada e caminhos absolutos da plataforma Íris."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

# Único armazenamento persistente autorizado no backend (RNF-01)
ALLOWED_PERSISTENT_STORES: tuple[str, ...] = ("rag_vector_readonly",)
FORBIDDEN_STUDENT_DB_ENV_VARS: tuple[str, ...] = (
    "STUDENT_DATABASE_URL",
    "STUDENTS_DATABASE_URL",
    "ALUNOS_DATABASE_URL",
    "IRIS_STUDENT_DB_DSN",
)


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

    # Parâmetros do RAG (base vetorial somente-leitura de artigos e manuais públicos)
    rag_banco: str = os.environ.get("RAG_BANCO", "pgvector")
    rag_metodo: str = os.environ.get("RAG_METODO", "qwen3+rerank50")
    rag_reranker: str = os.environ.get("RAG_RERANKER", "mminilm")
    rag_pg_dsn: str = os.environ.get("RAG_PG_DSN", "postgresql://iris:iris@127.0.0.1:5433/iris")

    # Guardrails arquiteturais inegociáveis (Pilar 3 / RNF-01 - Zero-Database de Alunos)
    zero_student_database: bool = True
    stateless_mode: bool = True
    allowed_persistent_stores: tuple[str, ...] = ALLOWED_PERSISTENT_STORES

    def __post_init__(self) -> None:
        if not self.zero_student_database:
            raise ValueError(
                "Violação de RNF-01: a plataforma Íris exige zero_student_database=True "
                "(sem tabelas ou banco de dados de estudantes)."
            )
        if not self.stateless_mode:
            raise ValueError(
                "Violação de RNF-01: a plataforma Íris exige stateless_mode=True "
                "(ciclo de vida restrito à sessão em memória)."
            )
        if tuple(self.allowed_persistent_stores) != ALLOWED_PERSISTENT_STORES:
            raise ValueError(
                "Violação de RNF-01: o único armazenamento persistente permitido no backend "
                "é a base vetorial somente-leitura de artigos e manuais públicos (RAG)."
            )


def validate_zero_database_configuration(settings: IrisSettings | None = None) -> dict[str, Any]:
    """Valida que a configuração da aplicação não habilita banco ou persistência de alunos."""
    cfg = settings or get_settings()
    active_forbidden_env = [var for var in FORBIDDEN_STUDENT_DB_ENV_VARS if os.environ.get(var, "").strip()]
    if active_forbidden_env:
        raise ValueError(
            "Violação de RNF-01: variáveis de ambiente de banco de dados de estudantes não são permitidas: "
            + ", ".join(active_forbidden_env)
        )
    return {
        "zero_student_database": cfg.zero_student_database,
        "stateless_mode": cfg.stateless_mode,
        "allowed_persistent_stores": list(cfg.allowed_persistent_stores),
        "rag_vector_store_only": True,
    }


def get_settings() -> IrisSettings:
    """Retorna a configuração atual lida das variáveis de ambiente."""
    return IrisSettings()

