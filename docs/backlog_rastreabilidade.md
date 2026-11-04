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
| `#34` | **História 4.1.1** | Detecção e anonimização local de PII na entrada de materiais | Épico 4.1 / Tema 4 | **RNF-02**, RF-01 | **História 1.1.1** (RF-01) | `priority: must` | `scope: privacy-lgpd`, `scope: api` |
| `#35` | **História 4.1.2** | Execução em arquitetura stateless Zero-Database sem persistência de alunos | Épico 4.1 / Tema 4 | **RNF-01**, RNF-12 | *Nenhuma (Restrição Arquitetural Base)* | `priority: must` | `scope: privacy-lgpd`, `scope: infra-eval` |
| `#36` | **História 4.1.3** | Re-hidratação local de marcadores anonimizados antes da exportação | Épico 4.1 / Tema 4 | **RNF-02**, **RF-14** | **História 4.1.1** (RNF-02), **História 2.2.3** (RF-14) | `priority: could` | `scope: privacy-lgpd`, `scope: front-web` |
| `#37` | **História 4.1.4** | Auditoria de não-retenção de payloads sensíveis em logs de execução | Épico 4.1 / Tema 4 | **RNF-01**, **RNF-02** | **História 4.1.1** (RNF-02), **História 4.1.2** (RNF-01) | `priority: must` | `scope: privacy-lgpd`, `scope: infra-eval` |
| `#39` | **História 4.2.1** | Estruturação de schema modular JSON/YAML para catálogos de características | Épico 4.2 / Tema 4 | **RF-06**, RNF-11, RNF-12 | *Nenhuma (Fundação do Catálogo)* | `priority: must` | `scope: rag`, `scope: api` |
| `#40` | **História 4.2.2** | Validação automatizada de rastreabilidade bibliográfica e métricas RAGAS | Épico 4.2 / Tema 4 | **RF-10**, **RNF-04**, **RNF-05**, **RNF-06** | **História 2.1.1** (RF-10), **História 2.1.4** (RF-12) | `priority: must` | `scope: infra-eval`, `scope: rag` |

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
| **RNF-02** | Sanitização Local e Detecção Automatizada de PII | Tema 4 | Épico 4.1 | **História 4.1.1** (`#34`), **História 4.1.3** (`#36`), **História 4.1.4** (`#37`) |
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

##### História 1.2.2: Registro de potencialidades, interesses e canais de engajamento
**História de Usuário**
Como professor, quero informar as potencialidades e áreas de interesse do estudante (ex.: facilidade com esquemas visuais, interesse por esportes ou natureza), para que os apoios pedagógicos utilizem âncoras motivacionais alinhadas à rede de engajamento do DUA.

**Requisito Base:** RF-05, RNF-06
**Critérios de Aceitação:**
* **Dado que** o professor selecionou as dificuldades funcionais do estudante,
* **Quando** ele preencher os seletores opcionais de potencialidades e interesses temáticos,
* **Então** o sistema deve anexar esses metadados ao contexto de geração vinculado ao Princípio I do DUA.
* **E** o uso de interesses não deve substituir os conceitos obrigatórios exigidos na avaliação.

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

##### História 1.3.1: Calibragem do nível de andaime cognitivo em 3 níveis (Leve, Moderado, Intensivo)
**História de Usuário**
Como professor, quero calibrar a intensidade de suporte da adaptação entre Nível 1 (Leve), Nível 2 (Moderado) e Nível 3 (Intensivo), para que eu possa dosar a ajuda proporcionalmente à necessidade do aluno sem comprometer o desenvolvimento da sua autonomia.

**Requisito Base:** RF-07, RNF-10
**Critérios de Aceitação:**
* **Dado que** o professor selecionou as características funcionais na Etapa 3,
* **Quando** ele escolher entre o Nível 1, Nível 2 ou Nível 3 de andaime cognitivo,
* **Então** o sistema deve configurar as diretrizes estruturais correspondentes (Nível 1: tipografia e destaque; Nível 2: chunking e checklists; Nível 3: passo a passo guiado e pausas).
* **E** a seleção de nível deve atuar unicamente sobre as características funcionais ativadas na História 1.2.1.

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

##### História 2.1.1: Recuperação de estratégias psicopedagógicas baseadas em evidências (RAG)
**História de Usuário**
Como especialista em educação inclusiva, quero que as regras de adaptação aplicadas pelo sistema sejam recuperadas de uma base científica curada (DUA, MEC e artigos sobre Funções Executivas), para que nenhuma intervenção seja fruto de alucinação ou senso comum.

**Requisito Base:** RF-10, RNF-06
**Critérios de Aceitação:**
* **Dado que** uma requisição de adaptação contém características funcionais ativadas e um nível de suporte,
* **Quando** o Agente Estrategista consultar o banco vetorial RAG,
* **Então** o sistema deve retornar os trechos normativos e estratégias científicas mais relevantes com metadados de fonte e citação.
* **E** a busca vetorial deve filtrar estritamente os documentos correspondentes às características selecionadas pelo professor.

