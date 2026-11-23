// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import catalogoRaw from "../../rag/catalogs/tdah_caracteristicas_funcionais.json";
import { JustificativaCard } from "../src/components/JustificativaCard";
import type { CharacteristicItem } from "../src/services/catalogsApi";
import { indicadoresAndaime, montarCartao, QuestaoEtapa5 } from "../src/services/comparisonCards";

const CATALOGO = catalogoRaw.caracteristicas as unknown as CharacteristicItem[];
afterEach(cleanup);

const questao = (extra: Partial<QuestaoEtapa5> = {}): QuestaoEtapa5 => ({
  id: "q1",
  original: "Para despertar a reflexão do leitor, a campanha faz uma referência irônica. Essa referência está presente em",
  adaptado: "A campanha faz uma referência irônica para despertar a reflexão do leitor.\n\n**Essa referência está presente em**",
  justificativas: ["Comando em ordem direta."],
  id_caracteristica: "ritmo_processamento_pressao_temporal",
  nivel: 2,
  adaptacao_aplicada: true,
  ...extra,
});

const cartao = (q: QuestaoEtapa5) => (
  <JustificativaCard numero={1} cartao={montarCartao(q, CATALOGO)} original={q.original} adaptado={q.adaptado} indicadores={indicadoresAndaime(q.adaptado)} />
);

describe("Etapa 5: recomendação ao docente no cartão", () => {
  it("aparece no cartão, com o aviso de que não vai para a prova", () => {
    render(cartao(questao({ recomendacao_docente: "Ofereça tempo flexível." })));
    const bloco = screen.getByTestId("recomendacao-docente");
    expect(bloco.textContent).toContain("Ofereça tempo flexível.");
    expect(bloco.textContent).toContain("não vai para a prova");
  });

  it("não aparece quando a adaptação não trouxe recomendação", () => {
    render(cartao(questao()));
    expect(screen.queryByTestId("recomendacao-docente")).toBeNull();
  });
});
