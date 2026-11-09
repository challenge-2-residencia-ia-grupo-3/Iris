# Requisitos Não Funcionais (RNF) — Íris

Este documento estabelece os **Requisitos Não Funcionais** da plataforma Íris, definindo as restrições arquiteturais, critérios de qualidade, parâmetros de segurança, conformidade com a LGPD e metas de validação quantitativa estabelecidas pelo Challenge 2.

---

## 1. Privacidade, Segurança e Conformidade Regulatória (LGPD)

### RNF-01: Arquitetura Stateless de Dados de Estudantes (*Zero-Database*)
* **Categoria:** Privacidade e Governança de Dados (LGPD).
* **Descrição:** A arquitetura do sistema deve ser estritamente *stateless* em relação a dados identificáveis de estudantes. É terminantemente vedada a criação de bancos de dados centrais (SQL/NoSQL) em servidores que armazenem nomes, cadastros ou históricos individualizados de menores de idade.
* **Critério de Aceite:** O banco de dados do sistema (se houver) deve restringir-se a vetores de conhecimento científico (RAG) e tabelas de configuração estática; nenhuma tabela de estudantes deve existir no schema da aplicação.
* **Validação:** Inspeção de segurança e auditoria de schema de dados nos pipelines de CI/CD.

### RNF-02: Sanitização Preventiva e Descarte Imediato de PII (Zero-Retention Scrubber)
* **Categoria:** Segurança da Informação e Privacidade.
* **Descrição:** A plataforma não solicita nem processa dados cadastrais de estudantes. Para prevenir a exposição de dados decorrente de inserções acidentais pelo docente (como cabeçalhos de provas antigas contendo nomes de alunos ou citações de nomes próprios em notas orais transcritas), todo insumo submetido deve passar por um módulo local de detecção e descarte imediato de PII (*Personally Identifiable Information*) antes de qualquer transmissão para APIs externas de modelos de linguagem.
* **Critério de Aceite:** Nomes próprios de pessoas e identificadores escolares devem ser substituídos de forma irreversível por marcadores genéricos estruturados (ex.: `[ESTUDANTE]`, `[ESCOLA]`). O módulo não deve gerar nem manter tabelas ou dicionários de reidratação em memória no servidor (*Zero-Retention*). A taxa de descarte preventivo de identificadores em testes sintéticos deve ser $\ge 98\%$.
* **Validação:** Testes unitários com dataset controlado de avaliações contendo nomes e cabeçalhos escolares sintéticos.

### RNF-03: Desacoplamento entre Dados Pedagógicos e Dados Clínicos
* **Categoria:** Ética e Proteção de Dados Sensíveis.
* **Descrição:** Os arquivos do Perfil Pedagógico Portátil (`.json` e `.pdf`) não devem armazenar laudos médicos, CID, histórico de medicação ou relatórios clínicos confidenciais. O arquivo deve conter exclusivamente **descrições de barreiras funcionais pedagógicas** e o histórico de intervenções didáticas adotadas.
* **Critério de Aceite:** O schema JSON do perfil portátil deve rejeitar qualquer atributo destinado a dados médicos ou diagnósticos clínicos formais.
* **Validação:** Validação estrita por Pydantic Schema com rejeição de campos não declarados (`extra = "forbid"`).

---

## 2. Confiabilidade Pedagógica, Métricas e Avaliação Objetiva

### RNF-04: Taxa de Retenção de Conceitos-Chave (TRCC)
* **Categoria:** Integridade Curricular.
* **Descrição:** O sistema deve assegurar quantitativamente que as travas curriculares e conceitos obrigatórios da atividade original permaneçam intactos no material adaptado em qualquer um dos três níveis.
* **Critério de Aceite:**
  $$\text{TRCC} = \frac{|\text{Conceitos da Trava Curricular no Material Adaptado}|}{|\text{Conceitos da Trava Curricular no Material Original}|} \ge 0.95 \quad (95\%)$$
* **Validação:** Execução automatizada no pipeline de testes e pelo Agente Auditor em tempo de execução via contagem e verificação semântica de entidades-chave.

### RNF-05: Monitoramento de Complexidade Sintática (Flesch-Kincaid PT-BR)
* **Categoria:** Adequação Linguística.
* **Descrição:** O sistema deve mensurar o impacto das adaptações na legibilidade textual utilizando a fórmula do Índice de Facilidade de Leitura Flesch calibrada para o Português Brasileiro (Martins et al.):
  $$\text{Flesch}_{\text{PT-BR}} = 248.835 - (1.015 \times \text{ASL}) - (84.6 \times \text{ASW})$$
  *(onde $\text{ASL}$ é o comprimento médio das frases e $\text{ASW}$ é o número de sílabas por palavra)*.
* **Critério de Aceite:** O material adaptado em Nível 2 e Nível 3 deve apresentar redução estatisticamente significativa do $\text{ASL}$ (frases mais curtas e diretas), aumentando o índice Flesch em direção à faixa "Fácil" / "Muito Fácil" de compreensão de comandos, sem reduzir a presença dos termos técnicos curriculares (conforme RNF-04).
* **Validação:** Script de avaliação de legibilidade integrado ao módulo `evaluations/metrics/readability_ptbr.py`.

