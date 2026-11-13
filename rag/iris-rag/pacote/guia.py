"""guia.py: as duas seções de orientação do painel (grupo "Guia" na navegação).

- Mapa do painel: para cada tela, a pergunta que ela responde, de onde vêm os números, o comando que os gera e
  quando olhar. É o que um membro novo do grupo lê primeiro.
- Ferramentas: que ferramenta do mercado cada tela imita, o que a bancada pegou dela, o que deixou de fora e por
  quê, e quando valeria trocar a versão caseira pela ferramenta de verdade.

Conteúdo escrito à mão (não depende de dados). Mantido aqui, e não no painel.py, para quem só quer editar texto.
"""
from __future__ import annotations

import html

# (seção, título, pergunta que responde, de onde vem, comando, quando olhar)
MAPA = [
    ("Estado", [
        ("visao", "Visão geral", "O último commit está bom, e tem algo grave aberto?",
         "status.json da verificação automática + achados derivados por regra", "make tudo (ou a verificação automática, a cada 10 min)",
         "Toda vez que abrir o painel."),
        ("commits", "Commits e portões", "Qual commit passou ou quebrou cada verificação, e as métricas estão subindo ou caindo?",
         "git log dos dois repositórios + historico.jsonl da verificação automática", "verificação automática",
         "Depois de um merge no dev, ou quando a visão geral mostrar reprovado."),
        ("prs", "PRs e issues", "Cada PR aberto melhora ou piora as métricas, e o que ele resolve?",
         "GitHub (gh, só leitura) + verificação automática na cabeça do PR", "make github",
         "Antes de aprovar um PR."),
        ("achados", "Achados", "O que está quebrado agora, com o caso que reproduz?",
         "regra escrita sobre a bateria adversarial, os portões e a regressão", "make adversarial",
         "Para abrir issue: cada achado já traz o caso mínimo."),
    ]),
    ("Código", [
        ("grafo", "Grafo do código", "Quem chama quem, por onde passa um fluxo, e o que não tem teste?",
         "GitNexus (funções) e ast do Python (módulos)", "make gitnexus · make mapa",
         "Antes de mexer numa função: veja quem depende dela."),
        ("pipeline", "Pipeline inteiro", "O que cada etapa faz, o que entrou e saiu, e quanto levou?",
         "rastro do arnês com o código do grupo (provedor determinístico)", "make rastro-pipeline · make etapas",
         "Quando uma adaptação sair estranha: ache a etapa onde mudou."),
        ("arq", "Arquitetura com LangGraph", "Como ficaria o fluxo dos agentes como grafo, com o laço do Auditor e a pausa da professora?",
         "protótipo em LangGraph que chama as funções do grupo", "make langgraph",
         "Ao discutir a adoção do LangGraph ou mudar a ordem dos agentes."),
    ]),
    ("RAG", [
        ("rastro-sec", "Rastro do RAG", "Para uma pergunta: o que a busca trouxe, o que a resposta disse, o que os juízes acharam?",
         "saídas gravadas das avaliações do RAG", "make rastro Q=Q07",
         "Para entender um erro concreto do RAG."),
        ("qualidade", "Qualidade por versão", "Qual configuração de busca e qual prompt funcionam melhor, com incerteza?",
         "registro das execuções (execucoes.jsonl) com intervalo de confiança", "make registrar · make regressao",
         "Antes de trocar modelo, busca ou prompt."),
        ("confianca", "Reprodutibilidade e custo", "Rodar de novo dá o mesmo resultado? Quanto custa e quanto demora?",
         "repetição da busca e dos juízes + custo por peça", "make repetir · make custo",
         "Antes de confiar numa diferença pequena entre versões."),
        ("revisao", "Revisão humana", "Onde os juízes discordam e uma pessoa precisa decidir?",
         "frases em que os juízes-modelo divergem", "make revisao",
         "Quando tiver 15 minutos: cada frase rotulada melhora a calibração do juiz."),
    ]),
    ("Qualidade", [
        ("q-avaliacao", "Conjunto de avaliação", "Este commit piorou alguma coisa na mesma prova de sempre?",
         "166 questões dos benchmarks do grupo, lacradas por hash, rodadas pelo pipeline", "make avaliacao",
         "Antes de aprovar um PR que mexe nos agentes ou no extrator."),
        ("q-rag", "RAG: os quatro elos", "Em qual pergunta a busca, a abstenção, a fidelidade ou a citação quebrou?",
         "respostas e juízes já gravados + Context Precision do RAGAS com as funções do grupo", "make rag-triade · make ragas",
         "Antes de mexer na busca, no prompt ou no gabarito."),
        ("q-ataque", "Ataque em massa", "Que tipo de dado pessoal passa pelo filtro, e como reproduzir?",
         "1.916 casos sintéticos contra sanitize_pii, o upload e o bloqueio clínico do grupo", "make ataque",
         "Antes de mexer no filtro de dados pessoais; cada padrão vira issue."),
        ("q-juiz", "Juízes x pessoas", "Posso confiar na nota que o juiz-modelo dá?",
         "votos dos juízes já gravados + rótulos de pessoas (ficha de rotulagem)", "make juiz · make rotular",
         "Antes de usar fidelidade de juiz como argumento; quando tiver tempo para rotular."),
        ("q-orcamento", "Orçamento RNF-07", "O pipeline cabe no tempo e nos tokens que o grupo prometeu?",
         "rastros do pipeline + medições reais do grupo com modelo (projeção)", "make orcamento",
         "Antes de ligar um agente novo (Estrategista, Auditor)."),
        ("q-producao", "Produção", "Quando estiver no ar: a professora usa o que o Íris entrega?",
         "proposta de registro só com metadados; hoje, simulação sintética", "make producao",
         "Para discutir com o grupo antes do piloto."),
    ]),
    ("Testes", [
        ("seguranca", "Segurança e ablação", "Dado pessoal vaza? Injeção passa? Cada peça faz diferença?",
         "bateria adversarial sintética + com/sem cada peça no benchmark do grupo", "make adversarial · make ablacao",
         "Sempre que mexer no filtro de dados pessoais ou nos agentes."),
        ("comandos", "Comandos", "Como rodar cada verificação, e o que é do grupo, da bancada ou proposta?",
         "Makefile", "make help",
         "No modo local, os botões ficam aqui."),
    ]),
]

