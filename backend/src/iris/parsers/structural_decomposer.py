"""Módulo de decomposição estrutural automática de materiais didáticos (História 1.1.2 - Issue #5 / RF-02).

Identifica e separa deterministicamente:
- Cabeçalhos institucionais e informações contextuais;
- Textos-base e textos de apoio (individuais e compartilhados);
- Enunciados ou comandos das questões;
- Alternativas de resposta (múltipla escolha);
- Linhas e espaços reservados para respostas;
- Vínculo relacional entre textos de apoio compartilhados e suas respectivas questões.

Garantias inegociáveis:
- 100% determinístico (sem uso de IA generativa para reescrever ou inventar);
- Preservação estrita da ordem e numeração original;
- Zero perda de conteúdo (todo trecho não classificado permanece em `unclassified_blocks`).
"""
from __future__ import annotations

import re
from typing import Any, Final, Optional

from iris.parsers.prose_organizer import organize_prose_structure
from iris.schemas.materials import (
    AlternativeItem,
    ContextBlock,
    MaterialStructure,
    QuestionItem,
)

# ==============================================================================
# Expressões Regulares de Detecção Estrutural
# ==============================================================================

# Marcador de Início de Questão
RE_QUESTION_MARKER = re.compile(
    r"(?im)^[ \t]*(?:"
    r"((?:quest[aã]o|atividade|exerc[ií]cio|item)\s+(\d{1,3}|[ivxlcdm]+))\s*[:.\-–)]?"
    r"|"
    r"((?:q)\.?\s*(\d{1,3}))\s*[:.\-–)]?"
    r"|"
    r"((\d{1,3})\s*(?:º|ª|\.º|\.ª)?\s*([.\-–)]))"
    r")[ \t]+",
)

# Marcador de Início de Texto de Apoio / Leitura Compartilhada
RE_CONTEXT_MARKER = re.compile(
    r"(?im)^[ \t]*(?:"
    r"(?:leia\s+o\s+texto\s+(?:abaixo|a\s+seguir)?\s*(?:para|e)\s*responder\s+[àa]s\s+quest[oõ]es\s+(?:de\s+)?(\d{1,3})\s*(?:a|e|à|-|at[eé])\s*(\d{1,3}))"
    r"|"
    r"(?:as\s+quest[oõ]es\s+(?:de\s+)?(\d{1,3})\s*(?:a|e|à|-|at[eé])\s*(\d{1,3})\s+referem-se\s+ao\s+texto)"
    r"|"
    r"(?:texto\s+(?:para\s+[àa]s\s+quest[oõ]es|referente\s+[àa]s\s+quest[oõ]es)\s+(\d{1,3}(?:\s*(?:e|,)\s*\d{1,3})+))"
    r"|"
    r"(?:texto\s+(?:para\s+a\s+quest[aã]o|referente\s+[aà]\s+quest[aã]o)\s+(\d{1,3}))"
    r"|"
    r"(?:texto\s*[-–]?\s*base|texto\s+de\s+apoio|texto\s+\d+\b|texto\s+[a-z](?=\s*(?:[:.\-–]|$)))\s*[:.\-–]?"
    r")",
)

# Extração de Intervalos de Questões Alvo (ex.: "questões de 1 a 3")
RE_TARGET_RANGE = re.compile(
    r"(?i)(?:quest[oõ]es|itens)\s+(?:de\s+)?(\d{1,3})\s*(?:a|à|-|at[eé])\s*(\d{1,3})",
)

# Extração de Lista de Questões Alvo (ex.: "questões 1, 2 e 3")
RE_TARGET_LIST = re.compile(
    r"(?i)(?:quest[oõ]es|itens)\s+(\d{1,3}(?:\s*(?:,|e|ou)\s*\d{1,3})+)",
)

# Extração de Questão Alvo Única (ex.: "texto para a questão 4")
RE_TARGET_SINGLE = re.compile(
    r"(?i)(?:quest[aã]o|item)\s+(\d{1,3})",
)

# Linhas de Alternativa (Múltipla Escolha): a), A), a., A., 1) a, [A], (A)
RE_OPTION_LINE = re.compile(
    r"(?im)^[ \t]*(?:\(([a-eA-E])\)|([a-eA-E])\s*[.\-–)]|\[([a-eA-E])\])[ \t]+(.*)$"
)

