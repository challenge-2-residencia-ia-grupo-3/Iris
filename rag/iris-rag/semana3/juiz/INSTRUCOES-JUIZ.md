# Instruções para o juiz (semana 3)

Você vai julgar respostas de um assistente para professores e adaptações de questões escolares.
Não sabe, e não deve tentar adivinhar, qual sistema gerou cada uma. Julgue cada linha sozinha.

Há dois tipos de arquivo:

- `resp-lote-NN.jsonl`: respostas a perguntas de professores sobre TDAH, adaptação de atividades,
  normas e evidências (campo `tipo_tarefa` = `resposta_ao_professor`).
- `adapt-lote-NN.jsonl`: adaptações de questões escolares para um aluno com dificuldade de seguir
  comandos múltiplos (campo `tipo_tarefa` = `adaptacao_de_questao`).

Cada critério tem resposta **sim** ou **não**. "Parcial" só existe em `util` e só com justificativa
escrita. Na dúvida entre sim e não, escolha a resposta mais conservadora (a que não favorece a
resposta) e diga o motivo em `obs`.

## 1. Respostas ao professor (`resp-lote-*`)

Cada linha traz: `pergunta`, `trechos_da_base` (T1 a T5, ou menos: o que a base de documentos tem de
mais próximo da pergunta), `resposta` e `frases` (a resposta dividida e numerada).

Use **apenas os trechos** como referência de verdade. O que a resposta disser e não estiver nos
trechos conta como não sustentado, mesmo que você saiba que é verdade. A resposta pode ou não ter
marcas como [T1]; julgue a frase contra todos os trechos, não só o citado.

### Por frase (para cada item de `frases`)

| Campo | Pergunta | Valores |
|---|---|---|
| `sustentada` | O conteúdo da frase está dito nos trechos, no mesmo grau (sem transformar "pode" em "deve", sem acrescentar efeito, número, autor ou lei que o trecho não traz)? | sim / não |
| `contradiz` | A frase diz o contrário do que algum trecho diz? (só preencher se `sustentada` = não) | sim / não |

Frase que só anuncia (ex.: "Seguem algumas estratégias:") ou só diz que não sabe responder: marque
`sustentada` = sim.

### Por resposta

| Campo | Pergunta | Valores |
|---|---|---|
| `util` | Um professor conseguiria agir a partir desta resposta para a pergunta feita? | sim / não / parcial (com justificativa) |
| `inventou` | A resposta traz fato, número, dose, lei, autor, documento ou estudo que não está nos trechos e que parece específico (não conhecimento geral)? | sim / não |
| `absteve` | A resposta diz que não sabe ou que a base não tem a informação? | sim / não |

Respostas com `frases` = null são trechos de documento devolvidos sem reescrita. Para elas, não há
julgamento por frase: preencha só `util`, `inventou` (normalmente não) e `absteve` (não), e em `util`
pense se o professor, lendo só este texto, teria a resposta da pergunta.

### Formato da saída (uma linha JSON por resposta, no mesmo arquivo de lote, em `veredito-<lote>.jsonl`)

```json
{"id_cego": "R0001", "frases": [{"n": 1, "sustentada": "sim", "contradiz": null}, {"n": 2, "sustentada": "não", "contradiz": "não"}], "util": "sim", "inventou": "não", "absteve": "não", "obs": "frase 2 acrescenta 'sempre', o trecho diz 'pode'"}
```

## 2. Adaptações de questão (`adapt-lote-*`)

Cada linha traz: `disciplina`, `ano`, `nivel_de_apoio_pedido` (1 = destaque de termos; 2 = lista de
passos ou checklist; 3 = passo a passo explícito), `enunciado_original` e `adaptacao`.

O objetivo da adaptação é ajudar o aluno a entender e seguir o que a questão pede, sem mudar o que ela
avalia e sem resolver por ele.

| Campo | Pergunta | Valores |
|---|---|---|
| `util` | A adaptação deixa a questão mais fácil de entender e de seguir para um aluno com dificuldade em comandos múltiplos? | sim / não / parcial (com justificativa) |
| `entrega_resposta` | A adaptação dá a resposta, ou uma dica tão direta que o aluno não precisa mais pensar (efeito muleta)? | sim / não |
| `mudou_o_que_avalia` | A adaptação tirou, trocou ou facilitou o conteúdo que a questão avalia (conceito, conta, texto-base, pergunta)? | sim / não |
| `inventou` | A adaptação acrescenta informação que não está no enunciado (dado, nome, número, regra)? | sim / não |
| `nivel_respeitado` | A forma segue o nível de apoio pedido? | sim / não |

```json
{"id_cego": "R0201", "util": "sim", "entrega_resposta": "não", "mudou_o_que_avalia": "não", "inventou": "não", "nivel_respeitado": "sim", "obs": ""}
```

## 3. Regras gerais

- Não pule linhas. Se uma linha estiver quebrada ou ilegível, devolva `{"id_cego": ..., "erro": "motivo"}`.
- Não reescreva a resposta nem sugira melhoria; só julgue.
- Se for um modelo julgando: temperatura 0, um lote por vez, sem ver outros lotes. Registre o nome do
  modelo e a data no nome do arquivo de saída (ex.: `veredito-resp-lote-01-gpt-oss-120b-2026-11-13.jsonl`).
- A ficha `ficha-humana.jsonl` tem 30 respostas sorteadas dos lotes, com os mesmos `id_cego`. Uma
  pessoa preenche o campo `conferencia_humana` com o mesmo formato acima. Ela serve para medir quanto o
  juiz modelo concorda com uma pessoa; até ser preenchida, os números do juiz modelo valem como
  "juiz não validado".
