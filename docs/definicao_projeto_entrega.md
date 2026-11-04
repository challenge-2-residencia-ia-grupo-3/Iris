# ENTREGA DA SEMANA: DEFINIÇÃO DO PROJETO

## Plataforma Web de Adaptação de Materiais Pedagógicos com IA (Íris)

> **Programa:** Residência em Inteligência Artificial Aplicada (UnB / Lab Livre / Eldorado / Softex / MCTI)  
> **Challenge:** 2 — Big Idea: Qualidade de Vida  
> **Grupo:** 3

---

## 1. Cenário Escolhido

O cenário educacional brasileiro reflete uma crescente e indispensável inclusão de estudantes neurodivergentes, abrangendo indivíduos no Espectro Autista (TEA), com Transtorno do Déficit de Atenção com Hiperatividade (TDAH) e Dislexia no ensino regular. Contudo, essa ampliação no número de matrículas não veio acompanhada de suporte estrutural e operacional suficiente ao corpo docente.

Professores da educação básica lidam rotineiramente com jornadas exaustivas, turmas numerosas e escassez de recursos de apoio pedagógico. Embora possuam preparo e sensibilidade diagnóstica para mapear as barreiras de aprendizagem presentes na sala de aula, a execução prática, que exige converter atividades genéricas em múltiplos materiais customizados, torna-se inviável pela falta crônica de tempo hábil.

Nesse contexto insere-se o **Desenho Universal para a Aprendizagem (DUA)**: em vez de esperar que o estudante se adapte à rigidez do material, o currículo e as atividades didáticas devem oferecer múltiplos meios de representação, ação, expressão e engajamento. 

A solução concebida — **Íris** — é uma ferramenta web potencializada por Inteligência Artificial Generativa e recuperação de evidências científicas (RAG), estruturada para atuar como **copiloto pedagógico**: o professor fornece a atividade base e seleciona critérios de adaptação fundamentados em **barreiras funcionais observáveis** (com foco prioritário de validação no **TDAH** e catálogo modular expansível para **TEA** e **Dislexia**). A aplicação devolve a versão adaptada em até 3 níveis de andaime cognitivo, acompanhada das respectivas justificativas pedagógicas à luz do DUA e garantindo a preservação integral da habilidade avaliada por meio de **Travas Curriculares Inegociáveis**.

---

## 2. Problema

### 2.1. Formulação do Problema
Professores encontram-se sobrecarregados com demandas burocráticas, aulas e correções, sem tempo hábil para planejar e elaborar versões customizadas de materiais didáticos para estudantes com perfis atípicos de aprendizagem. Como consequência:

* **Acompanhamento comprometido:** O professor tem dificuldade de manter o ritmo coletivo da turma e, simultaneamente, oferecer a atenção individualizada demandada pelo aluno neurodivergente.
* **Sobrecarga cognitiva do aluno:** Estudantes enfrentam enunciados excessivamente longos, estruturas textuais densas e carência de apoios visuais ou escalonamento de instruções.
* **Prejuízo educacional:** O estudante atípico tem seu aprendizado bloqueado pela barreira de acessibilidade e pelo formato da atividade, não por falta de capacidade intelectual.

### 2.2. Impactos Principais
* **Sobrecarga docente:** Gargalo operacional no trabalho manual de reescrita, síntese, diagramação e busca avulsa de adaptações.
* **Risco de desmotivação e subexposição cognitiva (*efeito muleta*):** Estudantes neurodivergentes sentem-se frustrados ou expostos diante de materiais inacessíveis ou de simplificações infantilizadas que eliminam o desafio pedagógico.
* **Insegurança curricular:** Dificuldade docente em flexibilizar enunciados mantendo o rigor conceitual exigido pelas matrizes curriculares e competências da BNCC.

---

## 3. Essential Question e Guiding Questions

### ESSENTIAL QUESTION DA EQUIPE
> *"Como podemos ajudar professores a adaptar materiais didáticos para alunos com diferentes necessidades de aprendizagem, reduzindo o trabalho docente sem prejudicar o aprendizado?"*

### 3.1. Guiding Questions e Diagnósticos

#### 1. Quais etapas da adaptação de materiais consomem mais tempo dos professores?
* **Diagnóstico e resposta:** Identificar as dificuldades dos alunos, reescrever textos extensos, estruturar instruções por etapas, buscar recursos visuais e revisar para garantir que o rigor conceitual não foi perdido.

#### 2. Como transformar as dificuldades de aprendizagem em critérios de adaptação sem exigir laudos clínicos?
* **Diagnóstico e resposta:** Oferecer filtros funcionais e pedagógicos diretamente ligados a necessidades práticas (textos mais curtos, linguagem simplificada, passos sequenciais, recursos visuais e destaque de palavras-chave), sem burocracia médica e com parametrização modular baseada no DUA.

#### 3. Como simplificar o material sem prejudicar o conteúdo curricular?
* **Diagnóstico e resposta:** Preservar rigorosamente os conceitos essenciais e os objetivos da atividade por meio de **Travas Curriculares**, transformando exclusivamente a carga de leitura, a diagramação e a estratégia de explicação dos conteúdos.