# Alternativas inline na mesma linha: (A) Opção 1  (B) Opção 2... ou A) ... B) ...
RE_INLINE_OPTIONS = re.compile(
    r"(?:[ \t]*(?:\(([A-Ea-e])\)|([A-Ea-e])\s*[.\-–)]|\[([A-Ea-e])\])[ \t]+(.*?)(?=[ \t]+(?:\([A-Ea-e]\)|[A-Ea-e]\s*[.\-–)]|\[[A-Ea-e]\])|$))"
)

# Espaços e Linhas de Resposta Dissertativa
RE_ANSWER_SPACE_LINE = re.compile(
    r"(?im)^[ \t]*(?:"
    r"_{3,}"
    r"|\.{4,}"
    r"|\(\s{3,}\)"
    r"|\[\s{3,}\]"
    r"|(?:resposta|r|justificativa|justifique|solu[cç][aã]o|c[aá]lculo|espa[cç]o(?:\s+para\s+\w+)?)\s*[:.\-–]\s*(?:_{2,}|\.{2,})?"
    r"|.*?[ \t]+_{3,}"
    r").*$"
)

# Indicadores de Cabeçalho / Instruções
RE_HEADER_INDICATORS = re.compile(
    r"(?i)\b(?:escola|col[eé]gio|instituto|aluno|aluna|estudante|discente|professor|professora|"
    r"turma|ano|bimestre|trimestre|data|disciplina|avalia[cç][aã]o|prova|teste|simulado|instru[cç][oõ]es|orienta[cç][oõ]es)\b"
)


# Título de bloco de instruções gerais (ex.: "Instruções:", "Orientações gerais")
RE_INSTRUCTIONS_HEADING = re.compile(
    r"(?i)^[ \t]*(?:instru[cç][oõ]es|orienta[cç][oõ]es)(?:\s+gerais)?\s*[:.\-–]?\s*$"
)

# Lacuna de preenchimento (três ou mais sublinhados)
RE_GAP = re.compile(r"_{3,}")


def _is_fill_in_the_blank(line: str) -> bool:
    """Distingue enunciado com lacuna ("O Brasil foi descoberto em ____.") de rótulo com linha ("Nome: ____")."""
    before = RE_GAP.split(line.strip(), maxsplit=1)[0].strip()
    if not before or before.endswith(":"):
        return False
    return len(before.split()) >= 3


def _extract_target_questions(text: str) -> list[str]:
    """Extrai os números das questões vinculadas a uma diretiva de texto de apoio."""
    m_range = RE_TARGET_RANGE.search(text)
    if m_range:
        try:
            start, end = int(m_range.group(1)), int(m_range.group(2))
            if start <= end and (end - start) < 50:
                return [str(n) for n in range(start, end + 1)]
        except ValueError:
            pass

    m_list = RE_TARGET_LIST.search(text)
    if m_list:
        nums = re.findall(r"\d{1,3}", m_list.group(1))
        if nums:
            return nums

    m_single = RE_TARGET_SINGLE.search(text)
    if m_single:
        return [m_single.group(1)]

    return []


