# Requisitos Funcionais (RF) — Íris

Este documento especifica os **Requisitos Funcionais** da plataforma Íris. Em estrita conformidade com as diretrizes do projeto, os requisitos são apresentados em formato de especificação de engenharia de software (entradas, regras de processamento e saídas), sem utilização de histórias de usuário nesta etapa.

---

## Módulo 1: Entrada e Gestão de Insumos Pedagógicos

### RF-01: Inserção de Conteúdo Pedagógico via Texto e Documentos
* **Descrição:** O sistema deve permitir que o professor insira o material didático original (avaliações, listas de exercícios, textos de apoio ou roteiros de aula) por digitação direta em campo de texto ou por upload de arquivos nos formatos `.pdf`, `.docx` e `.txt`.
* **Entradas:** Texto livre ou arquivo digital contendo questões, enunciados e textos-base.
* **Processamento:**
  1. Extração do texto bruto e sanitização de formatação indesejada.
  2. Validação do tamanho do texto (mínimo de 50 caracteres e limite seguro de tokens da janela de contexto).
* **Saída:** Objeto estruturado em memória contendo o material pedagógico bruto.

### RF-02: Decomposição Estrutural Automática do Material
* **Descrição:** O sistema deve identificar e segmentar deterministicamente os componentes estruturais da atividade pedagógica submetida.
* **Entradas:** Texto do material validado no RF-01.
* **Processamento:**
  1. Identificação de cabeçalhos contextuais, textos de apoio/leitura obrigatória.
  2. Isolamento de cada questão individual, segmentando enunciado, alternativas (quando múltipla escolha) e linhas de resposta esperadas.
* **Saída:** Estrutura de dados hierárquica dividida em blocos de conteúdo e questões isoladas.

### RF-03: Entrada Multimodal de Provas e Imagens (Semana 5)
* **Descrição:** O sistema deve permitir o upload de fotos ou digitalizações de materiais impressos e imagens auxiliares associadas às questões.
* **Entradas:** Arquivos de imagem (`.png`, `.jpg`, `.jpeg`).
* **Processamento:**
  1. Execução de pipeline OCR/Visão Computacional para transcrição fidedigna do texto.
  2. Análise da imagem associada para identificar densidade de informação e potencial poluição visual.
* **Saída:** Texto transcrito integrado à decomposição estrutural e indicadores de poluição visual.

---

## Módulo 2: Parametrização Pedagógica & Mapeamento Funcional

### RF-04: Seleção Modular de Barreiras Funcionais Observadas
* **Descrição:** O sistema deve fornecer uma interface de seleção baseada em barreiras funcionais executivas observadas em sala de aula, impedindo o tratamento homogêneo do diagnóstico de TDAH.
* **Entradas:** Seleção do professor sobre o catálogo modular de barreiras.
* **Processamento:**
  1. Carregamento do catálogo oficial de barreiras funcionais (`tdah_barreiras_funcionais.json`).
  2. Registro das opções selecionadas (ex.: *Atenção sustentada a textos longos*, *Sobrecarga de memória de trabalho*, *Iniciação/organização sequencial de respostas*, *Vulnerabilidade a poluição visual*).
* **Saída:** Vetor de restrições funcionais associado à sessão atual de adaptação.

### RF-05: Registro de Potencialidades e Estilos de Engajamento
* **Descrição:** O sistema deve coletar as potencialidades, interesses temáticos e canais preferenciais de demonstração de conhecimento do aluno para orientar a contextualização da adaptação.
* **Entradas:** Campos de seleção e texto livre (ex.: interesse em ciências práticas, preferência por esquemas visuais, narrativa histórica).
* **Processamento:**
  1. Associação das potencialidades às diretrizes do Princípio I do DUA (Múltiplas Formas de Engajamento).
* **Saída:** Metadados de potencialidades anexados ao perfil da sessão.

