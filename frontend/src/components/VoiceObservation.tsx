"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Mic, Square, Upload, X } from "lucide-react";
import {
  escolherMimeType,
  extensaoDoMime,
  formatarTempo,
  MAX_SEGUNDOS,
  ResultadoVoz,
  sugerirDeTexto,
  transcreverAudio,
  validarArquivoLocal,
  VoiceError,
} from "@/services/voiceObservation";

interface Props {
  /** Ids já marcados na Etapa 2 (aparecem como "já selecionada"). */
  jaSelecionadas: string[];
  /** Chamado só quando o professor clica em confirmar, com os ids que ele deixou marcados. */
  onConfirm: (ids: string[]) => void;
}

type Fase = "ocioso" | "gravando" | "enviando" | "resultado";

const BTN = "inline-flex min-h-[44px] items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold transition-colors disabled:opacity-60 disabled:pointer-events-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E35336] focus-visible:ring-offset-2";
const BTN_PRIMARIO = `${BTN} bg-[#0D0221] text-white hover:bg-[#2a1850] dark:bg-white dark:text-[#0D0221] dark:hover:bg-white/90`;
const BTN_SECUNDARIO = `${BTN} border border-[#335C67]/50 bg-white text-[#0D0221] hover:bg-[#F5EDF0] dark:border-white/30 dark:bg-white/10 dark:text-white dark:hover:bg-white/20`;
const BTN_GRAVAR = `${BTN} bg-[#B91C1C] text-white hover:bg-[#991B1B]`;

/**
 * Observação por voz na Etapa 2 (História 1.2.3): o professor grava (até 60 s) ou envia um áudio, vê a transcrição
 * (que pode corrigir) e as características sugeridas já marcadas. Só depois de confirmar elas entram na seleção, e
 * a seleção da Etapa 2 continua livre para marcar e desmarcar. O áudio não é guardado no navegador.
 */
