// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PerfilImport } from "../src/components/PerfilImport";
import { Step2FunctionalProfile } from "../src/components/Step2FunctionalProfile";
import { Step3ScaffoldingLevel } from "../src/components/Step3ScaffoldingLevel";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { ENGAGEMENT_PROFILE_STORAGE_KEY, SURGICAL_VECTOR_STORAGE_KEY } from "../src/services/catalogsApi";
import { STEP4_RESULT_STORAGE_KEY } from "../src/services/agentsApi";
import { STEP5_ADAPTACAO_STORAGE_KEY } from "../src/services/comparisonCards";
import { criarPerfilPortatil, perfilParaJson } from "../src/services/portableProfile";
import { PERFIL_IMPORTADO_STORAGE_KEY } from "../src/services/portableProfileImport";
import { SCAFFOLDING_STORAGE_KEY } from "../src/services/scaffoldingApi";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const ID_A = "sobrecarga_memoria_trabalho_comandos_multiplos";
const ID_B = "retencao_dados_intermediarios_problemas_multietapas";

function perfilValido() {
  return {
    ...criarPerfilPortatil([ID_A, ID_B]),
    historico_intervencoes: [
      {
        estrategia: "Checklist com andaime nível 3",
        id_caracteristica: ID_A,
        eficacia: "alta" as const,
        observacao: null,
        registrado_em: "2026-11-20T12:00:00Z",
      },
    ],
  };
}

async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

function escolher(container: HTMLElement, conteudo: string, nome = "perfil.json") {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File([conteudo], nome, { type: "application/json" })] } });
}

beforeEach(() => {
  window.sessionStorage.clear();
  // Servidor fora do ar: vale a validação local do mesmo schema (o teste do servidor está em test_importacao_perfil.py).
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
});
afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("Importação do perfil no início do fluxo (História 3.2.2)", () => {
  it("mostra a prévia do que será restaurado e passa no axe", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    const previa = await screen.findByTestId("previa-importacao");
    expect(previa.textContent).toContain("2 características funcionais");
    expect(previa.textContent).toContain("Nível de suporte sugerido para a Etapa 3: Intensivo");
    expect(await violacoes(container)).toEqual([]);
  });

  it("só grava na sessão depois de 'Aplicar ao fluxo', e remove ao descartar", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    await screen.findByTestId("previa-importacao");
    expect(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Aplicar ao fluxo/ }));
    expect(screen.getByTestId("perfil-aplicado")).toBeTruthy();
    expect(JSON.parse(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)!).caracteristicas).toEqual([ID_A, ID_B]);

    fireEvent.click(screen.getByRole("button", { name: /Remover perfil importado/ }));
    expect(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)).toBeNull();
    expect(screen.queryByTestId("perfil-aplicado")).toBeNull();
  });

  it("arquivo corrompido mostra erro amigável sem gravar nada e a tela segue funcionando", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, "{isto está quebrado");
    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("não é um JSON válido");
    expect(alerta.textContent).toContain("continuar normalmente sem importar");
    expect(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)).toBeNull();
    expect(await violacoes(container)).toEqual([]);

    // Em seguida um arquivo válido ainda pode ser importado.
    escolher(container, perfilParaJson(perfilValido()));
    expect(await screen.findByTestId("previa-importacao")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("recusa arquivo que não é .json com a orientação certa", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, "%PDF-1.7", "perfil-aluno-8f7a2c1b.pdf");
    expect((await screen.findByRole("alert")).textContent).toContain("Envie o arquivo .json");
  });

  it("perfil com dado pessoal é recusado", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, JSON.stringify({ ...perfilValido(), nome: "Maria Souza" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Campo 'nome' proibido");
    expect(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)).toBeNull();
  });

  it("avisa que aplicar substitui a seleção já feita e, ao aplicar, a descarta", async () => {
    window.sessionStorage.setItem(SURGICAL_VECTOR_STORAGE_KEY, JSON.stringify({ id_catalogo: "x", selected_ids: [ID_B] }));
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    const previa = await screen.findByTestId("previa-importacao");
    expect(previa.textContent).toMatch(/substitui o que já está na sessão.*interesses.*Etapas 4 e 5/);
    fireEvent.click(screen.getByRole("button", { name: /Aplicar ao fluxo/ }));
    expect(window.sessionStorage.getItem(SURGICAL_VECTOR_STORAGE_KEY)).toBeNull();
  });

  it("aplicar também limpa interesses e o resultado das Etapas 4 e 5, e o aviso cita isso", async () => {
    for (const k of [ENGAGEMENT_PROFILE_STORAGE_KEY, STEP4_RESULT_STORAGE_KEY, STEP5_ADAPTACAO_STORAGE_KEY]) {
      window.sessionStorage.setItem(k, "{}");
    }
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    expect((await screen.findByTestId("previa-importacao")).textContent).toContain("Etapas 4 e 5");
    fireEvent.click(screen.getByRole("button", { name: /Aplicar ao fluxo/ }));
    for (const k of [ENGAGEMENT_PROFILE_STORAGE_KEY, STEP4_RESULT_STORAGE_KEY, STEP5_ADAPTACAO_STORAGE_KEY]) {
      expect(window.sessionStorage.getItem(k)).toBeNull();
    }
  });

  it("'Cancelar' na prévia de outro arquivo NÃO remove o perfil já aplicado", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    await screen.findByTestId("previa-importacao");
    fireEvent.click(screen.getByRole("button", { name: /Aplicar ao fluxo/ }));

    escolher(container, perfilParaJson(perfilValido()));
    await screen.findByTestId("previa-importacao");
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)).not.toBeNull();
    expect(screen.getByTestId("perfil-aplicado")).toBeTruthy();
    expect(screen.queryByTestId("previa-importacao")).toBeNull();
  });

  it("'Remover perfil importado' desfaz também a seleção e a calibração vindas do perfil", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    await screen.findByTestId("previa-importacao");
    fireEvent.click(screen.getByRole("button", { name: /Aplicar ao fluxo/ }));
    // O docente confirmou a Etapa 2 e a 3 com o que o perfil trouxe.
    window.sessionStorage.setItem(SURGICAL_VECTOR_STORAGE_KEY, JSON.stringify({ id_catalogo: "x", selected_ids: [ID_A] }));
    window.sessionStorage.setItem(SCAFFOLDING_STORAGE_KEY, JSON.stringify({ nivel: 3 }));

    fireEvent.click(screen.getByRole("button", { name: /Remover perfil importado/ }));

    expect(window.sessionStorage.getItem(PERFIL_IMPORTADO_STORAGE_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(SURGICAL_VECTOR_STORAGE_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(SCAFFOLDING_STORAGE_KEY)).toBeNull();
  });

  it("perfil sem característica mostra mensagem própria (validação local)", async () => {
    const { container } = render(<PerfilImport />);
    escolher(container, JSON.stringify({ ...criarPerfilPortatil([ID_A]), caracteristicas_selecionadas: [] }));
    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("nenhuma característica funcional selecionada");
    expect(alerta.textContent).not.toContain("não pôde ser lida");
  });

  it("não usa localStorage nem IndexedDB para o material importado", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { container } = render(<PerfilImport />);
    escolher(container, perfilParaJson(perfilValido()));
    await screen.findByTestId("previa-importacao");
    fireEvent.click(screen.getByRole("button", { name: /Aplicar ao fluxo/ }));
    expect(window.localStorage.length).toBe(0);
    for (const chamada of setItem.mock.calls) expect(chamada[0]).toBe(PERFIL_IMPORTADO_STORAGE_KEY);
  });
});

