/**
 * Exportação do material adaptado em PDF econômico ou DOCX editável (História 2.2.3 — Issue #23, RF-14).
 *
 * O servidor recebe o texto já aprovado pelo professor, monta o arquivo e não guarda nada
 * (`Cache-Control: no-store`). Aqui não há localStorage, sessionStorage nem cookie.
 */
export type FormatoMaterial = "pdf" | "docx";

export interface MaterialParaExportar {
  titulo?: string;
  texto: string;
}

export interface AvisosExportacao {
  titulo: string;
  possiveis_dados_pessoais: number;
  categorias_clinicas_no_texto: string[];
  pode_exportar: boolean;
}

export class ExportacaoMaterialError extends Error {
  constructor(message: string, public readonly code: string) {
    super(message);
    this.name = "ExportacaoMaterialError";
  }
}

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const ROTA_EXPORTAR_MATERIAL = "/api/v1/adaptacao/exportar";
export const ROTA_VERIFICAR_EXPORTACAO = "/api/v1/adaptacao/verificar-exportacao";

export function nomeArquivoMaterial(formato: FormatoMaterial): string {
  return `atividade-adaptada.${formato}`;
}

async function chamar(rota: string, material: MaterialParaExportar): Promise<Response> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_BASE_URL}${rota}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo: material.titulo, texto: material.texto }),
      cache: "no-store",
    });
  } catch {
    throw new ExportacaoMaterialError(
      "Não foi possível falar com o servidor para gerar o documento. Tente novamente em instantes.",
      "EXPORT_SERVER_UNAVAILABLE"
    );
  }
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    const detalhe = corpo?.detail;
    const mensagem =
      typeof detalhe === "object" && detalhe?.detail
        ? String(detalhe.detail)
        : "O servidor recusou o material e não gerou o documento.";
    throw new ExportacaoMaterialError(mensagem, detalhe?.code ?? "EXPORT_REJECTED");
  }
  return resposta;
}

/** Pergunta ao servidor se há aviso (dado pessoal ou termo clínico no texto) antes de exportar. */
export async function verificarExportacao(material: MaterialParaExportar): Promise<AvisosExportacao> {
  const resposta = await chamar(`${ROTA_VERIFICAR_EXPORTACAO}`, material);
  return (await resposta.json()) as AvisosExportacao;
}

export function temAvisos(a: AvisosExportacao): boolean {
  return a.possiveis_dados_pessoais > 0 || a.categorias_clinicas_no_texto.length > 0;
}

/** Pede o arquivo ao servidor e o entrega como download. Nada é guardado no navegador. */
export async function baixarMaterial(material: MaterialParaExportar, formato: FormatoMaterial): Promise<void> {
  const resposta = await chamar(`${ROTA_EXPORTAR_MATERIAL}?formato=${formato}`, material);
  const blob = await resposta.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivoMaterial(formato);
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
