# Semana 3: LLM sozinho x RAG. Pré-registro

Escrito em 12/11/2026, **antes** de gerar qualquer resposta deste estudo. O que estiver aqui não muda
depois de ver o resultado. Mudança, se houver, entra no fim como desvio, com data e motivo, antes de
rodar a parte afetada.

Código de partida: commit `ddd29b8` do branch `ana/c2-iris-rag` (com arquivos de saída antigos
modificados e a pasta `semana3/` nova, ainda fora do git). Código do grupo: clone em `65e1f09`, só
leitura. Trechos: `pacote/chunks.jsonl` congelado (sha256 começa com `1b517d249bef1873`).

## Pergunta

Vale usar RAG no Íris? E, se vale, com ou sem LLM escrevendo a resposta? A pergunta é feita em dois
níveis: (1) o Estrategista respondendo perguntas de professor (testes A, B e C) e (2) o produto
inteiro adaptando questões escolares (teste D).

## Modelos

| Papel | Modelo | Onde roda | Por quê |
|---|---|---|---|
| Principal (a decisão usa este) | Llama 3.1 8B (`llama3.1:8b`) | Ollama local, no PC do Matheus | é o modelo de produção do Íris (`config.py` do grupo: `IRIS_LLM_MODEL` padrão `llama3.1:8b`); roda local, igual à produção |
| Comparação de tamanho | Qwen 3.8 27B (`qwen/qwen3.8-27b`) | Groq (API, plano gratuito) | modelo maior, para medir quanto o tamanho muda |

O Groq não oferece mais o Llama 3.1 8B (lista de modelos conferida em 12/11/2026 pela API:
só `qwen/qwen3.8-27b`, `gpt-oss` e `prompt-guard`). A VPS não tem memória para rodar o Llama
(7 GB de RAM, sem GPU). Por isso o Qwen roda agora na VPS pelo Groq (substituído, ver desvio de 20:40) e o Llama roda depois no PC,
com **os mesmos prompts, byte a byte**: os prompts de A e C são gravados num arquivo e o PC só os
envia ao Ollama (o PC não refaz a busca). Temperatura 0 nos dois.

Só entra no Groq material público: as 40 perguntas do gabarito (escritas pela equipe, sem dado de
aluno), trechos de documentos públicos e as 30 questões do Golden Benchmark do grupo (questões
escolares públicas, sem dado de aluno).

## Conjunto de perguntas

- A, B e C: as 40 perguntas de `gabarito/gabarito_rascunho_v0.json` (38 com trechos relevantes
  marcados; Q39 e Q40 sem resposta na base, de propósito).
- Categoria de cada pergunta, calculada pelo gabarito antes de gerar:
  - **factual**: todos os trechos de nota 2 vêm de um único documento (14 perguntas);
  - **síntese entre fontes**: trechos de nota 2 em dois ou mais documentos (24);
  - **fora da base**: sem trecho relevante (2: Q39 e Q40).
- Documento-fonte dominante: o documento com mais trechos de nota 2 na pergunta (26 documentos
  diferentes). Serve para o IC agrupado por documento.
- D: as 30 questões do Golden Benchmark do grupo (`data/golden_benchmark.json`, status "rascunho"),
  as mesmas que já estão no conjunto congelado `bancada/avaliacao/conjunto-v1.jsonl`.

## Os quatro testes

**A) LLM sozinho (sem RAG).** O mesmo modelo responde as 40 perguntas sem trechos. Prompt
equivalente ao do C: mesmo papel (Agente Estrategista do Íris, que apoia professores a adaptar
atividades para alunos com TDAH sem reduzir a habilidade avaliada), em português, no máximo 6 frases,
sem introdução nem conclusão genérica, e uma frase fixa quando não souber
("Não sei responder a isso com segurança."). Sem citação (não há trecho para citar).
3 repetições por pergunta.

**B) RAG sem LLM (só busca).** A resposta é o texto cru dos trechos que a busca padrão
(`qwen3+rerank`, top-5) traz: variante B1 = só o 1º trecho; variante B3 = os 3 primeiros.
Determinístico: 1 rodada. A busca é rodada uma vez para as 40 perguntas e os trechos ficam gravados
(`saidas/trechos_busca.jsonl`); A, C e o pacote do juiz usam esses mesmos trechos. Já foi medido
que a busca devolve o mesmo top-5, na mesma ordem, em 38 de 38 perguntas entre dias e máquinas
(`pacote/outputs/22-repeticao.txt`).