### RF-06: Extensibilidade de Catálogos de Perfis
* **Descrição:** A arquitetura do sistema deve permitir a inclusão de novos catálogos de barreiras funcionais (para futura expansão: Dislexia, Discalculia, TEA) por meio de esquemas padronizados em JSON/YAML, sem necessidade de alteração no núcleo do código.
* **Entradas:** Arquivo de definição de perfil com metadados científicos e mapeamento de barreiras.
* **Processamento:**
  1. Validação do schema contra o modelo Pydantic do catálogo de perfis.
  2. Disponibilização imediata das novas barreiras na interface de seleção.
* **Saída:** Catálogo validado e registrado no pool de perfis do sistema.

---

## Módulo 3: Calibragem de Andaimes e Travas Curriculares

### RF-07: Calibragem do Nível de Andaime Cognitivo (*Scaffolding*)
* **Descrição:** O sistema deve permitir que o professor selecione a intensidade de suporte necessária para a atividade entre três níveis pré-estabelecidos.
* **Entradas:** Seleção de nível (Nível 1 — Leve, Nível 2 — Moderado, Nível 3 — Intensivo).
* **Processamento:**
  1. Configuração dos parâmetros de transformação conforme as regras de negócio:
     * **Nível 1 (Leve):** Reestruturação tipográfica, espaçamento generoso, destaque em negrito de palavras de comando e vocabulário-chave. Preserva 100% da estrutura frasal original.
     * **Nível 2 (Moderado):** *Chunking* de parágrafos extensos, divisão do enunciado em *checklists* de execução passo a passo, inserção de caixas de apoio conceitual.
     * **Nível 3 (Intensivo):** Decomposição da questão em sub-etapas com checagem intermediária, indicação de pausas estratégicas de autorregulação e organizadores visuais gráficos.
* **Saída:** Diretiva de transformação de andaime atribuída ao pipeline da sessão.

### RF-08: Definição Explícita de Travas Curriculares Inegociáveis
* **Descrição:** O sistema deve exigir ou capturar do professor quais habilidades curriculares, conceitos e objetivos avaliativos não podem sofrer qualquer redução de rigor cognitivo.
* **Entradas:** Campo de texto estruturado ou seleção de códigos da BNCC e conceitos inegociáveis (ex.: *"Avalia a capacidade de deduzir o conceito de fotossíntese a partir do experimento"*).
* **Processamento:**
  1. Extração dos conceitos-chave da trava curricular.
  2. Geração de invariantes de avaliação para envio ao Agente Auditor.
* **Saída:** Lista de invariantes curriculares inalteráveis.

### RF-09: Validador Preventivo de Perda Cognitiva (*Anti-Muleta*)
* **Descrição:** O sistema deve verificar preventivamente se a trava curricular definida entra em conflito com o nível de andaime selecionado (ex.: pedir Nível 3 com remoção de interpretação numa questão cuja trava é interpretação de texto).
* **Entradas:** Nível de andaime e declaração da trava curricular.
* **Processamento:**
  1. Execução de regras de verificação lógica de incompatibilidade pedagógica.
  2. Emissão de alerta ao professor caso o andaime pretendido ameace o objetivo avaliado.
* **Saída:** Liberação do fluxo ou alerta orientador com sugestão de calibração.

---

## Módulo 4: Motor de Adaptação Inteligente e Auditoria

### RF-10: Recuperação de Estratégias Pedagógicas Baseadas em Evidências (RAG)
* **Descrição:** O sistema deve consultar uma base de conhecimento vetorial indexada contendo referenciais do DUA, diretrizes do MEC e literatura científica sobre Funções Executivas no TDAH, recuperando apenas estratégias validadas para as barreiras selecionadas.
* **Entradas:** Vetor de barreiras funcionais + Nível de andaime + Tipo de questão.
* **Processamento:**
  1. Geração de embedding da consulta de parametrização.
  2. Busca semântica e filtragem por metadados na base vetorial.
  3. Recuperação de trechos normativos e orientações práticas de adaptação com citações da fonte.
* **Saída:** Contexto de evidências científicas anexado ao prompt de adaptação.