export function VoiceObservation({ jaSelecionadas, onConfirm }: Props) {
  const [fase, setFase] = useState<Fase>("ocioso");
  const [segundos, setSegundos] = useState(0);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoVoz | null>(null);
  const [texto, setTexto] = useState("");
  const [marcadas, setMarcadas] = useState<string[]>([]);
  const [atualizando, setAtualizando] = useState(false);
  const [podeGravar, setPodeGravar] = useState(false);
  const [aviso, setAviso] = useState<string>("");

  const idArquivo = useId();
  const idTexto = useId();
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const pedacos = useRef<Blob[]>([]);
  const relogio = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelado = useRef(false);
  const tituloResultado = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    setPodeGravar(
      typeof window !== "undefined" &&
        typeof MediaRecorder !== "undefined" &&
        !!navigator.mediaDevices?.getUserMedia &&
        escolherMimeType((m) => MediaRecorder.isTypeSupported(m)) !== null
    );
  }, []);

  const liberarMicrofone = useCallback(() => {
    if (relogio.current) clearInterval(relogio.current);
    relogio.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  useEffect(
    () => () => {
      cancelado.current = true;
      if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
      liberarMicrofone();
      pedacos.current = [];
    },
    [liberarMicrofone]
  );

  const aplicarResultado = (r: ResultadoVoz) => {
    setResultado(r);
    setTexto(r.transcricao);
    setMarcadas(r.sugestoes.map((s) => s.id_caracteristica));
    setFase("resultado");
  };

  useEffect(() => {
    if (fase === "resultado") tituloResultado.current?.focus();
  }, [fase]);

  const enviar = useCallback(async (audio: Blob, nome: string) => {
    setFase("enviando");
    setErro(null);
    try {
      aplicarResultado(await transcreverAudio(audio, nome));
    } catch (e) {
      setErro(e instanceof VoiceError ? e.message : "Não foi possível transcrever o áudio.");
      setFase("ocioso");
    }
  }, []);

  const iniciarGravacao = async () => {
    setErro(null);
    setAviso("");
    const mime = escolherMimeType((m) => MediaRecorder.isTypeSupported(m));
    if (!mime) return;
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setErro("Não consegui acessar o microfone. Libere a permissão no navegador ou envie um arquivo de áudio.");
      return;
    }
    cancelado.current = false;
    pedacos.current = [];
    const rec = new MediaRecorder(stream.current, { mimeType: mime });
    recorder.current = rec;
    rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) pedacos.current.push(ev.data);
    };
    rec.onstop = () => {
      liberarMicrofone();
      const blob = new Blob(pedacos.current, { type: rec.mimeType || mime });
      pedacos.current = [];
      if (cancelado.current) {
        setFase("ocioso");
        return;
      }
      void enviar(blob, `observacao.${extensaoDoMime(blob.type || mime)}`);
    };
    setSegundos(0);
    rec.start();
    setFase("gravando");
    setAviso("Gravando. Fale a dificuldade observada no aluno. A gravação para sozinha em 60 segundos.");
    relogio.current = setInterval(() => {
      setSegundos((s) => {
        const prox = s + 1;
        if (prox >= MAX_SEGUNDOS && recorder.current && recorder.current.state === "recording") recorder.current.stop();
        return prox;
      });
    }, 1000);
  };

  const pararEEnviar = () => {
    if (recorder.current && recorder.current.state === "recording") recorder.current.stop();
  };

  const cancelarGravacao = () => {
    cancelado.current = true;
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    else {
      liberarMicrofone();
      setFase("ocioso");
    }
    setAviso("Gravação descartada.");
  };

  const aoEscolherArquivo = (ev: React.ChangeEvent<HTMLInputElement>) => {
    const arq = ev.target.files?.[0];
    ev.target.value = "";
    if (!arq) return;
    const problema = validarArquivoLocal(arq);
    if (problema) {
      setErro(problema);
      return;
    }
    void enviar(arq, arq.name);
  };

  const atualizarSugestoes = async () => {
    setAtualizando(true);
    setErro(null);
    try {
      const r = await sugerirDeTexto(texto);
      setResultado(r);
      setMarcadas(r.sugestoes.map((s) => s.id_caracteristica));
    } catch (e) {
      setErro(e instanceof VoiceError ? e.message : "Não foi possível atualizar as sugestões.");
    } finally {
      setAtualizando(false);
    }
  };

  const alternar = (id: string) => setMarcadas((m) => (m.includes(id) ? m.filter((x) => x !== id) : [...m, id]));

  const descartar = () => {
    setResultado(null);
    setTexto("");
    setMarcadas([]);
    setErro(null);
    setFase("ocioso");
    setAviso("Observação descartada.");
  };

  const confirmar = () => {
    onConfirm(marcadas);
    descartar();
    setAviso(`${marcadas.length} característica(s) aplicada(s) à seleção. Revise abaixo e desmarque o que não se aplica.`);
  };

  return (
    <section
      aria-labelledby={`${idArquivo}-titulo`}
      className="space-y-3 rounded-2xl border border-[#335C67]/30 bg-[#F5EDF0]/50 p-4 text-[#0D0221] dark:border-white/15 dark:bg-[#160A30]/80 dark:text-white"
    >
      <div className="space-y-1">
        <h2 id={`${idArquivo}-titulo`} className="flex items-center gap-2 text-sm font-extrabold">
          <Mic className="h-4 w-4" aria-hidden="true" /> Observação por voz
        </h2>
        <p className="text-xs text-[#0D0221]/80 dark:text-white/80">
          Conte em até {MAX_SEGUNDOS} segundos a dificuldade que você observa no aluno. A Íris transcreve e sugere as características; você confirma ou
          desmarca. O áudio não é guardado. Evite citar o nome do aluno.
        </p>
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {aviso}
      </p>

      {fase === "ocioso" && (
        <div className="flex flex-wrap items-center gap-3">
          {podeGravar ? (
            <button type="button" onClick={iniciarGravacao} className={BTN_GRAVAR}>
              <Mic className="h-4 w-4" aria-hidden="true" /> Gravar observação
            </button>
          ) : (
            <p className="text-xs text-[#0D0221]/80 dark:text-white/80">Este navegador não grava áudio. Envie um arquivo de áudio.</p>
          )}
          <label htmlFor={idArquivo} className={`${BTN_SECUNDARIO} cursor-pointer`}>
            <Upload className="h-4 w-4" aria-hidden="true" /> Enviar áudio gravado
          </label>
          <input id={idArquivo} type="file" accept="audio/*,.wav,.webm,.ogg,.m4a,.mp4" onChange={aoEscolherArquivo} className="sr-only" />
        </div>
      )}

      {fase === "gravando" && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2 text-sm font-bold" role="timer" aria-label="Tempo gravado">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[#B91C1C]" aria-hidden="true" />
            {formatarTempo(segundos)} / {formatarTempo(MAX_SEGUNDOS)}
          </span>
          <button type="button" onClick={pararEEnviar} className={BTN_PRIMARIO}>
            <Square className="h-4 w-4" aria-hidden="true" /> Parar e transcrever
          </button>
          <button type="button" onClick={cancelarGravacao} className={BTN_SECUNDARIO}>
            <X className="h-4 w-4" aria-hidden="true" /> Cancelar
          </button>
        </div>
      )}

      {fase === "enviando" && (
        <p role="status" className="flex items-center gap-2 text-sm font-semibold">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Transcrevendo e buscando as características…
        </p>
      )}

      {erro && (
        <p role="alert" className="flex items-start gap-2 rounded-xl bg-[#FFF1DC] px-3 py-2 text-sm font-semibold text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {erro}
        </p>
      )}

      {fase === "resultado" && resultado && (
        <div className="space-y-4">
          <h3 ref={tituloResultado} tabIndex={-1} className="text-sm font-extrabold focus:outline-none">
            O que a Íris entendeu
          </h3>

          {resultado.avisos.map((a) => (
            <p key={a.code} role="note" className="rounded-xl bg-[#FFF1DC] px-3 py-2 text-xs font-semibold text-[#5C2A00] dark:bg-[#4A2A08] dark:text-[#FFE2B8]">
              {a.detail}
            </p>
          ))}

          <div className="space-y-1">
            <label htmlFor={idTexto} className="text-xs font-bold uppercase tracking-wide">
              Transcrição (corrija se precisar)
            </label>
            <textarea
              id={idTexto}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={4}
              className="w-full rounded-xl border border-[#335C67]/50 bg-white p-2.5 text-sm text-[#0D0221] dark:border-white/30 dark:bg-[#0D0221] dark:text-white"
            />
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={atualizarSugestoes} disabled={atualizando || !texto.trim()} className={BTN_SECUNDARIO}>
                {atualizando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Atualizar sugestões
              </button>
              {resultado.pii_substituicoes > 0 && (
                <span className="text-xs text-[#0D0221]/80 dark:text-white/80">
                  {resultado.pii_substituicoes} dado(s) pessoal(is) foram trocados por marcadores.
                </span>
              )}
            </div>
          </div>

          {resultado.sugestoes.length === 0 ? (
            <p role="status" className="text-sm">
              Não identifiquei nenhuma característica nesse relato. Você pode descrever com outras palavras, ou fechar e selecionar as características
              manualmente na lista.
            </p>
          ) : (
            <fieldset className="space-y-2">
              <legend className="text-xs font-bold uppercase tracking-wide">Características sugeridas (desmarque o que não se aplica)</legend>
              <ul className="space-y-2">
                {resultado.sugestoes.map((s) => {
                  const id = `${idArquivo}-${s.id_caracteristica}`;
                  return (
                    <li key={s.id_caracteristica} className="rounded-xl border border-[#335C67]/30 bg-white p-3 dark:border-white/20 dark:bg-[#0D0221]/60">
                      <div className="flex items-start gap-3">
                        <input
                          id={id}
                          type="checkbox"
                          checked={marcadas.includes(s.id_caracteristica)}
                          onChange={() => alternar(s.id_caracteristica)}
                          className="mt-1 h-5 w-5 shrink-0 accent-[#B3401E]"
                        />
                        <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
                          <span className="block text-sm font-bold">{s.nome}</span>
                          <span className="block text-xs text-[#0D0221]/80 dark:text-white/80">
                            Confiança {s.confianca === "alta" ? "alta" : "média"}
                            {jaSelecionadas.includes(s.id_caracteristica) ? " · já está selecionada" : ""}
                          </span>
                          {s.evidencias.length > 0 && (
                            <span className="mt-1 block break-words text-xs italic">
                              Você disse: {s.evidencias.map((e) => `“${e}”`).join(", ")}
                            </span>
                          )}
                        </label>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </fieldset>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={confirmar} disabled={marcadas.length === 0} className={BTN_PRIMARIO}>
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> Confirmar {marcadas.length > 0 ? `${marcadas.length} sugestão(ões)` : "sugestões"}
            </button>
            <button type="button" onClick={descartar} className={BTN_SECUNDARIO}>
              <X className="h-4 w-4" aria-hidden="true" /> Descartar
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
