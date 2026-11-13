# Íris — Plataforma Inteligente de Adaptação de Materiais Pedagógicos

> **Residência em IA — Challenge 2 (Grupo 3)**  
> **Parceria:** Universidade de Brasília (UnB) • Lab Livre • Instituto de Pesquisas Eldorado • Softex • MCTI  
> **Metodologia:** Challenge Based Learning (CBL)

---

## 1. Visão Geral do Projeto

O **Íris** é um sistema inteligente desenhado para apoiar professores da educação básica e especialistas em AEE na tomada de decisão e na adaptação personalizada de avaliações, atividades e materiais didáticos para estudantes com **TDAH**.

O sistema supera o empobrecimento curricular gerado por LLMs genéricos ao introduzir:
1. **Barreiras Funcionais > Rótulo Clínico:** Parametrização por dificuldades executivas reais observadas em sala de aula combinadas às potencialidades do aluno.
2. **Andaime Cognitivo (*Scaffolding*) em 3 Níveis + Trava Curricular:** Suporte visual e procedural graduado, com proibição estrita de resolver ou interpretar pelo aluno (*anti-efeito muleta*).
3. **Privacy by Design (Zero-Database & LGPD):** Arquitetura *stateless* sem cadastro de alunos, sanitização local de dados pessoais (PII) e **Perfil Pedagógico Portátil** (`.json`/`.pdf`) local.

---

## 2. Documentação Oficial (MkDocs)

A documentação completa do projeto é compilada e servida via **MkDocs Material**.

### Conteúdo Disponível na Documentação:
* **Visão do Produto:** Justificativa pedagógica, personas, proposta de valor e limites do MVP.
* **Requisitos Funcionais (RF-01 a RF-15):** Especificação técnica completa de entrada de materiais, parametrização, travas, motor RAG, multiagentes e perfil portátil.
* **Requisitos Não Funcionais (RNF-01 a RNF-12):** Critérios de privacidade (LGPD), latência, WCAG 2.1 AA, modularidade e métricas objetivas (TRCC $\ge 95\%$, Flesch PT-BR e RAGAS).
* **Arquitetura & Decisões:** Diagramas e fluxo de dados *stateless*.
* **Metodologia CBL:** Big Idea, Essential Question, Guiding Questions e Roadmap de 7 semanas.
* **Catálogo de Skills:** Instruções para agentes e papéis de engenharia/PO.

---

## 3. Gerenciamento do Projeto com UV

O projeto utiliza exclusivamente o **[uv](https://docs.astral.sh/uv/)** para gerenciamento de dependências e ambientes virtuais Python ultra-rápidos e determinísticos.

### Pré-requisitos
Certifique-se de ter o `uv` instalado em sua máquina:
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ou via Homebrew (macOS)
brew install uv
```

### Comandos Rápidos de Documentação

```bash
# 1. Sincronizar o ambiente virtual e instalar dependências (incluindo mkdocs)
uv sync

# 2. Executar o servidor local de documentação com live-reload
uv run mkdocs serve

# Acesse no navegador: http://127.0.0.1:8000

# 3. Compilar a documentação estática (geração da pasta site/)
uv run mkdocs build
```

### Comandos Rápidos via `Makefile` (Recomendado — Zero Configuração Manual)

Se você acabou de clonar o repositório, **não precisa instalar nada manualmente antes**: os comandos do `Makefile` verificam o que falta (`uv`, `.venv`, pacotes Python, `node_modules`, base RAG, `pgvector` e `Ollama`/`Llama 3`), instalam o que for necessário e **pulam automaticamente tudo o que já estiver instalado**:

```bash
# 1. Preparar todo o ambiente após o git clone (instala o que faltar e pula o que já existe)
make setup

# 2. Subir tudo (verifica/instala dependências + Ollama + RAG + Backend :8000 + Frontend Next.js :3000)
make up

# 3. Verificar integridade do ambiente, catálogo, PII, API, RAG e Agente Extrator
make check

# 4. Abrir menus interativos de validação e testes no terminal
make rag         # Central do RAG, 12 métricas e consulta ao vivo
make extrator    # Agente Extrator Curricular (#17), Benchmark e Analytics
make test        # Bateria completa de testes unitários
```

Para o passo a passo completo de testes manuais por issue, consulte [docs/roteiro_testes.md](docs/roteiro_testes.md).

### Execução Manual Individual (Backend FastAPI e Frontend Next.js)

```bash
# 1. Iniciar a API Backend FastAPI (porta 8000)
uv run uvicorn iris.main:app --app-dir backend/src --reload --port 8000

# 2. Em outro terminal, iniciar o Frontend Next.js (porta 3000)
cd frontend && npm install && npm run dev

# Acesse a aplicação web no navegador: http://localhost:3000
```

### Gerenciamento de Dependências e Testes com UV

```bash
# Adicionar nova dependência de produção no Backend
uv add nome-do-pacote

# Executar a bateria completa de testes unitários do Backend
uv run pytest
# ou diretamente via unittest:
python3 -m unittest discover -s backend/tests -v
```

---

## 4. Estrutura do Repositório (Separação Backend Python & Frontend Next.js)

```text
iris/
├── .env.example                  # Exemplo padronizado de variáveis de ambiente
├── backend/                      # Camada de Backend Python (FastAPI + Agentes + RAG Bridge)
│   ├── src/iris/
│   │   ├── config.py             # Configurações centralizadas e guardrails Zero-Database
│   │   ├── main.py               # Entrypoint FastAPI stateless + CORS para o Next.js
│   │   ├── api/                  # Rotas REST stateless (/api/v1/materials/upload e /text)
│   │   ├── core/                 # Cliente unificado de LLM (Ollama Local + API) e telemetria
│   │   ├── schemas/              # Contratos de validação (Catálogo, Materiais, Perfil Portátil)
│   │   ├── security/             # Sanitizador preventivo de PII (Zero-Retention Scrubber)
│   │   ├── parsers/              # Extratores em memória (.pdf, .docx, .txt) e decompositor
│   │   ├── agents/               # Orquestração multiagentes (Extrator, Estrategista, Adaptador, Auditor)
│   │   └── rag/                  # Ponte (bridge.py) de integração com rag/iris-rag/pacote
│   └── tests/                    # Suíte de testes automatizados do Backend (unittest / pytest)
├── frontend/                     # Camada de Frontend Web Docente (Next.js 14 + TypeScript + Tailwind CSS)
│   ├── package.json              # Dependências do Next.js, React 18 e Lucide Icons
│   ├── next.config.mjs           # Configuração e proxy reverso para o Backend FastAPI
│   ├── tailwind.config.ts        # Tokens visuais oficiais da Íris (#335C67, #E35336, #0D0221, #F5EDF0)
│   └── src/
│       ├── app/                  # App Router (Tela de Acesso Figma `/` e Etapa 1 `/etapa-1`)
│       ├── components/           # Componentes acessíveis WCAG 2.1 AA (Step1MaterialIntake, Stepper5Etapas)
│       └── services/             # Cliente HTTP (`materialsApi.ts`) integrado à API FastAPI
├── docs/                         # Documentação oficial do projeto (MkDocs Material)
├── rag/                          # Subsistemas de Conhecimento Científico e Catálogos Modulares (#39)
├── scripts/                      # Automação de backlog e sincronização com GitHub
├── mkdocs.yml                    # Configuração do MkDocs Material
├── pyproject.toml                # Especificação unificada de dependências Python (UV)
└── README.md                     # Visão geral rápida do repositório
```
