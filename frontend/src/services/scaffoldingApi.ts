/**
 * Cliente HTTP e persistência em sessão para a Calibragem do Nível de Andaime Cognitivo e
 * Definição de Travas Curriculares Inegociáveis (Histórias 1.3.1 e 1.3.2 — Issues #12 e #13).
 *
 * Endpoints consumidos:
 * - GET  /api/v1/scaffolding/levels
 * - POST /api/v1/scaffolding/calibrate
 * - POST /api/v1/scaffolding/curriculum-locks/validate
 *
 * Oferece contingência offline / local utilizando o catálogo oficial modular importado,
 * garantindo conformidade com o princípio Zero-Database e alta resiliência.
 */

import { IrisApiError } from "./materialsApi";
import {
  CharacteristicItem,
  FALLBACK_OFFICIAL_CATALOG,
} from "./catalogsApi";

export type ScaffoldingLevel = 1 | 2 | 3;

export interface ScaffoldingLevelMeta {
  nivel: ScaffoldingLevel;
  rotulo: string;
  nome_curto: string;
  objetivo_geral: string;
  foco_pedagogico: string;
  transformacoes_estruturais: string[];
  salvaguardas_antimuleta: string[];
}

export interface CharacteristicScaffoldingDirectiveItem {
  id_caracteristica: string;
  nome_caracteristica: string;
  nivel: ScaffoldingLevel;
  rotulo: string;
  objetivo_andaime: string;
  acoes_permitidas: string[];
  restricoes_escopo: string[];
}

export interface CurriculumLockInput {
  conceitos_obrigatorios: string[];
  termos_tecnicos_intocaveis?: string[];
  habilidade_bncc?: string | null;
  verbo_comando_bncc?: string | null;
  objetivo_avaliativo?: string | null;
  observacao_adaptacao_docente?: string | null;
}

export interface AuditorInvariantsContract {
  blindagem_ativa: boolean;
  conceitos_obrigatorios: string[];
  termos_tecnicos_intocaveis: string[];
  verbo_comando_bncc: string;
  habilidade_bncc: string | null;
  objetivo_avaliativo: string | null;
  operacao_cognitiva: string;
  trcc_minimo_exigido: number;
  alerta_anti_muleta_auditor: string;
}

export interface PreventiveAntiCrutchAlert {
  emitido: boolean;
  severidade: "none" | "warning" | "critical";
  codigo: string;
  titulo: string;
  mensagem: string;
  conflitos_detectados: string[];
  recomendacao_pedagogica: string;
  nivel_sugerido: ScaffoldingLevel | null;
}

export interface CurriculumLockExample {
  id_exemplo: string;
  disciplina: string;
  rotulo: string;
  conceitos_obrigatorios: string[];
  termos_tecnicos_intocaveis: string[];
  habilidade_bncc: string;
  verbo_comando_bncc: string;
  objetivo_avaliativo: string;
}

export interface ScaffoldingCalibrationResult {
  status: string;
  nivel: ScaffoldingLevel;
  rotulo_nivel: string;
  nome_curto: string;
  objetivo_geral: string;
  foco_pedagogico: string;
  transformacoes_estruturais: string[];
  salvaguardas_antimuleta: string[];
  total_caracteristicas_afetadas: number;
  caracteristicas_afetadas: CharacteristicScaffoldingDirectiveItem[];
  caracteristicas_bloqueadas_ids: string[];
  aviso_antimuleta: string;
  trava_curricular?: CurriculumLockInput;
  invariantes_auditor?: AuditorInvariantsContract;
  alerta_preventivo_antimuleta?: PreventiveAntiCrutchAlert;
  pii_removido_automaticamente?: boolean;
}

export interface ScaffoldingCalibrationPayload {
  selected_ids: string[];
  nivel: ScaffoldingLevel;
  id_catalogo?: string;
  trava_curricular?: CurriculumLockInput;
}

export const SCAFFOLDING_STORAGE_KEY = "iris_session_scaffolding_v1";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const AVISO_ANTIMULETA_PADRAO =
  "A calibração do andaime cognitivo ajusta o formato de apresentação, fragmentação e suporte procedimental " +
  "da atividade escolar. O sistema é estritamente proibido de fornecer respostas prontas, reduzir conceitos " +
  "obrigatórios ou produzir as inferências avaliadas pela questão.";

