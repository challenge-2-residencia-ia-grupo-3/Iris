---
name: challenge2-cbl-pedagogical-adapter
description: >-
  Diretrizes arquiteturais, restrições obrigatórias do Challenge 2 (Residência em IA),
  metodologia CBL, regras de negócio do MVP (Barreiras Funcionais > Rótulo Clínico,
  Andaime Cognitivo em 3 Níveis, Travas Curriculares e Privacy by Design / Zero-Database),
  roadmap de 7 semanas e backlog estruturado. Ative esta skill sempre que for planejar,
  documentar, arquitetar, codificar ou avaliar qualquer componente da Plataforma
  Inteligente de Adaptação de Materiais Pedagógicos para alunos neurodivergentes (TDAH).
---

# Skill: Challenge 2 — Plataforma Inteligente de Adaptação de Materiais Pedagógicos

Esta skill define as regras de negócio inegociáveis, as restrições metodológicas (CBL) e os padrões arquiteturais do **Grupo 3 — Challenge 2 da Residência em IA (UnB / Lab Livre / Eldorado / Softex / MCTI)**.

Todo código, prompt, agente, pipeline RAG, interface ou documentação gerado neste repositório **DEVE** obedecer estritamente às diretrizes abaixo.

---

## 1. Estrutura CBL (Challenge Based Learning) — Semana 1

* **Big Idea:** Qualidade de Vida (*"Empoderando pessoas com IA para compreender melhor, decidir melhor e viver melhor"*).
* **Contexto do Problema:** Professores da educação básica enfrentam forte sobrecarga de trabalho e falta de tempo hábil para adaptar provas, atividades e materiais didáticos para alunos neurodivergentes (iniciando o recorte por **TDAH**). Quando tentam usar LLMs genéricos, o modelo apenas "resume" ou simplifica excessivamente o texto, empobrecendo o currículo, eliminando a habilidade avaliada e gerando subexposição cognitiva (*efeito muleta*) no aluno.
* **Essential Question:** *"Como podemos apoiar professores na decisão e adaptação personalizada de materiais pedagógicos para alunos neurodivergentes, reduzindo a sobrecarga docente sem comprometer os objetivos de aprendizagem?"*
* **Guiding Questions (Perguntas Norteadoras):**
  1. Quais etapas do processo de adaptação de materiais didáticos consomem mais tempo e esforço cognitivo dos professores no dia a dia escolar?
  2. Como traduzir as barreiras funcionais de aprendizagem observadas em sala de aula (como no TDAH) em critérios práticos de adaptação, sem reduzir o aluno a um diagnóstico clínico padronizado?
  3. Onde está o limite entre remover uma barreira de acesso (linguística, visual ou executiva) e simplificar excessivamente o conteúdo a ponto de invalidar a habilidade curricular avaliada?
  4. Como calibrar diferentes níveis de suporte pedagógico em um material para que o professor possa decidir a intensidade ideal de ajuda sem comprometer o desenvolvimento da autonomia do aluno?

---

## 2. Restrições Obrigatórias do Challenge (Checklist de Conformidade)

Antes de implementar qualquer funcionalidade, valide os 5 critérios obrigatórios:

1. **Entender o problema antes da solução:** Nenhuma feature técnica existe isolada da dor docente ou da necessidade funcional do estudante.
2. **Justificar todas as decisões técnicas:** Toda escolha de arquitetura, modelo de linguagem/visão, estratégia de *chunking*, banco vetorial e engenharia de prompt deve ser documentada e tecnicamente justificada (ex: via ADRs — *Architecture Decision Records*).
3. **Explicitar riscos, viés e limitações:**
   * O sistema **NÃO diagnostica alunos**, não emite laudos e não substitui avaliação clínica/psicopedagógica.
   * O sistema atua exclusivamente no apoio à decisão pedagógica com revisão docente obrigatória (**Human-in-the-Loop**).
4. **Validar com métricas objetivas:**
   * **Taxa de Retenção de Conceitos-Chave (TRCC):** Garantia quantitativa de que os conceitos obrigatórios da trava curricular foram mantidos.
   * **Índice de Legibilidade Flesch-Kincaid (PT-BR):** Medição da adequação linguística dos enunciados.
   * **Aderência Estrutural ao Nível Solicitado:** Verificação objetiva das regras do Nível 1, 2 ou 3.
   * **Métricas RAGAS:** *Faithfulness* (fidelidade às evidências científicas recuperadas), *Context Precision* e *Answer Relevancy*.
5. **Utilizar evidências confiáveis:** Todas as estratégias de adaptação devem ser ancoradas em fontes científicas e normativas curadas:
   * Desenho Universal para a Aprendizagem (DUA / CAST);
   * Manuais e diretrizes de educação inclusiva do MEC / BNCC;
   * Literatura científica revisada por pares sobre **Funções Executivas no TDAH** (memória de trabalho, controle inibitório, flexibilidade cognitiva, autorregulação).

---

## 3. Escopo Técnico do MVP e Três Pilares Inegociáveis

