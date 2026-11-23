"""Orquestra a observação por voz: valida o áudio, transcreve, sanitiza PII e sugere características.

Ordem fixa (RNF-02): o áudio é transcrito localmente, o TEXTO passa pelo sanitizador de PII e só o texto
sanitizado alimenta o mapeador. O áudio e a transcrição bruta não são guardados: vivem apenas nas variáveis desta
chamada. Nada é gravado em disco, banco ou log (RNF-01).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from iris.audio.erros import AudioError
from iris.audio.mapeador import sugerir_caracteristicas
from iris.audio.transcricao import Transcritor, obter_transcritor
from iris.audio.validacao import validar_audio
from iris.config import CATALOGS_DIR
from iris.schemas.catalog import load_all_catalogs, load_official_tdah_catalog
from iris.schemas.portable_profile import detectar_conteudo_clinico
from iris.security.pii_scrubber import sanitize_pedagogical_note

MAX_TEXTO = 5_000
IDIOMA = "pt"
AVISO_CLINICO = (
    "A fala cita termos clínicos (diagnóstico, laudo ou medicação). A Íris trabalha só com o que o aluno faz em "
    "sala: esses termos foram ignorados nas sugestões."
)


def _catalogo(id_catalogo: str | None, diretorio: Path):
    if id_catalogo and id_catalogo.strip():
        todos = load_all_catalogs(diretorio)
        if id_catalogo.strip() not in todos:
            raise AudioError(f"Catálogo funcional '{id_catalogo}' não encontrado.", "CATALOG_NOT_FOUND", 422, "id_catalogo")
        return todos[id_catalogo.strip()]
    return load_official_tdah_catalog(diretorio)


def _sugerir(texto_bruto: str, id_catalogo: str | None, diretorio: Path) -> dict[str, Any]:
    texto, pii = sanitize_pedagogical_note(texto_bruto)
    categorias = sorted({v.categoria for v in detectar_conteudo_clinico(texto, "transcricao")})
    catalogo = _catalogo(id_catalogo, diretorio)
    sugestoes = sugerir_caracteristicas(texto, catalogo)
    avisos = [{"code": "CLINICAL_TERMS_IGNORED", "categorias": categorias, "detail": AVISO_CLINICO}] if categorias else []
    return {
        "status": "ok",
        "transcricao": texto,
        "pii_substituicoes": pii,
        "avisos": avisos,
        "id_catalogo": catalogo.id_catalogo,
        "sugestoes": [s.to_dict() for s in sugestoes],
    }


def transcrever_observacao(
    audio: bytes,
    transcritor: Transcritor | None = None,
    id_catalogo: str | None = None,
    diretorio: Path = CATALOGS_DIR,
) -> dict[str, Any]:
    meta = validar_audio(audio)
    bruto = (transcritor or obter_transcritor()).transcrever(audio, IDIOMA)
    if not bruto or not bruto.strip():
        raise AudioError(
            "Não foi possível entender a fala. Grave de novo, falando mais perto do microfone.", "NO_SPEECH_DETECTED", 422
        )
    resposta = _sugerir(bruto[:MAX_TEXTO], id_catalogo, diretorio)
    resposta["duracao_segundos"] = meta.duracao_segundos
    resposta["formato"] = meta.formato
    return resposta


def sugerir_de_texto(texto: Any, id_catalogo: str | None = None, diretorio: Path = CATALOGS_DIR) -> dict[str, Any]:
    """Mesmo mapeamento para o texto digitado ou corrigido pelo professor (sem áudio)."""
    if not isinstance(texto, str) or not texto.strip():
        raise AudioError("Escreva ou grave a observação.", "EMPTY_TEXT", 422, "texto")
    if len(texto) > MAX_TEXTO:
        raise AudioError(f"A observação passa de {MAX_TEXTO} caracteres.", "TEXT_TOO_LONG", 422, "texto")
    return _sugerir(texto, id_catalogo, diretorio)
