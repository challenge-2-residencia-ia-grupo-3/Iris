// @vitest-environment jsdom
import React from "react";
import axe from "axe-core";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceObservation } from "../src/components/VoiceObservation";
import type { ResultadoVoz } from "../src/services/voiceObservation";

const RESULTADO: ResultadoVoz = {
  status: "ok",
  transcricao: "Em textos longos ele pula direto para as alternativas e fica parado olhando para a folha em branco.",
  pii_substituicoes: 1,
  avisos: [{ code: "CLINICAL_TERMS_IGNORED", categorias: ["diagnostico"], detail: "A fala cita termos clínicos. Eles foram ignorados." }],
  id_catalogo: "tdah",
  sugestoes: [
    { id_caracteristica: "atencao_sustentada_textos_longos", nome: "Leitura de textos longos e densos", pontuacao: 6, confianca: "alta", evidencias: ["textos longos", "pula direto para as alternativas"] },
    { id_caracteristica: "bloqueio_iniciacao_tarefas_abertas", nome: "Dificuldade para iniciar questões abertas", pontuacao: 2, confianca: "media", evidencias: ["folha em branco"] },
  ],
};
const VAZIO: ResultadoVoz = { ...RESULTADO, avisos: [], pii_substituicoes: 0, sugestoes: [] };

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function respostaOk(corpo: ResultadoVoz) {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => corpo });
}

function arquivo(nome = "obs.wav", tipo = "audio/wav") {
  return new File([new Uint8Array(2000)], nome, { type: tipo });
}

async function enviarArquivo(f = arquivo()) {
  const input = document.querySelector("input[type=file]") as HTMLInputElement;
  await act(async () => {
    fireEvent.change(input, { target: { files: [f] } });
  });
}

async function violacoes(container: HTMLElement) {
  const r = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
}

// ---- gravador de mentira ---------------------------------------------------------------------------
class GravadorFalso {
  static ultimo: GravadorFalso | null = null;
  static suporta = (_m: string) => true;
  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(public stream: unknown, opts: { mimeType: string }) {
    this.mimeType = opts.mimeType;
    GravadorFalso.ultimo = this;
  }
  static isTypeSupported(m: string) { return GravadorFalso.suporta(m); }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array(500)], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function instalarMicrofone(permitir = true) {
  const faixa = { stop: vi.fn() };
  const getUserMedia = permitir ? vi.fn().mockResolvedValue({ getTracks: () => [faixa] }) : vi.fn().mockRejectedValue(new DOMException("negado", "NotAllowedError"));
  vi.stubGlobal("MediaRecorder", GravadorFalso);
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  return { faixa, getUserMedia };
}

beforeEach(() => {
  GravadorFalso.suporta = () => true;
  GravadorFalso.ultimo = null;
});

