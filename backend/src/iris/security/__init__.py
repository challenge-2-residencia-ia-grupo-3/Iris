"""Guardrails de privacidade e conformidade LGPD (Sanitizador Preventivo de PII / Zero-Retention)."""
from iris.security.pii_scrubber import (
    detect_clinical_reference,
    sanitize_pedagogical_note,
    sanitize_pii,
)

__all__ = ["sanitize_pii", "sanitize_pedagogical_note", "detect_clinical_reference"]


