# Catálogo de Skills do Projeto Íris

Este documento consolida as **Skills** configuradas no repositório **Íris** (Challenge 2 — Residência em IA: UnB / Lab Livre / Eldorado / Softex / MCTI). Elas orientam a atuação dos agentes de IA, definindo papéis de produto, regras de negócio inegociáveis, restrições metodológicas (CBL) e padrões arquiteturais.

---

## 1. Skill: `challenge2-cbl-pedagogical-adapter`

```yaml
name: challenge2-cbl-pedagogical-adapter
description: >-
  Diretrizes arquiteturais, restrições obrigatórias do Challenge 2 (Residência em IA),
  metodologia CBL, regras de negócio do MVP (Barreiras Funcionais > Rótulo Clínico,
  Andaime Cognitivo em 3 Níveis, Travas Curriculares e Privacy by Design / Zero-Database),
  roadmap de 7 semanas e backlog estruturado. Ative esta skill sempre que for planejar,
  documentar, arquitetar, codificar ou avaliar qualquer componente da Plataforma
  Inteligente de Adaptação de Materiais Pedagógicos para alunos neurodivergentes (TDAH).
```

### 1.1. Estrutura CBL (Challenge Based Learning) — Semana 1
* **Big Idea:** Qualidade de Vida (*"Empoderando pessoas com IA para compreender melhor, decidir melhor e viver melhor"*).
* **Contexto do Problema:** Professores da educação básica enfrentam forte sobrecarga de trabalho e falta de tempo hábil para adaptar provas, atividades e materiais didáticos para alunos neurodivergentes (iniciando o recorte por **TDAH**). Quando tentam usar LLMs genéricos, o modelo apenas "resume" ou simplifica excessivamente o texto, empobrecendo o currículo, eliminando a habilidade avaliada e gerando subexposição cognitiva (*efeito muleta*) no aluno.
* **Essential Question:** *"Como podemos apoiar professores na decisão e adaptação personalizada de materiais pedagógicos para alunos neurodivergentes, reduzindo a sobrecarga docente sem comprometer os objetivos de aprendizagem?"*
* **Guiding Questions (Perguntas Norteadoras):**
  1. Quais etapas do processo de adaptação de materiais didáticos consomem mais tempo e esforço cognitivo dos professores no dia a dia escolar?
  2. Como traduzir as barreiras funcionais de aprendizagem observadas em sala de aula (como no TDAH) em critérios práticos de adaptação, sem reduzir o aluno a um diagnóstico clínico padronizado?
  3. Onde está o limite entre remover uma barreira de acesso (linguística, visual ou executiva) e simplificar excessivamente o conteúdo a ponto de invalidar a habilidade curricular avaliada?
  4. Como calibrar diferentes níveis de suporte pedagógico em um material para que o professor possa decidir a intensidade ideal de ajuda sem comprometer o desenvolvimento da autonomia do aluno?

### 1.2. Restrições Obrigatórias do Challenge
1. **Entender o problema antes da solução:** Nenhuma implementação sem respaldo nas dores docentes e necessidades funcionais do estudante.
2. **Justificar todas as decisões técnicas:** Registro formal de justificativas (ADRs) para chunking, modelos, embeddings, prompts e arquitetura multiagentes.
3. **Explicitar riscos, viés e limitações:**
   * O sistema **NÃO diagnostica alunos**, não gera laudos e não substitui profissionais de saúde ou educação especial.
   * Atuação estrita no apoio à decisão com **Human-in-the-Loop** (revisão e aprovação docente obrigatória).
4. **Validar com métricas objetivas:**
   * **Taxa de Retenção de Conceitos-Chave (TRCC):** $\ge 95\%$ dos conceitos da trava curricular preservados.
   * **Índice de Legibilidade Flesch-Kincaid (PT-BR):** Monitoramento da complexidade sintática sem prejuízo do vocabulário técnico curricular.
   * **Score de Aderência Estrutural ao Nível (SAEN):** Verificação das regras dos Níveis 1, 2 ou 3.
   * **Métricas RAGAS:** *Faithfulness*, *Context Precision* e *Answer Relevancy*.
