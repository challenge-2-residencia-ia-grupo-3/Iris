"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
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
  Sparkles,
  Sun,
  Trash2,
  XCircle,
} from "lucide-react";
import { IrisLogoBanner } from "./IrisLogoBanner";
import { Stepper5Etapas } from "./Stepper5Etapas";
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
  darkMode: boolean;
  onToggleDarkMode: () => void;
}

const SAMPLE_PEDAGOGICAL_ACTIVITY = `Escola Municipal Professora Cecília Meireles
Aluno(a): Gabriel Silva de Oliveira — Turma: 7º Ano B — Matrícula: 20261045

AVALIAÇÃO BIMESTRAL DE CIÊNCIAS DA NATUREZA

Texto de Apoio:
Os ecossistemas brasileiros apresentam grande diversidade biológica e dependem diretamente do equilíbrio dos ciclos biogeoquímicos (água, carbono e nitrogênio). Nas regiões de Cerrado, as matas ciliares desempenham papel essencial na proteção das bacias hidrográficas.

Questão 1: Leia atentamente o trecho acima, identifique dois fatores que ameaçam a conservação das bacias hidrográficas no Cerrado, relacione-os ao ciclo da água e proponha uma ação prática de preservação ambiental.`;

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

      const piiNote =
        response.metadata.sanitized && response.metadata.pii_removed_count > 0
          ? ` (${response.metadata.pii_removed_count} dado(s) pessoal(is) anonimizado(s) preventivamente via Zero-Retention Scrubber).`
          : "";

      setFeedbackBanner({
        type: "success",
        title: "Conteúdo extraído em memória para conferência imediata",
        message: `${response.message}${piiNote} Confira o texto abaixo antes de prosseguir.`,
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
      } else if (typeof window !== "undefined") {
        window.location.href = "/etapa-2";
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

      const piiInfo =
        response.metadata.sanitized && response.metadata.pii_removed_count > 0
          ? ` Foram removidos preventivamente ${response.metadata.pii_removed_count} identificador(es) pessoal(is) (PII) para conformidade com a LGPD.`
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

  const handleLoadExample = () => {
    setTextContent(SAMPLE_PEDAGOGICAL_ACTIVITY);
    setSelectedFile(null);
    setServerMetadata(null);
    setConfirmedForStep2(false);
    setFeedbackBanner({
      type: "info",
      title: "Exemplo de avaliação carregado",
      message:
        "Observe que o exemplo contém cabeçalho escolar com nome de aluno e matrícula. Ao clicar em 'Validar e Conferir no Servidor', o sanitizador Zero-Retention substituirá os dados pessoais por [ESTUDANTE] e [IDENTIFICADOR].",
    });
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F5EDF0] dark:bg-[#0D0221] text-[#0D0221] dark:text-[#F5EDF0] hc-surface">
      {/* Barra Superior Institucional */}
      <header className="sticky top-0 z-30 backdrop-blur-md bg-[#F5EDF0]/90 dark:bg-[#0D0221]/90 border-b border-[#335C67]/15 dark:border-white/15 px-4 sm:px-8 py-3.5 hc-surface">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <IrisLogoBanner compact />
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#335C67]/10 dark:bg-white/10 border border-[#335C67]/25 text-xs font-semibold text-[#335C67] dark:text-[#F5EDF0]">
              <ShieldCheck className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
              <span>Zero-Database • Conformidade LGPD</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden sm:inline-block text-xs font-medium text-[#0D0221]/70 dark:text-white/70">
              Docente: <strong className="text-[#0D0221] dark:text-white">{teacherEmail}</strong>
            </span>

            {/* Botão Alto Contraste (WCAG 2.1 AA - RNF-09) */}
            <button
              type="button"
              onClick={() => setHighContrast((prev) => !prev)}
              aria-pressed={highContrast}
              aria-label="Alternar modo de alto contraste"
              title="Alternar modo de alto contraste (WCAG 2.1 AA)"
              className="p-2.5 rounded-xl border border-[#335C67]/25 dark:border-white/20 hover:bg-[#335C67]/10 dark:hover:bg-white/10 transition-colors"
            >
              <Contrast className="w-4 h-4" aria-hidden="true" />
            </button>

            {/* Botão Modo Claro / Escuro idêntico ao protótipo do Figma */}
            <button
              type="button"
              onClick={onToggleDarkMode}
              aria-pressed={darkMode}
              aria-label={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
              title={darkMode ? "Ativar modo claro" : "Ativar modo escuro"}
              className="p-2.5 rounded-xl border border-[#335C67]/25 dark:border-white/20 hover:bg-[#335C67]/10 dark:hover:bg-white/10 transition-colors"
            >
              {darkMode ? (
                <Sun className="w-4 h-4 text-[#E35336]" aria-hidden="true" />
              ) : (
                <Moon className="w-4 h-4 text-[#0D0221]" aria-hidden="true" />
              )}
            </button>

            {onBackToLogin && (
              <button
                type="button"
                onClick={onBackToLogin}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#335C67] dark:text-[#F5EDF0] hover:bg-[#335C67]/10 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
                Trocar conta
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Conteúdo Principal */}
      <main id="conteudo-principal" className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-8 space-y-6">
        {/* Stepper das 5 Etapas (RNF-10) */}
        <Stepper5Etapas currentStep={1} />

        {/* Cabeçalho da Etapa 1 */}
        <section aria-labelledby="titulo-etapa-1" className="space-y-2">
          <div className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#E35336]">
            <span>Etapa 1 de 5 • Gestão de Insumos Pedagógicos</span>
          </div>
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h1
                id="titulo-etapa-1"
                className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[#0D0221] dark:text-white"
              >
                Identificação e Entrada do Material Didático
              </h1>
              <p className="text-sm sm:text-base text-[#0D0221]/75 dark:text-white/75 mt-1 max-w-3xl">
                Cole diretamente o texto da sua avaliação ou faça o upload de um arquivo (
                <code className="font-mono font-semibold text-[#335C67] dark:text-[#E35336]">.pdf</code>,{" "}
                <code className="font-mono font-semibold text-[#335C67] dark:text-[#E35336]">.docx</code> ou{" "}
                <code className="font-mono font-semibold text-[#335C67] dark:text-[#E35336]">.txt</code>
                ). A extração ocorre 100% em memória com preservação da acentuação (UTF-8) e descarte imediato de dados pessoais.
              </p>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={handleLoadExample}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-[#335C67]/10 dark:bg-white/10 text-[#335C67] dark:text-white hover:bg-[#335C67]/20 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5 text-[#E35336]" aria-hidden="true" />
                Preencher com atividade de exemplo
              </button>
              {textContent.length > 0 && (
                <button
                  type="button"
                  onClick={handleClearAll}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-red-700 dark:text-red-300 bg-red-500/10 hover:bg-red-500/20 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                  Limpar
                </button>
              )}
            </div>
          </div>
        </section>

        {/* Banner de Alerta / Feedback Estruturado (ARIA Live para Leitores de Tela) */}
        <div id={statusRegionId} aria-live="polite" aria-atomic="true">
          {feedbackBanner && (
            <div
              role={feedbackBanner.type === "error" ? "alert" : "status"}
              className={`rounded-2xl p-4 border flex items-start gap-3.5 shadow-sm transition-all ${
                feedbackBanner.type === "error"
                  ? "bg-red-50 dark:bg-red-950/50 border-red-400 dark:border-red-700 text-red-900 dark:text-red-100"
                  : feedbackBanner.type === "success"
                  ? "bg-emerald-50 dark:bg-emerald-950/50 border-emerald-500/60 text-emerald-950 dark:text-emerald-100"
                  : feedbackBanner.type === "warning"
                  ? "bg-amber-50 dark:bg-amber-950/50 border-amber-500/60 text-amber-950 dark:text-amber-100"
                  : "bg-white dark:bg-[#160A30] border-[#335C67]/40 text-[#0D0221] dark:text-white"
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
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-bold text-sm">{feedbackBanner.title}</p>
                  {feedbackBanner.code && (
                    <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-black/10 dark:bg-white/10">
                      {feedbackBanner.code}
                    </span>
                  )}
                </div>
                <p className="text-xs sm:text-sm mt-0.5 leading-relaxed opacity-90">{feedbackBanner.message}</p>
              </div>

              <button
                type="button"
                onClick={() => setFeedbackBanner(null)}
                aria-label="Fechar mensagem de feedback"
                className="text-xs font-semibold underline opacity-75 hover:opacity-100"
              >
                Fechar
              </button>
            </div>
          )}
        </div>

        {/* Grid Principal: Coluna Esquerda (Upload Drag-and-Drop) + Coluna Direita (Colagem Direta e Conferência) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* COLUNA 1: Upload Drag-and-Drop de Arquivo Único (.pdf, .docx, .txt) */}
          <section
            aria-labelledby="heading-upload-doc"
            className="lg:col-span-5 bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-2xl p-6 shadow-sm space-y-5 hc-surface"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="heading-upload-doc" className="text-lg font-bold text-[#0D0221] dark:text-white flex items-center gap-2">
                  <FileUp className="w-5 h-5 text-[#E35336]" aria-hidden="true" />
                  Upload de Documento
                </h2>
                <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-0.5">
                  Envie um arquivo existente do seu computador (1 arquivo por envio).
                </p>
              </div>
              <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#335C67]/10 text-[#335C67] dark:bg-white/10 dark:text-white">
                Extração em Memória
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
              className={`relative rounded-2xl border-2 border-dashed p-7 text-center cursor-pointer transition-all ${
                isDragging
                  ? "border-[#E35336] bg-[#E35336]/10 scale-[1.01]"
                  : selectedFile?.status === "rejected"
                  ? "border-red-500 bg-red-500/5"
                  : selectedFile?.status === "accepted"
                  ? "border-emerald-600 bg-emerald-500/5"
                  : "border-[#335C67]/35 dark:border-white/25 hover:border-[#E35336] bg-[#F5EDF0]/45 dark:bg-white/5"
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

              <div className="mx-auto w-14 h-14 rounded-2xl bg-[#E35336]/15 text-[#E35336] flex items-center justify-center mb-3">
                {isProcessing ? (
                  <Loader2 className="w-7 h-7 animate-spin" aria-hidden="true" />
                ) : (
                  <FileUp className="w-7 h-7" aria-hidden="true" />
                )}
              </div>

              <p className="text-sm font-bold text-[#0D0221] dark:text-white">
                {isDragging
                  ? "Solte o arquivo aqui para extrair o texto"
                  : "Arraste e solte sua atividade aqui"}
              </p>
              <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-1">
                ou <span className="text-[#E35336] font-bold underline">clique para selecionar do dispositivo</span>
              </p>

              {/* Badges Visuais de Formatos Aceitos */}
              <div id="formatos-suportados-hint" className="mt-4 flex flex-wrap items-center justify-center gap-2">
                {ALLOWED_EXTENSIONS.map((ext) => (
                  <span
                    key={ext}
                    className="font-mono text-xs font-bold px-2.5 py-1 rounded-lg bg-white dark:bg-[#0D0221] border border-[#335C67]/25 dark:border-white/20 text-[#335C67] dark:text-[#F5EDF0]"
                  >
                    {ext.toUpperCase()}
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-[#0D0221]/60 dark:text-white/60 mt-2">
                Apenas 1 arquivo por envio • Preservação UTF-8 garantida
              </p>
            </div>

            {/* Feedback Visual de Formato Aceito / Rejeitado */}
            {selectedFile && (
              <div
                aria-live="polite"
                className={`rounded-xl p-4 border flex items-center justify-between gap-3 ${
                  selectedFile.status === "accepted"
                    ? "bg-emerald-500/10 border-emerald-600/40 text-emerald-950 dark:text-emerald-100"
                    : selectedFile.status === "rejected"
                    ? "bg-red-500/10 border-red-500/40 text-red-950 dark:text-red-100"
                    : "bg-[#335C67]/10 border-[#335C67]/30 text-[#0D0221] dark:text-white"
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
                    <p className="text-xs font-bold truncate" title={selectedFile.name}>
                      {selectedFile.name}
                    </p>
                    <p className="text-[11px] opacity-80">
                      {selectedFile.status === "accepted" &&
                        `Formato ${selectedFile.extension.toUpperCase()} aceito • ${formatFileSize(selectedFile.sizeBytes)}`}
                      {selectedFile.status === "rejected" &&
                        `Formato ou arquivo rejeitado (${selectedFile.extension}) — Tente novamente`}
                      {selectedFile.status === "uploading" && "Extraindo e sanitizando em memória..."}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-white/80 dark:bg-white/10 hover:bg-white transition-colors flex-shrink-0"
                >
                  <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                  Nova tentativa
                </button>
              </div>
            )}

            {/* Resumo da Extração e Sanitização de PII (quando retornado pelo Backend) */}
            {serverMetadata && (
              <div className="rounded-xl bg-[#F5EDF0]/70 dark:bg-white/5 border border-[#335C67]/20 p-4 space-y-2">
                <p className="text-xs font-bold uppercase tracking-wider text-[#335C67] dark:text-[#E35336]">
                  Diagnóstico de Processamento em Memória
                </p>
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2 rounded-lg bg-white dark:bg-[#0D0221]/60">
                    <dt className="opacity-70">Origem</dt>
                    <dd className="font-mono font-bold uppercase">{serverMetadata.source_type}</dd>
                  </div>
                  <div className="p-2 rounded-lg bg-white dark:bg-[#0D0221]/60">
                    <dt className="opacity-70">Sanitização LGPD</dt>
                    <dd className="font-bold text-emerald-700 dark:text-emerald-400">
                      {serverMetadata.sanitized
                        ? `${serverMetadata.pii_removed_count} PII descartado(s)`
                        : "Sem PII detectado"}
                    </dd>
                  </div>
                </dl>
              </div>
            )}
          </section>

          {/* COLUNA 2: Área Acessível de Colagem Direta e Conferência Imediata (`textarea`) */}
          <section
            aria-labelledby="heading-textarea-conferencia"
            className="lg:col-span-7 bg-white dark:bg-[#160A30] border border-[#335C67]/20 dark:border-white/15 rounded-2xl p-6 shadow-sm flex flex-col space-y-4 hc-surface"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <label
                  htmlFor={textareaId}
                  id="heading-textarea-conferencia"
                  className="text-lg font-bold text-[#0D0221] dark:text-white flex items-center gap-2 cursor-pointer"
                >
                  <ClipboardPaste className="w-5 h-5 text-[#E35336]" aria-hidden="true" />
                  Colagem Direta e Conferência do Material
                </label>
                <p className="text-xs text-[#0D0221]/70 dark:text-white/70 mt-0.5">
                  Cole o texto da sua atividade abaixo ou confira/edite o conteúdo extraído do documento enviado.
                </p>
              </div>

              {serverMetadata?.filename && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-800 dark:text-emerald-200">
                  <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                  Extraído de: {serverMetadata.filename}
                </span>
              )}
            </div>

            {/* Textarea Acessível (WCAG 2.1 AA) */}
            <div className="relative">
              <textarea
                id={textareaId}
                value={textContent}
                onChange={(e) => {
                  setTextContent(e.target.value);
                  setConfirmedForStep2(false);
                }}
                rows={13}
                placeholder="Cole aqui os textos de apoio, enunciados e alternativas da atividade ou faça upload de um arquivo (.pdf, .docx, .txt) ao lado..."
                aria-invalid={textContent.length > 0 && (!metrics.meetsMinimum || metrics.exceedsSafeContext)}
                aria-describedby="contador-tempo-real-info"
                className="w-full rounded-xl bg-[#FAFAFC] dark:bg-[#0D0221]/90 border border-[#335C67]/30 dark:border-white/20 p-4 text-sm sm:text-base leading-relaxed text-[#0D0221] dark:text-[#F5EDF0] placeholder:text-[#0D0221]/40 dark:placeholder:text-white/40 focus:border-[#E35336] transition-colors resize-y font-sans"
              />
            </div>

            {/* Barra de Contadores em Tempo Real (Sem limite máximo fixo de palavras na interface) */}
            <div
              id="contador-tempo-real-info"
              aria-live="polite"
              className="rounded-xl bg-[#F5EDF0]/75 dark:bg-white/5 border border-[#335C67]/15 dark:border-white/10 p-3.5 flex flex-wrap items-center justify-between gap-4"
            >
              <div className="flex flex-wrap items-center gap-4">
                <div>
                  <span className="text-[11px] uppercase tracking-wider opacity-70 block">Caracteres</span>
                  <span className="font-mono text-sm font-bold text-[#0D0221] dark:text-white">
                    {metrics.charCount.toLocaleString("pt-BR")}
                  </span>
                </div>

                <div className="h-7 w-px bg-[#335C67]/20 dark:bg-white/15" aria-hidden="true" />

                <div>
                  <span className="text-[11px] uppercase tracking-wider opacity-70 block">Palavras</span>
                  <span className="font-mono text-sm font-bold text-[#0D0221] dark:text-white">
                    {metrics.wordCount.toLocaleString("pt-BR")}
                  </span>
                </div>

                <div className="h-7 w-px bg-[#335C67]/20 dark:bg-white/15" aria-hidden="true" />

                <div>
                  <span className="text-[11px] uppercase tracking-wider opacity-70 block">
                    Janela de Contexto IA (Estimada)
                  </span>
                  <span className="font-mono text-xs font-semibold text-[#335C67] dark:text-[#F5EDF0]">
                    ~{metrics.estimatedTokens.toLocaleString("pt-BR")} tokens{" "}
                    <span className="opacity-75">
                      ({metrics.exceedsSafeContext ? "Acima da capacidade segura" : "Dentro da capacidade segura"})
                    </span>
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
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30">
                    <AlertCircle className="w-3.5 h-3.5" aria-hidden="true" />
                    Faltam {MIN_MATERIAL_CHARS - metrics.charCount} caractere(s) (mín. {MIN_MATERIAL_CHARS})
                  </span>
                ) : metrics.exceedsSafeContext ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-red-500/15 text-red-800 dark:text-red-300 border border-red-500/30">
                    <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
                    Excede capacidade segura de processamento
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 border border-emerald-500/30">
                    <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                    Mínimo de {MIN_MATERIAL_CHARS} caracteres atingido
                  </span>
                )}
              </div>
            </div>

            {/* Rodapé de Ação Principal (Estilo Fiery Terracotta #E35336 do Figma) */}
            <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t border-[#335C67]/15 dark:border-white/10">
              <p className="text-xs text-[#0D0221]/70 dark:text-white/70">
                Ao prosseguir, o conteúdo passa pelo sanitizador local de PII (Zero-Retention) e fica disponível em memória para a Etapa 2.
              </p>

              <button
                type="button"
                disabled={!metrics.meetsMinimum || metrics.exceedsSafeContext || isProcessing}
                onClick={handleValidateAndAdvance}
                className="inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl font-bold text-sm text-white bg-[#E35336] hover:bg-[#c94429] disabled:opacity-45 disabled:cursor-not-allowed shadow-[0_8px_20px_-4px_rgba(227,83,54,0.45)] transition-all flex-shrink-0"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                    Processando em memória...
                  </>
                ) : confirmedForStep2 ? (
                  <>
                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                    Conferido! Avançar para Etapa 2
                    <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  </>
                ) : (
                  <>
                    Validar e Conferir Material
                    <ArrowRight className="w-4 h-4" aria-hidden="true" />
                  </>
                )}
              </button>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
