# Backlog Estruturado e Matriz de Rastreabilidade — Íris

Este documento consolida a hierarquia completa do backlog do projeto **Íris** (**Temas $\rightarrow$ Épicos $\rightarrow$ Histórias de Usuário**), o sistema de **Labels** e a **Matriz de Rastreabilidade** cruzando cada item com os Requisitos Funcionais (RF) e Não Funcionais (RNF).

---

## 1. Arquitetura de Labels do Repositório

### 1.1. Labels de Tipo (Hierarquia)
| Label | Cor Hex | Descrição |
| :--- | :---: | :--- |
| `type: theme` | `#0D0221` | Tema estratégico macro do produto (Nível 1 da hierarquia) |
| `type: epic` | `#6F42C1` | Épico funcional agrupador de histórias (Nível 2 — Sub-issue de Tema) |
| `type: story` | `#1A7F37` | História de Usuário implementável com critérios BDD (Nível 3 — Sub-issue de Épico) |

### 1.2. Labels de Prioridade (MoSCoW)
| Label | Cor Hex | Descrição |
| :--- | :---: | :--- |
| `priority: must` | `#B60205` | Crítico e obrigatório para o funcionamento do MVP e regras inegociáveis |
| `priority: should` | `#FBCA04` | Importante para a completude pedagógica e multimodalidade |
| `priority: could` | `#0E8A16` | Desejável para refinamento de experiência e extensões futuras |

### 1.3. Labels de Escopo Técnico (Arquitetura Íris)
| Label | Cor Hex | Descrição |
| :--- | :---: | :--- |
| `scope: front-web` | `#D97706` | Interface web docente (WCAG 2.1 AA, fluxo de 5 etapas, editor lado a lado) |
| `scope: api` | `#4F46E5` | Backend FastAPI, rotas stateless, parsers de documentos e exportação |
| `scope: rag` | `#0891B2` | Base de conhecimento científica (DUA/MEC), chunking, embeddings e busca vetorial |
| `scope: agents` | `#335C67` | Sistema multiagentes, engenharia de prompts, isolamento de escopo e auditoria |
| `scope: privacy-lgpd` | `#059669` | Sanitizador local de PII, arquitetura Zero-Database e Perfil Pedagógico Portátil |
| `scope: infra-eval` | `#E35336` | Infraestrutura UV, CI/CD, testes e métricas objetivas (TRCC, Flesch-Kincaid, RAGAS) |

---

## 2. Matriz de Rastreabilidade e Dependências Funcionais (Requisitos $\times$ Backlog)

### 2.1. Rastreabilidade Direta (Histórias $\rightarrow$ Requisitos $\rightarrow$ Dependências de Precedência)

| Issue GitHub | ID História | Título da História de Usuário | Épico / Tema | Requisitos Atendidos (RF / RNF) | Depende de (Pré-requisitos Funcionais) | Prioridade | Escopo Técnico |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `#4` | **História 1.1.1** | Entrada de material didático via texto e upload de documentos | Épico 1.1 / Tema 1 | **RF-01**, RNF-10 | *Nenhuma (Ponto de Entrada)* | `priority: must` | `scope: front-web`, `scope: api` |
| `#5` | **História 1.1.2** | Decomposição estrutural automática de questões e enunciados | Épico 1.1 / Tema 1 | **RF-02** | **História 1.1.1** (RF-01) | `priority: must` | `scope: api`, `scope: agents` |
| `#6` | **História 1.1.3** | Extração multimodal de provas digitalizadas via OCR e análise visual | Épico 1.1 / Tema 1 | **RF-03** | **História 1.1.1** (RF-01), **História 1.1.2** (RF-02) | `priority: should` | `scope: agents`, `scope: api` |
| `#8` | **História 1.2.1** | Seleção cirúrgica de características funcionais atômicas observadas | Épico 1.2 / Tema 1 | **RF-04**, RNF-10 | **História 4.2.1** (RF-06 — Schema do Catálogo) | `priority: must` | `scope: front-web`, `scope: api` |
| `#9` | **História 1.2.2** | Registro de potencialidades, interesses e canais de engajamento | Épico 1.2 / Tema 1 | **RF-05**, RNF-06 | **História 1.2.1** (RF-04) | `priority: should` | `scope: front-web`, `scope: api` |
| `#10` | **História 1.2.3** | Transcrição de observações pedagógicas docentes via entrada de áudio | Épico 1.2 / Tema 1 | **RF-03**, **RF-05** | **História 1.2.1** (RF-04), **História 4.1.1** (RNF-02) | `priority: could` | `scope: agents`, `scope: api` |
| `#12` | **História 1.3.1** | Calibragem do nível de andaime cognitivo em 3 níveis (Leve, Moderado, Intensivo) | Épico 1.3 / Tema 1 | **RF-07**, RNF-10 | **História 1.2.1** (RF-04) | `priority: must` | `scope: front-web`, `scope: agents` |
| `#13` | **História 1.3.2** | Definição de Travas Curriculares Inegociáveis e alerta preventivo anti-muleta | Épico 1.3 / Tema 1 | **RF-08**, **RF-09** | **História 1.1.2** (RF-02), **História 1.3.1** (RF-07) | `priority: must` | `scope: front-web`, `scope: agents` |
| `#16` | **História 2.1.1** | Recuperação de estratégias psicopedagógicas baseadas em evidências (RAG) | Épico 2.1 / Tema 2 | **RF-10**, RNF-06 | **História 1.2.1** (RF-04), **História 1.3.1** (RF-07), **História 4.2.1** (RF-06) | `priority: must` | `scope: rag` |
| `#17` | **História 2.1.2** | Extração de invariantes curriculares pelo Agente Extrator | Épico 2.1 / Tema 2 | **RF-08**, **RF-11** | **História 1.1.2** (RF-02), **História 1.3.2** (RF-08), **História 4.1.1** (RNF-02) | `priority: must` | `scope: agents` |
| `#18` | **História 2.1.3** | Adaptação com isolamento estrito de escopo à característica selecionada | Épico 2.1 / Tema 2 | **RF-04**, **RF-11**, RNF-07, RNF-08 | **História 2.1.1** (RF-10), **História 2.1.2** (RF-11) | `priority: must` | `scope: agents`, `scope: rag` |
| `#19` | **História 2.1.4** | Auditoria automatizada de retenção curricular (TRCC) e não-intrusividade | Épico 2.1 / Tema 2 | **RF-12**, RNF-04, RNF-05 | **História 2.1.3** (RF-11) | `priority: must` | `scope: agents`, `scope: infra-eval` |
| `#21` | **História 2.2.1** | Visualização comparativa lado a lado com justificativas pedagógicas do DUA | Épico 2.2 / Tema 2 | **RF-10**, **RF-13**, RNF-09 | **História 2.1.4** (RF-12) | `priority: must` | `scope: front-web` |
| `#22` | **História 2.2.2** | Edição livre docente em tempo real e aprovação Human-in-the-Loop | Épico 2.2 / Tema 2 | **RF-13**, RNF-09 | **História 2.2.1** (RF-13) | `priority: must` | `scope: front-web`, `scope: api` |
| `#23` | **História 2.2.3** | Exportação do material adaptado em PDF diagramado econômico e DOCX editável | Épico 2.2 / Tema 2 | **RF-14** | **História 2.2.2** (RF-13) | `priority: must` | `scope: api`, `scope: front-web` |
| `#26` | **História 3.1.1** | Geração de Perfil Pedagógico Portátil com identificador anônimo aleatório | Épico 3.1 / Tema 3 | **RF-15**, RNF-01 | **História 1.2.1** (RF-04), **História 4.1.2** (RNF-01) | `priority: should` | `scope: privacy-lgpd`, `scope: api` |
| `#27` | **História 3.1.2** | Registro de histórico de eficácia das intervenções por característica | Épico 3.1 / Tema 3 | **RF-15** | **História 3.1.1** (RF-15), **História 2.2.2** (RF-13) | `priority: should` | `scope: privacy-lgpd`, `scope: front-web` |
| `#28` | **História 3.1.3** | Bloqueio de inserção de dados clínicos e diagnósticos formais no perfil | Épico 3.1 / Tema 3 | **RF-15**, RNF-03 | **História 3.1.1** (RF-15) | `priority: must` | `scope: privacy-lgpd`, `scope: api` |
| `#30` | **História 3.2.1** | Exportação local do Perfil Pedagógico Portátil em JSON e PDF | Épico 3.2 / Tema 3 | **RF-15**, RNF-01 | **História 3.1.2** (RF-15), **História 3.1.3** (RNF-03) | `priority: should` | `scope: privacy-lgpd`, `scope: api` |
| `#31` | **História 3.2.2** | Importação e restauração de sessão a partir de arquivo JSON portátil | Épico 3.2 / Tema 3 | **RF-15**, RNF-10 | **História 3.2.1** (RF-15), **História 1.2.1** (RF-04) | `priority: should` | `scope: privacy-lgpd`, `scope: front-web` |
| `#34` | **História 4.1.1** | Detecção e descarte preventivo de PII na entrada de materiais | Épico 4.1 / Tema 4 | **RNF-02**, RF-01 | **História 1.1.1** (RF-01) | `priority: must` | `scope: privacy-lgpd`, `scope: api` |
| `#35` | **História 4.1.2** | Execução em arquitetura stateless Zero-Database sem persistência de alunos | Épico 4.1 / Tema 4 | **RNF-01**, RNF-12 | *Nenhuma (Restrição Arquitetural Base)* | `priority: must` | `scope: privacy-lgpd`, `scope: infra-eval` |
| `#36` | **História 4.1.3** | Descarte preventivo de PII acidental e formatação de cabeçalho escolar neutro | Épico 4.1 / Tema 4 | **RNF-02**, **RF-14** | **História 4.1.1** (RNF-02), **História 2.2.3** (RF-14) | `priority: must` | `scope: privacy-lgpd`, `scope: front-web` |
| `#37` | **História 4.1.4** | Auditoria de não-retenção de payloads sensíveis em logs de execução | Épico 4.1 / Tema 4 | **RNF-01**, **RNF-02** | **História 4.1.1** (RNF-02), **História 4.1.2** (RNF-01) | `priority: must` | `scope: privacy-lgpd`, `scope: infra-eval` |
| `#39` | **História 4.2.1** | Estruturação de schema modular JSON/YAML para catálogos de características | Épico 4.2 / Tema 4 | **RF-06**, RNF-11, RNF-12 | *Nenhuma (Fundação do Catálogo)* | `priority: must` | `scope: rag`, `scope: api` |
| `#40` | **História 4.2.2** | Análise exploratória de dados (EDA do corpus e benchmark) e validação RAGAS | Épico 4.2 / Tema 4 | **RF-10**, **RNF-04**, **RNF-05**, **RNF-06** | **História 2.1.1** (RF-10), **História 2.1.4** (RF-12) | `priority: must` | `scope: infra-eval`, `scope: rag` |
| `#43` | **História 4.2.3** | Camada de abstração híbrida de LLM (Ollama Local + API Externa) e setup do Llama 3 | Épico 4.2 / Tema 4 | **RNF-01**, **RNF-07**, **RNF-08**, **RNF-12** | **História 4.2.4** (`#44`) | `priority: must` | `scope: infra-eval`, `scope: agents`, `scope: rag` |
| `#44` | **História 4.2.4** | Unificação de dependências no pyproject.toml, estrutura base src/iris e ponte com o módulo RAG | Épico 4.2 / Tema 4 | **RNF-11**, **RNF-12** | *Nenhuma (Fundação de Código)* | `priority: must` | `scope: infra-eval`, `scope: api`, `scope: rag` |
| `#45` | **História 4.2.5** | Curadoria e estruturação do dataset Golden Benchmark de questões escolares (Fundamental II e Médio) | Épico 4.2 / Tema 4 | **RF-08**, **RF-10**, **RNF-04**, **RNF-05** | **História 4.2.1** (`#39`) | `priority: must` | `scope: infra-eval`, `scope: rag` |

