#!/usr/bin/env python3
"""
Cria as 3 issues estruturais e de engenharia ausentes no backlog do Íris,
vincula-as ao Épico 4.2 (#38) como Sub-issues e adiciona-as ao GitHub Project V2.
"""
import json
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from scripts.sync_github_backlog import (
    API_BASE,
    GRAPHQL_URL,
    OWNER,
    REPO,
    create_or_update_issue,
    get_existing_issues,
    get_github_token,
    github_request,
    link_sub_issue_graphql,
)

NEW_STORIES = [
    {
        "prefix": "História 4.2.3:",
        "title": "História 4.2.3: Camada de abstração híbrida de LLM (Ollama Local + API Externa) e setup do Llama 3",
        "labels": ["type: story", "priority: must", "scope: infra-eval", "scope: agents", "scope: rag"],
        "body": """**Épico Pai:** #38 (Épico 4.2)

**História de Usuário**
Como engenheiro de IA e desenvolvedor da equipe Íris, quero uma camada de abstração unificada para chamadas de LLM (`IrisLLMClient`) que permita alternar transparentemente via variáveis de ambiente entre modelos locais no Ollama (como `llama3.1:8b` e `qwen2.5:7b`) e provedores via API (Groq / OpenAI), para que toda a equipe possa desenvolver e rodar baterias de testes sem custo, sem bloqueios de *rate limit* e em total conformidade com a LGPD.

**Requisito Base:** RNF-01, RNF-07, RNF-08, RNF-12
**Critérios de Aceitação:**
* **Dado que** o desenvolvedor configura `IRIS_LLM_PROVIDER=ollama` ou `IRIS_LLM_PROVIDER=groq` no arquivo `.env`,
* **Quando** qualquer módulo do RAG ou agente invocar o `IrisLLMClient`,
* **Então** o cliente deve rotear a requisição usando o contrato OpenAI-compatible (`/v1/chat/completions`) sem exigir alterações no código chamador.
* **E** o cliente deve suportar respostas em texto livre e saídas estruturadas validadas por schemas Pydantic (*Structured Outputs*).
* **E** toda chamada deve retornar telemetria padronizada (`prompt_tokens`, `completion_tokens`, `latency_ms` e `model_used`).
* **E** o repositório deve conter um `Modelfile` / script de setup com parâmetros reprodutíveis (`temperature=0`, `seed=42`) para execução local no Ollama.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Implementar `src/iris/core/llm_client.py` suportando `generate_text` e `generate_structured` (Pydantic JSON Schema) para Ollama e API Groq/OpenAI.
- [ ] **[Infra]** Criar `scripts/setup_ollama.sh` e configuração padrão para provisionamento reprodutível do modelo local (`llama3.1:8b` / `qwen2.5:7b`).
- [ ] **[RAG / IA]** Integrar `gerar.py` do pacote RAG com a configuração unificada de provedores e variáveis de ambiente.
- [ ] **[Testes]** Testes unitários em `tests/core/test_llm_client.py` validando fallback, extração JSON e coleta de métricas de latência/tokens.""",
    },
    {
        "prefix": "História 4.2.4:",
        "title": "História 4.2.4: Unificação de dependências no pyproject.toml, estrutura base src/iris e ponte com o módulo RAG",
        "labels": ["type: story", "priority: must", "scope: infra-eval", "scope: api", "scope: rag"],
        "body": """**Épico Pai:** #38 (Épico 4.2)

**História de Usuário**
Como desenvolvedor da plataforma Íris, quero que todas as dependências do projeto estejam unificadas no `pyproject.toml` (gerenciado pelo `uv`) e que a árvore de pacotes em `src/iris/` esteja estruturada e integrada ao módulo `rag/iris-rag/pacote/`, para que a equipe trabalhe em paralelo na API, no Frontend e nos Agentes sem conflitos de diretórios ou erros de importação.

**Requisito Base:** RNF-11, RNF-12
**Critérios de Aceitação:**
* **Dado que** um desenvolvedor clona o repositório e executa `uv sync`,
* **Quando** a instalação finalizar,
* **Então** todas as dependências da API FastAPI, manipulação de documentos (`.pdf`, `.docx`) e do pipeline RAG (`pgvector`, `rank-bm25`, `sentence-transformers`) devem estar resolvidas num único ambiente virtual.
* **E** o pacote `src/iris/` deve conter a estrutura modular inicial (`api/`, `core/`, `schemas/`, `security/`, `parsers/`, `agents/`, `rag/`) instalável em modo editável.
* **E** o serviço de busca e geração do RAG deve poder ser importado a partir de `src/iris/` independentemente do diretório de trabalho (`cwd`) da aplicação.
* **E** deve existir um arquivo `.env.example` na raiz documentando todas as variáveis de configuração do projeto.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Infra]** Unificar as dependências de `rag/iris-rag/pacote/requirements.txt` nos grupos do `pyproject.toml`, habilitar empacotamento editável de `src/iris` e atualizar o `uv.lock`.
- [ ] **[Backend]** Criar a estrutura de diretórios e pacotes base em `src/iris/` (`api`, `core`, `schemas`, `security`, `parsers`, `agents`, `rag`) e diretório `tests/`.
- [ ] **[RAG / IA]** Criar adaptador em `src/iris/rag/` encapsulando `consultar.buscar` e `gerar.responder` sem depender de `cwd` relativo.
- [ ] **[Infra]** Criar arquivo `.env.example` padronizado na raiz do repositório.""",
    },
    {
        "prefix": "História 4.2.5:",
        "title": "História 4.2.5: Curadoria e estruturação do dataset Golden Benchmark de questões escolares (Fundamental II e Médio)",
        "labels": ["type: story", "priority: must", "scope: infra-eval", "scope: rag"],
        "body": """**Épico Pai:** #38 (Épico 4.2)

**História de Usuário**
Como pesquisador responsável pela validação experimental da Semana 3, quero um dataset estruturado (*Golden Benchmark*) contendo de 30 a 50 questões escolares reais de Ensino Fundamental II e Médio anotadas com suas respectivas Travas Curriculares e características-alvo, para viabilizar a EDA 2 (legibilidade Flesch-Kincaid PT-BR) e o experimento comparativo entre LLM Puro vs. Íris (RAG).

**Requisito Base:** RF-08, RF-10, RNF-04, RNF-05
**Critérios de Aceitação:**
* **Dado que** o experimento da Semana 3 e a EDA 2 exigem avaliações escolares reais (e não apenas dúvidas teóricas sobre TDAH),
* **Quando** o dataset `data/benchmarks/questoes_escolares_v1.json` for carregado,
* **Então** cada questão deve conter: `id`, `disciplina`, `ano_escolar`, `habilidade_bncc`, `enunciado_original`, `alternativas` (quando objetiva), `conceitos_trava_curricular` (lista de termos/conceitos inegociáveis), `operacao_cognitiva` e `id_caracteristica_alvo`.
* **E** o conjunto deve conter no mínimo 30 questões públicas (ex.: INEP/SAEB, ENEM, bancos abertos alinhados à BNCC) cobrindo enunciados longos, múltiplos comandos conjugados e textos de apoio densos.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Definir schema Pydantic `BenchmarkQuestionItem` para validação do dataset de questões escolares.
- [ ] **[RAG / IA]** Coletar e anotar no mínimo 30 questões públicas (Fundamental II e Médio) em `data/benchmarks/questoes_escolares_v1.json` com Travas Curriculares e características funcionais associadas.
- [ ] **[RAG / IA]** Implementar funções utilitárias de cálculo do Índice Flesch-Kincaid PT-BR e contagem de verbos de comando por enunciado para alimentar a EDA 2 (#40).""",
    },
]