export const EXEMPLOS_TRAVAS_CURRICULARES: CurriculumLockExample[] = [
  {
    id_exemplo: "lp_interpretacao_inferencia",
    disciplina: "Língua Portuguesa",
    rotulo: "Interpretação de Texto e Inferência",
    conceitos_obrigatorios: ["sentido figurado", "ironia", "intenção do autor"],
    termos_tecnicos_intocaveis: ["ironia", "metáfora"],
    habilidade_bncc: "EF67LP08",
    verbo_comando_bncc: "inferir",
    objetivo_avaliativo: "Avaliar interpretação de texto e inferência de sentido implícito na crônica.",
  },
  {
    id_exemplo: "mat_equacao_1grau",
    disciplina: "Matemática",
    rotulo: "Equação Polinomial do 1º Grau",
    conceitos_obrigatorios: ["equação", "incógnita", "2x + 6 = 14"],
    termos_tecnicos_intocaveis: ["incógnita", "2x + 6 = 14"],
    habilidade_bncc: "EF07MA18",
    verbo_comando_bncc: "calcular",
    objetivo_avaliativo: "Resolver problemas que possam ser representados por equações polinomiais de 1º grau.",
  },
  {
    id_exemplo: "cie_fotossintese",
    disciplina: "Ciências",
    rotulo: "Fotossíntese e Fluxo de Energia",
    conceitos_obrigatorios: ["fotossíntese", "cloroplastos", "luz solar", "glicose"],
    termos_tecnicos_intocaveis: ["cloroplastos", "glicose"],
    habilidade_bncc: "EF06CI05",
    verbo_comando_bncc: "explicar",
    objetivo_avaliativo: "Explicar a conversão de energia luminosa em energia química nas células vegetais.",
  },
];

export const FALLBACK_SCAFFOLDING_LEVELS: ScaffoldingLevelMeta[] = [
  {
    nivel: 1,
    rotulo: "Nível 1 — Adaptação Leve (Acessibilidade e Destaque Visual)",
    nome_curto: "Leve",
    objetivo_geral:
      "Ajustes de formatação, organização visual e destaque tipográfico, preservando 100% da estrutura frasal, sintática e da complexidade original do conteúdo.",
    foco_pedagogico: "Acessibilidade perceptiva, foco atencional e redução de distratibilidade visual.",
    transformacoes_estruturais: [
      "Aplicação de negrito em palavras-chave e verbos de comando (ex.: identifique, calcule, explique).",
      "Destaque de conectivos restritivos críticos (ex.: NÃO, EXCETO, APENAS, INCORRETA).",
      "Espaçamento ampliado e respiro visual entre parágrafos e alternativas.",
    ],
    salvaguardas_antimuleta: [
      "Proibido reescrever enunciados ou simplificar vocabulário conceitual.",
      "Proibido fragmentar a questão em subitens ou alterar a ordem dos elementos.",
      "Preserva integralmente a extensão textual e a complexidade sintática.",
    ],
  },
  {
    nivel: 2,
    rotulo: "Nível 2 — Adaptação Moderada (Fragmentação e Checklist de Etapas)",
    nome_curto: "Moderado",
    objetivo_geral:
      "Divisão da atividade em etapas explícitas com checklists de execução (passo a passo), chunking de blocos textuais extensos e inserção de caixas de apoio/glossário contextual.",
    foco_pedagogico: "Redução da sobrecarga da memória de trabalho e organização sequencial da resolução.",
    transformacoes_estruturais: [
      "Fragmentação estruturada (chunking) de parágrafos longos em blocos de leitura direta.",
      "Conversão de múltiplos comandos conjugados em listas sequenciais de checagem ([ ]).",
      "Inserção de caixas de apoio contextual ou glossário contextual discreto.",
    ],
    salvaguardas_antimuleta: [
      "Proibido responder ou resolver qualquer etapa pelo estudante.",
      "Proibido sugerir a fórmula, regra ou inferência exigida pela habilidade curricular.",
      "Mantém a totalidade das operações e comandos originais solicitados.",
    ],
  },
  {
    nivel: 3,
    rotulo: "Nível 3 — Adaptação Intensiva (Decomposição Guiada e Pausas Ativas)",
    nome_curto: "Intensivo",
    objetivo_geral:
      "Apresentação guiada de uma etapa por vez com campos de registro dedicados, lembretes de autorregulação, pausas ativas estratégicas e organizadores visuais gráficos.",
    foco_pedagogico:
      "Suporte intensivo à função executiva, iniciação de tarefa e autorregulação em avaliações densas.",
    transformacoes_estruturais: [
      "Decomposição em subetapas com caixas de resolução exclusivas para cada etapa.",
      "Lembretes de checagem intermediária ('Revise se você concluiu a etapa anterior antes de prosseguir').",
      "Indicação de pausas estratégicas de autorregulação e respiração entre blocos avaliativos.",
      "Inclusão de organizadores visuais/gráficos para suporte à estruturação da resposta.",
    ],
    salvaguardas_antimuleta: [
      "Proibido o efeito muleta: a IA jamais faz as inferências ou fornece a resolução pelo aluno.",
      "Preservação inegociável dos objetivos de aprendizagem e dos conceitos da Trava Curricular.",
      "Garante a mesma habilidade avaliada, modificando unicamente o formato de demonstração.",
    ],
  },
];

