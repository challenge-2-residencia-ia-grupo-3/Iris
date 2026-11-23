import { afterEach, describe, expect, it, vi } from "vitest";
import {
  FILE_INPUT_ACCEPT,
  IrisApiError,
  fileExtension,
  isImageFile,
  uploadMaterialImage,
  validateClientFileFormat,
  type OcrMaterialResponse,
} from "../src/services/materialsApi";

afterEach(() => vi.unstubAllGlobals());

const arquivo = (nome: string, tamanho = 2000, tipo = "image/png") => new File([new Uint8Array(tamanho)], nome, { type: tipo });

const RESPOSTA: OcrMaterialResponse = {
  status: "success",
  message: "ok",
  raw_text: "1. Um instituto de pesquisa constatou que o crescimento foi de 135,25 por cento. Qual é a taxa?",
  metadata: { source_type: "image", char_count: 90, word_count: 16, sanitized: false, pii_removed_count: 0, filename: null },
  ocr: { confianca_media: 91, palavras_reconhecidas: 16, avisos: [] },
  analise_visual: {
    nivel: "baixa",
    indicador_poluicao: false,
    escore: 0.1,
    densidade_bordas: 0.15,
    proporcao_colorida: 0,
    cobertura_blocos: 0.86,
    contraste: 0.9,
    motivos: [],
    mensagem: null,
  },
  imagem: { formato: "png", largura: 1240, altura: 1754 },
};

describe("entrada de imagem de prova (História 1.1.3)", () => {
  it("reconhece imagens pela extensão, sem diferenciar maiúsculas", () => {
    expect(fileExtension("Prova.JPG")).toBe(".jpg");
    expect(fileExtension("sem-extensao")).toBe("");
    for (const nome of ["a.png", "a.jpg", "a.jpeg", "A.PNG"]) expect(isImageFile(arquivo(nome))).toBe(true);
    for (const nome of ["a.pdf", "a.docx", "a.txt", "a.gif"]) expect(isImageFile(arquivo(nome))).toBe(false);
  });

  it("aceita .png, .jpg e .jpeg na validação do cliente e continua aceitando os documentos", () => {
    for (const nome of ["prova.png", "prova.jpg", "prova.jpeg", "prova.pdf", "prova.docx", "prova.txt"]) {
      expect(validateClientFileFormat(arquivo(nome)).valid, nome).toBe(true);
    }
  });

  it("recusa outros formatos de imagem e diz quais são aceitos", () => {
    const r = validateClientFileFormat(arquivo("prova.gif", 2000, "image/gif"));
    expect(r.valid).toBe(false);
    expect(r.errorCode).toBe("UNSUPPORTED_FORMAT");
    expect(r.errorMessage).toContain(".png, .jpg");
  });

  it("recusa imagem vazia ou acima de 10 MB antes de enviar", () => {
    expect(validateClientFileFormat(arquivo("a.png", 0)).errorCode).toBe("EMPTY_FILE");
    expect(validateClientFileFormat(arquivo("a.png", 10 * 1024 * 1024 + 1)).errorCode).toBe("FILE_TOO_LARGE");
  });

  it("o seletor de arquivos aceita imagens e documentos", () => {
    for (const parte of [".png", ".jpg", ".jpeg", "image/png", "image/jpeg", ".pdf", ".docx", ".txt"]) {
      expect(FILE_INPUT_ACCEPT).toContain(parte);
    }
  });

  it("envia a imagem em multipart para /api/v1/materials/ocr", async () => {
    const fetchFalso = vi.fn().mockResolvedValue({ ok: true, json: async () => RESPOSTA });
    vi.stubGlobal("fetch", fetchFalso);
    const r = await uploadMaterialImage(arquivo("prova.png"));
    expect(r.metadata.source_type).toBe("image");
    const [url, init] = fetchFalso.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/materials\/ocr$/);
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("repassa o motivo da recusa do backend (imagem desfocada, resolução baixa)", async () => {
    const corpo = { detail: { status: "error", code: "IMAGE_TOO_BLURRY", field: "file", detail: "A imagem está desfocada ou tremida." } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => corpo }));
    await expect(uploadMaterialImage(arquivo("prova.png"))).rejects.toMatchObject({
      name: "IrisApiError",
      code: "IMAGE_TOO_BLURRY",
      statusCode: 422,
      message: "A imagem está desfocada ou tremida.",
    });
    await expect(uploadMaterialImage(arquivo("prova.png"))).rejects.toBeInstanceOf(IrisApiError);
  });
});