##### História 2.1.2: Extração de invariantes curriculares pelo Agente Extrator
**História de Usuário**
Como professor, quero que o sistema analise a questão original antes de adaptá-la e identifique seu núcleo conceitual e operação cognitiva exigida, para garantir que o rigor da avaliação seja mantido.

**Requisito Base:** RF-08, RF-11
**Critérios de Aceitação:**
* **Dado que** uma questão e suas Travas Curriculares são enviadas ao pipeline multiagentes,
* **Quando** o Agente Extrator Curricular processar o insumo,
* **Então** ele deve produzir uma lista estruturada de conceitos obrigatórios, termos técnicos intocáveis e o verbo de comando cognitivo (ex.: inferir, calcular, relacionar).
* **E** essa lista deve ser repassada como restrição rígida para os agentes subsequentes.

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

##### História 2.2.1: Visualização comparativa lado a lado com justificativas pedagógicas do DUA
**História de Usuário**
Como professor, quero visualizar na tela a questão original ao lado da questão adaptada, acompanhada da justificativa pedagógica de cada modificação feita com base no DUA, para que eu compreenda e valide tecnicamente a sugestão da IA.

**Requisito Base:** RF-10, RF-13, RNF-09
**Critérios de Aceitação:**
* **Dado que** o pipeline multiagentes concluiu a geração e auditoria da atividade,
* **Quando** a Etapa 5 de Revisão for carregada na interface web,
* **Então** o sistema deve exibir o material original na coluna da esquerda e a versão adaptada sincronizada na coluna da direita.
* **E** cada questão adaptada deve apresentar um cartão explicativo citando qual característica funcional foi tratada e qual diretriz do DUA/MEC fundamentou a alteração.

##### História 2.2.2: Edição livre docente em tempo real e aprovação Human-in-the-Loop
**História de Usuário**
Como professor autoridade pedagógica da turma, quero editar livremente qualquer palavra, formatação ou etapa da versão sugerida pela IA antes de finalizar, para garantir que o material reflita meu julgamento profissional.

**Requisito Base:** RF-13, RNF-09
**Critérios de Aceitação:**
* **Dado que** o professor está visualizando a comparação lado a lado,
* **Quando** ele alterar o texto da coluna adaptada ou clicar em aprovar questão,
* **Então** o sistema deve atualizar imediatamente a versão final em memória.
* **E** o botão de exportação final só deve ser liberado após a revisão/confirmação explícita do professor (*Human-in-the-Loop* obrigatório).

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

##### História 3.1.1: Geração de Perfil Pedagógico Portátil com identificador anônimo aleatório
**História de Usuário**
Como professor ou profissional do AEE, quero gerar um perfil portátil identificado apenas por um código aleatório anônimo (ex.: `aluno-8f7a2c1b`), para registrar os parâmetros funcionais que deram certo sem armazenar o nome ou dados pessoais do estudante na plataforma.

**Requisito Base:** RF-15, RNF-01
**Critérios de Aceitação:**
* **Dado que** o professor concluiu uma adaptação na plataforma,
* **Quando** ele optar por gerar um novo Perfil Pedagógico Portátil,
* **Então** o sistema deve criar uma estrutura em memória contendo um hash/código aleatório único, a data e as características funcionais selecionadas.
* **E** nenhum dado criado deve ser salvo em banco de dados no servidor da aplicação.

##### História 3.1.2: Registro de histórico de eficácia das intervenções por característica
**História de Usuário**
Como professor, quero registrar no perfil portátil se uma estratégia específica funcionou ou não para o aluno (ex.: "fragmentação em checklist teve alta eficácia"), para que nas próximas provas eu ou outros professores possamos evoluir a calibragem pedagógica.

**Requisito Base:** RF-15
**Critérios de Aceitação:**
* **Dado que** um Perfil Pedagógico Portátil está carregado na sessão,
* **Quando** o professor adicionar uma anotação de eficácia (`alta`, `média`, `baixa`) e observação pedagógica para a estratégia utilizada,
* **Então** o sistema deve anexar o registro ao histórico de intervenções do perfil.

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

##### História 3.2.1: Exportação local do Perfil Pedagógico Portátil em JSON e PDF
**História de Usuário**
Como professor do AEE, quero baixar o Perfil Pedagógico Portátil tanto em formato `.json` (para reuso futuro no sistema) quanto em `.pdf` (para anexar ao Plano de Desenvolvimento Individual na escola), para compartilhar as estratégias com os professores regentes.

**Requisito Base:** RF-15, RNF-01
**Critérios de Aceitação:**
* **Dado que** o professor solicita o salvamento do Perfil Pedagógico Portátil,
* **Quando** ele clicar em exportar perfil,
* **Então** o navegador deve baixar o arquivo `.json` validado pelo schema oficial e/ou o relatório síntese em `.pdf`.
* **E** toda a sessão temporária no servidor deve poder ser encerrada sem perda dos dados baixados localmente pelo professor.

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