const RE_HABILIDADE_INTERPRETACAO =
  /\b(?:interpreta[cç][aã]o(?:\s+de\s+texto|\s+textual)?|interpretar|infer[eê]ncia|inferir|sentido\s+(?:impl[ií]cito|figurado|conotativo)|ideia\s+central|ironia|ambiguidade|compreens[aã]o\s+leitora|dedu[cç][aã]o|deduzir|subentendido|hip[oó]tese)\b/i;

const RE_MULETA_INTERPRETACAO =
  /\b(?:resumo\s+interpretativo|resumir\s+o\s+texto|resumo\s+do\s+texto|resumo\s+explicativo|explicar\s+o\s+sentido|explica[cç][aã]o\s+do\s+sentido|entregar\s+a\s+interpreta[cç][aã]o|dizer\s+o\s+que\s+o\s+autor\s+quis\s+dizer|explicar\s+a\s+ironia|explicar\s+a\s+met[aá]fora|antecipar\s+a\s+infer[eê]ncia|dar\s+a\s+ideia\s+central|s[ií]ntese\s+interpretativa|resposta\s+pronta|gabarito|indicar\s+a\s+alternativa\s+correta)\b/i;

const RE_HABILIDADE_CALCULO =
  /\b(?:calcular|c[aá]lculo|resolver\s+a?\s*equa[cç][aã]o|equa[cç][aã]o|inc[oó]gnita|opera[cç][aã]o\s+alg[eé]brica|f[oó]rmula|propor[cç][aã]o|regra\s+de\s+tr[eê]s|sistema\s+linear|demonstrar|determinar\s+o\s+valor)\b/i;

const RE_MULETA_CALCULO =
  /\b(?:f[oó]rmula\s+pronta|dar\s+a\s+f[oó]rmula|entregar\s+a\s+f[oó]rmula|equa[cç][aã]o\s+montada|montar\s+a\s+equa[cç][aã]o|resolver\s+o\s+primeiro\s+passo|passo\s+resolvido|resultado\s+intermedi[aá]rio|isolar\s+a\s+inc[oó]gnita\s+pelo\s+aluno|resposta\s+pronta|gabarito|indicar\s+a\s+alternativa\s+correta)\b/i;

const RE_HABILIDADE_CONCEITUAL =
  /\b(?:definir|defini[cç][aã]o|conceituar|classificar|identificar\s+o\s+conceito|diferenciar|nomear|reconhecer\s+a\s+fun[cç][aã]o)\b/i;

const RE_MULETA_DEFINICAO =
  /\b(?:definir\s+o\s+termo\s+avaliado|dar\s+a\s+defini[cç][aã]o\s+pronta|explicar\s+o\s+conceito\s+no\s+enunciado|gloss[aá]rio\s+com\s+a\s+resposta|destacar\s+a\s+resposta|indicar\s+a\s+alternativa\s+correta|resposta\s+pronta|gabarito)\b/i;

/**
 * Validador Preventivo de Perda Cognitiva / Anti-Muleta executado localmente (RF-09).
 */
