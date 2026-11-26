"""Gerenciamento de conexão PostgreSQL e DDL do schema isolado `docente` (ADR-10 / RNF-01).

Este módulo opera exclusivamente sobre o schema `docente` (`professores`, `identidades_oauth`,
`atividades_historico` e `refresh_tokens`), mantendo total separação da tabela vetorial do RAG
(`public.iris_trechos`) e proibição absoluta de tabelas ou dados de estudantes.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

from iris.config import get_settings

SCHEMA_DOCENTE_DDL = """
CREATE SCHEMA IF NOT EXISTS docente;

CREATE TABLE IF NOT EXISTS docente.professores (
    id                UUID PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE,
    email_verificado  BOOLEAN NOT NULL DEFAULT FALSE,
    nome_exibicao     TEXT NOT NULL,
    senha_hash        TEXT NULL,
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS docente.identidades_oauth (
    id                UUID PRIMARY KEY,
    professor_id      UUID NOT NULL REFERENCES docente.professores(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,
    provider_subject  TEXT NOT NULL,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_subject)
);

CREATE TABLE IF NOT EXISTS docente.atividades_historico (
    id                   UUID PRIMARY KEY,
    professor_id         UUID NOT NULL REFERENCES docente.professores(id) ON DELETE CASCADE,
    titulo               TEXT NOT NULL,
    disciplina           TEXT NULL,
    ano_escolar          TEXT NULL,
    nivel_andaime        SMALLINT NOT NULL CHECK (nivel_andaime BETWEEN 1 AND 3),
    caracteristicas_ids  TEXT[] NOT NULL DEFAULT '{}',
    travas_curriculares  JSONB NOT NULL DEFAULT '{}'::jsonb,
    questoes             JSONB NOT NULL,
    metricas             JSONB NOT NULL DEFAULT '{}'::jsonb,
    status               TEXT NOT NULL CHECK (status IN ('rascunho', 'homologada')),
    versao_schema        TEXT NOT NULL DEFAULT '1.0',
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_atividades_prof_data
    ON docente.atividades_historico (professor_id, atualizado_em DESC);

CREATE INDEX IF NOT EXISTS idx_atividades_caracteristicas_gin
    ON docente.atividades_historico USING GIN (caracteristicas_ids);

CREATE TABLE IF NOT EXISTS docente.refresh_tokens (
    id            UUID PRIMARY KEY,
    professor_id  UUID NOT NULL REFERENCES docente.professores(id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,
    expira_em     TIMESTAMPTZ NOT NULL,
    revogado_em   TIMESTAMPTZ NULL,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_prof
    ON docente.refresh_tokens (professor_id);
"""


class DatabaseUnavailableError(RuntimeError):
    """Indica indisponibilidade do PostgreSQL para persistência do histórico docente."""

    def __init__(self, detail: str = "Banco de dados PostgreSQL indisponível no momento.") -> None:
        super().__init__(detail)
        self.status_code = 503
        self.code = "DATABASE_UNAVAILABLE"


class PostgresConnectionManager:
    """Gerencia conexões transacionais e inicialização idempotente do schema `docente`."""

    def __init__(self, dsn: str | None = None, *, connect_timeout: int = 3) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._schema_ready = False
        self._lock = threading.Lock()

    @property
    def dsn(self) -> str:
        return self._dsn or get_settings().app_pg_dsn

    def _open_raw_connection(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise DatabaseUnavailableError(
                "Driver PostgreSQL (psycopg) não instalado no ambiente."
            ) from exc

        try:
            return psycopg.connect(self.dsn, connect_timeout=self._connect_timeout)
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Não foi possível conectar ao PostgreSQL do histórico docente."
            ) from exc

    def ensure_schema(self, *, force: bool = False) -> None:
        """Cria o schema `docente` e suas tabelas de forma idempotente."""
        if self._schema_ready and not force:
            return
        with self._lock:
            if self._schema_ready and not force:
                return
            con = self._open_raw_connection()
            try:
                with con:
                    with con.cursor() as cur:
                        cur.execute(SCHEMA_DOCENTE_DDL)
                self._schema_ready = True
            finally:
                con.close()

    @contextmanager
    def connection(self, *, ensure_ddl: bool = True) -> Iterator[Any]:
        """Fornece uma conexão transacional com commit automático ou rollback em exceção."""
        if ensure_ddl:
            self.ensure_schema()
        con = self._open_raw_connection()
        try:
            with con:
                yield con
        finally:
            con.close()

    def is_available(self) -> bool:
        """Verifica rapidamente se o PostgreSQL responde a uma consulta simples."""
        try:
            con = self._open_raw_connection()
            try:
                with con.cursor() as cur:
                    cur.execute("SELECT 1")
                return True
            finally:
                con.close()
        except DatabaseUnavailableError:
            return False
