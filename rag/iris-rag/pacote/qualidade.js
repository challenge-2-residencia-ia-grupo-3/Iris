/* qualidade.js: as telas do grupo "Qualidade" (saídas 32 a 38). Embutido no painel por painel.py.
   Usa os utilitários do painel: D (dados), $, esc, cab, ic, quando. Cores: --pii vermelho (dado pessoal), --er vermelho
   (erro/reprovado), --at âmbar (aviso), --ok verde. Nada aqui chama a rede. */

function pct(v,d=0){return v==null?'—':(100*v).toFixed(d)+'%'}
function num(v,d=2){return v==null?'—':(+v).toFixed(d)}
function icTxt(a){return a&&a.length==2?`<span class=mut3 style="font-size:11.5px">IC95 ${num(a[0],2)}–${num(a[1],2)}</span>`:''}
function icPct(a){return a&&a.length==2?`<span class=mut3 style="font-size:11.5px">IC95 ${pct(a[0])}–${pct(a[1])}</span>`:''}
function vazioQ(txt,cmd){return `<div class=vazio-bloco><b>${txt}</b><br>Rode na pasta <code>pacote</code>: <code>${cmd}</code> (ou o botão no modo local).</div>`}
/* barra horizontal 0–1 com IC; cor pelo significado */
function barraQ(v,ic,cor='var(--ac)',w=180){if(v==null)return '—';const m=6,x=t=>m+Math.max(0,Math.min(1,t))*w,passou=v>1;
return `<svg width=${w+2*m+(passou?10:0)} height=14 role=img aria-label="${pct(v)}${passou?' (passou do limite)':''}"><rect x=${m} y=5 width=${w} height=4 rx=2 fill=var(--s3) />${ic?`<rect x=${x(ic[0])} y=4 width=${Math.max(2,x(ic[1])-x(ic[0]))} height=6 rx=3 fill=${cor} opacity=.35 />`:''}${passou?`<path d="M${m+w+3} 3 l6 4 l-6 4z" fill=${cor} />`:''}<circle cx=${x(v)} cy=7 r=4.5 fill=${cor} /></svg>`}
function seloPortaoQ(nome){const st=D.status||{};const p=(st.portoes||[]).find(x=>x.portao=='qualidade: '+nome);
if(!p)return '';return p.ok===false?'<span class="selo er">reprovado na verificação</span>':p.ok?'<span class="selo ok">aprovado na verificação</span>':'<span class="selo at">aviso</span>'}