export function evaluatePreventiveAntiCrutchLocally(
  nivel: ScaffoldingLevel,
  selectedIds: string[],
  lock?: CurriculumLockInput | null
): PreventiveAntiCrutchAlert {
  const safeLock: CurriculumLockInput = {
    conceitos_obrigatorios: lock?.conceitos_obrigatorios || [],
    termos_tecnicos_intocaveis: lock?.termos_tecnicos_intocaveis || [],
    habilidade_bncc: lock?.habilidade_bncc || null,
    verbo_comando_bncc: lock?.verbo_comando_bncc || null,
    objetivo_avaliativo: lock?.objetivo_avaliativo || null,
    observacao_adaptacao_docente: lock?.observacao_adaptacao_docente || null,
  };

  const textoHabilidade = [
    safeLock.objetivo_avaliativo,
    safeLock.habilidade_bncc,
    safeLock.verbo_comando_bncc,
    safeLock.conceitos_obrigatorios.join(" "),
  ]
    .filter(Boolean)
    .join(" ");

  const textoPedidoDocente = [
    safeLock.observacao_adaptacao_docente,
    safeLock.objetivo_avaliativo,
  ]
    .filter(Boolean)
    .join(" ");

  const avaliaInterpretacao = RE_HABILIDADE_INTERPRETACAO.test(textoHabilidade);
  const matchMuletaInterpretacao = textoPedidoDocente.match(RE_MULETA_INTERPRETACAO);

  const avaliaCalculo = RE_HABILIDADE_CALCULO.test(textoHabilidade);
  const matchMuletaCalculo = textoPedidoDocente.match(RE_MULETA_CALCULO);

  const avaliaConceito =
    RE_HABILIDADE_CONCEITUAL.test(textoHabilidade) || safeLock.conceitos_obrigatorios.length > 0;
  const matchMuletaDefinicao = textoPedidoDocente.match(RE_MULETA_DEFINICAO);

  if (avaliaInterpretacao && matchMuletaInterpretacao) {
    const termo = matchMuletaInterpretacao[0];
    return {
      emitido: true,
      severidade: "critical",
      codigo: "CONTRADICAO_DIRETA_INTERPRETACAO",
      titulo: "Alerta Preventivo Anti-Muleta: Risco Crítico de Perda Cognitiva",
      mensagem: `A questão avalia interpretação/inferência textual, mas foi solicitado '${termo}'. Fornecer resumo interpretativo ou explicar o sentido implícito entrega a resposta pronta ao aluno e invalida o objetivo avaliativo da BNCC.`,
      conflitos_detectados: [
        `Solicitação de '${termo}' contradiz diretamente a habilidade avaliada de interpretação/inferência textual.`,
      ],
      recomendacao_pedagogica:
        "Remova o pedido de resumo interpretativo/explicação de sentido e utilize destaque tipográfico (Nível 1) ou fragmentação da leitura em blocos sem antecipar a inferência (Nível 2).",
      nivel_sugerido: nivel === 3 ? 2 : nivel,
    };
  }

  if (avaliaCalculo && matchMuletaCalculo) {
    const termo = matchMuletaCalculo[0];
    return {
      emitido: true,
      severidade: "critical",
      codigo: "CONTRADICAO_DIRETA_CALCULO",
      titulo: "Alerta Preventivo Anti-Muleta: Antecipação Indevida de Resolução",
      mensagem: `A questão avalia resolução matemática ou algébrica, mas foi solicitado '${termo}'. Entregar a equação montada ou etapas resolvidas elimina o raciocínio avaliado.`,
      conflitos_detectados: [
        `Solicitação de '${termo}' contradiz a habilidade avaliada de resolução matemática/algébrica.`,
      ],
      recomendacao_pedagogica:
        "Substitua a entrega da fórmula/cálculo pronto por um checklist de verificação procedural (Nível 2) preservando intactos os dados numéricos e a incógnita.",
      nivel_sugerido: nivel === 3 ? 2 : nivel,
    };
  }

  if (avaliaConceito && matchMuletaDefinicao) {
    const termo = matchMuletaDefinicao[0];
    return {
      emitido: true,
      severidade: "critical",
      codigo: "CONTRADICAO_DIRETA_CONCEITO",
      titulo: "Alerta Preventivo Anti-Muleta: Exposição da Resposta Conceitual",
      mensagem: `A adaptação solicitada ('{${termo}}') antecipa a definição ou alternativa avaliada pela questão.`,
      conflitos_detectados: [
        `Solicitação de '${termo}' entrega diretamente o conceito que é objeto de avaliação.`,
      ],
      recomendacao_pedagogica:
        "Mantenha os conceitos obrigatórios protegidos na Trava Curricular e limite o suporte ao destaque dos verbos de comando e organização visual.",
      nivel_sugerido: 1,
    };
  }

  if (nivel === 3 && avaliaInterpretacao) {
    return {
      emitido: true,
      severidade: "warning",
      codigo: "RISCO_NIVEL_INTENSIVO_INFERENCIA",
      titulo: "Atenção Anti-Muleta: Decomposição Intensiva em Questão de Inferência",
      mensagem:
        "Você selecionou o Nível 3 (Intensivo) para uma atividade cujo objetivo avaliativo envolve interpretação textual ou inferência de sentido. Decompor uma questão inferencial em subetapas muito guiadas pode induzir a conclusão lógica pelo estudante.",
      conflitos_detectados: [
        "Nível 3 (Adaptação Intensiva com decomposição guiada em subetapas) selecionado para questão que avalia interpretação/inferência.",
      ],
      recomendacao_pedagogica:
        "Considere calibrar para o Nível 2 (Moderado) ou Nível 1 (Leve). Caso mantenha o Nível 3, o Agente Adaptador e o Agente Auditor aplicarão trava estrita proibindo dicas sobre o sentido implícito.",
      nivel_sugerido: 2,
    };
  }

  const termosIntocaveis = safeLock.termos_tecnicos_intocaveis || [];

  if (
    nivel === 3 &&
    (selectedIds.includes("bloqueio_iniciacao_tarefas_abertas") ||
      selectedIds.includes("organizacao_sequencial_expressao_escrita")) &&
    termosIntocaveis.length > 0
  ) {
    const listaTermos = termosIntocaveis.slice(0, 4).join(", ");
    return {
      emitido: true,
      severidade: "warning",
      codigo: "CAUTELA_GLOSSARIO_TERMOS_TRAVADOS",
      titulo: "Salvaguarda Anti-Muleta: Termos Técnicos Protegidos no Suporte Guiado",
      mensagem: `O suporte guiado de iniciação/expressão escrita está ativo no Nível ${nivel}, porém os termos [${listaTermos}] foram marcados como Trava Curricular Inegociável.`,
      conflitos_detectados: [
        `Suporte intensivo de iniciação/expressão escrita ativo no Nível ${nivel} com termos técnicos intocáveis (${listaTermos}).`,
      ],
      recomendacao_pedagogica:
        "Os organizadores e pistas de iniciação estruturarão apenas a forma da resposta, ficando estritamente proibidos de definir, substituir ou antecipar o emprego dos termos técnicos travados.",
      nivel_sugerido: null,
    };
  }

  return {
    emitido: false,
    severidade: "none",
    codigo: "OK_NO_CONFLICT",
    titulo: "Trava curricular compatível com o nível de andaime",
    mensagem:
      "Nenhuma contradição pedagógica detectada entre a habilidade avaliada e o suporte configurado.",
    conflitos_detectados: [],
    recomendacao_pedagogica:
      "A parametrização preserva o rigor cognitivo e os invariantes para o Agente Auditor.",
    nivel_sugerido: null,
  };
}

