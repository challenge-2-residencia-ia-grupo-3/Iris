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

### Gerenciamento de Dependências com UV

```bash
# Adicionar nova dependência de produção
uv add nome-do-pacote

# Adicionar dependência ao grupo de documentação
uv add --group docs nome-do-pacote

# Executar scripts ou testes com o ambiente isolado do UV
uv run pytest
```

---

## 4. Estrutura do Repositório

```text
iris/
├── .agents/                      # Configurações e skills do agente de desenvolvimento
│   └── skills/
│       ├── challenge2-cbl-pedagogical-adapter/
│       └── po-ia-educacional/
├── docs/                         # Documentação oficial do projeto (MkDocs)
│   ├── index.md                  # Apresentação e navegação
│   ├── visao_produto.md          # Visão, dores, personas e proposta de valor
│   ├── requisitos_funcionais.md  # RF-01 a RF-15 (sem user stories)
│   ├── requisitos_nao_funcionais.md # RNF-01 a RNF-12 (LGPD, SLA, métricas)
│   ├── arquitetura.md            # Diagramas, fluxo stateless e multiagentes
│   ├── cbl.md                    # Big Idea, EQ, Guiding Questions e Roadmap
│   └── skills.md                 # Catálogo das skills do projeto
├── mkdocs.yml                    # Configuração do MkDocs Material
├── pyproject.toml                # Especificação de dependências e metadados UV
├── .python-version               # Versão do Python (3.12)
├── .gitignore                    # Regras de exclusão do Git
├── README.md                     # Visão geral rápida do repositório
└── skills.md                     # Espelho do catálogo de skills
```
