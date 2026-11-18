"""Erros do módulo de áudio, com o status HTTP que a rota deve devolver."""
from __future__ import annotations


class AudioError(ValueError):
    def __init__(self, mensagem: str, code: str, status: int = 422, field: str = "audio") -> None:
        super().__init__(mensagem)
        self.code, self.status, self.field = code, status, field

    def to_dict(self) -> dict[str, str]:
        return {"status": "error", "code": self.code, "field": self.field, "detail": str(self)}
