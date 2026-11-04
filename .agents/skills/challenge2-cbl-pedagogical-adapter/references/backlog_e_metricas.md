# Backlog Estruturado e Protocolo de Métricas — Challenge 2

## 1. Estrutura Completa do Backlog (Temas → Épicos → Histórias de Usuário)

### Tema 1: Gestão de Insumos e Parametrização Pedagógica
* **Épico 1.1: Identificação e Entrada de Materiais Didáticos (US 1.1.1 a 1.1.3)**
  * Entrada de materiais via texto estruturado, documentos (`.pdf`, `.docx`) e insumos multimodais (fotos/scans de provas impressas via OCR/Visão na Semana 5).
  * Identificação automática da estrutura da atividade (enunciados, textos-base, alternativas, imagens).
* **Épico 1.2: Mapeamento de Perfil Funcional de Aprendizagem (US 1.2.1 a 1.2.3)**
  * Seleção de barreiras funcionais observadas em sala de aula (atenção sustentada, memória de trabalho, iniciação de tarefa, organização sequencial, sobrecarga visual) em vez de rótulo clínico único.
  * Registro de potencialidades e interesses do estudante (incluindo suporte a entrada por áudio docente na Semana 5).
* **Épico 1.3: Calibragem de Nível de Suporte e Travas Curriculares (US 1.3.1 a 1.3.2)**
  * Escolha do nível de Andaime Cognitivo (*Scaffolding*): Nível 1 (Leve), Nível 2 (Moderada) ou Nível 3 (Intensiva).
  * Definição explícita das **Travas Curriculares Inegociáveis** (habilidades BNCC, conceitos-chave e objetivos avaliativos que não podem ser alterados ou respondidos pela IA).

### Tema 2: Motor de Adaptação Inteligente e Revisão Docente
* **Épico 2.1: Geração de Materiais Adaptados Baseada em Evidências (US 2.1.1 a 2.1.4)**
  * Recuperação de estratégias psicopedagógicas via RAG (DUA, MEC, literatura revisada por pares sobre Funções Executivas no TDAH).
  * Orquestração do Sistema Multiagentes:
    1. **Agente Extrator Curricular:** Analisa o material original e isola os conceitos e habilidades da Trava Curricular.
    2. **Agente Estrategista Psicopedagógico (RAG):** Seleciona as intervenções baseadas nas barreiras funcionais do perfil e no nível de suporte.
    3. **Agente Adaptador:** Reescreve e reestrutura o material aplicando os andaimes cognitivos sem violar as travas.
    4. **Agente Auditor de Fidelidade e Nível:** Verifica quantitativa e qualitativamente se houve perda de conteúdo (*efeito muleta*) ou desvio do nível solicitado, acionando *self-correction* se necessário.
* **Épico 2.2: Edição Lado a Lado e Exportação de Materiais (US 2.2.1 a 2.2.3)**
  * Interface *Human-in-the-Loop* de comparação e edição lado a lado (Material Original vs. Material Adaptado + Justificativas Pedagógicas do RAG).
  * Exportação do material final aprovado pelo professor em formatos prontos para aplicação.

### Tema 3: Continuidade Pedagógica e Portabilidade
* **Épico 3.1: Criação e Gestão do Perfil Pedagógico Portátil (US 3.1.1 a 3.1.3)**
  * Estruturação local do perfil identificado apenas por código aleatório anônimo.
  * Registro contínuo de estratégias que funcionaram, estratégias que não funcionaram e observações pedagógicas (estritamente separadas de dados clínicos).
* **Épico 3.2: Exportação e Importação Descentralizada de Perfis (US 3.2.1 a 3.2.2)**
  * Exportação e reimportação do Perfil Pedagógico Portátil em `.json` (interoperabilidade com a plataforma) e `.pdf` (documentação escolar humana) para transição entre bimestres, anos letivos ou professores sem banco de dados centralizado.

### Tema 4: Privacidade desde a Concepção (Privacy by Design) e Governança Científica
* **Épico 4.1: Proteção de Dados e Conformidade LGPD (US 4.1.1 a 4.1.4)**
  * Arquitetura *Zero-Database* de estudantes (*stateless* para dados pessoais).
  * Detector e sanitizador local de PII (nomes, CPFs, nomes de instituições, contatos) na entrada de materiais antes de qualquer chamada externa de LLM.
* **Épico 4.2: Curadoria e Validação do Catálogo de Perfis de Aprendizagem (US 4.2.1 a 4.2.2)**
  * Arquitetura modular baseada em esquemas validados para permitir expansão futura para outros recortes de neurodivergência (Dislexia, Discalculia, TEA) com rastreabilidade bibliográfica obrigatória.

---

## 2. Protocolo de Métricas Objetivas (Semanas 3 e 7)

1. **Taxa de Retenção de Conceitos-Chave (TRCC):**
   $$\text{TRCC} = \frac{|\text{Conceitos da Trava Curricular Presentes no Material Adaptado}|}{|\text{Conceitos da Trava Curricular no Material Original}|}$$
   * **Critério:** Deve ser $\ge 0.95$ (95%) em todos os níveis de suporte, provando que o sistema não remove o conteúdo curricular avaliado.
2. **Índice de Facilidade de Leitura Flesch (Adaptação PT-BR — Martins et al.):**
   $$\text{Flesch}_{\text{PT-BR}} = 248.835 - (1.015 \times \text{ASL}) - (84.6 \times \text{ASW})$$
   *(onde $\text{ASL}$ = comprimento médio da sentença em palavras e $\text{ASW}$ = número médio de sílabas por palavra)*.
   * **Critério:** Redução controlada de $\text{ASL}$ (frases mais diretas e instruções fragmentadas nos Níveis 2 e 3) sem eliminar termos técnicos obrigatórios da Trava Curricular.
3. **Aderência Estrutural ao Nível Solicitado (SAEN):**
   * Checklist automatizado verificando marcadores visuais/negrito sem quebra estrutural (Nível 1), presença de *checklists* e *chunking* de enunciados (Nível 2), e decomposição passo a passo com pausas/andaimes explícitos (Nível 3).
4. **Métricas RAGAS (Pipeline de Evidências):**
   * **Faithfulness:** Mede se as justificativas e estratégias psicopedagógicas aplicadas derivam fielmente dos documentos recuperados (MEC, DUA, artigos sobre TDAH) sem alucinação.
   * **Context Precision:** Avalia a relevância dos *chunks* recuperados para as barreiras funcionais específicas selecionadas pelo professor.
   * **Answer Relevancy:** Avalia a pertinência da adaptação final frente às restrições parametrizadas pelo docente.
