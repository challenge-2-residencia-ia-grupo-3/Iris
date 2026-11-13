/* llmxrag.js: aba "LLM x RAG" (saída 40, semana 3). Embutido no painel por painel.py.
   Só lê o que semana3/painel_dados.py gravou (que por sua vez só copia os números do juiz_metricas e do metricas).
   Nada aqui recalcula estatística. Cores: verde = sustentado/útil, âmbar = parcial, vermelho = inventou/contradiz. */
let LX_MOD='llama',LX_Q='Q40';
function lxNum(v,d=2){return v==null||isNaN(v)?'—':(+v).toFixed(d).replace('.',',')}
const LX_NOME={A:'A · LLM sozinho',B1:'B1 · busca, 1 trecho',B3:'B3 · busca, 3 trechos',C:'C · RAG + LLM',C50:'C · busca com 50 candidatos',
 'B1-50':'B1 · busca com 50 candidatos','B3-50':'B3 · busca com 50 candidatos','A-gptoss':'A · LLM sozinho (gpt-oss 20B)','C-gptoss':'C · RAG + LLM (gpt-oss 20B)'};
const LX_CURTO={A:'A',B1:'B1',B3:'B3',C:'C',C50:'C·50','B1-50':'B1·50','B3-50':'B3·50','A-gptoss':'A·gpt','C-gptoss':'C·gpt'};
const LX_GRUPOS={llama:{t:'Llama 3.1 8B (produção)',c:['A','B1','B3','C']},gpt:{t:'gpt-oss 20B (H4)',c:['A-gptoss','B1','B3','C-gptoss']},
 r50:{t:'busca com 50 candidatos',c:['C','C50','B3','B3-50']}};
/* métricas: [chave, rótulo, explicação, maior é melhor?] */
const LX_MET=[['util_sim','Resposta útil','o juiz diria ao professor: isto resolve (só "sim" conta)',true],
 ['util_sim_ou_parcial','Útil ou em parte','conta também "parcial"',true],
 ['fidelidade','Frases apoiadas na base','frases sustentadas pelos trechos ÷ frases da resposta; "não sei" conta como apoiada',true],
 ['fidelidade_sem_abstencao','Apoiadas, só quando respondeu','a mesma medida sem as abstenções (que valem 1 por construção)',true],
 ['inventou','Inventou fato ou fonte','trouxe fato específico que não está na base',false],
 ['tem_frase_que_contradiz','Alguma frase contradiz a base','pelo menos uma frase diz o contrário do trecho',false]];
function lxDot(ic,cor,w=150){if(!ic)return '<span class=mut3>não se aplica</span>';return barraQ(ic[0],[ic[1],ic[2]],cor,w)}
function lxIc(ic){return ic?`<b class=mono>${lxNum(ic[0])}</b> <span class=mut3 style="font-size:11.5px">[${lxNum(ic[1])}; ${lxNum(ic[2])}]</span>`:'<span class=mut3>—</span>'}
function lxCor(k,bom){return k=='inventou'||k=='tem_frase_que_contradiz'?'var(--er)':bom?'var(--ok)':'var(--ac)'}

