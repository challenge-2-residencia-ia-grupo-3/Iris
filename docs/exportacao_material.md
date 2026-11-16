# Exportação do material adaptado (PDF e DOCX)

História 2.2.3 (RF-14). O professor exporta a atividade **já aprovada** em `.pdf` (impressão econômica) ou
`.docx` (editável) para aplicar em sala.

## Rotas
| Rota | Para quê |
|---|---|
| `POST /api/v1/adaptacao/verificar-exportacao` | pré-checagem em JSON: avisa sobre possível dado pessoal e termo clínico no texto |
| `POST /api/v1/adaptacao/exportar?formato=pdf\|docx` | devolve o arquivo para download (`atividade-adaptada.pdf` / `.docx`) |

Corpo (só estes dois campos; qualquer outro é recusado): `{"titulo": "Ciências - Ciclo da água", "texto": "..."}`.
O `titulo` é opcional (padrão: "Atividade adaptada"). Limites: título até 120 caracteres, texto até 60 000.

## O que o documento tem
- **A4**, margens de 2,5 cm, corpo em **12 pt** com espaçamento **1,5**.
- **Só tons de cinza** e **fonte sem serifa** (Arial no DOCX; Helvetica-like no PDF). Sem fundo, tarja, caixa ou
  imagem: nada de bloco denso de tinta.
- **Cabeçalho genérico**: o título e uma linha em branco `Nome: ____ Data: ____` para o aluno preencher. O servidor
  nunca escreve nome de aluno nem rótulo clínico no cabeçalho.
- DOCX sem metadado de autor.

## Rótulo clínico e dado pessoal
| Onde | O que acontece |
|---|---|
| **Título** | recusado com `422` se tiver laudo, CID, diagnóstico, medicação (mesmo bloqueio da #28) ou dado pessoal (`sanitize_pii`). A mensagem não repete o que foi digitado |
| **Corpo** | **não é alterado**: é o texto que o professor aprovou. A rota de verificação só avisa (quantidade de possíveis dados pessoais e categorias clínicas) e a interface pede confirmação |

Por que o corpo não é bloqueado: uma aula de Biologia pode ter "síndrome de Down" como conteúdo legítimo, e trocar
o texto aprovado em silêncio seria pior do que avisar. Se o grupo preferir bloquear o corpo, é uma mudança em
`validar_material`.

## Sem estado (RNF-01)
A rota recebe o texto, monta o arquivo em memória, devolve os bytes e esquece (`Cache-Control: no-store`). Não usa
disco, banco, cache nem variável global; os testes provam isso.

## Frontend
`frontend/src/services/materialExport.ts` e `frontend/src/components/MaterialExportButtons.tsx`. O componente
**ainda não está ligado a nenhuma tela**: deve ser colocado na tela de revisão/aprovação das Histórias 2.2.1 e 2.2.2,
passando o texto aprovado em `texto`.

## Limites conhecidos
- O texto é tratado como texto simples (parágrafos e quebras de linha). Não há tabela, imagem nem fórmula.
- Nome de pessoa em texto corrido não é detectado automaticamente.
- Só há rota no FastAPI; o servidor de reserva (stdlib) não a oferece.