**C) RAG + LLM (o sistema atual).** O prompt `v1` de `pacote/gerar.py` (o que está em produção) com
os 5 trechos gravados, montado por `gerar.montar_prompt`. É o mesmo que `gerar.responder` faz, só
que com a busca feita uma vez antes. 3 repetições por pergunta. **A rodada C não serve para escolher
prompt**: é o sistema como está.

**D) Produto.** O Adaptador do Íris nas 30 questões do Golden Benchmark, pelo arnês da bancada
(Extrator, busca bm25, diretiva, Adaptador com laudo de escopo), nível 2, característica
"comandos múltiplos", em duas configurações: `completo` (com RAG) e `sem_rag`. 1 rodada de cada
(3 se o tempo e o limite do Groq deixarem). O arnês recusa provedor externo por padrão (trava contra
dado de aluno). Para este teste há uma liberação explícita, `BANCADA_PERMITIR_EXTERNO=benchmark-publico`,
que só libera o Groq e fica registrada no JSON de saída. Sem a variável, a recusa continua.

## Métricas

Por resposta, calculadas por código (A e C):

| Métrica | Definição |
|---|---|
| Abstenção correta | Q39 e Q40 respondidas com a frase fixa (A: "Não sei responder..."; C: a `FRASE_SEM_RESPOSTA` do `gerar.py`) |
| Cobertura | das 38 perguntas com resposta, em quantas o sistema respondeu (não se absteve) |
| Frases com citação | frases com `[Tn]` / frases (só C) |
| Citação existente | toda citação aponta para um trecho que existe (`gerar.conferir`, só C) |
| Tamanho | caracteres, palavras e frases |
| Latência | segundos da geração; no C soma-se o tempo da busca daquela pergunta |
| Tokens e custo | tokens de entrada e saída informados pela API; custo pelo preço público do Groq para o Qwen (US$ 0,80 por milhão de entrada e US$ 4,00 por milhão de saída, consultado em 12/11/2026); Llama local = US$ 0 |
| Estabilidade | entre as 3 repetições: texto idêntico? abstenção igual? |

B: recall@5, hit@5 e MRR contra o gabarito (só trechos de nota 2, como em `avaliar_opus.py`),
Flesch PT-BR do texto (função `flesch_ptbr` do grupo) e tamanho.

D (funções do grupo: `avaliar_trcc`, `analyze_question`, que traz `flesch_ptbr` e
`count_conjugated_commands`, e `verificar_aderencia_nivel`, chamadas por `semana3/teste_d.py`): retenção da trava curricular
(TRCC), comandos conjugados resolvidos, Flesch antes e depois, aderência ao nível, laudo de escopo,
taxa de reserva (o Adaptador caiu nas regras de reserva), tokens e tempo do ciclo contra o RNF-07
(40 s no nível 2).

Pelo juiz (etapa seguinte, fora deste roteiro de geração), com rubrica **binária por critério**:

- por frase: sustentada pelos trechos (sim/não); se não, se contradiz o trecho (sim/não);
- por resposta: útil (sim/não; "parcial" só com justificativa escrita); inventou fato ou fonte (sim/não);
- D, por adaptação: útil para o aluno (sim/não); entrega a resposta (efeito muleta, sim/não); mudou o
  que a questão avalia (sim/não); inventou informação (sim/não).

**Fidelidade por frase** = frases sustentadas / frases, média por pergunta (média das 3 repetições
antes, para cada pergunta pesar igual). Em A, o juiz compara as frases com os mesmos 5 trechos que
a busca traria: mede se o que o modelo diz de memória é sustentado pela base.

O juiz recebe os pacotes cegos (`juiz/`), sem saber o teste nem o modelo. 30 respostas sorteadas
(semente fixa, misturando condições) vão para uma ficha de conferência humana
(`juiz/ficha-humana.jsonl`); até a ficha ser preenchida, todo número do juiz leva o rótulo
"juiz não validado".

## Hipóteses (escritas antes)

