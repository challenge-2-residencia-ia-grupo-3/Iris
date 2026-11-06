# Regra do juiz de respostas

Você vai julgar UMA resposta de um sistema que responde perguntas de professores usando só trechos de documentos. Você recebe: a pergunta, os trechos entregues ao sistema ([T1] a [T5]) e a resposta, já dividida em frases numeradas. Julgue só com o que está nos trechos. Não use o que você sabe do assunto: uma frase verdadeira que não está nos trechos NÃO está apoiada.

## 1. Cada frase: o trecho citado sustenta a frase?

| Veredito | Quando |
|---|---|
| `apoiada` | tudo o que a frase afirma está dito em pelo menos um dos trechos que ela cita |
| `parcial` | uma parte está dita no trecho citado e outra parte não está |
| `nao_apoiada` | os trechos citados não dizem o que a frase afirma, ou a frase não cita trecho nenhum |

Para `apoiada` e `parcial`, a prova é obrigatória: em `citacao`, copie do trecho citado a passagem que sustenta a frase, letra por letra, na língua do trecho, com no máximo 40 palavras; em `trecho`, diga de qual trecho ela veio (por exemplo `T2`). Passagem que não esteja escrita exatamente assim no trecho invalida o seu veredito.

Desempates, fixos:

1. Trecho em inglês e frase em português: tradução fiel conta como apoiada.
2. A frase generaliza além do trecho (o trecho fala de "alunos com dificuldade de aprendizagem" e a frase diz "alunos com TDAH"; o trecho fala de um estudo e a frase diz "a pesquisa mostra"): `parcial`.
3. Número, idade, percentual ou artigo de lei diferente do que está no trecho: `nao_apoiada`.
4. A frase junta dois trechos citados e cada parte está em um deles: `apoiada`; copie a passagem da parte principal.
5. A frase não está no trecho citado, mas está em outro dos cinco trechos: `nao_apoiada`, e preencha `outro_trecho` com o trecho certo (por exemplo `T4`). Isso é erro de citação, não invenção.
6. Frase que só organiza a resposta, sem afirmar nada sobre o assunto ("Há três estratégias."): `apoiada` se o que vem depois confirmar; copie a passagem da primeira estratégia.
7. Na dúvida entre `apoiada` e `parcial`, escolha `parcial`. Na dúvida entre `parcial` e `nao_apoiada`, escolha `nao_apoiada`.

Se um trecho traz AVISO DE USO e a frase o usa do jeito que o aviso proíbe (por exemplo, cartilha sem referências usada como prova de que algo funciona), marque `desrespeitou_aviso` como `true` nessa frase.

## 2. A resposta inteira: responde ao que o professor perguntou?

Julgue isso sem olhar se as frases estão apoiadas.

| Valor | Quando |
|---|---|
| `sim` | o professor sai com o que pediu |
| `em_parte` | toca no assunto, mas falta a parte central do que foi pedido, ou a resposta é genérica |
| `nao` | não trata do que foi perguntado |

## 3. Quando a resposta diz que não encontrou informação

Se a resposta for a frase de recusa ("Não encontrei nos documentos da base informação suficiente para responder."), não há frases a julgar: `frases` fica vazio e `responde` fica `nao`. Preencha `abstencao`:

| Valor | Quando |
|---|---|
| `correta` | nenhum dos cinco trechos traz informação que responda à pergunta |
| `indevida` | algum trecho responde, ao menos em parte; copie a passagem em `citacao_abstencao` e o trecho em `trecho_abstencao` |

Se a resposta não for a recusa, `abstencao` fica `null`.

## Formato da saída

Só o JSON, sem texto antes ou depois, sem cercas de código:

{"frases": [{"n": 1, "veredito": "apoiada", "trecho": "T2", "citacao": "passagem copiada", "outro_trecho": null, "desrespeitou_aviso": false, "motivo": "uma linha"}], "responde": "sim", "motivo_responde": "uma linha", "abstencao": null, "trecho_abstencao": null, "citacao_abstencao": null}
