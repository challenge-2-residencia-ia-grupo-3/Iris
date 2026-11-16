# Revisão docente e homologação (História 2.2.2)

O professor é a autoridade pedagógica: edita qualquer palavra da versão sugerida pela IA, aprova questão por questão e confirma a revisão no fim. **O arquivo final só é gerado depois dessa confirmação** (Human-in-the-Loop obrigatório, RF-13 e RNF-09).

## Endpoints (`/api/v1`)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/sessions` | Abre a sessão em memória com as questões `{id?, original?, adaptado}` |
| `GET` | `/sessions/{id}` | Estado: versão final, aprovações, `pode_homologar`, `pode_exportar` |
| `PUT` | `/sessions/{id}/review` | Grava edições (`adaptado`), aprovação por questão (`aprovada`) e `homologar` |
| `POST` | `/sessions/{id}/verify-export` | Avisa sobre possível dado pessoal ou termo clínico no texto |
| `POST` | `/sessions/{id}/export?formato=pdf\|docx` | Gera o arquivo. **409 `EXPORT_BLOCKED`** sem homologação |
| `DELETE` | `/sessions/{id}` | Descarta a sessão |

## Regras (todas no servidor)

- Editar uma questão aprovada **tira a aprovação dela e revoga a homologação**.
- Desaprovar qualquer questão depois de homologar também revoga.
- Homologar exige **todas** as questões aprovadas (`409 NOT_ALL_APPROVED`).
- Não existe parâmetro para pular a homologação na exportação.
- A revisão é "tudo ou nada": se um item for inválido, nada é aplicado.
- O texto original nunca muda; o corpo do professor não é alterado pelo servidor.

## Memória e privacidade

As sessões vivem só na memória do processo: expiram após 2 h sem uso, no máximo 200 simultâneas, e nada é gravado em disco, banco ou rede. Reiniciar o servidor descarta todas. Com mais de um processo/worker, cada um tem a sua memória: para essa fase, rodar com um único worker.

## Front

`services/reviewState.ts` (regras puras), `services/sessionReview.ts` (cliente) e `components/ReviewEditor.tsx` (edição inline, aprovar por questão, "Confirmar revisão final", exportar). O editor salva sozinho (600 ms depois de parar de digitar) e só libera a exportação com tudo salvo e homologado. Ainda não está ligado a uma página: depende da tela lado a lado (#21).