- **H1.** RAG + LLM (C) tem mais frases sustentadas pela base que o LLM sozinho (A).
- **H2.** RAG sem LLM (B) tem menos respostas úteis que RAG + LLM (C).
- **H3.** Com RAG, o Adaptador mantém a TRCC e não piora comandos conjugados nem Flesch em relação ao
  sem RAG (D).
- **H4.** O modelo maior não muda a decisão: o vencedor é o mesmo com Llama 3.1 8B e com Qwen 3.8 27B.

## Análise estatística

- Comparações **pareadas por pergunta** (mesma pergunta em todas as condições): diferença média com
  IC 95% por bootstrap (2.000 reamostragens, semente 20261112) e teste de Wilcoxon pareado como
  complemento. "Diferença" só quando o IC exclui o zero.
- Resultado também por categoria (factual, síntese, fora da base) e com IC agrupado por documento
  dominante (bootstrap que sorteia documentos, não perguntas).
- Com 38 perguntas, uma pergunta vale 2,6 pontos; com 30 questões no D, 3,3 pontos.
- Antes de pontuar: checagem de integridade (respostas vazias, erros de API, duplicatas, faltantes),
  com a contagem gravada em `saidas/integridade.json`. Resposta com erro de API é refeita; se não
  der, fica de fora e a contagem diz quantas.

## Regra de decisão (escrita antes)

**Estrategista (A, B, C), decidida com o Llama 3.1 8B:**

1. Portões: só concorre a condição que (a) se abstém em Q39 e Q40 nas 3 repetições (6 de 6) e
   (b) tem latência p95 dentro do RNF-07 (40 s, o limite do nível 2). B não tem como se abster
   (sempre devolve trechos), então não passa no portão (a); B entra como referência de utilidade.
2. Vence a condição com maior fidelidade por frase pelo juiz.
3. Empate (IC pareado da diferença passa pelo zero): vence a mais simples e barata, nesta ordem:
   B, A, C.

**Produto (D):** H3 se confirma se, na diferença pareada `completo - sem_rag`, o limite inferior do
IC 95% fica acima de -0,05 na retenção da trava e em comandos conjugados resolvidos, e acima de
-5 pontos no Flesch. Se H3 se confirmar e o juiz não apontar mais "entrega a resposta" no
`completo`, o RAG fica no produto; se não, o relatório diz qual métrica piorou.

**H4:** aplica-se a mesma regra com o Qwen; se o vencedor mudar, a decisão continua com o Llama e a
diferença vai para a discussão.

## Expectativas (escritas antes)

- A (sem trechos) vai responder Q39 (dose de metilfenidato) com conteúdo de memória: risco alto.
- A vai ter fidelidade baixa contra os trechos, não por estar errada, mas por dizer coisas que a base
  não diz.
- C deve repetir o que já foi medido com o Qwen: fidelidade 0,95 (juiz gpt-oss) a 0,80 (juiz Haiku);
  com o Llama 8B, esperamos menos citações e mais frases sem citação.
- Temperatura 0 no Groq não garante texto idêntico entre repetições; no Ollama, com semente fixa,
  deve dar idêntico.
- D: com o Llama, a diferença entre `completo` e `sem_rag` deve ser pequena nas métricas do grupo,
  porque a diretiva do RAG muda o texto do Adaptador, mas a trava e o laudo seguram o conteúdo.

## Ordem de execução e limite do Groq

O plano gratuito do Groq para o `qwen/qwen3.8-27b` permite 8 mil tokens por minuto e 200 mil tokens
por dia (página de limites do Groq, consultada em 12/11/2026). Conta aproximada: A ≈ 120 × 0,8 mil,
C ≈ 120 × 3,5 mil, D ≈ 30 × 3,5 mil, ou seja, perto de 600 mil tokens, três dias de cota. Prazo: sexta
13/11. Por isso a ordem fica fixada agora, antes de gerar, e não depende do resultado:

1. Repetição 1 de A e de C (40 perguntas cada), intercaladas por repetição.
2. D com 1 rodada (`completo` e `sem_rag`).
3. Repetições 2 e 3 de A e C, na mesma ordem.
4. Rodadas 2 e 3 do D, se sobrar cota.

