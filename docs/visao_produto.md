# Visão do Produto — Íris

## 1. Declaração de Visão do Produto

> **Para** professores da educação básica e especialistas em Atendimento Educacional Especializado (AEE),  
> **que** enfrentam alta sobrecarga de trabalho e escassez de tempo para adaptar materiais didáticos para estudantes com necessidades atípicas de aprendizagem,  
> **o Íris** é uma plataforma inteligente de apoio à decisão pedagógica e adaptação de atividades didáticas,  
> **que** atua como copiloto pedagógico aplicando andaimes cognitivos (*scaffolding*) graduados baseados em evidências científicas (DUA e Funções Executivas) e barreiras funcionais observadas em sala de aula, preservando integralmente o núcleo curricular avaliado.  
> **Diferente de** ferramentas de LLM genéricas (que resumem superficialmente o texto, eliminam a complexidade conceitual e geram subexposição cognitiva),  
> **o nosso produto** garante a integridade curricular por meio de **travas avaliativas inegociáveis**, conformidade estrita com a **LGPD (Zero-Database)** e rastreabilidade pedagógica com supervisão docente contínua (*Human-in-the-Loop*).

---

## 2. O Cenário Escolhido e o Problema Real

### 2.1. O Cenário Educacional
O cenário educacional brasileiro reflete uma crescente e indispensável inclusão de estudantes neurodivergentes, abrangendo indivíduos no Espectro Autista (TEA), com Transtorno do Déficit de Atenção com Hiperatividade (TDAH) e Dislexia no ensino regular. Contudo, essa ampliação no número de matrículas não veio acompanhada de suporte estrutural e operacional suficiente ao corpo docente.

Professores da educação básica lidam rotineiramente com jornadas exaustivas, turmas numerosas e escassez de recursos de apoio pedagógico. Embora possuam preparo e sensibilidade diagnóstica para mapear as barreiras de aprendizagem presentes na sala de aula, a execução prática, que exige converter atividades genéricas em múltiplos materiais customizados, torna-se inviável pela falta crônica de tempo hábil.

### 2.2. A Falácia dos Modelos Genéricos e o Efeito Muleta
Ao tentarem utilizar modelos de linguagem comerciais genéricos com prompts simples (*"Adapte esta prova para um aluno com TDAH"*), os professores recebem resultados danosos:
* **Empobrecimento Curricular:** A IA costuma apenas encurtar textos, substituir termos técnicos por analogias excessivamente infantis e remover alternativas de raciocínio.
* **Subexposição Cognitiva (*Efeito Muleta*):** A IA frequentemente responde a pergunta ou faz a inferência crítica no próprio enunciado modificado, retirando do aluno a oportunidade de desenvolver a habilidade cognitiva-alvo.
* **Homogeneização Clínica:** Tratam todo diagnóstico como idêntico, ignorando que cada estudante manifesta perfis executivos e potencialidades singulares.

---

## 3. Proposta de Valor e Diferenciais

| Dimensão | Soluções Comerciais Genéricas | Plataforma Íris |
| :--- | :--- | :--- |
| **Abordagem de Perfil** | Rótulo diagnóstico genérico e estereotipado | **Barreiras Funcionais Observadas** + Potencialidades do Aluno |
| **Intensidade do Suporte** | Binária (ou simplifica tudo ou não muda nada) | **Andaime Cognitivo em 3 Níveis** (Leve, Moderado, Intensivo) |
| **Preservação Curricular** | Alto risco de eliminação de habilidades da BNCC | **Trava Curricular Inegociável** monitorada por Agente Auditor |
| **Fundamentação Pedagógica** | Alucinação probabilística de estratégias | **RAG Científico** ancorado no DUA, MEC e literatura de Funções Executivas |
| **Privacidade de Menores** | Coleta e armazenamento de dados em nuvem | **Zero-Database de Estudantes** + Sanitização local de PII |
| **Continuidade Pedagógica** | Inexistente ou dependente de banco central | **Perfil Pedagógico Portátil** (`.json`/`.pdf`) local e anônimo |

---

## 4. Personas