/**
 * Constrói localmente o contrato de invariantes obrigatórios para o Agente Auditor (RF-08).
 */
export function buildAuditorInvariantsLocally(
  lock: CurriculumLockInput | null | undefined,
  alert: PreventiveAntiCrutchAlert
): AuditorInvariantsContract {
  const conceitos = Array.from(
    new Set([
      ...(lock?.conceitos_obrigatorios || []),
      ...(lock?.termos_tecnicos_intocaveis || []),
    ].map((c) => c.trim()).filter(Boolean))
  );
  const termos = Array.from(
    new Set(
      (lock?.termos_tecnicos_intocaveis?.length
        ? lock.termos_tecnicos_intocaveis
        : conceitos
      )
        .map((t) => t.trim())
        .filter(Boolean)
    )
  );
  const objetivo = lock?.objetivo_avaliativo?.trim() || null;
  const bnccInline = objetivo?.match(/\b(?:EF\d{2}[A-Z]{2}\d{2}|EM\d{2}[A-Z]{3}\d{3})\b/);
  const habBncc = lock?.habilidade_bncc?.trim() || (bnccInline ? bnccInline[0] : null);
  let verbo = lock?.verbo_comando_bncc?.trim().toLowerCase() || "";
  if (!verbo && objetivo) {
    const palavrasObj = objetivo.match(/[A-Za-zÀ-ÖØ-öø-ÿ]{3,}/g) || [];
    for (const p of palavrasObj) {
      const low = p.toLowerCase();
      if (VERBOS_COMANDO_MAP[low]) {
        verbo = VERBOS_COMANDO_MAP[low];
        break;
      }
    }
  }
  if (!verbo) verbo = "identificar";
  const blindagemAtiva = Boolean(
    conceitos.length > 0 || habBncc || objetivo || lock?.verbo_comando_bncc
  );

  const operacao =
    objetivo ||
    (habBncc && conceitos.length > 0
      ? `Demonstrar a habilidade ${habBncc} preservando ${conceitos.slice(0, 4).join(", ")}.`
      : conceitos.length > 0
      ? `Preservar integralmente os conceitos obrigatórios: ${conceitos.slice(0, 5).join(", ")}.`
      : "Executar a operação cognitiva exigida pela questão escolar sem redução de rigor.");

  const alertaAuditor = alert.emitido
    ? `${alert.titulo}: ${alert.recomendacao_pedagogica}`
    : conceitos.length > 0
    ? `Proibido omitir, substituir ou explicar de forma conclusiva os invariantes: ${conceitos.join(", ")}.`
    : AVISO_ANTIMULETA_PADRAO;

  return {
    blindagem_ativa: blindagemAtiva,
    conceitos_obrigatorios: conceitos,
    termos_tecnicos_intocaveis: termos,
    verbo_comando_bncc: verbo,
    habilidade_bncc: habBncc,
    objetivo_avaliativo: objetivo,
    operacao_cognitiva: operacao,
    trcc_minimo_exigido: 0.95,
    alerta_anti_muleta_auditor: alertaAuditor,
  };
}

/**
 * Calibração local síncrona / fallback quando o Backend FastAPI estiver indisponível.
 */