# (ferramenta, o que é, tela, o que a bancada pegou, o que ficou de fora, quando trocar pela de verdade, link)
FERRAMENTAS = [
    ("LangGraph (LangChain)", "Monta agentes como um grafo de passos com estado: setas com condição, laços com limite, pausa para uma pessoa decidir e retomada depois de falha.",
     "arq", "O fluxo do Íris como grafo, rodando as funções do grupo, com o laço Auditor-Adaptador limitado a 2 voltas, a pausa da professora e a retomada após falha.",
     "LangGraph Studio e LangSmith (telas de acompanhamento ao vivo, pagas acima do plano gratuito) e a persistência em banco.",
     "Se o grupo adotar: o laço e a pausa da professora deixam de ser código escondido em funções e passam a aparecer no desenho.",
     "https://langchain-ai.github.io/langgraph"),
    ("GitNexus", "Indexa um repositório num grafo de conhecimento (funções, chamadas, comunidades, fluxos).",
     "grafo", "O próprio GitNexus gera o índice; o painel só desenha o grafo, os fluxos e a busca.",
     "O servidor web e o MCP dele (perguntas em linguagem natural ao código).",
     "Já é a ferramenta real. Licença PolyForm Noncommercial: serve para a residência, não para produto comercial.",
     "https://github.com/abhigyanpatwari/GitNexus"),
    ("Langfuse / Arize Phoenix", "Observabilidade de aplicações com LLM: cada chamada com prompt, resposta, tokens, tempo e custo, em árvore.",
     "pipeline", "O rastro por etapa e por chamada de agente (entrada, prompt, saída, tokens, tempo), lido dos arquivos do arnês.",
     "Servidor, banco de dados, sessões de usuário, anotação em equipe.",
     "Quando o Íris rodar com modelo real para várias professoras ao mesmo tempo. Atenção à regra de não reter conteúdo.",
     "https://langfuse.com"),
    ("Codecov / comentário de PR", "Mostra no PR quanto a cobertura e as métricas sobem ou caem em relação à branch principal.",
     "prs", "A coluna “vs dev”: as mesmas verificações rodadas na cabeça do PR, comparadas com a última rodada do dev.",
     "O comentário automático dentro do PR no GitHub.",
     "Quando o grupo quiser o resultado dentro do próprio PR: um GitHub Action que roda o make tudo e comenta.",
     "https://about.codecov.io"),
    ("GitHub Actions (histórico de CI)", "Roda os testes a cada push e guarda o histórico de execuções.",
     "commits", "O veredito de cada portão por commit, a tendência das métricas e a leitura do CI do grupo.",
     "Rodar dentro do GitHub (a bancada roda na VPS e no PC de cada um).",
     "Quando as verificações sem modelo forem para o repositório do grupo: viram um job do CI.",
     "https://docs.github.com/actions"),
    ("Ragas (usado de verdade) / DeepEval", "Métricas prontas de RAG. O grupo já usa o Ragas 0.4.3: Context Precision em iris.eval.precisao_contexto (PR #68, com teste) e fidelidade por frase em iris.eval.fidelidade_frases.",
     "q-rag", "A bancada chama as funções do grupo com a biblioteca real (make ragas) e acrescenta o que faltava: citação, abstenção e onde cada pergunta quebra.",
     "A Faithfulness do Ragas com um modelo julgando ao vivo (iris.eval.faithfulness): o grupo não rodou por falta de credencial.",
     "Já é a ferramenta real para a precisão do contexto. Para fidelidade com juiz ao vivo, só depois da calibração contra pessoas.",
     "https://docs.ragas.io"),
    ("promptfoo (red team)", "Gera ataques em massa contra um sistema com LLM e mede o que passa.",
     "q-ataque", "1.916 casos sintéticos (dado pessoal, dado clínico, evasão, injeção, controles) contra o filtro real do grupo, com padrões e o caso mínimo de cada falha.",
     "Os geradores de ataque por LLM e os plugins prontos.",
     "Quando houver modelo real no caminho: o promptfoo testa o sistema inteiro, não só o filtro.",
     "https://www.promptfoo.dev"),
    ("Label Studio / Argilla", "Ferramentas para pessoas rotularem dados e medirem concordância.",
     "q-juiz", "A ficha de rotulagem (3 botões, salva arquivo) e o kappa de cada juiz contra a pessoa, com quantos rótulos faltam.",
     "Interface de anotação com várias pessoas e controle de quem rotulou o quê.",
     "Se a professora e o time forem rotular centenas de frases.",
     "https://labelstud.io"),
    ("DVC / MLflow", "Versionam dados, experimentos e métricas, para saber qual configuração gerou qual número.",
     "q-avaliacao", "O conjunto de avaliação lacrado por hash (versão), o registro de cada configuração com o commit que a produziu e a regressão contra a linha de base.",
     "Armazenamento remoto de dados e interface de experimentos.",
     "Quando houver treino de modelo próprio ou dados grandes que não cabem no git.",
     "https://mlflow.org"),
]


