# Metodologia CBL — Challenge 2

O projeto **Íris** é desenvolvido no âmbito da **Residência em IA (UnB / Lab Livre / Eldorado / Softex / MCTI)**, orientado pelo framework pedagógico **Challenge Based Learning (CBL)**.

---

## 1. Concepção CBL (Semana 1)

### Big Idea
**Qualidade de Vida**  
> *"Empoderando pessoas com IA para compreender melhor, decidir melhor e viver melhor."*

### Essential Question (Pergunta Essencial)
> *"Como podemos ajudar professores a adaptar materiais didáticos para alunos com diferentes necessidades de aprendizagem, reduzindo o trabalho docente sem prejudicar o aprendizado?"*

### Contexto e Formulação do Problema
Professores encontram-se sobrecarregados com demandas burocráticas, aulas e correções, sem tempo hábil para planejar e elaborar versões customizadas de materiais didáticos para estudantes com perfis atípicos de aprendizagem (com foco prioritário no **TDAH** e arquitetura modular preparada para expansão em **TEA** e **Dislexia**). Como consequência:

* **Acompanhamento comprometido:** O professor tem dificuldade de manter o ritmo coletivo da turma e, simultaneamente, oferecer a atenção individualizada demandada pelo aluno neurodivergente.
* **Sobrecarga cognitiva do aluno:** Estudantes enfrentam enunciados excessivamente longos, estruturas textuais densas e carência de apoios visuais ou escalonamento de instruções.
* **Prejuízo educacional:** O estudante atípico tem seu aprendizado bloqueado pela barreira de acessibilidade e pelo formato da atividade, não por falta de capacidade intelectual.

### Impactos Principais
* **Sobrecarga docente:** Gargalo operacional no trabalho manual de reescrita, síntese, diagramação e busca avulsa de adaptações.
* **Risco de desmotivação:** Estudantes neurodivergentes sentem-se frustrados ou expostos diante de materiais inacessíveis ou de simplificações infantilizadas (*efeito muleta*).
* **Insegurança curricular:** Dificuldade docente em flexibilizar enunciados mantendo o rigor conceitual exigido pelas matrizes curriculares e competências da BNCC.

---

## 2. Guiding Questions (Perguntas Norteadoras e Diagnóstico)

### 1. Quais etapas da adaptação de materiais consomem mais tempo dos professores?
* **Diagnóstico e resposta:** Identificar as dificuldades dos alunos, reescrever textos extensos, estruturar instruções por etapas, buscar recursos visuais e revisar para garantir que o rigor conceitual não foi perdido.

### 2. Como transformar as dificuldades de aprendizagem em critérios de adaptação sem exigir laudos clínicos?
* **Diagnóstico e resposta:** Oferecer filtros funcionais e pedagógicos diretamente ligados a necessidades práticas (textos mais curtos, linguagem simplificada, passos sequenciais, recursos visuais e destaque de palavras-chave), sem burocracia médica.

### 3. Como simplificar o material sem prejudicar o conteúdo curricular?
* **Diagnóstico e resposta:** Preservar rigorosamente os conceitos essenciais e os objetivos da atividade (por meio de Travas Curriculares), transformando exclusivamente a carga de leitura, a diagramação e a estratégia de explicação dos conteúdos.

### 4. Como definir o nível de ajuda adequado para cada atividade?
* **Diagnóstico e resposta:** Permitir que o professor calibre o suporte entre adaptações leves, moderadas ou intensivas (andaimes cognitivos em 3 níveis), preservando sua autonomia conforme a necessidade pedagógica e a meta da aula.

---

## 3. Mapeamento de Stakeholders

| Stakeholder | Papel no Ecossistema | Interesses e Necessidades | Influência / Impacto |
| :--- | :--- | :--- | :--- |
| **Professores Regentes** | Usuários primários da solução | Economizar tempo hábil, preservar a autonomia pedagógica e gerar materiais inclusivos com rapidez. | Alta / Alto |
| **Alunos Neurodivergentes** | Beneficiários finais diretos | Receber materiais didáticos claros, acessíveis, sem sobrecarga cognitiva e em paridade com a turma. | Alta / Alto |
| **Equipe de AEE / Salas de Recursos** | Co-avaliadores pedagógicos | Validar critérios técnicos de acessibilidade e alinhar práticas ao Plano de Desenvolvimento Individual (PDI). | Média / Alto |
| **Coordenação Pedagógica e Direção** | Gestão educacional | Garantir equidade no processo de ensino, cumprimento legal das diretrizes de inclusão e desempenho. | Alta / Médio |
| **Famílias dos Estudantes** | Comunidade escolar | Assegurar que o estudante receba estímulo pedagógico digno, sem exclusão ou desamparo acadêmico. | Média / Médio |
| **Equipe Técnica e IA** | Desenvolvimento do produto | Entregar interface intuitiva, tempos rápidos de resposta, conformidade estrita com a LGPD e precisão nos prompts. | Alta / Médio |