O que não couber antes do prazo fica registrado como faltante em `saidas/integridade.json` e no
relatório; a análise usa só repetições completas (as 40 perguntas). No Llama (PC) não há limite
de cota e roda tudo.

## Limites conhecidos

- Gabarito rascunho de um único marcador (modelo), sem conferência humana.
- 40 perguntas e 30 questões: medem ordem de grandeza, não diferença fina.
- O juiz é modelo; a validação humana vem da ficha.
- B é reconhecível pela forma (texto cru de documento), então não fica cego de verdade.
- Llama e Qwen rodam em máquinas e provedores diferentes; latência não é comparável entre eles.
- O Golden Benchmark do grupo está em "rascunho" (sem revisão pedagógica).

## Desvios (datados, sem mudar hipótese, métrica nem regra)

- **12/11/2026, 19:55, antes de gerar a repetição 2:** as repetições 2 e 3 de A e C e as rodadas 2 e 3
  do D com o Qwen saem da VPS e rodam no PC do Matheus (`qwen_resto.py`), com a chave Groq dele, mesmos
  prompts, mesmo modelo e temperatura 0. Motivo: cota gratuita da conta da VPS. Cada linha registra a
  máquina pelo campo `commit` e a data; a análise não muda.
- **12/11/2026, 20:20, antes de qualquer saída do D entrar na análise:** a cota diária da conta Groq da
  VPS (200 mil tokens) acabou no meio do D da rodada 1 (13 de 30 questões de `completo`, nenhuma de
  `sem_rag`). Essas 13 saídas foram descartadas sem olhar o resultado (pasta
  `saidas/d_execucao/descartado-vps-cota-*`, fora da análise) e o D do Qwen inteiro (rodadas 1 a 3) passa
  para o PC do Matheus, para `completo` e `sem_rag` saírem da mesma máquina e conta. A rodada 1 de A e C
  (40 + 40) ficou completa na VPS.
- **12/11/2026, 20:40, decisão do Matheus, antes de qualquer julgamento:** o estudo não usa Groq. Os
  geradores passam a ser só modelos locais no PC dele (Ollama), o que também é o cenário da produção (dado
  do aluno não sai da escola): **Llama 3.1 8B** (`llama3.1:8b`, modelo de produção; a decisão usa este) e
  **gpt-oss 20B** (`gpt-oss:20b`, aberto e maior, mede H4: o tamanho muda o vencedor?). O Qwen 3.8 27B
  sai do estudo. As 80 respostas do Qwen (A e C, repetição 1) e as 13 saídas parciais do D foram movidas
  para `saidas/fora-da-analise/` e retiradas dos pacotes do juiz, sem terem sido julgadas. Os prompts,
  os trechos da busca e o teste B continuam os mesmos. O gpt-oss raciocina antes de responder: roda com
  esforço de raciocínio "low" e teto de 4000 tokens, e só a resposta final é avaliada. Juiz: Claude Opus
  pela assinatura do Matheus (Claude Code no Mac), lotes de 40, família diferente das dos geradores
  (Meta e OpenAI). Modelos fechados (Claude Sonnet, GPT) não entram como gerador: não são o que a
  produção vai usar, e mandariam o material a terceiros sem necessidade.
- **12/11/2026, 21:05, antes de qualquer julgamento:** (a) o Llama 3.1 8B foi gerado no PC pelo Claude
  (Fable) num worktree no commit `7360db5` (sem mudança de prompt; `sha16_prompt` de todas as 240 linhas
  de A e C confere com `prompts_ac.jsonl`) e com um segundo `ollama serve` na porta 11435 com
  `OLLAMA_CONTEXT_LENGTH=8192`, porque o cliente Ollama do grupo não manda `num_ctx` no D. (b) O PREREG
  previa texto idêntico entre repetições no Ollama; não aconteceu em A (idêntico em 20 de 40 perguntas;
  C 38 de 40; D 30 de 30). Por isso o juiz recebe cada texto distinto uma vez: repetições com texto
  idêntico viram um item só, e o julgamento vale para todas elas (`repeticoes` na chave). A análise por
  pergunta continua sendo a média das 3 repetições. (c) No D, 75 de 90 saídas de cada configuração caíram
  na reserva do Adaptador (escopo reprovado). O D é relatado em duas partes: taxa de reserva por
  configuração, e comparação completo x sem_rag só onde as duas passaram (3 questões na rodada 1: pouco
  para concluir; fica como achado e limitação).
