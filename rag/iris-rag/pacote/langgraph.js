/* langgraph.js: tela "Arquitetura com LangGraph" (saída 39). Embutido no painel por painel.py.
   Mostra: o fluxo de agentes como seria em LangGraph (desenho em SVG, sem biblioteca externa), o caminho que cada
   execução percorreu de verdade, o estado que passa entre os nós (e se carrega dado pessoal) e a comparação com hoje. */
let LG_EXEC=0;
const LG_COR={deterministico:'#59626f',agente:'var(--ac)',decisao:'var(--at)',pessoa:'var(--ok)',reserva:'var(--er)',fim:'#59626f'};
const LG_ROT={deterministico:'passo sem modelo',agente:'agente (modelo)',decisao:'decisão',pessoa:'professora',reserva:'saída de reserva',fim:'fim'};
/* Desenho com posições fixas por passo (grade de 6 colunas) e setas em ângulo reto, para nenhuma seta cruzar caixa.
   Se o protótipo ganhar um passo novo que não está aqui, ele aparece numa linha extra no fim (não some). */
const LG_POS={entrada:[0,0],extracao_documento:[1,0],filtro_pii:[2,0],decomposicao:[3,0],selecao_caracteristica:[4,0],perfil:[5,0],
  proxima_questao:[0,1],extrator:[1,1],busca_rag:[2,1],estrategista:[3,1],adaptador:[4,1],auditor:[5,1],
  __end__:[0,2],revisao_professora:[2.5,2],decisao:[5,2],saida_de_reserva:[4,3]};
function lgSvg(G,ex){
  const bw=172,bh=46,cw=204,X0=20,RY=[40,166,286,384];const nos=[...(G.nos||[])];
  if((G.arestas||[]).some(a=>a.para==='__end__')&&!nos.find(n=>n.id==='__end__'))nos.push({id:'__end__',nome:'Fim do material',o_que_faz:'Acabaram as questões: o material adaptado vai para a professora baixar.',tipo:'fim'});
  const pos={};let extra=0;nos.forEach(n=>{const p=LG_POS[n.id];pos[n.id]=p?{x:X0+p[0]*cw,y:RY[p[1]]}:{x:X0+(extra++)*cw,y:RY[3]+80}});
  const alt=(extra?RY[3]+80:RY[3])+bh+24,larg=X0+5*cw+bw+24;
  const vis=new Set(ex?ex.caminho:[]),seq=ex?ex.caminho:[];const passou=new Set();for(let i=0;i+1<seq.length;i++)passou.add(seq[i]+'>'+seq[i+1]);
  const c=id=>pos[id].x+bw/2,mid=id=>pos[id].y+bh/2,top=id=>pos[id].y,bot=id=>pos[id].y+bh,L=id=>pos[id].x,R=id=>pos[id].x+bw;
  const g1=(RY[0]+bh+RY[1])/2,g2=(RY[1]+bh+RY[2])/2;
  /* rotas: lista de pontos [x,y] e onde vai o rótulo da condição */
  const rota=a=>{const d=a.de,p=a.para;
    if(d==='perfil'&&p==='proxima_questao')return {pts:[[c(d),bot(d)],[c(d),g1],[c(p),g1],[c(p),top(p)]]};
    if(d==='auditor'&&p==='decisao')return {pts:[[c(d)+30,bot(d)],[c(p)+30,top(p)]]};
    if(d==='decisao'&&p==='adaptador')return {pts:[[c(d)-30,top(d)],[c(d)-30,g2],[c(p),g2],[c(p),bot(p)]],lab:[c(p)-10,g2-7,'end']};
    if(d==='decisao'&&p==='revisao_professora')return {pts:[[L(d),mid(d)],[R(p),mid(p)]],lab:[(L(d)+R(p))/2,mid(p)-7,'middle']};
    if(d==='decisao'&&p==='saida_de_reserva')return {pts:[[c(d),bot(d)],[c(d),mid(p)],[R(p),mid(p)]],lab:[c(d)-8,bot(d)+16,'end']};
    if(d==='saida_de_reserva'&&p==='revisao_professora')return {pts:[[L(d),mid(d)],[c(p),mid(d)],[c(p),bot(p)]]};
    if(d==='revisao_professora'&&p==='proxima_questao')return {pts:[[c(d),top(d)],[c(d),g2],[c(p)+30,g2],[c(p)+30,bot(p)]],lab:[c(p)+40,g2-7,'start']};
    if(d==='proxima_questao'&&p==='__end__')return {pts:[[c(d)-30,bot(d)],[c(p)-30,top(p)]],lab:[c(d)-24,(bot(d)+top(p))/2+4,'start']};
    if(d==='proxima_questao'&&p==='extrator')return {pts:[[R(d),mid(d)],[L(p),mid(p)]],lab:[R(d)+4,top(p)-8,'start']};
    if(top(d)===top(p))return {pts:[[R(d),mid(d)],[L(p),mid(p)]]};
    return {pts:[[c(d),bot(d)],[c(d),(bot(d)+top(p))/2],[c(p),(bot(d)+top(p))/2],[c(p),top(p)]]}};
  let s=`<svg viewBox="0 0 ${larg} ${alt}" width=${larg} height=${alt} class=lg-svg role=img aria-label="fluxo dos agentes do Íris em LangGraph"><defs>`+
    [['lgseta','#5d6776'],['lgseta2','#e9edf2'],['lgseta3','#e5b443']].map(([id,f])=>`<marker id=${id} viewBox="0 0 10 10" refX=9 refY=5 markerWidth=7 markerHeight=7 orient=auto-start-reverse><path d="M0,0L10,5L0,10z" fill="${f}"/></marker>`).join('')+`</defs>`;
  s+=`<text x=${X0} y=${RY[0]-14} class=lg-faixa>uma vez por material</text><text x=${X0} y=${RY[1]-14} class=lg-faixa>para cada questão</text>`;
  const labs=[];
  (G.arestas||[]).forEach(a=>{if(!pos[a.de]||!pos[a.para])return;const on=passou.has(a.de+'>'+a.para)||(a.para==='__end__'&&ex&&seq[seq.length-1]===a.de&&false);const r=rota(a);
    const cor=on?'#e9edf2':a.tipo==='laco'?'#e5b443':'#4a5260',mk=on?'lgseta2':a.tipo==='laco'?'lgseta3':'lgseta';
    s+=`<polyline points="${r.pts.map(p=>p.join(',')).join(' ')}" fill=none stroke="${cor}" stroke-width="${on?2.2:1.4}" stroke-linejoin=round ${a.tipo!=='normal'?'stroke-dasharray="5 4"':''} marker-end="url(#${mk})"><title>${esc(a.de)} → ${esc(a.para)}${a.condicao?': '+esc(a.condicao):''}</title></polyline>`;
    if(a.condicao&&r.lab)labs.push(`<text x=${r.lab[0]} y=${r.lab[1]} class="lg-cond${on?' on':''}" text-anchor=${r.lab[2]}>${esc(a.condicao)}</text>`)});
  s+=labs.join('');
  nos.forEach(n=>{const p=pos[n.id];const on=vis.has(n.id),cr=LG_COR[n.tipo]||'#59626f';const sub=n.origem&&n.origem!=='dev'?n.origem:LG_ROT[n.tipo]||'';
    s+=`<g class="lg-no ${on?'on':''} ${ex&&!on?'fora':''}" data-dica="${esc(n.nome)}: ${esc(n.o_que_faz||'')}${n.funcao_grupo?' Função do grupo: '+esc(n.funcao_grupo):''}"><rect x=${p.x} y=${p.y} width=${bw} height=${bh} rx=8 style="stroke:${cr}"/><rect x=${p.x} y=${p.y} width=4 height=${bh} rx=2 style="fill:${cr}"/>`+
    `<text x=${p.x+12} y=${p.y+20}>${esc(n.nome)}</text><text x=${p.x+12} y=${p.y+36} class=lg-sub>${esc(sub)}</text><title>${esc(n.nome)}: ${esc(n.o_que_faz||'')}${n.funcao_grupo?'\n'+esc(n.funcao_grupo):''}</title></g>`});
  return s+`</svg>`}
