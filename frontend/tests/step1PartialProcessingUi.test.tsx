// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Step1MaterialIntake } from "../src/components/Step1MaterialIntake";
import { ThemeProvider } from "../src/contexts/ThemeContext";
import {
  extractPartialProcessingNotice,
  type MaterialResponse,
} from "../src/services/materialsApi";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const TEXTO_VALIDO_SANITIZADO =
  "Avaliação de Ciências sobre o ciclo da água e os estados físicos da matéria. Questão 1: Explique a evaporação.";

function renderStep1() {
  return render(
    <ThemeProvider>
      <Step1MaterialIntake />
    </ThemeProvider>
  );
}

function selecionarPdf(container: HTMLElement, nome = "prova.pdf") {
  const inputs = container.querySelectorAll('input[type="file"]');
  const inputMaterial = Array.from(inputs).find((el) =>
    (el.getAttribute("accept") || "").includes(".pdf")
  ) as HTMLInputElement;
  expect(inputMaterial).toBeTruthy();
  const file = new File(["%PDF-1.4\nconteudo simulado"], nome, { type: "application/pdf" });
  fireEvent.change(inputMaterial, { target: { files: [file] } });
}

function mockUploadResponse(payload: MaterialResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    })
  );
}

async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("extractPartialProcessingNotice (contrato backend/frontend)", () => {
  it("retorna null para resposta integralmente processada mesmo com observações visuais gerais", () => {
    const response: MaterialResponse = {
      status: "success",
      message: "Arquivo 'prova.pdf' processado via OCR e sanitizado com sucesso.",
      raw_text: TEXTO_VALIDO_SANITIZADO,
      metadata: {
        source_type: "scanned_pdf",
        char_count: TEXTO_VALIDO_SANITIZADO.length,
        word_count: 19,
        sanitized: false,
        pii_removed_count: 0,
        filename: "prova.pdf",
      },
      raw_content: {
        text: TEXTO_VALIDO_SANITIZADO,
        source_type: "scanned_pdf",
        pii_sanitized: true,
        metadata: {
          partial_extraction: false,
          failed_pages: [],
          unreadable_pages: [],
          ocr_unavailable_pages: [],
        },
      },
      visual_analysis: {
        notes: "Identificadas páginas com alta concentração de elementos visuais concorrentes.",
      },
    };
    expect(extractPartialProcessingNotice(response)).toBeNull();
  });

  it("identifica processamento parcial, deduplica visual_analysis.notes e tolera campos nulos/ausentes", () => {
    const notice = extractPartialProcessingNotice({
      status: "success",
      message:
        "Arquivo 'prova.pdf' processado parcialmente com avisos nas páginas 2. Confira as observações de análise visual antes de avançar.",
      raw_text: TEXTO_VALIDO_SANITIZADO,
      metadata: {
        source_type: "mixed_pdf",
        char_count: TEXTO_VALIDO_SANITIZADO.length,
        word_count: 19,
        sanitized: false,
        pii_removed_count: 0,
        filename: "prova.pdf",
      },
      raw_content: {
        text: TEXTO_VALIDO_SANITIZADO,
        source_type: "mixed_pdf",
        metadata: {
          partial_extraction: true,
          failed_pages: [],
          unreadable_pages: [2],
          ocr_unavailable_pages: [],
        },
      },
      visual_analysis: {
        notes:
          "Página 2: nenhum texto legível foi reconhecido pelo OCR nesta página digitalizada.; Página 2: nenhum texto legível foi reconhecido pelo OCR nesta página digitalizada.",
      },
    });

    expect(notice).not.toBeNull();
    expect(notice!.affectedPages).toEqual([2]);
    expect(notice!.notes).toEqual([
      "Página 2: nenhum texto legível foi reconhecido pelo OCR nesta página digitalizada.",
    ]);

    // Fallback seguro com campos opcionais ausentes/nulos
    const fallbackNotice = extractPartialProcessingNotice({
      status: "success",
      message: "",
      raw_text: TEXTO_VALIDO_SANITIZADO,
      metadata: {
        source_type: "scanned_pdf",
        char_count: TEXTO_VALIDO_SANITIZADO.length,
        word_count: 19,
        sanitized: false,
        pii_removed_count: 0,
      },
      raw_content: {
        text: TEXTO_VALIDO_SANITIZADO,
        source_type: "scanned_pdf",
        metadata: { partial_extraction: true, failed_pages: [2] },
      },
      visual_analysis: null,
    });
    expect(fallbackNotice).not.toBeNull();
    expect(fallbackNotice!.message).toContain("página 2");
    expect(fallbackNotice!.notes).toEqual([]);
    expect(extractPartialProcessingNotice(null)).toBeNull();
  });
});