---

### 2.2. Rastreabilidade Inversa (Requisitos Funcionais e Não Funcionais $\rightarrow$ Backlog)

| Código Requisito | Nome do Requisito | Tema(s) | Épico(s) | Histórias de Usuário Vinculadas |
| :--- | :--- | :--- | :--- | :--- |
| **RF-01** | Inserção de Conteúdo Pedagógico via Texto e Documentos | Tema 1, Tema 4 | Épico 1.1, Épico 4.1 | **História 1.1.1** (`#4`), **História 4.1.1** (`#34`) |
| **RF-02** | Decomposição Estrutural Automática do Material | Tema 1 | Épico 1.1 | **História 1.1.2** (`#5`) |
| **RF-03** | Entrada Multimodal de Provas, Imagens e Áudio | Tema 1 | Épico 1.1, Épico 1.2 | **História 1.1.3** (`#6`), **História 1.2.3** (`#10`) |
| **RF-04** | Seleção Cirúrgica de Características Neurodivergentes Específicas | Tema 1, Tema 2 | Épico 1.2, Épico 2.1 | **História 1.2.1** (`#8`), **História 2.1.3** (`#18`) |
| **RF-05** | Registro de Potencialidades e Estilos de Engajamento | Tema 1 | Épico 1.2 | **História 1.2.2** (`#9`), **História 1.2.3** (`#10`) |
| **RF-06** | Extensibilidade de Catálogos de Perfis | Tema 4 | Épico 4.2 | **História 4.2.1** (`#39`) |
| **RF-07** | Calibragem do Nível de Andaime Cognitivo (*Scaffolding*) | Tema 1 | Épico 1.3 | **História 1.3.1** (`#12`) |
| **RF-08** | Definição Explícita de Travas Curriculares Inegociáveis | Tema 1, Tema 2 | Épico 1.3, Épico 2.1 | **História 1.3.2** (`#13`), **História 2.1.2** (`#17`) |
| **RF-09** | Validador Preventivo de Perda Cognitiva (*Anti-Muleta*) | Tema 1 | Épico 1.3 | **História 1.3.2** (`#13`) |
| **RF-10** | Recuperação de Estratégias Pedagógicas Baseadas em Evidências (RAG) | Tema 2, Tema 4 | Épico 2.1, Épico 2.2, Épico 4.2 | **História 2.1.1** (`#16`), **História 2.2.1** (`#21`), **História 4.2.2** (`#40`) |
| **RF-11** | Orquestração Multiagentes com Isolamento de Escopo | Tema 2 | Épico 2.1 | **História 2.1.2** (`#17`), **História 2.1.3** (`#18`) |
| **RF-12** | Auditoria Automatizada de Preservação Curricular e Não-Intrusividade | Tema 2 | Épico 2.1 | **História 2.1.4** (`#19`) |
| **RF-13** | Interface de Revisão e Edição Lado a Lado (*Human-in-the-Loop*) | Tema 2 | Épico 2.2 | **História 2.2.1** (`#21`), **História 2.2.2** (`#22`) |
| **RF-14** | Exportação em Formatos Prontos para Impressão e Uso Digital | Tema 2, Tema 4 | Épico 2.2, Épico 4.1 | **História 2.2.3** (`#23`), **História 4.1.3** (`#36`) |
| **RF-15** | Exportação e Importação do Perfil Pedagógico Portátil | Tema 3 | Épico 3.1, Épico 3.2 | **História 3.1.1** (`#26`), **História 3.1.2** (`#27`), **História 3.1.3** (`#28`), **História 3.2.1** (`#30`), **História 3.2.2** (`#31`) |
| **RNF-01** | Arquitetura Stateless de Dados de Estudantes (*Zero-Database*) | Tema 3, Tema 4 | Épico 3.1, Épico 3.2, Épico 4.1 | **História 3.1.1** (`#26`), **História 3.2.1** (`#30`), **História 4.1.2** (`#35`), **História 4.1.4** (`#37`) |
| **RNF-02** | Sanitização Preventiva e Descarte Imediato de PII (Zero-Retention) | Tema 4 | Épico 4.1 | **História 4.1.1** (`#34`), **História 4.1.3** (`#36`), **História 4.1.4** (`#37`) |
| **RNF-03** | Desacoplamento entre Dados Pedagógicos e Dados Clínicos | Tema 3 | Épico 3.1 | **História 3.1.3** (`#28`) |
| **RNF-04** | Taxa de Retenção de Conceitos-Chave ($\text{TRCC} \ge 95\%$) | Tema 2, Tema 4 | Épico 2.1, Épico 4.2 | **História 2.1.4** (`#19`), **História 4.2.2** (`#40`) |
| **RNF-05** | Monitoramento de Complexidade Sintática (Flesch-Kincaid PT-BR) | Tema 2, Tema 4 | Épico 2.1, Épico 4.2 | **História 2.1.4** (`#19`), **História 4.2.2** (`#40`) |
| **RNF-06** | Qualidade e Rastreabilidade do Pipeline RAG (RAGAS) | Tema 1, Tema 2, Tema 4 | Épico 1.2, Épico 2.1, Épico 4.2 | **História 1.2.2** (`#9`), **História 2.1.1** (`#16`), **História 4.2.2** (`#40`) |
| **RNF-07 / RNF-08** | Latência ($\le 15\text{s}$ / $\le 40\text{s}$) e Eficiência de Tokens | Tema 2 | Épico 2.1 | **História 2.1.3** (`#18`) |
| **RNF-09 / RNF-10** | Acessibilidade (WCAG 2.1 AA) e Fluxo Guiado em 5 Etapas | Tema 1, Tema 2, Tema 3 | Épico 1.1 a 1.3, Épico 2.2, Épico 3.2 | **História 1.1.1** (`#4`), **História 1.2.1** (`#8`), **História 1.3.1** (`#12`), **História 2.2.1** (`#21`), **História 2.2.2** (`#22`), **História 3.2.2** (`#31`) |
| **RNF-11 / RNF-12** | Gerenciamento via UV e Modularidade Arquitetural | Tema 4 | Épico 4.1, Épico 4.2 | **História 4.1.2** (`#35`), **História 4.2.1** (`#39`) |