def _parse_question_body(
    original_number: str,
    body_text: str,
    raw_block: str,
    index: int,
) -> tuple[QuestionItem, Optional[str]]:
    """Decompõe o corpo de uma questão em enunciado, alternativas e linhas de resposta.

    Retorna também o trecho que aparece depois das alternativas sem pertencer a elas
    (separado por linha em branco), para que seja preservado em `unclassified_blocks`.
    """
    lines = body_text.split("\n")
    statement_lines: list[str] = []
    options: list[AlternativeItem] = []
    answer_space_lines: list[str] = []

    trailing_lines: list[str] = []

    in_options = False
    options_closed = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_options:
                # Linha em branco encerra a continuação da última alternativa
                options_closed = True
            elif not answer_space_lines:
                statement_lines.append("")
            continue

        # Verifica se a linha contém múltiplas alternativas inline (ex: (A) Opção 1  (B) Opção 2)
        inline_matches = list(RE_INLINE_OPTIONS.finditer(line))
        if len(inline_matches) >= 2:
            prefix = line[:inline_matches[0].start()].strip()
            if prefix:
                statement_lines.append(prefix)
            in_options = True
            options_closed = False
            for m in inline_matches:
                let = (m.group(1) or m.group(2) or m.group(3)).upper()
                opt_txt = m.group(4).strip()
                options.append(AlternativeItem(letter=let, text=opt_txt))
            continue

        # Verifica se é uma linha de alternativa individual
        m_opt = RE_OPTION_LINE.match(line)
        if m_opt:
            in_options = True
            options_closed = False
            letter = (m_opt.group(1) or m_opt.group(2) or m_opt.group(3)).upper()
            text = m_opt.group(4).strip()
            options.append(AlternativeItem(letter=letter, text=text))
            continue

        # Verifica se é uma linha de espaço de resposta
        if RE_ANSWER_SPACE_LINE.match(line) and not _is_fill_in_the_blank(line):
            in_options = False
            answer_space_lines.append(stripped)
            continue

        # Linha normal ou continuação
        if in_options and options_closed:
            # Texto após as alternativas, separado por linha em branco: não pertence à última alternativa
            trailing_lines.append(stripped)
        elif in_options:
            # Continuação da alternativa anterior (ex.: parágrafo longo de opção)
            if options:
                options[-1].text += " " + stripped
            else:
                statement_lines.append(line)
        else:
            statement_lines.append(line)

    # Fallback para alternativas inline quando não houver alternativas em linhas separadas
    if not options:
        inline_matches = list(RE_INLINE_OPTIONS.finditer(body_text))
        # Verifica se há ao menos 2 letras consecutivas (ex: A, B ou A, B, C...)
        if len(inline_matches) >= 2:
            letters = [(m.group(1) or m.group(2) or m.group(3)).upper() for m in inline_matches]
            # Valida ordenação mínima (A vem antes de B)
            if letters[0] in ("A", "1") and letters[1] in ("B", "2"):
                for m in inline_matches:
                    let = (m.group(1) or m.group(2) or m.group(3)).upper()
                    options.append(AlternativeItem(letter=let, text=m.group(4).strip()))
                # Remove as alternativas inline do enunciado
                first_opt_pos = inline_matches[0].start()
                statement_text = body_text[:first_opt_pos].strip()
                statement_lines = [statement_text]

    statement = "\n".join(statement_lines).strip()
    answer_space = "\n".join(answer_space_lines).strip() if answer_space_lines else None

    # Classificação do tipo da questão
    if len(options) >= 2 and answer_space:
        question_type = "mista"
    elif len(options) >= 2:
        question_type = "multipla_escolha"
    else:
        question_type = "dissertativa"

    question = QuestionItem(
        id=f"q_{index}",
        original_number=original_number,
        statement=statement,
        question_type=question_type,
        options=options,
        answer_space=answer_space,
        context_refs=[],
        raw_text=raw_block.strip(),
    )
    return question, ("\n".join(trailing_lines) if trailing_lines else None)


def _parse_context_block(block_text: str, index: int) -> ContextBlock:
    """Decompõe um bloco de texto de apoio em título, diretiva e conteúdo."""
    raw_lines = block_text.split("\n")
    lines = [l.strip() for l in raw_lines if l.strip()]
    if not lines:
        return ContextBlock(id=f"ctx_{index}", text="")

    instruction: Optional[str] = None
    title: Optional[str] = None
    body_start_idx = 0

    # Verifica primeira linha
    first_line = lines[0]
    targets = _extract_target_questions(first_line)
    if targets or "leia" in first_line.lower() or "referem-se" in first_line.lower():
        instruction = first_line
        body_start_idx = 1
        # Verifica se a segunda linha é um título (ex: "Texto 1: A Célula")
        if len(lines) > 1 and re.match(r"(?i)^(?:texto\s*\d*|título|artigo)\b", lines[1]):
            title = lines[1]
            body_start_idx = 2
    elif re.match(r"(?i)^(?:texto\s*[-–]?\s*base|texto\s+de\s+apoio|texto\s+\d+|texto\s+[a-z])\b", first_line):
        title = first_line
        body_start_idx = 1
        # Verifica se a próxima linha tem uma instrução
        if len(lines) > 1:
            next_targets = _extract_target_questions(lines[1])
            if next_targets:
                instruction = lines[1]
                targets = next_targets
                body_start_idx = 2

    # Se não extraiu targets da diretiva, tenta procurar no título ou primeiras linhas
    if not targets:
        for l in lines[:3]:
            t = _extract_target_questions(l)
            if t:
                targets = t
                if not instruction and ("leia" in l.lower() or "referem-se" in l.lower()):
                    instruction = l
                break

    # Corpo com as quebras de linha originais (parágrafos e estrofes preservados)
    if body_start_idx < len(lines):
        non_empty_positions = [pos for pos, l in enumerate(raw_lines) if l.strip()]
        body_first_line = non_empty_positions[body_start_idx]
        text_body = "\n".join(l.rstrip() for l in raw_lines[body_first_line:]).strip()
    else:
        text_body = block_text.strip()

    return ContextBlock(
        id=f"ctx_{index}",
        title=title,
        text=text_body if text_body else block_text.strip(),
        instruction=instruction,
        target_questions=targets,
    )