DESC_GRUPO = {'Estado': 'Se o código está bom agora e o que pede ação.', 'Código': 'Como o código do grupo está montado e o que cada etapa faz.', 'RAG': 'A busca na base científica e as respostas, pergunta por pergunta.', 'Qualidade': 'Notas que valem entre versões: avaliação, ataque, orçamento.', 'Testes': 'Segurança, ablação e os comandos para rodar tudo.', 'Guia': 'Por onde começar.'}


def mapa_html() -> str:
    linhas = []
    for n, (grupo, itens) in enumerate(MAPA, 1):
        larg = {1: 12, 2: 6, 3: 4, 4: 3}.get(len(itens), 4)
        linhas.append(f"<header class=guia-sec><span class=guia-num>{n:02d}</span><div><h2>{html.escape(grupo)}</h2>"
                      f"<p>{html.escape(DESC_GRUPO.get(grupo, ''))}</p></div><span class=guia-qtd>{len(itens)} telas</span></header>"
                      "<div class='g12 guia-grade'>")
        for k, (sid, tit, perg, fonte, cmd, quando) in enumerate(itens):
            linhas.append(
                f"<button class='guia-card' style='--span:{larg};--i:{k}' onclick=\"ir('{sid}')\">"
                f"<span class=guia-tit>{html.escape(tit)}<i aria-hidden=true>→</i></span>"
                f"<span class=guia-perg>{html.escape(perg)}</span>"
                f"<dl><dt>Quando olhar</dt><dd>{html.escape(quando)}</dd>"
                f"<dt>De onde vem</dt><dd>{html.escape(fonte)}</dd>"
                f"<dt>Comando</dt><dd><code>{html.escape(cmd)}</code></dd></dl></button>")
        linhas.append("</div>")
    passos = [("Commit no GitHub", "no dev ou num PR"),
              ("A verificação automática traz o código", "por uma verificação automática, ou pelo botão atualizar do GitHub no modo local"),
              ("Verificações rodam", "sem modelo: pipeline, ataque, ablação, mapa, grafo, métricas"),
              ("Portões decidem", "tudo passou: publica; algo falhou: fica a última versão boa e a faixa vermelha"),
              ("O painel só lê", "os arquivos gravados pelas verificações; abrir não roda nada")]
    fluxo = ("<div class=guia-fluxo><h2>Como as peças se ligam</h2><ol>" +
             "".join(f"<li style='--i:{k}'><b>{html.escape(a)}</b><span>{html.escape(b)}</span></li>" for k, (a, b) in enumerate(passos)) +
             "</ol></div>")
    return ("<div class=cab><div><h1>Mapa do painel</h1><p class=sub>Cada tela responde a uma pergunta. Comece pela "
            "visão geral; clique num cartão para abrir a tela.</p></div></div>" + fluxo + "".join(linhas))