/* 1 ---------------------------------------------------------------- conjunto de avaliação */
function avaliacaoSec(){const A=D.q_avaliacao,el=$('q-avaliacao');if(!el)return;
let h=cab('Conjunto de avaliação','Uma prova fixa: 166 questões dos benchmarks do grupo, lacradas por um hash. Cada commit roda a mesma prova pelo pipeline e recebe nota. Se a prova mudar, a nota deixa de ser comparável e começa uma série nova.',seloPortaoQ('conjunto de avaliação'));
if(!A){el.innerHTML=h+vazioQ('Ainda não há rodada do conjunto.','make avaliacao');return}
const ag=A.agregado||{},c=A.conjunto||{},cmp=A.comparabilidade||{};
const k=(t,v,sub,cls='')=>`<div class="c3 kpi ${cls}"><span>${t}</span><b>${v}</b><em>${sub}</em></div>`;
h+=`<div class=g12>`+k('Questões avaliadas',`${A.n_avaliados}`,`conjunto ${esc(c.versao)} · lacre ${c.lacre_intacto?'intacto':'<b style="color:var(--er)">rompido</b>'} · <code>${esc((c.sha256||'').slice(0,12))}</code>`)+
k('Rodou sem erro',pct((ag.roda_sem_erro||{}).proporcao),icPct((ag.roda_sem_erro||{}).ic95))+
k('Retenção curricular ≥ 0,95',pct((ag.trcc_aprovado||{}).proporcao,1),'conceitos da trava continuam na questão adaptada · '+icPct((ag.trcc_aprovado||{}).ic95))+
k('Laudo pega saída estragada',pct((ag.laudo_sensibilidade||{}).media),'saídas sabotadas de propósito que o laudo de escopo acusou')+`</div>`;
const linhas=[['Comando conjugado resolvido','conjugado_resolvido','questões com vários comandos que viraram passos separados'],['Aderência ao nível de apoio','aderencia_nivel','a adaptação respeita o nível 2 pedido'],['Texto mudou','mudou_texto','o resto voltou igual porque já tinha um comando só'],['Usou a saída de reserva','usou_reserva','o agente caiu no plano B'],['Extrator achou a trava','trava_recall_extrator','fração dos conceitos da trava que o Extrator listou']];
h+=`<div class=g12 style="margin-top:16px"><div class="c7 painel"><div class=ph><h3>O que a nota olha</h3><p>${esc(A.definicao_nota||'')}</p></div><table><tbody>`+linhas.map(([t,kk,s])=>{const m=ag[kk]||{};const v=m.proporcao??m.media;return `<tr><td style="padding-left:16px">${t}<div class=mut3 style="font-size:12px">${s}</div></td><td>${barraQ(v,m.ic95)}</td><td class=mono style="text-align:right;padding-right:16px">${pct(v)}<div>${icPct(m.ic95)}</div></td></tr>`}).join('')+`</tbody></table></div>`;
const disc=A.por_disciplina||{};
h+=`<div class="c5 painel"><div class=ph><h3>Por disciplina</h3><p>Retenção curricular e comando conjugado resolvido. Disciplina com poucas questões tem intervalo largo.</p></div><table><thead><tr><th style="padding-left:16px">disciplina</th><th>n</th><th>retenção</th><th>conjugado</th></tr></thead><tbody>`+
Object.entries(disc).sort((a,b)=>b[1].n_itens-a[1].n_itens).map(([d,m])=>`<tr><td style="padding-left:16px">${esc(d)}</td><td class=mono>${m.n_itens}</td><td>${barraQ((m.trcc_aprovado||{}).proporcao,(m.trcc_aprovado||{}).ic95,'var(--ok)',110)}</td><td>${barraQ((m.conjugado_resolvido||{}).proporcao,(m.conjugado_resolvido||{}).ic95,'var(--ac)',110)}</td></tr>`).join('')+`</tbody></table></div></div>`;
h+=`<div class="painel plano" style="margin-top:16px;padding:12px 16px"><b>Comparável com a rodada anterior?</b> ${cmp.comparavel===false?'<span class="selo at">não</span>':cmp.comparavel?'<span class="selo ok">sim</span>':'<span class="selo">primeira rodada</span>'} <span class=mut>${esc(cmp.motivo||'')}</span>${cmp.diferenca_nota_media!=null?` · diferença da nota: <b class=mono>${(+cmp.diferenca_nota_media).toFixed(3)}</b>`:''}<p class=mut3 style="font-size:12px;margin:6px 0 0">${esc(A.aviso||'')}</p></div>`;
const falhas=(A.itens||[]).filter(i=>!i.roda_sem_erro||!i.trcc_aprovado||!i.escopo_gabarito_aprovado);
if(falhas.length)h+=`<div class="painel" style="margin-top:16px"><div class=ph><h3>Questões que falharam · ${falhas.length}</h3></div><table><tbody>`+falhas.map(i=>`<tr><td style="padding-left:16px"><code>${esc(i.id)}</code></td><td>${esc(i.disciplina)}</td><td>${i.erro?`<span class="selo er">erro</span> ${esc(String(i.erro).slice(0,120))}`:!i.trcc_aprovado?`retenção ${num(i.trcc_adaptado)}${i.conceitos_ausentes_no_original?` · <span class="selo at">${i.conceitos_ausentes_no_original} conceito(s) da trava não estão nem no original: defeito do gabarito</span>`:''}`:'laudo de escopo reprovou'}</td></tr>`).join('')+`</tbody></table></div>`;
el.innerHTML=h}