---

## 3. Especificação Completa das Issues (Temas, Épicos e Histórias)

---

### Tema 1: Gestão de Insumos e Parametrização Pedagógica
* **Tipo:** `type: theme`
* **Descrição:** Compreende os fluxos de entrada de atividades didáticas, decomposição estrutural e parametrização cirúrgica por características funcionais observadas em sala de aula, níveis de andaime e travas curriculares.
* **Épicos vinculados:** Épico 1.1, Épico 1.2, Épico 1.3.

---

#### Épico 1.1: Identificação e Entrada de Materiais Didáticos
* **Tipo:** `type: epic` | **Pai:** Tema 1
* **Descrição:** Módulo responsável pela recepção, validação e decomposição de atividades pedagógicas em texto digital, documentos e insumos multimodais.

##### História 1.1.1: Entrada de material didático via texto e upload de documentos
**História de Usuário**
Como professor da educação básica, quero inserir o conteúdo da minha atividade por colagem direta de texto ou upload de arquivos (`.pdf`, `.docx`, `.txt`), para que eu possa submeter avaliações já existentes sem precisar redigitá-las manualmente.

**Requisito Base:** RF-01, RNF-10
**Critérios de Aceitação:**
* **Dado que** o professor acessa a Etapa 1 da plataforma Íris,
* **Quando** ele colar um texto ou fizer upload de um arquivo `.pdf`, `.docx` ou `.txt` válido,
* **Então** o sistema deve extrair o conteúdo textual em memória e exibi-lo para conferência imediata.
* **E** o sistema deve validar que o texto possui no mínimo 50 caracteres e no máximo 2.000 palavras.
* **E** a extração não deve falhar ou corromper acentuações da língua portuguesa (UTF-8).

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint FastAPI `POST /api/v1/materials/upload` com suporte a multipart/form-data e extração de texto bruto (`.txt`, `.pdf`, `.docx`).
- [ ] **[Backend]** Validação de tamanho (mínimo 50 caracteres e limite seguro de 2.000 palavras) com mensagens de erro estruturadas.
- [ ] **[Frontend]** Componente da Etapa 1 com área de colagem de texto (textarea acessível) e contador de caracteres/palavras em tempo real.
- [ ] **[Frontend]** Componente drag-and-drop de arquivos com feedback visual de formato aceito/rejeitado (WCAG 2.1 AA).
- [ ] **[Testes]** Testes unitários de extração de arquivos em `tests/api/test_materials.py` com mocks de PDF e DOCX.

##### História 1.1.2: Decomposição estrutural automática de questões e enunciados
**História de Usuário**
Como professor regente, quero que a plataforma identifique e separe automaticamente os textos-base, os enunciados de cada questão e as alternativas, para que a adaptação preserve a numeração e a organização original da prova.

**Requisito Base:** RF-02
**Critérios de Aceitação:**
* **Dado que** um material pedagógico bruto foi carregado na sessão,
* **Quando** o módulo de decomposição estrutural processar o texto,
* **Então** o sistema deve segmentar cada questão em um bloco estruturado independente (texto de apoio, comando da questão e opções de resposta).
* **E** o sistema deve manter a ordem sequencial exata das questões originais.
* **E** o processamento não deve fundir questões distintas mesmo quando a formatação original não possuir quebras de página explícitas.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Módulo `src/iris/parsers/structural_decomposer.py` para isolar cabeçalho institucional, enunciados e alternativas.
- [ ] **[Backend]** Schema Pydantic `MaterialStructure` contendo blocos de contexto e lista de `QuestionItem`.
- [ ] **[RAG / IA]** Heurísticas e expressões regulares com fallback para modelo leve de NLP para identificar numeração de questões.
- [ ] **[Testes]** Testes com dataset sintético de 10 provas com layouts variados comprovando preservação sequencial.

##### História 1.1.3: Extração multimodal de provas digitalizadas via OCR e análise visual
**História de Usuário**
Como professor, quero enviar fotos ou digitalizações de atividades impressas (`.png`, `.jpg`), para que o sistema transcreva o texto automaticamente e identifique se há excesso de poluição visual nas imagens da questão.

**Requisito Base:** RF-03
**Critérios de Aceitação:**
* **Dado que** o professor faz o upload de uma imagem de prova impressa,
* **Quando** o pipeline multimodal de OCR e Visão processar o arquivo,
* **Então** o sistema deve extrair o texto com fidelidade e integrá-lo à estrutura de questões da sessão.
* **E** o sistema deve emitir um indicador caso detecte alta densidade de elementos visuais concorrentes na imagem.
* **E** o sistema deve rejeitar imagens ilegíveis ou com resolução insuficiente informando claramente o motivo ao docente.

---

#### Épico 1.2: Mapeamento de Perfil Funcional por Características Atômicas
* **Tipo:** `type: epic` | **Pai:** Tema 1
* **Descrição:** Parametrização centrada nas características neurodivergentes específicas observadas em sala de aula, eliminando pacotes diagnósticos homogêneos.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint `POST /api/v1/materials/ocr` para upload de imagens de provas (`.png`, `.jpg`).
- [ ] **[RAG / IA]** Integração com pipeline OCR / modelo de visão computacional (VLM) para transcrição fidedigna.
- [ ] **[RAG / IA]** Módulo de análise heurística de poluição visual (densidade de bordas e contraste da imagem).
- [ ] **[Frontend]** Exibição de preview da imagem digitalizada com indicador de densidade visual na tela do docente.
- [ ] **[Testes]** Testes de acurácia de OCR sobre amostra de provas escaneadas em diferentes resoluções.