def ferramentas_html() -> str:
    cards = []
    for nome, oque, sid, pegou, fora, trocar, link in FERRAMENTAS:
        cards.append(
            f"<div class='c6 painel guia-ferr'><div class=ph><h3>{html.escape(nome)}</h3>"
            f"<button class='btn sec mini' onclick=\"ir('{sid}')\">ver no painel</button></div>"
            f"<p class=mut>{html.escape(oque)}</p><dl>"
            f"<dt>o que a bancada pegou</dt><dd>{html.escape(pegou)}</dd>"
            f"<dt>o que ficou de fora</dt><dd>{html.escape(fora)}</dd>"
            f"<dt>quando usar a de verdade</dt><dd>{html.escape(trocar)}</dd></dl>"
            f"<p class=mut3 style='font-size:12px;margin:8px 0 0'>{html.escape(link)}</p></div>")
    return ("<div class=cab><div><h1>Ferramentas</h1><p class=sub>As telas imitam ferramentas que times de IA usam. "
            "A bancada refaz só a parte que importa para o Íris, em Python simples, sem servidor, sem conta e sem mandar "
            "dado para fora. Aqui está cada uma, o que foi aproveitado e quando valeria usar a original.</p></div></div>"
            "<div class=g12>" + "".join(cards) + "</div>")


