"""Utilitários criptográficos da autenticação docente: Argon2id, JWT HS256 e tokens opacos."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from iris.config import IrisSettings, get_settings

_EPHEMERAL_DEV_SECRET: str | None = None


class AuthTokenError(ValueError):
    """Erro de emissão ou validação de token JWT."""

    def __init__(self, detail: str, *, code: str = "INVALID_TOKEN") -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = 401


def resolve_jwt_secret(settings: IrisSettings | None = None) -> str:
    """Resolve o segredo HMAC para JWTs (exige configuração explícita em produção)."""
    global _EPHEMERAL_DEV_SECRET
    cfg = settings or get_settings()
    if cfg.jwt_secret.strip():
        return cfg.jwt_secret.strip()
    if cfg.env.strip().lower() == "production":
        raise RuntimeError(
            "IRIS_JWT_SECRET deve estar configurado em ambiente de produção."
        )
    if _EPHEMERAL_DEV_SECRET is None:
        _EPHEMERAL_DEV_SECRET = secrets.token_urlsafe(32)
    return _EPHEMERAL_DEV_SECRET


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))


def hash_password(password: str) -> str:
    """Gera hash Argon2id seguro para senha local."""
    from argon2 import PasswordHasher

    ph = PasswordHasher()
    return ph.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verifica senha contra hash Argon2id em tempo constante."""
    if not password_hash:
        return False
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError

    ph = PasswordHasher()
    try:
        return bool(ph.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(
    *,
    professor_id: str,
    email: str,
    nome_exibicao: str,
    secret: str,
    ttl_minutes: int = 30,
) -> tuple[str, int]:
    """Emite JWT HS256 padrão (RFC 7519) e retorna `(token, expires_in_seconds)`."""
    now = int(time.time())
    ttl_seconds = max(60, int(ttl_minutes) * 60)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(professor_id),
        "email": email,
        "name": nome_exibicao,
        "typ": "access",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}", ttl_seconds


def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:
    """Valida assinatura e expiração de um JWT HS256 e retorna o payload."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise AuthTokenError("Token de acesso malformado.")

    h_b64, p_b64, s_b64 = parts
    try:
        header = json.loads(_b64url_decode(h_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        sig = _b64url_decode(s_b64)
    except Exception as exc:
        raise AuthTokenError("Token de acesso inválido.") from exc

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise AuthTokenError("Algoritmo de token não suportado.")

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        f"{h_b64}.{p_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(sig, expected_sig):
        raise AuthTokenError("Assinatura do token inválida.")

    if not isinstance(payload, dict) or payload.get("typ") != "access" or not payload.get("sub"):
        raise AuthTokenError("Payload de token inválido.")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or int(time.time()) >= int(exp):
        raise AuthTokenError("Sessão expirada. Faça login novamente.", code="TOKEN_EXPIRED")

    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Gera refresh token opaco e seu hash SHA-256 para armazenamento seguro."""
    raw = secrets.token_urlsafe(48)
    digest = hash_opaque_token(raw)
    return raw, digest


def hash_opaque_token(raw_token: str) -> str:
    """Calcula SHA-256 hexadecimal de um token opaco."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def sign_value(value: str, *, secret: str) -> str:
    """Assina um valor curto (ex.: state OAuth) com HMAC-SHA256."""
    sig = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return f"{value}.{_b64url_encode(sig)}"


def verify_signed_value(signed: str, *, secret: str) -> str | None:
    """Verifica assinatura HMAC de um valor curto e retorna o valor original."""
    if "." not in signed:
        return None
    value, s_b64 = signed.rsplit(".", 1)
    try:
        sig = _b64url_decode(s_b64)
    except Exception:
        return None
    expected = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    return value
