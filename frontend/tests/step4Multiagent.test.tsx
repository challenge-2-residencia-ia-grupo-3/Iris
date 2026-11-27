// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import { Step4AgentAdaptation } from "../src/components/Step4AgentAdaptation";
import {
  clearStep4ResultFromSession,
  fontesCitadas,
  loadStep4ResultFromSession,
  MultiAgentMaterialResponse,
  runMultiAgentAdaptation,
  saveStep4ResultToSession,
  STEP4_RESULT_STORAGE_KEY,
} from "../src/services/agentsApi";
import { STEP5_ADAPTACAO_STORAGE_KEY } from "../src/services/comparisonCards";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  pushMock.mockReset();
});

const MOCK_RESPONSE: MultiAgentMaterialResponse = {
  status: "success",
  titulo: "Atividade de Ciências",
  provider: "extractive",
  model: "deterministic-fallback",
  nivel: 2,
  selected_ids: ["sobrecarga_memoria_trabalho_comandos_multiplos"],
  pii_substituicoes: 0,
  total_questoes: 1,
  aprovadas_auditor: 1,
  requerem_revisao_humana: 0,
  total_ms: 42.5,
  total_tokens: 0,
  etapa5_entrada: {
    titulo: "Atividade de Ciências",
    questoes: [
      {
        id: "q_1",
        original: "Leia o texto e explique a fotossíntese.",
        adaptado: "1. [ ] **Leia** o texto\n2. [ ] **Explique** a fotossíntese.",
        justificativas: ["2 comandos separados em checklist."],
        id_caracteristica: "sobrecarga_memoria_trabalho_comandos_multiplos",
        nivel: 2,
        adaptacao_aplicada: true,
      },
    ],
  },
  questoes_trace: [
    {
      id: "q_1",
      numero_original: "1",
      original: "Leia o texto e explique a fotossíntese.",
      adaptado: "1. [ ] **Leia** o texto\n2. [ ] **Explique** a fotossíntese.",
      justificativas: ["2 comandos separados em checklist."],
      id_caracteristica: "sobrecarga_memoria_trabalho_comandos_multiplos",
      caracteristicas_selecionadas: ["sobrecarga_memoria_trabalho_comandos_multiplos"],
      nivel: 2,
      adaptacao_aplicada: true,
      aprovado_final: true,
      requer_revisao_humana: false,
      extrator: {
        invariants: {
          conceitos_obrigatorios: ["fotossíntese"],
          termos_tecnicos_intocaveis: ["fotossíntese"],
          verbo_comando_bncc: "explicar",
          operacao_cognitiva: "explicar o processo de fotossíntese",
          habilidade_bncc_sugerida: "EF06CI05",
          alerta_anti_muleta: "Não explique a reação pronta.",
          justificativa_preservacao: "Preserva conceito central.",
        },
        telemetry: {
          provider: "extractive",
          model: "deterministic-fallback",
          used_fallback: true,
          total_ms: 1.2,
          prompt_tokens: 0,
          completion_tokens: 0,
        },
      },
      estrategista: {
        diretiva: "Para sobrecarga_memoria_trabalho_comandos_multiplos: Ações do catálogo [T1]",
        intervencoes: [
          {
            id_caracteristica: "sobrecarga_memoria_trabalho_comandos_multiplos",
            texto: "Ações do catálogo [T1]",
            citacoes: ["T1"],
            origem: "catalogo",
          },
        ],
        fontes: [
          {
            rotulo: "T1",
            chunk_id: "c1",
            doc: "dua",
            titulo: "Diretrizes DUA",
            pagina: "10",
            url: "https://exemplo.org/dua",
            referencia: "Diretrizes DUA, p. 10",
            caracteristicas: ["sobrecarga_memoria_trabalho_comandos_multiplos"],
            aviso_de_uso: null,
          },
        ],
        caracteristicas_sem_evidencia: [],
        trechos_fora_do_filtro: [],
        intervencoes_descartadas: [],
        telemetry: {
          metodo_solicitado: "bm25",
          metodo_efetivo: "bm25",
          provider: "extractive",
          model: "deterministic-fallback",
          used_fallback: true,
          motivo_fallback: "provedor_sem_modelo",
          n_trechos: 1,
          total_ms: 12.4,
          total_tokens: 0,
        },
      },
      tentativas: [
        {
          tentativa: 1,
          texto_minuta: "1. [ ] **Leia** o texto\n2. [ ] **Explique** a fotossíntese.",
          justificativas: ["2 comandos separados em checklist."],
          escopo_aprovado: true,
          violacoes_escopo: [],
          trcc: 1.0,
          conceitos_retidos: ["fotossíntese"],
          conceitos_ausentes: [],
          intocaveis_ausentes: [],
          resolucao_indevida: false,
          intrusoes: [],
          aprovado_auditor: true,
          motivos_auditor: [],
          feedback_gerado: null,
          total_ms: 2.1,
        },
      ],
      ciclo_resumo: {
        chamadas: 3,
        chamadas_com_fallback: 3,
        total_ms: 15.7,
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        nivel: 2,
        limite_ms: 40000,
        dentro_do_limite: true,
      },
    },
  ],
};