#### 4. Como definir o nível de ajuda adequado para cada atividade?
* **Diagnóstico e resposta:** Permitir que o professor calibre o suporte entre adaptações **leves (Nível 1)**, **moderadas (Nível 2)** ou **intensivas (Nível 3)**, preservando sua autonomia conforme a necessidade pedagógica e a meta da aula.

---

## 4. Stakeholders

O mapeamento a seguir sintetiza os grupos de interesse diretamente envolvidos ou impactados pelo ecossistema da solução:

| Stakeholder | Papel no Ecossistema | Interesses e Necessidades | Influência / Impacto |
| :--- | :--- | :--- | :--- |
| **Professores Regentes** | Usuários primários da solução | Economizar tempo hábil, preservar a autonomia pedagógica e gerar materiais inclusivos com rapidez. | Alta / Alto |
| **Alunos Neurodivergentes** | Beneficiários finais diretos | Receber materiais didáticos claros, acessíveis, sem sobrecarga cognitiva e em paridade com a turma. | Alta / Alto |
| **Equipe de AEE / Salas de Recursos** | Co-avaliadores pedagógicos | Validar critérios técnicos de acessibilidade e alinhar práticas ao Plano de Desenvolvimento Individual (PDI). | Média / Alto |
| **Coordenação Pedagógica e Direção** | Gestão educacional | Garantir equidade no processo de ensino, cumprimento legal das diretrizes de inclusão e desempenho. | Alta / Médio |
| **Famílias dos Estudantes** | Comunidade escolar | Assegurar que o estudante receba estímulo pedagógico digno, sem exclusão ou desamparo acadêmico. | Média / Médio |
| **Equipe Técnica e IA** | Desenvolvimento do produto | Entregar interface intuitiva, tempos rápidos de resposta, conformidade estrita com a LGPD e precisão nos prompts. | Alta / Médio |

---

## 5. Personas

### Persona 1: O Professor (Carlos)
* **Perfil:** Carlos, 38 anos, professor de Biologia no Ensino Fundamental II (redes pública e privada, 35 horas semanais em sala de aula).
* **Contexto da sala de aula:** Leciona para 6 turmas com média de 32 alunos. Em uma mesma sala, tem dois alunos autistas (nível 1 de suporte) e uma aluna com dislexia.
* **Dores:** Dedica finais de semana ao planejamento e correção. Sente frustração e culpa por não conseguir produzir adaptações a tempo, recorrendo a simplificações de última hora sem embasamento formal.
* **Objetivo no sistema:** Colar o texto de sua avaliação bimestral, selecionar critérios funcionais (enunciados curtos, vocabulário simplificado e suporte visual) e receber a versão pronta com a justificativa de cada alteração à luz do DUA.

### Persona 2: Estudante com Barreiras (Beatriz)
* **Perfil:** Beatriz, 13 anos, aluna do 8º ano com TDAH e histórico de bloqueio diante de avaliações extensas.
* **Contexto escolar:** Demonstra bom raciocínio em discussões orais, mas paralisa diante de provas com blocos contínuos de texto e múltiplos comandos na mesma questão.
* **Dores:** Comete erros recorrentes em conteúdos que domina unicamente devido à sobrecarga de leitura e desatenção na interpretação de enunciados complexos.
* **Necessidades pedagógicas:** Atividades diagramadas com espaçamento limpo, instruções divididas em tópicos (*bullet points*), palavras de comando em negrito e suporte imagético explicativo.

---

## 6. Requisitos do Sistema

### 6.1. Requisitos Funcionais (RF)

* **RF01 - Inserção de conteúdo:** O sistema deve permitir a entrada de enunciados e atividades didáticas via inserção direta de texto ou upload de arquivos (`.docx`, `.pdf` e `.txt`). *(Equivalente a RF-01 e RF-02 da especificação técnica).*
* **RF02 - Seleção de critérios:** O sistema deve disponibilizar filtros baseados em necessidades observáveis (ex.: textos curtos, segmentação de comandos, linguagem direta, glossário, apoios visuais) sem exigir laudos clínicos formais, com foco prioritário em barreiras do TDAH e catálogo extensível para TEA e Dislexia. *(Equivalente a RF-04, RF-05 e RF-06).*
* **RF03 - Calibração de nível de suporte:** O professor deve poder parametrizar a intensidade da intervenção pedagógica entre os níveis Leve (Nível 1), Moderado (Nível 2) e Intensivo (Nível 3), com aplicação de Travas Curriculares inegociáveis. *(Equivalente a RF-07 e RF-08).*
* **RF04 - Geração com justificativas DUA:** O motor de IA (potencializado por RAG e arquitetura multiagentes) deve gerar a versão adaptada acompanhada de explicações pedagógicas pontuais justificando as modificações feitas à luz dos princípios do DUA. *(Equivalente a RF-10 e RF-11).*
* **RF05 - Editor comparativo:** A plataforma deve disponibilizar visualização comparativa (lado a lado) entre a versão original e a adaptada, permitindo edição livre e revisão pelo docente (*Human-in-the-Loop*). *(Equivalente a RF-13).*
* **RF06 - Exportação e Portabilidade:** O sistema deve possibilitar a exportação do material adaptado em formato pronto para impressão (PDF formatado), documento editável (DOCX) e o Perfil Pedagógico Portátil local (`.json`/`.pdf`) anônimo. *(Equivalente a RF-14 e RF-15).*

