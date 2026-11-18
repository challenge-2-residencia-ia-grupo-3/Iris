"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardPaste,
  Contrast,
  FileCheck2,
  FileText,
  FileUp,
  Loader2,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
  Trash2,
  XCircle,
} from "lucide-react";
import { IrisHeader } from "./IrisHeader";
import { IrisSidebar } from "./IrisSidebar";
import { useTheme } from "@/contexts/ThemeContext";
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
  const { darkMode: contextDarkMode, toggleDarkMode: contextToggleDarkMode } = useTheme();
  const isDarkMode = darkMode ?? contextDarkMode;
  const handleToggleDarkMode = onToggleDarkMode ?? contextToggleDarkMode;

  const textareaId = useId();
  const fileInputId = useId();
  const statusRegionId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [highContrast, setHighContrast] = useState(false);
  const [textContent, setTextContent] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  // Estado do arquivo enviado (apenas 1 arquivo por envio)
  const [selectedFile, setSelectedFile] = useState<Step1SelectedFileInfo | null>(null);

  // Resultado processado pelo Backend FastAPI (`POST /api/v1/materials/upload` ou `POST /api/v1/materials/text`)
  const [serverMetadata, setServerMetadata] = useState<MaterialMetadata | null>(null);
  const [feedbackBanner, setFeedbackBanner] = useState<{
    type: "success" | "error" | "warning" | "info";
    title: string;
    message: string;
    code?: string;
  } | null>(null);

  const [confirmedForStep2, setConfirmedForStep2] = useState<boolean>(false);

  // Restaura o material e arquivo enviados anteriormente na sessão ao voltar da Etapa 2
  useEffect(() => {
    const saved = loadStep1StateFromSession();
    if (saved && saved.textContent) {
      setTextContent(saved.textContent);
      setServerMetadata(saved.metadata);
      setSelectedFile(saved.selectedFile);
      setConfirmedForStep2(saved.confirmedForStep2);
      setFeedbackBanner({
        type: "info",
        title: "Material recuperado da sessão atual",
        message:
          "O conteúdo e os dados do material carregado anteriormente foram mantidos em memória para sua revisão.",
      });
    }
  }, []);

  useEffect(() => {
    if (!feedbackBanner) return;
    const timer = window.setTimeout(() => {
      setFeedbackBanner(null);
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [feedbackBanner]);

  useEffect(() => {
    const root = document.documentElement;
    if (highContrast) {
      root.classList.add("high-contrast");
    } else {
      root.classList.remove("high-contrast");
    }
  }, [highContrast]);

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
      setSelectedFile({
        name: file.name,
        sizeBytes: file.size,
        extension: validation.extension,
        status: "rejected",
      });
      setServerMetadata(null);
      setFeedbackBanner({
        type: "error",
        title: "Arquivo rejeitado na validação",
        message:
          validation.errorMessage ||
          "Formato não suportado. Envie apenas um arquivo nos formatos .pdf, .docx ou .txt.",
        code: validation.errorCode,
      });
      return;
    }

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

      saveStep1StateToSession({
        textContent: response.raw_text,
        metadata: response.metadata,
        selectedFile: acceptedFileInfo,
        confirmedForStep2: false,
      });

      const piiCount = response.metadata.pii_removed_count || 0;
      const piiNote =
        response.metadata.sanitized && piiCount > 0
          ? ` (${piiCount === 1 ? "1 dado pessoal anonimizado" : `${piiCount} dados pessoais anonimizados`} preventivamente via Zero-Retention Scrubber).`
          : "";

      setFeedbackBanner({
        type: "success",
        title: "Conteúdo extraído em memória para conferência imediata",
        message: `Confira o texto abaixo antes de prosseguir.`,
      });
    } catch (err) {
      setSelectedFile({
        name: file.name,
        sizeBytes: file.size,
        extension: validation.extension,
        status: "rejected",
      });
      setServerMetadata(null);

      if (err instanceof IrisApiError) {
        setFeedbackBanner({
          type: "error",
          title: "Não foi possível extrair o documento",
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
        message: `${response.message}${piiInfo} Clique novamente em 'Conferido! Avançar para Etapa 2' para selecionar as características funcionais.`,
      });
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
    clearStep1StateFromSession();
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] hc-surface">
      <IrisHeader
        currentStep={1}
        stepTitle="Entrada do material didático"
        teacherEmail={teacherEmail}
        highContrast={highContrast}
        onToggleHighContrast={() => setHighContrast((prev) => !prev)}
        darkMode={isDarkMode}
        onToggleDarkMode={handleToggleDarkMode}
        onBackToLogin={onBackToLogin}
      />

      {/* Estrutura Principal com Sidebar Lateral Modular + Conteúdo */}
      <div className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 sm:py-8 flex flex-col lg:flex-row gap-6 items-start">
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
        <main id="conteudo-principal" className="flex-1 min-w-0 space-y-6">
          {/* Cabeçalho Editorial da Etapa 1 */}
          <section
            aria-labelledby="titulo-etapa-1"
            className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-4 border-b border-[#335C67]/15 dark:border-white/10"
          >
            <div className="space-y-1">
              <h1
                id="titulo-etapa-1"
                className="font-display text-2xl sm:text-3xl font-semibold tracking-tight text-[#0D0221] dark:text-white"
              >
                Entrada do material didático
              </h1>
              <p className="text-xs sm:text-sm text-[#0D0221]/70 dark:text-white/70 max-w-2xl">
                Envie um documento ou cole o enunciado da atividade para extração e proteção automática de dados.
              </p>
            </div>

            {textContent.length > 0 && (
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  type="button"
                  onClick={handleClearAll}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-red-700 dark:text-red-300 bg-red-500/10 hover:bg-red-500/20 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Limpar material</span>
                </button>
              </div>
            )}
          </section>

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
                className={`pointer-events-auto rounded-xl p-4 border border-l-4 flex items-start gap-3 shadow-lg backdrop-blur-md transition-all ${
                  feedbackBanner.type === "error"
                    ? "bg-white/95 dark:bg-[#160A30]/95 border-red-200 dark:border-red-800/60 border-l-red-600 text-red-950 dark:text-red-100"
                    : feedbackBanner.type === "success"
                    ? "bg-white/95 dark:bg-[#160A30]/95 border-emerald-200 dark:border-emerald-800/60 border-l-emerald-600 text-emerald-950 dark:text-emerald-100"
                    : feedbackBanner.type === "warning"
                    ? "bg-white/95 dark:bg-[#160A30]/95 border-amber-200 dark:border-amber-800/60 border-l-amber-500 text-amber-950 dark:text-amber-100"
                    : "bg-white/95 dark:bg-[#160A30]/95 border-[#335C67]/25 dark:border-white/15 border-l-[#E35336] text-[#0D0221] dark:text-white"
                }`}
              >
                {feedbackBanner.type === "error" ? (
                  <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                ) : feedbackBanner.type === "success" ? (
                  <CheckCircle2
                    className="w-5 h-5 text-emerald-600 dark:text-emerald-400 flex-shrink-0 mt-0.5"
                    aria-hidden="true"
                  />
                ) : (
                  <AlertCircle className="w-5 h-5 text-[#E35336] flex-shrink-0 mt-0.5" aria-hidden="true" />
                )}

                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-xs sm:text-sm leading-snug">{feedbackBanner.title}</p>
                  <p className="text-xs mt-1 leading-relaxed opacity-85">{feedbackBanner.message}</p>
                </div>

                <button
                  type="button"
                  onClick={() => setFeedbackBanner(null)}
                  aria-label="Fechar mensagem de feedback"
                  className="text-xs font-semibold opacity-60 hover:opacity-100 px-1.5 py-0.5 rounded hover:bg-black/5 dark:hover:bg-white/10 transition-opacity flex-shrink-0"
                >
                  ✕
                </button>
              </div>
            )}
          </div>

          {/* Grid Principal: Coluna Esquerda (Upload Drag-and-Drop) + Coluna Direita (Folha de Conferência) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
            {/* COLUNA 1: Upload Drag-and-Drop de Arquivo Único (.pdf, .docx, .txt) */}
            <section
              aria-labelledby="heading-upload-doc"
              className="bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-xl p-5 flex flex-col justify-between gap-4 hc-surface lg:h-[480px]"
            >
              <div className="flex-1 flex flex-col space-y-3 min-h-0">
                <div className="flex items-center justify-between gap-3">
                  <h2
                    id="heading-upload-doc"
                    className="text-base font-bold text-[#0D0221] dark:text-white flex items-center gap-2"
                  >
                    <FileUp className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                    <span>Enviar documento</span>
                  </h2>
                  <span
                    id="formatos-suportados-hint"
                    className="text-xs text-[#0D0221]/60 dark:text-white/60 font-mono"
                  >
                    {ALLOWED_EXTENSIONS.join(", ")}
                  </span>
                </div>

                {/* Zona Drag-and-Drop Acessível por Teclado e Mouse */}
                <div
                  role="button"
                  tabIndex={0}
                  aria-label="Área de envio de arquivo. Arraste e solte um arquivo .pdf, .docx ou .txt aqui ou pressione Enter para selecionar do dispositivo."
                  aria-describedby="formatos-suportados-hint"
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragging(true);
                  }}
                  onDragLeave={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragging(false);
                  }}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  className={`relative rounded-xl border-2 border-dashed p-6 text-center cursor-pointer transition-colors flex-1 flex flex-col items-center justify-center min-h-0 ${
                    isDragging
                      ? "border-[#E35336] bg-[#E35336]/10"
                      : selectedFile?.status === "rejected"
                      ? "border-red-500 bg-red-500/5"
                      : selectedFile?.status === "accepted"
                      ? "border-emerald-600 bg-emerald-500/5"
                      : "border-[#335C67]/30 dark:border-white/20 hover:border-[#E35336] bg-[#FAF7F8] dark:bg-white/[0.03]"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    id={fileInputId}
                    type="file"
                    accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                    onChange={handleFileInputChange}
                    className="sr-only"
                  />

                  <div className="mx-auto w-12 h-12 rounded-xl bg-[#E35336]/12 text-[#E35336] flex items-center justify-center mb-3">
                    {isProcessing ? (
                      <Loader2 className="w-6 h-6 animate-spin" aria-hidden="true" />
                    ) : (
                      <FileUp className="w-6 h-6" aria-hidden="true" />
                    )}
                  </div>

                  <p className="text-sm font-semibold text-[#0D0221] dark:text-white">
                    {isDragging
                      ? "Solte o arquivo aqui para extrair o texto"
                      : "Arraste e solte sua atividade aqui"}
                  </p>
                  <p className="text-xs text-[#0D0221]/65 dark:text-white/65 mt-1">
                    ou <span className="text-[#E35336] font-semibold underline">selecione um arquivo do dispositivo</span>
                  </p>
                </div>
              </div>

              {/* Feedback Visual de Formato Aceito / Rejeitado */}
              {selectedFile && (
                <div
                  aria-live="polite"
                  className={`rounded-lg p-3.5 border flex items-center justify-between gap-3 ${
                    selectedFile.status === "accepted"
                      ? "bg-emerald-500/10 border-emerald-600/35 text-emerald-950 dark:text-emerald-100"
                      : selectedFile.status === "rejected"
                      ? "bg-red-500/10 border-red-500/35 text-red-950 dark:text-red-100"
                      : "bg-[#335C67]/10 border-[#335C67]/25 text-[#0D0221] dark:text-white"
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {selectedFile.status === "accepted" ? (
                      <FileCheck2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" aria-hidden="true" />
                    ) : selectedFile.status === "rejected" ? (
                      <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" aria-hidden="true" />
                    ) : (
                      <Loader2 className="w-5 h-5 text-[#E35336] animate-spin flex-shrink-0" aria-hidden="true" />
                    )}

                    <div className="min-w-0">
                      <p className="text-xs font-semibold truncate" title={selectedFile.name}>
                        {selectedFile.name}
                      </p>
                      <p className="text-[11px] opacity-80">
                        {selectedFile.status === "accepted" &&
                          `Arquivo ${selectedFile.extension.toUpperCase()} (${formatFileSize(selectedFile.sizeBytes)})`}
                        {selectedFile.status === "rejected" &&
                          `Arquivo não suportado (${selectedFile.extension}). Escolha outro arquivo.`}
                        {selectedFile.status === "uploading" && "Extraindo e sanitizando em memória..."}
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-white/80 dark:bg-white/10 hover:bg-white transition-colors flex-shrink-0"
                  >
                    <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>Trocar arquivo</span>
                  </button>
                </div>
              )}
            </section>

            {/* COLUNA 2: Folha de Colagem Direta e Conferência Imediata (`textarea`) */}
            <section
              aria-labelledby="heading-textarea-conferencia"
              className="bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-xl p-5 flex flex-col justify-between gap-3 hc-surface lg:h-[480px]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 flex-shrink-0">
                <label
                  htmlFor={textareaId}
                  id="heading-textarea-conferencia"
                  className="text-base font-bold text-[#0D0221] dark:text-white flex items-center gap-2 cursor-pointer"
                >
                  <ClipboardPaste className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
                  <span>Texto da atividade para conferência</span>
                </label>

                {serverMetadata?.filename && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-500/15 text-emerald-800 dark:text-emerald-200">
                    <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>Origem: {serverMetadata.filename}</span>
                  </span>
                )}
              </div>

              {/* Textarea Acessível (WCAG 2.1 AA) */}
              <div className="relative flex-1 min-h-0 flex flex-col">
                <textarea
                  id={textareaId}
                  value={textContent}
                  onChange={(e) => {
                    setTextContent(e.target.value);
                    setConfirmedForStep2(false);
                  }}
                  rows={8}
                  placeholder="Cole aqui os textos de apoio, enunciados e alternativas da atividade ou envie um arquivo ao lado..."
                  aria-invalid={textContent.length > 0 && (!metrics.meetsMinimum || metrics.exceedsSafeContext)}
                  aria-describedby="contador-tempo-real-info"
                  className="w-full flex-1 min-h-[140px] rounded-lg bg-[#FAF7F8] dark:bg-[#0D0221]/90 border border-[#335C67]/25 dark:border-white/15 p-3.5 text-sm sm:text-base leading-relaxed text-[#0D0221] dark:text-[#F5EDF0] placeholder:text-[#0D0221]/40 dark:placeholder:text-white/40 focus:border-[#E35336] transition-colors resize-none overflow-y-auto font-sans"
                />
              </div>

              {/* Barra de Contadores em Tempo Real (Sentence case, sem ALL-CAPS) */}
              <div
                id="contador-tempo-real-info"
                aria-live="polite"
                className="rounded-lg bg-[#FAF7F8] dark:bg-white/[0.04] border border-[#335C67]/15 dark:border-white/10 px-3.5 py-2 flex flex-wrap items-center justify-between gap-2 text-xs flex-shrink-0"
              >
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-[#0D0221]/65 dark:text-white/65">Caracteres:</span>
                    <span className="font-mono font-semibold text-[#0D0221] dark:text-white">
                      {metrics.charCount.toLocaleString("pt-BR")}
                    </span>
                  </div>

                  <div className="h-4 w-px bg-[#335C67]/20 dark:bg-white/15" aria-hidden="true" />

                  <div className="flex items-baseline gap-1.5">
                    <span className="text-[#0D0221]/65 dark:text-white/65">Palavras:</span>
                    <span className="font-mono font-semibold text-[#0D0221] dark:text-white">
                      {metrics.wordCount.toLocaleString("pt-BR")}
                    </span>
                  </div>
                </div>

                {/* Indicador do Critério de Aceite: Mínimo de 50 caracteres */}
                <div className="flex items-center gap-2">
                  {metrics.charCount === 0 ? (
                    <span className="text-xs text-[#0D0221]/65 dark:text-white/65">
                      Mínimo necessário: <strong>{MIN_MATERIAL_CHARS} caracteres</strong>
                    </span>
                  ) : !metrics.meetsMinimum ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30">
                      <AlertCircle className="w-3.5 h-3.5" aria-hidden="true" />
                      {MIN_MATERIAL_CHARS - metrics.charCount === 1
                        ? `Falta 1 caractere (mín. ${MIN_MATERIAL_CHARS})`
                        : `Faltam ${MIN_MATERIAL_CHARS - metrics.charCount} caracteres (mín. ${MIN_MATERIAL_CHARS})`}
                    </span>
                  ) : metrics.exceedsSafeContext ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-red-500/15 text-red-800 dark:text-red-300 border border-red-500/30">
                      <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
                      Excede a capacidade segura de processamento
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 border border-emerald-500/30">
                      <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                      Mínimo de {MIN_MATERIAL_CHARS} caracteres atingido
                    </span>
                  )}
                </div>
              </div>

              {/* Rodapé de Ação Principal */}
              <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-end gap-3 border-t border-[#335C67]/15 dark:border-white/10 flex-shrink-0">
                <button
                  type="button"
                  disabled={!metrics.meetsMinimum || metrics.exceedsSafeContext || isProcessing}
                  onClick={handleValidateAndAdvance}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm text-white bg-[#E35336] hover:bg-[#c94429] disabled:opacity-45 disabled:cursor-not-allowed transition-colors flex-shrink-0"
                >
                  {isProcessing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                      <span>Processando em memória...</span>
                    </>
                  ) : confirmedForStep2 ? (
                    <>
                      <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                      <span>Avançar para Etapa 2</span>
                      <ArrowRight className="w-4 h-4" aria-hidden="true" />
                    </>
                  ) : (
                    <>
                      <span>Validar e conferir material</span>
                      <ArrowRight className="w-4 h-4" aria-hidden="true" />
                    </>
                  )}
                </button>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
