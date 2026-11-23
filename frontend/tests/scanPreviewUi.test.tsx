// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ScanPreview } from "../src/components/ScanPreview";
import type { OcrMaterialResponse } from "../src/services/materialsApi";

afterEach(cleanup);

const BASE: OcrMaterialResponse = {
  status: "success",
  message: "ok",
  raw_text: "texto",
  metadata: { source_type: "image", char_count: 5, word_count: 1, sanitized: false, pii_removed_count: 0, filename: null },
  ocr: { confianca_media: 91, palavras_reconhecidas: 16, avisos: [] },
  analise_visual: {
    nivel: "baixa",
    indicador_poluicao: false,
    escore: 0.1,
    densidade_bordas: 0.152,
    proporcao_colorida: 0,
    cobertura_blocos: 0.86,
    contraste: 0.9,
    motivos: [],
    mensagem: null,
  },
  imagem: { formato: "png", largura: 1240, altura: 1754 },
};

const POLUIDA: OcrMaterialResponse = {
  ...BASE,
  ocr: { ...BASE.ocr, confianca_media: 62, avisos: [{ code: "LOW_CONFIDENCE", detail: "Algumas palavras podem ter sido lidas errado. Confira o texto com a prova na mão." }] },
  analise_visual: {
    ...BASE.analise_visual,
    nivel: "alta",
    indicador_poluicao: true,
    escore: 0.8,
    densidade_bordas: 0.2,
    proporcao_colorida: 0.3,
    motivos: ["áreas coloridas extensas"],
    mensagem: "Esta prova tem muitos elementos visuais concorrentes (áreas coloridas extensas). Confira o layout ao revisar a adaptação.",
  },
};

const tela = (r: OcrMaterialResponse) => (
  <main>
    <h1>Etapa 1</h1>
    <ScanPreview previewUrl="blob:http://localhost/abc" fileName="prova.png" resultado={r} />
  </main>
);

async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

describe("ScanPreview (História 1.1.3)", () => {
  it("mostra a imagem com texto alternativo e as dimensões", () => {
    render(tela(BASE));
    expect(screen.getByRole("img", { name: /Pré-visualização da prova digitalizada prova\.png/ })).toBeTruthy();
    expect(screen.getByText(/1240×1754 px/)).toBeTruthy();
  });

  it("baixa densidade: indicador tranquilo, em texto e sem aviso de alerta", () => {
    render(tela(BASE));
    const indicador = screen.getByTestId("indicador-densidade-visual");
    expect(indicador.getAttribute("data-nivel")).toBe("baixa");
    expect(within(indicador).getByText("Baixa densidade visual")).toBeTruthy();
    expect(within(indicador).getByText(/Não há excesso de elementos visuais/)).toBeTruthy();
  });

  it("alta densidade: emite o indicador com a mensagem do backend e o aviso de confiança baixa", () => {
    render(tela(POLUIDA));
    const indicador = screen.getByTestId("indicador-densidade-visual");
    expect(indicador.getAttribute("data-nivel")).toBe("alta");
    expect(within(indicador).getByText("Alta densidade visual")).toBeTruthy();
    expect(within(indicador).getByText(/muitos elementos visuais concorrentes/)).toBeTruthy();
    expect(screen.getByText(/Confira o texto com a prova na mão/)).toBeTruthy();
  });

  it("explica que a medida é uma estimativa e não um laudo", () => {
    render(tela(POLUIDA));
    expect(screen.getByText("Como medimos")).toBeTruthy();
    expect(screen.getByText(/não um laudo/)).toBeTruthy();
  });

  it("não tem violações de acessibilidade (axe), nos dois estados", async () => {
    for (const r of [BASE, POLUIDA]) {
      const { container, unmount } = render(tela(r));
      expect(await violacoes(container)).toEqual([]);
      unmount();
    }
  });
});