export function calibrateScaffoldingLocally(
  selectedIds: string[],
  nivel: ScaffoldingLevel,
  catalog = FALLBACK_OFFICIAL_CATALOG,
  travaCurricular?: CurriculumLockInput
): ScaffoldingCalibrationResult {
  if (![1, 2, 3].includes(nivel)) {
    throw new IrisApiError(
      `Nível de andaime inválido (${nivel}). Deve ser 1 (Leve), 2 (Moderado) ou 3 (Intensivo).`,
      "INVALID_SCAFFOLDING_LEVEL",
      422,
      "nivel"
    );
  }

  const uniqueIds = Array.from(new Set(selectedIds));
  if (uniqueIds.length === 0) {
    throw new IrisApiError(
      "Selecione ao menos 1 característica funcional na Etapa 2 antes de calibrar o nível de andaime.",
      "EMPTY_CHARACTERISTIC_SELECTION",
      422,
      "selected_ids"
    );
  }

  const catalogMap = new Map<string, CharacteristicItem>(
    catalog.caracteristicas.map((c) => [c.id_caracteristica, c])
  );

  const unknown = uniqueIds.filter((id) => !catalogMap.has(id));
  if (unknown.length > 0) {
    throw new IrisApiError(
      `Característica(s) funcional(is) não reconhecida(s) no catálogo: ${unknown.join(", ")}.`,
      "UNKNOWN_CHARACTERISTIC_ID",
      422,
      "selected_ids"
    );
  }

  const nivelKey = `nivel_${nivel}` as "nivel_1" | "nivel_2" | "nivel_3";
  const diretrizes: CharacteristicScaffoldingDirectiveItem[] = uniqueIds.map((id) => {
    const item = catalogMap.get(id)!;
    const guideline = item.diretrizes_andaime[nivelKey];
    return {
      id_caracteristica: item.id_caracteristica,
      nome_caracteristica: item.nome,
      nivel,
      rotulo: guideline.rotulo,
      objetivo_andaime: guideline.objetivo_andaime,
      acoes_permitidas: [...guideline.acoes_permitidas],
      restricoes_escopo: [...guideline.restricoes_escopo],
    };
  });

  const allIds = catalog.caracteristicas.map((c) => c.id_caracteristica);
  const blockedIds = allIds.filter((id) => !uniqueIds.includes(id)).sort();
  const meta = FALLBACK_SCAFFOLDING_LEVELS.find((m) => m.nivel === nivel)!;

  const cleanLock: CurriculumLockInput = {
    conceitos_obrigatorios: Array.from(
      new Set((travaCurricular?.conceitos_obrigatorios || []).map((c) => c.trim()).filter(Boolean))
    ),
    termos_tecnicos_intocaveis: Array.from(
      new Set(
        (travaCurricular?.termos_tecnicos_intocaveis || []).map((t) => t.trim()).filter(Boolean)
      )
    ),
    habilidade_bncc: travaCurricular?.habilidade_bncc?.trim() || null,
    verbo_comando_bncc: travaCurricular?.verbo_comando_bncc?.trim().toLowerCase() || null,
    objetivo_avaliativo: travaCurricular?.objetivo_avaliativo?.trim() || null,
    observacao_adaptacao_docente: travaCurricular?.observacao_adaptacao_docente?.trim() || null,
  };

  const alertaPreventivo = evaluatePreventiveAntiCrutchLocally(nivel, uniqueIds, cleanLock);
  const invariantesAuditor = buildAuditorInvariantsLocally(cleanLock, alertaPreventivo);

  return {
    status: "success",
    nivel,
    rotulo_nivel: meta.rotulo,
    nome_curto: meta.nome_curto,
    objetivo_geral: meta.objetivo_geral,
    foco_pedagogico: meta.foco_pedagogico,
    transformacoes_estruturais: [...meta.transformacoes_estruturais],
    salvaguardas_antimuleta: [...meta.salvaguardas_antimuleta],
    total_caracteristicas_afetadas: diretrizes.length,
    caracteristicas_afetadas: diretrizes,
    caracteristicas_bloqueadas_ids: blockedIds,
    aviso_antimuleta: AVISO_ANTIMULETA_PADRAO,
    trava_curricular: cleanLock,
    invariantes_auditor: invariantesAuditor,
    alerta_preventivo_antimuleta: alertaPreventivo,
    pii_removido_automaticamente: false,
  };
}

/**
 * Consulta metadados informativos dos 3 níveis de andaime no Backend, com fallback local.
 */