describe("agentsApi e persistência em sessão", () => {
  it("salva e recupera o resultado da Etapa 4 e grava entrada da Etapa 5", () => {
    saveStep4ResultToSession(MOCK_RESPONSE);
    expect(loadStep4ResultFromSession()?.titulo).toBe("Atividade de Ciências");
    expect(window.sessionStorage.getItem(STEP4_RESULT_STORAGE_KEY)).toBeTruthy();
    expect(window.sessionStorage.getItem(STEP5_ADAPTACAO_STORAGE_KEY)).toBeTruthy();

    clearStep4ResultFromSession();
    expect(loadStep4ResultFromSession()).toBeNull();
  });

  it("runMultiAgentAdaptation envia POST para /api/v1/agents/adapt", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await runMultiAgentAdaptation({
      text: "Leia o texto e explique a fotossíntese.",
      selected_ids: ["sobrecarga_memoria_trabalho_comandos_multiplos"],
      nivel: 2,
      provider: "extractive",
    });

    expect(res.aprovadas_auditor).toBe(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/agents/adapt");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(loadStep4ResultFromSession()?.status).toBe("success");
  });
});

describe("fontes citadas na Etapa 4", () => {
  const est = MOCK_RESPONSE.questoes_trace[0].estrategista;
  const fonte = (rotulo: string) => ({ ...est.fontes[0], rotulo, chunk_id: `c-${rotulo}`, referencia: `Fonte ${rotulo}` });

  it("lista só as fontes que a diretiva cita, mesmo que a busca tenha devolvido mais", () => {
    const comCinco = {
      ...est,
      fontes: ["T1", "T2", "T3", "T4", "T5"].map(fonte),
      intervencoes: [
        { ...est.intervencoes[0], citacoes: ["T4"] },
        { ...est.intervencoes[0], citacoes: ["T1", "T4"] },
      ],
    };
    expect(fontesCitadas(comCinco).map((f) => f.rotulo)).toEqual(["T1", "T4"]);
  });

  it("sem citação na diretiva, não há fonte citada", () => {
    expect(fontesCitadas({ ...est, fontes: ["T1", "T2"].map(fonte), intervencoes: [] })).toEqual([]);
  });

  it("a tela mostra a fonte citada e esconde a que só veio da busca", async () => {
    const resposta: MultiAgentMaterialResponse = {
      ...MOCK_RESPONSE,
      questoes_trace: [
        {
          ...MOCK_RESPONSE.questoes_trace[0],
          estrategista: { ...est, fontes: [fonte("T1"), fonte("T2")] },
        },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => resposta }));
    render(
      <ThemeProvider>
        <Step4AgentAdaptation />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: /Executar Sistema Multiagentes/i }));
    await waitFor(() => expect(screen.getByTestId("fontes-citadas")).toBeTruthy());
    const bloco = screen.getByTestId("fontes-citadas").textContent ?? "";
    expect(bloco).toContain("Fonte T1");
    expect(bloco).not.toContain("Fonte T2");
  });
});

