"""Módulo de organização estrutural automática de textos corridos (História 1.1.4 - Issue #7 / RF-02 Extensão).

Identifica deterministicamente e organiza em árvore hierárquica:
- Títulos e Subtítulos (numerados e não-numerados);
- Seções e Subseções com múltiplos níveis de profundidade;
- Parágrafos de texto corrido associados às respectivas seções;
- Listas agrupadas (ordenadas e com marcadores/bullets) e seus itens individuais;
- Blocos de exercícios/questões e textos de apoio em materiais combinados.

Garantias inegociáveis:
- 100% determinístico (heurísticas e regex, sem IA generativa);
- Preservação estrita da sequência original de ocorrência (campo `order`);
- Zero-loss de conteúdo textual (nenhum trecho descartado ou reescrito);
- Disponibilização estruturada para o motor de adaptação pedagógica (História 2.1.3).
"""
from __future__ import annotations

import re
from typing import Any, Final, Optional

from iris.schemas.materials import ProseStructure, StructuralNode

# ==============================================================================
# Expressões Regulares de Detecção Estrutural de Textos Corridos
# ==============================================================================

# Seções e Subseções com Numeração Decimal (ex.: 1., 1.1, 1.1.1, 1.2.3.4)
RE_NUMERIC_SECTION = re.compile(
    r"^[ \t]*(\d{1,2}(?:\.\d{1,2})+)\s*[:.\-–]?\s+(.+)$"
)

# Seções com Numeração Simples (ex.: 1. Introdução, 2 - Metodologia, 3) Fundamentação)
RE_SINGLE_NUMERIC_SECTION = re.compile(
    r"^[ \t]*(\d{1,2})\s*([.\-–)])\s+([A-ZÀ-Ú0-9].*)$"
)

# Seções Nomeadas Explícitas (ex.: Capítulo 1: A Célula, Seção 2 - O Núcleo, Módulo I)
RE_NAMED_SECTION = re.compile(
    r"(?im)^[ \t]*(?:se[cç][aã]o|cap[ií]tulo|m[oó]dulo|unidade|parte|t[oó]pico)\s+(\d+|[ivxlcdm]+)\s*[:.\-–]?\s*(.*)$"
)

# Seções com Numerais Romanos (ex.: I. Introdução, II - Metodologia)
RE_ROMAN_SECTION = re.compile(
    r"^[ \t]*([IVXLCDM]{1,6})\s*[.\-–]\s+([A-ZÀ-Ú0-9].*)$"
)

# Palavras-chave Tradicionais de Seções e Subtítulos Acadêmico-Pedagógicos
RE_CLASSICAL_HEADING = re.compile(
    r"(?i)^[ \t]*(?:"
    r"introdu[cç][aã]o|"
    r"conclus[aã]o|"
    r"resumo|"
    r"objetivos?(?:\s+gerais?|\s+espec[ií]ficos?)?|"
    r"desenvolvimento|"
    r"fundamenta[cç][aã]o(?:\s+te[oó]rica)?|"
    r"metodologia|"
    r"discuss[aã]o|"
    r"refer[eê]ncias(?:\s+bibliogr[aá]ficas?)?|"
    r"considera[cç][oõ]es\s+finais|"
    r"contextualiza[cç][aã]o|"
    r"revis[aã]o\s+bibliogr[aá]fica|"
    r"aplica[cç][oõ]es(?:\s+pr[aá]ticas)?|"
    r"conceitos\s+b[aá]sicos|"
    r"exerc[ií]cios(?:\s+de\s+fixa[cç][aã]o)?|"
    r"atividades(?:\s+propostas)?|"
    r"quest[oõ]es"
    r")\b\s*[:.\-–]?\s*$"
)

# Marcadores de Lista Não Ordenada (Bullets)
RE_BULLET_ITEM = re.compile(
    r"^[ \t]*([•*–—+⁃▪▫◦\u2022\u25e6]|-)[ \t]+(.+)$"
)

# Marcadores de Lista Ordenada (ex.: 1. Item, 2) Item, a) Item, (1) Item)
RE_ORDERED_ITEM = re.compile(
    r"^[ \t]*(?:(\d{1,2}|[a-zA-Z]|[ivxlcdmIVXLCDM]{1,4})[.)]|\((\d{1,2}|[a-zA-Z])\))[ \t]+(.+)$"
)

# Indicadores de Pergunta / Questão para Desambiguação
RE_QUESTION_INDICATOR = re.compile(
    r"(?i)\?|^(?:calcule|explique|assinale|determine|indique|qual|quais|o\s+que|como|por\s+que|quem|em\s+qual|responda)\b"
)