export async function fetchScaffoldingLevels(): Promise<ScaffoldingLevelMeta[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/scaffolding/levels`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.niveis) && data.niveis.length === 3) {
        return data.niveis as ScaffoldingLevelMeta[];
      }
    }
  } catch {
    // Falha silenciosa para contingência local
  }

  return FALLBACK_SCAFFOLDING_LEVELS;
}

/**
 * Calibra a diretiva de andaime e travas curriculares enviando o payload ao Backend FastAPI, com contingência local.
 */
export async function calibrateScaffoldingSession(
  payload: ScaffoldingCalibrationPayload
): Promise<ScaffoldingCalibrationResult> {
  try {
    const bodyObj: Record<string, unknown> = {
      selected_ids: payload.selected_ids,
      nivel: payload.nivel,
      id_catalogo: payload.id_catalogo || "tdah_funcoes_executivas_v1",
    };
    if (payload.trava_curricular) {
      bodyObj.trava_curricular = payload.trava_curricular;
    }

    const res = await fetch(`${API_BASE_URL}/api/v1/scaffolding/calibrate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(bodyObj),
    });

    if (res.ok) {
      const data = (await res.json()) as ScaffoldingCalibrationResult;
      return data;
    }

    const errorJson = await res.json().catch(() => null);
    const detail = errorJson?.detail;
    if (detail && typeof detail === "object") {
      throw new IrisApiError(
        detail.detail || "Erro de validação na calibração de andaime.",
        detail.code || "SCAFFOLDING_VALIDATION_ERROR",
        res.status,
        detail.field
      );
    }
  } catch (err) {
    if (err instanceof IrisApiError) {
      throw err;
    }
    // Falha de rede: fallback local determinístico
  }

  return calibrateScaffoldingLocally(
    payload.selected_ids,
    payload.nivel,
    FALLBACK_OFFICIAL_CATALOG,
    payload.trava_curricular
  );
}

/**
 * Valida explicitamente a Trava Curricular Inegociável e o Alerta Anti-Muleta no Backend, com contingência local.
 */
export async function validateCurriculumLocksSession(
  payload: ScaffoldingCalibrationPayload
): Promise<ScaffoldingCalibrationResult> {
  const lock = payload.trava_curricular;
  const hasAnyLock =
    Boolean(lock?.conceitos_obrigatorios && lock.conceitos_obrigatorios.length > 0) ||
    Boolean(lock?.termos_tecnicos_intocaveis && lock.termos_tecnicos_intocaveis.length > 0) ||
    Boolean(lock?.objetivo_avaliativo && lock.objetivo_avaliativo.trim()) ||
    Boolean(lock?.habilidade_bncc && lock.habilidade_bncc.trim());

  if (!hasAnyLock) {
    throw new IrisApiError(
      "Defina ao menos um conceito-chave obrigatório ou o objetivo avaliativo/BNCC para validar a Trava Curricular.",
      "EMPTY_CURRICULUM_LOCK",
      422,
      "conceitos_obrigatorios"
    );
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/scaffolding/curriculum-locks/validate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        selected_ids: payload.selected_ids,
        nivel: payload.nivel,
        id_catalogo: payload.id_catalogo || "tdah_funcoes_executivas_v1",
        trava_curricular: payload.trava_curricular,
      }),
    });

    if (res.ok) {
      return (await res.json()) as ScaffoldingCalibrationResult;
    }

    const errorJson = await res.json().catch(() => null);
    const detail = errorJson?.detail;
    if (detail && typeof detail === "object") {
      throw new IrisApiError(
        detail.detail || "Erro de validação na Trava Curricular.",
        detail.code || "CURRICULUM_LOCK_VALIDATION_ERROR",
        res.status,
        detail.field
      );
    }
  } catch (err) {
    if (err instanceof IrisApiError) {
      throw err;
    }
  }

  return calibrateScaffoldingLocally(
    payload.selected_ids,
    payload.nivel,
    FALLBACK_OFFICIAL_CATALOG,
    payload.trava_curricular
  );
}

/**
 * Persiste a calibração de andaime e travas curriculares aprovadas na sessão do navegador (Zero-Database).
 */
export function saveScaffoldingToSession(result: ScaffoldingCalibrationResult): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SCAFFOLDING_STORAGE_KEY, JSON.stringify(result));
  } catch {
    // Ignora restrições de sessionStorage
  }
}

/**
 * Recupera a calibração de andaime e travas curriculares salvas na sessão do navegador.
 */
export function loadScaffoldingFromSession(): ScaffoldingCalibrationResult | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SCAFFOLDING_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ScaffoldingCalibrationResult;
  } catch {
    return null;
  }
}

/**
 * Limpa a calibração de andaime da sessão do navegador.
 */
export function clearScaffoldingFromSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(SCAFFOLDING_STORAGE_KEY);
  } catch {
    // Ignora restrições de sessionStorage
  }
}

