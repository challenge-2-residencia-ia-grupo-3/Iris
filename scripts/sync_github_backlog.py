#!/usr/bin/env python3
"""
Script de Automação do Backlog no GitHub (Labels + Temas + Épicos + Histórias + Sub-issues).
Repositório: challenge-2-residencia-ia-grupo-3/Iris

Funcionalidades:
1. Cria ou atualiza todas as Labels padronizadas (type, priority, scope) no GitHub.
2. Cria as Issues de Nível 1 (Temas 1 a 4).
3. Cria as Issues de Nível 2 (Épicos 1.1 a 4.2) e vincula como Sub-issues dos Temas.
4. Cria as Issues de Nível 3 (Histórias 1.1.1 a 4.2.2) no template BDD/Gherkin com Requisitos Base,
   aplica as Labels correspondentes e vincula como Sub-issues dos Épicos.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "challenge-2-residencia-ia-grupo-3"
REPO = "Iris"
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
GRAPHQL_URL = "https://api.github.com/graphql"

# ============================================================================
# 1. DEFINIÇÃO DAS LABELS APROVADAS
# ============================================================================
LABELS = [
    # Tipo (Hierarquia)
    {"name": "type: theme", "color": "0D0221", "description": "Tema estratégico macro do produto (Nível 1)"},
    {"name": "type: epic", "color": "6F42C1", "description": "Épico funcional agrupador de histórias (Nível 2 - Sub-issue de Tema)"},
    {"name": "type: story", "color": "1A7F37", "description": "História de Usuário com critérios BDD (Nível 3 - Sub-issue de Épico)"},
    # Prioridade (MoSCoW)
    {"name": "priority: must", "color": "B60205", "description": "Crítico e obrigatório para o MVP e regras inegociáveis"},
    {"name": "priority: should", "color": "FBCA04", "description": "Importante para completude pedagógica e multimodalidade"},
    {"name": "priority: could", "color": "0E8A16", "description": "Desejável para refinamento de experiência e extensões"},
    # Escopo Técnico (Arquitetura Íris)
    {"name": "scope: front-web", "color": "D97706", "description": "Interface web docente (WCAG 2.1 AA, fluxo de 5 etapas, editor lado a lado)"},
    {"name": "scope: api", "color": "4F46E5", "description": "Backend FastAPI, rotas stateless, parsers de documentos e exportação"},
    {"name": "scope: rag", "color": "0891B2", "description": "Base de conhecimento científica (DUA/MEC), chunking e busca vetorial"},
    {"name": "scope: agents", "color": "335C67", "description": "Sistema multiagentes, prompts, isolamento de escopo e auditoria"},
    {"name": "scope: privacy-lgpd", "color": "059669", "description": "Sanitizador local de PII, Zero-Database e Perfil Pedagógico Portátil"},
    {"name": "scope: infra-eval", "color": "E35336", "description": "Infraestrutura UV, CI/CD, testes e métricas objetivas (TRCC, Flesch, RAGAS)"},
]

# Mapeamento de metadados (Prioridade e Escopo) por código de História
STORY_METADATA = {
    "1.1.1": {"priority": "priority: must", "scopes": ["scope: front-web", "scope: api"]},
    "1.1.2": {"priority": "priority: must", "scopes": ["scope: api", "scope: agents"]},
    "1.1.3": {"priority": "priority: should", "scopes": ["scope: agents", "scope: api"]},
    "1.2.1": {"priority": "priority: must", "scopes": ["scope: front-web", "scope: api"]},
    "1.2.2": {"priority": "priority: should", "scopes": ["scope: front-web", "scope: api"]},
    "1.2.3": {"priority": "priority: could", "scopes": ["scope: agents", "scope: api"]},
    "1.3.1": {"priority": "priority: must", "scopes": ["scope: front-web", "scope: agents"]},
    "1.3.2": {"priority": "priority: must", "scopes": ["scope: front-web", "scope: agents"]},
    "2.1.1": {"priority": "priority: must", "scopes": ["scope: rag"]},
    "2.1.2": {"priority": "priority: must", "scopes": ["scope: agents"]},
    "2.1.3": {"priority": "priority: must", "scopes": ["scope: agents", "scope: rag"]},
    "2.1.4": {"priority": "priority: must", "scopes": ["scope: agents", "scope: infra-eval"]},
    "2.2.1": {"priority": "priority: must", "scopes": ["scope: front-web"]},
    "2.2.2": {"priority": "priority: must", "scopes": ["scope: front-web", "scope: api"]},
    "2.2.3": {"priority": "priority: must", "scopes": ["scope: api", "scope: front-web"]},
    "3.1.1": {"priority": "priority: should", "scopes": ["scope: privacy-lgpd", "scope: api"]},
    "3.1.2": {"priority": "priority: should", "scopes": ["scope: privacy-lgpd", "scope: front-web"]},
    "3.1.3": {"priority": "priority: must", "scopes": ["scope: privacy-lgpd", "scope: api"]},
    "3.2.1": {"priority": "priority: should", "scopes": ["scope: privacy-lgpd", "scope: api"]},
    "3.2.2": {"priority": "priority: should", "scopes": ["scope: privacy-lgpd", "scope: front-web"]},
    "4.1.1": {"priority": "priority: must", "scopes": ["scope: privacy-lgpd", "scope: api"]},
    "4.1.2": {"priority": "priority: must", "scopes": ["scope: privacy-lgpd", "scope: infra-eval"]},
    "4.1.3": {"priority": "priority: could", "scopes": ["scope: privacy-lgpd", "scope: front-web"]},
    "4.1.4": {"priority": "priority: must", "scopes": ["scope: privacy-lgpd", "scope: infra-eval"]},
    "4.2.1": {"priority": "priority: must", "scopes": ["scope: rag", "scope: api"]},
    "4.2.2": {"priority": "priority: must", "scopes": ["scope: infra-eval", "scope: rag"]},
}


def get_github_token() -> str:
    """Obtém o token do GitHub da variável de ambiente ou do git credential helper."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            capture_output=True,
            check=True,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass

    print("ERRO: Token do GitHub não encontrado.", file=sys.stderr)
    print("Defina GITHUB_TOKEN='seu_token' antes de rodar o script.", file=sys.stderr)
    sys.exit(1)