### Persona 1: O Professor (Carlos)
* **Perfil:** Carlos, 38 anos, professor de Biologia no Ensino Fundamental II (redes pública e privada, 35 horas semanais em sala de aula).
* **Contexto da sala de aula:** Leciona para 6 turmas com média de 32 alunos. Em uma mesma sala, tem dois alunos autistas (nível 1 de suporte) e uma aluna com dislexia.
* **Dores:** Dedica finais de semana ao planejamento e correção. Sente frustração e culpa por não conseguir produzir adaptações a tempo, recorrendo a simplificações de última hora sem embasamento formal.
* **Objetivo no sistema:** Colar o texto de sua avaliação bimestral, selecionar critérios funcionais (enunciados curtos, vocabulário simplificado e suporte visual) e receber a versão pronta com a justificativa de cada alteração à luz do DUA.

### Persona 2: A Estudante com Barreiras (Beatriz)
* **Perfil:** Beatriz, 13 anos, aluna do 8º ano com TDAH e histórico de bloqueio diante de avaliações extensas.
* **Contexto escolar:** Demonstra bom raciocínio em discussões orais, mas paralisa diante de provas com blocos contínuos de texto e múltiplos comandos na mesma questão.
* **Dores:** Comete erros recorrentes em conteúdos que domina unicamente devido à sobrecarga de leitura e desatenção na interpretação de enunciados complexos.
* **Necessidades pedagógicas:** Atividades diagramadas com espaçamento limpo, instruções divididas em tópicos (*bullet points*), palavras de comando em negrito e suporte imagético explicativo.

---

## 5. Escopo do MVP e Evolução por Neurodivergência

### 5.1. Recorte Prioritário do MVP: TDAH
O MVP do Challenge 2 tem como foco prioritário a validação com **estudantes com TDAH**, atacando as seguintes barreiras funcionais executivas:
1. Sustentação de atenção em textos longos;
2. Sobrecarga de memória de trabalho;
3. Iniciação e organização sequencial de tarefas;
4. Vulnerabilidade a concorrência de estímulos visuais;
5. Necessidade de instruções diretas e unívocas.

### 5.2. Arquitetura Modular e Expansão para TEA e Dislexia
Embora o MVP priorize o TDAH para validação experimental rigorosa nas Semanas 3 e 7, o sistema foi concebido desde o Dia 1 com catálogo modular de barreiras (`catalogs/`), permitindo atender progressivamente às dores de professores como Carlos:
* **Para Alunos no Espectro Autista (TEA):** Redução de ambiguidades linguísticas, literalidade nas instruções, antecipação estrutural da prova e remoção de linguagem metafórica não essencial.
* **Para Alunos com Dislexia:** Apoio na decodificação leitora (tipografia específica, maior espaçamento entre caracteres e linhas, suporte imagético para vocabulário incomum e fragmentação sintática).

---

## 6. Limites do MVP (O que entra vs. O que não entra)

### No Escopo do MVP
1. **Entrada de Materiais Didáticos:** Inserção direta de texto ou upload (.pdf, .docx, .txt).
2. **Seleção de Critérios Funcionais:** Filtros práticos baseados em necessidades observáveis, sem burocracia de laudos.
3. **Calibragem em 3 Níveis:** Leve, Moderado e Intensivo.
4. **Travas Curriculares Inegociáveis:** Garantia de que a habilidade avaliada não seja simplificada.
5. **Geração com Justificativas DUA:** Explicações transparentes de cada intervenção pedagógica.
6. **Editor Comparativo Lado a Lado:** Revisão livre e supervisão docente obrigatória (*Human-in-the-Loop*).
7. **Exportação Pronta:** PDF formatado e DOCX editável.
8. **Privacidade e Portabilidade:** Zero-Database, detector local de PII e Perfil Portátil local.

### Fora do Escopo do MVP (Limites Éticos Inegociáveis)
1. **Diagnóstico ou Triagem Clínica:** O Íris não realiza testes psicológicos, não emite laudos e não rotula clinicamente os estudantes.
2. **Armazenamento Centralizado de Menores:** Proibido qualquer banco de dados cadastral de estudantes.
3. **Geração sem Validação Humana:** O material nunca é enviado para aplicação com alunos sem a revisão e aprovação explícita do professor regente.