/* 1 ------------------------------------------------------------ decisão: regra x recomendação */
function lxDecisao(X){const d=(X.decisao||{})['llama3.1-8b']||{},ca=(d.candidatas||{});
const port=(n,c)=>{if(!c)return '';const pa=c.portao_a_passa,pb=c.portao_b_passa;
 return `<tr><td style="padding-left:16px"><b>${n}</b></td><td>${c.portao_a_abstencao_q39_q40!=null?`<span class="selo ${pa?'ok':'er'}">${pa?'✓':'✗'} ${esc(c.portao_a_abstencao_q39_q40)}</span>`:'<span class=mut3>não se abstém</span>'}</td>
 <td>${c.portao_b_latencia_p95_s!=null?`<span class="selo ${pb?'ok':'er'}">${pb?'✓':'✗'} ${lxNum(c.portao_b_latencia_p95_s,1)} s</span>`:'—'}</td><td style="padding-right:16px">${c.concorre?'<span class="selo ok">✓ concorre</span>':'<span class="selo er">fora</span>'}</td></tr>`};
const C=X.condicoes||{},a=C.A||{},c=C.C||{};
return `<div class=g12><div class="c6 painel"><div class=ph><h3>1 · A regra escrita antes do resultado</h3><p>O PREREG manda: primeiro dois portões de segurança (abster-se nas perguntas Q39 e Q40, que não têm resposta na base, nas 3 repetições; latência p95 dentro do RNF-07). Só quem passa compete em fidelidade.</p></div>
<table><thead><tr><th style="padding-left:16px">condição</th><th>abstenção Q39+Q40</th><th>latência p95</th><th>resultado</th></tr></thead><tbody>${port('A · LLM sozinho',ca.A)}${port('C · RAG + LLM',ca.C)}
<tr><td style="padding-left:16px"><b>B · só a busca</b></td><td colspan=3 class=mut3 style="padding-right:16px">${esc((ca.B||{}).motivo||'')}</td></tr></tbody></table>
<div class="lx-veredito neutro"><span>Pela regra pré-registrada vence</span><b>${esc(d.vencedor||'nenhuma')}</b><em>${esc(d.motivo||'')}. C respondeu a Q40 nas 3 repetições: uma pergunta decide a regra.</em></div></div>
<div class="c6 painel"><div class=ph><h3>2 · O que os mesmos dados mostram <span class="selo at">interpretação posterior</span></h3><p>Escrita depois de ver o resultado e registrada como desvio no PREREG. Não substitui a regra: fica ao lado dela.</p></div>
<table><tbody>${[['Resposta útil','util_sim',1],['Apoiadas, quando respondeu','fidelidade_sem_abstencao',1],['Inventou fato ou fonte','inventou',0]].map(([t,k,b])=>`<tr><td style="padding-left:16px">${t}</td><td class=mono>A ${pct((a[k]||[])[0])}</td><td class=mono>C ${pct((c[k]||[])[0])}</td><td style="padding-right:16px">${(b?(c[k]||[0])[0]>(a[k]||[0])[0]:(c[k]||[0])[0]<(a[k]||[0])[0])?'<span class="selo ok">C melhor</span>':'<span class="selo er">A melhor</span>'}</td></tr>`).join('')}
<tr><td style="padding-left:16px">Abstenção indevida (tinha resposta)</td><td class=mono>A ${pct(1-(a.cobertura_38??1))}</td><td class=mono>C ${pct(1-(c.cobertura_38??1))}</td><td style="padding-right:16px"><span class="selo ok">C melhor</span></td></tr></tbody></table>
<div class="lx-veredito at"><span>Recomendação do relatório (seção 8.2)</span><b>C, depois de corrigir a abstenção</b><em>A passa no portão porque se cala muito: abstém-se em ${Math.round(38*(1-(a.cobertura_38??1)))} das 38 perguntas que têm resposta na base. C só vira aprovada quando parar de responder fora da base (limiar de relevância antes da geração), verificado com mais perguntas fora da base.</em></div></div></div>`}

/* 2 ------------------------------------------------------------ condições lado a lado */
function lxCondicoes(X){const G=LX_GRUPOS[LX_MOD],C=X.condicoes||{};
const seg=`<div class=seg role=tablist>${Object.entries(LX_GRUPOS).map(([k,g])=>`<button class="${LX_MOD==k?'on':''}" onclick="LX_MOD='${k}';llmxragSec()">${g.t}</button>`).join('')}</div>`;
const cab2=`<tr><th style="padding-left:16px">métrica</th>${G.c.map(k=>`<th>${esc(LX_NOME[k])}</th>`).join('')}</tr>`;
const linhas=LX_MET.map(([k,t,ex,bom])=>`<tr><td style="padding-left:16px;min-width:190px">${t}<div class=mut3 style="font-size:12px">${ex}</div></td>${G.c.map(c=>{const v=(C[c]||{})[k];
 return `<td>${v?`${lxIc(v)}<div>${lxDot(v,lxCor(k,bom),120)}</div>`:'<span class=mut3>não se aplica</span>'}</td>`}).join('')}</tr>`).join('');
const cod=[['abstencao_correta_q39_q40','Abstenção em Q39 e Q40',v=>v==null?'<span class=mut3>não se abstém</span>':`<span class="selo ${v=='6/6'?'ok':'er'}">${esc(v)}</span>`],
 ['cobertura_38','Respondeu, das 38 com resposta',v=>v==null?'<span class=mut3>1,00 (sempre devolve)</span>':`<b class=mono>${lxNum(v)}</b>`],
 ['pct_frases_com_citacao_media','Frases com citação [Tn]',v=>v==null?'<span class=mut3>—</span>':`<b class=mono>${pct(v)}</b>`],
 ['latencia_p95_s','Latência p95',v=>v==null?'<span class=mut3>—</span>':`<b class=mono>${lxNum(v,1)} s</b>`],
 ['texto_identico_nas_3','Mesmo texto nas 3 repetições',v=>v==null?'<span class=mut3>determinístico</span>':`<b class=mono>${v} de 40</b>`]];
const linhas2=cod.map(([k,t,f])=>`<tr><td style="padding-left:16px">${t}<div class=mut3 style="font-size:12px">medido por código, sem juiz</div></td>${G.c.map(c=>`<td>${f((C[c]||{})[k])}</td>`).join('')}</tr>`).join('');
return `<div class="painel" style="margin-top:16px"><div class=ph style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap"><div><h3>As condições lado a lado</h3><p>Média das 40 perguntas (cada pergunta vale igual; nas que têm 3 repetições, a média delas). Entre colchetes, o intervalo de confiança de 95% por bootstrap. Bolinha = valor; faixa = intervalo.</p></div>${seg}</div>
<div class=rolar><table class=lx-tab><thead>${cab2}</thead><tbody>${linhas}${linhas2}</tbody></table></div></div>`}