def github_request(method: str, url: str, token: str, data: dict | None = None, extra_headers: dict | None = None) -> dict:
    """Executa requisição HTTP para a API do GitHub."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Iris-Backlog-Sync",
    }
    if extra_headers:
        headers.update(extra_headers)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} em {method} {url}: {err_body}") from e


def sync_labels(token: str) -> None:
    """Cria ou atualiza todas as labels do projeto no GitHub."""
    print("=== 1. Sincronizando Labels ===")
    existing = github_request("GET", f"{API_BASE}/labels?per_page=100", token)
    existing_names = {lbl["name"].lower(): lbl["name"] for lbl in existing}

    for lbl in LABELS:
        name = lbl["name"]
        payload = {
            "name": name,
            "color": lbl["color"],
            "description": lbl["description"],
        }
        if name.lower() in existing_names:
            encoded = urllib.parse.quote(existing_names[name.lower()], safe="")
            github_request("PATCH", f"{API_BASE}/labels/{encoded}", token, payload)
            print(f"  [ATUALIZADA] {name} (#{lbl['color']})")
        else:
            github_request("POST", f"{API_BASE}/labels", token, payload)
            print(f"  [CRIADA]     {name} (#{lbl['color']})")


def parse_backlog_markdown(md_path: Path) -> list[dict]:
    """Lê docs/backlog_rastreabilidade.md e extrai a árvore de Temas -> Épicos -> Histórias."""
    content = md_path.read_text(encoding="utf-8")
    spec_section = content.split("## 3. Especificação Completa das Issues", 1)[1]

    themes: list[dict] = []
    current_theme = None
    current_epic = None

    # Divide por cabeçalhos de nível 3, 4 e 5
    pattern = re.compile(r"^(#{3,5})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(spec_section))

    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_section)
        block_body = spec_section[start:end].strip()
        # Remove separadores markdown finais
        block_body = re.sub(r"\n---\s*$", "", block_body).strip()

        if level == 3 and title.startswith("Tema "):
            theme_code = title.split(":", 1)[0].strip()  # "Tema 1"
            current_theme = {
                "code": theme_code,
                "title": title,
                "body": block_body,
                "epics": [],
            }
            themes.append(current_theme)
        elif level == 4 and title.startswith("Épico "):
            epic_code = title.split(":", 1)[0].strip()  # "Épico 1.1"
            current_epic = {
                "code": epic_code,
                "title": title,
                "body": block_body,
                "stories": [],
            }
            if current_theme is not None:
                current_theme["epics"].append(current_epic)
        elif level == 5 and title.startswith("História "):
            story_id = title.split(":", 1)[0].replace("História ", "").strip()  # "1.1.1"
            if current_epic is not None:
                current_epic["stories"].append(
                    {
                        "id": story_id,
                        "title": title,
                        "body": block_body,
                    }
                )

    return themes


def link_sub_issue_graphql(token: str, parent_node_id: str, child_node_id: str) -> bool:
    """Vincula uma issue filha a uma issue pai usando a API nativa de Sub-issues do GitHub."""
    query = """
    mutation AddSubIssue($parentId: ID!, $subIssueId: ID!) {
      addSubIssue(input: {issueId: $parentId, subIssueId: $subIssueId}) {
        issue { id }
        subIssue { id }
      }
    }
    """
    try:
        res = github_request(
            "POST",
            GRAPHQL_URL,
            token,
            {"query": query, "variables": {"parentId": parent_node_id, "subIssueId": child_node_id}},
            extra_headers={"GraphQL-Features": "sub_issues"},
        )
        return "errors" not in res
    except Exception as e:
        print(f"    [Aviso GraphQL Sub-issue]: {e}")
        return False


def get_existing_issues(token: str) -> dict[str, dict]:
    """Retorna um dicionário {titulo: issue_obj} de todas as issues abertas do repositório."""
    issues_map = {}
    page = 1
    while True:
        items = github_request("GET", f"{API_BASE}/issues?state=all&per_page=100&page={page}", token)
        if not items:
            break
        for it in items:
            if "pull_request" not in it:
                issues_map[it["title"].strip()] = it
        page += 1
    return issues_map


def create_or_get_issue(token: str, existing_map: dict, title: str, body: str, labels: list[str]) -> dict:
    """Cria uma issue se não existir, ou atualiza suas labels se já existir."""
    if title in existing_map:
        issue = existing_map[title]
        github_request("PATCH", f"{API_BASE}/issues/{issue['number']}", token, {"body": body, "labels": labels})
        print(f"  [EXISTENTE #{issue['number']}] {title}")
        return issue

    issue = github_request(
        "POST",
        f"{API_BASE}/issues",
        token,
        {"title": title, "body": body, "labels": labels},
    )
    print(f"  [CRIADA    #{issue['number']}] {title}")
    time.sleep(0.6)  # Evita rate-limit secundário do GitHub
    return issue


def sync_issues(token: str, themes: list[dict]) -> None:
    """Cria Temas, Épicos e Histórias e constrói os vínculos de Sub-issues."""
    print("\n=== 2. Sincronizando Issues e Hierarquia (Tema -> Épico -> História) ===")
    existing_map = get_existing_issues(token)

    for theme in themes:
        theme_issue = create_or_get_issue(
            token,
            existing_map,
            theme["title"],
            theme["body"],
            labels=["type: theme"],
        )
        epic_numbers = []

        for epic in theme["epics"]:
            epic_body_with_parent = f"**Tema Pai:** #{theme_issue['number']}\n\n{epic['body']}"
            epic_issue = create_or_get_issue(
                token,
                existing_map,
                epic["title"],
                epic_body_with_parent,
                labels=["type: epic"],
            )
            epic_numbers.append(epic_issue["number"])

            # Vincula Épico como Sub-issue do Tema
            link_sub_issue_graphql(token, theme_issue["node_id"], epic_issue["node_id"])

            story_numbers = []
            for story in epic["stories"]:
                meta = STORY_METADATA.get(story["id"], {"priority": "priority: must", "scopes": ["scope: api"]})
                story_labels = ["type: story", meta["priority"]] + meta["scopes"]
                story_body_with_parent = f"**Épico Pai:** #{epic_issue['number']} ({epic['code']})\n\n{story['body']}"

                story_issue = create_or_get_issue(
                    token,
                    existing_map,
                    story["title"],
                    story_body_with_parent,
                    labels=story_labels,
                )
                story_numbers.append((story_issue["number"], story["title"]))

                # Vincula História como Sub-issue do Épico
                link_sub_issue_graphql(token, epic_issue["node_id"], story_issue["node_id"])

            # Atualiza corpo do Épico com checklist de Histórias filhas
            checklist_stories = "\n".join([f"- [ ] #{num} — {t}" for num, t in story_numbers])
            updated_epic_body = f"{epic_body_with_parent}\n\n### Histórias de Usuário Vinculadas\n{checklist_stories}"
            github_request("PATCH", f"{API_BASE}/issues/{epic_issue['number']}", token, {"body": updated_epic_body})

        # Atualiza corpo do Tema com checklist de Épicos filhos
        checklist_epics = "\n".join([f"- [ ] #{num}" for num in epic_numbers])
        updated_theme_body = f"{theme['body']}\n\n### Épicos Vinculados\n{checklist_epics}"
        github_request("PATCH", f"{API_BASE}/issues/{theme_issue['number']}", token, {"body": updated_theme_body})


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    md_path = repo_root / "docs" / "backlog_rastreabilidade.md"

    if not md_path.exists():
        print(f"ERRO: Arquivo {md_path} não encontrado.", file=sys.stderr)
        sys.exit(1)

    token = get_github_token()
    themes = parse_backlog_markdown(md_path)

    sync_labels(token)
    sync_issues(token, themes)
    print("\nConcluído! Todas as Labels, Temas, Épicos, Histórias e Sub-issues estão sincronizados no GitHub.")


if __name__ == "__main__":
    main()

