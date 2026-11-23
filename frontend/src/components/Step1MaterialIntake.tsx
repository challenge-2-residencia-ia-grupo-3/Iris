"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ClipboardPaste,
  FileCheck2,
  FileText,
  FileUp,
  Loader2,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";
import { IrisHeader, STEP_TITLES } from "./IrisHeader";
import { IrisSidebar } from "./IrisSidebar";
import {
  ALLOWED_EXTENSIONS,
  IrisApiError,
  MaterialMetadata,
  MIN_MATERIAL_CHARS,
  computeTextMetrics,
  submitMaterialText,
  uploadMaterialFile,
  validateClientFileFormat,
} from "@/services/materialsApi";
import {
  clearStep1StateFromSession,
  loadStep1StateFromSession,
  saveStep1StateToSession,
  Step1SelectedFileInfo,
} from "@/services/catalogsApi";

interface Step1MaterialIntakeProps {
  teacherEmail?: string;
  onBackToLogin?: () => void;
  onAdvanceToStep2?: (materialText: string, metadata?: MaterialMetadata | null) => void;
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
}

/**
 * Componente da Etapa 1 (Issue 1.1.1 — Entrada de Material Didático via Texto e Upload de Documentos).
 *
 * Atende estritamente:
 * - Área acessível para colagem direta de texto (`textarea`) com preservação UTF-8.
 * - Contador de caracteres e palavras em tempo real, SEM apresentar limite máximo fixo na interface.
 * - Validação do mínimo de 50 caracteres e aviso claro se ultrapassar a capacidade segura da janela de contexto da IA.
 * - Componente de upload drag-and-drop e seleção pelo dispositivo (1 arquivo por envio: `.pdf`, `.docx`, `.txt`).
 * - Feedback visual e acessível (WCAG 2.1 AA) de formatos aceitos e rejeitados.
 * - Exibição imediata do conteúdo extraído e sanitizado (Zero-Retention PII Scrubber) para conferência docente.
 */
