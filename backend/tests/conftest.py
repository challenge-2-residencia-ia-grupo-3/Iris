"""Configuração comum dos testes.

Nenhum teste chama a API da Anthropic de verdade. Com uma chave no ambiente ou no `.env`, o juiz Sonnet entra sozinho
no modo "auto" e quatro testes do RAG e da bancada faziam 18 chamadas pagas (medido em 17/11/2026 com a rede bloqueada
e uma chave falsa). Aqui a rede para api.anthropic.com é bloqueada em toda a suíte; os testes que simulam a API trocam
o `urlopen` dentro do próprio teste e não são afetados.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

_URLOPEN_ORIGINAL = urllib.request.urlopen


def _urlopen_sem_anthropic(req, *args, **kwargs):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "anthropic.com" in url:
        raise urllib.error.URLError("rede para a API da Anthropic bloqueada nos testes")
    return _URLOPEN_ORIGINAL(req, *args, **kwargs)


@pytest.fixture(autouse=True)
def _sem_chamada_paga(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_sem_anthropic)
    yield
