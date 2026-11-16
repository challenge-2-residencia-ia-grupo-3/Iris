import { describe, expect, it } from "vitest";
import {
  definirAprovacao,
  editarQuestao,
  EstadoRevisao,
  homologar,
  podeExportar,
  podeHomologar,
  resumo,
  versaoFinal,
} from "../src/services/reviewState";

const base = (): EstadoRevisao => ({
  homologada: false,
  questoes: [
    { id: "q1", original: "o1", adaptado: "a1", aprovada: false, editada: false },
    { id: "q2", original: "o2", adaptado: "a2", aprovada: false, editada: false },
  ],
});
const tudoAprovado = () => definirAprovacao(definirAprovacao(base(), "q1", true), "q2", true);

describe("revisão: edição imediata", () => {
  it("atualiza a versão final na hora e marca a questão como editada", () => {
    const e = editarQuestao(base(), "q1", "texto do professor");
    expect(e.questoes[0]).toMatchObject({ adaptado: "texto do professor", editada: true });
    expect(versaoFinal(e)).toBe("texto do professor\n\na2");
  });
  it("não mexe no original nem em outras questões", () => {
    const e = editarQuestao(base(), "q1", "x");
    expect(e.questoes[0].original).toBe("o1");
    expect(e.questoes[1]).toEqual(base().questoes[1]);
  });
  it("mesmo texto não conta como edição", () => {
    const e = tudoAprovado();
    expect(editarQuestao(e, "q1", "a1").questoes[0]).toMatchObject({ aprovada: true, editada: false });
  });
});

describe("revisão: Human-in-the-Loop", () => {
  it("começa sem poder homologar nem exportar", () => {
    expect(podeHomologar(base())).toBe(false);
    expect(podeExportar(base(), true)).toBe(false);
  });
  it("aprovar todas as questões não libera a exportação: falta a homologação", () => {
    const e = tudoAprovado();
    expect(podeHomologar(e)).toBe(true);
    expect(podeExportar(e, true)).toBe(false);
  });
  it("só homologa com todas aprovadas", () => {
    expect(homologar(definirAprovacao(base(), "q1", true)).homologada).toBe(false);
    expect(homologar(tudoAprovado()).homologada).toBe(true);
  });
  it("exporta só homologado e com tudo salvo", () => {
    const e = homologar(tudoAprovado());
    expect(podeExportar(e, true)).toBe(true);
    expect(podeExportar(e, false)).toBe(false);
  });
  it("editar depois de homologar revoga a aprovação da questão e a homologação", () => {
    const e = editarQuestao(homologar(tudoAprovado()), "q2", "mudou");
    expect(e.homologada).toBe(false);
    expect(e.questoes[1].aprovada).toBe(false);
    expect(podeExportar(e, true)).toBe(false);
  });
  it("desaprovar depois de homologar revoga a homologação", () => {
    expect(definirAprovacao(homologar(tudoAprovado()), "q1", false).homologada).toBe(false);
  });
  it("sem questões nunca se homologa", () => {
    expect(homologar({ questoes: [], homologada: false }).homologada).toBe(false);
  });
  it("resumo conta aprovadas", () => {
    expect(resumo(definirAprovacao(base(), "q1", true))).toEqual({ aprovadas: 1, total: 2 });
  });
});