/* 3 ------------------------------------------------------------ diferenças pareadas */
function lxPareados(X){const P=X.pareados||{};
const quais=LX_MOD=='gpt'?[['C − A (gpt-oss)','fidelidade'],['C − A (gpt-oss)','util_sim'],['C − A (gpt-oss)','inventou']]:
 LX_MOD=='r50'?[['C50 − C','fidelidade'],['C50 − C','util_sim'],['B3-50 − B3','util_sim'],['C50 − B3-50','util_sim']]:
 [['C − A','fidelidade'],['C − A','fidelidade_sem_abstencao'],['C − A','util_sim'],['C − A','inventou'],['C − B1','util_sim'],['C − B3','util_sim'],['C − B3','util_sim_ou_parcial']];
const rot={fidelidade:'apoiadas na base',fidelidade_sem_abstencao:'apoiadas, só respondidas',util_sim:'resposta útil',util_sim_ou_parcial:'útil ou em parte',inventou:'inventou'};
const W=260,x=v=>W/2+v*W/2;
const lin=quais.map(([c,m])=>{const d=(P[c]||{})[m];if(!d||!d.dif)return '';const [v,lo,hi]=d.dif,bom=m=='inventou'?hi<0:lo>0,ruim=m=='inventou'?lo>0:hi<0,cor=bom?'var(--ok)':ruim?'var(--er)':'var(--tx3)';
 return `<tr><td style="padding-left:16px"><b>${esc(c)}</b> · ${rot[m]}</td><td><svg width=${W+12} height=18 role=img aria-label="diferença ${lxNum(v)}"><line x1=${6+W/2} x2=${6+W/2} y1=0 y2=18 stroke=var(--bd2) stroke-dasharray=2,2 /><rect x=${6+x(lo)} y=7 width=${Math.max(2,x(hi)-x(lo))} height=4 rx=2 fill=${cor} opacity=.45 /><circle cx=${6+x(v)} cy=9 r=5 fill=${cor} /></svg></td>
 <td class=mono>${v>0?'+':''}${lxNum(v)} <span class=mut3 style="font-size:11.5px">[${lxNum(lo)}; ${lxNum(hi)}]</span></td><td class=mono>${d.p==null?'—':d.p<0.001?'&lt; 0,001':lxNum(d.p,3)}</td><td class=mono style="padding-right:16px">${d.melhoraram??'—'} / ${d.pioraram??'—'}</td></tr>`}).join('');
return `<div class="painel" style="margin-top:16px"><div class=ph><h3>A diferença pergunta a pergunta</h3><p>Para cada pergunta, a nota de uma condição menos a da outra (pareado: a mesma pergunta dos dois lados). A linha tracejada é o zero. Verde = o intervalo inteiro fica do lado bom; cinza = o intervalo cruza o zero, e então não dá para afirmar diferença. p = Wilcoxon.</p></div>
<div class=rolar><table><thead><tr><th style="padding-left:16px">comparação</th><th>−1 · 0 · +1</th><th>diferença [IC 95%]</th><th>p</th><th style="padding-right:16px">melhoraram / pioraram</th></tr></thead><tbody>${lin}</tbody></table></div></div>`}

