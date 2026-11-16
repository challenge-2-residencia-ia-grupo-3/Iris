/* glossario.js: explica cada peça do painel ao passar o mouse (ou tocar, no celular).
   Como funciona: depois que cada tela é desenhada, procura cabeçalhos de tabela, rótulos de cartão, selos e fases
   e, quando o texto bate com um termo do GLOSS, marca o elemento com data-dica. Um único balão (role=tooltip)
   mostra a dica; os title="" que já existiam passam a usar o mesmo balão, para valer também no toque. */
const GLOSS={
/* tabelas e colunas */
'quando':'Data e hora em que a verificação rodou.',
'alvo':'O que foi verificado: o ramo dev do grupo ou a cabeça de um PR aberto.',
'grupo':'Commit do repositório do grupo que foi verificado (7 primeiros caracteres).',

'commit':'Identificador curto do commit no git.',
'mensagem':'A mensagem que o autor escreveu no commit.',
'veredito':'Aprovado se nenhum portão reprovou. Um portão reprovado basta para reprovar a rodada.',
'resultado':'Como a verificação terminou.',
'status':'Situação atual do item.',
'situação':'Situação atual do item.',
'vs dev':'Diferença entre as métricas do PR e as do dev. Verde melhora, vermelho piora.',
'portões no PR':'Os mesmos portões do dev, rodados na versão do PR antes de ele entrar.',
'PR':'Pull request: um pedido para juntar um ramo ao dev. Ainda não entrou.',
'PRs abertos':'Pedidos de junção que ainda não foram aceitos nem fechados.',
'issue':'Tarefa ou problema registrado no GitHub do grupo.',
'dono':'Quem está responsável pela issue no GitHub.',
'CI do grupo':'Os testes automáticos que o próprio GitHub do grupo roda a cada envio (GitHub Actions).',
'etapa':'Um passo do pipeline do Íris, na ordem em que acontece.',
'etapas do pipeline':'Os passos que o material percorre, do envio do arquivo até a revisão da professora.',
'etapas tocadas':'Quantas etapas do pipeline este item exercitou.',
'agente':'Etapa que chama um modelo de linguagem para decidir ou escrever algo.',
'o que faz':'O papel da etapa, em uma frase.',
'entrada → saída':'Um exemplo real do que entrou na etapa e do que saiu dela.',
'o que saiu':'O texto que a etapa devolveu.',
'o que saiu do filtro':'O texto depois do filtro de dados pessoais. O que aparece em vermelho deveria ter sido apagado.',
'tempo':'Quanto a etapa levou, em segundos.',
'mediana':'O valor do meio: metade das execuções foi mais rápida e metade mais lenta.',
'p95':'95% das execuções foram mais rápidas que este valor. Mostra os casos lentos.',
'limite':'O máximo combinado nos requisitos do grupo (RNF).',
'tokens':'Pedaços de texto que o modelo lê ou escreve. É o que se paga na API.',
'tokens entrada (máx)':'O maior número de tokens enviados ao modelo numa chamada.',
'modelo':'Qual modelo de linguagem respondeu.',
'configuração':'Uma combinação de peças ligadas e desligadas. Serve para medir quanto cada peça ajuda.',
'variante':'Uma versão alternativa da mesma etapa, para comparar.',
'n':'Quantos itens entraram na conta.',
'questão':'Uma questão do material escolar.',
'questões':'Quantas questões entraram na conta.',
'material · questão':'Qual material sintético e qual questão dele.',
'disciplina':'Matéria escolar da questão.',
'nível':'Nível de apoio pedido pela professora (quanto o material é simplificado).',
'caso':'Um exemplo de teste.',
'cenário':'A situação simulada no teste.',
'tipo':'A categoria do item.',
'onde':'Arquivo e linha no código do grupo.',
'evidência':'O trecho de texto ou o dado que sustenta a conclusão.',
'peça':'Uma parte do sistema medida separadamente.',
'uso':'Para que a peça serve no Íris.',
'idade':'Há quanto tempo o item está aberto.',
'linha do tempo':'Quando cada coisa aconteceu, da mais antiga para a mais nova.',
'resolve / avança':'Qual issue este PR resolve ou faz andar.',
'par':'Os dois juízes (ou o juiz e a pessoa) comparados.',
'rótulos':'Respostas marcadas por uma pessoa como certas ou erradas. São o gabarito para conferir os juízes.',
'útil = sim':'Quantas vezes a pessoa marcou a resposta como útil.',
'respondeu':'Se o sistema respondeu ou preferiu não responder.',
'certos':'Quantos acertos.',
'comando':'O comando make que gera esta parte do painel.',
'conjugado':'Questão com mais de um comando na mesma frase ("leia e responda"). Para aluno com TDAH, o Íris separa em passos.',
'retenção':'Quanto do conteúdo obrigatório (a trava curricular) continuou na versão adaptada.',
'fidelidade':'Se cada frase da resposta está apoiada nos trechos recuperados. Frase sem apoio é invenção do modelo.',
'frases sem citação':'Frases da resposta que não indicam de qual trecho vieram.',
'abstenção certa Q39/Q40':'Perguntas sem resposta nos documentos: o certo é o sistema dizer que não sabe.',
'top-5':'Os 5 trechos que a busca trouxe primeiro.',
'hit@5':'Se pelo menos um trecho certo apareceu entre os 5 primeiros.',
'recall@5':'De todos os trechos certos, quantos apareceram entre os 5 primeiros.',
'MRR':'Quão no alto aparece o primeiro trecho certo. 1 é em primeiro lugar, 0,5 em segundo.',
'kappa (−0,2 a 1)':'Concordância descontando o acaso. Perto de 0 é concordar por sorte; acima de 0,6 é bom.',
'100% sustentada':'Respostas em que todas as frases têm apoio nos trechos.',
'bruta':'O número antes de qualquer correção.',
'copia o aviso da curadoria':'Se a resposta repete o aviso que a curadoria pediu para mostrar.',
/* fases da tabela de rodadas */
'CI':'Testes do GitHub do grupo.',
'pipeline':'O Íris inteiro roda, sem erro, do envio até a saída; inclui a ablação e o orçamento de tempo.',
'dados pessoais':'Filtro de dados pessoais (LGPD): ataques planejados, ataque em massa e o registro de produção.',
'RAG':'A busca nos documentos e a resposta: busca, fidelidade, citação, abstenção, juízes e regressão das métricas.',
'avaliação':'O conjunto de 166 questões lacrado, rodado a cada versão.',
'código':'Mapa e grafo do código do grupo.',
'bancada':'A própria bancada: repetição dá o mesmo resultado, custo, arquivos válidos e publicação.',
/* cartões */
'Portões da última rodada':'Cada portão é uma verificação com regra escrita. A rodada só é publicada se nenhum reprovar.',
'Dados pessoais LGPD':'Dados de aluno que passaram pelo filtro quando não deviam.',
'Filtro de dados pessoais LGPD':'Quantos casos de teste com dado pessoal o filtro apagou.',
'Injeção de prompt':'Texto escondido no material tentando mandar no modelo ("ignore as instruções"). Barrar é o certo.',
'Formatos difíceis':'Arquivos estranhos (tabela, imagem, PDF quebrado) que o pipeline precisa aguentar.',
'Rodou sem erro':'Etapas do pipeline que terminaram sem erro.',
'Módulos':'Arquivos de código Python do grupo.',
'Módulos com teste':'Arquivos de código que têm pelo menos um teste automático.',
'Símbolos no grafo':'Funções, classes e métodos encontrados pelo GitNexus no código do grupo.',
'Comunidades e fluxos':'Comunidades são grupos de funções que se chamam muito entre si; fluxos são caminhos de execução.',
'Questões avaliadas':'Quantas questões do conjunto lacrado passaram pelo pipeline nesta rodada.',
'Retenção curricular ≥ 0,95':'Questões em que ao menos 95% do conteúdo obrigatório continuou na adaptação.',
'Laudo pega saída estragada':'Estragamos a saída de propósito de 6 jeitos; mede se o laudo do grupo percebe.',
'Vazou no material':'Casos do ataque em massa em que o dado pessoal ficou no texto do material.',
'Perfil aceitou dado clínico':'Casos em que diagnóstico, CID ou remédio entrou no perfil do aluno.',
'Dribla um bloqueio que existe':'Vazamentos que contornam uma regra que o filtro já tem (por exemplo, um nome com acento).',
'Apagou conteúdo que devia ficar':'Falso alarme: o filtro apagou texto escolar comum achando que era dado pessoal.',
'Estouros duros':'Execuções que passaram do limite de tempo ou de custo dos requisitos.',
'Projeção com modelo real (RNF-07)':'Estimativa do tempo com um modelo de verdade, a partir das medições do próprio grupo.',
'Privacidade do registro':'Tentativas de gravar dado pessoal no registro de produção que o registrador recusou.',
'Alertas':'Sinais que pedem atenção, mas não reprovam sozinhos.',
'Busca do sistema atual':'Qualidade da busca nos documentos com a configuração que o Íris usa hoje.',
'Fidelidade da resposta':'Parte das frases da resposta que está apoiada nos trechos.',
'Aceitou sem mexer':'Respostas que a professora aceitou do jeito que vieram.',
'Aceitou (com ou sem edição)':'Respostas que a professora usou, editando ou não.',
'Quando editou, mudou':'Quanto do texto a professora mudou quando decidiu editar.',
'1 · Busca: recall@5':'Se os trechos certos aparecem entre os 5 primeiros da busca.',
'2 · Fidelidade':'Se a resposta só diz o que os trechos dizem.',
'3 · Frases com citação':'Se cada frase indica de qual trecho veio.',
'4 · Abstenção certa':'Se o sistema diz que não sabe quando a resposta não está nos documentos.',
/* selos */
'aprovado':'Nenhum portão reprovou.',
'reprovado':'Pelo menos um portão reprovou. Clique na linha para ver qual.',
'aprovado na verificação':'A cabeça deste PR passou em todos os portões da bancada.',
'atenção':'Merece olhar, mas não reprova.',
'aviso':'Merece olhar, mas não reprova.',
'proposta':'Ainda não existe no código do grupo; é uma sugestão da bancada.',
'protótipo':'Feito pela bancada para mostrar a ideia; não está no código do grupo.',
'existe no repo do grupo':'Esta peça já está no código do grupo.',
'não existe ainda':'Esta peça ainda não está no código do grupo.',
'determinístico':'Medido por regra fixa, sem modelo de linguagem: dá sempre o mesmo resultado.',
'juiz não calibrado':'Medido por um modelo que ainda não foi comparado com rótulos de pessoas.',
'sem CI':'Este PR não tem testes do GitHub rodados.',
'CI ok':'Os testes do GitHub do grupo passaram.',
'precisa julgar mais respostas':'Ainda há poucos rótulos para a conta ser confiável.',
'memória de trabalho':'Ajuda para o aluno guardar a instrução enquanto faz a tarefa (uma das características de TDAH).',
'T1':'Característica de TDAH 1 do catálogo do grupo.',
'LGPD':'Lei Geral de Proteção de Dados: dado de aluno não pode vazar nem ficar guardado sem necessidade.',
'vazou':'O dado pessoal passou pelo filtro.',
};
/* nomes legíveis das métricas da tendência (antes apareciam como chave de código) */

