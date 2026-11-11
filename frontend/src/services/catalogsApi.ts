/**
 * Cliente HTTP e persistência em sessão para o Catálogo de Características Funcionais Atômicas
 * e Seleção Cirúrgica da Etapa 2 (História 1.2.1 — Issue #8).
 *
 * Endpoints consumidos:
 * - GET  /api/v1/catalogs/characteristics
 * - POST /api/v1/catalogs/characteristics/select
 */

import { IrisApiError, MaterialMetadata } from "./materialsApi";

export interface Step1SelectedFileInfo {
  name: string;
  sizeBytes: number;
  extension: string;
  status: "accepted" | "rejected" | "uploading";
}

export interface Step1SessionState {
  textContent: string;
  metadata: MaterialMetadata | null;
  selectedFile: Step1SelectedFileInfo | null;
  confirmedForStep2: boolean;
}

export interface BibliographicReferenceItem {
  doc_id: string;
  citacao_curta: string;
  tipo_evidencia: string;
  ponto_verificacao_dua?: string | null;
}

export interface ScaffoldingLevelGuidelineItem {
  nivel: 1 | 2 | 3;
  rotulo: string;
  objetivo_andaime: string;
  acoes_permitidas: string[];
  restricoes_escopo: string[];
}

export interface CharacteristicItem {
  id_caracteristica: string;
  nome: string;
  descricao_observavel: string;
  exemplos_manifestacao_sala: string[];
  barreira_rag_associada: string;
  principio_dua_primario: "representacao" | "acao_e_expressao" | "engajamento";
  palavras_chave_busca: string[];
  diretrizes_andaime: {
    nivel_1: ScaffoldingLevelGuidelineItem;
    nivel_2: ScaffoldingLevelGuidelineItem;
    nivel_3: ScaffoldingLevelGuidelineItem;
  };
  referencias_bibliograficas: BibliographicReferenceItem[];
}

export interface CharacteristicsCatalogResponse {
  id_catalogo: string;
  versao_schema: string;
  perfil_referencia: string;
  titulo: string;
  descricao: string;
  aviso_etico_lgpd: string;
  caracteristicas: CharacteristicItem[];
  total_caracteristicas: number;
  exige_laudo_medico: boolean;
  barreiras_disponiveis: string[];
  principios_dua_disponiveis: string[];
}