### Pilar 1: Características Singulares > Pacote Clínico (Intervenção Cirúrgica)
* **Proibição de Estereótipo Clínico em Bloco:** O sistema jamás aplica um "template fechado para a condição".
* **Intervenção Cirúrgica por Característica:** Se uma condição como o TDAH possui 15 características hipotéticas e o professor assinala apenas 1 dificuldade observada em sala, a IA atua estritamente sobre essa dimensão, preservando 100% da autonomia e do formato original nas outras 14.
* **Regra de Isolamento de Escopo:** O pipeline multiagentes é estritamente proibido de introduzir andaimes ou simplificações não solicitadas para traços que o professor não selecionou.
* **Modularidade:** Catálogo atômico modular (`.json` / `.yaml`) desacoplado do código-fonte para expansão progressiva a outros perfis (TEA, Dislexia).

### Pilar 2: Andaime Cognitivo (Scaffolding) em 3 Níveis + Trava Curricular
* **Nível 1 (Adaptação Leve):** Ajustes de formatação, organização visual, destaque de palavras-chave (negrito/marcadores) e clareza das instruções, preservando **100% da estrutura e complexidade** original.
* **Nível 2 (Adaptação Moderada):** Divisão da atividade em etapas explícitas (*checklists* passo a passo), *chunking* (fragmentação estruturada) de enunciados ou textos longos e organização de informações de apoio/glossário contextual.
* **Nível 3 (Adaptação Intensiva):** Reorganização significativa da apresentação (exibição de uma etapa por vez, sugestão de pausas ativas/autorregulação, suporte estruturado como organizadores gráficos e formas compatíveis de demonstrar a mesma aprendizagem).
* **Trava Curricular Inegociável:** O professor define quais habilidades, objetivos e conteúdos são inegociáveis. **Regra de Ouro:** Se a atividade avalia interpretação de texto, resolução de problema matemático ou inferência causal, a IA é estritamente proibida de dar a resposta ou fazer a inferência pelo aluno (prevenção do *efeito muleta*).

### Pilar 3: Privacy by Design (Zero-Database de Alunos & LGPD)
* **Arquitetura Stateless para Dados de Estudantes:** É terminantemente **proibido** criar tabela/banco de dados centralizado com cadastro de alunos, nomes de menores ou histórico clínico identificável.
* **Sanitização / Detector de PII na Entrada:** Todo material submetido pelo professor deve passar por um filtro local de detecção e anonimização de PII (nomes próprios, CPFs, nomes de escolas, telefones, e-mails) **antes** de ser enviado a qualquer provedor externo de LLM.
* **Perfil Pedagógico Portátil (`.json` / `.pdf`):** Para garantir continuidade pedagógica ao longo dos bimestres ou entre diferentes professores sem violar o princípio *Zero-Database*:
  * O sistema exporta e importa localmente um arquivo estruturado (`.json` para reimportação no sistema e `.pdf` para leitura humana).
  * Identificado apenas por um **código aleatório anônimo** (gerenciado localmente pelo professor/escola).
  * Contém: barreiras funcionais mapeadas, estratégias que funcionaram, estratégias que não funcionaram e observações pedagógicas (estritamente separadas de dados clínicos).

---

## 4. Alinhamento com o Roadmap de 7 Semanas

Toda evolução do repositório deve respeitar a cadência de entregáveis semanais:

| Semana | Foco do Challenge | Entregável Técnico no Repositório |
| :---: | :--- | :--- |
| **1** | Problema, stakeholders, riscos e métricas | Documentação CBL, mapa de stakeholders, matriz de riscos/LGPD, protocolo de métricas e estrutura do repositório. |
| **2** | Base de conhecimento e recuperação | Curadoria científica (MEC, DUA, artigos sobre Funções Executivas/TDAH), pipeline de ingestão/chunking e primeiro mecanismo **RAG**. |
| **3** | Comparação LLM Puro vs. RAG | Experimento quantitativo provando com métricas que o RAG preserva o currículo e aplica andaimes baseados em evidências, enquanto o LLM puro apenas resume/empobrece. |
| **4** | Sistema Multiagentes | Orquestração de agentes especializados: (1) *Agente Extrator Curricular*, (2) *Agente Estrategista Psicopedagógico via RAG*, (3) *Agente Adaptador* e (4) *Agente Auditor de Fidelidade/Nível*. |
| **5** | Multimodalidade | Agentes multimodais: upload de fotos/scans de provas impressas via OCR/Visão, análise de poluição visual em questões com imagens e entrada de observações docentes por áudio. |
| **6** | Integração completa | Aplicação Web funcional com fluxo guiado de 5 etapas: *Identificar Material → Definir Perfil Funcional → Definir Nível e Travas → Gerar Adaptação → Revisar Lado a Lado e Exportar Material/Perfil Portátil*. |
| **7** | Testes e refinamento | Bateria completa de testes automatizados, coleta final de métricas objetivas (TRCC, Flesch-Kincaid, RAGAS), refinamento e relatório final + apresentação. |

---

## 5. Backlog Estruturado de Referência (Temas → Épicos → Histórias)

Para consultar o mapeamento completo de Temas, Épicos e Histórias de Usuário (US 1.1.1 a US 4.2.2) durante o desenvolvimento, leia o arquivo de referência:
* [Referência do Backlog e Critérios de Aceite](./references/backlog_e_metricas.md)