- **12/11/2026, 21:15, decisão do Matheus, antes de qualquer veredito chegar:** a ficha humana (30
  respostas sorteadas, `juiz/ficha-humana.jsonl`) fica para depois da entrega da semana 3. Os números do
  juiz (Claude Opus) entram no relatório como "juiz não validado por pessoa". A ficha continua sorteada e
  guardada; quando for preenchida, mede a concordância juiz x pessoa sem mudar nada do que já foi julgado.
- **12/11/2026, 21:20, depois dos 7 vereditos gravados e antes de abrir a `chave.json`:** (a) o julgamento
  foi feito no PC do Matheus (Claude Code no Windows, não no Mac), por 7 subagentes Claude Opus
  (`claude-opus-5-5`), um por lote, cada um com contexto novo e uma pasta só com o próprio lote e as
  instruções. A sessão que orquestrou (Claude Fable) já tinha visto as saídas do Llama e não julgou nada.
  (b) **Incidente de isolamento:** três juízes gravaram rascunhos com nomes genéricos numa pasta
  temporária comum, e os arquivos se sobrescreveram. O juiz do lote 01 leu 4 respostas do lote 02; o do
  lote 03 leu 12 respostas dos lotes 01 e 02. Nos dois casos o veredito saiu com o id alheio, o conferidor
  (`juntar.py`) recusou, e os itens certos foram julgados de novo a partir de arquivos de nome único.
  Conferência por código depois: os 242 vereditos têm exatamente os ids de cada lote e o mesmo número de
  frases de cada resposta; a abstenção detectada por código bate com a do juiz em 100 de 102 respostas com
  frases. Nenhum veredito final ficou com item trocado. A regra "sem ver outros lotes" foi quebrada nesses
  16 itens; isso não revela teste nem modelo, e fica como limitação. (c) A análise do juiz está em
  `semana3/analise_juiz.py`, escrita antes de abrir a chave. Dois complementos que o PREREG não define e
  que não entram na regra de decisão: "útil" conta só "sim" ("parcial" é contado à parte), e a fidelidade
  também é relatada só nas respostas em que o sistema respondeu, porque a frase de abstenção vale
  fidelidade 1 por construção (`INSTRUCOES-JUIZ.md`). (d) O gpt-oss 20B (H4) foi gerado no commit `1c49e6a`
  e ainda não foi julgado: os 7 lotes desta rodada são só do Llama e do teste B.
- **12/11/2026, 21:25, depois de abrir a chave e ver o resultado do Llama; registrado antes de rodar
  qualquer item abaixo.** O que já se sabe neste momento: pela regra de decisão, o vencedor do
  Estrategista é o A (único que passa no portão de abstenção; o C responde a Q40 nas 3 repetições), e o
  juiz dá ao C fidelidade 0,755 contra 0,454 do A, útil 0,525 contra 0,183 e "inventou" 0 contra 0,292.
  (a) **Rejulgamento dos lotes 01 e 03**, por causa do incidente de isolamento: dois juízes Claude Opus
  novos, cada um com pasta de rascunho própria, julgam de novo os lotes `resp-lote-01` e `resp-lote-03`
  inteiros. **O veredito novo substitui o antigo nos dois lotes, qualquer que seja o resultado**; os
  antigos ficam em `juiz/vereditos/substituidos/` e a concordância entre os dois julgamentos (mesmo item,
  mesmo modelo de juiz, sessões diferentes) é relatada como medida de estabilidade do juiz. Todos os
  números do juiz são recalculados com `analise_juiz.py`, sem mudança no script. (b) **gpt-oss 20B (H4):**
  as respostas de A e C (240 linhas, 158 textos distintos) entram em lotes novos (`resp-lote-06` em
  diante), julgados do mesmo jeito. O D do gpt-oss não vai ao juiz: o cliente Ollama do grupo não manda
  `think`, o modelo gasta o teto de tokens raciocinando, a chamada volta cortada (`JSONDecodeError`) e a
  saída é a reserva; ele é relatado só pela contagem de reserva. (c) **Decisão do Matheus sobre a
  apresentação:** o relatório aplica a regra como está escrita (A vence) e traz, em seção separada e
  rotulada como interpretação posterior ao resultado, a recomendação para o produto. A regra, as
  hipóteses e as métricas não mudam. (d) **Análise qualitativa de erros:** taxonomia das falhas a partir
  do campo `obs` dos vereditos, com contagem; é descritiva e não entra na regra.
