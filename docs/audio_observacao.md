# Observação pedagógica por voz (História 1.2.3 — Issue #10)

Na Etapa 2 o professor pode **gravar (até 60 s) ou enviar um áudio** descrevendo o aluno. A Íris transcreve a fala,
sugere características do catálogo e **o professor confirma ou desmarca livremente** antes de seguir.

## Endpoints

| Método | Rota | Corpo | Uso |
|---|---|---|---|
| POST | `/api/v1/audio/transcribe` | `multipart/form-data`, campo `file`; query opcional `id_catalogo` | áudio → transcrição + sugestões |
| POST | `/api/v1/audio/suggest` | JSON `{texto, id_catalogo?}` | recalcula sugestões após o professor corrigir a transcrição |

Resposta: `status`, `transcricao`, `pii_substituicoes`, `avisos`, `id_catalogo`, `sugestoes[]`
(`id_caracteristica`, `nome`, `pontuacao`, `confianca`, `evidencias`), `duracao_segundos`, `formato`.
Erros: `{status:"error", code, field, detail}`.

## Limites

- Formatos: WAV, WebM, Ogg, MP4/M4A (detectados pelos bytes, não pela extensão).
- Duração: 0,5 s a 60 s (+1 s de tolerância). WAV tem a duração conferida também pelo tamanho, então cabeçalho adulterado não passa.
- Tamanho: até 12 MB.

| code | HTTP | Quando |
|---|---|---|
| EMPTY_AUDIO | 422 | arquivo vazio |
| AUDIO_TOO_LARGE | 413 | acima de 12 MB |
| UNSUPPORTED_AUDIO | 415 | formato não reconhecido |
| CORRUPT_AUDIO | 422 | não decodifica |
| AUDIO_TOO_LONG / AUDIO_TOO_SHORT | 422 | fora de 0,5–60 s |
| NO_SPEECH_DETECTED | 422 | sem fala |
| STT_UNAVAILABLE / STT_MODEL_UNAVAILABLE / DECODER_UNAVAILABLE | 503 | motor ou decodificador ausente |

## Privacidade (RNF-01, RNF-02, RNF-03)

- O áudio é processado **somente em memória**: sem arquivo temporário, banco ou log. Nada é guardado no navegador.
  O formulário é lido por um leitor próprio (`_MultipartEmMemoria`), porque o `UploadFile` padrão grava em disco
  qualquer envio acima de 1 MB; o corpo é cortado em 12 MB + 64 KB antes de chegar à memória.
- A transcrição passa pelo removedor de dados pessoais antes do mapeador.
- Termos clínicos (diagnóstico, laudo, medicação) geram aviso e **nunca** viram sugestão: só comportamento observável conta.
- A resposta vai com `Cache-Control: no-store`.

## Instalação do motor de voz

O reconhecimento é local (faster-whisper) e é dependência **opcional**:

```bash
pip install faster-whisper
```

Na primeira transcrição o modelo é baixado (precisa de internet nesse momento). Variáveis:
`IRIS_STT_MODEL` (padrão `small`), `IRIS_STT_DEVICE`, `IRIS_STT_COMPUTE`, `IRIS_STT_OFFLINE=1` (só usa modelo já baixado).
Sem o pacote, o endpoint responde 503 e a tela avisa que dá para selecionar manualmente. O motor é trocável via `definir_transcritor`.

## Como as sugestões são geradas

Léxico determinístico e explicável (sem LLM): cada característica tem termos fortes (peso 2) e fracos (peso 1);
sugere-se com pontuação ≥ 2, no máximo 4, com confiança `alta` (≥ 4) ou `media`. A evidência é o trecho literal que o professor disse.
Um teste garante que o léxico cobre todas as características do catálogo.

## Limitações

- A precisão do mapeador em fala real de professores ainda não foi medida; as frases de teste foram escritas pela equipe.
- Nome próprio dito sem "o aluno" pode escapar do removedor por regex; a transcrição é só exibida, nunca gravada nem repassada.
- Em WAV a validação usa só a biblioteca padrão; WebM/Ogg/MP4 exigem `av` (instalado junto do faster-whisper).