##### História 1.2.1: Seleção cirúrgica de características funcionais atômicas observadas
**História de Usuário**
Como professor, quero selecionar especificamente a característica funcional em que o aluno sente dificuldade (ex.: apenas dificuldade com comandos múltiplos na mesma frase, dentre as várias características associadas ao TDAH), para que a aplicação adapte estritamente esse ponto sem alterar o restante da atividade.

**Requisito Base:** RF-04, RNF-10
**Critérios de Aceitação:**
* **Dado que** o professor está na Etapa 2 de parametrização do perfil de aprendizagem,
* **Quando** ele selecionar uma ou mais características atômicas no catálogo funcional sem informar laudo médico,
* **Então** o sistema deve registrar exclusivamente as características marcadas como escopo permitido de adaptação.
* **E** as demais características não assinaladas do catálogo devem permanecer bloqueadas para intervenção.
* **E** o sistema deve impedir o avanço caso nenhuma característica funcional seja selecionada.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint `GET /api/v1/catalogs/characteristics` retornando o catálogo oficial de barreiras atômicas.
- [ ] **[Frontend]** Componente de seleção cirúrgica (Etapa 2) com filtros atômicos desacoplados de rótulo clínico.
- [ ] **[Frontend]** Bloqueio de avanço de fluxo com alerta acessível caso nenhuma característica seja selecionada.
- [ ] **[Testes]** Teste de renderização do catálogo e persistência do vetor de seleção no estado da sessão do cliente.

##### História 1.2.2: Registro de potencialidades, interesses e canais de engajamento
**História de Usuário**
Como professor, quero informar as potencialidades e áreas de interesse do estudante (ex.: facilidade com esquemas visuais, interesse por esportes ou natureza), para que os apoios pedagógicos utilizem âncoras motivacionais alinhadas à rede de engajamento do DUA.

**Requisito Base:** RF-05, RNF-06
**Critérios de Aceitação:**
* **Dado que** o professor selecionou as dificuldades funcionais do estudante,
* **Quando** ele preencher os seletores opcionais de potencialidades e interesses temáticos,
* **Então** o sistema deve anexar esses metadados ao contexto de geração vinculado ao Princípio I do DUA.
* **E** o uso de interesses não deve substituir os conceitos obrigatórios exigidos na avaliação.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Schema Pydantic para metadados de potencialidades, interesses e canais preferenciais (Princípio I DUA).
- [ ] **[Frontend]** Seletor de interesses temáticos (esportes, natureza, tecnologia) e campo de potencialidades na Etapa 2.
- [ ] **[RAG / IA]** Mapeamento dos metadados de potencialidade para injeção de contexto motivacional no prompt de adaptação.
- [ ] **[Testes]** Teste unitário verificando que a injeção de potencialidades não substitui os conceitos da trava curricular.

##### História 1.2.3: Transcrição de observações pedagógicas docentes via entrada de áudio
**História de Usuário**
Como professor com rotina sobrecarregada, quero gravar ou enviar um breve áudio relatando a dificuldade específica observada no aluno em sala, para que o sistema transcreva e sugira automaticamente os filtros de características correspondentes.

**Requisito Base:** RF-03, RF-05
**Critérios de Aceitação:**
* **Dado que** o professor aciona o recurso de observação por voz na parametrização,
* **Quando** um áudio de até 60 segundos for submetido ao módulo de transcrição,
* **Então** o sistema deve converter a fala em texto e pré-selecionar as características funcionais compatíveis no catálogo.
* **E** o professor deve poder confirmar ou desmarcar livremente qualquer sugestão antes de prosseguir.

---

#### Épico 1.3: Calibragem de Nível de Suporte e Travas Curriculares
* **Tipo:** `type: epic` | **Pai:** Tema 1
* **Descrição:** Controle docente sobre a intensidade do andaime cognitivo (*scaffolding*) e blindagem das habilidades curriculares avaliadas.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Endpoint `POST /api/v1/audio/transcribe` para recepção de áudio docente (formato WAV/WebM até 60s).
- [ ] **[RAG / IA]** Pipeline de transcrição de áudio para texto (Speech-to-Text) com descarte imediato de PII.
- [ ] **[RAG / IA]** Mapeador semântico de fala para sugestão de checkboxes correspondentes do catálogo funcional.
- [ ] **[Frontend]** Componente de gravação de áudio no navegador com botão de confirmação das sugestões identificadas.
- [ ] **[Testes]** Testes de transcrição em amostra de áudios simulados de relatos docentes em português.

##### História 1.3.1: Calibragem do nível de andaime cognitivo em 3 níveis (Leve, Moderado, Intensivo)
**História de Usuário**
Como professor, quero calibrar a intensidade de suporte da adaptação entre Nível 1 (Leve), Nível 2 (Moderado) e Nível 3 (Intensivo), para que eu possa dosar a ajuda proporcionalmente à necessidade do aluno sem comprometer o desenvolvimento da sua autonomia.

**Requisito Base:** RF-07, RNF-10
**Critérios de Aceitação:**
* **Dado que** o professor selecionou as características funcionais na Etapa 3,
* **Quando** ele escolher entre o Nível 1, Nível 2 ou Nível 3 de andaime cognitivo,
* **Então** o sistema deve configurar as diretrizes estruturais correspondentes (Nível 1: tipografia e destaque; Nível 2: chunking e checklists; Nível 3: passo a passo guiado e pausas).
* **E** a seleção de nível deve atuar unicamente sobre as características funcionais ativadas na História 1.2.1.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Definição das diretrizes de andaime nos schemas de configuração de sessão (Nível 1, 2 e 3).
- [ ] **[Frontend]** Componente visual de calibração de suporte na Etapa 3 com cards explicativos de cada nível.
- [ ] **[Frontend]** Feedback visual detalhando as transformações estruturais de cada intensidade (Leve, Moderada, Intensiva).
- [ ] **[Testes]** Teste de validação garantindo que a diretiva de nível seja atribuída estritamente às características ativadas.

##### História 1.3.2: Definição de Travas Curriculares Inegociáveis e alerta preventivo anti-muleta
**História de Usuário**
Como professor, quero definir explicitamente quais conceitos técnicos e habilidades da BNCC estão sendo avaliados na questão, para que a IA seja proibida de simplificar esses termos ou entregar a resposta pronta ao aluno.

**Requisito Base:** RF-08, RF-09
**Critérios de Aceitação:**
* **Dado que** o professor insere os conceitos-chave ou objetivo avaliativo no campo de Trava Curricular,
* **Quando** a parametrização for validada pelo sistema,
* **Então** esses conceitos devem ser marcados como invariantes obrigatórios para o Agente Auditor.
* **E** se o professor solicitar uma adaptação que contradiga diretamente a habilidade avaliada (ex.: pedir resumo interpretativo em questão que avalia interpretação de texto), o sistema deve emitir um alerta preventivo anti-muleta.

---

### Tema 2: Motor de Adaptação Inteligente e Revisão Docente
* **Tipo:** `type: theme`
* **Descrição:** Contempla a recuperação de evidências científicas via RAG, a orquestração do sistema multiagentes com isolamento de escopo, a auditoria de fidelidade e a interface comparativa de revisão docente (*Human-in-the-Loop*).
* **Épicos vinculados:** Épico 2.1, Épico 2.2.

---

