import { afterEach, describe, expect, it, vi } from "vitest";
import {
  escolherMimeType,
  extensaoDoMime,
  formatarTempo,
  MAX_BYTES,
  mesclarSelecao,
  ROTA_SUGERIR,
  ROTA_TRANSCREVER,
  sugerirDeTexto,
  transcreverAudio,
  validarArquivoLocal,
  VoiceError,
} from "../src/services/voiceObservation";

afterEach(() => vi.unstubAllGlobals());

describe("escolherMimeType", () => {
  it("prefere WebM/Opus e cai para Ogg e MP4 conforme o navegador", () => {
    expect(escolherMimeType(() => true)).toBe("audio/webm;codecs=opus");
    expect(escolherMimeType((m) => m === "audio/mp4")).toBe("audio/mp4"); // Safari
    expect(escolherMimeType((m) => m.startsWith("audio/ogg"))).toBe("audio/ogg;codecs=opus"); // Firefox antigo
  });
  it("devolve null quando nada serve e não quebra se isTypeSupported lançar", () => {
    expect(escolherMimeType(() => false)).toBeNull();
    expect(escolherMimeType(() => { throw new Error("x"); })).toBeNull();
  });
  it("extensão pelo tipo", () => {
    expect(extensaoDoMime("audio/webm;codecs=opus")).toBe("webm");
    expect(extensaoDoMime("audio/ogg")).toBe("ogg");
    expect(extensaoDoMime("audio/mp4")).toBe("m4a");
    expect(extensaoDoMime("audio/wav")).toBe("wav");
    expect(extensaoDoMime("")).toBe("audio");
  });
});

describe("validarArquivoLocal", () => {
  const ok = { name: "obs.wav", type: "audio/wav", size: 1000 };
  it("aceita áudio", () => expect(validarArquivoLocal(ok)).toBeNull());
  it("aceita pela extensão quando o navegador não informa o tipo", () => {
    expect(validarArquivoLocal({ name: "obs.M4A", type: "", size: 10 })).toBeNull();
  });
  it.each([
    [{ ...ok, size: 0 }, /vazio/],
    [{ ...ok, size: MAX_BYTES + 1 }, /passa de/],
    [{ name: "relato.pdf", type: "application/pdf", size: 10 }, /WAV, WebM/],
  ])("recusa %#", (arq, msg) => expect(validarArquivoLocal(arq)).toMatch(msg));
});

describe("mesclarSelecao e formatarTempo", () => {
  it("soma sem repetir e sem tirar o que já estava marcado", () => {
    expect(mesclarSelecao(["a", "b"], ["b", "c"])).toEqual(["a", "b", "c"]);
    expect(mesclarSelecao([], [])).toEqual([]);
  });
  it("ignora ids que não existem no catálogo", () => {
    expect(mesclarSelecao(["a"], ["x", "b"], new Set(["a", "b"]))).toEqual(["a", "b"]);
  });
  it("não altera os arrays recebidos", () => {
    const atual = ["a"];
    mesclarSelecao(atual, ["b"]);
    expect(atual).toEqual(["a"]);
  });
  it("formata o cronômetro", () => {
    expect(formatarTempo(0)).toBe("00:00");
    expect(formatarTempo(59.9)).toBe("00:59");
    expect(formatarTempo(60)).toBe("01:00");
    expect(formatarTempo(-3)).toBe("00:00");
  });
});

describe("chamadas ao backend", () => {
  const resposta = { status: "ok", transcricao: "x", pii_substituicoes: 0, avisos: [], id_catalogo: "c", sugestoes: [] };

  it("transcreverAudio envia multipart no campo 'file', sem cache", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => resposta });
    vi.stubGlobal("fetch", f);
    await transcreverAudio(new Blob(["abc"], { type: "audio/webm" }), "observacao.webm");
    const [url, init] = f.mock.calls[0];
    expect(String(url).endsWith(ROTA_TRANSCREVER)).toBe(true);
    expect(init.method).toBe("POST");
    expect(init.cache).toBe("no-store");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(Blob);
    expect(init.headers).toBeUndefined(); // o navegador define o boundary do multipart
  });

  it("sugerirDeTexto envia JSON", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => resposta });
    vi.stubGlobal("fetch", f);
    await sugerirDeTexto("textos longos");
    expect(String(f.mock.calls[0][0]).endsWith(ROTA_SUGERIR)).toBe(true);
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ texto: "textos longos" });
  });

  it("áudio acima de 60 s vira erro com a mensagem do servidor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 422, json: async () => ({ detail: { code: "AUDIO_TOO_LONG", detail: "O áudio tem 75 segundos. O limite é de 60 segundos." } }),
    }));
    const e = await transcreverAudio(new Blob(["x"]), "a.wav").catch((x) => x);
    expect(e).toBeInstanceOf(VoiceError);
    expect(e).toMatchObject({ code: "AUDIO_TOO_LONG", status: 422, message: "O áudio tem 75 segundos. O limite é de 60 segundos." });
  });

  it("motor de transcrição fora do ar (503) lembra que dá para selecionar à mão", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 503, json: async () => ({ detail: { code: "STT_UNAVAILABLE", detail: "A transcrição por voz não está instalada." } }),
    }));
    const e = await transcreverAudio(new Blob(["x"]), "a.wav").catch((x) => x);
    expect(e.message).toMatch(/selecionar as características manualmente/);
  });

  it("servidor fora do ar e resposta sem corpo viram erros claros", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("rede")));
    await expect(sugerirDeTexto("x")).rejects.toMatchObject({ code: "SERVER_UNAVAILABLE", status: 0 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error("sem json"); } }));
    await expect(sugerirDeTexto("x")).rejects.toMatchObject({ code: "REJECTED", status: 500 });
  });
});
