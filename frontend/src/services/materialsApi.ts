/**
 * Cliente HTTP de integração entre o Frontend Next.js e o Backend FastAPI (`backend/src/iris/api/routes/materials.py`).
 *
 * Endpoints consumidos (História 1.1.1 — Issue #4):
 * - POST /api/v1/materials/text
 * - POST /api/v1/materials/upload
 * - POST /api/v1/materials/ocr (História 1.1.3: foto ou digitalização de prova)
 */

export type MaterialSourceType = "text" | "txt" | "pdf" | "docx" | "image";

export interface MaterialMetadata {
  source_type: MaterialSourceType;
  char_count: number;
  word_count: number;
  sanitized: boolean;
  pii_removed_count: number;
  filename?: string | null;
  estimated_tokens?: number;
}

export interface MaterialResponse {
  status: string;
  message: string;
  raw_text: string;
  metadata: MaterialMetadata;
}

export interface ApiErrorDetail {
  detail: string;
  code: string;
  field?: string;
}

export class IrisApiError extends Error {
  public readonly code: string;
  public readonly field?: string;
  public readonly statusCode: number;

  constructor(message: string, code = "UNKNOWN_ERROR", statusCode = 400, field?: string) {
    super(message);
    this.name = "IrisApiError";
    this.code = code;
    this.statusCode = statusCode;
    this.field = field;
  }
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"] as const;
export const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg"] as const;
export const ACCEPTED_EXTENSIONS = [...ALLOWED_EXTENSIONS, ...IMAGE_EXTENSIONS] as const;
/** Atributo `accept` do seletor de arquivos: documentos e imagens de prova. */
export const FILE_INPUT_ACCEPT =
  ".pdf,.docx,.txt,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/png,image/jpeg";
export const MIN_MATERIAL_CHARS = 50;
export const MAX_SAFE_CONTEXT_CHARS = 100_000;
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

/**
 * Conta caracteres e palavras em tempo real no cliente (sem impor limite máximo fixo de palavras na UI).
 */
export function computeTextMetrics(text: string): {
  charCount: number;
  wordCount: number;
  estimatedTokens: number;
  meetsMinimum: boolean;
  exceedsSafeContext: boolean;
} {
  const cleaned = text.trim();
  const charCount = cleaned.length;
  const wordCount = cleaned.length === 0 ? 0 : cleaned.split(/\s+/).filter(Boolean).length;
  const estimatedTokens = charCount === 0 ? 0 : Math.max(1, Math.round(charCount / 4));

  return {
    charCount,
    wordCount,
    estimatedTokens,
    meetsMinimum: charCount >= MIN_MATERIAL_CHARS,
    exceedsSafeContext: charCount > MAX_SAFE_CONTEXT_CHARS,
  };
}

/** Extensão do arquivo em minúsculas, com o ponto ("" se não houver). */
export function fileExtension(name: string): string {
  const dotIndex = (name || "").lastIndexOf(".");
  return dotIndex >= 0 ? name.slice(dotIndex).toLowerCase() : "";
}

/** True para foto ou digitalização de prova (.png, .jpg, .jpeg), que segue pelo OCR em vez da extração de documento. */
export function isImageFile(file: File): boolean {
  return (IMAGE_EXTENSIONS as readonly string[]).includes(fileExtension(file.name));
}

/**
 * Valida se o arquivo selecionado tem extensão suportada (.pdf, .docx, .txt, .png, .jpg).
 */
export function validateClientFileFormat(file: File): {
  valid: boolean;
  extension: string;
  errorMessage?: string;
  errorCode?: string;
} {
  const name = file.name || "";
  const dotIndex = name.lastIndexOf(".");
  const extension = dotIndex >= 0 ? name.slice(dotIndex).toLowerCase() : "";

  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extension)) {
    return {
      valid: false,
      extension: extension || "(sem extensão)",
      errorCode: "UNSUPPORTED_FORMAT",
      errorMessage: `Formato de arquivo '${extension || "desconhecido"}' não suportado. Os formatos aceitos pela plataforma são: .docx, .pdf, .txt, .png, .jpg.`,
    };
  }

  if (file.size === 0) {
    return {
      valid: false,
      extension,
      errorCode: "EMPTY_FILE",
      errorMessage: `O arquivo '${file.name}' está vazio (0 bytes). Selecione um documento com conteúdo textual válido.`,
    };
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
    return {
      valid: false,
      extension,
      errorCode: "FILE_TOO_LARGE",
      errorMessage: `O arquivo enviado (${sizeMb} MB) excede o limite técnico seguro de processamento em memória (10 MB).`,
    };
  }

  return { valid: true, extension };
}

/**
 * Extrai a mensagem de erro estruturada retornada pelo FastAPI (`HTTPException(detail={"detail", "code", "field"})`).
 */
async function parseErrorResponse(res: Response): Promise<IrisApiError> {
  try {
    const body = await res.json();
    const detailObj = body?.detail;
    if (typeof detailObj === "object" && detailObj !== null) {
      return new IrisApiError(
        detailObj.detail || "Não foi possível processar o material enviado.",
        detailObj.code || "VALIDATION_ERROR",
        res.status,
        detailObj.field
      );
    }
    if (typeof detailObj === "string") {
      return new IrisApiError(detailObj, "API_ERROR", res.status);
    }
  } catch {
    // Fallback se a resposta não for JSON
  }
  return new IrisApiError(
    `Erro de comunicação com o servidor (HTTP ${res.status}). Verifique se o backend FastAPI está em execução.`,
    "HTTP_ERROR",
    res.status
  );
}

/**
 * Envia um arquivo (.pdf, .docx, .txt) via multipart/form-data para `POST /api/v1/materials/upload`.
 */
export async function uploadMaterialFile(file: File): Promise<MaterialResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/v1/materials/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as MaterialResponse;
}

export type NivelPoluicaoVisual = "baixa" | "media" | "alta";

/** Indicador de densidade visual da imagem (heurística; o backend a calibra, a tela só mostra). */
export interface AnaliseVisual {
  nivel: NivelPoluicaoVisual;
  indicador_poluicao: boolean;
  escore: number;
  densidade_bordas: number;
  proporcao_colorida: number;
  cobertura_blocos: number;
  contraste: number;
  motivos: string[];
  mensagem: string | null;
}

export interface OcrAviso {
  code: string;
  detail: string;
}

export interface OcrInfo {
  confianca_media: number;
  palavras_reconhecidas: number;
  avisos: OcrAviso[];
}

/** Resposta do OCR: o mesmo envelope do upload de documentos, mais a confiança da leitura e a análise visual. */
export interface OcrMaterialResponse extends MaterialResponse {
  ocr: OcrInfo;
  analise_visual: AnaliseVisual;
  imagem: { formato: string; largura: number; altura: number };
}

/**
 * Envia a foto ou digitalização de uma prova (.png, .jpg) para `POST /api/v1/materials/ocr`.
 * O backend lê o texto em memória (sem guardar a imagem) e mede a poluição visual.
 */
export async function uploadMaterialImage(file: File): Promise<OcrMaterialResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/v1/materials/ocr`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as OcrMaterialResponse;
}

/**
 * Envia texto colado/digitado diretamente para `POST /api/v1/materials/text`
 * para sanitização preventiva de PII e validação no backend.
 */
export async function submitMaterialText(text: string): Promise<MaterialResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/materials/text`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as MaterialResponse;
}
