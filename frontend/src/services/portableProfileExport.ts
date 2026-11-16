/**
 * Exportação do perfil em .pdf (História 3.2.1 — Issue #30, RF-15, RNF-01).
 *
 * O PDF é montado pelo servidor, que recebe o perfil, valida, devolve o arquivo e não guarda nada
 * (resposta com `Cache-Control: no-store`). Esta é a ÚNICA chamada de rede do perfil: o .json é gerado
 * localmente em `portableProfile.ts`, que continua sem rede nem armazenamento.
 */
import {
  baixarBlob,
  PerfilPortatilError,
  type PerfilPedagogicoPortatil,
  perfilParaJson,
} from "./portableProfile";

const API_BASE_URL =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
    ? process.env.NEXT_PUBLIC_API_BASE_URL
    : "http://127.0.0.1:8000";

export const ROTA_EXPORTAR_PERFIL = "/api/v1/perfil/exportar";

export function nomePdfPerfil(perfil: PerfilPedagogicoPortatil): string {
  return `perfil-${perfil.codigo_anonimo}.pdf`;
}

/** Pede o PDF ao servidor e o entrega como download. Nada é guardado no navegador. */
export async function baixarPerfilPdf(perfil: PerfilPedagogicoPortatil): Promise<void> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_BASE_URL}${ROTA_EXPORTAR_PERFIL}?formato=pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: perfilParaJson(perfil),
      cache: "no-store",
    });
  } catch {
    throw new PerfilPortatilError(
      "Não foi possível falar com o servidor para gerar o PDF. O arquivo .json continua disponível offline.",
      "PDF_SERVER_UNAVAILABLE"
    );
  }

  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    const detalhe = corpo?.detail;
    const mensagem =
      typeof detalhe === "object" && detalhe?.detail
        ? String(detalhe.detail)
        : "O servidor recusou o perfil e não gerou o PDF.";
    throw new PerfilPortatilError(mensagem, detalhe?.code ?? "PDF_EXPORT_REJECTED");
  }

  baixarBlob(await resposta.blob(), nomePdfPerfil(perfil));
}