Object.assign(GLOSS,{'ataques planejados barrados':'Dos ataques escritos à mão (dado pessoal, injeção, formato), quantos o Íris barrou.','vazamento no ataque (%)':'Parte dos casos do ataque em massa em que o dado pessoal ficou no material.','vaza dado clínico (%)':'Diagnóstico, CID ou remédio que passou pelo filtro.','retenção curricular (ablação)':'Retenção do conteúdo obrigatório na configuração completa do pipeline.','nota do conjunto lacrado':'Média das notas das 166 questões do conjunto congelado.','falso alarme do filtro (%)':'Texto escolar comum que o filtro apagou por engano.'});
Object.assign(GLOSS,{'ok':'Passou na regra desta verificação.','erro':'A etapa terminou com erro.','falhou':'A verificação não passou.','sim':'Sim, atende.','cabe':'Cabe no limite combinado.',
'nenhuma métrica caiu':'Nenhum número piorou em relação à última rodada aprovada.','estrategia':'Etapa do Agente Estrategista.','dado pessoal':'Dado que identifica um aluno (nome, documento, contato, saúde).',
'#':'Posição na ordem.','dados pessoais bloqueados':'Casos com dado pessoal que o filtro apagou.','injeção barrada':'Tentativas de mandar no modelo que foram barradas.','formatos ok':'Formatos difíceis que o pipeline aguentou.',
'etapas ok':'Etapas que rodaram sem erro.','etapas com erro':'Etapas que terminaram com erro.','latência do pipeline (s)':'Tempo total do pipeline, em segundos (com o modelo substituto).',
'módulos sem teste':'Arquivos de código sem nenhum teste automático.','funções':'Funções no código do grupo.','testes':'Testes automáticos do grupo.','símbolos':'Funções, classes e métodos no grafo.','chamadas':'Ligações “esta função chama aquela” no grafo.',
'ataques planejados':'Total de ataques escritos à mão.','casos de dado pessoal':'Total de casos de teste com dado pessoal.','casos de injeção':'Total de casos de injeção de prompt.','formatos testados':'Total de formatos difíceis testados.',
'comandos separados (%)':'Questões com mais de um comando que o Íris separou em passos.','falhas na ablação':'Configurações da ablação que deram erro.','retenção ≥ 0,95':'Questões que mantiveram ao menos 95% do conteúdo obrigatório.',
'segue o nível de apoio':'Questões em que a adaptação respeitou o nível de apoio pedido.','comandos separados':'Questões com comandos juntos que foram separadas.','vaza nome (%)':'Casos em que o nome do aluno passou.','vaza documento (%)':'Casos em que CPF, RG ou matrícula passou.',
'vaza contato (%)':'Casos em que telefone, e-mail ou endereço passou.','padrões de vazamento':'Tipos diferentes de vazamento; cada um vira uma issue com o menor caso que reproduz.','estouros de orçamento':'Execuções que passaram do limite de tempo ou custo.'});
for(const k of ['T2','T3','T4','T5'])GLOSS[k]=`Característica de TDAH ${k.slice(1)} do catálogo do grupo.`;
const GL_LOWER={};for(const k in GLOSS)GL_LOWER[k.toLowerCase()]=GLOSS[k];
function glTexto(e){return (e.childNodes.length?[...e.childNodes].filter(n=>n.nodeType===3||n.tagName==='B'||n.tagName==='SPAN'&&!n.classList.contains('cont')).map(n=>n.textContent).join(''):e.textContent).replace(/\s+/g,' ').trim()}
function glAchar(t){if(!t)return null;const l=t.toLowerCase();if(GL_LOWER[l])return GL_LOWER[l];
  const sem=l.replace(/\s*\d+$/,'').replace(/\s+(determinístico|juiz não calibrado)$/,'');if(GL_LOWER[sem])return GL_LOWER[sem];
  if(/^t\d( t\d)*$/.test(l))return 'Características de TDAH do catálogo do grupo que esta questão trabalha.';
  if(/^[\d.,]+ s$/.test(l))return 'Tempo da etapa, em segundos.';
  if(/^\d+ etapas$/.test(l))return 'Quantas etapas do pipeline existem nesta versão.';
  if(/não implementadas$/.test(l))return 'Etapas que o grupo ainda não escreveu (aparecem como “a fazer” no fluxo).';
  if(/^(alta|grave) · /.test(l))return 'Gravidade e tipo do achado. Grave = vazamento de dado pessoal ou quebra de regra do projeto.';
  if(/^útil: /.test(l))return 'Avaliação da professora sobre a resposta.';
  if(/frases na fila$/.test(l))return 'Frases que ainda esperam alguém marcar se estão certas.';
  if(/defeito do gabarito$/.test(l))return 'O problema está no gabarito, não no Íris: o conceito exigido nem aparece no texto original.';
  return null}