/* 2 ---------------------------------------------------------------- juízes x pessoas */
function juizSec(){const J=D.q_juiz,el=$('q-juiz');if(!el)return;
let h=cab('Juízes x pessoas','Um juiz-modelo só vale se concordar com uma pessoa. O kappa mede essa concordância descontando o acaso: com quase tudo “sustentada”, concordar é fácil, por isso a concordância bruta engana.',seloPortaoQ('juiz calibrado contra pessoas'));
if(!J){el.innerHTML=h+vazioQ('Ainda não há calibração.','make juiz');return}
const rn=J.rotulos_necessarios||{},rh=J.rotulos_humanos||{};
const aguard=(J.estado||'').startsWith('aguardando');
h+=`<div class="alerta ${aguard?'':'ok'}" style="${aguard?'background:#3b3214;box-shadow:inset 0 0 0 1px #7a6220':''}"><div class=n>${rh.n_frases_rotuladas||0}</div><h2>${aguard?'Nenhuma nota de juiz está calibrada ainda':esc(J.estado)}</h2><ul><li>${rh.n_frases_rotuladas||0} frases rotuladas por pessoas; para o intervalo do kappa ficar com ±0,15 são precisas ~${rn.recomendado_kappa_0_6} (se o kappa real for 0,6).</li><li>Para começar: <code>make rotular</code> gera a ficha (82 frases, 3 botões, salva um arquivo); depois <code>python bancada/calibracao/rotular.py importar ARQUIVO.json</code>.</li></ul></div>`;
const pares=(J.entre_juizes||{}).pares||[];
const corT={'mesmo modelo (repeticao)':'var(--ok)','mesma familia':'var(--at)','familia diferente':'var(--ac)'};
h+=`<div class=g12 style="margin-top:16px"><div class="c8 painel"><div class=ph><h3>Concordância entre juízes · ${pares.length} pares</h3><p>Bolinha = kappa; faixa = IC95. O mesmo modelo concorda consigo mesmo; modelos diferentes quase não, mesmo com concordância bruta alta.</p></div><table><thead><tr><th style="padding-left:16px">par</th><th>tipo</th><th>bruta</th><th>kappa (−0,2 a 1)</th></tr></thead><tbody>`+
pares.slice().sort((a,b)=>b.kappa-a.kappa).map(p=>{const s=t=>(t+0.2)/1.2;return `<tr><td style="padding-left:16px"><code>${esc(p.a)}</code> × <code>${esc(p.b)}</code></td><td><span class=mut style="font-size:12px">${esc(p.tipo)}</span></td><td class=mono>${pct(p.concordancia_bruta)}</td><td style="white-space:nowrap">${barraQ(s(p.kappa),p.kappa_ic95?[s(p.kappa_ic95[0]),s(p.kappa_ic95[1])]:null,corT[p.tipo]||'var(--ac)',170)} <span class=mono>${num(p.kappa)}</span></td></tr>`}).join('')+`</tbody></table></div>`;
const tp=(J.entre_juizes||{}).tres_principais||{};
h+=`<div class="c4 painel"><div class=ph><h3>Onde eles discordam</h3></div><p style="margin:0 16px 8px">${tp.n_frases_comuns||'—'} frases julgadas pelos três principais: <b>${tp.unanimes||0}</b> unânimes, <b style="color:var(--at)">${tp.com_desacordo||0}</b> com desacordo. As com desacordo entram primeiro na ficha de rotulagem.</p><p class=mut3 style="margin:0 16px 14px;font-size:12px">${esc((J.entre_juizes||{}).leitura||'')}</p>
<div class=ph><h3>Quantos rótulos bastam</h3></div><table><tbody>`+(rn.cenarios||[]).map(c=>`<tr><td style="padding-left:16px">se o kappa real for ${c.kappa_esperado}</td><td class=mono>${c.n_frases_com_efeito_de_desenho}</td><td>${c.cabe_no_total_disponivel?'<span class="selo ok">cabe</span>':'<span class="selo at">precisa julgar mais respostas</span>'}</td></tr>`).join('')+`</tbody></table></div></div>`;
el.innerHTML=h}