### RF-11: Orquestração Multiagentes de Adaptação
* **Descrição:** A geração da adaptação deve ser dividida entre agentes de IA com responsabilidades segregadas, executados em sequência coordenada:
  1. **Agente Extrator Curricular:** Isola os conceitos centrais e objetivos da questão.
  2. **Agente Estrategista RAG:** Seleciona as intervenções pedagógicas adequadas à barreira funcional e nível.
  3. **Agente Adaptador:** Reescreve e formata o material aplicando os andaimes aprovados.
  4. **Agente Auditor:** Realiza a conferência de qualidade e fidelidade antes da entrega ao professor.
* **Entradas:** Material estruturado, barreiras, travas e contexto RAG recuperado.
* **Processamento:** Execução ordenada do pipeline com passagem de estado em memória.
* **Saída:** Versão adaptada acompanhada das justificativas técnicas de cada alteração.

### RF-12: Auditoria Automatizada de Preservação Curricular e Nível
* **Descrição:** O Agente Auditor deve submeter o material gerado a um crivo rigoroso antes de exibi-lo ao professor.
* **Entradas:** Material original, material adaptado, travas curriculares e nível solicitado.
* **Processamento:**
  1. Cálculo determinístico da Taxa de Retenção de Conceitos-Chave (TRCC).
  2. Verificação de conformidade estrutural com as regras do nível solicitado (SAEN).
  3. Detecção de resoluções indevidas (verificar se a IA respondeu à pergunta no próprio enunciado).
  4. Disparo de auto-correção (*self-refinement*) pelo Agente Adaptador se $\text{TRCC} < 95\%$.
* **Saída:** Relatório de auditoria (Aprovado ou Refinado com métricas de validação).

---

## Módulo 5: Revisão Humana, Exportação e Portabilidade

### RF-13: Interface de Revisão e Edição Lado a Lado (*Human-in-the-Loop*)
* **Descrição:** O sistema deve apresentar ao professor uma interface comparativa dividida em duas colunas: à esquerda o material original e à direita a versão adaptada sugerida, permitindo edição direta pelo docente.
* **Entradas:** Material original e material adaptado auditado.
* **Processamento:**
  1. Alinhamento síncrono das questões correspondentes nas duas colunas.
  2. Exibição de painel retrátil de justificativas pedagógicas vinculadas a cada alteração (indicando qual barreira e qual referência científica justificou a intervenção).
  3. Habilitação de campos de texto editáveis para que o professor faça ajustes manuais finais.
* **Saída:** Material didático final revisado e homologado pelo professor.

### RF-14: Exportação em Formatos Prontos para Impressão e Uso Digital
* **Descrição:** O sistema deve exportar a versão final aprovada em formatos diretamente aplicáveis na rotina escolar.
* **Entradas:** Material adaptado aprovado pelo professor.
* **Processamento:**
  1. Compilação para formato `.pdf` diagramado com tipografia amigável (fontes sem serifa, espaçamento entre linhas de 1,5, caixas delimitadoras de questões).
  2. Opção de exportação em `.docx` para edições futuras pelo professor.
* **Saída:** Arquivo compilado disponibilizado para download imediato.

### RF-15: Exportação e Importação do Perfil Pedagógico Portátil
* **Descrição:** O sistema deve permitir gerar e consumir localmente o Perfil Pedagógico Portátil do estudante, garantindo continuidade pedagógica sem armazenamento centralizado.
* **Entradas:** Registros da sessão (código anônimo, barreiras observadas, histórico de estratégias eficazes/ineficazes e anotações pedagógicas).
* **Processamento:**
  1. Geração de arquivo estruturado `.json` para reimportação em sessões futuras na plataforma.
  2. Geração de documento `.pdf` de síntese pedagógica para arquivamento no dossiê escolar do estudante.
  3. Parsing e validação de schema na reimportação de arquivo `.json` existente.
* **Saída:** Arquivo de perfil portátil baixado localmente ou perfil recarregado na sessão.