describe("Restauração nas etapas seguintes", () => {
  it("Etapa 3 abre com o nível do perfil pré-selecionado e o docente pode trocar", async () => {
    window.sessionStorage.setItem(
      PERFIL_IMPORTADO_STORAGE_KEY,
      JSON.stringify({
        codigo_anonimo: "aluno-8f7a2c1b",
        caracteristicas: [ID_A],
        alta_eficacia: [ID_A],
        nivel_andaime: 3,
        motivo_nivel: "Nível Intensivo: citado em 1 estratégia de eficácia alta do histórico do perfil.",
      })
    );
    const { container } = render(
      <ThemeProvider>
        <Step3ScaffoldingLevel />
      </ThemeProvider>
    );
    const nota = await screen.findByTestId("nivel-sugerido-perfil");
    expect(nota.textContent).toContain("Intensivo pré-selecionado pelo perfil aluno-8f7a2c1b");
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["false", "false", "true"]);
    fireEvent.click(radios[0]);
    expect(screen.getAllByRole("radio")[0].getAttribute("aria-checked")).toBe("true");
    expect(await violacoes(container)).toEqual([]);
  });

  it("Etapa 3 respeita a calibração que o docente já tinha feito na sessão", async () => {
    window.sessionStorage.setItem(
      PERFIL_IMPORTADO_STORAGE_KEY,
      JSON.stringify({ codigo_anonimo: "aluno-8f7a2c1b", caracteristicas: [ID_A], alta_eficacia: [], nivel_andaime: 3, motivo_nivel: "" })
    );
    window.sessionStorage.setItem(
      SCAFFOLDING_STORAGE_KEY,
      JSON.stringify({ nivel: 1, rotulo_nivel: "Leve", caracteristicas_afetadas: [], trava_curricular: null })
    );
    render(
      <ThemeProvider>
        <Step3ScaffoldingLevel />
      </ThemeProvider>
    );
    await waitFor(() => expect(screen.getAllByRole("radio")[0].getAttribute("aria-checked")).toBe("true"));
    expect(screen.queryByTestId("nivel-sugerido-perfil")).toBeNull();
  });

  it("Etapa 2 abre com as características do perfil pré-marcadas e avisa quando alguma não consta no catálogo", async () => {
    window.sessionStorage.setItem(
      PERFIL_IMPORTADO_STORAGE_KEY,
      JSON.stringify({
        codigo_anonimo: "aluno-8f7a2c1b",
        caracteristicas: [ID_A, ID_B, "caracteristica_que_nao_existe_no_catalogo"],
        alta_eficacia: [],
        nivel_andaime: null,
        motivo_nivel: "",
      })
    );
    render(
      <ThemeProvider>
        <Step2FunctionalProfile />
      </ThemeProvider>
    );
    const aviso = await screen.findByText(/Perfil aluno-8f7a2c1b aplicado/);
    expect(aviso).toBeTruthy();
    expect(await screen.findByText(/2 característica\(s\) pré-marcada\(s\)/)).toBeTruthy();
    expect(screen.getByText(/1 não consta\(m\) no catálogo ativo/)).toBeTruthy();

    // O aviso do perfil importado não some sozinho (os outros avisos da Etapa 2 somem em 4 s).
    await new Promise((r) => setTimeout(r, 4300));
    expect(screen.getByText(/Perfil aluno-8f7a2c1b aplicado/)).toBeTruthy();
  }, 10000);
});