/* 3 ---------------------------------------------------------------- RAG: os quatro elos + RAGAS do grupo */
let QTCFG='v1';
const ROT_ELO={busca:'busca',abstencao:'abstenção',fidelidade:'fidelidade',citacao:'citação',nenhum:'nenhum (tudo certo)'};
const SIMB_ELO={ok:'✓',quebrou:'✕',duvida:'?',nao_se_aplica:'',sem_medida:'·'};
function ragTriadeSec(){const T=D.q_rag,R=D.q_ragas,el=$('q-rag');if(!el)return;
let h=cab('RAG: os quatro elos','Para cada pergunta: a busca trouxe o trecho certo? Absteve quando devia? A resposta só diz o que o trecho diz? Cita a fonte? O primeiro elo que quebra mostra onde mexer.',seloPortaoQ('RAG: busca, fidelidade, citação, abstenção'));
if(!T){el.innerHTML=h+vazioQ('Ainda não há medição.','make rag-triade');return}
const cfgs=T.configuracoes||[],C=cfgs.find(c=>c.config==QTCFG)||cfgs[0],m=C.metricas||{};
h+=`<div class=seg role=tablist style="margin-bottom:14px">`+cfgs.map(c=>`<button class="${c.config==C.config?'on':''}" onclick="QTCFG='${c.config}';ragTriadeSec()">${esc(c.config)}</button>`).join('')+`</div><p class=mut style="margin:-6px 0 14px;font-size:13px">${esc(C.descricao||'')}</p>`;
const b=m['1_busca']||{},ci=m['3_citacao']||{},ab=m['4_abstencao']||{},fi=(m['2_fidelidade']||{}).por_juiz||{};
const k=(t,v,sub,tag)=>`<div class="c3 kpi"><span>${t} ${tag}</span><b>${v}</b><em>${sub}</em></div>`;
const det='<span class="selo ok" title="contado por código">determinístico</span>',jz='<span class="selo at" title="juiz-modelo não calibrado contra pessoas">juiz não calibrado</span>';
const f1=Object.entries(fi)[0];
h+=`<div class=g12>`+k('1 · Busca: recall@5',num((b['recall@5']||{}).v),icTxt((b['recall@5']||{}).ic95)+` · hit@5 ${(b['hit@5']||{}).k}/${(b['hit@5']||{}).n}`,det)+
k('2 · Fidelidade',f1?num(f1[1].v):'—',f1?esc(f1[0])+' · '+icTxt(f1[1].ic95):'sem juiz nesta versão',jz)+
k('3 · Frases com citação',pct((ci.prop_frases_citadas||{}).v,1),`${ci.frases_sem_citacao_total||0} sem citação · ${ci.citacoes_a_trecho_inexistente_total||0} citação a trecho inexistente`,det)+
k('4 · Abstenção certa',`${(ab.absteve_certo_sem_resposta||{}).k??'—'}/${(ab.absteve_certo_sem_resposta||{}).n??'—'}`,`absteve com o trecho certo no top-5: ${(ab.absteve_com_trecho_certo||{}).k??0}`,det)+`</div>`;
const M=(T.matriz||[]).filter(x=>x.config==C.config);const elos=['busca','abstencao','fidelidade','citacao'];
const cor={ok:'#2A4446',quebrou:'var(--er)',duvida:'var(--at)',nao_se_aplica:'transparent',sem_medida:'transparent'};
const pq=C.primeiro_elo_quebrado_contagem||{};
h+=`<div class=g12 style="margin-top:16px"><div class="c8 painel"><div class=ph><h3>Pergunta × elo · ${M.length} perguntas</h3><p>✓ ok · ✕ quebrou · ? dúvida (os juízes divergem) · vazio = não se aplica. Contorno branco = o primeiro elo que quebra naquela pergunta. Passe o mouse para o motivo.</p></div><div class=rolar style="padding:0 16px 14px"><div class=qt-mat>`+
`<span></span>`+elos.map(e=>`<span class=qt-h>${ROT_ELO[e]}</span>`).join('')+
M.map(x=>`<span class="mono qt-id">${esc(x.id)}</span>`+elos.map(e=>{const d=(x.detalhe||{})[e]||{};return `<span class="qt-c${x.primeiro_elo_quebrado==e?' prim':''}" title="${esc(x.id)} · ${ROT_ELO[e]}: ${esc(d.motivo||d.estado||x[e])}${x.primeiro_elo_quebrado==e?' (primeiro elo que quebra)':''}" style="background:${cor[x[e]]||'transparent'};${x[e]=='sem_medida'||x[e]=='nao_se_aplica'?'box-shadow:inset 0 0 0 1px var(--bd2)':''}">${SIMB_ELO[x[e]]??''}</span>`}).join('')).join('')+
`</div></div></div><div class="c4 painel"><div class=ph><h3>Primeiro elo que quebra</h3><p>Contorno branco na matriz. É por onde começar.</p></div><table><tbody>`+Object.entries(pq).map(([e,n])=>`<tr><td style="padding-left:16px">${ROT_ELO[e]||e}</td><td class=mono style="text-align:right;padding-right:16px">${n}</td></tr>`).join('')+`</tbody></table>`;
if(R){const pc=R.precisao_contexto||{};h+=`<div class=ph style="margin-top:8px"><h3>RAGAS do grupo</h3><p>${esc(R.credito||'')}. Biblioteca ${esc(R.ragas_versao||'')}.</p></div><table><tbody><tr><td style="padding-left:16px">Context Precision (RAGAS)<div class=mut3 style="font-size:12px">${esc(pc.leitura||'')}</div></td><td class=mono style="text-align:right;padding-right:16px">${num(pc.media)}<div>${icTxt(pc.ic95)}</div><div class=mut3 style="font-size:11.5px">teto ${num(pc.teto_medio)}</div></td></tr>`+
Object.entries((R.fidelidade_por_frase||{}).por_gerador||{}).map(([g,d])=>`<tr><td style="padding-left:16px">Fidelidade por frase · ${esc(g)}<div class=mut3 style="font-size:12px">${esc(d.leitura)} (meta ${num((R.fidelidade_por_frase||{}).meta)})</div></td><td class=mono style="text-align:right;padding-right:16px">${num(d.fidelidade_final.media)}<div>${icTxt(d.fidelidade_final.ic95)}</div></td></tr>`).join('')+`</tbody></table>`}
else h+=`<div style="padding:0 16px 14px">${vazioQ('Métricas RAGAS do grupo ainda não rodadas.','make ragas')}</div>`;
h+=`</div></div><p class=mut3 style="font-size:12px;margin-top:10px">${esc((T.origem_dos_numeros||{}).aviso||'')} ${esc((T.gabarito||{}).aviso||'')}</p>`;
el.innerHTML=h}