/* 4 ------------------------------------------------------------ mapa: cada pergunta, cada condição */
function lxMapa(X){const Q=X.perguntas||[],G=LX_GRUPOS[LX_MOD].c;
const cel=(n)=>{if(!n)return `<td class=lx-c><i class="lx-q vz" title="sem dado"></i></td>`;
 const cls=n.inventou>0?'er':n.absteve>=1?'cz':n.util>=0.67?'ok':n.util>0||n.parcial>0?'at':'nd';
 const t=n.inventou>0?'inventou':n.absteve>=1?'não sei':n.util>=0.67?'útil':n.util>0||n.parcial>0?'em parte':'não útil';
 return `<td class=lx-c><i class="lx-q ${cls}" title="${t}${n.fid!=null?' · apoiadas '+pct(n.fid):''}"></i></td>`};
const cat={factual:'factual',sintese:'síntese',fora_da_base:'fora da base'};
const rows=Q.map(q=>`<tr class="lx-l ${LX_Q==q.id?'on':''}" onclick="LX_Q='${q.id}';llmxragSec();document.getElementById('lx-nav').scrollIntoView({behavior:'smooth'})"><td class=mono style="padding-left:16px">${q.id}</td><td class=lx-perg>${esc(q.pergunta)}</td><td><span class="selo ${q.categoria=='fora_da_base'?'er':''}">${cat[q.categoria]||'—'}</span></td>${G.map(c=>cel((q.notas||{})[c])).join('')}</tr>`).join('');
const leg=[['ok','útil'],['at','em parte'],['nd','não útil'],['cz','disse "não sei"'],['er','inventou fato ou fonte']].map(([c,t])=>`<span><i class="lx-q ${c}"></i>${t}</span>`).join('');
return `<div class="painel" style="margin-top:16px"><div class=ph><h3>As 40 perguntas, uma por linha</h3><p>Cada quadrado é o veredito do juiz naquela pergunta (média das repetições). Clique numa linha para ver as respostas lado a lado.</p><div class=lx-leg>${leg}</div></div>
<div class=rolar style="max-height:520px;overflow:auto"><table class=lx-mapa><thead><tr><th style="padding-left:16px">id</th><th>pergunta</th><th>tipo</th>${G.map(c=>`<th class=lx-c title="${esc(LX_NOME[c])}">${LX_CURTO[c]}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div></div>`}

/* 5 ------------------------------------------------------------ navegador de respostas */
function lxNavegador(X){const T=D.llmxrag_textos,el=`<div id=lx-nav class=painel style="margin-top:16px">`;
const q=(X.perguntas||[]).find(p=>p.id==LX_Q)||{};
const sel=`<select class=q aria-label=pergunta onchange="LX_Q=this.value;llmxragSec()">${(X.perguntas||[]).map(p=>`<option value=${p.id} ${p.id==LX_Q?'selected':''}>${p.id} · ${esc(p.pergunta.slice(0,80))}</option>`).join('')}</select>`;
if(!T)return el+`<div class=ph><h3>Respostas lado a lado</h3></div>${vazioQ('O texto das respostas fica fora do git (traz trecho de documento sem licença aberta).','python ../semana3/painel_dados.py')}</div>`;
const R=T[LX_Q]||{};
const corS={sim:'ok',parcial:'at','não':'er'};
const caixa=k=>{const r=R[k];if(!r)return `<div class=lx-resp><h4>${esc(LX_NOME[k])}</h4><p class=mut3>sem resposta julgada</p></div>`;
 const corpo=r.frases?r.frases.map(f=>`<span class="lx-fr ${f.s=='sim'?'ok':f.s=='parcial'?'at':'er'}" title="${f.s=='sim'?'sustentada pelos trechos':f.s=='parcial'?'em parte':'não sustentada'}${f.c?' · contradiz: '+esc(f.c):''}">${esc(f.t)}</span>`).join(' ')
  :`<div class=mut3 style="font-size:11.5px;margin-bottom:6px">trecho de documento sem redação: o juiz avalia só a resposta inteira, não frase a frase</div><div class=lx-cru>${esc(r.resposta)}</div>`;
 const sel=[`<span class="selo ${corS[r.util]||''}">útil: ${esc(r.util||'—')}</span>`,r.inventou=='sim'?'<span class="selo er">inventou</span>':'',r.absteve=='sim'?'<span class="selo">disse "não sei"</span>':''].join(' ');
 return `<div class=lx-resp><h4>${esc(LX_NOME[k])}</h4><div class=lx-selos>${sel}</div><div class=lx-texto>${corpo}</div>${r.obs?`<details><summary>o que o juiz anotou</summary><p>${esc(r.obs)}</p></details>`:''}${(r.trechos||[]).length&&k!='A'?`<details><summary>trechos que ${k=='C'?'o modelo recebeu':'a busca devolveu'} (${r.trechos.length})</summary><ol>${r.trechos.map(t=>`<li>${esc(t.ref)} · ${esc(t.doc)}${t.pag?' · p. '+esc(t.pag):''}</li>`).join('')}</ol></details>`:''}</div>`};
return el+`<div class=ph style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start"><div><h3>Respostas lado a lado</h3><p>Repetição 1, com o Llama 3.1 8B. Cada frase pintada pelo juiz: verde = está nos trechos, âmbar = em parte, vermelho = não está. Passe o mouse para ver o motivo.</p></div>${sel}</div>
<p class=lx-pg><b>${esc(q.id||'')}</b> ${esc(q.pergunta||'')} <span class=mut3>· ${esc(q.categoria||'')}${q.doc?' · documento principal: '+esc(q.doc):''}</span></p>
<div class=lx-quatro>${['A','B1','B3','C'].map(caixa).join('')}</div></div>`}

/* 6 ------------------------------------------------------------ hipóteses, produto (D), modelo maior, juiz */
function lxResto(X){const H=X.hipoteses||{},D_=(X.D||{})['llama3.1-8b']||{},pc=D_.por_config||{},dm=((X.D||{}).metricas||{})['llama3.1-8b']||{},dg=((X.D||{}).metricas||{})['gpt-oss-20b']||{},K=X.concordancia_juiz||{},b=X.busca||{};
const hip=Object.entries(H).map(([h,t])=>{const ok=/: confirmada/.test(t),nao=/não confirmada/.test(t);return `<tr><td style="padding-left:16px">${esc(h)}</td><td style="padding-right:16px"><span class="selo ${nao?'er':ok?'ok':'at'}">${nao?'não confirmada':ok?'confirmada':'ver texto'}</span><div class=mut3 style="font-size:12px;margin-top:4px">${esc(t.split(': ').slice(0,-1).join(': ')||t)}</div></td></tr>`}).join('');
const res=c=>`${(pc[c]||{}).reserva??'—'} de ${(pc[c]||{}).saidas??'—'}`;
const kp=(t,v,s,cls='')=>`<div class="c3 kpi ${cls}"><span>${t}</span><b>${v}</b><em>${s}</em></div>`;
return `<div class=g12 style="margin-top:16px">
${kp('Busca: recall@5',lxNum((b.k20||{})['recall@5']?.[0]),`20 candidatos (padrão do código, usado em B e C) · com 50: ${lxNum((b.k50||{})['recall@5']?.[0])}`)}
${kp('Produto (D): saída de reserva',pct(dm.completo?.pct_reserva),`com RAG ${res('completo')} · sem RAG ${res('sem_rag')}: o Llama reprova no laudo de escopo e o plano B entra`,'at')}
${kp('Juiz consigo mesmo',`κ ${lxNum((K.frase_sustentada||{}).kappa)}`,`${(K.frase_sustentada||{}).iguais} de ${(K.frase_sustentada||{}).n} frases iguais ao rejulgar · útil κ ${lxNum((K.util||{}).kappa)}. Não é concordância com pessoa.`)}
${kp('gpt-oss no D',pct(dg.completo?.pct_reserva),'reserva: o cliente do grupo não limita o raciocínio e a resposta volta cortada. Teste não válido.','er')}</div>
<div class=g12 style="margin-top:16px"><div class="c7 painel"><div class=ph><h3>Hipóteses do PREREG</h3><p>Como foram escritas antes, e o que os dados disseram.</p></div><table><tbody>${hip}</tbody></table></div>
<div class="c5 painel"><div class=ph><h3>Teste D: o Adaptador com e sem RAG</h3><p>Em 25 das 30 questões o Adaptador cai na saída de reserva nas duas configurações: as duas entregam o mesmo texto e a comparação fica sem poder. Só 3 questões passaram nas duas.</p></div>
<table><thead><tr><th style="padding-left:16px">medida</th><th>com RAG</th><th style="padding-right:16px">sem RAG</th></tr></thead><tbody>
<tr><td style="padding-left:16px">Saída de reserva</td><td class=mono>${res('completo')}</td><td class=mono style="padding-right:16px">${res('sem_rag')}</td></tr>
<tr><td style="padding-left:16px">Adaptação útil (juiz)</td><td class=mono>${pct((pc.completo||{}).util_sim?.[0])}</td><td class=mono style="padding-right:16px">${pct((pc.sem_rag||{}).util_sim?.[0])}</td></tr>
<tr><td style="padding-left:16px">Nível de apoio respeitado</td><td class=mono>${pct((pc.completo||{}).nivel_respeitado?.[0])}</td><td class=mono style="padding-right:16px">${pct((pc.sem_rag||{}).nivel_respeitado?.[0])}</td></tr>
<tr><td style="padding-left:16px">Entrega a resposta / muda o que avalia</td><td class=mono>${pct((pc.completo||{}).entrega_resposta?.[0])} / ${pct((pc.completo||{}).mudou_o_que_avalia?.[0])}</td><td class=mono style="padding-right:16px">${pct((pc.sem_rag||{}).entrega_resposta?.[0])} / ${pct((pc.sem_rag||{}).mudou_o_que_avalia?.[0])}</td></tr>
<tr><td style="padding-left:16px">Tokens por questão</td><td class=mono>${Math.round(dm.completo?.tokens_media||0).toLocaleString('pt-BR')}</td><td class=mono style="padding-right:16px">${Math.round(dm.sem_rag?.tokens_media||0).toLocaleString('pt-BR')}</td></tr></tbody></table></div></div>`}

function llmxragSec(){const el=$('llmxrag'),X=D.llmxrag;if(!el)return;
let h=cab('LLM x RAG','O estudo da semana 3: o mesmo modelo de produção respondendo de memória (A), só a busca (B) e a busca entregue ao modelo (C), com juiz de outra família e regra de decisão escrita antes. Os números são copiados das saídas do estudo, sem recalcular.',X?`<span class=selo>gerado ${esc((X.gerado_em||'').slice(0,10))}</span>`:'');
if(!X){el.innerHTML=h+vazioQ('Ainda não há os números da semana 3.','python ../semana3/painel_dados.py');return}
const y=window.scrollY;
el.innerHTML=h+lxDecisao(X)+lxCondicoes(X)+lxPareados(X)+lxMapa(X)+lxNavegador(X)+lxResto(X)+lxReforco(X)+
`<p class=mut3 style="font-size:12px;margin-top:14px">Fontes: ${(X.fontes||[]).map(f=>`<code>${esc(f)}</code>`).join(' · ')} · relatório em <code>${esc(X.relatorio||'')}</code>. Limitações principais: juiz não conferido por pessoa; o portão de abstenção da regra depende de 2 perguntas (a rodada de 27 é complementar); 40 perguntas não enxergam diferenças menores que ≈ 0,22.</p>`;
window.scrollTo(0,y)}

/* 7 ------------------------------------------------------------ reforço de 13/11 (seções 6.8 a 6.11) */
function lxReforco(X){const F=X.reforco;if(!F)return '';
const pc=v=>v==null?'—':Math.round(100*v)+'%';
const ab=F.abstencao||{},jf=F.juiz_fora||{},L=F.limiar||{};
const barra=(t,cor)=>{const [v,lo,hi]=t||[];if(v==null)return '';const W=150,x=q=>q*W;return `<svg width=${W+8} height=14 role=img aria-label="${pc(v)}"><rect x=4 y=5 width=${W} height=4 rx=2 fill=var(--s3) /><rect x=${4+x(lo)} y=4 width=${Math.max(2,x(hi)-x(lo))} height=6 rx=3 fill=${cor} opacity=.35 /><circle cx=${4+x(v)} cy=7 r=4.5 fill=${cor} /></svg>`};
const linAb=[['A','A · LLM sozinho'],['C','C · RAG + LLM'],['C50','C50 · 50 candidatos']].map(([k,n])=>{const a=ab[k]||{},j=jf[k]||{};
 return `<tr><td style="padding-left:16px"><b>${n}</b></td><td>${barra((a.perto||{}).taxa_ic95,'var(--ac)')} <span class=mono>${pc(((a.perto||{}).taxa_ic95||[])[0])}</span></td><td class=mono>${pc(((a.longe||{}).taxa_ic95||[])[0])}</td><td>${barra((a.todas27||{}).taxa_ic95,'var(--ac)')} <span class=mono>${pc(((a.todas27||{}).taxa_ic95||[])[0])}</span> <span class=mut3 style="font-size:11.5px">[${pc(((a.todas27||{}).taxa_ic95||[])[1])}; ${pc(((a.todas27||{}).taxa_ic95||[])[2])}]</span></td><td class=mono>${(a.nao_absteve||[]).length}</td><td class=mono style="padding-right:16px">${j.perguntas_com_invencao?`<span style="color:${j.perguntas_com_invencao.length?'var(--er)':'var(--tx2)'}">${j.perguntas_com_invencao.length}</span>`:'—'}</td></tr>`}).join('');
const sec1=`<div class="c7 painel"><div class=ph><h3>Perguntas que a base não responde <span class=selo>seção 6.8</span></h3><p>O portão da regra usa só Q39 e Q40. Aqui, 25 perguntas novas sem resposta na base (20 do tema do produto, 5 de outro assunto), mais Q39 e Q40. Abstenção contada por código, nas 3 repetições (o comportamento foi o mesmo nas 3).</p></div>
<div class=rolar><table><thead><tr><th style="padding-left:16px">condição</th><th>do tema (20)</th><th>outro assunto (5)</th><th>as 27</th><th>respondeu (de 25)</th><th style="padding-right:16px">com invenção</th></tr></thead><tbody>${linAb}</tbody></table></div>
<p class=mut3 style="font-size:12.5px;padding:10px 16px 14px">A falha da Q40 não é caso isolado: no tema do produto, C responde a 4 de cada 10 perguntas sem resposta e, quando responde, traz fato ausente dos trechos em metade delas (juiz). As 25 perguntas foram escritas por modelo e conferidas por busca de termos, sem revisão de pessoa.</p></div>`;
const pb=L.sem_resposta_acima_do_corte||[],bar=L.com_resposta_abaixo_do_corte||[];
const sec2=`<div class="c5 painel"><div class=ph><h3>O escore da busca como trava <span class="selo at">candidato, não validado</span></h3><p>O reordenador dá uma nota ao 1º trecho. Pergunta sem resposta costuma ter nota baixa: dá para recusar antes de gerar?</p></div>
<div style="padding:4px 16px 14px"><div class=g12 style="gap:10px">
<div class="c6 kpi" style="min-height:0"><span>Separação (AUC)</span><b>${lxNum((L.auc_ic95||[])[0])}</b><em>IC95 ${lxNum((L.auc_ic95||[])[1])}–${lxNum((L.auc_ic95||[])[2])} · 0,5 = acaso</em></div>
<div class="c6 kpi" style="min-height:0"><span>Corte testado</span><b>${lxNum(L.corte_youden)}</b><em>escolhido nas mesmas 65 perguntas</em></div></div>
<table style="margin-top:10px"><tbody>
<tr><td>sem resposta, barradas</td><td class=mono><b>${L.sem_resposta_abaixo_do_corte}</b> de ${L.n_sem} <span class=mut3>(${L.fora_da_amostra_sem_resposta_barradas} sem otimismo)</span></td></tr>
<tr><td>com resposta, liberadas</td><td class=mono><b>${L.com_resposta_acima_do_corte}</b> de ${L.n_com} <span class=mut3>(${L.fora_da_amostra_com_resposta_liberadas} sem otimismo)</span></td></tr>
<tr><td style="color:var(--er)">escapa</td><td class=mono style="color:var(--er)">${pb.map(esc).join(', ')||'—'}</td></tr>
<tr><td>recusadas sem motivo</td><td class=mono>${bar.map(esc).join(', ')||'—'}</td></tr></tbody></table>
<p class=mut3 style="font-size:12.5px;margin-top:8px">A Q39 (dose de remédio) escapa porque a base fala do remédio sem dizer a dose: a nota é alta. É o caso mais grave e precisa de outro mecanismo. "Sem otimismo" = cada pergunta julgada por um corte escolhido sem ela.</p></div></div>`;
const bc=(F.busca_certa||{})['C|llama3.1-8b']||{},bA=(F.busca_certa||{})['A|llama3.1-8b']||{},u=(bc.campos||{}).util_sim||{},uA=(bA.campos||{}).util_sim||{};
const H=F.holm||[];
const linH=H.map(h=>{const sig=h.p_holm<0.05,mudou=h.p_wilcoxon<0.05&&!sig;return `<tr${mudou?' style="background:var(--atbg)"':''}><td style="padding-left:16px">${esc(h.comparacao.replace(' - ',' − '))}</td><td class=mono>${h.dif_media>0?'+':''}${lxNum(h.dif_media)}</td><td class=mono>${h.p_wilcoxon<0.001?'&lt; 0,001':lxNum(h.p_wilcoxon,3)}</td><td class=mono>${h.p_holm<0.001?'&lt; 0,001':lxNum(h.p_holm,3)}</td><td>${sig?'<span class="selo ok">✓ se mantém</span>':mudou?'<span class="selo at">deixou de valer</span>':'<span class=selo>não</span>'}</td><td class=mono style="padding-right:16px">${h.menor_diferenca_detectavel==null?'—':lxNum(h.menor_diferenca_detectavel)}</td></tr>`}).join('');
const sec3=`<div class="c5 painel"><div class=ph><h3>Busca certa x busca errada <span class=selo>seção 6.9</span></h3><p>As 38 perguntas com resposta, separadas por a busca ter trazido ou não um trecho relevante entre os 5.</p></div>
<div style="padding:4px 16px 14px"><table><thead><tr><th></th><th>busca certa</th><th>busca errada</th></tr></thead><tbody>
<tr><td><b>C</b> · resposta útil</td><td>${barra(u.certa,'var(--ok)')} <span class=mono>${pc((u.certa||[])[0])}</span> <span class=mut3>n=${u.n_certa}</span></td><td>${barra(u.errada,'var(--er)')} <span class=mono>${pc((u.errada||[])[0])}</span> <span class=mut3>n=${u.n_errada}</span></td></tr>
<tr><td><b>A</b> · controle</td><td>${barra(uA.certa,'var(--tx3)')} <span class=mono>${pc((uA.certa||[])[0])}</span></td><td>${barra(uA.errada,'var(--tx3)')} <span class=mono>${pc((uA.errada||[])[0])}</span></td></tr></tbody></table>
<p class=mut3 style="font-size:12.5px;margin-top:8px">Quando a busca erra, C quase nunca é útil. O A, que não vê os trechos, não muda entre os grupos: as perguntas de busca certa não são só mais fáceis. A utilidade depende primeiro da busca. Busca errada tem só 9 perguntas.</p></div></div>`;
const sec4=`<div class="c7 painel"><div class=ph><h3>Correção para várias comparações (Holm) e poder <span class=selo>seção 6.10</span></h3><p>Com 9 comparações, alguma daria p &lt; 0,05 por sorte. Holm corrige isso. A última coluna é a menor diferença que 40 perguntas conseguem enxergar (poder de 80%).</p></div>
<div class=rolar><table><thead><tr><th style="padding-left:16px">comparação</th><th>diferença</th><th>p</th><th>p Holm</th><th>vale?</th><th style="padding-right:16px">menor detectável</th></tr></thead><tbody>${linH}</tbody></table></div>
<p class=mut3 style="font-size:12.5px;padding:10px 16px 14px">C − B3 em utilidade (+0,18) deixa de valer com a correção e está abaixo do que o estudo enxerga (≈ 0,22): não dá para afirmar nem descartar.</p></div>`;
const DM=F.D_minuta||{},dl=DM['llama3.1-8b']||{},dg=DM['gpt-oss-20b (cliente corrigido)']||{};
const ap=(d,c)=>{const x=(d[c]||{});return x.execucoes?`<b>${x.minuta_aprovada_no_laudo}</b> de ${x.execucoes}`:'—'};
const pg=((dg.pareado||{})['minuta aprovada no laudo']||{}).dif_media_ic95||[];
const viol=(d)=>{const v=d.violacoes_nas_reprovadas||{};return Object.entries(v).sort((a,b)=>b[1]-a[1]).slice(0,2).map(([k,n])=>`${esc(k)} (${n})`).join('; ')};
const sec5=`<div class="c12 painel"><div class=ph><h3>Por que o Adaptador cai na reserva <span class=selo>seção 6.11</span></h3><p>O rastro guarda o texto que o modelo escreveu (a minuta) antes do laudo de escopo do grupo. Lendo a minuta dá para comparar com e sem RAG mesmo quando o professor recebeu a reserva.</p></div>
<div class=rolar><table><thead><tr><th style="padding-left:16px">modelo</th><th>minuta aprovada, com RAG</th><th>sem RAG</th><th>motivo mais comum de reprovação (com RAG)</th><th style="padding-right:16px">tamanho da minuta / original</th></tr></thead><tbody>
<tr><td style="padding-left:16px"><b>Llama 3.1 8B</b> <span class=mut3>(produção, 3 rodadas)</span></td><td class=mono>${ap(dl,'completo')}</td><td class=mono>${ap(dl,'sem_rag')}</td><td>${viol(dl.completo||{})}</td><td class=mono style="padding-right:16px">${lxNum((dl.completo||{}).palavras_minuta_sobre_original_mediana,1)}× · ${lxNum((dl.sem_rag||{}).palavras_minuta_sobre_original_mediana,1)}×</td></tr>
<tr><td style="padding-left:16px"><b>gpt-oss 20B</b> <span class=mut3>(cliente corrigido, 1 rodada)</span></td><td class=mono style="color:var(--er)">${ap(dg,'completo')}</td><td class=mono>${ap(dg,'sem_rag')}</td><td>${viol(dg.completo||{})}</td><td class=mono style="padding-right:16px">${lxNum((dg.completo||{}).palavras_minuta_sobre_original_mediana,1)}× · ${lxNum((dg.sem_rag||{}).palavras_minuta_sobre_original_mediana,1)}×</td></tr></tbody></table></div>
<p class=mut3 style="font-size:12.5px;padding:10px 16px 14px">O laudo do grupo só aceita o enunciado original reorganizado; o modelo reescreve e acrescenta palavras. Com o Llama, o RAG não muda a aprovação (15 e 15). Com o gpt-oss, piora: ${lxNum(pg[0])} [${lxNum(pg[1])}; ${lxNum(pg[2])}], porque o modelo copia marcas de citação e trechos da orientação para dentro da questão. O gpt-oss corrigido é uma rodada, numa configuração que não é a do produto.</p></div>`;
return `<h2 class=lx-h2 style="margin:28px 0 4px;font:600 18px/1.3 'Space Grotesk',sans-serif">Reforço de 13/11 <span class="selo at">complementar, registrado antes de rodar</span></h2><p class=mut3 style="font-size:13px;margin:0 0 12px">Rodadas pedidas depois de ver a análise principal. Não mudam a regra nem as hipóteses: testam se as conclusões aguentam.</p>
<div class=g12>${sec1}${sec2}${sec3}${sec4}${sec5}</div>`}