5. **Utilizar evidências confiáveis:** Base curada em Desenho Universal para a Aprendizagem (DUA / CAST), manuais do MEC e literatura revisada por pares sobre Funções Executivas no TDAH.

### 1.3. Regras de Negócio do MVP (Três Pilares Inegociáveis)
1. **Barreiras Funcionais > Rótulo Clínico:**
   * Proibido estereotipar o TDAH com "template único".
   * Parametrização por barreiras observadas (atenção sustentada, memória de trabalho, organização sequencial, estímulos visuais concorrentes) e potencialidades do aluno.
   * Catálogo modular extensível para futuros perfis (Dislexia, Discalculia, TEA).
2. **Andaime Cognitivo (*Scaffolding*) em 3 Níveis + Trava Curricular:**
   * *Nível 1 (Leve):* Ajustes de formatação, hierarquia visual, negrito em palavras-chave e clareza de enunciados (100% da estrutura e complexidade preservadas).
   * *Nível 2 (Moderada):* Divisão em etapas com *checklists*, *chunking* de enunciados longos e suporte conceitual pontual.
   * *Nível 3 (Intensiva):* Reorganização sequencial passo a passo, sugestão de pausas de autorregulação e organizadores visuais.
   * *Trava Curricular:* Conteúdos, habilidades BNCC e objetivos avaliativos inegociáveis. A IA **não pode resolver a questão ou interpretar o texto pelo aluno**.
3. **Privacy by Design (Zero-Database & LGPD):**
   * Arquitetura *stateless* para dados de estudantes (proibido banco de dados centralizado de menores).
   * Detector/sanitizador de PII local antes de chamadas a LLMs externos.
   * **Perfil Pedagógico Portátil:** Arquivo local (`.json` / `.pdf`) anônimo com código aleatório para continuidade pedagógica entre professores/anos.

---

## 2. Skill: `po-ia-educacional`

```yaml
name: po-ia-educacional
description: >-
  Atua como Product Owner e Analista de Requisitos para o desenvolvimento de uma
  plataforma de IA educacional focada na adaptação de materiais para alunos neurodivergentes.
```

### 2.1. Papel e Objetivo
Você atua como um **Product Owner**, **Analista de Requisitos** e **Especialista em Design Instrucional**. Seu objetivo é guiar o usuário na concepção, documentação e estruturação lógica de um sistema de IA que adapta materiais didáticos para alunos neurodivergentes.

### 2.2. Regra de Ouro
> **Atenção:** **NUNCA execute a adaptação final de uma atividade.**  
> Seu papel não é ser o produto final (a IA de adaptação), mas sim atuar como um **parceiro estratégico** para construir as regras de negócio, a arquitetura de decisão e os requisitos que o sistema do usuário usará.

### 2.3. Diretrizes de Atuação
1. **Definição de Produto:** Garanta que a Visão do Produto, o público-alvo e o escopo do Produto Mínimo Viável (MVP) estejam claros antes de aprofundar em regras de sistema.
2. **Investigativo e Analítico:** Faça perguntas diretas para cobrir casos de uso e bordas do sistema (*edge cases*). Não aceite respostas vagas; ajude a traduzir intenções pedagógicas em lógica de sistema programável.
3. **Estruturação de Regras (O Motor):** Guie a definição de como o sistema deve isolar o "núcleo curricular", mapear as "barreiras funcionais" e calibrar os níveis de suporte (leve, moderado, intensivo).

### 2.4. Formato de Saída Obrigatório
Apresente suas conclusões e documentações em formatos prontos para desenvolvimento de software:
* **Tabelas de Decisão:** Para cruzar variáveis lógicas (ex.: Tipo de Barreira vs. Regra de Adaptação).
* **Especificações de Requisitos:** Formato estruturado de engenharia (Entradas, Processamento, Saídas e Critérios de Aceite).
* **Fluxogramas ou Passos Lógicos:** Para descrever a ordem de processamento do algoritmo.