/* 4 ---------------------------------------------------------------- ataque em massa */
function ataqueSec(){const X=D.q_ataque,el=$('q-ataque');if(!el)return;
let h=cab('Ataque em massa','Centenas de variações sintéticas de dado pessoal, dado clínico e injeção, passadas pelo filtro real do grupo. Vermelho = dado pessoal que passou. Cada padrão traz o menor caso que o reproduz, pronto para virar issue.',seloPortaoQ('ataque em massa (dados pessoais)'));
if(!X){el.innerHTML=h+vazioQ('Ainda não há rodada de ataque.','make ataque');return}
const vm=(X.vazamento||{}).material||{},vp=(X.vazamento||{}).perfil||{},fp=((X.falso_positivo||{}).material||{}).geral||{},ev=(X.vazamento||{}).evasao||{};
const k=(t,tx,sub,cls='')=>`<div class="c3 kpi ${cls}"><span>${t}</span><b>${tx}</b><em>${sub}</em></div>`;
h+=`<div class=g12>`+k('Vazou no material',pct((vm.geral||{}).taxa),`${(vm.geral||{}).k}/${(vm.geral||{}).n} casos · `+icPct((vm.geral||{}).ic95),'pii')+
k('Perfil aceitou dado clínico',pct((vp.so_clinico||{}).taxa),`${(vp.so_clinico||{}).k}/${(vp.so_clinico||{}).n} · `+icPct((vp.so_clinico||{}).ic95),'pii')+
k('Dribla um bloqueio que existe',pct((ev.geral||{}).taxa),`letras espaçadas, caractere invisível, cirílico · ${(ev.geral||{}).k}/${(ev.geral||{}).n}`,'pii')+
k('Apagou conteúdo que devia ficar',pct(fp.taxa),`falso positivo nos controles · ${fp.k}/${fp.n}`)+`</div>`;
const fam=vm.por_familia||{};
h+=`<div class=g12 style="margin-top:16px"><div class="c5 painel"><div class=ph><h3>Por tipo de dado</h3><p>Fração que passou pelo filtro.</p></div><table><tbody>`+Object.entries(fam).sort((a,b)=>b[1].taxa-a[1].taxa).map(([f,d])=>`<tr><td style="padding-left:16px">${esc(f)}</td><td>${barraQ(d.taxa,d.ic95,'var(--pii)',150)}</td><td class=mono style="text-align:right;padding-right:16px">${pct(d.taxa)} <span class=mut3>${d.k}/${d.n}</span></td></tr>`).join('')+`</tbody></table>`;
const pr=X.promessa_do_grupo||[];
h+=`<div class=ph style="margin-top:8px"><h3>O que o filtro promete cobrir</h3><p>Lido das regras do filtro do grupo. Se uma promessa quebrar, o portão reprova.</p></div><table><tbody>`+pr.map(p=>`<tr><td style="padding-left:16px">${ic(p.cumpre?'ok':'er')} ${esc(p.tipo)}</td><td class=mut style="font-size:12px">${esc(p.promessa||'')}</td></tr>`).join('')+`</tbody></table></div>`;
const pad=X.padroes||[];
h+=`<div class="c7 painel"><div class=ph><h3>Padrões de vazamento · ${pad.length}</h3><p>Do mais grave para o menos. Abra para ver o menor caso que reproduz.</p></div><div style="padding:0 16px 14px;max-height:620px;overflow:auto">`+
pad.map(p=>`<details class=qa-pad><summary><span class="selo ${['grave','alta'].includes(p.gravidade)&&p.grupo!='injecao'?'pii':'at'}">${esc(p.gravidade||'')}${p.grupo!='injecao'?' · dado pessoal':' · injeção'}</span> ${esc(p.descricao)} <span class="mono mut3">${p.k}/${p.n}</span></summary>${p.caso_minimo?`<p class=mut3 style="font-size:12px;margin:6px 0 4px">rota <code>${esc(p.caso_minimo.rota||'')}</code> · formato ${esc(p.caso_minimo.formato||'')} · dado sintético <mark class=pii>${esc(p.caso_minimo.dado_sintetico||'')}</mark></p><pre style="max-height:140px">${marca(p.caso_minimo.saida_do_filtro||p.caso_minimo.texto||'',[p.caso_minimo.dado_sintetico])}</pre>`:''}</details>`).join('')+`</div></div></div>`;
el.innerHTML=h}