#### Épico 2.1: Geração de Materiais Adaptados Baseada em Evidências
* **Tipo:** `type: epic` | **Pai:** Tema 2
* **Descrição:** Pipeline RAG e sistema multiagentes para adaptação cirúrgica fundamentada no DUA, manuais do MEC e literatura sobre Funções Executivas.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Schema Pydantic para invariantes da Trava Curricular (conceitos obrigatórios, habilidades BNCC).
- [ ] **[Frontend]** Campo de texto estruturado na Etapa 3 com exemplos de travas e aviso de validação cognitiva.
- [ ] **[RAG / IA]** Validador preventivo de perda cognitiva (alerta anti-muleta) cruzando nível solicitado com trava definida.
- [ ] **[Testes]** Teste automatizado de detecção de incompatibilidade pedagógica (ex.: trava de inferência vs. andaime simplificador).

##### História 2.1.1: Recuperação de estratégias psicopedagógicas baseadas em evidências (RAG)
**História de Usuário**
Como especialista em educação inclusiva, quero que as regras de adaptação aplicadas pelo sistema sejam recuperadas de uma base científica curada (DUA, MEC e artigos sobre Funções Executivas), para que nenhuma intervenção seja fruto de alucinação ou senso comum.

**Requisito Base:** RF-10, RNF-06
**Critérios de Aceitação:**
* **Dado que** uma requisição de adaptação contém características funcionais ativadas e um nível de suporte,
* **Quando** o Agente Estrategista consultar o banco vetorial RAG,
* **Então** o sistema deve retornar os trechos normativos e estratégias científicas mais relevantes com metadados de fonte e citação.
* **E** a busca vetorial deve filtrar estritamente os documentos correspondentes às características selecionadas pelo professor.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Ingestão do corpus curado (DUA/CAST, MEC, Funções Executivas) no ChromaDB com metadados por característica.
- [ ] **[RAG / IA]** Função de busca vetorial filtrada deterministicamente pelo `id_caracteristica` selecionado.
- [ ] **[RAG / IA]** Mapeador de contexto injetando trechos normativos e citações bibliográficas no prompt do Agente Estrategista.
- [ ] **[Testes]** Teste automatizado com RAGAS avaliando Context Precision e Faithfulness do trecho recuperado.

##### História 2.1.2: Extração de invariantes curriculares pelo Agente Extrator
**História de Usuário**
Como professor, quero que o sistema analise a questão original antes de adaptá-la e identifique seu núcleo conceitual e operação cognitiva exigida, para garantir que o rigor da avaliação seja mantido.

**Requisito Base:** RF-08, RF-11
**Critérios de Aceitação:**
* **Dado que** uma questão e suas Travas Curriculares são enviadas ao pipeline multiagentes,
* **Quando** o Agente Extrator Curricular processar o insumo,
* **Então** ele deve produzir uma lista estruturada de conceitos obrigatórios, termos técnicos intocáveis e o verbo de comando cognitivo (ex.: inferir, calcular, relacionar).
* **E** essa lista deve ser repassada como restrição rígida para os agentes subsequentes.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Prompt e contrato Pydantic do Agente Extrator Curricular em `src/iris/agents/curriculum_extractor.py`.
- [ ] **[RAG / IA]** Extração determinística de vocabulário técnico, conceitos centrais e verbos de comando taxonômicos.
- [ ] **[Backend]** Estrutura de passagem de estado em memória com a lista de invariantes intocáveis.
- [ ] **[Testes]** Teste com 10 questões padrão aferindo a integridade dos conceitos extraídos pelo agente.

##### História 2.1.3: Adaptação com isolamento estrito de escopo à característica selecionada
**História de Usuário**
Como professor, quero que o Agente Adaptador modifique exclusivamente os aspectos ligados à característica que selecionei para o aluno, para evitar que a prova sofra super-adaptação ou infantilização em áreas onde o estudante tem plena autonomia.

**Requisito Base:** RF-04, RF-11, RNF-07
**Critérios de Aceitação:**
* **Dado que** o professor selecionou apenas 1 característica funcional (ex.: múltiplos comandos conjugados) em Nível 2,
* **Quando** o Agente Adaptador reestruturar a questão com base no plano do RAG,
* **Então** ele deve aplicar o andaime estritamente na separação dos comandos em etapas/checklists.
* **E** deve manter 100% do vocabulário, densidade conceitual e demais estruturas não relacionadas à característica marcada.
* **E** o tempo total de processamento não deve exceder 15 segundos para Nível 1 e 40 segundos para Níveis 2 e 3.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Prompt e lógica de execução do Agente Adaptador em `src/iris/agents/adapter_agent.py`.
- [ ] **[RAG / IA]** Implementação da Regra de Isolamento de Escopo: restrição estrita das transformações à característica ativa.
- [ ] **[Backend]** Telemetria de latência e consumo de tokens por ciclo de geração multiagentes.
- [ ] **[Testes]** Teste de não-modificação de dimensões textuais não associadas à dificuldade selecionada.

##### História 2.1.4: Auditoria automatizada de retenção curricular (TRCC) e não-intrusividade
**História de Usuário**
Como professor, quero que um Agente Auditor verifique automaticamente se a questão adaptada preservou pelo menos 95% dos conceitos-chave e não entregou a resposta pronta, para que eu tenha segurança pedagógica no resultado gerado.

**Requisito Base:** RF-12, RNF-04, RNF-05
**Critérios de Aceitação:**
* **Dado que** o Agente Adaptador gerou uma minuta de questão adaptada,
* **Quando** o Agente Auditor avaliar a minuta frente ao material original e às Travas Curriculares,
* **Então** ele deve calcular a Taxa de Retenção de Conceitos-Chave (TRCC) e verificar se houve resolução indevida da questão.
* **E** deve validar que não houve modificações intrusivas para características não selecionadas pelo professor.
* **E** caso a TRCC seja inferior a 95%, deve acionar automaticamente um ciclo de auto-correção antes de exibir ao usuário.

---

#### Épico 2.2: Edição Lado a Lado e Exportação de Materiais
* **Tipo:** `type: epic` | **Pai:** Tema 2
* **Descrição:** Interface de revisão docente obrigatória (*Human-in-the-Loop*), transparência algorítmica das justificativas DUA e geração de arquivos finais para impressão.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Prompt e motor de auditoria do Agente Auditor em `src/iris/agents/auditor_agent.py`.
- [ ] **[Backend]** Implementação do cálculo da Taxa de Retenção de Conceitos-Chave (TRCC) e validação de nível (SAEN).
- [ ] **[Backend]** Mecanismo de Circuit Breaker (`max_retries = 2`) para auto-correção sem loop infinito.
- [ ] **[Testes]** Teste de rejeição automática e disparo de refinamento quando TRCC < 95%.

##### História 2.2.1: Visualização comparativa lado a lado com justificativas pedagógicas do DUA
**História de Usuário**
Como professor, quero visualizar na tela a questão original ao lado da questão adaptada, acompanhada da justificativa pedagógica de cada modificação feita com base no DUA, para que eu compreenda e valide tecnicamente a sugestão da IA.

**Requisito Base:** RF-10, RF-13, RNF-09
**Critérios de Aceitação:**
* **Dado que** o pipeline multiagentes concluiu a geração e auditoria da atividade,
* **Quando** a Etapa 5 de Revisão for carregada na interface web,
* **Então** o sistema deve exibir o material original na coluna da esquerda e a versão adaptada sincronizada na coluna da direita.
* **E** cada questão adaptada deve apresentar um cartão explicativo citando qual característica funcional foi tratada e qual diretriz do DUA/MEC fundamentou a alteração.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Componente da Etapa 5 com layout comparativo sincronizado lado a lado (Original vs. Adaptado).
- [ ] **[Frontend]** Cartões retráteis de justificativas pedagógicas com referências ao DUA e ao catálogo funcional.
- [ ] **[Frontend]** Indicadores visuais acessíveis destacando os andaimes cognitivos aplicados em cada questão.
- [ ] **[Testes]** Teste de responsividade e acessibilidade (WCAG 2.1 AA) em diferentes tamanhos de tela.