def decompose_material(raw_text: str) -> MaterialStructure:
    """Segmenta deterministicamente o material pedagógico bruto em componentes estruturados.

    Args:
        raw_text: Texto integral da atividade didática (colado ou extraído de documento).

    Returns:
        MaterialStructure: Objeto hierárquico contendo cabeçalho, textos de apoio e questões.
    """
    if not raw_text or not raw_text.strip():
        return MaterialStructure(
            header=None,
            instructions=None,
            context_blocks=[],
            questions=[],
            unclassified_blocks=[],
            total_questions=0,
            has_shared_contexts=False,
        )

    # 1. Normalizar quebras de linha
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    # 2. Escanear marcadores estruturais (questões e textos de apoio)
    # Lista de tuplas: (tipo, linha_idx, match, numeração_original)
    markers: list[tuple[str, int, Any, str]] = []
    instruction_idx: set[int] = set()
    in_instructions = False

    for idx, line in enumerate(lines):
        m_c = RE_CONTEXT_MARKER.match(line)
        m_q = RE_QUESTION_MARKER.match(line)

        # Bloco de instruções gerais antes da primeira questão: itens numerados não são questões.
        # O bloco termina em linha em branco, em texto de apoio ou em questão com rótulo ("Questão 1").
        if in_instructions:
            labeled_question = bool(m_q and (m_q.group(1) or m_q.group(3)))
            if not line.strip() or m_c or labeled_question:
                in_instructions = False
            else:
                instruction_idx.add(idx)
                continue
        elif not markers and RE_INSTRUCTIONS_HEADING.match(line):
            in_instructions = True
            instruction_idx.add(idx)
            continue

        if m_c:
            markers.append(("context", idx, m_c, ""))
            continue

        if m_q:
            # Extrai a numeração original da questão
            orig_num = (
                m_q.group(1)
                or (f"Q.{m_q.group(4)}" if m_q.group(3) else None)
                or m_q.group(5)
                or (m_q.group(6) if len(m_q.groups()) >= 6 else None)
                or "1"
            ).strip()
            # Limpa caracteres de pontuação externa redundantes
            orig_num_clean = re.sub(r"[:.\-–)]+$", "", orig_num).strip()
            markers.append(("question", idx, m_q, orig_num_clean))

    # Se nenhum marcador de questão ou contexto for encontrado
    if not markers:
        prose_struct = organize_prose_structure(raw_text)
        return MaterialStructure(
            header=None,
            instructions=None,
            context_blocks=[],
            questions=[],
            unclassified_blocks=[raw_text.strip()] if not prose_struct.root_nodes else [],
            total_questions=0,
            has_shared_contexts=False,
            prose_structure=prose_struct,
        )

    # 3. Isolar Cabeçalho Inicial
    first_marker_line = markers[0][1]
    header_text: Optional[str] = None
    if first_marker_line > 0:
        candidate_header = "\n".join(
            l for pos, l in enumerate(lines[:first_marker_line]) if pos not in instruction_idx
        ).strip()
        if candidate_header:
            header_text = candidate_header

    # 4. Agrupar seções consecutivas
    # Para cada marcador, seu conteúdo vai da linha do marcador até o próximo marcador
    context_blocks: list[ContextBlock] = []
    questions: list[QuestionItem] = []
    unclassified_blocks: list[str] = []
    context_subsequent_questions: dict[str, list[QuestionItem]] = {}
    context_question_offset: dict[str, int] = {}
    current_ctx_id: Optional[str] = None

    q_counter = 1
    ctx_counter = 1

    i = 0
    while i < len(markers):
        mtype, start_idx, match_obj, orig_num = markers[i]
        end_idx = markers[i + 1][1] if i + 1 < len(markers) else len(lines)
        block_lines = lines[start_idx:end_idx]
        block_text = "\n".join(block_lines).strip()

        if mtype == "context":
            # Verifica se o próximo marcador também é um marcador de contexto contíguo
            # (ex: linha 1 instrução, linha 2 título do texto)
            while i + 1 < len(markers) and markers[i + 1][0] == "context" and markers[i + 1][1] <= start_idx + 3:
                i += 1
                end_idx = markers[i + 1][1] if i + 1 < len(markers) else len(lines)
                block_lines = lines[start_idx:end_idx]
                block_text = "\n".join(block_lines).strip()

            cb = _parse_context_block(block_text, ctx_counter)
            context_blocks.append(cb)
            current_ctx_id = cb.id
            context_subsequent_questions[cb.id] = []
            context_question_offset[cb.id] = len(questions)
            ctx_counter += 1

        elif mtype == "question":
            # Extrai o enunciado removendo o prefixo do marcador da primeira linha
            first_line = block_lines[0]
            marker_len = match_obj.end()
            body_first_line = first_line[marker_len:].strip()
            rest_of_body = "\n".join([body_first_line] + block_lines[1:])

            q_item, trailing_text = _parse_question_body(
                original_number=orig_num if orig_num else str(q_counter),
                body_text=rest_of_body,
                raw_block=block_text,
                index=q_counter,
            )
            questions.append(q_item)
            if trailing_text:
                unclassified_blocks.append(trailing_text)
            if current_ctx_id and current_ctx_id in context_subsequent_questions:
                context_subsequent_questions[current_ctx_id].append(q_item)
            q_counter += 1

        else:
            unclassified_blocks.append(block_text)

        i += 1

    # 5. Associação Relacional entre Textos de Apoio e Questões
    # Numeração normalizada (apenas dígitos) de cada questão, na ordem do documento
    question_digits: list[Optional[str]] = []
    for q in questions:
        digits = re.findall(r"\d+", q.original_number)
        question_digits.append(digits[0] if digits else None)

    def _find_target(number: str, offset: int) -> Optional[QuestionItem]:
        """Primeira questão com esse número depois do texto de apoio; se não houver, a mais próxima antes dele."""
        for pos in list(range(offset, len(questions))) + list(range(offset - 1, -1, -1)):
            if question_digits[pos] == number:
                return questions[pos]
        return None

    for cb in context_blocks:
        # Se tem alvos explícitos
        if cb.target_questions:
            for t in cb.target_questions:
                # Numeração pode se repetir entre seções: resolve pela posição do texto de apoio
                target_q = _find_target(t, context_question_offset.get(cb.id, 0))
                if target_q and cb.id not in target_q.context_refs:
                    target_q.context_refs.append(cb.id)
        else:
            # Heurística de proximidade: vincula às questões subsequentes contíguas
            # que ainda não possuam contexto associado
            subsequent_qs = context_subsequent_questions.get(cb.id, [])
            for q in subsequent_qs:
                if not q.context_refs:
                    q.context_refs.append(cb.id)
                    cb.target_questions.append(q.original_number)

    # Se houver textos de apoio compartilhados entre 2 ou mais questões
    has_shared = any(len(cb.target_questions) >= 2 for cb in context_blocks)
    if not has_shared:
        # Verifica se alguma questão compartilha o mesmo contexto
        ref_counts: dict[str, int] = {}
        for q in questions:
            for ref in q.context_refs:
                ref_counts[ref] = ref_counts.get(ref, 0) + 1
        has_shared = any(c >= 2 for c in ref_counts.values())

    prose_struct = organize_prose_structure(raw_text)

    return MaterialStructure(
        header=header_text,
        instructions="\n".join(lines[pos].strip() for pos in sorted(instruction_idx)) or None,
        context_blocks=context_blocks,
        questions=questions,
        unclassified_blocks=unclassified_blocks,
        total_questions=len(questions),
        has_shared_contexts=has_shared,
        prose_structure=prose_struct,
    )