- **12/11/2026, 21:40, fechamento:** a segunda rodada de julgamento terminou sem incidente (6 agentes, 238
  itens, nenhum id alheio, nada gravado fora da pasta do lote). Concordância entre o primeiro julgamento e o
  rejulgamento dos lotes 01 e 03: frase sustentada 189 de 196 (kappa 0,93), útil 70 de 80 (0,81), inventou
  78 de 80 (0,91), absteve 80 de 80 (`saidas/juiz_concordancia.txt`). O rejulgamento não mudou o resultado
  da regra, mas mudou a leitura de H2 contra o B3: a diferença de útil C - B3 era 0,10 [-0,08; 0,28] na
  primeira rodada (`saidas/juiz-rodada-1-antes-do-rejulgamento/`) e ficou 0,18 [0,03; 0,33]. As métricas sem
  juiz foram recalculadas no PC com o gpt-oss incluído; o `respostas_B.jsonl` foi regerado localmente por
  `teste_b.py` e reproduziu o recall@5 de 0,357. Os lotes novos foram montados por `pacotes_juiz.py` com o D
  do gpt-oss filtrado na chamada (item (b) do desvio das 21:25). O D do gpt-oss entrou com 2 das 3 rodadas.
- **12/11/2026, 21:50, atualização do fechamento:** (a) a terceira rodada do D do gpt-oss terminou: 180
  saídas, 144 de reserva (143 por `JSONDecodeError`, 1 por escopo), extrator na salvaguarda em 180 de 180,
  diretiva do RAG vazia em 87 de 88. `saidas/metricas.*` e o relatório foram atualizados. (b) **Recall
  reconciliado:** o 0,36 deste estudo é o `qwen3+rerank` com 20 candidatos, padrão de `pacote/consultar.py`
  (`CANDIDATOS_RERANK = 20`); o 0,42 do relatório de 09/11 é o `qwen3+rerank50`
  (`outputs/18-variacoes-busca.txt`), que não é o padrão do código. Mesmo gabarito nos dois. B e C deste
  estudo usaram a busca de 20 candidatos, como o PREREG previa ("busca padrão"); fica como limitação.
- **12/11/2026, 21:48, pedido do Matheus, depois de conhecidos todos os resultados acima; registrado antes de
  rodar a busca nova.** Rodada complementar com a busca de **50 candidatos** na reordenação
  (`qwen3+rerank50`, a variante apontada como adotada no relatório de 09/11), no lugar dos 20 do padrão do
  código. Novas condições: **B50** (top-1 e top-3) e **C50** (prompt `v1`, Llama 3.1 8B, 3 repetições,
  temperatura 0, mesmo `chamar_ollama`). O gpt-oss não entra nesta rodada. A busca roda no PC
  (`RAG_BANCO=memoria`, vetores do cache). **Conferências antes de gerar:** (1) com 20 candidatos, o top-5
  do PC tem de ser igual ao gravado em `saidas/trechos_busca.jsonl`; (2) com 50, o recall@5 tem de
  reproduzir 0,42 e 33 de 38 (`outputs/18-variacoes-busca.txt`). Se uma das duas falhar, a rodada para e
  o motivo é relatado. Julgamento: lotes novos, mesmo juiz, mesma rubrica, um agente por lote com pasta
  própria. Análise: as mesmas métricas e o mesmo cálculo de `analise_juiz.py`; comparações pareadas
  C50 - C, C50 - A, B50 - B e C50 - B50. **A análise pré-registrada (busca padrão) continua a principal**; a
  regra de decisão é aplicada também ao C50 só como leitura complementar, e qualquer mudança de
  configuração do produto a partir daqui é recomendação, não resultado da regra.