def _clean_text(text: str) -> str:
    """Remove espaços em branco supérfluos nas extremidades mantendo o conteúdo integral."""
    return text.strip() if text else ""


def _is_question_line(line: str) -> bool:
    """Verifica se a linha é o comando de uma questão de avaliação para evitar falso-positivo com títulos."""
    stripped = line.strip()
    if RE_QUESTION_INDICATOR.search(stripped):
        return True
    if re.match(r"(?im)^[ \t]*(?:quest[aã]o|atividade|exerc[ií]cio|item)\s+\d+", stripped):
        return True
    return False


def _detect_heading(
    line: str,
    is_first_line: bool = False,
    prev_line_empty: bool = True,
    next_line_empty: bool = False,
) -> Optional[tuple[str, int, str, dict[str, Any]]]:
    """Analisa uma linha e retorna (element_type, level, clean_title, metadata) se for título/seção.

    Retorna None caso seja parágrafo normal ou item de lista.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None

    # Se for comando de questão com interrogação ou verbo imperativo, não é título de seção
    if _is_question_line(stripped):
        return None

    # 1. Seções com numeração decimal multi-nível: 1.1, 1.2, 1.1.1, etc.
    m_multi = RE_NUMERIC_SECTION.match(stripped)
    if m_multi:
        num_str = m_multi.group(1)
        title_text = m_multi.group(2).strip()
        parts = num_str.split(".")
        depth = len(parts)
        elem_type = "subsection" if depth >= 2 else "section"
        level = depth + 1  # 1.1 -> level 3; 1.1.1 -> level 4
        return (elem_type, level, stripped, {"number": num_str, "clean_title": title_text})

    # 2. Seções nomeadas: "Capítulo 1: ...", "Seção 2 - ..."
    m_named = RE_NAMED_SECTION.match(stripped)
    if m_named:
        label_num = m_named.group(1)
        title_text = m_named.group(2).strip()
        return ("section", 2, stripped, {"section_label": label_num, "clean_title": title_text})

    # 3. Numerais Romanos: "I. Introdução", "II - ..."
    m_roman = RE_ROMAN_SECTION.match(stripped)
    if m_roman:
        roman_num = m_roman.group(1)
        title_text = m_roman.group(2).strip()
        return ("section", 2, stripped, {"roman": roman_num, "clean_title": title_text})

    # 4. Palavras-chave clássicas de seções (Introdução, Conclusão, etc.)
    if RE_CLASSICAL_HEADING.match(stripped):
        return ("section", 2, stripped, {"is_classical": True})

    # 5. Seção numerada simples: "1. Introdução", "2. Histórico"
    # Diferencia de itens de lista verificando comprimento, ausência de ponto final de frase e capitalização
    m_single = RE_SINGLE_NUMERIC_SECTION.match(stripped)
    if m_single:
        num = m_single.group(1)
        content_after = m_single.group(3).strip()
        # Se for curto e parece título
        if len(content_after) <= 80 and not content_after.endswith((".", ",", ";")):
            return ("section", 2, stripped, {"number": num, "clean_title": content_after})
        # Se contiver termos clássicos de seção
        if any(term in content_after.lower() for term in ("introdução", "conceito", "histórico", "fundamento", "aspecto", "característica")):
            return ("section", 2, stripped, {"number": num, "clean_title": content_after})

    # 6. Título Principal na primeira posição do documento
    if is_first_line and len(stripped) <= 90 and not stripped.endswith((".", ",", ";", ":")):
        words = stripped.split()
        if len(words) <= 12 and (stripped.isupper() or stripped.istitle() or words[0][0].isupper()):
            return ("title", 1, stripped, {"is_document_title": True})

    # 7. Subtítulo / Seção em Title Case ou ALL CAPS isolado por linhas em branco
    if prev_line_empty and (next_line_empty or len(stripped) <= 60):
        words = stripped.split()
        if len(words) <= 12 and not stripped.endswith((".", ",", ";", "!", "?")):
            if stripped.isupper() and len(stripped) >= 3:
                return ("section", 2, stripped, {"is_all_caps": True})
            cap_words = [w for w in words if w[0].isupper()]
            if len(cap_words) >= max(1, int(len(words) * 0.5)):
                elem = "title" if is_first_line else "subtitle"
                lvl = 1 if is_first_line else 2
                return (elem, lvl, stripped, {"is_title_case": True})

    # 8. Linhas explícitas com marcadores Markdown de cabeçalho (#, ##, ###)
    m_md = re.match(r"^(#{1,6})\s+(.+)$", stripped)
    if m_md:
        hashes = len(m_md.group(1))
        md_text = m_md.group(2).strip()
        elem = "title" if hashes == 1 else ("section" if hashes == 2 else "subsection")
        return (elem, hashes, md_text, {"markdown_level": hashes})

    return None


def organize_prose_structure(raw_text: str) -> ProseStructure:
    """Segmenta e organiza deterministicamente um texto corrido em árvore hierárquica.

    Args:
        raw_text: Conteúdo textual completo do material didático (artigo, capítulo, apostila).

    Returns:
        ProseStructure: Estrutura em árvore de nós contendo títulos, seções, subseções,
                       parágrafos e listas agrupadas.
    """
    if not raw_text or not raw_text.strip():
        return ProseStructure(
            title=None,
            root_nodes=[],
            total_elements=0,
            max_depth=0,
        )

    # 1. Normalização de quebras de linha
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = normalized.split("\n")

    # 2. Varredura preliminar para agrupar em unidades estruturais (Headings, List Items, Paragraphs)
    # Tuplas: (tipo_preliminar, texto, level_se_heading, metadata)
    units: list[dict[str, Any]] = []
    total_lines = len(raw_lines)

    idx = 0
    while idx < total_lines:
        line = raw_lines[idx]
        stripped = line.strip()

        if not stripped:
            idx += 1
            continue

        prev_empty = (idx == 0) or (not raw_lines[idx - 1].strip())
        next_empty = (idx + 1 >= total_lines) or (not raw_lines[idx + 1].strip())
        is_first = (len(units) == 0)

        # A. Verifica se é Título ou Seção
        heading_info = _detect_heading(
            line,
            is_first_line=is_first,
            prev_line_empty=prev_empty,
            next_line_empty=next_empty,
        )
        if heading_info:
            elem_type, level, clean_title, meta = heading_info
            units.append({
                "kind": "heading",
                "element_type": elem_type,
                "level": level,
                "content": clean_title,
                "metadata": meta,
            })
            idx += 1
            continue

        # B. Verifica se é Item de Lista (Marcador com Bullet)
        m_bullet = RE_BULLET_ITEM.match(line)
        if m_bullet:
            bullet_char = m_bullet.group(1)
            item_text = m_bullet.group(2).strip()
            units.append({
                "kind": "list_item",
                "element_type": "list_item",
                "content": item_text,
                "metadata": {"list_type": "unordered", "marker": bullet_char},
            })
            idx += 1
            continue

        # C. Verifica se é Item de Lista Ordenada (ex.: 1. Passo A, 2. Passo B)
        # Requer que seja precedido ou sucedido por outro item de lista ou dois pontos
        m_ord = RE_ORDERED_ITEM.match(line)
        if m_ord:
            marker_str = m_ord.group(1) or m_ord.group(2)
            ord_text = m_ord.group(3).strip()
            # Valida se a próxima linha ou a anterior também é um item de lista ordenada
            is_in_ordered_list = False
            if idx > 0 and raw_lines[idx - 1].strip().endswith(":"):
                is_in_ordered_list = True
            elif idx + 1 < total_lines and RE_ORDERED_ITEM.match(raw_lines[idx + 1].strip()):
                is_in_ordered_list = True
            elif idx > 0 and RE_ORDERED_ITEM.match(raw_lines[idx - 1].strip()):
                is_in_ordered_list = True
            elif len(units) > 0 and units[-1]["kind"] == "list_item":
                is_in_ordered_list = True

            if is_in_ordered_list and not _is_question_line(line):
                units.append({
                    "kind": "list_item",
                    "element_type": "list_item",
                    "content": ord_text,
                    "metadata": {"list_type": "ordered", "marker": marker_str},
                })
                idx += 1
                continue

        # D. Bloco de Parágrafo Normal
        # Agrupa linhas contínuas até encontrar linha vazia ou início de heading/lista
        para_lines = [stripped]
        idx += 1
        while idx < total_lines:
            next_l = raw_lines[idx]
            next_str = next_l.strip()
            if not next_str:
                break
            # Verifica se a próxima linha inicia uma nova estrutura
            if RE_BULLET_ITEM.match(next_l) or _detect_heading(next_l, False, False, False):
                break
            if RE_ORDERED_ITEM.match(next_l) and idx + 1 < total_lines and RE_ORDERED_ITEM.match(raw_lines[idx + 1].strip()):
                break
            para_lines.append(next_str)
            idx += 1

        units.append({
            "kind": "paragraph",
            "element_type": "paragraph",
            "content": " ".join(para_lines),
            "metadata": {},
        })

    # 3. Agrupamento de Listas e Construção dos Nós Estruturais
    # Agrupa múltiplos 'list_item' consecutivos em um elemento 'list' composto
    raw_nodes_plan: list[dict[str, Any]] = []
    u_idx = 0
    while u_idx < len(units):
        u = units[u_idx]
        if u["kind"] == "list_item":
            # Coleta todos os itens de lista consecutivos
            list_items: list[dict[str, Any]] = []
            while u_idx < len(units) and units[u_idx]["kind"] == "list_item":
                list_items.append(units[u_idx])
                u_idx += 1

            list_type = list_items[0]["metadata"].get("list_type", "unordered")
            list_content = "\n".join([f"- {it['content']}" for it in list_items])
            raw_nodes_plan.append({
                "kind": "list_container",
                "element_type": "list",
                "content": list_content,
                "metadata": {"list_type": list_type, "item_count": len(list_items)},
                "items": list_items,
            })
        else:
            raw_nodes_plan.append(u)
            u_idx += 1

    # 4. Construção da Árvore Hierárquica com Pilha de Contexto Ativo
    root_nodes: list[StructuralNode] = []
    # Pilha armazena tuplas: (nível_hierárquico, nó_pai)
    heading_stack: list[tuple[int, StructuralNode]] = []

    node_counter = 1
    max_depth_observed = 1
    doc_title: Optional[str] = None

    for plan in raw_nodes_plan:
        ptype = plan["element_type"]
        pcontent = plan["content"]
        pmeta = plan.get("metadata", {})

        if plan["kind"] == "heading":
            req_level = plan.get("level", 2)
            if ptype == "title":
                req_level = 1
                if not doc_title:
                    doc_title = pcontent

            # Desempilha cabeçalhos de mesmo nível ou mais profundos
            while heading_stack and heading_stack[-1][0] >= req_level:
                heading_stack.pop()

            parent = heading_stack[-1][1] if heading_stack else None
            node = StructuralNode(
                id=f"node_{node_counter}",
                element_type=ptype,
                content=pcontent,
                order=node_counter,
                level=req_level,
                parent_id=parent.id if parent else None,
                children=[],
                metadata=pmeta,
            )
            node_counter += 1

            if req_level > max_depth_observed:
                max_depth_observed = req_level

            if parent:
                parent.children.append(node)
            else:
                root_nodes.append(node)

            heading_stack.append((req_level, node))

        elif plan["kind"] == "list_container":
            # Lista associada à seção ativa ou raiz
            parent = heading_stack[-1][1] if heading_stack else None
            list_level = (parent.level + 1) if parent and parent.level else 2

            list_node = StructuralNode(
                id=f"list_{node_counter}",
                element_type="list",
                content=pcontent,
                order=node_counter,
                level=list_level,
                parent_id=parent.id if parent else None,
                children=[],
                metadata=pmeta,
            )
            node_counter += 1

            if list_level > max_depth_observed:
                max_depth_observed = list_level

            if parent:
                parent.children.append(list_node)
            else:
                root_nodes.append(list_node)

            # Adiciona os itens filhos da lista
            for it in plan.get("items", []):
                item_node = StructuralNode(
                    id=f"item_{node_counter}",
                    element_type="list_item",
                    content=it["content"],
                    order=node_counter,
                    level=list_level + 1,
                    parent_id=list_node.id,
                    children=[],
                    metadata=it.get("metadata", {}),
                )
                node_counter += 1
                list_node.children.append(item_node)
                if (list_level + 1) > max_depth_observed:
                    max_depth_observed = list_level + 1

        else:
            # Parágrafo normal
            parent = heading_stack[-1][1] if heading_stack else None
            p_level = (parent.level + 1) if parent and parent.level else 2

            p_node = StructuralNode(
                id=f"p_{node_counter}",
                element_type="paragraph",
                content=pcontent,
                order=node_counter,
                level=p_level,
                parent_id=parent.id if parent else None,
                children=[],
                metadata=pmeta,
            )
            node_counter += 1

            if p_level > max_depth_observed:
                max_depth_observed = p_level

            if parent:
                parent.children.append(p_node)
            else:
                root_nodes.append(p_node)

    # Se não identificou título explícito mas há um root node de seção/heading no topo
    if not doc_title and root_nodes:
        first = root_nodes[0]
        if first.element_type in ("title", "section"):
            doc_title = first.content

    total_count = node_counter - 1

    return ProseStructure(
        title=doc_title,
        root_nodes=root_nodes,
        total_elements=total_count,
        max_depth=max_depth_observed,
    )