export function Step1MaterialIntake({
  teacherEmail = "marina.alves@escola.edu.br",
  onBackToLogin,
  onAdvanceToStep2,
  darkMode,
  onToggleDarkMode,
}: Step1MaterialIntakeProps) {
  const router = useRouter();

  const textareaId = useId();
  const fileInputId = useId();
  const statusRegionId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [textContent, setTextContent] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  // Estado do arquivo enviado (apenas 1 arquivo por envio)
  const [selectedFile, setSelectedFile] = useState<Step1SelectedFileInfo | null>(null);

  // Resultado processado pelo Backend FastAPI (`POST /api/v1/materials/upload` ou `POST /api/v1/materials/text`)
  const [serverMetadata, setServerMetadata] = useState<MaterialMetadata | null>(null);
  const [feedbackBanner, setFeedbackBanner] = useState<{
    type: "success" | "error";
    title: string;
    message?: string;
    code?: string;
  } | null>(null);

  const [confirmedForStep2, setConfirmedForStep2] = useState<boolean>(false);
  const [showUploadZone, setShowUploadZone] = useState<boolean>(true);

  // Restaura o material e arquivo enviados anteriormente na sessão ao voltar de outras etapas
  useEffect(() => {
    const saved = loadStep1StateFromSession();
    if (saved && saved.textContent) {
      setTextContent(saved.textContent);
      setServerMetadata(saved.metadata);
      setSelectedFile(saved.selectedFile);
      setConfirmedForStep2(saved.confirmedForStep2);
      setShowUploadZone(saved.selectedFile?.status !== "accepted");
    }
  }, []);

  useEffect(() => {
    if (!feedbackBanner) return;
    const timer = window.setTimeout(() => {
      setFeedbackBanner(null);
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [feedbackBanner]);

  // Métricas em tempo real (sem limite máximo fixo de palavras na interface)
  const metrics = computeTextMetrics(textContent);

  /**
   * Processa o arquivo único via Backend FastAPI (`POST /api/v1/materials/upload`).
   */
  const handleSingleFileProcess = useCallback(async (file: File) => {
    setConfirmedForStep2(false);

    // 1. Validação instantânea no cliente (extensão, vazio, tamanho binário)
    const validation = validateClientFileFormat(file);
    if (!validation.valid) {
      const errorMsg =
        validation.errorMessage ||
        "Formato não suportado. Envie apenas um arquivo nos formatos .pdf, .docx ou .txt.";
      setSelectedFile({
        name: file.name,
        sizeBytes: file.size,
        extension: validation.extension,
        status: "rejected",
        errorMessage: errorMsg,
      });
      setServerMetadata(null);
      setShowUploadZone(true);
      setFeedbackBanner({
        type: "error",
        title: "Arquivo rejeitado na validação",
        message: errorMsg,
        code: validation.errorCode,
      });
      return;
    }

    setShowUploadZone(true);
    setSelectedFile({
      name: file.name,
      sizeBytes: file.size,
      extension: validation.extension,
      status: "uploading",
    });
    setIsProcessing(true);
    setFeedbackBanner(null);

    try {
      const response = await uploadMaterialFile(file);
      const acceptedFileInfo: Step1SelectedFileInfo = {
        name: file.name,
        sizeBytes: file.size,
        extension: validation.extension,
        status: "accepted",
      };
      setTextContent(response.raw_text);
      setServerMetadata(response.metadata);
      setSelectedFile(acceptedFileInfo);
      setShowUploadZone(false);

      saveStep1StateToSession({
        textContent: response.raw_text,
        metadata: response.metadata,
        selectedFile: acceptedFileInfo,
        confirmedForStep2: false,
      });

      setFeedbackBanner({
        type: "success",
        title: "Confira o texto abaixo antes de prosseguir.",
      });
    } catch (err) {
      const serverReason = err instanceof IrisApiError ? err.message : undefined;
      setSelectedFile({
        name: file.name,
        sizeBytes: file.size,
        extension: validation.extension,
        status: "rejected",
        errorMessage: serverReason,
      });
      setServerMetadata(null);
      setShowUploadZone(true);

      if (err instanceof IrisApiError) {
        setFeedbackBanner({
          type: "error",
          title: "Não foi possível extrair esse material.",
          message: err.message,
          code: err.code,
        });
      } else {
        setFeedbackBanner({
          type: "error",
          title: "Erro de conexão com o servidor",
          message:
            "Não foi possível conectar ao endpoint POST /api/v1/materials/upload. Verifique se o backend FastAPI está ativo na porta 8000.",
          code: "NETWORK_ERROR",
        });
      }
    } finally {
      setIsProcessing(false);
    }
  }, []);

  /**
   * Evento de soltar arquivo na área de Drag-and-Drop (garante apenas 1 arquivo por envio).
   */
  const handleDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      const files = e.dataTransfer.files;
      if (!files || files.length === 0) return;

      if (files.length > 1) {
        setSelectedFile({
          name: `${files.length} arquivos selecionados`,
          sizeBytes: 0,
          extension: "múltiplos",
          status: "rejected",
        });
        setFeedbackBanner({
          type: "error",
          title: "Apenas um arquivo permitido por envio",
          message:
            "Por favor, envie apenas um arquivo (.pdf, .docx ou .txt) por vez para garantir a integridade da atividade pedagógica.",
          code: "SINGLE_FILE_ONLY",
        });
        return;
      }

      await handleSingleFileProcess(files[0]);
    },
    [handleSingleFileProcess]
  );

  /**
   * Evento de seleção de arquivo pelo seletor do dispositivo.
   */
  const handleFileInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      if (files.length > 1) {
        setFeedbackBanner({
          type: "error",
          title: "Apenas um arquivo permitido por envio",
          message: "Selecione somente um arquivo (.pdf, .docx ou .txt) por envio.",
          code: "SINGLE_FILE_ONLY",
        });
        e.target.value = "";
        return;
      }

      await handleSingleFileProcess(files[0]);
      e.target.value = "";
    },
    [handleSingleFileProcess]
  );

  /**
   * Valida e sanitiza o texto atual via Backend FastAPI (`POST /api/v1/materials/text`)
   * antes de avançar para a Etapa 2.
   */
  const handleValidateAndAdvance = async () => {
    if (confirmedForStep2) {
      saveStep1StateToSession({
        textContent,
        metadata: serverMetadata,
        selectedFile,
        confirmedForStep2: true,
      });
      if (onAdvanceToStep2) {
        onAdvanceToStep2(textContent, serverMetadata);
      } else {
        router.push("/etapa-2");
      }
      return;
    }

    setConfirmedForStep2(false);

    if (!metrics.meetsMinimum) {
      setFeedbackBanner({
        type: "error",
        title: "Conteúdo insuficiente para análise pedagógica",
        message: `O material deve possuir no mínimo ${MIN_MATERIAL_CHARS} caracteres (atual: ${metrics.charCount} caracteres).`,
        code: "TEXT_TOO_SHORT",
      });
      return;
    }

    if (metrics.exceedsSafeContext) {
      setFeedbackBanner({
        type: "error",
        title: "Limite seguro da janela de contexto excedido",
        message:
          "O conteúdo ultrapassa a capacidade segura de processamento da janela de contexto da IA. Divida o material em partes menores para prosseguir.",
        code: "CONTEXT_WINDOW_EXCEEDED",
      });
      return;
    }

    setIsProcessing(true);
    setFeedbackBanner(null);

    try {
      const response = await submitMaterialText(textContent);
      setTextContent(response.raw_text);
      setServerMetadata(response.metadata);
      setConfirmedForStep2(true);

      saveStep1StateToSession({
        textContent: response.raw_text,
        metadata: response.metadata,
        selectedFile,
        confirmedForStep2: true,
      });

      const piiCount = response.metadata.pii_removed_count || 0;
      const piiInfo =
        response.metadata.sanitized && piiCount > 0
          ? ` ${piiCount === 1 ? "Foi removido preventivamente 1 identificador pessoal (PII)" : `Foram removidos preventivamente ${piiCount} identificadores pessoais (PIIs)`} para conformidade com a LGPD.`
          : "";

      setFeedbackBanner({
        type: "success",
        title: "Material validado e pronto para a Etapa 2!",
        message: `${response.message}${piiInfo}`,
      });

      if (onAdvanceToStep2) {
        onAdvanceToStep2(response.raw_text, response.metadata);
      } else {
        router.push("/etapa-2");
      }
    } catch (err) {
      if (err instanceof IrisApiError) {
        setFeedbackBanner({
          type: "error",
          title: "Falha na validação do material",
          message: err.message,
          code: err.code,
        });
      } else {
        setFeedbackBanner({
          type: "error",
          title: "Erro de comunicação com a API",
          message:
            "Não foi possível contatar o endpoint POST /api/v1/materials/text. Certifique-se de que o backend FastAPI está rodando.",
          code: "NETWORK_ERROR",
        });
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleClearAll = () => {
    setTextContent("");
    setSelectedFile(null);
    setServerMetadata(null);
    setFeedbackBanner(null);
    setConfirmedForStep2(false);
    setShowUploadZone(true);
    clearStep1StateFromSession();
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] hc-surface">
      {/* Barra Superior Institucional */}
      <IrisHeader
        currentStep={1}
        teacherEmail={teacherEmail}
        darkMode={darkMode}
        onToggleDarkMode={onToggleDarkMode}
      />

      {/* Toast / Alerta Flutuante no Canto Superior Direito (ARIA Live) */}
      <div
        id={statusRegionId}
        aria-live="polite"
        aria-atomic="true"
        className="fixed top-20 right-4 sm:right-6 z-50 w-[calc(100vw-2rem)] sm:w-96 max-w-md pointer-events-none"
      >
        {feedbackBanner && (
          <div
            role={feedbackBanner.type === "error" ? "alert" : "status"}
            className={`pointer-events-auto rounded-2xl p-4 border border-l-4 flex items-start gap-3 shadow-[0_12px_32px_-8px_rgba(13,2,33,0.28)] backdrop-blur-md transition-all animate-in fade-in slide-in-from-top-2 duration-200 ${
              feedbackBanner.type === "error"
                ? "bg-white/95 dark:bg-[#160A30]/95 border-red-200 dark:border-red-800/60 border-l-red-600 text-red-950 dark:text-red-100"
                : "bg-white/95 dark:bg-[#160A30]/95 border-emerald-200 dark:border-emerald-800/60 border-l-emerald-600 text-emerald-950 dark:text-emerald-100"
            }`}
          >
            {feedbackBanner.type === "error" ? (
              <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            ) : (
              <CheckCircle2
                className="w-5 h-5 text-emerald-600 dark:text-emerald-400 flex-shrink-0 mt-0.5"
                aria-hidden="true"
              />
            )}

            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-bold text-xs sm:text-sm leading-snug">{feedbackBanner.title}</p>
                {feedbackBanner.code && (
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-black/10 dark:bg-white/10">
                    {feedbackBanner.code}
                  </span>
                )}
              </div>
              {feedbackBanner.message && (
                <p className="text-xs mt-1 leading-relaxed opacity-85">{feedbackBanner.message}</p>
              )}
            </div>

            <button
              type="button"
              onClick={() => setFeedbackBanner(null)}
              aria-label="Fechar mensagem de feedback"
              className="text-xs font-bold opacity-60 hover:opacity-100 px-1.5 py-0.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-opacity flex-shrink-0"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        id={fileInputId}
        type="file"
        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
        onChange={handleFileInputChange}
        className="hidden"
      />

      {/* Estrutura Principal com Sidebar Lateral Modular + Conteúdo */}
      <div className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-8 flex flex-col lg:flex-row gap-6">
        <IrisSidebar
          currentStep={1}
          enabledSteps={confirmedForStep2 ? [1, 2] : [1]}
          onNavigateHome={onBackToLogin}
          onNavigateStep={(step) => {
            if (step === 2 && confirmedForStep2) {
              handleValidateAndAdvance();
            }
          }}
        />

        {/* Conteúdo Principal */}
        <main id="conteudo-principal" className="flex-1 min-w-0 space-y-5">
          {/* Cabeçalho da Etapa 1 */}
        <section aria-labelledby="titulo-etapa-1" className="space-y-2">
          <div className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#B53319] dark:text-[#FF8A70]">
            <span>{STEP_TITLES[1]}</span>
          </div>
          <h1
            id="titulo-etapa-1"
            className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[#0D0221] dark:text-white"
          >
            Entrada do material didático
          </h1>
        </section>

        {/* Card Único Integrado: Upload Drag-and-Drop (colapsa ao anexar) + Colagem Direta e Conferência */}
        <section
          aria-labelledby="heading-textarea-conferencia"
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragging(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
              setIsDragging(false);
            }
          }}
          onDrop={handleDrop}
          className={`relative bg-white dark:bg-[#160A30] border rounded-2xl px-6 pt-5 pb-6 shadow-sm flex flex-col gap-5 hc-surface transition-colors ${
            isDragging
              ? "border-[#E35336] ring-2 ring-[#E35336]/30"
              : "border-[#335C67]/20 dark:border-white/15"
          }`}
        >
          {/* Estado 1: Dropzone visível antes do upload ou ao retornar para a Etapa 1 */}
          {showUploadZone && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base sm:text-lg font-bold text-[#0D0221] dark:text-white flex items-center gap-2">
                  <FileUp className="w-5 h-5 text-[#E35336]" aria-hidden="true" />
                  Enviar documento ou colar texto
                </h2>
                <span id="formatos-suportados-hint" className="text-xs text-[#0D0221]/65 dark:text-white/65">
                  Formatos: <strong>{ALLOWED_EXTENSIONS.join(", ")}</strong> (1 arquivo por envio)
                </span>
              </div>

              <div
                role="button"
                tabIndex={0}
                aria-label="Área de envio de arquivo. Arraste e solte um arquivo .pdf, .docx ou .txt aqui ou pressione Enter para selecionar do dispositivo."
                aria-describedby="formatos-suportados-hint"
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                className={`rounded-2xl border-2 border-dashed px-5 py-5 cursor-pointer transition-all flex flex-col sm:flex-row items-center justify-center gap-4 text-center sm:text-left ${
                  isDragging
                    ? "border-[#E35336] bg-[#E35336]/10 scale-[1.005]"
                    : selectedFile?.status === "rejected"
                    ? "border-red-500 bg-red-500/5"
                    : "border-[#335C67]/30 dark:border-white/20 hover:border-[#E35336] bg-[#F5EDF0]/45 dark:bg-white/5"
                }`}
              >
                <div className="w-11 h-11 rounded-xl bg-[#E35336]/15 text-[#E35336] flex items-center justify-center flex-shrink-0">
                  {isProcessing ? (
                    <Loader2 className="w-6 h-6 animate-spin" aria-hidden="true" />
                  ) : (
                    <FileUp className="w-6 h-6" aria-hidden="true" />
                  )}
                </div>

                <div className="space-y-0.5">
                  <p className="text-sm font-bold text-[#0D0221] dark:text-white">
                    {isDragging
                      ? "Solte o arquivo aqui para extrair o texto"
                      : "Arraste e solte sua atividade aqui"}
                  </p>
                  <p className="text-xs text-[#0D0221]/70 dark:text-white/70">
                    ou <span className="text-[#E35336] font-bold underline">clique para selecionar do dispositivo</span>
                  </p>
                </div>
              </div>

              {/* Feedback de arquivo em processamento ou rejeitado */}
              {selectedFile && selectedFile.status !== "accepted" && (
                <div
                  aria-live="polite"
                  className={`rounded-xl px-4 py-3 border flex items-center justify-between gap-3 ${
                    selectedFile.status === "rejected"
                      ? "bg-red-500/10 border-red-500/40 text-red-950 dark:text-red-100"
                      : "bg-[#335C67]/10 border-[#335C67]/30 text-[#0D0221] dark:text-white"
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {selectedFile.status === "rejected" ? (
                      <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" aria-hidden="true" />
                    ) : (
                      <Loader2 className="w-5 h-5 text-[#E35336] animate-spin flex-shrink-0" aria-hidden="true" />
                    )}

                    <div className="min-w-0">
                      <p className="text-xs font-bold truncate" title={selectedFile.name}>
                        {selectedFile.name}
                      </p>
                      <p className="text-[11px] opacity-80">
                        {selectedFile.status === "rejected" &&
                          (selectedFile.errorMessage ||
                            `Formato ou arquivo rejeitado (${selectedFile.extension}) — Tente novamente`)}
                        {selectedFile.status === "uploading" && "Extraindo e sanitizando em memória..."}
                      </p>
                    </div>
                  </div>

                  {selectedFile.status === "rejected" && (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/80 dark:bg-white/10 hover:bg-white transition-colors flex-shrink-0"
                    >
                      <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                      Nova tentativa
                    </button>
                  )}
                </div>
              )}

              {/* Divisor discreto entre upload e colagem */}
              <div className="relative flex items-center py-0.5" aria-hidden="true">
                <div className="flex-grow border-t border-[#335C67]/15 dark:border-white/15" />
                <span className="flex-shrink mx-3 text-[11px] font-semibold uppercase tracking-wider text-[#0D0221]/50 dark:text-white/50">
                  ou cole o material abaixo
                </span>
                <div className="flex-grow border-t border-[#335C67]/15 dark:border-white/15" />
              </div>
            </div>
          )}

          {/* Área Acessível de Colagem Direta e Conferência Imediata (`textarea`) */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label
                htmlFor={textareaId}
                id="heading-textarea-conferencia"
                className="text-base sm:text-lg font-bold text-[#0D0221] dark:text-white flex items-center gap-2 cursor-pointer"
              >
                <ClipboardPaste className="w-5 h-5 text-[#E35336]" aria-hidden="true" />
                {selectedFile?.status === "accepted"
                  ? "Conferência e Edição do Material Extraído"
                  : "Colagem Direta e Conferência do Material"}
              </label>

              {selectedFile?.status !== "accepted" && serverMetadata?.filename && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-800 dark:text-emerald-200">
                  <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                  Extraído de: {serverMetadata.filename}
                </span>
              )}
            </div>

            <div className="relative">
              <textarea
                id={textareaId}
                value={textContent}
                onChange={(e) => {
                  setTextContent(e.target.value);
                  setConfirmedForStep2(false);
                }}
                rows={selectedFile?.status === "accepted" && !showUploadZone ? 13 : 9}
                placeholder="Cole aqui os textos de apoio, enunciados e alternativas da atividade ou arraste um arquivo para cá..."
                aria-invalid={textContent.length > 0 && (!metrics.meetsMinimum || metrics.exceedsSafeContext)}
                aria-describedby="contador-tempo-real-info"
                className="w-full rounded-xl bg-[#FAFAFC] dark:bg-[#0D0221]/90 border border-[#335C67]/30 dark:border-white/20 p-4 text-sm sm:text-base leading-relaxed text-[#0D0221] dark:text-[#F5EDF0] placeholder:text-[#0D0221]/40 dark:placeholder:text-white/40 focus:border-[#E35336] transition-colors resize-y font-sans"
              />
            </div>
          </div>

          {/* Barra de Contadores em Tempo Real (Sem limite máximo fixo de palavras na interface) */}
          <div
            id="contador-tempo-real-info"
            aria-live="polite"
            className="rounded-xl bg-[#F5EDF0]/75 dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 px-3.5 py-2 flex flex-wrap items-center justify-between gap-2.5"
          >
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-baseline gap-1.5">
                <span className="text-[11px] uppercase tracking-wider opacity-70">Caracteres</span>
                <span className="font-mono text-xs sm:text-sm font-bold text-[#0D0221] dark:text-white">
                  {metrics.charCount.toLocaleString("pt-BR")}
                </span>
              </div>

              <div className="h-4 w-px bg-[#335C67]/20 dark:bg-white/15" aria-hidden="true" />

              <div className="flex items-baseline gap-1.5">
                <span className="text-[11px] uppercase tracking-wider opacity-70">Palavras</span>
                <span className="font-mono text-xs sm:text-sm font-bold text-[#0D0221] dark:text-white">
                  {metrics.wordCount.toLocaleString("pt-BR")}
                </span>
              </div>
            </div>

            {/* Indicador do Critério de Aceite: Mínimo de 50 caracteres */}
            <div className="flex items-center gap-2">
              {metrics.charCount === 0 ? (
                <span className="text-xs font-medium text-[#0D0221]/65 dark:text-white/65">
                  Mínimo necessário: <strong>{MIN_MATERIAL_CHARS} caracteres</strong>
                </span>
              ) : !metrics.meetsMinimum ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30">
                  <AlertCircle className="w-3.5 h-3.5" aria-hidden="true" />
                  {MIN_MATERIAL_CHARS - metrics.charCount === 1
                    ? `Falta 1 caractere (mín. ${MIN_MATERIAL_CHARS})`
                    : `Faltam ${MIN_MATERIAL_CHARS - metrics.charCount} caracteres (mín. ${MIN_MATERIAL_CHARS})`}
                </span>
              ) : metrics.exceedsSafeContext ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-500/15 text-red-800 dark:text-red-300 border border-red-500/30">
                  <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
                  Excede capacidade segura de processamento
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 border border-emerald-500/30">
                  <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                  Mínimo de {MIN_MATERIAL_CHARS} caracteres atingido
                </span>
              )}
            </div>
          </div>

          {/* Card verde de arquivo anexado embaixo da conferência do material */}
          {selectedFile?.status === "accepted" && (
            <div
              aria-live="polite"
              className="rounded-xl px-3.5 py-2 border bg-emerald-500/10 border-emerald-600/35 text-emerald-950 dark:text-emerald-100 flex items-center justify-between gap-3"
            >
              <div className="flex items-center gap-2.5 flex-1 min-w-0">
                <FileCheck2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" aria-hidden="true" />
                <p className="text-xs sm:text-sm font-bold truncate" title={serverMetadata?.filename || selectedFile.name}>
                  Extraído de: {serverMetadata?.filename || selectedFile.name}
                </p>
              </div>

              <button
                type="button"
                disabled={isProcessing}
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-white/90 dark:bg-white/10 hover:bg-white dark:hover:bg-white/20 text-[#0D0221] dark:text-white border border-emerald-600/25 transition-colors flex-shrink-0"
              >
                {isProcessing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                )}
                Trocar arquivo
              </button>
            </div>
          )}

          {/* Rodapé de Ação Principal (Estilo Fiery Terracotta #E35336 do Figma) */}
          <div className="pt-2 flex flex-col-reverse sm:flex-row sm:items-center justify-between gap-3 border-t border-[#335C67]/15 dark:border-white/10">
            {(textContent.length > 0 || selectedFile !== null) && (
              <button
                type="button"
                onClick={handleClearAll}
                className="inline-flex items-center justify-center gap-1.5 px-4 py-3 rounded-xl text-xs font-semibold text-red-700 dark:text-red-300 bg-red-500/10 hover:bg-red-500/20 transition-colors"
              >
                <Trash2 className="w-4 h-4" aria-hidden="true" />
                Limpar
              </button>
            )}

            <button
              type="button"
              disabled={!metrics.meetsMinimum || metrics.exceedsSafeContext || isProcessing}
              onClick={handleValidateAndAdvance}
              className="sm:ml-auto inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl font-bold text-sm text-white bg-[#E35336] hover:bg-[#c94429] disabled:opacity-45 disabled:cursor-not-allowed shadow-[0_8px_20px_-4px_rgba(227,83,54,0.45)] transition-all flex-shrink-0"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  Processando em memória...
                </>
              ) : confirmedForStep2 ? (
                <>
                  <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                  Avançar para Etapa 2
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </>
              ) : (
                <>
                  Validar e Avançar para Etapa 2
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </section>
        </main>
      </div>
    </div>
  );
}
