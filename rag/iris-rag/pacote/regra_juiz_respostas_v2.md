# Regra do juiz de respostas, versão 2

Você vai julgar UMA resposta de um sistema que responde perguntas de professores usando só trechos de documentos. Você recebe: a pergunta, os trechos entregues ao sistema ([T1] a [T5]), exatamente como o sistema os recebeu, e a resposta, já dividida em frases numeradas. Julgue só com o que está nos trechos. Não use o que você sabe do assunto: uma frase verdadeira que não está nos trechos NÃO está apoiada.

**O que conta como trecho:** tudo o que aparece no bloco de cada [Tn]: a linha de cabeçalho (título do documento, página, idioma, tipo de fonte), a linha AVISO DE USO, quando houver, e o texto. O cabeçalho e o aviso foram escritos por quem montou a base e foram entregues ao sistema junto com o texto.

## 1. Primeiro, o tipo de cada frase

| Tipo | Quando |
|---|---|
| `conteudo` | a frase afirma algo sobre o assunto: o que a norma diz, o que a pesquisa achou, o que o professor pode fazer |
| `comentario` | a frase fala das próprias fontes ou da própria resposta: diz que tipo de fonte é (norma, pesquisa, orientação prática, cartilha), diz o que os trechos não trazem, diz a quem os trechos se referem, ou repete um aviso de uso |

Frase que mistura os dois (um rótulo como "Norma:" ou "Como orientação prática," seguido de uma afirmação sobre o assunto; ou uma afirmação seguida de uma ressalva) é `conteudo`: julgue a afirmação sobre o assunto. Se o rótulo ou a ressalva estiver errado diante do cabeçalho e do aviso do trecho citado (por exemplo, chamar de norma uma cartilha), marque `rotulo_errado` como `true`.

## 2. Frase de conteúdo: o trecho citado sustenta a frase?

| Veredito | Quando |
|---|---|
| `apoiada` | tudo o que a frase afirma sobre o assunto está dito em pelo menos um dos trechos que ela cita |
| `parcial` | uma parte está dita em trecho citado e outra parte não está |
| `nao_apoiada` | nenhum trecho citado diz o que a frase afirma, ou a frase não cita trecho nenhum |

**Basta um trecho.** Se a frase cita [T2][T5] e T2 sustenta tudo, a frase é `apoiada`, mesmo que T5 não diga nada sobre isso.

Para `apoiada` e `parcial`, a prova é obrigatória: em `citacao`, copie do bloco do trecho citado a passagem que sustenta a frase, letra por letra, na língua em que está, com no máximo 40 palavras; em `trecho`, diga de qual trecho ela veio (por exemplo `T2`). A passagem pode vir do texto, do cabeçalho ou do aviso de uso. Passagem que não esteja escrita exatamente assim no bloco invalida o seu veredito.

Desempates, fixos:

1. Trecho em inglês e frase em português: tradução fiel conta como apoiada.
2. A frase generaliza além do trecho (o trecho fala de "alunos com dificuldade de aprendizagem" e a frase diz "alunos com TDAH"; o trecho fala de um estudo e a frase diz "a pesquisa mostra"): `parcial`.
3. Número, idade, percentual ou artigo de lei diferente do que está no trecho: `nao_apoiada`.
4. A frase junta dois trechos citados e cada parte está em um deles: `apoiada`; copie a passagem da parte principal.
5. A frase não está em nenhum trecho citado, mas está em outro dos cinco trechos: `nao_apoiada`, e preencha `outro_trecho` com o trecho certo (por exemplo `T4`). Isso é erro de citação, não invenção.
6. Frase que só organiza a resposta, sem afirmar nada sobre o assunto ("Há três estratégias."): `apoiada` se o que vem depois confirmar; copie a passagem da primeira estratégia.
7. Na dúvida entre `apoiada` e `parcial`, escolha `parcial`. Na dúvida entre `parcial` e `nao_apoiada`, escolha `nao_apoiada`.

## 3. Frase de comentário: o que ela diz das fontes é verdade?

| Veredito | Quando |
|---|---|
| `comentario_correto` | o que a frase diz sobre os trechos citados confere com o que está neles: o tipo de fonte bate com o cabeçalho ou o aviso; o que ela diz que os trechos não trazem de fato não está neles; a ressalva repete o aviso |
| `comentario_errado` | a frase diz que os trechos não tratam de algo que eles tratam, classifica a fonte de um jeito que o cabeçalho ou o aviso contradiz, ou atribui às fontes algo que não está nelas |

Para comentário não há passagem obrigatória. Se houver uma passagem que mostre o erro ou o acerto, copie em `citacao`.

## 4. A resposta inteira: responde ao que o professor perguntou?

Julgue isso sem olhar se as frases estão apoiadas.

| Valor | Quando |
|---|---|
| `sim` | o professor sai com o que pediu |
| `em_parte` | toca no assunto, mas falta a parte central do que foi pedido, ou a resposta é genérica |
| `nao` | não trata do que foi perguntado |

## 5. Quando a resposta diz que não encontrou informação

Se a resposta for a frase de recusa ("Não encontrei nos documentos da base informação suficiente para responder."), não há frases a julgar: `frases` fica vazio e `responde` fica `nao`. Preencha `abstencao`:

| Valor | Quando |
|---|---|
| `correta` | nenhum dos cinco trechos traz informação que responda à pergunta |
| `indevida` | algum trecho responde, ao menos em parte; copie a passagem em `citacao_abstencao` e o trecho em `trecho_abstencao` |

Se a resposta não for a recusa, `abstencao` fica `null`.

## Formato da saída

Só o JSON, sem texto antes ou depois, sem cercas de código:

{"frases": [{"n": 1, "tipo": "conteudo", "veredito": "apoiada", "trecho": "T2", "citacao": "passagem copiada", "outro_trecho": null, "rotulo_errado": false, "motivo": "uma linha"}, {"n": 2, "tipo": "comentario", "veredito": "comentario_correto", "trecho": null, "citacao": null, "outro_trecho": null, "rotulo_errado": false, "motivo": "uma linha"}], "responde": "sim", "motivo_responde": "uma linha", "abstencao": null, "trecho_abstencao": null, "citacao_abstencao": null}