describe("envio de arquivo, sugestões e confirmação (HITL)", () => {
  it("pré-marca as sugestões, deixa desmarcar e só aplica o que o professor confirmou", async () => {
    vi.stubGlobal("fetch", respostaOk(RESULTADO));
    const onConfirm = vi.fn();
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={onConfirm} />);
    await enviarArquivo();

    const caixas = (await screen.findAllByRole("checkbox")) as HTMLInputElement[];
    expect(caixas).toHaveLength(2);
    expect(caixas.every((c) => c.checked)).toBe(true); // pré-selecionadas
    expect(screen.getByText(/Você disse: “textos longos”, “pula direto para as alternativas”/)).toBeTruthy();
    expect(onConfirm).not.toHaveBeenCalled(); // nada é aplicado sem confirmação

    fireEvent.click(screen.getByRole("checkbox", { name: /Dificuldade para iniciar questões abertas/ })); // desmarca uma
    fireEvent.click(screen.getByRole("button", { name: /Confirmar 1 sugestão/ }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith(["atencao_sustentada_textos_longos"]);
  });

  it("não permite confirmar com tudo desmarcado", async () => {
    vi.stubGlobal("fetch", respostaOk(RESULTADO));
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await enviarArquivo();
    for (const c of await screen.findAllByRole("checkbox")) fireEvent.click(c);
    expect((screen.getByRole("button", { name: /Confirmar sugestões/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("descartar não aplica nada e volta ao início", async () => {
    vi.stubGlobal("fetch", respostaOk(RESULTADO));
    const onConfirm = vi.fn();
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={onConfirm} />);
    await enviarArquivo();
    fireEvent.click(await screen.findByRole("button", { name: /Descartar/ }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("mostra aviso clínico, troca de dados pessoais e a marca de 'já selecionada'", async () => {
    vi.stubGlobal("fetch", respostaOk(RESULTADO));
    render(<VoiceObservation jaSelecionadas={["atencao_sustentada_textos_longos"]} onConfirm={vi.fn()} />);
    await enviarArquivo();
    expect((await screen.findByRole("note")).textContent).toMatch(/termos clínicos/);
    expect(screen.getByText(/1 dado\(s\) pessoal\(is\) foram trocados/)).toBeTruthy();
    expect(screen.getByText(/já está selecionada/)).toBeTruthy();
  });

  it("sem sugestão explica o que fazer e não mostra botão de confirmar", async () => {
    vi.stubGlobal("fetch", respostaOk(VAZIO));
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await enviarArquivo();
    expect(await screen.findByText(/Não identifiquei nenhuma característica/)).toBeTruthy();
  });

  it("o professor corrige a transcrição e atualiza as sugestões pelo texto", async () => {
    const f = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VAZIO })
      .mockResolvedValueOnce({ ok: true, json: async () => RESULTADO });
    vi.stubGlobal("fetch", f);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await enviarArquivo();
    const caixa = await screen.findByLabelText(/Transcrição/);
    fireEvent.change(caixa, { target: { value: "Em textos longos ele pula direto para as alternativas." } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Atualizar sugestões/ }));
    });
    expect(JSON.parse(f.mock.calls[1][1].body).texto).toBe("Em textos longos ele pula direto para as alternativas.");
    expect(await screen.findAllByRole("checkbox")).toHaveLength(2);
  });

  it.each([
    [{ ok: false, status: 422, json: async () => ({ detail: { code: "AUDIO_TOO_LONG", detail: "O áudio tem 75 segundos. O limite é de 60 segundos." } }) }, /75 segundos/],
    [{ ok: false, status: 503, json: async () => ({ detail: { code: "STT_UNAVAILABLE", detail: "A transcrição por voz não está instalada." } }) }, /manualmente/],
  ])("erro do servidor %# aparece como alerta e deixa tentar de novo", async (resp, msg) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resp));
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await enviarArquivo();
    expect((await screen.findByRole("alert")).textContent).toMatch(msg);
    expect(document.querySelector("input[type=file]")).toBeTruthy();
  });

  it("recusa no navegador um arquivo que não é áudio, sem chamar o servidor", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await enviarArquivo(new File(["x"], "relato.pdf", { type: "application/pdf" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/WAV, WebM/);
    expect(f).not.toHaveBeenCalled();
  });
});

describe("gravação no navegador", () => {
  it("grava, mostra o cronômetro, envia o áudio e libera o microfone", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { faixa } = instalarMicrofone();
    const f = respostaOk(RESULTADO);
    vi.stubGlobal("fetch", f);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);

    await act(async () => { fireEvent.click(await screen.findByRole("button", { name: /Gravar observação/ })); });
    const timer = await screen.findByRole("timer");
    expect(timer.textContent).toMatch(/00:00/);
    await act(async () => { vi.advanceTimersByTime(3000); });
    expect(timer.textContent).toMatch(/00:03/);

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Parar e transcrever/ })); });
    expect(faixa.stop).toHaveBeenCalled(); // microfone solto
    await waitFor(() => expect(f).toHaveBeenCalledTimes(1));
    const arq = (f.mock.calls[0][1].body as FormData).get("file") as File;
    expect(arq.name).toBe("observacao.webm");
    expect(await screen.findAllByRole("checkbox")).toHaveLength(2);
  });

  it("para sozinha aos 60 segundos", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    instalarMicrofone();
    const f = respostaOk(RESULTADO);
    vi.stubGlobal("fetch", f);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await act(async () => { fireEvent.click(await screen.findByRole("button", { name: /Gravar observação/ })); });
    await act(async () => { vi.advanceTimersByTime(59_000); });
    expect(f).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(1_500); });
    await waitFor(() => expect(f).toHaveBeenCalledTimes(1));
    expect(GravadorFalso.ultimo!.state).toBe("inactive");
  });

  it("cancelar descarta o áudio sem enviar nada", async () => {
    instalarMicrofone();
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await act(async () => { fireEvent.click(await screen.findByRole("button", { name: /Gravar observação/ })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Cancelar/ })); });
    expect(f).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /Gravar observação/ })).toBeTruthy();
  });

  it("microfone negado: explica e continua oferecendo o envio de arquivo", async () => {
    instalarMicrofone(false);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await act(async () => { fireEvent.click(await screen.findByRole("button", { name: /Gravar observação/ })); });
    expect((await screen.findByRole("alert")).textContent).toMatch(/microfone/);
    expect(screen.getByText(/Enviar áudio gravado/)).toBeTruthy();
  });

  it("navegador sem gravador: só mostra o envio de arquivo", async () => {
    vi.stubGlobal("MediaRecorder", undefined);
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Gravar observação/ })).toBeNull();
    expect(screen.getByText(/não grava áudio/)).toBeTruthy();
    expect(screen.getByText(/Enviar áudio gravado/)).toBeTruthy();
  });

  it("sair da tela no meio da gravação solta o microfone", async () => {
    const { faixa } = instalarMicrofone();
    const { unmount } = render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await act(async () => { fireEvent.click(await screen.findByRole("button", { name: /Gravar observação/ })); });
    unmount();
    expect(faixa.stop).toHaveBeenCalled();
  });
});

