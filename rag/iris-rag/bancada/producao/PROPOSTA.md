# Rastro de produção do Íris: o que gravar quando a professora usa a ferramenta de verdade

Status: **proposta da bancada para o grupo**. Nada aqui altera o código do grupo (commit `65e1f09`).
Os números em `pacote/outputs/37-producao.json` são **SINTÉTICOS** (inventados com semente fixa) e só
servem para dar forma à tela do painel.

## 1. A ideia em uma frase

Analogia: o diário de bordo de um avião anota quanto tempo cada trecho levou, quanto combustível gastou e
se houve pouso de emergência, mas **nunca** anota a conversa dos passageiros. O rastro de produção faz o
mesmo com cada pedido de adaptação: guarda **metadados** (números e escolhas de lista) e **nenhum
conteúdo** (enunciado, texto adaptado, perfil, nome).

Junto disso, ele guarda o **retorno da professora** na tela de revisão (História 2.2.2, issue #22):
aceitou, editou (com quanto % do texto mudou) ou recusou (com o motivo escolhido numa lista). É isso que
transforma o rastro em métrica de produto: "a professora usa o que o Íris sugere?".

## 2. As regras do grupo que mandam aqui

| regra do grupo | o que diz (resumo) | consequência para o rastro |
|---|---|---|
| **RNF-01** (Zero-Database), issue **#35** (História 4.1.2) | nenhum dado do material ou do perfil pode ficar em disco ou banco depois da requisição; único armazenamento persistente permitido é a base RAG somente-leitura | rastro **desligado por padrão**; sem banco; nenhum campo com conteúdo do material; quando ligado, só arquivo local de metadados com apagamento automático |
| **RNF-02** (Zero-Retention), issue **#37** (História 4.1.4) e **#36** | logs registram só métricas operacionais (latência, tokens, status, TRCC), "sem jamais gravar o conteúdo bruto das provas ou perfis"; logs não podem exibir texto das questões "nem metadados identificáveis" | lista fechada de campos; texto livre recusado; detector de nome/CPF/telefone/e-mail; sentinela com as palavras do material; hash do material com chave descartável (não dá para "reconhecer" uma prova pelo hash) |
| **RNF-03**, issue **#28** | nada clínico (CID, laudo, medicação) | detector recusa padrões de CID (`CID-10`, `F90.0`); não existe campo de perfil no rastro |
| **RNF-07** e **RNF-08** | latência ≤ 15 s (nível 1) e ≤ 40 s (níveis 2 e 3); ≤ 8.000 tokens por ciclo de 5 questões | latência por etapa e tokens por adaptação **são** o que o rastro mede |
| **DEP-OC-05** (backlog) | o estado da sessão fica no navegador (`sessionStorage`); o backend é transiente | o **% de edição é calculado no navegador** e só o número viaja até o servidor |
| **DEP-OC-04** | o catálogo `tdah_caracteristicas_funcionais.json` é a fonte única dos `id_caracteristica` | o campo `caracteristica` só aceita ids do catálogo |
| precedente do próprio grupo: `iris.eval.extractor_analytics` (arquitetura §7.4) | já grava `reports/extractor_telemetry.jsonl` "anônimo (Zero-PII)" | o rastro segue a mesma linha, mas mais fechado: o arquivo do grupo aceita `tema` e `question_id` como texto livre, que podem carregar conteúdo; aqui não há campo assim |

## 3. O que gravar (lista completa; nada fora dela é aceito)

Três tipos de registro. Todos têm `tipo`, `versao_esquema`, `dia` (AAAA-MM-DD), `hora` (0–23) e, só na
simulação, `sintetico: true`.

**`requisicao`** (um por material enviado)

| campo | tipo | de onde vem |
|---|---|---|
| `material_hmac` | 16 hexadecimais | HMAC-SHA256 do texto com **chave aleatória que só existe na memória e troca todo dia**. Serve para contar "quantas vezes o mesmo material foi reenviado hoje" e nada mais. Ninguém consegue recalcular depois, nem com a prova original na mão |
| `formato` | lista: texto, txt, pdf, docx | rota usada |
| `faixa_tamanho` | lista: ate_500, 500_2000, 2000_10000, acima_10000 caracteres | faixa, não o tamanho exato |
| `n_questoes` | inteiro 0–500 | `decompose_material(...).total_questions` |
| `n_pii_substituidos` | inteiro | 2º valor de `sanitize_pii` (quantos dados pessoais o filtro trocou; nunca quais) |
| `etapas` | lista de `{etapa, ms, status}`; etapa de lista fechada | cronômetro do registrador |
| `erro_codigo` | lista fechada (códigos `code="..."` do grupo, nomes de exceção comuns, `outro`) | nunca a mensagem da exceção |
| `id_requisicao` | 32 hexadecimais aleatórios | só no modo `eventos`; não deriva de nada |

**`adaptacao`** (uma por questão adaptada)

| campo | tipo | de onde vem (código do grupo) |
|---|---|---|
| `questao_ordem` | inteiro | posição da questão (1, 2, 3...) |
| `caracteristica` | id do catálogo | `AdaptationRequest.id_caracteristica` |
| `nivel` | 1–3 | `AdaptationRequest.nivel` |
| `provedor`, `modelo` | lista / padrão curto sem espaço | `AdaptationTelemetry.provider/model` |
| `tokens_entrada`, `tokens_saida` | inteiros | soma Extrator + Adaptador |
| `usou_reserva`, `motivo_reserva` | sim/não; lista: nenhum, provedor_sem_modelo, escopo_reprovado, falha_llm | `telemetry.used_fallback/motivo_fallback` (o `falha_llm:NomeDaExcecao` do grupo é partido: a categoria vai aqui, o nome vai para `erro_codigo`) |
| `escopo_aprovado`, `violacoes` | sim/não; lista de categorias | `ScopeReport.aprovado`; as frases de `violacoes` do grupo **citam palavras do texto** (`palavra do original ausente: [...]`), então só a categoria é gravada |
| `trava_recall` | 0–1 | `ExtractionTelemetry.trava_recall` (quando existir referência) |
| `dentro_limite_rnf07` | sim/não | `AdaptationTelemetry.dentro_do_limite` |
| `etapas`, `erro_codigo` | como acima | |

**`retorno`** (um por questão revisada; chega do navegador)

| campo | tipo | observação |
|---|---|---|
| `caracteristica`, `nivel`, `usou_reserva` | como acima | repetidos para o modo `agregado` não precisar cruzar nada |
| `decisao` | lista: aceitou, editou, recusou, sem_retorno | |
| `pct_alterado` | 0–100, de 5 em 5 | só quando `editou`; calculado no navegador comparando minuta e versão final (a função `pct_alterado` do protótipo mostra a conta) |
| `motivo_recusa` | lista: mudou_o_que_a_questao_avalia, andaime_nao_ajuda_esta_caracteristica, linguagem_infantilizada, formatacao_quebrada, erro_de_conteudo, demorou_demais, outro | só quando `recusou`; **menu, não caixa de texto** |
| `segundos_ate_decisao` | 0–3600, de 10 em 10 | quanto tempo a professora levou para decidir |

## 4. O que NUNCA gravar (e por quê)

| nunca | por quê |
|---|---|
| enunciado, alternativas, texto de apoio, texto adaptado, diretiva, prompt, resposta do modelo | conteúdo bruto da prova: RNF-02 / #37 |
| a versão editada pela professora, ou o "diff" dela | também é conteúdo; só o **%** sai do navegador |
| nome de arquivo enviado | costuma ter nome de aluno ou turma ("prova_joao_7B.pdf") |
| perfil pedagógico, `codigo_anonimo`, observações da professora | RNF-01 / #35 e RNF-03 / #28 |
| qualquer campo de texto livre (comentário, motivo digitado, `tema`, `disciplina` digitada) | é por onde o conteúdo e o nome entram sem ninguém perceber |
| frases de violação do laudo de escopo, mensagens de exceção | citam palavras do texto; só a categoria/código |
| IP, usuário, escola, e-mail, horário com minuto e segundo | identificam a professora e, por tabela, a turma |
| hash simples (sha256) do material | quem tiver a prova consegue confirmar que ela passou pelo Íris; por isso a chave do HMAC é aleatória e diária |
| os `trechos` do RAG | licença restrita; no máximo o id do trecho (e nem isso é necessário em produção) |

## 5. Onde fica, por quanto tempo, como desligar

* **Desligado por padrão.** A variável `IRIS_RASTRO_PRODUCAO` vale `desligado` se ninguém mexer. Para
  ligar é preciso **duas** coisas: o modo e uma pasta (`IRIS_RASTRO_DIR`). Sem pasta, continua desligado.
* **Modo recomendado: `agregado`.** Só contadores por dia, do tipo
  `retorno|<caracteristica>|n2|recusou|formatacao_quebrada → 3`. Sem id de requisição, sem hash,
  sem hora. É o que basta para as métricas de produto da seção 6.
* **Modo `eventos`** (só em piloto combinado com a escola): uma linha JSON por evento, em
  `eventos-AAAA-MM-DD.jsonl`, permissão 600 (só o dono do processo lê), no **servidor de quem roda o
  Íris** (no piloto, a máquina do professor ou da escola). Nunca num serviço externo, nunca em banco.
* **Retenção:** `IRIS_RASTRO_RETENCAO_DIAS` (padrão 30, máximo 90). Ao ligar o servidor, arquivos mais
  velhos são apagados. Sugestão: no piloto, 30 dias em `eventos`; depois, só `agregado`.
* **Desligar:** apagar a variável (ou `IRIS_RASTRO_PRODUCAO=desligado`) e reiniciar a API. Para zerar:
  apagar a pasta. Como não há banco, não sobra nada em outro lugar.
* **Aviso na tela:** quando ligado, a tela de revisão mostra "este servidor conta aceites e recusas, sem
  guardar o texto". Isso é um pedido ao front; não está implementado.

## 6. Como vira métrica de produto

Tudo sai de `agregar()` em `rastro_producao.py`; o painel lê `pacote/outputs/37-producao.json`.

| métrica | conta | para que serve |
|---|---|---|
| **aceite por característica** | (aceitou + editou) ÷ retornos com decisão, por `caracteristica` (IC 95% Wilson) | descobrir em qual característica o andaime não convence |
| **aceite sem edição** | aceitou ÷ com decisão | "a minuta já serve como está?" |
| **edição média** | média de `pct_alterado` quando editou (IC 95% bootstrap) | quanto trabalho a professora ainda tem |
| **recusas por motivo** | contagem e proporção por `motivo_recusa` | `mudou_o_que_a_questao_avalia` alto = trava curricular falhando (RNF-04) |
| **reserva vs. modelo** | os mesmos números separados por `usou_reserva` | a saída de reserva (só negrito/etapas) agrada menos? |
| **por nível** | os mesmos números por nível 1/2/3 | nível 3 é editado mais? |
| **saúde técnica** | % de reserva e motivo, % escopo aprovado, % dentro do RNF-07, mediana e p90 de latência por etapa, tokens por adaptação (RNF-08) | o que já existe na bancada, agora com dado de uso real |

**Regra de tamanho mínimo:** célula com menos de 5 casos é **suprimida** (não mostra número). Numa escola
pequena, "1 recusa em nível 3 na característica X na terça" pode apontar uma pessoa.

## 7. O protótipo nesta pasta

| arquivo | o que faz |
|---|---|
| `rastro_producao.py` | `RegistradorProducao` (contexto por requisição, por questão e por etapa), esquema validado, listas fechadas, detector de dado pessoal, sentinela do material, HMAC diário, modos desligado/agregado/eventos, retenção, `pct_alterado`, `agregar()` com Wilson/bootstrap e supressão. Só stdlib |
| `exercitar.py` | liga o registrador no **código real do grupo** (filtro de PII, decomposição, Extrator, busca RAG bm25, Adaptador, laudo de escopo e reserva envolvidos em tempo de execução e desfeitos no fim), provedor `eco`, e audita: dado pessoal plantado no rastro, trigramas do material no rastro, 8 tentativas deliberadas de vazamento |
| `simular.py` | ~200 adaptações **sintéticas** (semente 20261112) passando pelo mesmo registrador em modo estrito; agrega e grava `pacote/outputs/37-producao.json`; o log bruto sintético fica em `pacote/reports/producao/` (fora do git) |
| `test_rastro_producao.py` | 22 testes `unittest`: texto do material, texto adaptado, nome, CPF, telefone, e-mail, CID, motivo digitado, nome como chave, texto dentro da lista de etapas → todos recusados; modo desligado não cria arquivo; agregado não guarda id nem hash; retenção apaga arquivo velho |

Como o grupo plugaria depois (não feito aqui): criar o registrador uma vez no `main.py`
(`RegistradorProducao.do_ambiente()`), abrir `with reg.requisicao(texto)` nas rotas de
`api/routes/materials.py`, `with req.questao(...)` em volta do Adaptador, e uma rota
`POST /api/v1/retorno` que recebe só `{caracteristica, nivel, decisao, pct_alterado, motivo_recusa}`.

## 8. Limites desta proposta

* O detector de nome é uma regra simples ("duas palavras com maiúscula"); a proteção principal são a
  lista fechada e a ausência de texto livre, não o detector.
* A sentinela só protege campos semiabertos (hoje só `modelo`); os demais já são lista fechada ou número.
* O `pct_alterado` em produção depende do front calcular e mandar só o número; o protótipo não controla o
  navegador.
* Os números de `37-producao.json` são inventados. A taxa de aceite real só existe depois de um piloto.
* A conferência no código do grupo usa o provedor `eco`: mede o encanamento, não a qualidade de um modelo.
