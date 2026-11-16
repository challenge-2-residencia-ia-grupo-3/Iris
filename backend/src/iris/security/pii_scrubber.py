"""Módulo de Sanitização Preventiva de PII (Zero-Retention Scrubber) — RNF-02 / LGPD.

Atende:
- RNF-02: Detecção e descarte irreversível de dados pessoais identificáveis (PII)
  em cabeçalhos de atividades didáticas e anotações docentes.
- RNF-01: Arquitetura Zero-Retention — nenhum mapa, tabela hash ou dicionário de
  reidratação de nomes é criado ou mantido em memória no servidor.
- Substituição por marcadores estruturados: [ESTUDANTE], [ESCOLA], [PROFESSOR], [IDENTIFICADOR], [CPF], [TELEFONE], [EMAIL].
"""
from __future__ import annotations

import re

# Padrões de cabeçalho escolar brasileiro para estudantes (não atravessa quebras de linha)
RE_ESTUDANTE_CABECALHO = re.compile(
    r"(?i)\b(nome\s+do\s+aluno(?:a)?|nome\s+da\s+crian[cç]a|nome\s+do\s+estudante|aluno\(a\)|aluna|aluno|estudante|discente)\s*[:：_–-]+\s*([A-Za-zÀ-ÖØ-öø-ÿ'][A-Za-zÀ-ÖØ-öø-ÿ' ]{1,59})",
)

# Padrões de cabeçalho para professores
RE_PROFESSOR_CABECALHO = re.compile(
    r"(?i)\b(professor\(a\)|professora|professor|prof\.|docente)\s*[:：_–-]+\s*([A-Za-zÀ-ÖØ-öø-ÿ'][A-Za-zÀ-ÖØ-öø-ÿ' ]{1,59})",
)

# Padrões de cabeçalho com rótulo explícito para instituições de ensino
RE_ESCOLA_CABECALHO = re.compile(
    r"(?i)\b(escola\s+municipal|escola\s+estadual|escola\s+particular|escola|col[eé]gio|institui[cç][aã]o|ciep|emef|eeem|ee|instituto)\s*[:：_–-]+\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\-][A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\- ]{2,79})",
)

# Padrões de linha isolada com nome de instituição (ex.: 'Colégio Municipal Paulo Freire' no topo da página)
RE_ESCOLA_LINHA_ISOLADA = re.compile(
    r"(?im)^\s*(col[eé]gio\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\- ]{3,60}|escola\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\- ]{3,60}|instituto\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\- ]{3,60}|ciep\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\- ]{3,60}|emef\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9'\.\- ]{3,60})\s*$",
)

# Padrão genérico de linha de cabeçalho "Nome: Fulano da Silva" (início de linha via multiline)
RE_NOME_GENERICO = re.compile(
    r"(?im)^\s*(nome)\s*[:：_–-]+\s*([A-Za-zÀ-ÖØ-öø-ÿ]{2,}(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]{2,}){1,4})\s*$",
)

# Documentos e identificadores escolares
RE_MATRICULA = re.compile(
    r"(?i)\b(matr[ií]cula|r\.?a\.?|r\.?m\.?)\s*[:：_–-]+\s*([A-Za-z0-9\-]{3,20})",
)
RE_CPF = re.compile(
    r"\b(?:\d{3}\.){2}\d{3}-\d{2}\b",
)
RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
RE_TELEFONE = re.compile(
    r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\s*\d{4}|\d{4})[-.\s]?\d{4}\b",
)


