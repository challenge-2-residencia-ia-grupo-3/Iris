"""Repositórios PostgreSQL do schema isolado `docente` (ADR-10).

Implementa CRUD de contas docentes (cadastro local + identidade OAuth Google),
tokens de atualização e histórico de atividades pedagógicas sanitizadas com isolamento
estrito por `professor_id`.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from iris.storage.database import PostgresConnectionManager
from iris.storage.privacy_gate import ActivitySavePayload, validate_and_prepare_activity


class StorageConflictError(ValueError):
    """Conflito de unicidade ou estado (ex.: e-mail já cadastrado)."""

    def __init__(self, detail: str, *, code: str = "CONFLICT") -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = 409


class StorageNotFoundError(LookupError):
    """Registro solicitado não existe ou não pertence ao docente autenticado."""

    def __init__(self, detail: str = "Registro não encontrado.", *, code: str = "NOT_FOUND") -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = 404


@dataclass(frozen=True)
class TeacherRecord:
    id: str
    email: str
    email_verificado: bool
    nome_exibicao: str
    senha_hash: str | None
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime

    def publico(self, *, providers: list[str] | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "email_verificado": self.email_verificado,
            "nome_exibicao": self.nome_exibicao,
            "possui_senha_local": bool(self.senha_hash),
            "oauth_providers": providers if providers is not None else [],
            "criado_em": self.criado_em.isoformat(),
        }


@dataclass(frozen=True)
class ActivitySummaryRecord:
    id: str
    professor_id: str
    titulo: str
    disciplina: str | None
    ano_escolar: str | None
    nivel_andaime: int
    caracteristicas_ids: list[str]
    status: str
    total_questoes: int
    criado_em: datetime
    atualizado_em: datetime

    def publico(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "disciplina": self.disciplina,
            "ano_escolar": self.ano_escolar,
            "nivel_andaime": self.nivel_andaime,
            "caracteristicas_ids": list(self.caracteristicas_ids),
            "status": self.status,
            "total_questoes": self.total_questoes,
            "criado_em": self.criado_em.isoformat(),
            "atualizado_em": self.atualizado_em.isoformat(),
        }


@dataclass(frozen=True)
class ActivityDetailRecord:
    id: str
    professor_id: str
    titulo: str
    disciplina: str | None
    ano_escolar: str | None
    nivel_andaime: int
    caracteristicas_ids: list[str]
    travas_curriculares: dict[str, Any]
    questoes: list[dict[str, Any]]
    metricas: dict[str, Any]
    status: str
    versao_schema: str
    criado_em: datetime
    atualizado_em: datetime

    def publico(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "disciplina": self.disciplina,
            "ano_escolar": self.ano_escolar,
            "nivel_andaime": self.nivel_andaime,
            "caracteristicas_ids": list(self.caracteristicas_ids),
            "travas_curriculares": dict(self.travas_curriculares),
            "questoes": list(self.questoes),
            "metricas": dict(self.metricas),
            "status": self.status,
            "versao_schema": self.versao_schema,
            "criado_em": self.criado_em.isoformat(),
            "atualizado_em": self.atualizado_em.isoformat(),
        }


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _parse_json_field(val: Any, default: Any) -> Any:
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        return json.loads(val)
    return default


def _row_to_teacher(row: tuple[Any, ...]) -> TeacherRecord:
    return TeacherRecord(
        id=str(row[0]),
        email=str(row[1]),
        email_verificado=bool(row[2]),
        nome_exibicao=str(row[3]),
        senha_hash=row[4],
        ativo=bool(row[5]),
        criado_em=row[6],
        atualizado_em=row[7],
    )


def _row_to_activity_detail(row: tuple[Any, ...]) -> ActivityDetailRecord:
    return ActivityDetailRecord(
        id=str(row[0]),
        professor_id=str(row[1]),
        titulo=str(row[2]),
        disciplina=row[3],
        ano_escolar=row[4],
        nivel_andaime=int(row[5]),
        caracteristicas_ids=list(row[6] or []),
        travas_curriculares=_parse_json_field(row[7], {}),
        questoes=_parse_json_field(row[8], []),
        metricas=_parse_json_field(row[9], {}),
        status=str(row[10]),
        versao_schema=str(row[11]),
        criado_em=row[12],
        atualizado_em=row[13],
    )


class TeacherRepository:
    """Persistência de contas docentes (cadastro local + vínculos OAuth Google)."""

    def __init__(self, db: PostgresConnectionManager) -> None:
        self._db = db

    def get_by_email(self, email: str) -> TeacherRecord | None:
        norm = _norm_email(email)
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, email_verificado, nome_exibicao, senha_hash, ativo, criado_em, atualizado_em
                    FROM docente.professores
                    WHERE email = %s
                    """,
                    (norm,),
                )
                row = cur.fetchone()
                return _row_to_teacher(row) if row else None

    def get_by_id(self, professor_id: str) -> TeacherRecord | None:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, email_verificado, nome_exibicao, senha_hash, ativo, criado_em, atualizado_em
                    FROM docente.professores
                    WHERE id = %s
                    """,
                    (str(professor_id),),
                )
                row = cur.fetchone()
                return _row_to_teacher(row) if row else None

    def list_oauth_providers(self, professor_id: str) -> list[str]:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT provider FROM docente.identidades_oauth WHERE professor_id = %s ORDER BY provider",
                    (str(professor_id),),
                )
                return [str(r[0]) for r in cur.fetchall()]

    def create_local_teacher(self, *, email: str, nome_exibicao: str, senha_hash: str) -> TeacherRecord:
        norm = _norm_email(email)
        nome = " ".join(nome_exibicao.split())
        new_id = str(uuid.uuid4())
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute("SELECT 1 FROM docente.professores WHERE email = %s", (norm,))
                if cur.fetchone() is not None:
                    raise StorageConflictError(
                        "Já existe uma conta cadastrada com este e-mail.",
                        code="EMAIL_ALREADY_REGISTERED",
                    )
                cur.execute(
                    """
                    INSERT INTO docente.professores
                        (id, email, email_verificado, nome_exibicao, senha_hash, ativo)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    RETURNING id, email, email_verificado, nome_exibicao, senha_hash, ativo, criado_em, atualizado_em
                    """,
                    (new_id, norm, False, nome, senha_hash),
                )
                row = cur.fetchone()
                return _row_to_teacher(row)

    def find_or_create_oauth_teacher(
        self,
        *,
        provider: str,
        provider_subject: str,
        email: str,
        email_verified: bool,
        nome_exibicao: str,
    ) -> TeacherRecord:
        """Autentica ou cria conta docente a partir de provedor OAuth (ex.: Google)."""
        norm_email = _norm_email(email)
        nome = " ".join(nome_exibicao.split()) or norm_email.split("@")[0]

        with self._db.connection() as con:
            with con.cursor() as cur:
                # 1. Identidade OAuth já vinculada
                cur.execute(
                    """
                    SELECT p.id, p.email, p.email_verificado, p.nome_exibicao, p.senha_hash, p.ativo, p.criado_em, p.atualizado_em
                    FROM docente.identidades_oauth io
                    JOIN docente.professores p ON p.id = io.professor_id
                    WHERE io.provider = %s AND io.provider_subject = %s
                    """,
                    (provider, provider_subject),
                )
                existing_oauth = cur.fetchone()
                if existing_oauth is not None:
                    return _row_to_teacher(existing_oauth)

                # 2. Conta existente com o mesmo e-mail: só vincula se o provedor confirmou o e-mail
                cur.execute(
                    """
                    SELECT id, email, email_verificado, nome_exibicao, senha_hash, ativo, criado_em, atualizado_em
                    FROM docente.professores
                    WHERE email = %s
                    """,
                    (norm_email,),
                )
                existing_email = cur.fetchone()
                if existing_email is not None:
                    if not email_verified:
                        raise StorageConflictError(
                            "O provedor OAuth não confirmou a propriedade deste e-mail para vincular à conta existente.",
                            code="OAUTH_EMAIL_NOT_VERIFIED",
                        )
                    teacher_id = str(existing_email[0])
                    cur.execute(
                        """
                        INSERT INTO docente.identidades_oauth (id, professor_id, provider, provider_subject)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (str(uuid.uuid4()), teacher_id, provider, provider_subject),
                    )
                    if not bool(existing_email[2]):
                        cur.execute(
                            "UPDATE docente.professores SET email_verificado = TRUE, atualizado_em = NOW() WHERE id = %s",
                            (teacher_id,),
                        )
                    cur.execute(
                        """
                        SELECT id, email, email_verificado, nome_exibicao, senha_hash, ativo, criado_em, atualizado_em
                        FROM docente.professores WHERE id = %s
                        """,
                        (teacher_id,),
                    )
                    return _row_to_teacher(cur.fetchone())

                # 3. Novo professor via OAuth
                new_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO docente.professores
                        (id, email, email_verificado, nome_exibicao, senha_hash, ativo)
                    VALUES (%s, %s, %s, %s, NULL, TRUE)
                    RETURNING id, email, email_verificado, nome_exibicao, senha_hash, ativo, criado_em, atualizado_em
                    """,
                    (new_id, norm_email, bool(email_verified), nome),
                )
                teacher_row = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO docente.identidades_oauth (id, professor_id, provider, provider_subject)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), new_id, provider, provider_subject),
                )
                return _row_to_teacher(teacher_row)

    def delete_teacher(self, professor_id: str) -> bool:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute("DELETE FROM docente.professores WHERE id = %s", (str(professor_id),))
                return cur.rowcount > 0


class RefreshTokenRepository:
    """Persistência de refresh tokens opacos (armazenados via hash SHA-256)."""

    def __init__(self, db: PostgresConnectionManager) -> None:
        self._db = db

    def store_token(self, *, professor_id: str, token_hash: str, expira_em: datetime) -> str:
        token_id = str(uuid.uuid4())
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO docente.refresh_tokens (id, professor_id, token_hash, expira_em)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (token_id, str(professor_id), token_hash, expira_em),
                )
        return token_id

    def get_active_token(self, token_hash: str) -> dict[str, Any] | None:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, professor_id, expira_em, revogado_em
                    FROM docente.refresh_tokens
                    WHERE token_hash = %s
                      AND revogado_em IS NULL
                      AND expira_em > NOW()
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "id": str(row[0]),
                    "professor_id": str(row[1]),
                    "expira_em": row[2],
                }

    def revoke_token(self, token_hash: str) -> bool:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    UPDATE docente.refresh_tokens
                    SET revogado_em = NOW()
                    WHERE token_hash = %s AND revogado_em IS NULL
                    """,
                    (token_hash,),
                )
                return cur.rowcount > 0

    def revoke_all_for_teacher(self, professor_id: str) -> int:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    UPDATE docente.refresh_tokens
                    SET revogado_em = NOW()
                    WHERE professor_id = %s AND revogado_em IS NULL
                    """,
                    (str(professor_id),),
                )
                return int(cur.rowcount or 0)


class ActivityHistoryRepository:
    """Persistência de atividades pedagógicas sanitizadas isolada por `professor_id`."""

    def __init__(self, db: PostgresConnectionManager) -> None:
        self._db = db

    def create_activity(
        self,
        *,
        professor_id: str,
        payload: Mapping[str, Any] | ActivitySavePayload,
        auto_sanitizar: bool = False,
    ) -> ActivityDetailRecord:
        sanitized = validate_and_prepare_activity(payload, auto_sanitizar=auto_sanitizar)
        new_id = str(uuid.uuid4())
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO docente.atividades_historico (
                        id, professor_id, titulo, disciplina, ano_escolar,
                        nivel_andaime, caracteristicas_ids, travas_curriculares,
                        questoes, metricas, status, versao_schema
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, '1.0')
                    RETURNING id, professor_id, titulo, disciplina, ano_escolar,
                              nivel_andaime, caracteristicas_ids, travas_curriculares,
                              questoes, metricas, status, versao_schema, criado_em, atualizado_em
                    """,
                    (
                        new_id,
                        str(professor_id),
                        sanitized.titulo,
                        sanitized.disciplina,
                        sanitized.ano_escolar,
                        sanitized.nivel_andaime,
                        sanitized.caracteristicas_ids,
                        json.dumps(sanitized.travas_curriculares, ensure_ascii=False),
                        json.dumps(sanitized.questoes, ensure_ascii=False),
                        json.dumps(sanitized.metricas, ensure_ascii=False),
                        sanitized.status,
                    ),
                )
                return _row_to_activity_detail(cur.fetchone())

    def list_activities(
        self,
        *,
        professor_id: str,
        q: str | None = None,
        disciplina: str | None = None,
        nivel_andaime: int | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ActivitySummaryRecord], int]:
        where = ["professor_id = %s"]
        params: list[Any] = [str(professor_id)]

        if q and q.strip():
            where.append("titulo ILIKE %s")
            params.append(f"%{q.strip()}%")
        if disciplina and disciplina.strip():
            where.append("disciplina = %s")
            params.append(disciplina.strip())
        if nivel_andaime is not None:
            where.append("nivel_andaime = %s")
            params.append(int(nivel_andaime))
        if status and status.strip():
            where.append("status = %s")
            params.append(status.strip().lower())

        where_sql = " AND ".join(where)
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))

        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM docente.atividades_historico WHERE {where_sql}", tuple(params))
                total = int(cur.fetchone()[0])

                cur.execute(
                    f"""
                    SELECT id, professor_id, titulo, disciplina, ano_escolar,
                           nivel_andaime, caracteristicas_ids, status,
                           jsonb_array_length(questoes) AS total_questoes,
                           criado_em, atualizado_em
                    FROM docente.atividades_historico
                    WHERE {where_sql}
                    ORDER BY atualizado_em DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*params, safe_limit, safe_offset),
                )
                rows = cur.fetchall()

        items = [
            ActivitySummaryRecord(
                id=str(r[0]),
                professor_id=str(r[1]),
                titulo=str(r[2]),
                disciplina=r[3],
                ano_escolar=r[4],
                nivel_andaime=int(r[5]),
                caracteristicas_ids=list(r[6] or []),
                status=str(r[7]),
                total_questoes=int(r[8] or 0),
                criado_em=r[9],
                atualizado_em=r[10],
            )
            for r in rows
        ]
        return items, total

    def get_activity(self, *, professor_id: str, activity_id: str) -> ActivityDetailRecord:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, professor_id, titulo, disciplina, ano_escolar,
                           nivel_andaime, caracteristicas_ids, travas_curriculares,
                           questoes, metricas, status, versao_schema, criado_em, atualizado_em
                    FROM docente.atividades_historico
                    WHERE id = %s AND professor_id = %s
                    """,
                    (str(activity_id), str(professor_id)),
                )
                row = cur.fetchone()
                if row is None:
                    raise StorageNotFoundError("Atividade não encontrada no seu histórico.")
                return _row_to_activity_detail(row)

    def update_activity(
        self,
        *,
        professor_id: str,
        activity_id: str,
        payload: Mapping[str, Any] | ActivitySavePayload,
        auto_sanitizar: bool = False,
    ) -> ActivityDetailRecord:
        sanitized = validate_and_prepare_activity(payload, auto_sanitizar=auto_sanitizar)
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    UPDATE docente.atividades_historico
                    SET titulo = %s,
                        disciplina = %s,
                        ano_escolar = %s,
                        nivel_andaime = %s,
                        caracteristicas_ids = %s,
                        travas_curriculares = %s::jsonb,
                        questoes = %s::jsonb,
                        metricas = %s::jsonb,
                        status = %s,
                        atualizado_em = NOW()
                    WHERE id = %s AND professor_id = %s
                    RETURNING id, professor_id, titulo, disciplina, ano_escolar,
                              nivel_andaime, caracteristicas_ids, travas_curriculares,
                              questoes, metricas, status, versao_schema, criado_em, atualizado_em
                    """,
                    (
                        sanitized.titulo,
                        sanitized.disciplina,
                        sanitized.ano_escolar,
                        sanitized.nivel_andaime,
                        sanitized.caracteristicas_ids,
                        json.dumps(sanitized.travas_curriculares, ensure_ascii=False),
                        json.dumps(sanitized.questoes, ensure_ascii=False),
                        json.dumps(sanitized.metricas, ensure_ascii=False),
                        sanitized.status,
                        str(activity_id),
                        str(professor_id),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise StorageNotFoundError("Atividade não encontrada no seu histórico.")
                return _row_to_activity_detail(row)

    def duplicate_activity(
        self,
        *,
        professor_id: str,
        activity_id: str,
        novo_titulo: str | None = None,
    ) -> ActivityDetailRecord:
        original = self.get_activity(professor_id=professor_id, activity_id=activity_id)
        titulo_copia = (novo_titulo or f"{original.titulo} (Cópia)")[:120]
        payload = {
            "titulo": titulo_copia,
            "disciplina": original.disciplina,
            "ano_escolar": original.ano_escolar,
            "nivel_andaime": original.nivel_andaime,
            "caracteristicas_ids": original.caracteristicas_ids,
            "travas_curriculares": original.travas_curriculares,
            "questoes": [
                {
                    **q,
                    "aprovada": False,
                }
                for q in original.questoes
            ],
            "metricas": original.metricas,
            "status": "rascunho",
        }
        return self.create_activity(professor_id=professor_id, payload=payload, auto_sanitizar=False)

    def delete_activity(self, *, professor_id: str, activity_id: str) -> bool:
        with self._db.connection() as con:
            with con.cursor() as cur:
                cur.execute(
                    "DELETE FROM docente.atividades_historico WHERE id = %s AND professor_id = %s",
                    (str(activity_id), str(professor_id)),
                )
                if cur.rowcount == 0:
                    raise StorageNotFoundError("Atividade não encontrada no seu histórico.")
                return True