##### História 2.2.2: Edição livre docente em tempo real e aprovação Human-in-the-Loop
**História de Usuário**
Como professor autoridade pedagógica da turma, quero editar livremente qualquer palavra, formatação ou etapa da versão sugerida pela IA antes de finalizar, para garantir que o material reflita meu julgamento profissional.

**Requisito Base:** RF-13, RNF-09
**Critérios de Aceitação:**
* **Dado que** o professor está visualizando a comparação lado a lado,
* **Quando** ele alterar o texto da coluna adaptada ou clicar em aprovar questão,
* **Então** o sistema deve atualizar imediatamente a versão final em memória.
* **E** o botão de exportação final só deve ser liberado após a revisão/confirmação explícita do professor (*Human-in-the-Loop* obrigatório).

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Editor de texto inline em tempo real na coluna da atividade adaptada.
- [ ] **[Frontend]** Botão de aprovação formal por questão e confirmação final do docente (Human-in-the-Loop).
- [ ] **[Backend]** Endpoint `PUT /api/v1/sessions/{id}/review` persistindo em memória as edições manuais feitas pelo professor.
- [ ] **[Testes]** Teste garantindo que a exportação final permanece bloqueada até homologação explícita do docente.

##### História 2.2.3: Exportação do material adaptado em PDF diagramado econômico e DOCX editável
**História de Usuário**
Como professor de escola com recursos limitados de impressão, quero exportar a atividade aprovada em arquivo PDF pronto para impressão econômica (A4, tons de cinza, fonte acessível) ou em DOCX editável, para aplicá-la diretamente em sala de aula.

**Requisito Base:** RF-14
**Critérios de Aceitação:**
* **Dado que** o professor homologou a revisão da atividade adaptada,
* **Quando** ele selecionar a opção de exportação em `.pdf` ou `.docx`,
* **Então** o sistema deve gerar e iniciar o download imediato do documento diagramado com fontes sem serifa, espaçamento adequado e sem blocos densos de tinta escura.
* **E** o documento exportado para o aluno não deve conter rótulos clínicos ou menções a transtornos no cabeçalho para evitar exposição ou estigma em sala.

---

### Tema 3: Continuidade Pedagógica e Portabilidade
* **Tipo:** `type: theme`
* **Descrição:** Mecanismo descentralizado de memória pedagógica longitudinal por meio do Perfil Pedagógico Portátil local (`.json` / `.pdf`), garantindo continuidade entre bimestres e professores sem banco de dados centralizado.
* **Épicos vinculados:** Épico 3.1, Épico 3.2.

---

#### Épico 3.1: Criação e Gestão do Perfil Pedagógico Portátil
* **Tipo:** `type: epic` | **Pai:** Tema 3
* **Descrição:** Estruturação local de metadados anônimos sobre características funcionais observadas e histórico de eficácia das intervenções pedagógicas.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Compilador de PDF econômico em tons de cinza com tipografia sem serifa e cabeçalho neutro escolar.
- [ ] **[Backend]** Exportador para formato `.docx` com formatação limpa e editável via `python-docx`.
- [ ] **[Frontend]** Botões de download direto para PDF e DOCX com feedback visual de geração de arquivo.
- [ ] **[Testes]** Teste de validação estética do PDF gerado verificando ausência de rótulos clínicos ou estigmas no cabeçalho.

##### História 3.1.1: Geração de Perfil Pedagógico Portátil com identificador anônimo aleatório
**História de Usuário**
Como professor ou profissional do AEE, quero gerar um perfil portátil identificado apenas por um código aleatório anônimo (ex.: `aluno-8f7a2c1b`), para registrar os parâmetros funcionais que deram certo sem armazenar o nome ou dados pessoais do estudante na plataforma.

**Requisito Base:** RF-15, RNF-01
**Critérios de Aceitação:**
* **Dado que** o professor concluiu uma adaptação na plataforma,
* **Quando** ele optar por gerar um novo Perfil Pedagógico Portátil,
* **Então** o sistema deve criar uma estrutura em memória contendo um hash/código aleatório único, a data e as características funcionais selecionadas.
* **E** nenhum dado criado deve ser salvo em banco de dados no servidor da aplicação.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Gerador de identificador aleatório anônimo (hash UUID desvinculado de nomes).
- [ ] **[Backend]** Schema Pydantic oficial para o Perfil Pedagógico Portátil em `src/iris/schemas/portable_profile.py`.
- [ ] **[Frontend]** Opção na interface para inicializar e nomear anonimamente uma ficha de perfil portátil.
- [ ] **[Testes]** Inspeção em código e testes automatizados comprovando ausência de persistência em banco de dados central.

##### História 3.1.2: Registro de histórico de eficácia das intervenções por característica
**História de Usuário**
Como professor, quero registrar no perfil portátil se uma estratégia específica funcionou ou não para o aluno (ex.: "fragmentação em checklist teve alta eficácia"), para que nas próximas provas eu ou outros professores possamos evoluir a calibragem pedagógica.

**Requisito Base:** RF-15
**Critérios de Aceitação:**
* **Dado que** um Perfil Pedagógico Portátil está carregado na sessão,
* **Quando** o professor adicionar uma anotação de eficácia (`alta`, `média`, `baixa`) e observação pedagógica para a estratégia utilizada,
* **Então** o sistema deve anexar o registro ao histórico de intervenções do perfil.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Componente de registro de feedback pedagógico com seletores de eficácia (`alta`, `média`, `baixa`).
- [ ] **[Frontend]** Campo de texto livre para anotação de observações pedagógicas contextuais sobre a intervenção.
- [ ] **[Backend]** Estruturação do registro no array `historico_intervencoes` do perfil portátil em memória.
- [ ] **[Testes]** Teste unitário de inclusão e histórico ordenado de estratégias no objeto de perfil.

##### História 3.1.3: Bloqueio de inserção de dados clínicos e diagnósticos formais no perfil
**História de Usuário**
Como gestor escolar comprometido com a ética e a LGPD, quero que o sistema valide e proíba o armazenamento de CIDs médicos, laudos clínicos ou receitas de medicamentos dentro do Perfil Pedagógico Portátil, para manter o foco estritamente educacional e proteger o sigilo do menor.

**Requisito Base:** RF-15, RNF-03
**Critérios de Aceitação:**
* **Dado que** o sistema valida os dados para compor o Perfil Pedagógico Portátil,
* **Quando** o validador de schema e conteúdo inspecionar os campos do perfil,
* **Então** qualquer atributo extra não declarado ou padrão de código CID/termo médico restrito deve ser rejeitado com mensagem orientadora ao docente.

---

#### Épico 3.2: Exportação e Importação Descentralizada de Perfis
* **Tipo:** `type: epic` | **Pai:** Tema 3
* **Descrição:** Interoperabilidade local via arquivos `.json` (sistema) e `.pdf` (leitura humana para dossiê escolar).

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Validador estrito de schema Pydantic com `extra = "forbid"` rejeitando campos não declarados.
- [ ] **[Backend]** Filtro de termos clínicos restritos bloqueando padrões de CID médicos, remédios ou laudos médicos.
- [ ] **[Frontend]** Mensagem orientadora explicando que o perfil é estritamente pedagógico caso haja tentativa de inserção clínica.
- [ ] **[Testes]** Testes com dataset de dados clínicos sintéticos garantindo 100% de rejeição pelo validador.

##### História 3.2.1: Exportação local do Perfil Pedagógico Portátil em JSON e PDF
**História de Usuário**
Como professor do AEE, quero baixar o Perfil Pedagógico Portátil tanto em formato `.json` (para reuso futuro no sistema) quanto em `.pdf` (para anexar ao Plano de Desenvolvimento Individual na escola), para compartilhar as estratégias com os professores regentes.