/* 5 ---------------------------------------------------------------- orçamento */
function orcamentoSec(){const O=D.q_orcamento,el=$('q-orcamento');if(!el)return;
let h=cab('Orçamento de tempo, tokens e custo','Cada etapa contra o limite. Os limites vêm do RNF-07 (tempo) e do RNF-08 (tokens) do grupo; o que não vem deles está marcado como proposta da bancada. Sem modelo, um substituto faz o papel do LLM: o tempo aqui só informa. A projeção usa medições reais do grupo com modelo.',seloPortaoQ('orçamento (RNF-07 e RNF-08)'));
if(!O){el.innerHTML=h+vazioQ('Ainda não há conferência do orçamento.','make orcamento');return}
const pt=O.portao||{},est=pt.projecao_modelo_real_estoura||[];
h+=`<div class=g12><div class="c3 kpi"><span>Estouros duros</span><b style="color:${pt.n_duros?'var(--er)':'var(--ok)'}">${pt.n_duros||0}</b><em>chamadas ao modelo e tokens (RNF-08)</em></div><div class="c3 kpi"><span>Alertas</span><b style="color:var(--at)">${pt.n_alertas||0}</b><em>só avisam</em></div><div class="c6 kpi" style="border-color:${est.length?'#7a6220':'var(--bd)'}"><span>Projeção com modelo real (RNF-07)</span><b style="color:${est.length?'var(--at)':'var(--ok)'}">${est.length} cenários estouram</b><em>${esc(est.slice(0,2).join(' · '))}${est.length>2?' …':''}</em></div></div>`;
const E=O.por_etapa||[];
h+=`<div class=g12 style="margin-top:16px"><div class="c7 painel"><div class=ph><h3>Por etapa</h3><p>p95 medido x limite. A barra mostra quanto do limite foi usado.</p></div><div class=rolar><table><thead><tr><th style="padding-left:16px">etapa</th><th>p95</th><th>limite</th><th>uso</th><th>tokens entrada (máx)</th></tr></thead><tbody>`+
E.map(e=>{const u=e.limite_latencia_p95_s?e.latencia_p95_s/e.limite_latencia_p95_s:null;return `<tr><td style="padding-left:16px"><code>${esc(e.etapa)}</code><div class=mut3 style="font-size:11.5px" title="${esc(e.fonte_limite||'')}">${esc((e.fonte_limite||'').slice(0,60))}${(e.fonte_limite||'').length>60?'…':''}</div></td><td class=mono>${num(e.latencia_p95_s,3)} s</td><td class=mono>${e.limite_latencia_p95_s??'—'} s</td><td>${u==null?'—':barraQ(u,null,u>1?'var(--er)':'var(--ok)',90)}</td><td class=mono>${e.tokens_entrada_max??'—'}${e.limite_tokens_entrada?` / ${e.limite_tokens_entrada}`:''}</td></tr>`}).join('')+`</tbody></table></div></div>`;
const P=O.projecao_modelo_real||{},cen=(P.resultado||[]);
h+=`<div class="c5 painel"><div class=ph><h3>Projeção com modelo real</h3><p>${esc(P.aviso||'')}</p></div><div class=rolar><table><thead><tr><th style="padding-left:16px">cenário</th><th>nível</th><th>questões</th><th>p95</th><th>limite</th></tr></thead><tbody>`+
(Array.isArray(cen)?cen:[]).map(c=>`<tr><td style="padding-left:16px">${esc((c.cenario||'').replaceAll('_',' '))}</td><td class=mono>${c.nivel??''}</td><td class=mono>${c.n_questoes??''}</td><td class=mono style="color:${c.folga_p95_s<0?'var(--at)':'inherit'}">${num(c.p95_s,1)} s</td><td class=mono>${c.limite_s??''} s</td></tr>`).join('')+`</tbody></table></div><p class=mut3 style="font-size:12px;margin:8px 16px 14px">${esc(O.aviso_tempo||'')}</p></div></div>`;
el.innerHTML=h}

