/**
 * Estado local da revisão docente (História 2.2.2 — RF-13, RNF-09). Funções puras: o componente só chama.
 *
 * As regras do Human-in-the-Loop aqui espelham as do servidor (que é quem manda): editar uma questão
 * aprovada tira a aprovação dela e a homologação; só se homologa com todas aprovadas; só se exporta
 * depois de homologar E com tudo já salvo no servidor.
 */
export interface QuestaoRevisao {
  id: string;
  original: string;
  adaptado: string;
  aprovada: boolean;
  editada: boolean;
}

export interface EstadoRevisao {
  questoes: QuestaoRevisao[];
  homologada: boolean;
}

export const SEPARADOR_QUESTOES = "\n\n";

export function editarQuestao(e: EstadoRevisao, id: string, adaptado: string): EstadoRevisao {
  return {
    homologada: false,
    questoes: e.questoes.map((q) =>
      q.id === id && q.adaptado !== adaptado ? { ...q, adaptado, editada: true, aprovada: false } : q
    ),
  };
}

export function definirAprovacao(e: EstadoRevisao, id: string, aprovada: boolean): EstadoRevisao {
  let mudou = false;
  const questoes = e.questoes.map((q) => {
    if (q.id !== id || q.aprovada === aprovada) return q;
    mudou = true;
    return { ...q, aprovada };
  });
  return mudou ? { questoes, homologada: false } : e;
}

export function podeHomologar(e: EstadoRevisao): boolean {
  return e.questoes.length > 0 && e.questoes.every((q) => q.aprovada);
}

export function homologar(e: EstadoRevisao): EstadoRevisao {
  return podeHomologar(e) ? { ...e, homologada: true } : e;
}

/** Botão de exportação: só com homologação explícita e sem alteração ainda por salvar. */
export function podeExportar(e: EstadoRevisao, salvo: boolean): boolean {
  return e.homologada && podeHomologar(e) && salvo;
}

export function versaoFinal(e: EstadoRevisao): string {
  return e.questoes.map((q) => q.adaptado.trim()).join(SEPARADOR_QUESTOES);
}

export function resumo(e: EstadoRevisao): { aprovadas: number; total: number } {
  return { aprovadas: e.questoes.filter((q) => q.aprovada).length, total: e.questoes.length };
}