### 6.2. Requisitos Não Funcionais (RNF)

* **RNF01 - Acessibilidade:** A interface deve seguir rigorosamente as diretrizes do WCAG (nível AA) e e-MAG (Modelo de Acessibilidade em Governo Eletrônico), garantindo suporte a leitores de tela, navegação por teclado e fontes acessíveis. *(Equivalente a RNF-09).*
* **RNF02 - Desempenho e Latência:** O processamento e geração da versão adaptada não devem ultrapassar **15 segundos para Nível 1** (ajustes tipográficos e visuais) e até **40 segundos para Níveis 2 e 3** (que executam a cadeia multiagentes completa com RAG e auditoria automatizada de travas), em atividades de até 2.000 palavras. *(Equivalente a RNF-07).*
* **RNF03 - Segurança e Privacidade (LGPD):** O sistema é fundamentado no princípio de *Privacy by Design* e arquitetura *Zero-Database*, vedando qualquer armazenamento centralizado de dados pessoais de estudantes e executando sanitização local de PII antes de requisições a LLMs externos. *(Equivalente a RNF-01, RNF-02 e RNF-03).*
* **RNF04 - Fidelidade ao DUA e Validação Objetiva:** A arquitetura de prompts e a formatação devem incorporar com rigor as três redes do DUA (representação, ação/expressão e engajamento), validadas por métricas objetivas de IA: Taxa de Retenção de Conceitos ($\text{TRCC} \ge 95\%$), Índice Flesch-Kincaid PT-BR e métricas RAGAS. *(Equivalente a RNF-04, RNF-05 e RNF-06).*

---

## 7. Premissas e Riscos do Projeto

### 7.1. Premissas
1. O professor possui o material curricular original em formato de texto digital ou passível de cópia/digitalização.
2. A tomada de decisão final é sempre humana: a IA atua como copiloto de apoio, mantendo o professor como mediador e autoridade pedagógica (*Human-in-the-Loop*).
3. Os professores possuem capacidade de observação empírica para mapear barreiras de aprendizado dos alunos sem depender exclusivamente de diagnósticos formais.
4. Modelos de linguagem modernos (LLMs) possuem capacidade semântica para reestruturar sintaxe e diagramação sem comprometer a precisão dos conteúdos conceituais, quando delimitados por evidências científicas e travas curriculares.

### 7.2. Matriz de Riscos e Mitigações

| Risco Identificado | Probabilidade | Impacto | Estratégia de Mitigação |
| :--- | :---: | :---: | :--- |
| **Alucinação ou simplificação excessiva do conteúdo curricular** | Média | Alto | Arquitetura de prompts estruturada com few-shot learning, âncoras conceituais rígidas (Travas Curriculares), RAG com documentos do DUA/MEC e auditor de fidelidade. |
| **Resistência ou desconfiança docente quanto ao uso de IA** | Alta | Médio | Transparência algorítmica: exibição clara da justificativa pedagógica de cada adaptação, interface comparativa lado a lado e posicionamento como ferramenta de apoio ao tempo docente. |
| **Limitações técnicas e escassez de infraestrutura na escola** | Média | Alto | Layout de impressão econômico (tons de cinza, padrão A4, sem preenchimentos densos de tinta), processamento em nuvem leve e compatibilidade total com dispositivos móveis. |
| **Vazamento ou armazenamento indevido de dados de estudantes** | Baixa | Crítico | Arquitetura estritamente *stateless* (*Zero-Database*); sanitizador local de PII; nenhuma informação cadastral ou histórico médico do aluno é requisitado ou registrado. |

---

## 8. Métricas de Sucesso

A validação e acompanhamento do impacto do projeto serão aferidos a partir dos seguintes indicadores-chave de desempenho:

* **Redução de tempo docente:** Redução mínima de **60%** no tempo despendido pelos professores no preparo e formatação de avaliações adaptadas, medido em testes controlados pré e pós-adoção.
* **Taxa de aceitação e confiabilidade:** Mais de **80%** das sugestões de adaptação geradas pelo copiloto mantidas ou aproveitadas pelos professores com ajustes mínimos, demonstrando alta assertividade pedagógica.
* **Engajamento e autonomia do aluno:** Índice favorável superior a **75%** nos relatos de professores sobre melhora na autonomia, concentração e resolução autônoma das atividades pelos estudantes beneficiados.
* **Retenção Curricular Comprovada:** Taxa de Retenção de Conceitos-Chave ($\text{TRCC}$) igual ou superior a **95%** em todos os testes comparativos.

