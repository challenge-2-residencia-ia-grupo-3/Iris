"""Rotas HTTP do Histórico de Atividades Docentes no PostgreSQL (ADR-10)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from iris.api.routes.auth import require_authenticated_teacher
from iris.exportacao.material import ExportacaoMaterialError, exportar_material
from iris.sessao.revisao import REPOSITORIO, SEPARADOR_QUESTOES, SessaoError
from iris.storage.database import DatabaseUnavailableError, PostgresConnectionManager
from iris.storage.privacy_gate import ActivityPrivacyViolationError
from iris.storage.repositories import (
    ActivityHistoryRepository,
    StorageConflictError,
    StorageNotFoundError,
    TeacherRecord,
)

_HISTORY_REPO = ActivityHistoryRepository(PostgresConnectionManager())


def get_history_repository() -> ActivityHistoryRepository:
    return _HISTORY_REPO


class SaveFromSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str | None = Field(default=None, max_length=120)
    disciplina: str | None = Field(default=None, max_length=80)
    ano_escolar: str | None = Field(default=None, max_length=60)
    nivel_andaime: int = Field(default=2, ge=1, le=3)
    caracteristicas_ids: list[str] = Field(default_factory=list, max_length=30)
    travas_curriculares: dict[str, Any] = Field(default_factory=dict)
    metricas: dict[str, Any] = Field(default_factory=dict)


class DuplicateActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    novo_titulo: str | None = Field(default=None, max_length=120)


try:
    from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

    router = APIRouter(prefix="/history", tags=["historico-docente"])

    def _translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, ActivityPrivacyViolationError):
            return HTTPException(status_code=422, detail=exc.to_dict())
        if isinstance(exc, StorageNotFoundError):
            return HTTPException(
                status_code=404,
                detail={"status": "error", "code": exc.code, "detail": str(exc)},
            )
        if isinstance(exc, StorageConflictError):
            return HTTPException(
                status_code=409,
                detail={"status": "error", "code": exc.code, "detail": str(exc)},
            )
        if isinstance(exc, DatabaseUnavailableError):
            return HTTPException(
                status_code=503,
                detail={"status": "error", "code": exc.code, "detail": str(exc)},
            )
        if isinstance(exc, SessaoError):
            return HTTPException(status_code=exc.status, detail=exc.to_dict())
        if isinstance(exc, ExportacaoMaterialError):
            return HTTPException(status_code=422, detail=exc.to_dict())
        return HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "code": "HISTORY_ERROR",
                "detail": "Erro interno ao processar a solicitação do histórico.",
            },
        )

    @router.get("", summary="Lista atividades salvas no histórico da conta docente")
    async def list_history(
        q: str | None = Query(default=None, max_length=100),
        disciplina: str | None = Query(default=None, max_length=80),
        nivel_andaime: int | None = Query(default=None, ge=1, le=3),
        status_filtro: str | None = Query(default=None, alias="status", pattern="^(rascunho|homologada)$"),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> dict[str, Any]:
        try:
            items, total = repo.list_activities(
                professor_id=teacher.id,
                q=q,
                disciplina=disciplina,
                nivel_andaime=nivel_andaime,
                status=status_filtro,
                limit=limit,
                offset=offset,
            )
            return {
                "items": [item.publico() for item in items],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post("", status_code=status.HTTP_201_CREATED, summary="Salva atividade sanitizada no histórico docente")
    async def create_history_activity(
        payload: dict[str, Any] = Body(...),
        auto_sanitizar: bool = Query(default=False, description="Anonimiza PII no corpo antes de gravar"),
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> dict[str, Any]:
        try:
            created = repo.create_activity(
                professor_id=teacher.id,
                payload=payload,
                auto_sanitizar=auto_sanitizar,
            )
            return created.publico()
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post(
        "/from-session/{session_id}",
        status_code=status.HTTP_201_CREATED,
        summary="Salva no histórico uma sessão de revisão em memória",
    )
    async def save_from_review_session(
        session_id: str,
        meta: SaveFromSessionRequest = Body(default_factory=SaveFromSessionRequest),
        auto_sanitizar: bool = Query(default=False),
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> dict[str, Any]:
        try:
            sessao = REPOSITORIO.ler(session_id)
            titulo_final = (meta.titulo or sessao.get("titulo") or "Atividade adaptada").strip()
            payload = {
                "titulo": titulo_final,
                "disciplina": meta.disciplina,
                "ano_escolar": meta.ano_escolar,
                "nivel_andaime": meta.nivel_andaime,
                "caracteristicas_ids": meta.caracteristicas_ids,
                "travas_curriculares": meta.travas_curriculares,
                "questoes": [
                    {
                        "id": str(q.get("id", f"q{idx}")),
                        "original": str(q.get("original") or ""),
                        "adaptado": str(q.get("adaptado") or ""),
                        "editada": bool(q.get("editada", False)),
                        "aprovada": bool(q.get("aprovada", False)),
                        "justificativas": [],
                    }
                    for idx, q in enumerate(sessao.get("questoes", []), start=1)
                ],
                "metricas": meta.metricas,
                "status": "homologada" if sessao.get("homologada") else "rascunho",
            }
            created = repo.create_activity(
                professor_id=teacher.id,
                payload=payload,
                auto_sanitizar=auto_sanitizar,
            )
            return created.publico()
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.get("/{activity_id}", summary="Obtém os detalhes de uma atividade do histórico")
    async def get_history_activity(
        activity_id: str,
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> dict[str, Any]:
        try:
            return repo.get_activity(professor_id=teacher.id, activity_id=activity_id).publico()
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.put("/{activity_id}", summary="Atualiza e/ou homologa uma atividade do histórico")
    async def update_history_activity(
        activity_id: str,
        payload: dict[str, Any] = Body(...),
        auto_sanitizar: bool = Query(default=False),
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> dict[str, Any]:
        try:
            updated = repo.update_activity(
                professor_id=teacher.id,
                activity_id=activity_id,
                payload=payload,
                auto_sanitizar=auto_sanitizar,
            )
            return updated.publico()
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post("/{activity_id}/duplicate", status_code=status.HTTP_201_CREATED, summary="Duplica atividade como novo rascunho")
    async def duplicate_history_activity(
        activity_id: str,
        payload: DuplicateActivityRequest = Body(default_factory=DuplicateActivityRequest),
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> dict[str, Any]:
        try:
            duplicated = repo.duplicate_activity(
                professor_id=teacher.id,
                activity_id=activity_id,
                novo_titulo=payload.novo_titulo,
            )
            return duplicated.publico()
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post("/{activity_id}/export", summary="Gera PDF ou DOCX sob demanda a partir de atividade homologada", response_class=Response)
    async def export_history_activity(
        activity_id: str,
        formato: str = Query("pdf", description="pdf ou docx"),
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> Response:
        try:
            activity = repo.get_activity(professor_id=teacher.id, activity_id=activity_id)
            todas_aprovadas = bool(activity.questoes) and all(bool(q.get("aprovada")) for q in activity.questoes)
            if activity.status != "homologada" or not todas_aprovadas:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "status": "error",
                        "code": "EXPORT_BLOCKED",
                        "field": "status",
                        "detail": "A exportação só é liberada para atividades com todas as questões aprovadas e homologadas.",
                    },
                )
            texto = SEPARADOR_QUESTOES.join(str(q.get("adaptado", "")).strip() for q in activity.questoes)
            arquivo = exportar_material({"titulo": activity.titulo, "texto": texto}, formato)
            return Response(
                content=arquivo.conteudo,
                media_type=arquivo.media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{arquivo.nome}"',
                    "Cache-Control": "no-store",
                },
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Exclui permanentemente uma atividade do histórico")
    async def delete_history_activity(
        activity_id: str,
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        repo: ActivityHistoryRepository = Depends(get_history_repository),
    ) -> Response:
        try:
            repo.delete_activity(professor_id=teacher.id, activity_id=activity_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

except ImportError:  # pragma: no cover
    router = None  # type: ignore[assignment]