describe("acessibilidade (WCAG 2.1 AA)", () => {
  it("sem violações no estado inicial", async () => {
    instalarMicrofone();
    const { container } = render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await screen.findByRole("button", { name: /Gravar observação/ });
    expect(await violacoes(container)).toEqual([]);
  });

  it("sem violações gravando, com erro e com resultado", async () => {
    instalarMicrofone();
    vi.stubGlobal("fetch", respostaOk(RESULTADO));
    const { container } = render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await act(async () => { fireEvent.click(await screen.findByRole("button", { name: /Gravar observação/ })); });
    expect(await violacoes(container)).toEqual([]);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Parar e transcrever/ })); });
    await screen.findAllByRole("checkbox");
    expect(await violacoes(container)).toEqual([]);
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: { code: "X", detail: "Falhou." } }) }));
    const outro = render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    await enviarArquivo();
    await screen.findByRole("alert");
    expect(await violacoes(outro.container)).toEqual([]);
  });

  it("controles têm nome acessível, alvo de 44 px e o foco vai para o resultado", async () => {
    instalarMicrofone();
    vi.stubGlobal("fetch", respostaOk(RESULTADO));
    render(<VoiceObservation jaSelecionadas={[]} onConfirm={vi.fn()} />);
    for (const b of screen.getAllByRole("button")) expect(b.className).toContain("min-h-[44px]");
    await enviarArquivo();
    const titulo = await screen.findByRole("heading", { name: /O que a Íris entendeu/ });
    await waitFor(() => expect(document.activeElement).toBe(titulo));
    const lista = screen.getByRole("group", { name: /Características sugeridas/ });
    for (const c of within(lista).getAllByRole("checkbox")) expect(c.getAttribute("id") && document.querySelector(`label[for='${c.id}']`)).toBeTruthy();
  });
});
