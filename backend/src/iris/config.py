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

# Modelo padrão do juiz (e do gerador da bateria com chave), num lugar só, para a classe e a leitura do ambiente
# não divergirem. O valor é o que o grupo fixou na dev; trocar o modelo é decisão do grupo (IRIS_JUDGE_MODEL).
JUIZ_MODELO_PADRAO = "claude-sonnet-4-5-20250929"

# Armazenamentos persistentes autorizados no backend (RNF-01 / ADR-10)
ALLOWED_PERSISTENT_STORES: tuple[str, ...] = ("rag_vector_readonly", "teacher_activity_history")
FORBIDDEN_STUDENT_DB_ENV_VARS: tuple[str, ...] = (
    "STUDENT_DATABASE_URL",
    "STUDENTS_DATABASE_URL",
    "ALUNOS_DATABASE_URL",
    "IRIS_STUDENT_DB_DSN",
)


def _parse_dotenv_file(dotenv_path: Path) -> dict[str, str]:
    """Lê pares CHAVE=VALOR de um arquivo `.env` sem dependências externas."""
    if not dotenv_path.exists():
        return {}
    valores: dict[str, str] = {}
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
                val = val[1:-1]
            if key:
                valores[key] = val
    except OSError:
        return {}
    return valores


def load_dotenv_into_environ(override_empty: bool = True) -> dict[str, str]:
    """Carrega variáveis de `iris/.env` (e `.env` da raiz se existir) para `os.environ`."""
    merged: dict[str, str] = {}
    for candidate in (REPO_ROOT.parent / ".env", REPO_ROOT / ".env"):
        merged.update(_parse_dotenv_file(candidate))
    for key, val in merged.items():
        current = os.environ.get(key)
        if current is None or (override_empty and current == "" and val != ""):
            os.environ[key] = val
    return merged


def _get_env(key: str, default: str = "", dotenv_map: dict[str, str] | None = None) -> str:
    """Obtém variável priorizando valor preenchido em `os.environ` ou atualização dinâmica do `.env`."""
    env_val = os.environ.get(key)
    if env_val is not None and env_val != "":
        return env_val
    if dotenv_map and dotenv_map.get(key):
        os.environ[key] = dotenv_map[key]
        return dotenv_map[key]
    if env_val is not None:
        return env_val
    if dotenv_map and key in dotenv_map:
        return dotenv_map[key]
    return default


@dataclass(frozen=True)
class IrisSettings:
    """Parâmetros de ambiente da aplicação stateless Íris."""

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # Provedor de LLM ("ollama" ou "groq")
    llm_provider: str = "ollama"
    llm_model: str = "llama3.1:8b"
    ollama_url: str = "http://127.0.0.1:11434"
    groq_api_key: str = ""

    # Juiz de Auditoria RAG (Claude Sonnet via API Anthropic)
    anthropic_api_key: str = ""
    judge_model: str = JUIZ_MODELO_PADRAO

    # Parâmetros do RAG (base vetorial somente-leitura de artigos e manuais públicos)
    rag_banco: str = "pgvector"
    rag_metodo: str = "qwen3+rerank50"
    rag_reranker: str = "mminilm"
    rag_pg_dsn: str = "postgresql://iris:iris@127.0.0.1:5433/iris"

    # Banco de histórico docente (schema isolado `docente` no PostgreSQL — ADR-10)
    app_pg_dsn: str = "postgresql://iris:iris@127.0.0.1:5433/iris"
    jwt_secret: str = ""
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8000/api/v1/auth/oauth/google/callback"
    frontend_url: str = "http://localhost:3000"

    # Guardrails arquiteturais inegociáveis (Pilar 3 / RNF-01 - Zero-Database de Alunos)
    zero_student_database: bool = True
    stateless_for_students: bool = True
    stateless_mode: bool = True
    allowed_persistent_stores: tuple[str, ...] = ALLOWED_PERSISTENT_STORES

    def __post_init__(self) -> None:
        if not self.zero_student_database:
            raise ValueError(
                "Violação de RNF-01: a plataforma Íris exige zero_student_database=True "
                "(sem tabelas ou banco de dados de estudantes)."
            )
        if not self.stateless_for_students or not self.stateless_mode:
            raise ValueError(
                "Violação de RNF-01: a plataforma Íris exige stateless_for_students=True e stateless_mode=True "
                "(sem estado persistido de estudantes ou cookies de sessão no servidor)."
            )
        if tuple(self.allowed_persistent_stores) != ALLOWED_PERSISTENT_STORES:
            raise ValueError(
                "Violação de RNF-01 / ADR-10: os únicos armazenamentos persistentes permitidos no backend "
                "são a base vetorial do RAG e o histórico sanitizado de atividades docentes."
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
        "stateless_for_students": cfg.stateless_for_students,
        "stateless_mode": cfg.stateless_mode,
        "allowed_persistent_stores": list(cfg.allowed_persistent_stores),
        "student_data_persistence_allowed": False,
    }