---

## 4. Premissas e Matriz de Riscos

### 4.1. Premissas do Projeto
1. O professor possui o material curricular original em formato de texto digital ou passível de cópia/digitalização.
2. A tomada de decisão final é sempre humana: a IA atua como copiloto de apoio, mantendo o professor como mediador e autoridade pedagógica (*Human-in-the-Loop*).
3. Os professores possuem capacidade de observação empírica para mapear barreiras de aprendizado dos alunos sem depender exclusivamente de diagnósticos clínicos formais.
4. Modelos de linguagem modernos (LLMs) possuem capacidade semântica para reestruturar sintaxe e diagramação sem comprometer a precisão dos conteúdos conceituais, desde que guiados por RAG e travas curriculares.

### 4.2. Matriz de Riscos e Mitigações

| Risco Identificado | Probabilidade | Impacto | Estratégia de Mitigação |
| :--- | :---: | :---: | :--- |
| **Alucinação ou simplificação excessiva do conteúdo curricular** | Média | Alto | Arquitetura de prompts estruturada com few-shot learning, ancoragem RAG em literatura confiável (DUA/MEC), Travas Curriculares inegociáveis e auditoria automatizada de TRCC. |
| **Resistência ou desconfiança docente quanto ao uso de IA** | Alta | Médio | Transparência algorítmica: exibição clara da justificativa pedagógica de cada adaptação, interface lado a lado para revisão livre e posicionamento da ferramenta como copiloto do professor. |
| **Limitações técnicas e escassez de infraestrutura na escola** | Média | Alto | Layout de exportação econômico para impressão (tons de cinza, padrão A4, sem preenchimentos densos de tinta), processamento em nuvem e interface compatível com dispositivos móveis. |
| **Vazamento ou armazenamento indevido de dados de estudantes** | Baixa | Crítico | Arquitetura estritamente *stateless* (*Zero-Database* de alunos); detector local de PII; nenhuma informação cadastral ou histórico médico do aluno é requisitado ou registrado. |

---

## 5. Indicadores e Métricas de Sucesso

### Métricas de Negócio e Impacto Docente
* **Redução de tempo docente:** Redução mínima de **60%** no tempo despendido pelos professores no preparo e formatação de avaliações adaptadas, medido em testes controlados pré e pós-adoção.
* **Taxa de aceitação e confiabilidade:** Mais de **80%** das sugestões de adaptação geradas pelo copiloto mantidas ou aproveitadas pelos professores com ajustes mínimos, demonstrando alta assertividade pedagógica.
* **Engajamento e autonomia do aluno:** Índice favorável superior a **75%** nos relatos de professores sobre melhora na autonomia, concentração e resolução autônoma das atividades pelos estudantes beneficiados.

### Métricas Técnicas de IA
* **Taxa de Retenção de Conceitos-Chave (TRCC):** $\ge 95\%$ dos conceitos da trava curricular preservados.
* **Índice de Facilidade de Leitura Flesch (PT-BR):** Redução controlada do comprimento médio de frases ($\text{ASL}$) sem remoção do vocabulário técnico curricular.
* **Métricas RAGAS:** *Faithfulness* $\ge 0.90$, *Context Precision* $\ge 0.85$ e *Answer Relevancy* $\ge 0.88$.

---

## 6. Roadmap de 7 Semanas

| Semana | Foco Temático do Challenge | Entregável Técnico no Íris |
| :---: | :--- | :--- |
| **Semana 1** | Problema, stakeholders, riscos e métricas | Documentação CBL, visão do produto, levantamento de RF/RNF, governança LGPD, personas nominais e configuração do projeto com UV e MkDocs. |
| **Semana 2** | Base de conhecimento e recuperação | Curadoria de corpus científico (MEC, DUA, Funções Executivas), pipeline de chunking semântico e primeiro mecanismo **RAG**. |
| **Semana 3** | Comparação LLM vs. RAG | Estudo experimental comparativo quantitativo (LLM Puro vs. RAG) validando a retenção curricular e aplicação de evidências. |
| **Semana 4** | Sistema Multiagentes | Orquestração do time de agentes especializados (Extrator Curricular, Estrategista RAG, Adaptador e Auditor de Fidelidade). |
| **Semana 5** | Multimodalidade | Processamento multimodal: OCR de provas impressas/manuscritas, detecção de poluição visual e transcrição de áudio docente. |
| **Semana 6** | Integração Completa | Aplicação web funcional integrada de ponta a ponta (Fluxo guiado de 5 etapas + Edição Lado a Lado + Perfil Portátil). |
| **Semana 7** | Testes e Refinamento | Bateria completa de testes automatizados, coleta das métricas objetivas (TRCC, Flesch PT-BR, RAGAS), relatório final e apresentação. |
