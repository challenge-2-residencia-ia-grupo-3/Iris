"""Camada de persistência PostgreSQL isolada para histórico docente (ADR-10 / RNF-01)."""
from iris.storage.database import (
    SCHEMA_DOCENTE_DDL,
    DatabaseUnavailableError,
    PostgresConnectionManager,
)
from iris.storage.privacy_gate import (
    FORBIDDEN_STUDENT_OR_CLINICAL_KEYS,
    ActivityPrivacyViolationError,
    ActivityQuestionInput,
    ActivitySavePayload,
    SanitizedActivityData,
    validate_and_prepare_activity,
)
from iris.storage.repositories import (
    ActivityDetailRecord,
    ActivityHistoryRepository,
    ActivitySummaryRecord,
    RefreshTokenRepository,
    StorageConflictError,
    StorageNotFoundError,
    TeacherRecord,
    TeacherRepository,
)

__all__ = [
    "ActivityDetailRecord",
    "ActivityHistoryRepository",
    "ActivityPrivacyViolationError",
    "ActivityQuestionInput",
    "ActivitySavePayload",
    "ActivitySummaryRecord",
    "DatabaseUnavailableError",
    "FORBIDDEN_STUDENT_OR_CLINICAL_KEYS",
    "PostgresConnectionManager",
    "RefreshTokenRepository",
    "SCHEMA_DOCENTE_DDL",
    "SanitizedActivityData",
    "StorageConflictError",
    "StorageNotFoundError",
    "TeacherRecord",
    "TeacherRepository",
    "validate_and_prepare_activity",
]