def _get_int_env(key: str, default: int, dotenv_map: dict[str, str] | None = None) -> int:
    raw = _get_env(key, str(default), dotenv_map)
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


def get_settings() -> IrisSettings:
    """Retorna a configuração atual lida das variáveis de ambiente e do arquivo `.env`."""
    dotenv_map = load_dotenv_into_environ(override_empty=True)
    llm_prov = _get_env("IRIS_LLM_PROVIDER", _get_env("RAG_LLM", "ollama", dotenv_map), dotenv_map)
    llm_mod = _get_env("IRIS_LLM_MODEL", _get_env("RAG_LLM_MODELO", "llama3.1:8b", dotenv_map), dotenv_map)
    port_val = _get_int_env("IRIS_PORT", 8000, dotenv_map)
    rag_dsn = _get_env("RAG_PG_DSN", "postgresql://iris:iris@127.0.0.1:5433/iris", dotenv_map)
    app_dsn = _get_env("IRIS_APP_PG_DSN", _get_env("APP_PG_DSN", rag_dsn, dotenv_map), dotenv_map)

    return IrisSettings(
        env=_get_env("IRIS_ENV", "development", dotenv_map),
        host=_get_env("IRIS_HOST", "127.0.0.1", dotenv_map),
        port=port_val,
        log_level=_get_env("IRIS_LOG_LEVEL", "INFO", dotenv_map),
        llm_provider=llm_prov,
        llm_model=llm_mod,
        ollama_url=_get_env("OLLAMA_URL", "http://127.0.0.1:11434", dotenv_map),
        groq_api_key=_get_env("GROQ_API_KEY", "", dotenv_map),
        anthropic_api_key=_get_env("ANTHROPIC_API_KEY", "", dotenv_map),
        judge_model=_get_env("IRIS_JUDGE_MODEL", JUIZ_MODELO_PADRAO, dotenv_map),
        rag_banco=_get_env("RAG_BANCO", "pgvector", dotenv_map),
        rag_metodo=_get_env("RAG_METODO", "qwen3+rerank50", dotenv_map),
        rag_reranker=_get_env("RAG_RERANKER", "mminilm", dotenv_map),
        rag_pg_dsn=rag_dsn,
        app_pg_dsn=app_dsn,
        jwt_secret=_get_env("IRIS_JWT_SECRET", "", dotenv_map),
        jwt_access_ttl_minutes=_get_int_env("IRIS_JWT_ACCESS_TTL_MINUTES", 30, dotenv_map),
        jwt_refresh_ttl_days=_get_int_env("IRIS_JWT_REFRESH_TTL_DAYS", 14, dotenv_map),
        google_client_id=_get_env("GOOGLE_CLIENT_ID", "", dotenv_map),
        google_client_secret=_get_env("GOOGLE_CLIENT_SECRET", "", dotenv_map),
        google_redirect_uri=_get_env(
            "GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8000/api/v1/auth/oauth/google/callback",
            dotenv_map,
        ),
        frontend_url=_get_env("IRIS_FRONTEND_URL", "http://localhost:3000", dotenv_map),
        zero_student_database=True,
    )