describe("Step1MaterialIntake — comunicação de processamento parcial (Correção A)", () => {
  it("PDF integralmente processado mantém a mensagem normal de sucesso", async () => {
    mockUploadResponse({
      status: "success",
      message: "Arquivo 'prova_completa.pdf' extraído e sanitizado com sucesso.",
      raw_text: TEXTO_VALIDO_SANITIZADO,
      metadata: {
        source_type: "pdf",
        char_count: TEXTO_VALIDO_SANITIZADO.length,
        word_count: 19,
        sanitized: false,
        pii_removed_count: 0,
        filename: "prova_completa.pdf",
      },
    });

    const { container } = renderStep1();
    selecionarPdf(container, "prova_completa.pdf");

    const banner = await screen.findByTestId("step1-feedback-banner");
    expect(banner.getAttribute("data-banner-type")).toBe("success");
    expect(banner.textContent).toContain("Confira o texto abaixo antes de prosseguir.");
    expect(screen.queryByText("Processamento parcial")).toBeNull();

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(textarea.value).toBe(TEXTO_VALIDO_SANITIZADO);
  });

  it("PDF parcialmente processado (falha na página 2) exibe aviso de atenção com response.message e visual_analysis.notes sem duplicação", async () => {
    const notaPagina2 =
      "Página 2: nenhum texto legível foi reconhecido pelo OCR nesta página digitalizada.";
    const mensagemBackend =
      "Arquivo 'prova_mista.pdf' processado parcialmente com avisos nas páginas 2. Confira as observações de análise visual antes de avançar.";

    mockUploadResponse({
      status: "success",
      message: mensagemBackend,
      raw_text: TEXTO_VALIDO_SANITIZADO,
      metadata: {
        source_type: "mixed_pdf",
        char_count: TEXTO_VALIDO_SANITIZADO.length,
        word_count: 19,
        sanitized: false,
        pii_removed_count: 0,
        filename: "prova_mista.pdf",
      },
      raw_content: {
        text: TEXTO_VALIDO_SANITIZADO,
        source_type: "mixed_pdf",
        pii_sanitized: true,
        metadata: {
          filename: "prova_mista.pdf",
          total_pages: 2,
          partial_extraction: true,
          failed_pages: [],
          unreadable_pages: [2],
          ocr_unavailable_pages: [],
        },
      },
      visual_analysis: {
        overall_clutter_level: "baixa",
        has_high_clutter: false,
        total_pages_analyzed: 2,
        flagged_pages: [],
        pages: [],
        notes: `${notaPagina2}; ${notaPagina2}`,
      },
    });

    const { container } = renderStep1();
    selecionarPdf(container, "prova_mista.pdf");

    const banner = await screen.findByTestId("step1-feedback-banner");
    expect(banner.getAttribute("data-banner-type")).toBe("warning");
    expect(banner.getAttribute("data-banner-type")).not.toBe("success");
    expect(banner.getAttribute("data-banner-type")).not.toBe("error");
    expect(banner.textContent).toContain("Processamento parcial");
    expect(banner.textContent).toContain(mensagemBackend);
    expect(banner.textContent).toContain(notaPagina2);

    // Garante ausência de duplicação da mensagem e da nota no DOM inteiro
    expect(screen.getAllByText(mensagemBackend)).toHaveLength(1);
    expect(screen.getAllByText(notaPagina2)).toHaveLength(1);

    // Documento foi aceito (não rejeitado como erro) e o texto segue editável para conferência docente
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(textarea.value).toBe(TEXTO_VALIDO_SANITIZADO);
    fireEvent.change(textarea, { target: { value: `${TEXTO_VALIDO_SANITIZADO} Revisado.` } });
    expect(textarea.value).toContain("Revisado.");

    expect(await violacoes(banner)).toEqual([]);
  });

  it("tolera campos opcionais nulos/ausentes e não reintroduz dados pessoais sanitizados", async () => {
    const textoSanitizado =
      "Aluno: [NOME_REMOVIDO], CPF: [CPF_REMOVIDO]. Questão 1: Descreva o processo de fotossíntese nas plantas.";

    mockUploadResponse({
      status: "success",
      message:
        "Arquivo 'avaliacao.pdf' processado parcialmente com avisos nas páginas 2. Confira as observações de análise visual antes de avançar.",
      raw_text: textoSanitizado,
      metadata: {
        source_type: "scanned_pdf",
        char_count: textoSanitizado.length,
        word_count: 15,
        sanitized: true,
        pii_removed_count: 2,
        filename: "avaliacao.pdf",
      },
      raw_content: null,
      visual_analysis: null,
    });

    const { container } = renderStep1();
    selecionarPdf(container, "avaliacao.pdf");

    const banner = await screen.findByTestId("step1-feedback-banner");
    expect(banner.getAttribute("data-banner-type")).toBe("warning");
    expect(banner.textContent).toContain("páginas 2");
    expect(banner.textContent).not.toContain("[CPF_REMOVIDO]");
    expect(banner.textContent).not.toContain("fotossíntese");

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(textarea.value).toBe(textoSanitizado);
    expect(container.textContent).not.toMatch(/\d{3}\.\d{3}\.\d{3}-\d{2}/);
  });
});
