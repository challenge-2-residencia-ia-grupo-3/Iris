"""Guardrails de privacidade e conformidade LGPD (Sanitizador Preventivo de PII / Zero-Retention)."""
from iris.security.pii_scrubber import sanitize_pii

__all__ = ["sanitize_pii"]