function glAplicar(raiz){(raiz||document).querySelectorAll('th,.kpi>span:first-child,.selo,.mat-cab .fase,.estado-pill,.cont').forEach(e=>{
  if(e.dataset.dica||e.getAttribute('title')||e.closest('[title],[data-dica]')&&e.closest('[title],[data-dica]')!==e)return;
  const d=glAchar(glTexto(e));if(d){e.dataset.dica=d;e.classList.add('tem-dica');if(!e.hasAttribute('tabindex')&&!/^(BUTTON|A)$/.test(e.tagName))e.tabIndex=0}})}
/* balão único: mouse, foco (teclado) e toque */
const GL_B=document.createElement('div');GL_B.className='dica-balao';GL_B.setAttribute('role','tooltip');GL_B.id='dica-balao';document.body.appendChild(GL_B);
let GL_ALVO=null;
function glMostrar(e){let t=e.dataset.dica;if(!t&&e.hasAttribute('title')){t=e.getAttribute('title');e.dataset.dica=t;e.removeAttribute('title')}if(!t)return;
  GL_ALVO=e;GL_B.textContent=t;GL_B.style.display='block';e.setAttribute('aria-describedby','dica-balao');
  const r=e.getBoundingClientRect(),b=GL_B.getBoundingClientRect();let x=r.left+r.width/2-b.width/2,y=r.top-b.height-8;
  if(y<8)y=r.bottom+8;x=Math.max(8,Math.min(innerWidth-b.width-8,x));GL_B.style.left=x+'px';GL_B.style.top=y+'px'}
function glEsconder(){if(GL_ALVO)GL_ALVO.removeAttribute('aria-describedby');GL_ALVO=null;GL_B.style.display='none'}
document.addEventListener('mouseover',ev=>{const e=ev.target.closest&&ev.target.closest('[data-dica],[title]');if(e&&!(e instanceof SVGElement)&&e!==document.documentElement)glMostrar(e);else if(GL_ALVO)glEsconder()});
document.addEventListener('focusin',ev=>{const e=ev.target.closest&&ev.target.closest('[data-dica],[title]');if(e)glMostrar(e)});
document.addEventListener('focusout',glEsconder);addEventListener('scroll',glEsconder,{passive:true});
document.addEventListener('keydown',ev=>{if(ev.key==='Escape')glEsconder()});
document.addEventListener('touchstart',ev=>{const e=ev.target.closest&&ev.target.closest('.tem-dica');if(e){if(GL_ALVO===e)glEsconder();else glMostrar(e)}else glEsconder()},{passive:true});
new MutationObserver(ms=>{let f=false;for(const m of ms)if(m.addedNodes.length){f=true;break}if(f)requestAnimationFrame(()=>glAplicar())}).observe(document.body,{childList:true,subtree:true});
glAplicar();