### RNF-06: Qualidade e Rastreabilidade do Pipeline RAG (RAGAS)
* **Categoria:** Precisão e Explicabilidade do Modelo.
* **Descrição:** O mecanismo de recuperação e geração aumentada por evidências deve ser avaliado sistematicamente pelo framework RAGAS (*Retrieval Augmented Generation Assessment*).
* **Critérios de Aceite:**
  * **Faithfulness (Fidelidade):** $\ge 0.90$ (garantia de que as intervenções sugeridas têm respaldo estrito nos manuais do DUA/MEC recuperados, sem invenção de estratégias).
  * **Context Precision (Precisão de Contexto):** $\ge 0.85$ (relevância dos trechos pedagógicos recuperados para as barreiras funcionais informadas).
  * **Answer Relevancy (Relevância da Resposta):** $\ge 0.88$ (aderência do material adaptado às restrições fornecidas pelo professor).
* **Validação:** Benchmark quantitativo executado nas Semanas 3 e 7 contra dataset anotado por especialistas pedagógicos.

---

## 3. Desempenho e Eficiência Operacional

### RNF-07: Tempo de Resposta da Pipeline de Adaptação (Latência)
* **Categoria:** Desempenho.
* **Descrição:** O processamento completo de uma atividade didática padrão (composta por até 5 questões ou até 1.500 palavras) pelo pipeline multiagentes não deve exceder os limites operacionais toleráveis em ambiente docente.
* **Critério de Aceite:**
  * Adaptação em Nível 1: Tempo total de resposta $\le 15$ segundos.
  * Adaptação em Níveis 2 e 3 (com orquestração completa e auditoria): Tempo total $\le 40$ segundos para requisições síncronas.
* **Validação:** Testes de carga e medição de latência ponta a ponta na API.

### RNF-08: Eficiência no Uso de Tokens e Contexto
* **Categoria:** Otimização de Recursos.
* **Descrição:** Os prompts dos agentes devem utilizar técnicas de *few-shot prompting* compacto e injeção estruturada de contexto recuperado pelo RAG, evitando saturação desnecessária da janela de contexto dos modelos.
* **Critério de Aceite:** O volume de tokens consumidos em cada ciclo de adaptação de 5 questões não deve exceder $8.000$ tokens no total da cadeia de agentes.
* **Validação:** Telemetria de consumo de tokens por ciclo de geração.

---

## 4. Usabilidade e Acessibilidade

### RNF-09: Conformidade com Acessibilidade Digital (WCAG 2.1 AA)
* **Categoria:** Acessibilidade.
* **Descrição:** A interface web da plataforma Íris deve seguir os critérios de sucesso das Diretrizes de Acessibilidade para Conteúdo Web (WCAG 2.1) em nível AA.
* **Critério de Aceite:**
  * Contraste mínimo de texto de $4.5:1$ em relação ao fundo.
  * Suporte integral a navegação por teclado (sem armadilhas de foco).
  * Tipografia sem serifa com dimensionamento escalável e espaçamento configurável.
  * Disponibilização de modo escuro e modo de alto contraste para docentes com fotossensibilidade.
* **Validação:** Auditoria automatizada via Lighthouse / Axe Core com score de acessibilidade $\ge 95/100$.

### RNF-10: Carga Cognitiva Reduzida na Interface do Professor
* **Categoria:** Experiência do Usuário (UX).
* **Descrição:** O fluxo de trabalho deve ser estruturado em no máximo 5 passos guiados e lineares (*Identificação de Material $\rightarrow$ Barreiras $\rightarrow$ Calibragem de Nível e Travas $\rightarrow$ Adaptação $\rightarrow$ Revisão Lado a Lado*).
* **Critério de Aceite:** O professor deve ser capaz de parametrizar e submeter uma atividade em menos de 3 minutos de interação na interface.
* **Validação:** Testes de usabilidade com gravação de tempo de tarefa em amostra de usuários.

---

## 5. Arquitetura, Portabilidade e Manutenibilidade

### RNF-11: Gerenciamento Moderno de Dependências via UV
* **Categoria:** Engenharia de Software e Reprodutibilidade.
* **Descrição:** Todo o ciclo de vida de empacotamento, resolução de dependências e execução de ferramentas do projeto deve ser orquestrado exclusivamente via **`uv`**, garantindo resolução determinística e velocidade de instalação.
* **Critério de Aceite:** Existência de arquivo `pyproject.toml` compatível com os padrões PEP 517/518/621 e `uv.lock` com hashes criptográficos validados. Instalação e execução de comandos exclusivamente por `uv run` ou `uv sync`.
* **Validação:** Verificação em ambiente limpo executando `uv sync` com sucesso em tempo inferior a 30 segundos.

### RNF-12: Modularidade e Desacoplamento dos Componentes
* **Categoria:** Arquitetura de Software.
* **Descrição:** A arquitetura deve separar rigidamente o motor de regras de negócio, a base vetorial RAG, os agentes de linguagem e a camada de interface web.
* **Critério de Aceite:** Cada componente deve possuir interfaces abstratas e tipadas (Pydantic / protocolos Python). A substituição de um modelo de LLM ou do banco vetorial não deve exigir alterações nas regras pedagógicas de andaime ou nos contratos da API.
* **Validação:** Testes unitários isolados com mock da camada de LLM e do banco vetorial.