- **12/11/2026, 22:02, resultado da rodada complementar (50 candidatos):** as duas conferências passaram
  (top-5 do PC igual ao da VPS em 40 de 40 com 20 candidatos; recall@5 de 0,421 e 33 de 38 com 50). O
  top-5 mudou em 30 de 40 perguntas. Julgamento: 4 agentes, 121 itens, sem incidente. C50 - C: frases
  sustentadas +0,02 [-0,06; 0,11], útil 0,00 [-0,13; 0,13]; o C50 continua respondendo a Q40 (abstenção 3 de
  6) e a resposta à Q12 bateu no teto de 1.500 tokens nas 3 repetições. B50 - B no top-3: útil +0,20 [0,08;
  0,35]. C50 - B50 top-3: útil -0,03 [-0,18; 0,13]. Saídas em `saidas_r50/`. A análise principal
  (`saidas/juiz_metricas.txt`) não mudou.
- **13/11/2026, 07:00, pedido do Matheus ("o que falta para o relatório ser robusto; precisamos fazer"),
  depois de conhecidos todos os resultados acima; registrado antes de rodar qualquer item.** Reforço
  metodológico em cinco partes. Nada aqui muda a regra de decisão, as hipóteses H1 a H4 nem a análise
  principal; tudo entra como complemento, rotulado como posterior ao resultado.
  (a) **Conjunto de perguntas fora da base** (`gabarito/fora_da_base_v1.json`, escrito antes de gerar): 20
  perguntas "perto" (tema do produto, pedido que nenhum trecho responde, mesmo desenho de Q39 e Q40) e 5
  "longe" (fora do assunto). Escritas por LLM, conferidas por busca de termos no corpus, sem revisão humana.
  Condições: A, C (busca padrão, 20 candidatos) e C50 (50 candidatos), Llama 3.1 8B, prompt e parâmetros
  iguais aos da análise principal, 3 repetições. Medida principal: **taxa de abstenção** pelo mesmo
  detector de código da análise principal (`metricas.por_resposta`), com IC 95% por bootstrap sobre
  perguntas, por estrato e junto com Q39 e Q40. Medida secundária, pelo juiz (mesma rubrica, lotes novos,
  um agente por lote com pasta própria): nas respostas em que o sistema não se absteve, frases sustentadas
  e "inventou". Só vão ao juiz os textos distintos em que não houve abstenção. Expectativa escrita antes:
  C se abstém em 40% a 70% das "perto" e em 80% ou mais das "longe"; A se abstém em 30% a 60% das "perto"
  e em menos de 20% das "longe" (o prompt do A manda responder com o que sabe); C50 igual a C, com
  diferença menor que 15 pontos. O que mudaria a leitura: C abaixo de 30% nas "perto" confirma que a
  falha em Q40 é regra, não exceção; C acima de 85% diz que Q40 é caso isolado.
  (b) **Limiar de escore da busca:** com os escores do reordenador já gravados (top-1 e média do top-3),
  medir se um corte separa as 38 perguntas com resposta das 27 sem resposta (Q39, Q40 e as 25 novas): AUC
  com IC 95% por bootstrap e, no melhor corte pelo índice de Youden, quantas de cada grupo ficam de cada
  lado. O corte é escolhido e relatado no mesmo conjunto, então o número é otimista e serve só para dizer
  se vale testar a ideia. Expectativa: AUC entre 0,65 e 0,85; Q39 (escore 5,0) fica do lado errado.
  (c) **Diagnóstico do teste D.** O que já se sabe: com o Llama, 75 de 90 saídas de cada configuração são
  a reserva determinística porque o laudo de escopo do grupo reprova o texto do modelo
  (`motivo_reserva = escopo_reprovado`); o rastro não guarda o texto reprovado nem as violações. Nova
  execução do D com o Llama, 1 rodada, 30 questões, as duas configurações, com o código do grupo sem
  alteração e um observador no arnês que grava o texto do modelo antes do laudo e as violações
  (`semana3/d_diagnostico.py`). Análise sem juiz: taxa de aprovação no laudo por configuração, tipos de
  violação, se a diretiva do RAG muda o texto do modelo, e as métricas do grupo (TRCC, comando conjugado,
  Flesch) no texto do modelo e na reserva. Expectativa: a diretiva muda o texto do modelo em mais da
  metade das questões, e a taxa de aprovação é igual nas duas configurações (diferença de até 2 questões).
  Para o gpt-oss, a mesma execução com um cliente do arnês que manda `think: "low"` e teto de 4.000 tokens
  (os mesmos parâmetros de `comum.chamar_ollama`); é uma configuração corrigida, diferente da do produto, e
  é relatada como tal. Expectativa: `JSONDecodeError` cai de 143 em 180 para menos de 10%.
  (d) **Análises sobre o dado já existente** (`semana3/analise_complementar.py`): fidelidade, utilidade e
  "inventou" do C separados por a busca ter trazido ou não um trecho relevante no top-5 (gabarito atual);
  correção de Holm nos valores-p de Wilcoxon das comparações pareadas da análise principal (família: as
  comparações do Llama em fidelidade, útil e inventou); e a menor diferença detectável com 40 perguntas
  (poder de 80%, alfa de 5% bilateral, desvio-padrão das diferenças observado).
  (e) **Partes humanas adiadas por decisão do Matheus:** a ficha humana de validação do juiz e a revisão
  do gabarito da busca não são feitas antes da entrega e ficam como limitação declarada.
  **Nota sobre a ordem (pedido da Ana, 13/11):** este registro foi commitado localmente às 07:00, antes de
  qualquer execução, e enviado ao remoto junto com os resultados, no mesmo push das 07:56. O remoto, portanto,
  não comprova a ordem; a prova é o horário de autoria do commit `60fa63f` (07:00), anterior ao das saídas.
  Nas próximas rodadas, o desvio é commitado e enviado antes de gerar.