##### História 4.1.1: Detecção e anonimização local de PII na entrada de materiais
**História de Usuário**
Como responsável pela conformidade LGPD da instituição, quero que um filtro local detecte e mascare automaticamente nomes próprios, CPFs, e-mails, telefones e nomes de escolas presentes no cabeçalho das provas antes de qualquer envio a APIs externas de LLM, para impedir o vazamento de dados pessoais de menores.

**Requisito Base:** RNF-02
**Critérios de Aceitação:**
* **Dado que** o professor insere um texto de prova contendo cabeçalho com nome de aluno, escola ou CPF,
* **Quando** o texto passar pelo gateway local de privacidade antes da chamada aos agentes de IA,
* **Então** o sanitizador deve substituir 100% dos padrões estruturados (CPF, e-mail, telefone) e nomes identificados por tokens anônimos (`[ALUNO_01]`, `[ESCOLA_01]`).
* **E** o payload enviado ao provedor externo de LLM não deve conter os dados originais identificados.

##### História 4.1.2: Execução em arquitetura stateless Zero-Database sem persistência de alunos
**História de Usuário**
Como arquiteto de software, quero garantir que o backend da plataforma opere de forma 100% *stateless* para dados de estudantes e sem nenhuma tabela de cadastro de alunos, para eliminar pela raiz o risco de vazamento de banco de dados centralizado.

**Requisito Base:** RNF-01
**Critérios de Aceitação:**
* **Dado que** uma sessão de adaptação é processada pela API do Íris,
* **Quando** a resposta final for entregue ao cliente web e a requisição encerrada,
* **Então** nenhum dado do material submetido ou do perfil funcional do estudante deve permanecer gravado em disco ou banco de dados no servidor.
* **E** o único armazenamento persistente permitido no backend deve ser a base vetorial somente-leitura de artigos científicos e manuais públicos (RAG).

##### História 4.1.3: Re-hidratação local de marcadores anonimizados antes da exportação
**História de Usuário**
Como professor, quero que os cabeçalhos institucionais que foram mascarados durante o processamento na nuvem sejam restaurados localmente no meu navegador na hora de gerar o PDF final, para que a prova impressa saia pronta para uso.

**Requisito Base:** RNF-02, RF-14
**Critérios de Aceitação:**
* **Dado que** o sanitizador substituiu o nome da escola por `[ESCOLA_01]` antes de enviar ao LLM,
* **Quando** o texto adaptado retornar para a interface de revisão do professor,
* **Então** o mapa local em memória deve restaurar o termo original exclusivamente para a visualização e exportação local pelo docente.

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
* **Descrição:** Governança científica dos catálogos modulares de características neurodivergentes e protocolo automatizado de avaliação quantitativa (Semana 3 e Semana 7).

##### História 4.2.1: Estruturação de schema modular JSON/YAML para catálogos de características
**História de Usuário**
Como pesquisador e desenvolvedor da plataforma, quero que o catálogo de características funcionais seja carregado a partir de arquivos estruturados e validados por schema (`.json`), para que possamos expandir o suporte do TDAH para TEA e Dislexia adicionando novos catálogos baseados em evidências sem alterar o código-fonte do motor.

**Requisito Base:** RF-06, RNF-12
**Critérios de Aceitação:**
* **Dado que** um arquivo de catálogo de características é adicionado ao diretório `rag/catalogs/`,
* **Quando** a aplicação inicializar ou carregar os perfis disponíveis,
* **Então** o modelo Pydantic deve validar a presença obrigatória do identificador da característica, descrição prática observável, diretrizes de andaime para os Níveis 1, 2 e 3 e referências bibliográficas (DUA/MEC/artigos).
* **E** catálogos sem referência bibliográfica válida devem ser rejeitados na validação.

##### História 4.2.2: Validação automatizada de rastreabilidade bibliográfica e métricas RAGAS
**História de Usuário**
Como avaliador técnico da Residência em IA, quero executar uma suíte automatizada de benchmark que compare o LLM Puro contra o pipeline RAG do Íris medindo TRCC, legibilidade Flesch-Kincaid PT-BR e métricas RAGAS (*Faithfulness*, *Context Precision* e *Answer Relevancy*), para comprovar quantitativamente a eficácia e segurança pedagógica da solução.

**Requisito Base:** RF-10, RNF-04, RNF-05, RNF-06
**Critérios de Aceitação:**
* **Dado que** o dataset de testes contendo questões curriculares padronizadas é executado na suíte de avaliação (`evaluations/`),
* **Quando** o script de benchmark comparar as saídas do LLM Puro vs. Íris (RAG + Multiagentes),
* **Então** o sistema deve gerar um relatório quantitativo comprovando $\text{TRCC} \ge 95\%$, *Faithfulness* $\ge 0.90$ e superioridade estatística na preservação curricular frente ao modelo genérico.

