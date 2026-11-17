import type { Step5Entrada } from "./comparisonCards";

/**
 * Exemplo ILUSTRATIVO para ver a tela sem rodar o pipeline (`/etapa-5?demo=1`).
 * Não é saída real do Agente Adaptador: a tela mostra um aviso quando este exemplo está ativo.
 */
export const ETAPA5_DEMO: Step5Entrada = {
  titulo: "Ciências — Ciclo da água (exemplo)",
  questoes: [
    {
      id: "q1",
      original: "Leia o texto sobre o ciclo da água, identifique as etapas e explique a evaporação.",
      adaptado: "1. [ ] **Leia** o texto sobre o ciclo da água.\n2. [ ] **Identifique** as etapas.\n3. [ ] **Explique** a evaporação.",
      justificativas: [
        "Cada verbo de comando virou um item numerado, para não sobrecarregar a memória de trabalho.",
        "Os verbos foram destacados em negrito para orientar o início de cada etapa.",
      ],
      id_caracteristica: "sobrecarga_memoria_trabalho_comandos_multiplos",
      nivel: 2,
      adaptacao_aplicada: true,
    },
    {
      id: "q2",
      original: "Descreva a condensação e dê um exemplo do dia a dia.",
      adaptado: "**Passo 1**\n**Descreva** a condensação.\nResposta: ______________________________\n\n**Passo 2**\n**Dê** um exemplo do dia a dia.\nResposta: ______________________________\n\nRevise se você preencheu todos os passos.",
      justificativas: ["Os dois comandos foram separados em passos, cada um com espaço próprio de resposta."],
      id_caracteristica: "sobrecarga_memoria_trabalho_comandos_multiplos",
      nivel: 3,
      adaptacao_aplicada: true,
    },
  ],
};