- **13/11/2026, 07:20, resultado do reforço metodológico.** (a) **Perguntas fora da base:** abstenção nas 20
  "perto": A 0,90 [0,75; 1,00], C 0,60 [0,40; 0,80], C50 0,70 [0,50; 0,90]; nas 5 "longe": 5, 5 e 4 de 5; nas
  27 com Q39 e Q40: A 0,93, C 0,67 [0,48; 0,85], C50 0,70. Idêntico nas 3 repetições em todas. Juiz: 1 agente,
  20 itens, sem incidente. C respondeu a 8 perguntas, com fato ausente dos trechos em 4 e nenhuma útil; o juiz
  viu abstenção em 2 respostas do C50 que o detector de código contou como respondidas (N02 e F04, recusa com
  outras palavras). **Expectativas:** C acertou (40% a 70% e 80% ou mais); C50 a menos de 15 pontos de C,
  acertou; **A errou**: previsto 30% a 60% nas "perto" e menos de 20% nas "longe", observado 90% e 100%. O
  prompt do A manda responder com o que sabe, e mesmo assim o Llama recusa quase tudo que não reconhece.
  (b) **Limiar de escore:** AUC 0,91 [0,83; 0,97] com 20 candidatos e 0,92 com 50; **expectativa (0,65 a 0,85)
  errou para baixo**; Q39 ficou do lado errado, como previsto. Corte 1,51: 32 de 38 liberadas, 26 de 27
  barradas. Acrescentada depois de ver o AUC, e mais dura que o registrado: conferência deixando uma de fora
  (31 de 38 e 25 de 27). (c) **Diagnóstico do D:** correção ao que este registro dizia: o rastro do arnês já
  guardava a minuta e as violações (etapa `laudo_isolamento_escopo`), então o Llama não foi executado de novo;
  a análise leu as 3 rodadas existentes (88 execuções com rastro por configuração). Minuta aprovada 15 e 15;
  diretiva muda a minuta em 82 de 88; expectativas acertaram. gpt-oss com cliente corrigido, 1 rodada:
  `JSONDecodeError` em 0 de 60 (expectativa acertou); minuta aprovada 6 de 30 com RAG e 17 de 30 sem
  (-0,37 [-0,60; -0,10], Wilcoxon p = 0,008), resultado que não estava previsto. (d) **Holm:** C - B3 em útil
  passa de p = 0,035 para 0,17 e deixa de ser significativa; as outras quatro diferenças se mantêm. Menor
  diferença detectável em útil: cerca de 0,22. Busca certa x errada: útil do C 0,62 (n = 29) contra 0,11
  (n = 9); o controle A não difere. Saídas: `saidas_fora/`, `saidas/analise_complementar.txt`,
  `saidas/d_diagnostico.txt`, `saidas_d_corrigido/`. A análise principal e a regra não mudaram.