**Requisito Base:** RF-15, RNF-01
**Critérios de Aceitação:**
* **Dado que** o professor solicita o salvamento do Perfil Pedagógico Portátil,
* **Quando** ele clicar em exportar perfil,
* **Então** o navegador deve baixar o arquivo `.json` validado pelo schema oficial e/ou o relatório síntese em `.pdf`.
* **E** toda a sessão temporária no servidor deve poder ser encerrada sem perda dos dados baixados localmente pelo professor.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Serializador para download local do arquivo estruturado `.json` e do relatório de síntese `.pdf`.
- [ ] **[Frontend]** Ação de exportação com acionamento de download nativo do arquivo no dispositivo do professor.
- [ ] **[Backend]** Destruição da sessão em memória logo após a finalização do download pelo cliente.
- [ ] **[Testes]** Teste de validação do arquivo JSON baixado contra o schema oficial do Perfil Portátil.

##### História 3.2.2: Importação e restauração de sessão a partir de arquivo JSON portátil
**História de Usuário**
Como professor regente iniciando um novo bimestre, quero fazer o upload do arquivo `.json` do Perfil Pedagógico Portátil recebido da coordenação/AEE, para que a plataforma preencha automaticamente as características funcionais e o nível de suporte recomendados para aquele código de aluno.

**Requisito Base:** RF-15, RNF-10
**Critérios de Aceitação:**
* **Dado que** o professor possui um arquivo `.json` de Perfil Pedagógico Portátil em seu computador,
* **Quando** ele importar o arquivo no início do fluxo da plataforma,
* **Então** o sistema deve validar a integridade do schema e pré-marcar automaticamente as características funcionais e o nível de andaime com histórico de alta eficácia.
* **E** caso o arquivo `.json` esteja corrompido ou fora do padrão, o sistema deve exibir erro amigável sem interromper o funcionamento da aplicação.

---

### Tema 4: Privacidade desde a Concepção (Privacy by Design) e Governança Científica
* **Tipo:** `type: theme`
* **Descrição:** Guardrails técnicos de proteção de dados pessoais (LGPD), arquitetura *Zero-Database*, curadoria modular de catálogos e validação quantitativa por métricas objetivas.
* **Épicos vinculados:** Épico 4.1, Épico 4.2.

---

#### Épico 4.1: Proteção de Dados e Conformidade LGPD
* **Tipo:** `type: epic` | **Pai:** Tema 4
* **Descrição:** Sanitização local de informações identificáveis (PII) e garantia de execução *stateless*.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Frontend]** Componente de upload e parsing do arquivo `.json` do Perfil Pedagógico Portátil no início do fluxo.
- [ ] **[Frontend]** Pré-seleção automática das características funcionais e do nível de andaime recomendados no arquivo.
- [ ] **[Backend]** Validação de schema no upload com tratamento de arquivos corrompidos ou com formato inválido.
- [ ] **[Testes]** Teste ponta a ponta de restauração de parâmetros da sessão a partir de arquivo JSON válido.

##### História 4.1.1: Detecção e descarte preventivo de PII na entrada de materiais
**História de Usuário**
Como responsável pela conformidade LGPD da instituição, quero que um filtro local detecte e remova preventivamente quaisquer dados de identificação pessoal (nomes próprios de docentes/estudantes, menções institucionais ou contatos) inseridos acidentalmente no material ou nas notas antes de qualquer envio a provedores externos de LLM, para impedir o tráfego de dados pessoais de menores.

**Requisito Base:** RNF-02
**Critérios de Aceitação:**
* **Dado que** o professor insere um texto de prova contendo cabeçalho antigo com nome de estudante ou escola,
* **Quando** o texto passar pelo gateway local de privacidade antes da chamada aos agentes de IA,
* **Então** o sanitizador deve substituir imediatamente os dados identificados por marcadores anônimos (`[ESTUDANTE]`, `[ESCOLA]`).
* **E** o payload enviado aos agentes de linguagem não deve conter os dados pessoais originais.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Módulo `src/iris/security/pii_scrubber.py` utilizando regex e modelo NER leve (ex.: spaCy pt-core-news-sm).
- [ ] **[Backend]** Substituição imediata e irreversível de nomes próprios e menções institucionais por marcadores genéricos.
- [ ] **[Testes]** Bateria de testes unitários com dataset de 50 cabeçalhos sintéticos de provas comprovando detecção >= 98%.
- [ ] **[Testes]** Teste de integridade comprovando que o payload enviado aos LLMs não possui dados identificáveis.

##### História 4.1.2: Execução em arquitetura stateless Zero-Database sem persistência de alunos
**História de Usuário**
Como arquiteto de software, quero garantir que o backend da plataforma opere de forma 100% *stateless* para dados de estudantes e sem nenhuma tabela de cadastro de alunos, para eliminar pela raiz o risco de vazamento de banco de dados centralizado.

**Requisito Base:** RNF-01
**Critérios de Aceitação:**
* **Dado que** uma sessão de adaptação é processada pela API do Íris,
* **Quando** a resposta final for entregue ao cliente web e a requisição encerrada,
* **Então** nenhum dado do material submetido ou do perfil funcional do estudante deve permanecer gravado em disco ou banco de dados no servidor.
* **E** o único armazenamento persistente permitido no backend deve ser a base vetorial somente-leitura de artigos científicos e manuais públicos (RAG).

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Arquitetura stateless no FastAPI com ciclo de vida de dados restrito à sessão em memória.
- [ ] **[Backend]** Configuração da aplicação sem tabelas de cadastro de alunos em banco central.
- [ ] **[Testes]** Script de auditoria em CI/CD inspecionando o repositório para certificar ausência de modelos ORM de estudantes.

##### História 4.1.3: Descarte preventivo de PII acidental e formatação de cabeçalho escolar neutro
**História de Usuário**
Como professor, quero que quaisquer dados de identificação pessoal inseridos acidentalmente no material didático (nomes de alunos em cabeçalhos antigos ou menções orais) sejam descartados imediatamente pelo sistema sem gerar mapeamento em memória, e que o material adaptado receba um cabeçalho escolar neutro em branco para preenchimento manual em sala de aula, garantindo privacidade absoluta (Zero-Retention) e prontidão para impressão.

**Requisito Base:** RNF-02, RF-14
**Critérios de Aceitação:**
* **Dado que** uma avaliação contendo nome de estudante ou cabeçalho identificado é inserida no sistema,
* **Quando** passar pela camada de sanitização preventiva,
* **Então** o sistema deve descartar irreversivelmente os dados identificadores substituindo-os por marcadores genéricos (`[ESTUDANTE]`, `[ESCOLA]`).
* **E** o sistema não deve armazenar nenhum dicionário ou mapa de restauração em memória (*Zero-Retention*).
* **E** na exportação para impressão (.pdf/.docx), o documento deve ser formatado com cabeçalho escolar neutro padronizado com linhas para preenchimento manual do estudante.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Gerador de cabeçalho escolar neutro padrão em branco para inserção automática nos exports.
- [ ] **[Backend]** Descarte preventivo de marcadores acidentais no fechamento da sessão sem dicionário de memória.
- [ ] **[Frontend]** Pré-visualização do cabeçalho limpo com linhas pontilhadas na tela de exportação de material.
- [ ] **[Testes]** Teste comprovando que o documento gerado sai formatado para preenchimento manual em sala de aula.

##### História 4.1.4: Auditoria de não-retenção de payloads sensíveis em logs de execução
**História de Usuário**
Como engenheiro de segurança e IA, quero que os logs de telemetria e depuração do servidor registrem apenas métricas operacionais (latência, contagem de tokens, status HTTP e scores TRCC) sem jamais gravar o conteúdo bruto das provas ou perfis, para manter conformidade integral com a LGPD.

