// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InterventionFeedback } from "../src/components/InterventionFeedback";
import { criarPerfilPortatil, type PerfilPedagogicoPortatil, type RegistroIntervencao } from "../src/services/portableProfile";

const A = "atencao_sustentada_textos_longos";
const B = "sobrecarga_memoria_trabalho_comandos_multiplos";
const NOMES = { [A]: "Leitura de textos longos e densos", [B]: "Múltiplos comandos na mesma questão" };

function reg(estrategia: string, id: string, eficacia: RegistroIntervencao["eficacia"], dia: number, observacao: string | null = null): RegistroIntervencao {
  return { estrategia, id_caracteristica: id, eficacia, observacao, registrado_em: `2026-11-${String(dia).padStart(2, "0")}T12:00:00Z` };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const perfilVazio = () => criarPerfilPortatil([A, B]);

async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

function preencher({ car = A, estrategia = "Fragmentação em checklist", eficacia = "Alta", obs = "Terminou a prova." } = {}) {
  fireEvent.change(screen.getByLabelText("Característica"), { target: { value: car } });
  fireEvent.change(screen.getByLabelText("Estratégia utilizada"), { target: { value: estrategia } });
  fireEvent.click(screen.getByRole("radio", { name: eficacia }));
  if (obs !== null) fireEvent.change(screen.getByLabelText(/Observação pedagógica/), { target: { value: obs } });
}

describe("formulário de eficácia", () => {
  it("tem as três opções de eficácia e só a característica do perfil", () => {
    render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    expect(screen.getAllByRole("radio").map((r) => (r as HTMLInputElement).value)).toEqual(["alta", "media", "baixa"]);
    expect(screen.getByRole("radio", { name: "Média" })).toBeTruthy();
    const opcoes = within(screen.getByLabelText("Característica")).getAllByRole("option").map((o) => o.textContent);
    expect(opcoes).toEqual(["Selecione…", NOMES[A], NOMES[B]]);
  });

  it("registra: envia ao servidor, devolve o perfil atualizado e limpa o formulário", async () => {
    const perfil = perfilVazio();
    const atualizado: PerfilPedagogicoPortatil = { ...perfil, historico_intervencoes: [reg("Fragmentação em checklist", A, "alta", 11, "Terminou a prova.")] };
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ perfil: atualizado }) });
    vi.stubGlobal("fetch", f);
    const onAtualizado = vi.fn();
    render(<InterventionFeedback perfil={perfil} nomes={NOMES} onPerfilAtualizado={onAtualizado} />);
    preencher();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Registrar eficácia/ })); });
    await waitFor(() => expect(onAtualizado).toHaveBeenCalledWith(atualizado));
    const corpo = JSON.parse(f.mock.calls[0][1].body);
    expect(corpo.intervencao).toEqual({ estrategia: "Fragmentação em checklist", id_caracteristica: A, eficacia: "alta", observacao: "Terminou a prova." });
    expect((screen.getByLabelText("Estratégia utilizada") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Característica") as HTMLSelectElement).value).toBe(A); // mantém para o próximo registro
    expect((await screen.findByRole("status")).textContent).toMatch(/adicionado ao histórico/);
  });

  it("campos faltando: mostra o erro e não chama o servidor", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Registrar eficácia/ }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Escolha a característica/);
    fireEvent.change(screen.getByLabelText("Característica"), { target: { value: A } });
    fireEvent.click(screen.getByRole("button", { name: /Registrar eficácia/ }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Descreva a estratégia/);
    expect(f).not.toHaveBeenCalled();
  });

  it("conteúdo clínico recusado pelo servidor aparece como alerta e o perfil não muda", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 422,
      json: async () => ({ detail: { code: "CLINICAL_DATA_BLOCKED", detail: "Dados clínicos não são permitidos no Perfil Pedagógico Portátil." } }),
    }));
    const onAtualizado = vi.fn();
    render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={onAtualizado} />);
    preencher({ obs: "toma Ritalina" });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Registrar eficácia/ })); });
    expect((await screen.findByRole("alert")).textContent).toMatch(/Dados clínicos não são permitidos/);
    expect(onAtualizado).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Estratégia utilizada") as HTMLInputElement).value).toBe("Fragmentação em checklist"); // não perde o texto
  });

  it("mostra o contador da observação", () => {
    render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Observação pedagógica/), { target: { value: "abcde" } });
    expect(screen.getByText("5/500 caracteres")).toBeTruthy();
  });
});

describe("histórico", () => {
  const comHistorico = (): PerfilPedagogicoPortatil => ({
    ...perfilVazio(),
    historico_intervencoes: [
      reg("Tempo extra", B, "baixa", 13),
      reg("Fragmentação em checklist", A, "alta", 11, "Terminou a prova."),
      reg("Enunciado em etapas", A, "media", 12),
    ],
  });

  it("vazio: diz que ainda não há registros", () => {
    render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    expect(screen.getByText(/Nenhuma intervenção registrada ainda/)).toBeTruthy();
  });

  it("lista as intervenções da mais recente para a mais antiga, com nome da característica e eficácia em texto", () => {
    render(<InterventionFeedback perfil={comHistorico()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    const itens = within(screen.getByRole("list", { name: /Intervenções registradas/ })).getAllByRole("listitem");
    expect(itens.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Tempo extra"),
      expect.stringContaining("Enunciado em etapas"),
      expect.stringContaining("Fragmentação em checklist"),
    ]);
    expect(itens[0].textContent).toMatch(/Eficácia baixa/);
    expect(itens[0].textContent).toContain(NOMES[B]);
    expect(itens[2].textContent).toContain("Terminou a prova.");
    expect(screen.getByText(/Histórico \(3\)/)).toBeTruthy();
  });

  it("resume por característica", () => {
    render(<InterventionFeedback perfil={comHistorico()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    const resumo = screen.getByRole("list", { name: "Resumo por característica" });
    expect(resumo.textContent).toMatch(/Leitura de textos longos e densos: alta 1 • média 1 • baixa 0 \(última: média\)/);
  });

  it("sem nomes do catálogo, usa o id da característica", () => {
    render(<InterventionFeedback perfil={comHistorico()} onPerfilAtualizado={vi.fn()} />);
    expect(screen.getAllByText(new RegExp(A)).length).toBeGreaterThan(0);
  });
});

describe("acessibilidade (WCAG 2.1 AA)", () => {
  it("sem violações vazio, com histórico e com erro", async () => {
    const { container, rerender } = render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    expect(await violacoes(container)).toEqual([]);
    rerender(<InterventionFeedback perfil={{ ...perfilVazio(), historico_intervencoes: [reg("Checklist", A, "alta", 11, "Ok.")] }} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    expect(await violacoes(container)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: /Registrar eficácia/ }));
    await screen.findByRole("alert");
    expect(await violacoes(container)).toEqual([]);
  });

  it("botão e controles têm alvo de 44 px e a eficácia é um grupo nomeado", () => {
    render(<InterventionFeedback perfil={perfilVazio()} nomes={NOMES} onPerfilAtualizado={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Registrar eficácia/ }).className).toContain("min-h-[44px]");
    expect(screen.getByRole("group", { name: "Eficácia" })).toBeTruthy();
  });
});
