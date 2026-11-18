"""Serviço de autenticação docente: cadastro/login local no PostgreSQL + OAuth Google."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from iris.auth.google_oauth import GoogleOAuthClient
from iris.auth.security import (
    AuthTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    resolve_jwt_secret,
    verify_password,
)
from iris.config import IrisSettings, get_settings
from iris.storage.database import PostgresConnectionManager
from iris.storage.repositories import RefreshTokenRepository, TeacherRecord, TeacherRepository

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class AuthError(ValueError):
    """Erro de autenticação traduzido para resposta HTTP estruturada."""

    def __init__(self, detail: str, *, code: str = "AUTH_ERROR", status_code: int = 401) -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = status_code

    def to_dict(self) -> dict[str, str]:
        return {
            "status": "error",
            "code": self.code,
            "detail": str(self),
        }


class AuthService:
    """Coordena cadastro/login local, refresh tokens, JWT e fluxo Google OAuth."""

    def __init__(
        self,
        db: PostgresConnectionManager | None = None,
        *,
        settings: IrisSettings | None = None,
        google_client: GoogleOAuthClient | None = None,
    ) -> None:
        self._settings = settings
        self.db = db or PostgresConnectionManager()
        self.teachers = TeacherRepository(self.db)
        self.refresh_tokens = RefreshTokenRepository(self.db)
        self.google = google_client or GoogleOAuthClient(settings=settings)

    @property
    def settings(self) -> IrisSettings:
        return self._settings or get_settings()

    def providers_status(self) -> dict[str, Any]:
        return {
            "local_enabled": True,
            "google_enabled": self.google.is_enabled(),
            "guest_mode_enabled": True,
            "database_online": self.db.is_available(),
        }

    def _issue_session_tokens(self, teacher: TeacherRecord) -> dict[str, Any]:
        cfg = self.settings
        secret = resolve_jwt_secret(cfg)
        access_token, expires_in = create_access_token(
            professor_id=teacher.id,
            email=teacher.email,
            nome_exibicao=teacher.nome_exibicao,
            secret=secret,
            ttl_minutes=cfg.jwt_access_ttl_minutes,
        )
        raw_refresh, refresh_hash = generate_refresh_token()
        expira_em = datetime.now(timezone.utc) + timedelta(days=cfg.jwt_refresh_ttl_days)
        self.refresh_tokens.store_token(
            professor_id=teacher.id,
            token_hash=refresh_hash,
            expira_em=expira_em,
        )
        providers = self.teachers.list_oauth_providers(teacher.id)
        return {
            "token_type": "bearer",
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "expires_in": expires_in,
            "teacher": teacher.publico(providers=providers),
        }

    def register_local(self, *, email: str, nome_exibicao: str, senha: str) -> dict[str, Any]:
        norm_email = email.strip().lower()
        if not _EMAIL_RE.match(norm_email):
            raise AuthError("Informe um e-mail válido.", code="INVALID_EMAIL", status_code=422)
        nome = " ".join(nome_exibicao.split())
        if len(nome) < 2 or len(nome) > 100:
            raise AuthError(
                "O nome de exibição deve ter entre 2 e 100 caracteres.",
                code="INVALID_NAME",
                status_code=422,
            )
        if len(senha) < 8 or len(senha) > 128:
            raise AuthError(
                "A senha deve ter entre 8 e 128 caracteres.",
                code="WEAK_PASSWORD",
                status_code=422,
            )

        senha_hash = hash_password(senha)
        teacher = self.teachers.create_local_teacher(
            email=norm_email,
            nome_exibicao=nome,
            senha_hash=senha_hash,
        )
        return self._issue_session_tokens(teacher)

    def login_local(self, *, email: str, senha: str) -> dict[str, Any]:
        norm_email = email.strip().lower()
        if not norm_email or not senha:
            raise AuthError("E-mail e senha são obrigatórios.", code="MISSING_CREDENTIALS", status_code=422)

        teacher = self.teachers.get_by_email(norm_email)
        if teacher is None:
            raise AuthError("E-mail ou senha inválidos.", code="INVALID_CREDENTIALS", status_code=401)
        if not teacher.ativo:
            raise AuthError("Conta desativada.", code="INACTIVE_ACCOUNT", status_code=403)
        if not teacher.senha_hash:
            raise AuthError(
                "Esta conta utiliza login pelo Google. Entre com o Google.",
                code="OAUTH_ONLY_ACCOUNT",
                status_code=401,
            )
        if not verify_password(senha, teacher.senha_hash):
            raise AuthError("E-mail ou senha inválidos.", code="INVALID_CREDENTIALS", status_code=401)

        return self._issue_session_tokens(teacher)

    def refresh_session(self, refresh_token: str) -> dict[str, Any]:
        if not refresh_token or not refresh_token.strip():
            raise AuthError("Refresh token obrigatório.", code="INVALID_REFRESH_TOKEN", status_code=401)

        token_hash = hash_opaque_token(refresh_token.strip())
        record = self.refresh_tokens.get_active_token(token_hash)
        if record is None:
            raise AuthError(
                "Refresh token inválido ou expirado.",
                code="INVALID_REFRESH_TOKEN",
                status_code=401,
            )

        teacher = self.teachers.get_by_id(record["professor_id"])
        if teacher is None or not teacher.ativo:
            raise AuthError("Conta docente não encontrada ou inativa.", code="INVALID_ACCOUNT", status_code=401)

        self.refresh_tokens.revoke_token(token_hash)
        return self._issue_session_tokens(teacher)

    def logout(self, refresh_token: str | None) -> None:
        if refresh_token and refresh_token.strip():
            self.refresh_tokens.revoke_token(hash_opaque_token(refresh_token.strip()))

    def authenticate_bearer(self, authorization_header: str | None) -> TeacherRecord:
        if not authorization_header or not authorization_header.strip():
            raise AuthError("Autenticação necessária.", code="NOT_AUTHENTICATED", status_code=401)
        parts = authorization_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise AuthError("Cabeçalho Authorization deve usar formato Bearer.", code="INVALID_AUTH_HEADER", status_code=401)

        secret = resolve_jwt_secret(self.settings)
        try:
            payload = decode_access_token(parts[1].strip(), secret=secret)
        except AuthTokenError as exc:
            raise AuthError(str(exc), code=exc.code, status_code=401) from exc

        teacher = self.teachers.get_by_id(str(payload["sub"]))
        if teacher is None or not teacher.ativo:
            raise AuthError("Conta docente não encontrada ou inativa.", code="INVALID_ACCOUNT", status_code=401)
        return teacher

    def complete_google_callback(self, *, code: str, signed_state: str) -> tuple[str, str]:
        """Processa callback do Google e devolve `(exchange_code, next_path)`."""
        pending = self.google.consume_state(signed_state)
        profile = self.google.exchange_code_for_profile(
            code=code,
            code_verifier=pending.code_verifier,
        )
        teacher = self.teachers.find_or_create_oauth_teacher(
            provider="google",
            provider_subject=profile.subject,
            email=profile.email,
            email_verified=profile.email_verified,
            nome_exibicao=profile.name,
        )
        session_payload = self._issue_session_tokens(teacher)
        exchange_code = self.google.create_exchange_code(session_payload)
        return exchange_code, pending.next_path

    def redeem_oauth_exchange(self, exchange_code: str) -> dict[str, Any]:
        return self.google.redeem_exchange_code(exchange_code)

    def delete_account(self, professor_id: str) -> bool:
        self.refresh_tokens.revoke_all_for_teacher(professor_id)
        return self.teachers.delete_teacher(professor_id)