def sanitize_pii(text: str) -> tuple[str, int]:
    """Sanitiza preventivamente o texto de entrada, substituindo dados identificáveis por marcadores.

    Opera sob o princípio Zero-Retention (RNF-02):
    A substituição é estritamente unidirecional e irreversível. Nenhum dicionário
    de de-anonimização é criado ou retido pelo sistema.

    Args:
        text: Texto bruto original da atividade pedagógica.

    Returns:
        tuple[str, int]: (texto_sanitizado, total_substituicoes_realizadas)
    """
    if not text:
        return text, 0

    sanitized = text
    total_replacements = 0

    # 1. Sanitizar CPFs
    sanitized, count = RE_CPF.subn("[CPF]", sanitized)
    total_replacements += count

    # 2. Sanitizar E-mails
    sanitized, count = RE_EMAIL.subn("[EMAIL]", sanitized)
    total_replacements += count

    # 3. Sanitizar Matrículas / RAs (executa antes de telefones para não confundir IDs numéricos)
    def _replace_matricula(match: re.Match[str]) -> str:
        rotulo = match.group(1)
        return f"{rotulo}: [IDENTIFICADOR]"

    sanitized, count = RE_MATRICULA.subn(_replace_matricula, sanitized)
    total_replacements += count

    # 4. Sanitizar Telefones
    def _replace_telefone(match: re.Match[str]) -> str:
        val = match.group(0).strip()
        # Não sanitizar anos comuns de 4 dígitos isolados
        if re.fullmatch(r"(?:19|20)\d{2}", val):
            return val
        return "[TELEFONE]"

    sanitized, count = RE_TELEFONE.subn(_replace_telefone, sanitized)
    total_replacements += count


    # 5. Sanitizar Cabeçalhos de Estudante
    def _replace_estudante(match: re.Match[str]) -> str:
        rotulo = match.group(1)
        return f"{rotulo}: [ESTUDANTE]"

    sanitized, count = RE_ESTUDANTE_CABECALHO.subn(_replace_estudante, sanitized)
    total_replacements += count

    # 6. Sanitizar Cabeçalhos de Professor
    def _replace_professor(match: re.Match[str]) -> str:
        rotulo = match.group(1)
        return f"{rotulo}: [PROFESSOR]"

    sanitized, count = RE_PROFESSOR_CABECALHO.subn(_replace_professor, sanitized)
    total_replacements += count

    # 7. Sanitizar Cabeçalhos com rótulo de Escola
    def _replace_escola(match: re.Match[str]) -> str:
        rotulo = match.group(1)
        return f"{rotulo}: [ESCOLA]"

    sanitized, count = RE_ESCOLA_CABECALHO.subn(_replace_escola, sanitized)
    total_replacements += count

    # 8. Sanitizar Linhas isoladas de Escola
    sanitized, count = RE_ESCOLA_LINHA_ISOLADA.subn("[ESCOLA]", sanitized)
    total_replacements += count

    # 9. Sanitizar 'Nome: Fulano de Tal' isolado em início de linha
    def _replace_nome_generico(match: re.Match[str]) -> str:
        rotulo = match.group(1)
        return f"{rotulo}: [ESTUDANTE]"

    sanitized, count = RE_NOME_GENERICO.subn(_replace_nome_generico, sanitized)
    total_replacements += count

    return sanitized, total_replacements


# Padrão para menções nominais inline em observações pedagógicas livres (ex.: "O aluno Gabriel Silva gosta...")
RE_ALUNO_PROSA = re.compile(
    r"(?<!\[)\b((?:[oa]|d[oa]|a[o]?|pel[oa])\s+(?:aluno|aluna|estudante|discente)|(?:aluno|aluna|estudante|discente))\s+"
    r"([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ']{1,29}(?:\s+(?:(?:da|de|do|das|dos|e)\s+)?[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ']{1,29}){0,3})"
)

# Termos estritamente clínicos/médicos vetados pelo RNF-03 em perfis e observações pedagógicas
RE_CLINICAL_REFERENCE = re.compile(
    r"(?i)\b(?:cid(?:\s*[-:]?\s*(?:10|11|[a-z]\d{2}(?:\.\d+)?))|laudo\s+(?:m[eé]dico|cl[ií]nico|psiqui[aá]trico|neurol[oó]gico)|"
    r"diagn[oó]stico\s+(?:cl[ií]nico|m[eé]dico|formal)|dsm\s*[-:]?\s*(?:iv|v|5)|"
    r"prescri[cç][aã]o\s+m[eé]dica|medica[cç][aã]o|ritalina|venvanse|concerta|metilfenidato|lisdexanfetamina)\b"
)


def sanitize_pedagogical_note(text: str) -> tuple[str, int]:
    """Sanitiza notas pedagógicas livres (ex.: potencialidades e interesses customizados).

    Executa `sanitize_pii` e remove adicionalmente nomes próprios citados após referências
    a estudante/aluno em prosa (ex.: "o aluno Gabriel Silva" -> "o aluno [ESTUDANTE]").
    Mantém o princípio Zero-Retention (RNF-02) sem mapa de reidratação.
    """
    if not text:
        return text, 0

    sanitized, total_replacements = sanitize_pii(text)

    def _replace_prosa(match: re.Match[str]) -> str:
        prefixo = match.group(1)
        return f"{prefixo} [ESTUDANTE]"

    sanitized, inline_count = RE_ALUNO_PROSA.subn(_replace_prosa, sanitized)
    total_replacements += inline_count
    return re.sub(r"\s{2,}", " ", sanitized).strip(), total_replacements


def detect_clinical_reference(text: str) -> str | None:
    """Detecta menções a CID, laudos médicos ou medicações em campos pedagógicos (RNF-03)."""
    if not text:
        return None
    match = RE_CLINICAL_REFERENCE.search(text)
    return match.group(0) if match else None