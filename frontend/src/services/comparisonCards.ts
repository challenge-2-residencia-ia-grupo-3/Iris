/**
 * Lógica da Etapa 5 — Revisão lado a lado (História 2.2.1 — Issue #21, RF-10/RF-13/RNF-09).
 * Funções puras (sem React, sem rede): montam o cartão pedagógico de cada questão a partir do catálogo
 * funcional oficial, marcam o que mudou entre original e adaptado e identificam os andaimes aplicados.
 */
import type { CharacteristicItem } from "./catalogsApi";

export type NivelAndaime = 1 | 2 | 3;

export interface QuestaoEtapa5 {
  id: string;
  original: string;
  adaptado: string;
  /** Uma frase por ação aplicada, como devolvida pelo Agente Adaptador. */
  justificativas: string[];
  /** Orientação ao docente; fica fora de `adaptado` e não é exportada. */
  recomendacao_docente?: string | null;
  /** Característica funcional tratada (id do catálogo). */
  id_caracteristica: string;
  nivel: NivelAndaime;
  adaptacao_aplicada: boolean;
}

export interface Step5Entrada {
  titulo?: string;
  questoes: QuestaoEtapa5[];
}

/** Entrega da Etapa 4 para a Etapa 5 (sessionStorage da aba, como nas demais etapas). */
export const STEP5_ADAPTACAO_STORAGE_KEY = "iris_session_step5_adaptacao_v1";

/** Confere o que veio do sessionStorage antes de usar: formato inválido vira "sem adaptação". */
export function validarEntrada(bruto: unknown): Step5Entrada | null {
  if (!bruto || typeof bruto !== "object") return null;
  const { titulo, questoes } = bruto as { titulo?: unknown; questoes?: unknown };
  if (!Array.isArray(questoes) || questoes.length === 0) return null;
  const ids = new Set<string>();
  const saida: QuestaoEtapa5[] = [];
  for (const q of questoes) {
    if (!q || typeof q !== "object") return null;
    const r = q as Record<string, unknown>;
    const nivel = r.nivel;
    if (
      typeof r.id !== "string" || !r.id || ids.has(r.id) ||
      typeof r.original !== "string" || typeof r.adaptado !== "string" || !r.adaptado.trim() ||
      typeof r.id_caracteristica !== "string" ||
      (nivel !== 1 && nivel !== 2 && nivel !== 3)
    ) return null;
    ids.add(r.id);
    saida.push({
      id: r.id,
      original: r.original,
      adaptado: r.adaptado,
      justificativas: Array.isArray(r.justificativas) ? r.justificativas.filter((j): j is string => typeof j === "string") : [],
      recomendacao_docente: typeof r.recomendacao_docente === "string" && r.recomendacao_docente.trim() ? r.recomendacao_docente.trim() : null,
      id_caracteristica: r.id_caracteristica,
      nivel,
      adaptacao_aplicada: r.adaptacao_aplicada !== false,
    });
  }
  return { titulo: typeof titulo === "string" ? titulo : undefined, questoes: saida };
}

export const PRINCIPIO_DUA_ROTULO: Record<string, string> = {
  representacao: "DUA I — Múltiplas formas de representação",
  acao_e_expressao: "DUA II — Múltiplas formas de ação e expressão",
  engajamento: "DUA III — Múltiplas formas de engajamento",
};

export interface ReferenciaCartao {
  doc_id: string;
  citacao_curta: string;
  ponto_verificacao_dua: string | null;
}

export interface CartaoPedagogico {
  /** Falso quando a característica não está no catálogo: o cartão avisa em vez de inventar fundamento. */
  caracteristicaEncontrada: boolean;
  caracteristicaId: string;
  caracteristicaNome: string;
  descricaoObservavel: string;
  principioDua: string;
  nivel: NivelAndaime;
  rotuloNivel: string;
  objetivoAndaime: string;
  acoesDoNivel: string[];
  justificativas: string[];
  /** Orientação ao docente da adaptação; ausente quando não há. */
  recomendacaoDocente?: string | null;
  referencias: ReferenciaCartao[];
  semMudanca: boolean;
}

export function montarCartao(q: QuestaoEtapa5, catalogo: readonly CharacteristicItem[]): CartaoPedagogico {
  const item = catalogo.find((c) => c.id_caracteristica === q.id_caracteristica);
  const semMudanca = !q.adaptacao_aplicada || q.adaptado.trim() === q.original.trim();
  const base = {
    caracteristicaId: q.id_caracteristica,
    nivel: q.nivel,
    justificativas: q.justificativas.map((j) => j.trim()).filter(Boolean),
    recomendacaoDocente: q.recomendacao_docente ?? null,
    semMudanca,
  };
  if (!item) {
    return {
      ...base,
      caracteristicaEncontrada: false,
      caracteristicaNome: "Característica não encontrada no catálogo",
      descricaoObservavel: "",
      principioDua: "",
      rotuloNivel: `Nível ${q.nivel}`,
      objetivoAndaime: "",
      acoesDoNivel: [],
      referencias: [],
    };
  }
  const diretriz = item.diretrizes_andaime[`nivel_${q.nivel}` as "nivel_1" | "nivel_2" | "nivel_3"];
  return {
    ...base,
    caracteristicaEncontrada: true,
    caracteristicaNome: item.nome,
    descricaoObservavel: item.descricao_observavel,
    principioDua: PRINCIPIO_DUA_ROTULO[item.principio_dua_primario] ?? item.principio_dua_primario,
    rotuloNivel: diretriz?.rotulo ?? `Nível ${q.nivel}`,
    objetivoAndaime: diretriz?.objetivo_andaime ?? "",
    acoesDoNivel: diretriz?.acoes_permitidas ?? [],
    referencias: item.referencias_bibliograficas.map((r) => ({
      doc_id: r.doc_id,
      citacao_curta: r.citacao_curta,
      ponto_verificacao_dua: r.ponto_verificacao_dua ?? null,
    })),
  };
}