CSS = """
.guia-fluxo{margin:4px 0 8px}.guia-fluxo h2{font:600 20px/1.2 var(--tit);letter-spacing:-.2px;color:var(--tx);margin:4px 0 14px}
.guia-fluxo ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;counter-reset:p}
.guia-fluxo li{counter-increment:p;position:relative;background:var(--s1);border:1px solid var(--bd);border-radius:var(--r2);padding:14px 14px 14px;box-shadow:var(--sh1);display:flex;flex-direction:column;gap:6px;animation:entra .42s var(--ease) both;animation-delay:calc(var(--i)*60ms + 80ms)}
.guia-fluxo li::before{content:counter(p);font:600 12px/1 var(--tit);color:var(--acf);background:#E9E1FF;width:22px;height:22px;border-radius:50%;display:grid;place-items:center}
.guia-fluxo li:not(:last-child)::after{content:"→";position:absolute;right:12px;top:14px;color:var(--tx3);font-size:13px}
.guia-fluxo li b{font:600 14px/1.25 var(--tit)}.guia-fluxo li span{color:var(--tx2);font-size:12.5px;line-height:1.45}
.guia-sec{display:flex;align-items:flex-end;gap:14px;margin:40px 0 14px;padding-bottom:12px;border-bottom:1px solid var(--bd)}
.guia-sec h2{font:600 21px/1.15 var(--tit);margin:0;letter-spacing:-.3px}.guia-sec p{margin:4px 0 0;color:var(--tx2);font-size:13px}
.guia-num{font:600 15px/1 var(--tit);color:var(--ac);padding:6px 8px;border:1px solid #4A3A80;border-radius:8px;background:var(--acbg)}.guia-qtd{margin-left:auto;color:var(--tx3);font-size:12px;padding-bottom:4px;white-space:nowrap}
.guia-card{all:unset;box-sizing:border-box;cursor:pointer;display:flex;flex-direction:column;gap:10px;padding:18px 18px 16px;min-width:0;
background:var(--s1);border:1px solid var(--bd);border-radius:var(--r2);box-shadow:var(--sh1);transition:transform .2s var(--ease),box-shadow .2s var(--ease),border-color .2s}
.g12>.guia-card{grid-column:span var(--span,4)}
.guia-card:hover,.guia-card:focus-visible{border-color:var(--acf);transform:translateY(-3px);box-shadow:var(--sh2)}
.guia-tit{display:flex;align-items:center;justify-content:space-between;gap:8px;font:600 16px/1.25 var(--tit);letter-spacing:-.2px;color:var(--tx)}
.guia-tit i{font-style:normal;color:var(--tx3);transition:transform .2s var(--ease),color .2s}.guia-card:hover .guia-tit i{transform:translateX(4px);color:var(--ac)}
.guia-perg{color:var(--tx);font-size:13.5px;line-height:1.5;min-height:4.5em}
.guia-card dl,.guia-ferr dl{margin:auto 0 0;padding-top:12px;border-top:1px solid var(--bd);display:grid;grid-template-columns:1fr;gap:2px;font-size:12.5px;line-height:1.45}
.guia-card dt,.guia-ferr dt{color:var(--tx3);font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin-top:8px}.guia-card dt:first-child,.guia-ferr dt:first-child{margin-top:0}
.guia-card dd,.guia-ferr dd{margin:0;color:var(--tx2);overflow-wrap:anywhere}.guia-card code{color:var(--ac)}
.guia-ferr{padding:18px 20px;display:flex;flex-direction:column}.guia-ferr .ph{padding:0;margin-bottom:6px}.guia-ferr h3{font-size:17px}
@media (max-width:1180px){.g12>.guia-card{grid-column:span 6}.guia-fluxo ol{grid-template-columns:repeat(2,minmax(0,1fr))}.guia-fluxo li::after{display:none}}
@media (max-width:900px){.g12>.guia-card{grid-column:span 12}.guia-fluxo ol{grid-template-columns:1fr}.guia-perg{min-height:0}}
"""