**Requisito Base:** RNF-01, RNF-02
**Critérios de Aceitação:**
* **Dado que** o sistema registra eventos de execução da API e dos agentes,
* **Quando** uma requisição for processada com sucesso ou erro,
* **Então** os arquivos de log e console não devem exibir o texto das questões nem metadados identificáveis.

---

#### Épico 4.2: Curadoria e Validação Científica do Catálogo e Métricas
* **Tipo:** `type: epic` | **Pai:** Tema 4
* **Descrição:** Governança científica dos catálogos modulares de características neurodivergentes, análise exploratória de dados (EDA) e protocolo automatizado de avaliação quantitativa (Semana 2, Semana 3 e Semana 7).

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Configuração de formatadores de log (Loguru / Logging Python) filtrando payloads de requisições.
- [ ] **[Backend]** Registro exclusivo de metadados operacionais (status HTTP, latência em segundos, contagem de tokens, score TRCC).
- [ ] **[Testes]** Teste automatizado de inspeção de saída de logs assegurando ausência de textos de questões ou observações.

##### História 4.2.1: Estruturação de schema modular JSON/YAML para catálogos de características
**História de Usuário**
Como pesquisador e desenvolvedor da plataforma, quero que o catálogo de características funcionais seja carregado a partir de arquivos estruturados e validados por schema (`.json`), para que possamos expandir o suporte do TDAH para TEA e Dislexia adicionando novos catálogos baseados em evidências sem alterar o código-fonte do motor.

**Requisito Base:** RF-06, RNF-12
**Critérios de Aceitação:**
* **Dado que** um arquivo de catálogo de características é adicionado ao diretório `rag/catalogs/`,
* **Quando** a aplicação inicializar ou carregar os perfis disponíveis,
* **Então** o modelo Pydantic deve validar a presença obrigatória do identificador da característica, descrição prática observável, diretrizes de andaime para os Níveis 1, 2 e 3 e referências bibliográficas (DUA/MEC/artigos).
* **E** catálogos sem referência bibliográfica válida devem ser rejeitados na validação.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[Backend]** Modelo Pydantic `CharacteristicCatalog` e `CharacteristicItem` com validação de campos obrigatórios.
- [ ] **[RAG / IA]** Criação do catálogo oficial `catalogs/tdah_caracteristicas_funcionais.json` estruturado por evidências.
- [ ] **[Testes]** Testes de carga e validação garantindo que novos catálogos (TEA, Dislexia) sejam carregados sem alterar código.

##### História 4.2.2: Análise exploratória de dados (EDA do corpus e benchmark) e validação RAGAS
**História de Usuário**
Como pesquisador e avaliador técnico da Residência em IA, quero conduzir a análise exploratória de dados (EDA) sobre o corpus científico e o dataset de avaliações escolares (*Golden Benchmark*), além de executar a suíte automatizada de benchmark comparando LLM Puro vs. Íris (RAG + Multiagentes), para justificar empiricamente as decisões técnicas de chunking/modelos e comprovar retenção curricular (TRCC >= 95%) e conformidade RAGAS.

**Requisito Base:** RF-10, RNF-04, RNF-05, RNF-06
**Critérios de Aceitação:**
* **Dado que** o corpus de documentos científicos (DUA, MEC, Funções Executivas) é carregado na Semana 2,
* **Quando** a EDA do corpus for executada,
* **Então** o sistema deve gerar gráficos de balanceamento temático por característica atômica e histograma de tokens por seção para fundamentar empiricamente o `chunk_size`.
* **E** dado o dataset de avaliações escolares (*Golden Benchmark* de 30 a 50 questões),
* **Quando** for realizada a EDA inicial das questões,
* **Então** o sistema deve mapear a distribuição de baseline do Flesch-Kincaid PT-BR e densidade de comandos conjugados.
* **E** quando o script de benchmark da Semana 3 comparar LLM Puro vs. Íris,
* **Então** deve gerar relatório estatístico comprovando $\text{TRCC} \ge 95\%$, *Faithfulness* $\ge 0.90$ e preservação curricular estrita.

### Tarefas de Implementação Técnica (INVEST)
- [ ] **[RAG / IA]** Notebook e scripts da EDA 1 (corpus científico RAG: balanceamento por característica e tokens).
- [ ] **[RAG / IA]** Dataset de 30 a 50 questões escolares (Golden Benchmark) e scripts da EDA 2 (baseline Flesch PT-BR e comandos).
- [ ] **[RAG / IA]** Script do benchmark comparativo da Semana 3 comparando LLM Puro vs. Íris (RAG + Multiagentes).
- [ ] **[Testes]** Relatório automatizado de validação comprovando TRCC >= 95% e métricas RAGAS (Faithfulness >= 0.90).

##### História 4.2.3: Camada de abstração híbrida de LLM (Ollama Local + API Externa) e setup do Llama 3
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
- [ ] **[Testes]** Testes unitários em `tests/core/test_llm_client.py` validando fallback, extração JSON e coleta de métricas de latência/tokens.

##### História 4.2.4: Unificação de dependências no pyproject.toml, estrutura base src/iris e ponte com o módulo RAG
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
- [x] **[Infra]** Unificar as dependências de `rag/iris-rag/pacote/requirements.txt` nos grupos do `pyproject.toml`, habilitar empacotamento editável de `src/iris` e atualizar o `uv.lock`.
- [x] **[Backend]** Criar a estrutura de diretórios e pacotes base em `src/iris/` (`api`, `core`, `schemas`, `security`, `parsers`, `agents`, `rag`) e diretório `tests/`.
- [x] **[RAG / IA]** Criar adaptador em `src/iris/rag/` encapsulando `consultar.buscar` e `gerar.responder` sem depender de `cwd` relativo.
- [x] **[Infra]** Criar arquivo `.env.example` padronizado na raiz do repositório.

##### História 4.2.5: Curadoria e estruturação do dataset Golden Benchmark de questões escolares (Fundamental II e Médio)
**História de Usuário**
Como pesquisador responsável pela validação experimental da Semana 3, quero um dataset estruturado (*Golden Benchmark*) contendo de 30 a 50 questões escolares reais de Ensino Fundamental II e Médio anotadas com suas respectivas Travas Curriculares e características-alvo, para viabilizar a EDA 2 (legibilidade Flesch-Kincaid PT-BR) e o experimento comparativo entre LLM Puro vs. Íris (RAG).

**Requisito Base:** RF-08, RF-10, RNF-04, RNF-05
**Critérios de Aceitação:**
* **Dado que** o experimento da Semana 3 e a EDA 2 exigem avaliações escolares reais (e não apenas dúvidas teóricas sobre TDAH),
* **Quando** o dataset `data/benchmarks/questoes_escolares_v1.json` for carregado,
* **Então** cada questão deve conter: `id`, `disciplina`, `ano_escolar`, `habilidade_bncc`, `enunciado_original`, `alternativas` (quando objetiva), `conceitos_trava_curricular` (lista de termos/conceitos inegociáveis), `operacao_cognitiva` e `id_caracteristica_alvo`.
* **E** o conjunto deve conter no mínimo 30 questões públicas (ex.: INEP/SAEB, ENEM, bancos abertos alinhados à BNCC) cobrindo enunciados longos, múltiplos comandos conjugados e textos de apoio densos.

### Tarefas de Implementação Técnica (INVEST)
- [x] **[RAG / IA]** Definir schema e loader `GoldenQuestion` em `src/iris/eval/benchmark.py` para o dataset de questões escolares.
- [x] **[RAG / IA]** Coletar e anotar 30 questões escolares em `data/golden_benchmark.json` com comandos conjugados e metadados.
- [x] **[RAG / IA]** Implementar funções utilitárias de cálculo do Índice Flesch-Kincaid PT-BR e contagem de verbos de comando por enunciado para alimentar a EDA 2 (#40).