/* 6 ---------------------------------------------------------------- produção */
function producaoSec(){const P=D.q_producao,el=$('q-producao');if(!el)return;
let h=cab('Produção: o retorno da professora','Proposta para quando o Íris estiver no ar: registrar só metadados (nunca o material nem nomes) e o que a professora fez com cada adaptação. Os números abaixo são sintéticos: mostram como a tela ficaria, não medem uso real.',seloPortaoQ('rastro de produção sem dado pessoal'));
if(!P){el.innerHTML=h+vazioQ('Ainda não há simulação.','make producao');return}
const m=P.metricas||{},g0=m.geral||{},c=P.conferencia_no_codigo_do_grupo||{};
h+=`<div class="alerta" style="background:#3b3214;box-shadow:inset 0 0 0 1px #7a6220"><div class=n>!</div><h2>Dados sintéticos</h2><ul><li>${esc(P.aviso_sintetico||'')}</li><li>Proposta completa em <code>bancada/producao/PROPOSTA.md</code> (o que gravar, o que nunca gravar, retenção, como desligar), ligada aos RNFs e às issues #35 e #37 do grupo.</li></ul></div>`;
const k=(t,v,sub)=>`<div class="c3 kpi"><span>${t}</span><b>${v}</b><em>${sub}</em></div>`;
h+=`<div class=g12 style="margin-top:16px">`+k('Aceitou (com ou sem edição)',pct((g0.aceite_com_ou_sem_edicao||{}).p),icPct((g0.aceite_com_ou_sem_edicao||{}).ic95))+k('Aceitou sem mexer',pct((g0.aceite_sem_edicao||{}).p),icPct((g0.aceite_sem_edicao||{}).ic95))+k('Quando editou, mudou',(g0.edicao_media_pct_quando_editou||{}).media!=null?num(g0.edicao_media_pct_quando_editou.media,1)+'%':'—','do texto, em média')+
k('Privacidade do registro',`${c.tentativas_recusadas??'—'}/${c.tentativas_total??'—'}`,`tentativas de vazamento recusadas · ${c.pii_vazado_no_rastro??'—'} dado pessoal no rastro`)+`</div>`;
h+=`<div class=g12 style="margin-top:16px"><div class="c7 painel"><div class=ph><h3>Por característica</h3><p>Taxa de aceite por característica do aluno. Células com menos de ${m.k_min_supressao||5} casos são escondidas.</p></div><table><tbody>`+(m.por_caracteristica||[]).map(x=>`<tr><td style="padding-left:16px"><code>${esc(x.caracteristica)}</code> <span class=mut3>${x.n_retornos}</span></td><td>${x.aceite_com_ou_sem_edicao&&!x.aceite_com_ou_sem_edicao.suprimido?barraQ(x.aceite_com_ou_sem_edicao.p,x.aceite_com_ou_sem_edicao.ic95,'var(--ok)',170):'<span class=mut3>suprimido</span>'}</td><td class=mono style="text-align:right;padding-right:16px">${x.aceite_com_ou_sem_edicao&&!x.aceite_com_ou_sem_edicao.suprimido?pct(x.aceite_com_ou_sem_edicao.p):''}</td></tr>`).join('')+`</tbody></table></div>`;
h+=`<div class="c5 painel"><div class=ph><h3>Por que recusou</h3><p>Lista fechada de motivos (sem texto livre).</p></div><table><tbody>`+(m.recusas_por_motivo||[]).map(x=>`<tr><td style="padding-left:16px">${esc(x.motivo.replaceAll('_',' '))}</td><td class=mono style="text-align:right;padding-right:16px">${x.contagem??x.k}</td></tr>`).join('')+`</tbody></table></div></div>`;
el.innerHTML=h}

function qualidadeTudo(){avaliacaoSec();juizSec();ragTriadeSec();ataqueSec();orcamentoSec();producaoSec()}
