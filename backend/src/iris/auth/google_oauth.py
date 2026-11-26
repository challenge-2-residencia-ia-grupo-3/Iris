"""Integração OAuth 2.0 / OIDC com Google (Authorization Code + PKCE, sem cookies)."""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from iris.auth.security import resolve_jwt_secret, sign_value, verify_signed_value
from iris.config import IrisSettings, get_settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

_STATE_TTL_SECONDS = 600
_EXCHANGE_TTL_SECONDS = 90
_MAX_PENDING_ENTRIES = 500


class GoogleOAuthError(ValueError):
    """Erro de configuração ou troca OAuth com o Google."""

    def __init__(self, detail: str, *, code: str = "GOOGLE_OAUTH_ERROR", status_code: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PendingOAuthState:
    code_verifier: str
    next_path: str
    expires_at: float


@dataclass(frozen=True)
class GoogleUserProfile:
    subject: str
    email: str
    email_verified: bool
    name: str


class _MemoryTTLStore:
    """Armazenamento efêmero em memória para `state` PKCE e códigos de troca únicos."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        expired = [k for k, (exp, _) in self._items.items() if exp <= now]
        for k in expired:
            del self._items[k]

    def put(self, key: str, value: Any, ttl_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if len(self._items) >= _MAX_PENDING_ENTRIES:
                oldest_key = min(self._items, key=lambda k: self._items[k][0])
                del self._items[oldest_key]
            self._items[key] = (now + ttl_seconds, value)

    def pop(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            entry = self._items.pop(key, None)
            if entry is None:
                return None
            exp, value = entry
            return value if exp > now else None


class GoogleOAuthClient:
    """Cliente Google OAuth 2.0 com PKCE S256 e código único de troca para o frontend."""

    def __init__(
        self,
        settings: IrisSettings | None = None,
        *,
        http_client_factory: Any = None,
    ) -> None:
        self._settings = settings
        self._http_client_factory = http_client_factory
        self._states = _MemoryTTLStore()
        self._exchanges = _MemoryTTLStore()

    @property
    def settings(self) -> IrisSettings:
        return self._settings or get_settings()

    def is_enabled(self) -> bool:
        cfg = self.settings
        return bool(cfg.google_client_id.strip() and cfg.google_client_secret.strip())

    def build_authorization_url(self, *, next_path: str = "/historico") -> str:
        """Gera URL de consentimento Google com PKCE e `state` assinado."""
        cfg = self.settings
        if not self.is_enabled():
            raise GoogleOAuthError(
                "Login com Google ainda não está configurado neste servidor.",
                code="GOOGLE_OAUTH_NOT_CONFIGURED",
                status_code=503,
            )

        safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/historico"
        nonce = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(48)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        self._states.put(
            nonce,
            PendingOAuthState(
                code_verifier=code_verifier,
                next_path=safe_next,
                expires_at=time.monotonic() + _STATE_TTL_SECONDS,
            ),
            _STATE_TTL_SECONDS,
        )
        signed_state = sign_value(nonce, secret=resolve_jwt_secret(cfg))
        query = urlencode(
            {
                "client_id": cfg.google_client_id.strip(),
                "redirect_uri": cfg.google_redirect_uri.strip(),
                "response_type": "code",
                "scope": "openid email profile",
                "state": signed_state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{GOOGLE_AUTH_URL}?{query}"

    def consume_state(self, signed_state: str) -> PendingOAuthState:
        """Valida e consome o `state` assinado devolvido no callback."""
        cfg = self.settings
        nonce = verify_signed_value(signed_state, secret=resolve_jwt_secret(cfg))
        if not nonce:
            raise GoogleOAuthError("Parâmetro state OAuth inválido.", code="INVALID_OAUTH_STATE", status_code=400)
        pending = self._states.pop(nonce)
        if pending is None:
            raise GoogleOAuthError(
                "Sessão de login Google expirada ou já utilizada.",
                code="EXPIRED_OAUTH_STATE",
                status_code=400,
            )
        return pending

    def exchange_code_for_profile(self, *, code: str, code_verifier: str) -> GoogleUserProfile:
        """Troca o authorization code pelo token e busca o perfil OIDC verificado no Google."""
        cfg = self.settings
        if not self.is_enabled():
            raise GoogleOAuthError(
                "Login com Google não está configurado.",
                code="GOOGLE_OAUTH_NOT_CONFIGURED",
                status_code=503,
            )

        client_ctx = (
            self._http_client_factory()
            if self._http_client_factory is not None
            else httpx.Client(timeout=10.0)
        )
        with client_ctx as client:
            token_resp = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": cfg.google_client_id.strip(),
                    "client_secret": cfg.google_client_secret.strip(),
                    "redirect_uri": cfg.google_redirect_uri.strip(),
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
            )
            if token_resp.status_code != 200:
                raise GoogleOAuthError(
                    "Não foi possível concluir a autenticação com o Google.",
                    code="GOOGLE_TOKEN_EXCHANGE_FAILED",
                    status_code=401,
                )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise GoogleOAuthError(
                    "Resposta inválida do Google ao obter token de acesso.",
                    code="GOOGLE_TOKEN_MISSING",
                    status_code=401,
                )

            userinfo_resp = client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                raise GoogleOAuthError(
                    "Não foi possível obter os dados da conta Google.",
                    code="GOOGLE_USERINFO_FAILED",
                    status_code=401,
                )
            info = userinfo_resp.json()

        subject = str(info.get("sub") or "").strip()
        email = str(info.get("email") or "").strip().lower()
        email_verified = bool(info.get("email_verified", False))
        name = str(info.get("name") or "").strip() or (email.split("@")[0] if email else "Professor(a)")

        if not subject or not email:
            raise GoogleOAuthError(
                "A conta Google não retornou identificador e e-mail válidos.",
                code="GOOGLE_PROFILE_INCOMPLETE",
                status_code=400,
            )

        return GoogleUserProfile(
            subject=subject,
            email=email,
            email_verified=email_verified,
            name=name,
        )

    def create_exchange_code(self, payload: dict[str, Any]) -> str:
        """Gera código único de curta duração para entregar tokens ao frontend sem expor JWT na URL."""
        code = secrets.token_urlsafe(32)
        self._exchanges.put(code, payload, _EXCHANGE_TTL_SECONDS)
        return code

    def redeem_exchange_code(self, code: str) -> dict[str, Any]:
        """Consome o código único de troca e retorna os tokens de sessão."""
        data = self._exchanges.pop(code.strip())
        if data is None:
            raise GoogleOAuthError(
                "Código de troca OAuth inválido ou expirado.",
                code="INVALID_EXCHANGE_CODE",
                status_code=401,
            )
        return data