// ---- o que mudou -------------------------------------------------------------------------------
export interface TrechoMarcado {
  texto: string;
  novo: boolean;
}

// RegExp por construtor: o tsconfig não declara `target`, e o literal com a flag "u" exigiria es6.
const BORDAS = new RegExp("^[^\\p{L}\\p{N}]+|[^\\p{L}\\p{N}]+$", "gu");
const limpar = (p: string) => p.replace(/\*\*/g, "").toLowerCase().replace(BORDAS, "");

/** Palavras do adaptado que não estavam no original, na mesma ordem (maior subsequência comum). */
export function marcarMudancas(original: string, adaptado: string): TrechoMarcado[] {
  const a = original.split(/\s+/).filter(Boolean).map(limpar);
  const palavras = adaptado.split(/(\s+)/);
  const b: { i: number; chave: string }[] = [];
  palavras.forEach((p, i) => {
    if (p && !/^\s+$/.test(p)) b.push({ i, chave: limpar(p) });
  });
  // LCS por programação dinâmica; textos de questão são curtos (limite de 5.000 caracteres).
  const n = a.length, m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j].chave && a[i] !== "" ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const mantidas = new Set<number>();
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j].chave && a[i] !== "") { mantidas.add(b[j].i); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  const saida: TrechoMarcado[] = [];
  const empilhar = (texto: string, novo: boolean) => {
    const ult = saida[saida.length - 1];
    if (ult && ult.novo === novo) ult.texto += texto;
    else saida.push({ texto, novo });
  };
  palavras.forEach((p, idx) => {
    if (p === "") return;
    if (/^\s+$/.test(p)) {
      // espaço entre duas palavras novas fica dentro do trecho novo
      const prox = b.find((x) => x.i > idx);
      const ult = saida[saida.length - 1];
      empilhar(p, !!ult && ult.novo && !!prox && !mantidas.has(prox.i));
    } else empilhar(p, limpar(p) !== "" && !mantidas.has(idx));
  });
  return saida;
}

export function contarTrechosNovos(trechos: readonly TrechoMarcado[]): number {
  return trechos.filter((t) => t.novo && t.texto.trim()).length;
}

// ---- andaimes aplicados ------------------------------------------------------------------------
export type IdIndicador = "verbos_destacados" | "checklist" | "passos_com_resposta" | "caixas_selecao" | "lembrete_conferencia";

export interface IndicadorAndaime {
  id: IdIndicador;
  rotulo: string;
  descricao: string;
  quantidade: number;
}

const LEMBRETE = /Revise se você preencheu todos os passos\./;

/**
 * Andaimes cognitivos identificados no TEXTO adaptado, pelos marcadores que o Agente Adaptador gera:
 * verbos em **negrito**, itens "1. [ ]", blocos "**Passo N**" com "Resposta: ____" e lembrete final.
 * Só aparece o que de fato está no texto: se o professor apagar o andaime, o indicador some.
 */
export function indicadoresAndaime(adaptado: string): IndicadorAndaime[] {
  const linhas = adaptado.split("\n");
  const negritos = (adaptado.match(/\*\*[^*\n]+\*\*/g) ?? []).filter((t) => !/^\*\*Passo \d+\*\*$/.test(t)).length;
  const checklist = linhas.filter((l) => /^\s*\d+\.\s\[[ xX]\]\s/.test(l)).length;
  const passos = linhas.filter((l) => /^\s*\*\*Passo \d+\*\*\s*$/.test(l)).length;
  const caixas = linhas.filter((l) => /^\s*\[ \]\s/.test(l)).length;
  const lista: IndicadorAndaime[] = [
    { id: "verbos_destacados", rotulo: "Verbos de comando em destaque", descricao: "Os verbos que dizem o que fazer aparecem em negrito.", quantidade: negritos },
    { id: "checklist", rotulo: "Etapas em lista de verificação", descricao: "Cada comando virou um item numerado com caixa para marcar.", quantidade: checklist },
    { id: "passos_com_resposta", rotulo: "Passos com espaço de resposta", descricao: "Um bloco por passo, com linha para registrar a resposta.", quantidade: passos },
    { id: "caixas_selecao", rotulo: "Caixas de conferência", descricao: "Comandos de leitura/observação com caixa para marcar.", quantidade: caixas },
    { id: "lembrete_conferencia", rotulo: "Lembrete de conferência final", descricao: "Aviso para revisar se todos os passos foram feitos.", quantidade: LEMBRETE.test(adaptado) ? 1 : 0 },
  ];
  return lista.filter((i) => i.quantidade > 0);
}

// ---- contraste (WCAG 2.1 AA) -------------------------------------------------------------------
export function luminancia(hex: string): number {
  const v = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((k) => parseInt(v.slice(k, k + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function razaoContraste(fg: string, bg: string): number {
  const [a, b] = [luminancia(fg), luminancia(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/** Cores dos indicadores e do trecho novo, em pares texto/fundo (claro e escuro), todas com ≥ 4,5:1. */
export const PALETA_ETAPA5 = {
  indicador: { claro: { fg: "#1F4650", bg: "#E6F0F2" }, escuro: { fg: "#CDE8F0", bg: "#1E3A44" } },
  aviso: { claro: { fg: "#5C2A00", bg: "#FFF1DC" }, escuro: { fg: "#FFE2B8", bg: "#4A2A08" } },
} as const;