const STOPWORDS_EXTRACAO = new Set([
  "para", "como", "qual", "quais", "onde", "quando", "sobre", "texto", "abaixo",
  "leia", "responda", "questao", "questão", "alternativa", "correta", "incorreta",
  "assinale", "marque", "seguinte", "seguintes", "entre", "pelo", "pela", "pelos",
  "pelas", "esse", "essa", "este", "esta", "isso", "aquilo", "muito", "mais",
  "menos", "cada", "todo", "toda", "todos", "todas", "outro", "outra", "mesmo",
  "mesma", "apenas", "somente", "então", "porque", "pois", "assim", "durante",
  "depois", "antes", "através", "acordo", "segundo", "aluno", "estudante",
  "escola", "professor", "atividade", "exercício", "exercicio", "enunciado",
]);

const VERBOS_COMANDO_MAP: Record<string, string> = {
  analise: "analisar", analisar: "analisar",
  avalie: "avaliar", avaliar: "avaliar",
  calcule: "calcular", calcular: "calcular",
  classifique: "classificar", classificar: "classificar",
  compare: "comparar", comparar: "comparar",
  conclua: "concluir", concluir: "concluir",
  deduza: "deduzir", deduzir: "deduzir",
  descreva: "descrever", descrever: "descrever",
  determine: "determinar", determinar: "determinar",
  diferencie: "diferenciar", diferenciar: "diferenciar",
  explique: "explicar", explicar: "explicar",
  identifique: "identificar", identificar: "identificar",
  infira: "inferir", inferir: "inferir",
  interprete: "interpretar", interpretar: "interpretar",
  justifique: "justificar", justificar: "justificar",
  localize: "localizar", localizar: "localizar",
  relacione: "relacionar", relacionar: "relacionar",
  resolva: "resolver", resolver: "resolver",
};

/**
 * Extrai automaticamente os conceitos-chave, termos técnicos e o objetivo avaliativo
 * diretamente do texto do material enviado/colado na Etapa 1.
 */
export function extractCurriculumLocksFromMaterialLocally(
  materialText: string
): CurriculumLockInput {
  if (!materialText || !materialText.trim()) {
    return {
      conceitos_obrigatorios: [],
      termos_tecnicos_intocaveis: [],
      habilidade_bncc: null,
      verbo_comando_bncc: null,
      objetivo_avaliativo: null,
    };
  }

  const text = materialText.trim();
  const bnccMatch = text.match(/\b(?:EF\d{2}[A-Z]{2}\d{2}|EM\d{2}[A-Z]{3}\d{3})\b/);
  const habBncc = bnccMatch ? bnccMatch[0] : null;

  const palavras = text.match(/[A-Za-zÀ-ÖØ-öø-ÿ]{3,}/g) || [];
  let verboEncontrado: string | null = null;
  for (const p of palavras) {
    const low = p.toLowerCase();
    if (VERBOS_COMANDO_MAP[low]) {
      verboEncontrado = VERBOS_COMANDO_MAP[low];
      break;
    }
  }

  const conceitos: string[] = [];
  const vistos = new Set<string>();
  const addTermo = (raw: string) => {
    const t = raw.replace(/^[.,:;!?()[\]{}"'“”\s]+|[.,:;!?()[\]{}"'“”\s]+$/g, "");
    if (t.length < 3 || t.startsWith("[")) return;
    const k = t.toLowerCase();
    if (!vistos.has(k) && !STOPWORDS_EXTRACAO.has(k)) {
      vistos.add(k);
      conceitos.push(t);
    }
  };

  const equacoes = text.match(/\b\d*[a-zA-Z]\s*[+\-]\s*\d+\s*=\s*\d+\b/g) || [];
  equacoes.forEach(addTermo);

  const aspas = text.match(/"([^"]{3,45})"|“([^”]{3,45})”/g) || [];
  aspas.forEach(addTermo);

  for (const p of palavras) {
    const low = p.toLowerCase();
    if (
      p.length >= 6 &&
      !STOPWORDS_EXTRACAO.has(low) &&
      !VERBOS_COMANDO_MAP[low]
    ) {
      addTermo(low);
    }
    if (conceitos.length >= 6) break;
  }

  const verboCapitalizado = verboEncontrado
    ? verboEncontrado.charAt(0).toUpperCase() + verboEncontrado.slice(1)
    : "Compreender";
  const resumoConceitos =
    conceitos.length > 0
      ? conceitos.slice(0, 4).join(", ")
      : "os conceitos centrais da atividade";
  const objetivo = `${verboCapitalizado} ${resumoConceitos}${habBncc ? ` (${habBncc})` : ""}.`;

  return {
    conceitos_obrigatorios: conceitos.slice(0, 6),
    termos_tecnicos_intocaveis: conceitos.slice(0, 6),
    habilidade_bncc: habBncc,
    verbo_comando_bncc: verboEncontrado || "identificar",
    objetivo_avaliativo: objetivo,
  };
}