describe("Step4AgentAdaptation: renderização e acessibilidade (WCAG 2.1 AA)", () => {
  const renderStep4 = () =>
    render(
      <ThemeProvider>
        <Step4AgentAdaptation />
      </ThemeProvider>
    );

  it("renderiza sem violações de acessibilidade no estado inicial e após execução", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => MOCK_RESPONSE,
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderStep4();
    const initialAxe = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    expect(initialAxe.violations).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: /Executar Sistema Multiagentes/i }));
    await waitFor(() => expect(screen.getByText(/1\. Agente Extrator Curricular/i)).toBeTruthy());

    expect(screen.getByText(/2\. Agente Estrategista RAG/i)).toBeTruthy();
    expect(screen.getByText(/3\. Agente Adaptador/i)).toBeTruthy();
    expect(screen.getByText(/4\. Agente Auditor/i)).toBeTruthy();

    const afterAxe = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    expect(afterAxe.violations).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: /Avançar para Etapa 5/i }));
    expect(pushMock).toHaveBeenCalledWith("/etapa-5");
  });

  it("mostra a recomendação ao docente fora do texto da questão, e só quando ela existe", async () => {
    const comRecado: MultiAgentMaterialResponse = {
      ...MOCK_RESPONSE,
      questoes_trace: [{ ...MOCK_RESPONSE.questoes_trace[0], recomendacao_docente: "Ofereça tempo flexível." }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => comRecado }));
    renderStep4();
    fireEvent.click(screen.getByRole("button", { name: /Executar Sistema Multiagentes/i }));
    await waitFor(() => expect(screen.getByText(/3\. Agente Adaptador/i)).toBeTruthy());
    const bloco = screen.getByTestId("recomendacao-docente");
    expect(bloco.textContent).toContain("Ofereça tempo flexível.");
    expect(bloco.textContent).toContain("não vai para a prova");
    expect(bloco.closest("pre")).toBeNull();

    cleanup();
    window.sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => MOCK_RESPONSE }));
    renderStep4();
    fireEvent.click(screen.getByRole("button", { name: /Executar Sistema Multiagentes/i }));
    await waitFor(() => expect(screen.getByText(/3\. Agente Adaptador/i)).toBeTruthy());
    expect(screen.queryByTestId("recomendacao-docente")).toBeNull();
  });

  it("exibe aviso local e desabilita provedores externos quando política proíbe envio externo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          external_adaptation_allowed: false,
          anthropic_configured: true,
          groq_configured: false,
          ollama_online: true,
          default_providers_by_agent: {
            extrator: "ollama",
            estrategista: "ollama",
            adaptador: "ollama",
            auditor: "ollama",
          },
          auto_uses_external_llm: false,
          dados_enviados_quando_externo: [],
          dados_nunca_enviados: [],
          aviso_docente_externo: "Aviso externo",
          aviso_docente_local:
            "Processamento 100% local (Privacidade por Padrão): nenhum enunciado ou característica funcional sai desta máquina.",
        }),
      })
    );

    const { container } = renderStep4();
    await waitFor(() =>
      expect(screen.getByTestId("aviso-privacidade-llm").textContent).toContain("Processamento 100% local")
    );
    const anthropicOpt = screen.getByRole("option", { name: /Anthropic Claude Haiku/i }) as HTMLOptionElement;
    expect(anthropicOpt.disabled).toBe(true);
    expect(anthropicOpt.textContent).toContain("desativado pela escola");

    const results = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("exibe aviso explícito de transparência quando opt-in externo está ativo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          external_adaptation_allowed: true,
          anthropic_configured: true,
          groq_configured: false,
          ollama_online: true,
          default_providers_by_agent: {
            extrator: "ollama",
            estrategista: "ollama",
            adaptador: "anthropic",
            auditor: "anthropic",
          },
          auto_uses_external_llm: true,
          dados_enviados_quando_externo: [],
          dados_nunca_enviados: [],
          aviso_docente_externo:
            "Processamento com IA externa (Anthropic Claude): envio apenas do enunciado sanitizado, característica funcional e nível de apoio. Nunca são enviados nome do estudante ou Perfil Portátil.",
          aviso_docente_local: "Processamento 100% local",
        }),
      })
    );

    const { container } = renderStep4();
    await waitFor(() =>
      expect(screen.getByTestId("aviso-privacidade-llm").textContent).toContain("Processamento com IA externa")
    );
    const anthropicOpt = screen.getByRole("option", { name: /Anthropic Claude Haiku/i }) as HTMLOptionElement;
    expect(anthropicOpt.disabled).toBe(false);

    const results = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});