def add_to_github_projects(token: str, issue_node_ids: list[str]) -> None:
    """Descobre os projetos V2 da organização/repositório e adiciona as novas issues."""
    query_projects = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        projectsV2(first: 10) {
          nodes { id title number }
        }
        owner {
          ... on Organization {
            projectsV2(first: 10) {
              nodes { id title number }
            }
          }
          ... on User {
            projectsV2(first: 10) {
              nodes { id title number }
            }
          }
        }
      }
    }
    """
    res = github_request("POST", GRAPHQL_URL, token, {"query": query_projects, "variables": {"owner": OWNER, "repo": REPO}})
    repo_data = (res.get("data") or {}).get("repository") or {}
    proj_nodes = []
    proj_nodes.extend(((repo_data.get("projectsV2") or {}).get("nodes") or []))
    proj_nodes.extend((((repo_data.get("owner") or {}).get("projectsV2") or {}).get("nodes") or []))

    seen = set()
    unique_projects = []
    for p in proj_nodes:
        if p and p["id"] not in seen:
            seen.add(p["id"])
            unique_projects.append(p)

    if not unique_projects:
        print("  [Aviso] Nenhum GitHub Project V2 encontrado via GraphQL.")
        return

    mutation_add = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item { id }
      }
    }
    """
    for proj in unique_projects:
        print(f"=== Adicionando issues ao Project '{proj['title']}' (#{proj['number']}) ===")
        for node_id in issue_node_ids:
            r = github_request(
                "POST",
                GRAPHQL_URL,
                token,
                {"query": mutation_add, "variables": {"projectId": proj["id"], "contentId": node_id}},
            )
            if "errors" in r:
                print(f"  [Erro ao adicionar ao project]: {r['errors']}")
            else:
                print(f"  [OK] Adicionada ao Project '{proj['title']}'")


def main():
    token = get_github_token()
    all_issues = get_existing_issues(token)

    # Localiza o Épico 4.2 (#38)
    epic_42 = next((i for i in all_issues if i["number"] == 38 or i["title"].startswith("Épico 4.2:")), None)
    if not epic_42:
        print("ERRO: Épico 4.2 (#38) não encontrado!", file=sys.stderr)
        sys.exit(1)

    print(f"=== Criando Novas Issues e vinculando ao {epic_42['title']} (#{epic_42['number']}) ===")
    created_issues = []
    for story in NEW_STORIES:
        issue = create_or_update_issue(
            token,
            all_issues,
            story["prefix"],
            story["title"],
            story["body"],
            story["labels"],
        )
        created_issues.append(issue)
        link_sub_issue_graphql(token, epic_42["node_id"], issue["node_id"])

    # Atualiza checklist do Épico 4.2 (#38) se necessário
    epic_body = epic_42.get("body") or ""
    for issue in created_issues:
        line = f"- [ ] #{issue['number']} — {issue['title']}"
        if f"#{issue['number']}" not in epic_body:
            epic_body = epic_body.rstrip() + "\n" + line
    github_request("PATCH", f"{API_BASE}/issues/{epic_42['number']}", token, {"body": epic_body})
    print(f"  [ATUALIZADO] Checklist do Épico #{epic_42['number']}")

    # Adiciona ao GitHub Projects
    add_to_github_projects(token, [i["node_id"] for i in created_issues])


if __name__ == "__main__":
    main()