function langgraphSec(){const el=$('lg-arq');if(!el)return;const G=D.langgraph;
  let h=cab('Arquitetura com LangGraph','Como ficaria o fluxo dos agentes do Íris se o grupo adotar o LangGraph: cada caixa é um passo, as setas dizem para onde ir e um “estado” passa de caixa em caixa. O grupo ainda não usa LangGraph. Este protótipo da bancada chama as funções reais do grupo e roda com o modelo substituto, sem rede.');
  if(!G){el.innerHTML=h+`<div class=vazio-bloco><b>O protótipo ainda não rodou.</b><br>Na pasta <code>pacote</code>: <code>make langgraph</code>. Explicação para o grupo em <code>bancada/langgraph/PROPOSTA.md</code>.</div>`;return}
  const E=G.execucoes||[],ex=E[LG_EXEC]||null,cm=G.codigo_montado||{};
  h+=`<p class=mut3 style="margin:-6px 0 14px;font-size:12.5px">${esc(G.aviso||'')} · LangGraph ${esc(G.versao_langgraph||'')} · código montado: dev <code>${esc(cm.dev||'')}</code>${cm.estrategista?` + Estrategista <code>${esc(cm.estrategista)}</code>`:''}${cm.auditor?` + Auditor <code>${esc(cm.auditor)}</code>`:''}</p>`;
  const k=(t,v,sub)=>`<div class="c3 kpi"><span>${t}</span><b>${v}</b><em>${sub}</em></div>`;
  const voltas=E.reduce((a,x)=>a+(x.voltas_auditor||0),0),pararam=E.filter(x=>x.parou_para_professora).length,res=E.filter(x=>x.resultado==='reserva').length;
  h+=`<div class=g12>`+k('Passos no grafo',(G.nos||[]).length,`${(G.arestas||[]).filter(a=>a.tipo!=='normal').length} setas com condição`)+k('Execuções',E.length,'materiais sintéticos')+k('Voltas do Auditor',voltas,`limite por questão: ${E[0]?E[0].limite_voltas:'—'}`)+k('Parou para a professora',`${pararam}/${E.length}`,`${res} terminaram na saída de reserva`)+`</div>`;
  h+=`<div class="painel" style="margin-top:16px"><div class=ph><h3>O fluxo</h3><div class=lg-seg role=group aria-label="escolher a execução">`+E.map((x,i)=>`<button class="${i===LG_EXEC?'on':''}" onclick="LG_EXEC=${i};langgraphSec()">${esc(x.material)}${x.questao?' · '+esc(x.questao):''}${x.voltas_auditor?' · '+x.voltas_auditor+' volta(s)':''}</button>`).join('')+`</div></div>`+
  `<p class=mut style="margin:0 16px 8px;font-size:12.5px">Linha branca: o caminho que esta execução percorreu. Tracejado cinza: caminho que depende de uma condição (escrita ao lado). Tracejado âmbar: laço, o fluxo volta atrás (o Auditor devolve ao Adaptador; depois da professora, segue para a próxima questão). Passe o mouse numa caixa para ver o que ela faz e qual função do grupo chama.</p><div class=rolar style="padding:0 12px 12px">${lgSvg(G,ex)}</div>`+
  `<p style="margin:0 16px 14px;font-size:12px" class=mut3>`+Object.entries(LG_ROT).map(([t,r])=>`<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px"><i class=sw style="background:${LG_COR[t]}"></i>${r}</span>`).join('')+`</p></div>`;
  if(ex){const lat=ex.latencia_s||{};const tot=Object.values(lat).reduce((a,b)=>a+(+b||0),0)||1;
    h+=`<div class=g12 style="margin-top:16px"><div class="c6 painel"><div class=ph><h3>Esta execução, passo a passo</h3><p>${esc(ex.material)} · resultado <b>${esc(ex.resultado)}</b> · ${ex.checkpoints} estados salvos (dá para voltar a qualquer um)</p></div><div class=rolar><table><tbody>`+
    ex.caminho.map((id,i)=>{const n=(G.nos||[]).find(x=>x.id===id)||{nome:id};const s=lat[id];return `<tr><td class=mut3 style="width:28px">${i+1}</td><td>${esc(n.nome)}</td><td style="width:42%">${s!=null?barraQ(s/tot,null,'var(--ac)',160)+` <span class="mono mut3" style="font-size:11.5px">${(+s).toFixed(3)} s</span>`:''}</td></tr>`}).join('')+`</tbody></table></div></div>`;
    const ST=G.estado||[];
    h+=`<div class="c6 painel"><div class=ph><h3>O estado que passa entre os passos</h3><p>É a “ficha” que cada caixa lê e preenche. Regra da bancada: nenhum campo carrega dado pessoal, só texto já filtrado.</p></div><div class=rolar><table><thead><tr><th>campo</th><th>quem preenche</th><th>dado pessoal?</th></tr></thead><tbody>`+
    ST.map(c=>`<tr><td><code>${esc(c.campo)}</code><div class=mut3 style="font-size:11.5px">${esc(c.tipo||'')}${c.observacao?' · '+esc(c.observacao):''}</div></td><td class=mut>${esc(c.quem_escreve||'')}</td><td>${c.contem_dado_pessoal?'<span class="selo pii">sim</span>':'<span class=mut3>não</span>'}</td></tr>`).join('')+`</tbody></table></div></div>`}
  const C=G.comparacao||[];
  if(C.length)h+=`<div class="painel plano" style="margin-top:16px"><div class=ph style="padding:14px 16px 0"><h3>Hoje x com LangGraph</h3><p>O que muda para o grupo, e o custo de cada mudança.</p></div><div class=rolar><table><thead><tr><th style="padding-left:16px">aspecto</th><th>hoje (Python em sequência)</th><th>com LangGraph</th><th>custo ou risco</th></tr></thead><tbody>`+
    C.map(c=>`<tr><td style="padding-left:16px"><b>${esc(c.aspecto)}</b></td><td class=mut>${esc(c.hoje)}</td><td>${esc(c.com_langgraph)}</td><td class=mut>${esc(c.custo_ou_risco)}</td></tr>`).join('')+`</tbody></table></div></div>`;
  if((G.limitacoes||[]).length)h+=`<details class="painel" style="margin-top:16px;padding:12px 16px"><summary>Limitações deste protótipo (${G.limitacoes.length})</summary><ul style="margin:8px 0 0">${G.limitacoes.map(l=>`<li class=mut style="font-size:13px">${esc(l)}</li>`).join('')}</ul></details>`;
  h+=`<p class=mut3 style="font-size:12.5px;margin-top:14px">Proposta completa para o grupo (o que é, o que muda no código, riscos com a regra de não reter dados, quando vale adotar e a migração em fases): <code>bancada/langgraph/PROPOSTA.md</code>.</p>`;
  el.innerHTML=h}
