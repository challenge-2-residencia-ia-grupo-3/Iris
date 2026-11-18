"""Rotas HTTP de Autenticação Docente: Cadastro/Login local + OAuth 2.0 Google (ADR-10)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from iris.auth.google_oauth import GoogleOAuthError
from iris.auth.service import AuthError, AuthService
from iris.storage.database import DatabaseUnavailableError
from iris.storage.repositories import StorageConflictError, TeacherRecord

_AUTH_SERVICE = AuthService()


def get_auth_service() -> AuthService:
    return _AUTH_SERVICE


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=5, max_length=254)
    nome_exibicao: str = Field(..., min_length=2, max_length=100)
    senha: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=254)
    senha: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., min_length=10, max_length=512)


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(default=None, max_length=512)


class OAuthExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=8, max_length=512)


try:
    from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
    from fastapi.responses import RedirectResponse

    router = APIRouter(prefix="/auth", tags=["auth"])

    def _translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, AuthError):
            return HTTPException(status_code=exc.status_code, detail=exc.to_dict())
        if isinstance(exc, GoogleOAuthError):
            return HTTPException(
                status_code=exc.status_code,
                detail={"status": "error", "code": exc.code, "detail": str(exc)},
            )
        if isinstance(exc, StorageConflictError):
            return HTTPException(
                status_code=exc.status_code,
                detail={"status": "error", "code": exc.code, "detail": str(exc)},
            )
        if isinstance(exc, DatabaseUnavailableError):
            return HTTPException(
                status_code=503,
                detail={"status": "error", "code": exc.code, "detail": str(exc)},
            )
        return HTTPException(
            status_code=500,
            detail={"status": "error", "code": "INTERNAL_AUTH_ERROR", "detail": str(exc)},
        )

    def require_authenticated_teacher(
        authorization: str | None = Header(default=None),
        auth: AuthService = Depends(get_auth_service),
    ) -> TeacherRecord:
        try:
            return auth.authenticate_bearer(authorization)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.get("/providers", summary="Provedores de autenticação habilitados")
    async def providers(auth: AuthService = Depends(get_auth_service)) -> dict[str, Any]:
        return auth.providers_status()

    @router.post("/register", status_code=status.HTTP_201_CREATED, summary="Cadastro de professor no PostgreSQL")
    async def register(
        payload: RegisterRequest,
        auth: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        try:
            return auth.register_local(
                email=payload.email,
                nome_exibicao=payload.nome_exibicao,
                senha=payload.senha,
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post("/login", summary="Login com e-mail e senha")
    async def login(
        payload: LoginRequest,
        auth: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        try:
            return auth.login_local(email=payload.email, senha=payload.senha)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post("/refresh", summary="Renova o JWT via refresh token")
    async def refresh(
        payload: RefreshRequest,
        auth: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        try:
            return auth.refresh_session(payload.refresh_token)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoga refresh token")
    async def logout(
        payload: LogoutRequest,
        auth: AuthService = Depends(get_auth_service),
    ) -> Response:
        try:
            auth.logout(payload.refresh_token)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.get("/me", summary="Perfil mínimo da conta docente autenticada")
    async def get_me(
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        auth: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        try:
            providers_list = auth.teachers.list_oauth_providers(teacher.id)
            return teacher.publico(providers=providers_list)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, summary="Exclui conta e todo histórico (LGPD)")
    async def delete_me(
        teacher: TeacherRecord = Depends(require_authenticated_teacher),
        auth: AuthService = Depends(get_auth_service),
    ) -> Response:
        try:
            auth.delete_account(teacher.id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

    @router.get("/oauth/google/start", summary="Inicia login OAuth 2.0 com Google (PKCE)")
    async def google_start(
        next_path: str = Query("/historico", alias="next"),
        mode: str = Query("redirect", pattern="^(redirect|json)$"),
        auth: AuthService = Depends(get_auth_service),
    ) -> Any:
        try:
            url = auth.google.build_authorization_url(next_path=next_path)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc
        if mode == "json":
            return {"authorization_url": url}
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

    @router.get("/oauth/google/callback", summary="Callback OAuth 2.0 do Google")
    async def google_callback(
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
        auth: AuthService = Depends(get_auth_service),
    ) -> RedirectResponse:
        frontend_base = auth.settings.frontend_url.rstrip("/")
        if error:
            qs = urlencode({"error": error})
            return RedirectResponse(url=f"{frontend_base}/auth/callback?{qs}", status_code=status.HTTP_302_FOUND)
        if not code or not state:
            qs = urlencode({"error": "missing_oauth_params"})
            return RedirectResponse(url=f"{frontend_base}/auth/callback?{qs}", status_code=status.HTTP_302_FOUND)
        try:
            exchange_code, next_path = auth.complete_google_callback(code=code, signed_state=state)
            qs = urlencode({"code": exchange_code, "next": next_path})
            return RedirectResponse(url=f"{frontend_base}/auth/callback?{qs}", status_code=status.HTTP_302_FOUND)
        except Exception as exc:  # noqa: BLE001
            err_code = getattr(exc, "code", "oauth_callback_failed")
            qs = urlencode({"error": str(err_code)})
            return RedirectResponse(url=f"{frontend_base}/auth/callback?{qs}", status_code=status.HTTP_302_FOUND)

    @router.post("/oauth/exchange", summary="Troca código único OAuth por tokens JWT da aplicação")
    async def oauth_exchange(
        payload: OAuthExchangeRequest,
        auth: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        try:
            return auth.redeem_oauth_exchange(payload.code)
        except Exception as exc:  # noqa: BLE001
            raise _translate_error(exc) from exc

except ImportError:  # pragma: no cover
    router = None  # type: ignore[assignment]
    require_authenticated_teacher = None  # type: ignore[assignment]
