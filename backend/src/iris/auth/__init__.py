"""Módulo de autenticação docente (cadastro/login local + Google OAuth 2.0)."""
from iris.auth.google_oauth import GoogleOAuthClient, GoogleOAuthError, GoogleUserProfile
from iris.auth.security import (
    AuthTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    resolve_jwt_secret,
    verify_password,
)
from iris.auth.service import AuthError, AuthService

__all__ = [
    "AuthError",
    "AuthService",
    "AuthTokenError",
    "GoogleOAuthClient",
    "GoogleOAuthError",
    "GoogleUserProfile",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "resolve_jwt_secret",
    "verify_password",
]