export interface SurgicalSelectionResponse {
  status: string;
  message: string;
  id_catalogo: string;
  total_catalog_characteristics: number;
  selected_count: number;
  blocked_count: number;
  selected_ids: string[];
  blocked_ids: string[];
  active_characteristics: CharacteristicItem[];
  scope_isolation_rule: string;
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const SURGICAL_VECTOR_STORAGE_KEY = "iris_session_surgical_vector_v1";
export const STEP1_MATERIAL_STORAGE_KEY = "iris_session_step1_material_v1";

/**
 * Rótulos amigáveis para as barreiras funcionais do RAG (filtros atômicos desacoplados de rótulo clínico).
 */
export const BARREIRA_LABELS: Record<string, string> = {
  memoria_trabalho: "Memória de Trabalho",
  leitura_texto_longo: "Leitura de Textos Longos",
  sobrecarga_visual: "Poluição e Sobrecarga Visual",
  controle_inibitorio: "Controle Inibitório / Impulsividade",
  organizacao_sequencial: "Organização Sequencial e Escrita",
  atencao_sustentada: "Atenção Sustentada e Fadiga",
  flexibilidade_cognitiva: "Flexibilidade Cognitiva e Transição",
  iniciacao_tarefa: "Iniciação de Tarefas Abertas",
  velocidade_processamento: "Velocidade de Processamento",
};

/**
 * Rótulos amigáveis para os Princípios do DUA (CAST).
 */
export const PRINCIPIO_DUA_LABELS: Record<string, string> = {
  representacao: "DUA I — Representação",
  acao_e_expressao: "DUA II — Ação e Expressão",
  engajamento: "DUA III — Engajamento",
};

/**
 * Catálogo local de contingência (espelho fiel de `rag/catalogs/tdah_caracteristicas_funcionais.json`)
 * para garantir funcionamento resiliente caso o servidor FastAPI esteja offline durante testes de UI.
 */
export const FALLBACK_OFFICIAL_CATALOG: CharacteristicsCatalogResponse = {
  id_catalogo: "tdah_funcoes_executivas_v1",
  versao_schema: "1.0.0",
  perfil_referencia: "TDAH",
  titulo: "Catálogo de Características Funcionais Observáveis — Funções Executivas",
  descricao:
    "Catálogo modular de barreiras funcionais atômicas observadas em sala de aula associadas às Funções Executivas, fundamentado no Desenho Universal para a Aprendizagem (DUA/CAST), normativas do MEC e literatura científica revisada por pares.",
  aviso_etico_lgpd:
    "Este catálogo destina-se exclusivamente à parametrização pedagógica de atividades escolares pelo professor regente ou AEE. Não constitui instrumento de diagnóstico clínico, não exige laudo médico e proíbe a aplicação de adaptações em bloco para características não selecionadas.",
  total_caracteristicas: 8,
  exige_laudo_medico: false,
  barreiras_disponiveis: [
    "atencao_sustentada",
    "controle_inibitorio",
    "flexibilidade_cognitiva",
    "iniciacao_tarefa",
    "leitura_texto_longo",
    "memoria_trabalho",
    "organizacao_sequencial",
    "sobrecarga_visual",
    "velocidade_processamento",
  ],
  principios_dua_disponiveis: ["acao_e_expressao", "engajamento", "representacao"],
  caracteristicas: [
    {
      id_caracteristica: "sobrecarga_memoria_trabalho_comandos_multiplos",
      nome: "Sobrecarga de memória de trabalho em comandos múltiplos conjugados",
      descricao_observavel:
        "O estudante compreende o conteúdo avaliado, mas esquece etapas ou omite partes da resposta quando o enunciado acumula dois ou mais verbos de comando na mesma frase ou parágrafo.",
      exemplos_manifestacao_sala: [
        "Responde apenas à primeira pergunta de uma questão que pede 'identifique, justifique e dê um exemplo'.",
        "Perde o fio da instrução no meio da leitura de enunciados com orações subordinadas longas.",
      ],
      barreira_rag_associada: "memoria_trabalho",
      principio_dua_primario: "acao_e_expressao",
      palavras_chave_busca: ["memória de trabalho", "múltiplos comandos", "etapas explícitas", "checklist"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Destaque Tipográfico de Comandos",
          objetivo_andaime:
            "Sinalizar visualmente cada verbo de ação sem alterar a estrutura sintática nem a extensão do enunciado original.",
          acoes_permitidas: [
            "Aplicar negrito ou caixa-alta exclusivamente nos verbos de comando e conectivos sequenciais.",
            "Manter 100% do texto, vocabulário técnico e parágrafos originais intactos.",
          ],
          restricoes_escopo: [
            "Proibido reescrever frases ou dividir a questão em subitens.",
            "Proibido simplificar vocabulário ou fornecer dicas conceituais.",
          ],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Decomposição em Checklist de Etapas",
          objetivo_andaime:
            "Externalizar a carga da memória de trabalho convertendo comandos encadeados em uma lista sequencial verificável.",
          acoes_permitidas: [
            "Separar cada comando conjugado em um item numerado ou caixa de seleção ([ ]) independente.",
            "Destacar o verbo de comando no início de cada etapa da lista.",
          ],
          restricoes_escopo: [
            "Proibido responder a qualquer etapa ou sugerir a fórmula/inferência exigida pela trava curricular.",
            "Proibido reduzir o número de comandos avaliados na questão.",
          ],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Escalonamento Guiado Passo a Passo",
          objetivo_andaime:
            "Apresentar uma operação cognitiva por vez com espaço de registro dedicado imediatamente abaixo de cada comando.",
          acoes_permitidas: [
            "Fragmentar a questão em blocos sequenciais ('Passo 1', 'Passo 2') com linhas ou caixas de resposta exclusivas para cada passo.",
            "Adicionar lembrete de conferência ao final ('Revise se você preencheu os Passos 1 e 2').",
          ],
          restricoes_escopo: [
            "Proibido antecipar o resultado do Passo 1 no enunciado do Passo 2.",
            "Proibido eliminar termos técnicos protegidos pela Trava Curricular.",
          ],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "RBEE-SEBASTIAN-HEREDERO-2020-DIRETRIZES-DUA",
          citacao_curta:
            "Diretriz 6 (Apoiar o desenvolvimento das funções executivas): oferecer indicações explícitas para cada etapa em qualquer processo sequencial e fornecer listas de verificação.",
          tipo_evidencia: "diretriz_dua",
          ponto_verificacao_dua: "DUA Diretriz 6 / Ponto 6.2 e 6.3",
        },
      ],
    },
    {
      id_caracteristica: "retencao_dados_intermediarios_problemas_multietapas",
      nome: "Dificuldade na retenção e manipulação mental de dados intermediários",
      descricao_observavel:
        "O estudante compreende o raciocínio lógico ou matemático, mas perde valores numéricos, premissas ou condições espalhadas ao longo do texto de apoio durante a resolução.",
      exemplos_manifestacao_sala: [
        "Esquece uma unidade de medida ou condição inicial informada no primeiro parágrafo ao realizar o cálculo final.",
        "Troca números ou perde resultados parciais por tentar sustentar todas as variáveis mentalmente.",
      ],
      barreira_rag_associada: "memoria_trabalho",
      principio_dua_primario: "representacao",
      palavras_chave_busca: ["memória de trabalho", "organizadores gráficos", "anotações", "carga cognitiva"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Realce Visual de Dados e Variáveis",
          objetivo_andaime: "Facilitar a localização visual rápida das variáveis e premissas fornecidas no texto-base.",
          acoes_permitidas: [
            "Destacar em negrito os dados numéricos, grandezas, datas ou premissas condicionais presentes no enunciado.",
          ],
          restricoes_escopo: ["Proibido extrair os dados para fora do texto ou montar a equação pelo aluno."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Quadro de Registro de Dados pelo Estudante",
          objetivo_andaime:
            "Oferecer espaço estruturado em branco para que o próprio estudante anote os dados antes de operar sobre eles.",
          acoes_permitidas: [
            "Inserir caixa estruturada de apoio ('Dados identificados no texto: ___ / O que a questão pede: ___').",
          ],
          restricoes_escopo: ["Proibido entregar o quadro de dados já preenchido."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Organizador Gráfico de Memória Externa",
          objetivo_andaime:
            "Fornecer tabela ou esquema visual estruturado separando espaço de dados, espaço de etapas parciais e resposta final.",
          acoes_permitidas: [
            "Adicionar organizador gráfico com colunas rotuladas ('Etapa Parcial', 'Registro / Rascunho', 'Verificação').",
          ],
          restricoes_escopo: ["Proibido resolver etapas intermediárias pelo estudante."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "ZERBATO-MENDES-2018-DUA-INCLUSAO-ESCOLAR",
          citacao_curta:
            "Permitir que os estudantes registrem respostas e informações intermediárias em papel ou organizadores reduz a sobrecarga de evocação.",
          tipo_evidencia: "pesquisa_empirica",
          ponto_verificacao_dua: "DUA Diretriz 3 / Ponto 3.3",
        },
      ],
    },
    {
      id_caracteristica: "atencao_sustentada_textos_longos",
      nome: "Fadiga de atenção sustentada em blocos textuais densos e contínuos",
      descricao_observavel:
        "O estudante demonstra domínio oral do tema, mas abandona a leitura ou salta linhas quando confrontado com textos-base extensos em parágrafo único sem respiro visual.",
      exemplos_manifestacao_sala: [
        "Inicia a leitura do texto de apoio, mas pula direto para as alternativas sem terminar o parágrafo.",
        "Reclama de perder a linha em textos longos com margens estreitas e espaçamento simples.",
      ],
      barreira_rag_associada: "leitura_texto_longo",
      principio_dua_primario: "representacao",
      palavras_chave_busca: ["atenção sustentada", "chunking", "espaçamento", "segmentação de texto"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Respiração Visual e Segmentação de Parágrafos",
          objetivo_andaime:
            "Reduzir o paredão visual do texto-base por meio de espaçamento entre linhas e quebra de parágrafos longos por unidade de sentido.",
          acoes_permitidas: ["Dividir parágrafos excessivamente longos mantendo 100% das palavras originais."],
          restricoes_escopo: ["Proibido resumir, omitir frases ou alterar o léxico do texto-base."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Chunking Textual com Subtítulos Orientadores",
          objetivo_andaime:
            "Fatiar o texto longo em blocos curtos numerados ou rotulados com subtítulos neutros de localização temática.",
          acoes_permitidas: ["Segmentar o texto-base em blocos curtos ('Bloco 1', 'Bloco 2') com rótulo neutro."],
          restricoes_escopo: ["Proibido usar subtítulos que entreguem a interpretação ou o gabarito da questão."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Leitura Guiada por Blocos com Checkpoints de Atenção",
          objetivo_andaime:
            "Intercalar os blocos do texto longo com micro-pausas de verificação de leitura e ancoragem direta ao comando.",
          acoes_permitidas: ["Dividir o texto em blocos curtos acompanhados de marcador de progresso de leitura."],
          restricoes_escopo: ["Proibido substituir o texto original por resumo."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "GALLIUSSI-2020-ESPACAMENTO-DISLEXIA",
          citacao_curta:
            "O aumento do espaçamento visual e a organização tipográfica reduzem o esforço oculomotor e apoiam a precisão de leitura.",
          tipo_evidencia: "pesquisa_empirica",
          ponto_verificacao_dua: "DUA Diretriz 1 / Ponto 1.1",
        },
      ],
    },
    {
      id_caracteristica: "distratibilidade_poluicao_visual_layout",
      nome: "Distratibilidade por poluição visual e elementos gráficos concorrentes",
      descricao_observavel:
        "O estudante desvia o foco quando a atividade contém caixas laterais decorativas, múltiplas fontes, excesso de informações periféricas ou alternativas mal alinhadas.",
      exemplos_manifestacao_sala: [
        "Prende-se a detalhes irrelevantes de ilustrações decorativas e perde o foco no enunciado.",
        "Confunde a marcação das alternativas quando estão dispostas em múltiplas colunas comprimidas.",
      ],
      barreira_rag_associada: "sobrecarga_visual",
      principio_dua_primario: "representacao",
      palavras_chave_busca: ["poluição visual", "layout", "distração", "organização visual"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Padronização Visual e Alinhamento Vertical",
          objetivo_andaime: "Limpar ruídos de formatação e alinhar alternativas em coluna única com espaçamento previsível.",
          acoes_permitidas: ["Dispor todas as alternativas estritamente em coluna única vertical."],
          restricoes_escopo: ["Proibido remover gráficos, mapas ou tabelas necessários para resolver a questão."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Isolamento Visual de Contexto, Comando e Opções",
          objetivo_andaime:
            "Delimitar visualmente onde termina o texto de apoio e onde começa a pergunta e as opções de resposta.",
          acoes_permitidas: ["Separar a questão em três zonas visuais distintas: [Texto de Apoio], [Pergunta] e [Alternativas]."],
          restricoes_escopo: ["Proibido interpretar o gráfico pelo estudante."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Apresentação Minimalista de Questão Única por Bloco",
          objetivo_andaime: "Eliminar qualquer estímulo periférico concorrente no campo visual imediato da questão.",
          acoes_permitidas: ["Formatar a questão para exibição isolada com bordas de contenção visual suaves."],
          restricoes_escopo: ["Proibido simplificar o rigor conceitual da pergunta."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "CDC-ADHD-CLASSROOM-2026",
          citacao_curta:
            "Reduzir estímulos visuais distratores nos materiais e organizar o layout de forma limpa e previsível auxilia o foco na tarefa.",
          tipo_evidencia: "guia_oficial",
          ponto_verificacao_dua: "DUA Diretriz 7 / Ponto 7.3",
        },
      ],
    },
    {
      id_caracteristica: "impulsividade_leitura_superficial_negacoes",
      nome: "Impulsividade na resposta e omissão de condições restritivas ou negações",
      descricao_observavel:
        "O estudante responde de forma precipitada logo após ler as primeiras palavras do enunciado, ignorando termos restritivos críticos como 'EXCETO', 'NÃO', 'INCORRETA' ou 'APENAS'.",
      exemplos_manifestacao_sala: [
        "Marca a primeira alternativa verdadeira em uma questão que pedia a alternativa INCORRETA.",
        "Deixa de aplicar uma restrição importante ('considere apenas números pares') por pressa na leitura.",
      ],
      barreira_rag_associada: "controle_inibitorio",
      principio_dua_primario: "acao_e_expressao",
      palavras_chave_busca: ["controle inibitório", "impulsividade", "atenção aos detalhes", "automonitoramento"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Sinalização de Contraste em Termos Restritivos",
          objetivo_andaime: "Criar um freio visual imediato sobre negações, restrições e condições de exceção no comando.",
          acoes_permitidas: ["Aplicar caixa-alta e negrito em termos restritivos ('NÃO', 'EXCETO', 'INCORRETA')."],
          restricoes_escopo: ["Proibido alterar o sentido das alternativas."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Freio Cognitivo e Reformulação Direta do Comando",
          objetivo_andaime:
            "Evitar duplas negações confusas no comando e inserir marcador de parada reflexiva antes das alternativas.",
          acoes_permitidas: ["Destacar a condição restritiva em linha própria antes das alternativas."],
          restricoes_escopo: ["Proibido indicar quais alternativas são verdadeiras ou falsas."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Protocolo de Checagem Pré-Resposta (Stop & Think)",
          objetivo_andaime:
            "Estruturar uma etapa explícita de inibição da resposta automática por meio de verificação item a item.",
          acoes_permitidas: ["Adicionar coluna de validação `[ Verdadeiro | Falso ]` em cada alternativa."],
          restricoes_escopo: ["Proibido eliminar alternativas distratoras."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "ZERBATO-MENDES-2018-DUA-INCLUSAO-ESCOLAR",
          citacao_curta:
            "Fazer uma pausa estruturada antes de dar a resposta para que o estudante registre e confira sua formulação apoia o controle inibitório.",
          tipo_evidencia: "pesquisa_empirica",
          ponto_verificacao_dua: "DUA Diretriz 6 / Ponto 6.4",
        },
      ],
    },
    {
      id_caracteristica: "organizacao_sequencial_expressao_escrita",
      nome: "Dificuldade na organização sequencial de etapas e expressão escrita",
      descricao_observavel:
        "O estudante sabe explicar o conteúdo oralmente, mas apresenta dificuldade ao ordenar início, meio e fim em respostas discursivas ou procedimentos sequenciais.",
      exemplos_manifestacao_sala: [
        "Escreve respostas telegráficas e fora de ordem lógica que omitem a justificativa exigida.",
        "Inverte a sequência de passos ao demonstrar a resolução de uma questão aberta.",
      ],
      barreira_rag_associada: "organizacao_sequencial",
      principio_dua_primario: "acao_e_expressao",
      palavras_chave_busca: ["organização", "planejamento", "expressão escrita", "andaime"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Explicitação dos Critérios Esperados na Resposta",
          objetivo_andaime:
            "Tornar transparente quantos e quais elementos a resposta discursiva precisa conter para ser considerada completa.",
          acoes_permitidas: ["Indicar ao final do enunciado a estrutura esperada ('Sua resposta deve conter: 1)... 2)...')."],
          restricoes_escopo: ["Proibido sugerir argumentos ou palavras de conteúdo da resposta."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Particionamento do Espaço de Resposta por Tópico",
          objetivo_andaime:
            "Substituir o bloco único de linhas em branco por campos rotulados correspondentes a cada parte da resposta discursiva.",
          acoes_permitidas: ["Dividir as linhas de resposta em subcampos rotulados neutros."],
          restricoes_escopo: ["Proibido redigir o conteúdo pelo estudante."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Organizador de Planejamento e Conectivos de Iniciação",
          objetivo_andaime:
            "Destravar a iniciação motora/executiva da escrita oferecendo esquema de rascunho prévio e conectivos sintáticos neutros.",
          acoes_permitidas: ["Incluir mini-roteiro de planejamento ('Ideia central -> Argumento -> Conclusão')."],
          restricoes_escopo: ["Proibido violar a Trava Curricular."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "RBEE-SEBASTIAN-HEREDERO-2020-DIRETRIZES-DUA",
          citacao_curta:
            "Diretriz 5 e 6: fornecer andaimes graduados para planejamento, composição textual e organização da expressão do conhecimento.",
          tipo_evidencia: "diretriz_dua",
          ponto_verificacao_dua: "DUA Diretriz 5 / Ponto 5.2",
        },
      ],
    },
    {
      id_caracteristica: "fadiga_executiva_autorregulacao_provas_extensas",
      nome: "Fadiga executiva e queda de sustentação atencional ao longo de avaliações extensas",
      descricao_observavel:
        "O estudante inicia a avaliação com bom desempenho nas primeiras questões, mas demonstra exaustão, frustração e respostas aleatórias na metade final da prova.",
      exemplos_manifestacao_sala: [
        "Acerta as questões difíceis do início da prova e erra questões simples no final por esgotamento.",
        "Demonstra ansiedade e desorganização temporal quando não percebe quanto falta para terminar.",
      ],
      barreira_rag_associada: "atencao_sustentada",
      principio_dua_primario: "engajamento",
      palavras_chave_busca: ["autorregulação", "fadiga", "pausas", "monitoramento de progresso"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Indicadores Visuais de Progresso na Avaliação",
          objetivo_andaime: "Dar previsibilidade espacial e senso de avanço ao estudante ao longo da atividade.",
          acoes_permitidas: ["Inserir indicador claro de posição em cada questão ('Questão 2 de 6')."],
          restricoes_escopo: ["Proibido excluir questões da prova."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Agrupamento Modular em Baterias Curtas",
          objetivo_andaime: "Dividir a prova extensa em metas curtas com lembretes de pausa rápida entre baterias.",
          acoes_permitidas: ["Agrupar questões a cada 2 ou 3 itens em blocos modulares com marcador de conclusão."],
          restricoes_escopo: ["Proibido reduzir o conteúdo avaliado."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Aplicação Fracionada por Cadernos/Etapas Autônomas",
          objetivo_andaime:
            "Permitir que o professor entregue e recolha a avaliação em blocos independentes, reduzindo a ansiedade de volume total.",
          acoes_permitidas: ["Estruturar a diagramação em seções autônomas destacáveis ('Parte 1', 'Parte 2')."],
          restricoes_escopo: ["Proibido alterar as Travas Curriculares."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "RBEE-SEBASTIAN-HEREDERO-2020-DIRETRIZES-DUA",
          citacao_curta:
            "Diretriz 9 (Proporcionar opções para a autorregulação): apoiar o controle da frustração e a percepção de progresso.",
          tipo_evidencia: "diretriz_dua",
          ponto_verificacao_dua: "DUA Diretriz 9 / Ponto 9.2",
        },
      ],
    },
    {
      id_caracteristica: "flexibilidade_cognitiva_alternancia_topicos",
      nome: "Rigidez na alternância entre tipos de tarefa ou mudança brusca de regra",
      descricao_observavel:
        "O estudante persiste usando a regra, fórmula ou lógica da questão anterior quando a prova muda abruptamente de tema ou de tipo de comando sem sinalização.",
      exemplos_manifestacao_sala: [
        "Continua somando em uma questão de subtração ou aplica o contexto do texto 1 ao responder sobre o texto 2.",
        "Confunde-se quando a prova mistura questões de cálculo, interpretação de gráfico e associação sem aviso de transição.",
      ],
      barreira_rag_associada: "flexibilidade_cognitiva",
      principio_dua_primario: "representacao",
      palavras_chave_busca: ["flexibilidade cognitiva", "funções executivas", "transição", "mudança de regra"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Rótulo de Contexto e Tipo de Tarefa no Topo da Questão",
          objetivo_andaime:
            "Sinalizar explicitamente a mudança de tema ou de tipo de operação antes do início da leitura do enunciado.",
          acoes_permitidas: ["Adicionar tag curta de transição no cabeçalho da questão."],
          restricoes_escopo: ["Proibido revelar qual fórmula ou conceito responde à questão."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Agrupamento por Natureza Cognitiva e Divisor de Transição",
          objetivo_andaime:
            "Inserir divisor visual explícito sempre que o texto-base ou a regra de resposta mudar em relação à questão anterior.",
          acoes_permitidas: ["Inserir barra divisória de mudança de contexto."],
          restricoes_escopo: ["Proibido alterar o conteúdo avaliado nas questões."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Ancoragem de Transição e Ativação de Conhecimento Prévio",
          objetivo_andaime:
            "Apoiar o desligamento do esquema mental anterior e a ativação do novo esquema exigido pela questão.",
          acoes_permitidas: ["Incluir quadro curto de transição e destacar a nova regra do comando."],
          restricoes_escopo: ["Proibido fornecer definições conceituais que façam parte da Trava Curricular."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "CORTESE-2015-META-TREINO-COGNITIVO",
          citacao_curta:
            "Apoios estruturais diretos no ambiente e na tarefa são necessários para contornar demandas de flexibilidade e funções executivas.",
          tipo_evidencia: "meta_analise",
          ponto_verificacao_dua: "DUA Diretriz 6 / Ponto 6.2",
        },
      ],
    },
    {
      id_caracteristica: "bloqueio_iniciacao_tarefas_abertas",
      nome: "Bloqueio na iniciação de tarefas abertas sem ponto de partida estruturado",
      descricao_observavel:
        "O estudante demora muito para começar a resolver questões abertas por dificuldade executiva em selecionar o primeiro passo diante de uma folha em branco.",
      exemplos_manifestacao_sala: [
        "Permanece parado olhando para a questão por vários minutos até que o professor indique por onde começar.",
        "Deixa questões abertas em branco, mas responde prontamente assim que recebe a primeira pergunta-guia.",
      ],
      barreira_rag_associada: "iniciacao_tarefa",
      principio_dua_primario: "acao_e_expressao",
      palavras_chave_busca: ["iniciação de tarefa", "ponto de partida", "andaime cognitivo", "planejamento"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Indicação Explícita do Ponto de Partida",
          objetivo_andaime: "Sinalizar ao estudante qual é a primeira ação concreta para iniciar a questão.",
          acoes_permitidas: ["Adicionar nota curta de partida ('Comece identificando no texto o trecho que fala sobre...')."],
          restricoes_escopo: ["Proibido apontar a resposta ou resolver o primeiro passo pelo aluno."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Estruturação do Primeiro Passo e Campos de Partida",
          objetivo_andaime: "Substituir o vazio inicial da resposta por um campo de aquecimento estruturado.",
          acoes_permitidas: ["Dividir a área de resposta iniciando por um campo objetivo de ancoragem."],
          restricoes_escopo: ["Proibido preencher o campo pelo aluno."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Andaime de Iniciação com Conectivo Neutro e Roteiro",
          objetivo_andaime:
            "Fornecer estrutura de início de frase estritamente sintática (sem conteúdo da trava) e roteiro visual de partida.",
          acoes_permitidas: ["Oferecer iniciador frasal neutro ('Com base nos dados apresentados, verifica-se que...')."],
          restricoes_escopo: ["Proibido incluir termos da resposta no iniciador frasal."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "GAASTRA-2016-META-INTERVENCOES-SALA",
          citacao_curta:
            "Instruções claras de início de tarefa e estruturação antecedente reduzem a latência de engajamento em estudantes com TDAH.",
          tipo_evidencia: "revisao_sistematica",
          ponto_verificacao_dua: "DUA Diretriz 6 / Ponto 6.2",
        },
      ],
    },
    {
      id_caracteristica: "ritmo_processamento_pressao_temporal",
      nome: "Sobrecarga por velocidade de processamento sob pressão de tempo e volume textual",
      descricao_observavel:
        "O estudante realiza o raciocínio correto quando dispõe de tempo para decodificar as informações, mas bloqueia diante de enunciados prolixos com excesso de rodeios sintáticos.",
      exemplos_manifestacao_sala: [
        "Demora o dobro do tempo na leitura de contextualizações longas que não contêm dados essenciais para a questão.",
        "Não consegue concluir as últimas questões da prova por lentidão na decodificação de frases na voz passiva.",
      ],
      barreira_rag_associada: "velocidade_processamento",
      principio_dua_primario: "representacao",
      palavras_chave_busca: ["velocidade de processamento", "tempo adicional", "clareza sintática"],
      diretrizes_andaime: {
        nivel_1: {
          nivel: 1,
          rotulo: "Adaptação Leve — Destaque da Pergunta Central e Dados Essenciais",
          objetivo_andaime:
            "Permitir que o estudante identifique rapidamente onde está o comando nuclear da questão sem precisar reler todo o texto várias vezes.",
          acoes_permitidas: ["Destacar em negrito a frase que contém a pergunta central da questão."],
          restricoes_escopo: ["Proibido cortar parágrafos ou simplificar termos técnicos."],
        },
        nivel_2: {
          nivel: 2,
          rotulo: "Adaptação Moderada — Ordem Direta no Comando e Recomendação de Tempo Flexível",
          objetivo_andaime:
            "Reorganizar períodos excessivamente longos do comando para a ordem sintática direta (Sujeito-Verbo-Objeto).",
          acoes_permitidas: ["Converter frases na voz passiva do comando em frases curtas na ordem direta."],
          restricoes_escopo: ["Proibido substituir vocabulário técnico-científico avaliado por sinônimos infantis."],
        },
        nivel_3: {
          nivel: 3,
          rotulo: "Adaptação Intensiva — Apresentação Direta de Premissas + Comando + Tempo Estendido",
          objetivo_andaime:
            "Apresentar as premissas do problema em tópicos objetivos seguidos do comando direto, minimizando o custo de decodificação periférica.",
          acoes_permitidas: ["Organizar as informações do enunciado em tópicos curtos ('Contexto:', 'Situação:', 'Comando:')."],
          restricoes_escopo: ["Proibido eliminar a operação cognitiva exigida."],
        },
      },
      referencias_bibliograficas: [
        {
          doc_id: "NCEO-TOOLKIT-TEMPO-EXTRA-2026",
          citacao_curta:
            "A acomodação de tempo adicional combinada à redução de barreiras de acesso na apresentação da prova beneficia estudantes com menor velocidade de processamento.",
          tipo_evidencia: "relatorio_tecnico",
          ponto_verificacao_dua: "DUA Diretriz 2 / Ponto 2.1",
        },
      ],
    },
  ],
};
FALLBACK_OFFICIAL_CATALOG.total_caracteristicas = FALLBACK_OFFICIAL_CATALOG.caracteristicas.length;

/**
 * Busca o catálogo oficial de características funcionais atômicas via `GET /api/v1/catalogs/characteristics`.
 * Caso o servidor não esteja acessível, retorna o catálogo oficial local validado.
 */
export async function fetchCharacteristicsCatalog(): Promise<{
  catalog: CharacteristicsCatalogResponse;
  fromServer: boolean;
}> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/catalogs/characteristics`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (response.ok) {
      const data = (await response.json()) as CharacteristicsCatalogResponse;
      return { catalog: data, fromServer: true };
    }
  } catch {
    // Fallback resiliente para catálogo local
  }
  return { catalog: FALLBACK_OFFICIAL_CATALOG, fromServer: false };
}

/**
 * Calcula localmente o vetor cirúrgico de características ativadas vs. bloqueadas (mesma regra determinística do Backend).
 */
export function buildLocalSurgicalSelection(
  selectedIds: string[],
  catalog: CharacteristicsCatalogResponse = FALLBACK_OFFICIAL_CATALOG
): SurgicalSelectionResponse {
  const uniqueIds = Array.from(new Set(selectedIds.map((id) => id.trim()).filter(Boolean)));
  if (uniqueIds.length === 0) {
    throw new IrisApiError(
      "Selecione pelo menos uma característica funcional observada em sala de aula para definir o escopo permitido de adaptação antes de avançar.",
      "EMPTY_CHARACTERISTIC_SELECTION",
      422,
      "selected_ids"
    );
  }

  const catalogMap = new Map(catalog.caracteristicas.map((c) => [c.id_caracteristica, c]));
  const unknown = uniqueIds.filter((id) => !catalogMap.has(id));
  if (unknown.length > 0) {
    throw new IrisApiError(
      `Característica(s) funcional(is) não reconhecida(s) no catálogo: ${unknown.join(", ")}.`,
      "UNKNOWN_CHARACTERISTIC_ID",
      422,
      "selected_ids"
    );
  }

  const selectedSet = new Set(uniqueIds);
  const activeCharacteristics = uniqueIds.map((id) => catalogMap.get(id)!);
  const blockedIds = catalog.caracteristicas
    .map((c) => c.id_caracteristica)
    .filter((id) => !selectedSet.has(id));

  return {
    status: "success",
    message: `Escopo cirúrgico registrado: ${uniqueIds.length} característica(s) ativada(s) para adaptação e ${blockedIds.length} característica(s) bloqueada(s) para preservar a autonomia do estudante.`,
    id_catalogo: catalog.id_catalogo,
    total_catalog_characteristics: catalog.caracteristicas.length,
    selected_count: uniqueIds.length,
    blocked_count: blockedIds.length,
    selected_ids: uniqueIds,
    blocked_ids: blockedIds,
    active_characteristics: activeCharacteristics,
    scope_isolation_rule:
      "O pipeline de adaptação atuará exclusivamente sobre as características em 'selected_ids'. Todas as dimensões listadas em 'blocked_ids' permanecem bloqueadas para intervenção, preservando 100% da estrutura e autonomia original.",
  };
}

/**
 * Submete a seleção cirúrgica da Etapa 2 para `POST /api/v1/catalogs/characteristics/select`
 * e persiste o vetor cirúrgico validado na sessão do cliente (`sessionStorage`).
 */
export async function submitSurgicalCharacteristicSelection(
  selectedIds: string[],
  catalog: CharacteristicsCatalogResponse = FALLBACK_OFFICIAL_CATALOG
): Promise<SurgicalSelectionResponse> {
  // 1. Validação imediata de seleção vazia no cliente
  if (!Array.isArray(selectedIds) || selectedIds.filter((id) => id.trim().length > 0).length === 0) {
    throw new IrisApiError(
      "Selecione pelo menos uma característica funcional observada em sala de aula para definir o escopo permitido de adaptação antes de avançar.",
      "EMPTY_CHARACTERISTIC_SELECTION",
      422,
      "selected_ids"
    );
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/catalogs/characteristics/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_ids: selectedIds,
        id_catalogo: catalog.id_catalogo,
      }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      if (detail && typeof detail === "object") {
        throw new IrisApiError(
          detail.detail || "Falha ao validar a seleção cirúrgica de características.",
          detail.code || "VALIDATION_ERROR",
          response.status,
          detail.field
        );
      }
      throw new IrisApiError(
        "Falha ao validar a seleção cirúrgica de características no servidor.",
        "HTTP_ERROR",
        response.status
      );
    }

    const result = (await response.json()) as SurgicalSelectionResponse;
    saveSurgicalSelectionToSession(result);
    return result;
  } catch (err) {
    if (err instanceof IrisApiError) {
      throw err;
    }
    // Se o backend estiver offline, aplica a validação determinística local e persiste na sessão
    const fallbackResult = buildLocalSurgicalSelection(selectedIds, catalog);
    saveSurgicalSelectionToSession(fallbackResult);
    return fallbackResult;
  }
}

/**
 * Persiste o vetor cirúrgico de seleção na sessão do navegador (Stateless / Zero-Database no servidor).
 */
export function saveSurgicalSelectionToSession(selection: SurgicalSelectionResponse): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SURGICAL_VECTOR_STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

/**
 * Recupera o vetor cirúrgico salvo na sessão do navegador.
 */
export function loadSurgicalSelectionFromSession(): SurgicalSelectionResponse | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SURGICAL_VECTOR_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SurgicalSelectionResponse;
  } catch {
    return null;
  }
}

export const STEP1_STATE_STORAGE_KEY = "iris_session_step1_state_v1";

/**
 * Persiste o material e metadados da Etapa 1 na sessão do navegador para revisão ao voltar da Etapa 2.
 */
export function saveStep1StateToSession(state: Step1SessionState): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STEP1_MATERIAL_STORAGE_KEY, state.textContent);
    window.sessionStorage.setItem(STEP1_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

/**
 * Recupera o material e metadados da Etapa 1 salvos na sessão do navegador.
 */
export function loadStep1StateFromSession(): Step1SessionState | null {
  if (typeof window === "undefined") return null;
  try {
    const rawState = window.sessionStorage.getItem(STEP1_STATE_STORAGE_KEY);
    if (rawState) {
      return JSON.parse(rawState) as Step1SessionState;
    }
    const rawText = window.sessionStorage.getItem(STEP1_MATERIAL_STORAGE_KEY);
    if (rawText) {
      return {
        textContent: rawText,
        metadata: null,
        selectedFile: null,
        confirmedForStep2: true,
      };
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Remove o material da Etapa 1 da sessão do navegador ao limpar o formulário.
 */
export function clearStep1StateFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STEP1_MATERIAL_STORAGE_KEY);
    window.sessionStorage.removeItem(STEP1_STATE_STORAGE_KEY);
  } catch {
    // Ignora caso sessionStorage esteja indisponível
  }
}

