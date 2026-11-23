# OCR de provas digitalizadas (História 1.1.3, #6)

`POST /api/v1/materials/ocr` recebe uma imagem `.png`/`.jpg` de uma prova impressa e devolve o texto bruto no mesmo formato de `MaterialResponse` (`source_type: "image"`), mais `ocr`, `analise_visual` e `imagem`. O OCR só extrai texto (DEP-OC-01): a estrutura de questões continua com o `StructuralDecomposer`.

## Requisição
`multipart/form-data` com o campo `file` (até 10 MB). Resposta com `Cache-Control: no-store`.

## Zero retenção
A imagem é lida em memória, enviada ao Tesseract por stdin e descartada. Nada é gravado em disco (o parser multipart usa buffer em memória). O texto passa por `sanitize_pii` antes de sair.

## Recusas (`detail.code`)
| Código | HTTP | Motivo |
|---|---|---|
| EMPTY_IMAGE | 422 | arquivo vazio |
| IMAGE_TOO_LARGE | 413 | acima de 10 MB ou 50 MP |
| UNSUPPORTED_IMAGE_FORMAT | 415 | não é PNG/JPEG |
| CORRUPT_IMAGE | 422 | não foi possível abrir |
| IMAGE_RESOLUTION_TOO_LOW | 422 | menor lado < 400 px ou < 400 mil pixels |
| IMAGE_TOO_DARK / IMAGE_NO_CONTRAST / IMAGE_TOO_BLURRY | 422 | imagem sem condição de leitura |
| NO_TEXT_DETECTED | 422 | nenhum texto (ou menos de 5 palavras) |
| ILLEGIBLE_TEXT | 422 | confiança média < 45 |
| TEXT_TOO_SHORT | 422 | menos de 50 caracteres após limpeza |
| OCR_ENGINE_UNAVAILABLE / OCR_LANGUAGE_UNAVAILABLE | 503 | Tesseract ou idioma `por` ausente |
| OCR_TIMEOUT | 504 | tempo excedido |

Confiança entre 45 e 70 gera o aviso `LOW_CONFIDENCE` (o texto é devolvido, com pedido de conferência).

## Indicador de densidade visual
`analise_visual` usa apenas numpy/PIL: densidade de bordas, proporção de pixels coloridos e cobertura de blocos, combinadas em um escore (`baixa`/`media`/`alta`). `indicador_poluicao` é verdadeiro no nível alto e traz `mensagem`. É um aviso, nunca bloqueia.

**Limitação:** os limiares foram calibrados em páginas sintéticas, não em provas reais. É uma estimativa para o docente conferir, não um laudo. Revisar com amostras reais antes de tratar o resultado como definitivo.

## Instalação do motor
- macOS: `brew install tesseract tesseract-lang`
- Ubuntu/CI: `sudo apt-get install tesseract-ocr tesseract-ocr-por`

Variáveis: `IRIS_OCR_BIN` (caminho do executável), `IRIS_OCR_LANG` (padrão `por`), `IRIS_OCR_TIMEOUT` (padrão 90 s). Sem Tesseract, os testes que dependem dele são ignorados.
