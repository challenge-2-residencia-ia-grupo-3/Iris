"""painel.py: gera o HTML da bancada (tema escuro, superfície de monitoramento). Ver ../bancada/DESIGN.md.

Usado por bancada.py (etapa html). Recebe os dados já montados e devolve UMA página, sem chamar ninguém de fora:
as fontes IBM Plex e o d3-force (para o grafo do código) vão embutidos a partir de ../bancada/vendor (licenças OFL e
ISC, cópias ao lado). Quando servida pelo vigia, a página consulta status.json a cada minuto.

Cores com significado fixo (legenda no rodapé da navegação):
  vermelho  = erro: portão reprovado, regressão de métrica, etapa que quebrou
  vermelho + cadeado = dado pessoal (LGPD): tudo que é do filtro de dados pessoais, e em destaque quando algo vaza
  âmbar     = atenção (falso positivo, injeção que sobrevive, parcial, sem teste)
  azul-esverdeado apagado = passou;  violeta = navegação/seleção
"""
from __future__ import annotations

import base64
import html
import json

import guia
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "bancada" / "vendor"

GRAVIDADE = {"pii": "grave", "injecao": "atencao", "formato": "atencao"}


def achados(dados: dict) -> list[dict]:
    """Achados derivados por regra escrita (não escolhidos à mão):
    dado pessoal/clínico que passa pelo filtro = grave + tipo 'pii' (vermelho);
    falso positivo que apaga conteúdo e injeção que sobrevive = atenção;
    portão reprovado e regressão de métrica = grave + tipo 'erro' (vermelho)."""
    out = []
    for c in dados.get("adversarial_casos") or []:
        if c.get("aprovado"):
            continue
        motivos = c.get("motivos") or []
        vazou = [m.split("'", 2)[1] for m in motivos if "sobrou:" in m and m.count("'") >= 2]
        falso_pos = "falso positivo" in (c.get("descricao") or "") + " ".join(motivos)
        nivel = "atencao" if falso_pos else GRAVIDADE.get(c.get("categoria"), "atencao")
        pii = c.get("categoria") == "pii"
        out.append({"nivel": nivel, "tipo": "pii" if pii and not falso_pos else ("erro" if nivel == "grave" else "atencao"),
                    "area": "Filtro de dados pessoais" if pii else "Pipeline",
                    "titulo": c.get("descricao", c["id"]), "id": c["id"], "vazou": vazou, "motivos": motivos,
                    "texto": c.get("saida_sanitizada", "")})
    st = dados.get("status") or {}
    for p in st.get("portoes", []):
        if p.get("ok") is False:
            out.append({"nivel": "grave", "tipo": "erro", "area": "Atualização automática", "titulo": f"portão reprovado: {p['portao']}",
                        "id": st.get("commit_grupo", ""), "vazou": [], "motivos": [p.get("detalhe", "")[:400]], "texto": ""})
    if dados.get("regressao") and "FALHOU" in dados["regressao"]:
        out.append({"nivel": "grave", "tipo": "erro", "area": "Métricas", "titulo": "regressão: alguma métrica caiu abaixo da linha de base",
                    "id": "", "vazou": [], "texto": "",
                    "motivos": [l for l in dados["regressao"].splitlines() if l.strip().startswith("CAIU")]})
    ordem = {"grave": 0, "atencao": 1}
    return sorted(out, key=lambda a: (ordem[a["nivel"]], a["tipo"] != "pii"))


CSS = r"""
:root{--bg:#18181C;--s1:#1F1F25;--s2:#26262E;--s3:#2F2F39;--bd:#2F2F38;--bd2:#3E3E4A;
--tx:#EDEDF2;--tx2:#B4B4C2;--tx3:#8A8A9A;--ac:#A68BFF;--acf:#723BFA;--acbg:#251B40;
--ok:#34D399;--okbg:#0F2A20;--okbd:#1F6B4A;--at:#E5B443;--atbg:#2E260F;--atbd:#5C4A17;
--er:#FF6B6B;--erbg:#35171B;--erbd:#6B2A33;--pii:#FF6B6B;--piibg:#35171B;--piibd:#8A3340;
--sh1:0 1px 0 rgba(255,255,255,.05) inset,0 1px 2px rgba(0,0,0,.45),0 12px 28px -14px rgba(0,0,0,.75);
--sh2:0 1px 0 rgba(255,255,255,.05) inset,0 2px 4px rgba(0,0,0,.35),0 18px 40px -18px rgba(0,0,0,.7);
--tit:"Space Grotesk","IBM Plex Sans",system-ui,sans-serif;
--r1:6px;--r2:12px;--ease:cubic-bezier(.2,.7,.2,1);--lado:244px}
*{box-sizing:border-box}html{color-scheme:dark;scroll-padding-top:64px}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
font-feature-settings:"tnum" 1;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
code,.mono,pre,kbd{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
code{font-size:.92em;color:#d5dbe4}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--ac);outline-offset:2px;border-radius:4px}
button{font:inherit;color:inherit}
.app{display:grid;grid-template-columns:var(--lado) minmax(0,1fr);min-height:100vh}

/* navegação */
.lado{position:sticky;top:0;height:100vh;overflow:auto;border-right:1px solid var(--bd);background:var(--s1);padding:20px 12px 16px;display:flex;flex-direction:column}
.marca{display:flex;align-items:center;gap:10px;padding:0 8px}.marca i{width:22px;height:22px;border-radius:6px;background:conic-gradient(from 200deg,#723BFA,#A68BFF,#5FB8C8,#723BFA);display:block}
.marca b{font:600 18px/1.1 var(--tit);letter-spacing:-.2px}.marca small{display:block;color:var(--tx3);font-size:12px;font-weight:400;line-height:1.2}
.lado nav{margin-top:20px;display:flex;flex-direction:column;gap:1px}
.lado .grupo-nav{display:flex;align-items:center;gap:8px;font:600 11.5px/1 var(--tit);color:var(--tx);text-transform:uppercase;letter-spacing:.12em;padding:20px 10px 8px}.lado .grupo-nav::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--bd2),transparent)}.lado .grupo-nav:first-child{padding-top:4px}
.lado nav button{all:unset;cursor:pointer;display:flex;align-items:center;gap:8px;min-height:34px;padding:0 10px;border-radius:var(--r1);color:var(--tx2);font-size:13.5px;transition:background .15s,color .15s}
.lado nav button span.r{flex:1}
.lado nav button:hover{background:var(--s2);color:var(--tx)}.lado nav button.on{background:var(--acbg);color:#fff;font-weight:500;box-shadow:inset 3px 0 0 var(--acf)}
.cont{font:600 11px/1 "IBM Plex Mono",monospace;padding:4px 7px;border-radius:20px;background:var(--s3);color:var(--tx2)}
.cont.er{background:var(--erbg);color:var(--er);box-shadow:inset 0 0 0 1px var(--erbd)}.selo.pii::before,.cont.pii::before{content:"";width:10px;height:10px;flex:none;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='%23FF6B6B' d='M5 7V5a3 3 0 0 1 6 0v2h1v7H4V7zm1.5 0h3V5a1.5 1.5 0 0 0-3 0z'/%3E%3C/svg%3E") center/contain no-repeat}.cont.pii{display:inline-flex;align-items:center;gap:3px;background:var(--piibg);color:var(--pii);box-shadow:inset 0 0 0 1px var(--piibd)}
.legenda{margin-top:auto;padding:14px 10px 4px;border-top:1px solid var(--bd);font-size:12px;color:var(--tx2);display:grid;gap:6px}
.legenda b{font:500 11px/1 "IBM Plex Mono",monospace;color:var(--tx3);letter-spacing:.3px;margin-bottom:2px}
.legenda span{display:flex;align-items:center;gap:8px}.legenda p{margin:8px 0 0;color:var(--tx3);font-size:11.5px;line-height:1.45}
.sw{width:10px;height:10px;border-radius:3px;display:inline-block;flex:none}
.sw.er{background:var(--er)}.sw.pii{background:var(--pii)}.sw.at{background:var(--at)}.sw.ok{background:var(--ok)}.sw.ac{background:var(--ac)}.sw.neu{background:#4a5260}

/* topo */
main{min-width:0;padding:0 32px 72px}
.topo{position:sticky;top:0;z-index:8;background:rgba(24,24,28,.94);backdrop-filter:blur(8px);backdrop-filter:saturate(1.2);border-bottom:1px solid var(--bd);
margin:0 -32px;padding:10px 32px;display:flex;align-items:center;gap:0;font-size:12.5px;color:var(--tx2);min-height:52px}
.topo>span{display:flex;align-items:center;gap:8px;padding:0 16px;border-left:1px solid var(--bd);white-space:nowrap;min-width:0}
.topo>span:first-child{padding-left:0;border-left:0}.topo b{color:var(--tx);font-weight:600}
.topo .tit{overflow:hidden;text-overflow:ellipsis;max-width:42ch;color:var(--tx2)}
.estado-pill{display:inline-flex;align-items:center;gap:7px;height:26px;padding:0 10px;border-radius:20px;font-weight:600;font-size:12.5px}
.estado-pill.ok{background:var(--okbg);color:var(--ok);box-shadow:inset 0 0 0 1px var(--okbd)}.estado-pill.er{background:var(--erbg);color:var(--er);box-shadow:inset 0 0 0 1px var(--erbd)}
.estado-pill.neu{background:var(--s3);color:var(--tx2)}
.ponto{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none;background:currentColor}
.novo{display:none;margin-left:auto;background:transparent;border:1px solid var(--bd2);color:var(--tx2);padding:5px 12px;border-radius:20px;cursor:pointer}

/* faixas de alerta */
.alerta{margin:20px 0 0;display:grid;grid-template-columns:auto 1fr auto;gap:2px 18px;align-items:center;border-radius:var(--r2);padding:14px 18px;animation:pulso 1.4s var(--ease) 1}
.alerta.er{background:#4a1f26;box-shadow:inset 0 0 0 1px #8a3340;--pulso:rgba(255,107,107,.45)}
.alerta.pii{background:#4a1f26;box-shadow:inset 0 0 0 1px #8a3340;--pulso:rgba(255,107,107,.45)}
.alerta .n{grid-row:span 2;font:700 30px/1 var(--tit);color:#fff;border-radius:8px;padding:9px 13px;min-width:52px;text-align:center}
.alerta.er .n{background:#b23a48}.alerta.pii .n{background:var(--pii);color:#18181C}
.alerta h2{margin:0;font:600 16px/1.3 var(--tit);color:#fff;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.alerta ul{margin:2px 0 0;padding-left:18px;color:#DCDCE6;font-size:13px}
.alerta .btn{grid-row:span 2}.alerta.pii .btn.claro{background:var(--pii);color:#18181C}.alerta.pii .btn.claro:hover{background:#FF8A8A}.alerta.pii .selo.pii{background:transparent;box-shadow:inset 0 0 0 1px #8a3340}.alerta{padding:16px 20px}
.qt-mat{display:grid;grid-template-columns:44px repeat(4,minmax(54px,1fr));gap:3px;min-width:320px}.qt-h{font:11px 'IBM Plex Mono',monospace;color:var(--tx3);text-align:center;padding-bottom:4px}.qt-id{font-size:11px;color:var(--tx2);align-self:center}.qt-c{height:16px;border-radius:3px;display:grid;place-items:center;font:600 10px/1 'IBM Plex Mono',monospace;color:#18181C}.qt-c.prim{box-shadow:0 0 0 2px #fff!important;position:relative;z-index:1}
.kpi.pii b{color:var(--pii)}
details.qa-pad{border-bottom:1px solid var(--bd);padding:8px 0}details.qa-pad summary{cursor:pointer;font-size:13px;line-height:1.5}details.qa-pad pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}details.qa-pad code,details.qa-pad p{overflow-wrap:anywhere}
mark.pii,.qa-pad mark{background:var(--piibg);color:var(--pii);box-shadow:inset 0 0 0 1px var(--piibd);border-radius:3px;padding:0 2px}
body.compacto .alerta{padding:8px 14px;margin-top:12px;animation:none}body.compacto .alerta ul{display:none}body.compacto .alerta .n{font-size:16px;padding:5px 9px;min-width:0;grid-row:auto}body.compacto .alerta .btn{grid-row:auto;height:28px}body.compacto .alerta h2{font-size:13.5px}
@keyframes pulso{0%{box-shadow:0 0 0 0 var(--pulso)}100%{box-shadow:0 0 0 12px transparent}}

/* botões e selos */
.btn{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:var(--r1);font-weight:600;font-size:13px;white-space:nowrap;transition:background .15s,border-color .15s}
.btn.claro{background:#EDEDF2;color:#18181C}.btn.claro:hover{background:#fff}
.btn.sec{border:1px solid var(--bd2);color:var(--tx);background:var(--s2)}.btn.sec:hover{border-color:var(--ac)}
.btn.mini{height:28px;padding:0 10px;font-size:12.5px;font-weight:500}
.seg{display:inline-flex;background:var(--s2);border:1px solid var(--bd);border-radius:8px;padding:3px;gap:2px}
.seg button{all:unset;cursor:pointer;height:28px;padding:0 12px;border-radius:6px;color:var(--tx2);font-size:13px}.seg button.on{background:var(--s3);color:var(--tx);box-shadow:0 1px 0 rgba(255,255,255,.04) inset}
.selo{display:inline-flex;align-items:center;gap:5px;font:600 11px/1 "IBM Plex Mono",monospace;padding:4px 8px;border-radius:20px;color:var(--tx2);background:var(--s3);white-space:nowrap}
.selo.er{color:var(--er);background:var(--erbg);box-shadow:inset 0 0 0 1px var(--erbd)}.selo.at{color:var(--at);background:var(--atbg);box-shadow:inset 0 0 0 1px var(--atbd)}
.selo.ok{color:var(--ok);background:var(--okbg);box-shadow:inset 0 0 0 1px var(--okbd)}.selo.pii{color:var(--pii);background:var(--piibg);box-shadow:inset 0 0 0 1px var(--piibd)}
.selo.ac{color:var(--ac);background:var(--acbg)}
.iss{font:500 11px/1 "IBM Plex Mono",monospace;padding:3px 6px;border-radius:4px;background:var(--s3);color:var(--tx2);white-space:nowrap}
.iss.open{color:var(--at);background:var(--atbg)}.iss.closed{color:var(--ok);background:var(--okbg)}

/* seções e grade de 12 colunas */
section.sec{display:none;padding-top:28px}section.sec.on{display:block}section.sec.on .cab{animation:entra .32s var(--ease) both}section.sec.on .g12>*,section.sec.on>div>.painel,section.sec.on .guia-fluxo{animation:entra .42s var(--ease) both;animation-delay:calc(var(--i,0)*35ms + 60ms)}
@keyframes entra{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes acende{0%,100%{box-shadow:var(--sh1),inset 3px 0 0 var(--pii),0 0 0 0 rgba(185,245,0,0)}50%{box-shadow:var(--sh1),inset 3px 0 0 var(--pii),0 0 0 4px rgba(185,245,0,.14)}}
body.compacto .alerta.pii{animation:acende 2.8s ease-in-out 1}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
.cab{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:20px;flex-wrap:wrap}
h1{font:600 34px/1.1 var(--tit);margin:0 0 10px;letter-spacing:-.8px}
*{scrollbar-width:thin;scrollbar-color:#3E3E4A transparent}::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:#3E3E4A;border-radius:8px;border:2px solid var(--bg)}::-webkit-scrollbar-track{background:transparent}.sub{color:var(--tx2);margin:0;max-width:92ch}
h3{font:600 15.5px/1.3 var(--tit);margin:0;letter-spacing:-.1px}.ph{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.ph p{margin:4px 0 0;color:var(--tx3);font-size:12.5px;flex-basis:100%;line-height:1.5}
.g12{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:16px;align-items:stretch}.g12>.painel.alto-livre{align-self:start}
.c3{grid-column:span 3}.c4{grid-column:span 4}.c5{grid-column:span 5}.c6{grid-column:span 6}.c7{grid-column:span 7}.c8{grid-column:span 8}.c9{grid-column:span 9}.c12{grid-column:span 12}
.estica{align-self:stretch}
.painel{background:var(--s1);border:1px solid var(--bd);border-radius:var(--r2);padding:18px 20px;min-width:0;box-shadow:var(--sh1)}
.painel.plano{padding:0;overflow:hidden}
.kpi.ok{border-color:var(--okbd);background:linear-gradient(180deg,var(--okbg),var(--s1) 70%)}.kpi.ok>span:first-child::before{content:"✓";display:inline-grid;place-items:center;width:16px;height:16px;margin-right:6px;border-radius:50%;background:var(--ok);color:#06281A;font:700 10px/1 "IBM Plex Mono",monospace;vertical-align:1px}.selo.ok::before{content:"✓";font-weight:700}.kpi{background:var(--s1);border:1px solid var(--bd);border-radius:var(--r2);padding:16px 18px;min-height:124px;display:flex;flex-direction:column;box-shadow:var(--sh1);overflow-wrap:anywhere;transition:transform .2s var(--ease),box-shadow .2s var(--ease),border-color .2s}.kpi:hover{transform:translateY(-2px);box-shadow:var(--sh2);border-color:var(--bd2)}
.kpi span{color:var(--tx2);font-size:12.5px}.kpi b{display:block;font:600 30px/1.1 var(--tit);letter-spacing:-.5px;margin:8px 0 4px;color:var(--tx)}
.kpi em{font-style:normal;color:var(--tx3);font-size:12px;margin-top:auto}
.kpi.pii{border-color:var(--bd);background:var(--s1);box-shadow:var(--sh1),inset 3px 0 0 var(--pii)}.kpi.er{border-color:var(--erbd)}
.barra-cob{height:6px;border-radius:4px;background:var(--s3);overflow:hidden;margin:6px 0 2px}.barra-cob i{display:block;height:100%;background:#3E5E61}
.ok{color:var(--ok)}.at{color:var(--at)}.er{color:var(--er)}.pii{color:var(--pii)}.mut{color:var(--tx2)}.mut3{color:var(--tx3)}

/* tabelas */
table{border-collapse:collapse;width:100%;font-size:13px}
th{color:var(--tx3);font-weight:500;text-align:left;font-size:12px;padding:8px 10px;border-bottom:1px solid var(--bd);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--bd);vertical-align:top}tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:rgba(255,255,255,.018)}td.num,th.num{font-family:"IBM Plex Mono",monospace;white-space:nowrap;text-align:right}
.rolar{overflow-x:auto;max-width:100%}.painel{overflow-wrap:anywhere}details.painel{display:block;width:100%;grid-column:1/-1}details.painel>summary{cursor:pointer;font:600 15px/1.3 var(--tit)}.painel span{min-width:0}

pre{white-space:pre-wrap;font-size:12.5px;line-height:1.55;background:var(--bg);border:1px solid var(--bd);border-radius:var(--r1);padding:10px 12px;max-height:360px;overflow:auto;margin:0;color:#d6dce5}
.chip{display:inline-flex;align-items:center;gap:4px;height:26px;padding:0 8px;margin:2px 4px 2px 0;border-radius:var(--r1);cursor:pointer;font:500 11.5px/1 "IBM Plex Mono",monospace;
border:1px solid var(--bd2);background:var(--s3);color:#cdd3dc;transition:transform .12s,border-color .12s}
.chip:hover{transform:translateY(-1px);border-color:var(--ac)}.chip.R{background:#1D3335;border-color:#3E6466;color:#D8EEEF}.chip.p{background:#3d3112;border-color:#7a6220;color:#ffeab3}
.chip.sel{outline:2px solid var(--ac);outline-offset:1px}
mark{background:#5A1A22;color:#FFE3E3;border-radius:3px;padding:1px 4px;box-shadow:0 0 0 1px #C2414F;font-weight:500}
.vazio{color:var(--tx3);font-style:italic}
.vazio-bloco{border:1px dashed var(--bd2);border-radius:var(--r1);padding:16px;color:var(--tx2);font-size:13px}.vazio-bloco b{color:var(--tx)}
.ic{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;font:700 11px/1 "IBM Plex Mono",monospace;flex:none}
.ic.ok{background:var(--okbg);color:var(--ok)}.ic.er{background:var(--erbg);color:var(--er)}.ic.at{background:var(--atbg);color:var(--at)}.ic.neu{background:var(--s3);color:var(--tx3)}.ic.pii{background:var(--piibg);color:var(--pii)}

/* matriz de portões */


.mat{display:flex;gap:10px 14px;align-items:center;flex-wrap:wrap}.fase{width:calc(var(--n)*16px + 6px);min-width:64px;flex:none;display:flex;flex-direction:column;gap:3px}
.mat-cab .fase{font:500 11.5px/1.2 "IBM Plex Sans",sans-serif;color:var(--tx2);flex-direction:row;gap:4px;align-items:baseline;white-space:nowrap}.mat-cab .fase small{color:var(--tx3);font:10px "IBM Plex Mono",monospace}
.fase-cel{display:flex;flex-direction:column;gap:3px}.fq{display:flex;gap:3px;flex-wrap:nowrap}.leg-mat{font-size:12px;display:inline-flex;flex-wrap:wrap;gap:14px;align-items:center}.fq i{width:13px;height:13px;border-radius:3px;display:grid;place-items:center;font:700 9px/1 "IBM Plex Mono",monospace;font-style:normal}.fn{font:11px "IBM Plex Mono",monospace;color:var(--tx3)}.fn.er{color:var(--er);font-weight:600}
.fq i.ok{background:var(--ok)}.fq i.ok::after{content:"✓";color:#06281A}.fq i.er{background:var(--er)}.fq i.er::after{content:"✕";color:#2A0F12}.fq i.neu::after{content:"–";color:#9A9AAE}.fq i.neu{background:#3c4452}.fq i.nr{box-shadow:inset 0 0 0 1px var(--bd2)}
tr.rod{cursor:pointer}tr.rod:hover td{background:var(--s2)}tr.rod-aberta td{background:var(--s2)}.rod-det{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px 20px;padding:10px 4px 6px}.rod-det b{display:block;font-size:12px;color:var(--tx2);margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em}
.dica-balao{position:fixed;z-index:200;display:none;max-width:300px;padding:8px 11px;border-radius:8px;background:#e9edf2;color:#10141a;font:400 12.5px/1.45 "IBM Plex Sans",sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.45);pointer-events:none;white-space:normal;text-transform:none;letter-spacing:0}
.tem-dica{cursor:help;text-decoration:underline dotted color-mix(in srgb,currentColor 45%,transparent);text-underline-offset:3px}.selo.tem-dica,.cont.tem-dica,.mat-cab .fase.tem-dica{text-decoration:none}.tem-dica:focus-visible{outline:2px solid var(--ac);outline-offset:2px;border-radius:3px}
.lg-svg{display:block;max-width:none}.lg-faixa{fill:var(--tx3);font:600 10.5px "IBM Plex Mono",monospace;letter-spacing:.06em;text-transform:uppercase}.lg-no{cursor:help}.lg-no rect:first-child{fill:var(--s2);stroke-width:1.2}.lg-no text{fill:var(--tx);font:500 12px "IBM Plex Sans",sans-serif}.lg-no .lg-sub{fill:var(--tx3);font:400 10.5px "IBM Plex Mono",monospace}.lg-no.fora{opacity:.35}.lg-no.on rect:first-child{fill:#1f2631}.lg-cond{fill:var(--tx2);font:400 11px "IBM Plex Sans",sans-serif;paint-order:stroke;stroke:var(--s1);stroke-width:4px}.lg-cond.on{fill:var(--tx)}
.lg-seg{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.lg-seg button{all:unset;cursor:pointer;font-size:12.5px;padding:5px 10px;border-radius:20px;color:var(--tx2);box-shadow:inset 0 0 0 1px var(--bd2)}.lg-seg button.on{color:var(--tx);background:var(--s3)}.lg-seg button:focus-visible{outline:2px solid var(--ac)}
.gate-l{display:flex;align-items:flex-start;gap:8px;font-size:12.5px;padding:3px 0;line-height:1.35}
@media (max-width:900px){#sec-visao .rolar.tem-mais{-webkit-mask-image:linear-gradient(90deg,#000 92%,transparent);mask-image:linear-gradient(90deg,#000 92%,transparent)}}.gate-l span{flex:1}.gate-l em{font:11px "IBM Plex Mono",monospace;color:var(--tx3);font-style:normal}.gate-l.er span{color:var(--er)}

/* grafo de commits */
.commits td{padding:0 10px;height:46px;vertical-align:middle}.commits td .t{max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.commits td.g{padding:0 0 0 8px;width:1%}.commits svg{display:block}
.commits tr{cursor:pointer}.commits tr.sel td{background:var(--acbg)}.commits .t{max-width:60ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.commits .meta{color:var(--tx3);font-size:12px}
.detalhe{position:sticky;top:76px;max-height:calc(100vh - 92px);overflow-y:auto;align-self:start;overscroll-behavior:contain}.gate{display:grid;grid-template-columns:22px 1fr auto;gap:4px 10px;align-items:start;padding:7px 0;border-bottom:1px solid var(--bd)}.gate:last-child{border:0}

/* pipeline em trilha */
.trilha{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;counter-reset:t}
.lx-veredito{margin:14px 16px 16px;border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:3px;border:1px solid var(--bd)}
.lx-veredito span{font-size:12px;color:var(--tx3)}.lx-veredito b{font:600 20px/1.2 "Space Grotesk",sans-serif}.lx-veredito em{font-style:normal;font-size:12.5px;color:var(--tx2)}
.lx-veredito.neutro{background:var(--acbg);border-color:#4A3A80}.lx-veredito.neutro b{color:var(--ac)}
.lx-veredito.at{background:var(--atbg);border-color:var(--atbd)}.lx-veredito.at b{color:var(--at)}
.lx-tab td,.lx-tab th{vertical-align:top}.lx-tab th{white-space:normal;min-width:130px}
.lx-mapa td{padding:6px 8px}.lx-c{text-align:center;width:52px}.lx-perg{font-size:12.5px;color:var(--tx2);max-width:560px}
.lx-l{cursor:pointer}.lx-l:hover td{background:var(--s2)}.lx-l.on td{background:var(--acbg)}
.lx-q{display:inline-block;width:16px;height:16px;border-radius:4px;vertical-align:middle;background:var(--s3)}
.lx-q.ok{background:var(--ok)}.lx-q.at{background:var(--at)}.lx-q.nd{background:#4A4A58}
.lx-q.cz{background:transparent;border-radius:50%;box-shadow:inset 0 0 0 2px var(--tx2)}.lx-q.er{background:var(--er)}.lx-q.vz{opacity:.25}
.lx-leg{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;font-size:12px;color:var(--tx2)}.lx-leg span{display:inline-flex;gap:6px;align-items:center}
.lx-pg{margin:0 16px 12px;font-size:14px}
.lx-quatro{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:0 16px 16px}
@media (max-width:1280px){.lx-quatro{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:700px){.lx-quatro{grid-template-columns:1fr}}
.lx-resp{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:12px;min-width:0}
.lx-resp h4{margin:0 0 6px;font:600 13px/1.3 "Space Grotesk",sans-serif}.lx-selos{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.lx-texto{font-size:13px;line-height:1.6;max-height:480px;overflow:auto;overflow-wrap:anywhere;padding-right:4px}
.lx-fr{border-bottom:2px solid;padding-bottom:1px}.lx-fr.ok{border-color:var(--okbd)}.lx-fr.at{border-color:var(--at);background:var(--atbg)}.lx-fr.er{border-color:var(--er);background:var(--erbg)}
.lx-cru{white-space:pre-wrap;color:var(--tx2);font-size:12.5px}
.lx-resp details{margin-top:8px;font-size:12px;color:var(--tx2)}.lx-resp summary{cursor:pointer;color:var(--ac)}.lx-resp ol{padding-left:18px;margin:6px 0}
.fx-grade{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,340px);gap:20px;align-items:start}
.fx{display:flex;flex-direction:column;align-items:stretch;max-width:620px;width:100%;margin:0 auto}
.fx-fase{position:relative;border:1px solid var(--bd);border-radius:var(--r2);background:var(--s1);padding:12px 14px 14px;box-shadow:var(--sh1)}
.fx-fase.laco{border-color:#4A3A80;background:linear-gradient(180deg,rgba(166,139,255,.06),transparent 60%),var(--s1)}
.fx-fase header{display:flex;align-items:baseline;gap:10px;margin-bottom:10px}
.fx-fase header b{font:600 15px/1.2 var(--tit)}.fx-fase header em{font-style:normal;color:var(--tx3);font-size:12px;margin-left:auto}
.fx-num{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--s3);font:600 12px/1 "IBM Plex Mono",monospace;color:var(--tx2);flex:none}
.fx-corpo{display:flex;flex-direction:column;align-items:center}
.fx-no{all:unset;box-sizing:border-box;cursor:pointer;width:100%;max-width:340px;background:var(--s2);border:1.5px solid var(--bd2);border-radius:9px;padding:8px 12px;display:flex;flex-direction:column;gap:5px;transition:border-color .15s,transform .15s}
.fx-no:hover{border-color:var(--ac);transform:translateY(-1px)}.fx-no:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
.fx-no.sel{border-color:var(--ac);box-shadow:0 0 0 2px var(--acbg)}
.fx-no.par{border-color:var(--atbd);background:var(--atbg)}
.fx-no.ni{border-style:dashed;background:transparent;opacity:.8}
.fx-no.banc{border-style:dotted}
.fx-no.fx-pii{border-color:var(--piibd);background:var(--piibg)}
.fx-t{display:flex;align-items:baseline;gap:8px}.fx-t b{font-size:13.5px;font-weight:600;line-height:1.25}.fx-t em{font:11.5px "IBM Plex Mono",monospace;color:var(--tx3);font-style:normal;margin-left:auto;white-space:nowrap}
.fx-s{display:flex;gap:4px;flex-wrap:wrap}.fx-s .selo{font-size:10px;padding:2px 6px}
.fx-seta{width:2px;height:18px;background:#5A5A6A;position:relative;margin:0 auto;flex:none}
.fx-seta::after{content:"";position:absolute;left:-5px;bottom:-3px;border:6px solid transparent;border-top-color:#5A5A6A;border-bottom:0}
.fx-seta.grande{height:26px}
.fx-ramo{display:grid;grid-template-columns:1fr 1fr;gap:10px;width:100%;max-width:440px;position:relative;padding-top:4px}
.fx-ramo::before{content:"";position:absolute;top:0;left:25%;right:25%;border-top:2px solid #5A5A6A}.fx-col{flex:1}.fx-desce{flex:1;width:2px;min-height:10px;background:#5A5A6A}.fx-junta{grid-column:1/-1;height:2px;margin:0 25%;background:#5A5A6A}
.fx-col{display:flex;flex-direction:column;align-items:center;gap:0;min-width:0}
.fx-rot{font-size:11.5px;color:var(--tx3);margin:4px 0 6px;text-align:center}
.fx-alt .fx-col:first-child .fx-no{opacity:.8}.fx-alt{column-gap:34px}.fx-alt::after{content:"ou";position:absolute;left:50%;top:50px;transform:translateX(-50%);font:600 11px "IBM Plex Mono",monospace;color:var(--tx3);background:var(--s1);padding:0 4px}
.fx-comlado{display:flex;flex-direction:column;align-items:center;width:100%}
.fx-lado,.fx-porta .fx-lado{all:unset;font-size:12px;color:var(--at);margin-top:6px;cursor:default;border:1px dashed var(--atbd);background:var(--atbg);border-radius:14px;padding:3px 10px}
.fx-porta{width:100%;max-width:420px;margin:0 auto 6px;text-align:center}.fx-porta .fx-lado{cursor:pointer;color:var(--tx2);border-color:var(--bd2);background:transparent}.fx-porta .fx-lado.sel{color:var(--ac)}
.fx-volta{display:block;text-align:center;margin-top:10px;font-size:12.5px;color:var(--ac);border-top:1px dashed #4A3A80;padding-top:8px}
.fx-fim{align-self:center;border:1.5px solid var(--okbd);background:var(--okbg);color:var(--ok);border-radius:20px;padding:6px 14px;font-size:13px;font-weight:600}
.fx-leg{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:var(--tx2);margin:8px 0 0}.fx-leg span{display:inline-flex;gap:6px;align-items:center}
.fx-det{position:sticky;top:68px;border:1px solid var(--bd2);border-radius:var(--r2);background:var(--s1);padding:14px 16px;box-shadow:var(--sh1);max-height:calc(100vh - 84px);overflow:auto}
.fx-det.fx-pii{border-color:var(--piibd);box-shadow:var(--sh1),inset 3px 0 0 var(--pii)}.fx-det.vazio{color:var(--tx2)}
.fx-det .k{margin:12px 0 4px;color:var(--tx3);font-size:11.5px;letter-spacing:.3px}.fx-det p{margin:0 0 4px}.fx-det pre{max-height:200px}
@media (max-width:1100px){.fx-grade{grid-template-columns:1fr}.fx-det{position:static;max-height:none}}
@media (max-width:520px){.fx-ramo{grid-template-columns:1fr}.fx-ramo::before{display:none}.fx-fase header em{display:none}}
.fx{max-width:720px}.fx-svg{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}.com-setas .fx-comlado .fx-lado,.com-setas .fx-volta{display:none}.com-setas .fx-porta .fx-lado{border-color:#55556A}
.passo{position:relative;background:var(--s2);border:1px solid var(--bd);border-radius:8px;padding:10px 12px 10px;min-height:96px;display:flex;flex-direction:column;gap:6px}
.passo .n{font:500 11px/1 "IBM Plex Mono",monospace;color:var(--tx3);display:flex;justify-content:space-between;align-items:center}
.passo b{font-size:13px;font-weight:600;line-height:1.3}
.g12>button.passo.passo{grid-column:span 3!important;display:block!important}@media (max-width:1180px){.g12>button.passo.passo{grid-column:span 6!important}}@media (max-width:600px){.g12>button.passo.passo{grid-column:span 12!important}}.passo small{color:var(--tx3);font-size:11.5px;margin-top:auto;overflow-wrap:anywhere;word-break:break-word}
#sec-prs td:last-child{min-width:190px;font-size:12px}#sec-prs td:last-child span{white-space:nowrap}#sec-prs table{min-width:0}
.passo.parcial{border-color:var(--atbd)}.passo.pii{border-color:var(--piibd);background:linear-gradient(180deg,#2A1518,var(--s2))}
.passo.nao_implementada,.passo.ausente{border-style:dashed;background:transparent}

/* grafo do código */
.gx{display:grid;grid-template-columns:minmax(0,1fr) 320px;border:1px solid var(--bd);border-radius:var(--r2);overflow:hidden;background:#141418;height:calc(100vh - 150px);min-height:560px}
.gx-tela{position:relative;min-width:0}.gx-tela canvas{display:block;width:100%;height:100%;cursor:grab}.gx-tela canvas.arrastando{cursor:grabbing}
.gx-barra{position:absolute;top:12px;left:12px;right:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;pointer-events:none}.gx-barra>*{pointer-events:auto}
.gx-busca{position:relative}.gx-busca input{width:260px;height:34px;background:rgba(20,24,30,.95);border:1px solid var(--bd2);border-radius:var(--r1);color:var(--tx);padding:0 10px 0 30px;font:inherit;font-size:13px}
.gx-busca:before{content:"⌕";position:absolute;left:10px;top:7px;color:var(--tx3)}
.gx-res{position:absolute;top:38px;left:0;width:340px;background:var(--s2);border:1px solid var(--bd2);border-radius:var(--r1);overflow:hidden;display:none;z-index:3;box-shadow:0 12px 28px rgba(0,0,0,.5)}
.gx-res button{all:unset;display:block;width:100%;box-sizing:border-box;padding:7px 10px;cursor:pointer;font-size:12.5px}.gx-res button:hover,.gx-res button.foco{background:var(--s3)}
.gx-res small{color:var(--tx3);display:block;font:11px "IBM Plex Mono",monospace}
.gx select{height:34px;background:rgba(20,24,30,.95);border:1px solid var(--bd2);border-radius:var(--r1);color:var(--tx);padding:0 8px;font:inherit;font-size:13px;max-width:280px}
.gx label.tg{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 10px;background:rgba(20,24,30,.95);border:1px solid var(--bd2);border-radius:var(--r1);font-size:12.5px;color:var(--tx2);cursor:pointer}
.gx-leg{position:absolute;left:12px;bottom:12px;right:56px;display:flex;gap:6px;flex-wrap:wrap;pointer-events:none}
.gx-leg button{pointer-events:auto;all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 8px;border-radius:20px;background:rgba(20,24,30,.92);border:1px solid var(--bd);font-size:11.5px;color:var(--tx2)}
.gx-leg button.off{opacity:.4}
@media (max-width:900px){.gx-tela{height:auto!important;display:flex;flex-direction:column}.gx-tela canvas{height:58vh!important;flex:none}.gx-leg{position:static;padding:10px 0 4px;max-height:132px;overflow-y:auto}.gx-tela{position:relative}.gx-zoom{bottom:auto;top:calc(58vh - 110px)}.gx-leg button{background:var(--s2)}}.gx-leg button:hover{border-color:var(--bd2);color:var(--tx)}
.gx-zoom{position:absolute;right:12px;bottom:12px;display:flex;flex-direction:column;gap:4px}.gx-zoom button{all:unset;cursor:pointer;width:30px;height:30px;display:grid;place-items:center;background:rgba(20,24,30,.95);border:1px solid var(--bd2);border-radius:var(--r1);color:var(--tx2)}
.gx-lado{border-left:1px solid var(--bd);background:var(--s1);overflow:auto;padding:16px}
.gx-lado h3{font:600 15px/1.3 "IBM Plex Mono",monospace;word-break:break-word}.gx-lado .k{color:var(--tx3);font-size:11.5px;margin:14px 0 6px;font-family:"IBM Plex Mono",monospace;letter-spacing:.3px}
.gx-lado ul{list-style:none;margin:0;padding:0}.gx-lado li button{all:unset;cursor:pointer;display:block;width:100%;box-sizing:border-box;padding:4px 6px;border-radius:4px;font:12px "IBM Plex Mono",monospace;color:var(--tx2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gx-lado li button:hover{background:var(--s3);color:var(--tx)}
.gx-dica{position:absolute;pointer-events:none;background:var(--s2);border:1px solid var(--bd2);border-radius:6px;padding:6px 8px;font-size:12px;display:none;max-width:320px;box-shadow:0 8px 20px rgba(0,0,0,.45);z-index:4}
.gx-dica b{font-family:"IBM Plex Mono",monospace;font-weight:600}.gx-dica small{display:block;color:var(--tx3);font:11px "IBM Plex Mono",monospace}

/* rastro */
.frase{display:grid;grid-template-columns:84px 1fr;gap:8px;padding:7px 0;border-bottom:1px solid var(--bd)}.frase:last-child{border:0}
select.q{font:inherit;background:var(--s2);color:var(--tx);border:1px solid var(--bd2);border-radius:var(--r1);padding:0 10px;height:40px;width:100%}
.leitor{position:sticky;top:76px}
svg text{fill:var(--tx2);font:11px "IBM Plex Mono",monospace}svg .rot{fill:var(--tx);font:12px "IBM Plex Sans",sans-serif}
.barra{transform-origin:var(--cx) 50%;animation:abre .22s var(--ease) both}@keyframes abre{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.achado{border:1px solid var(--bd);border-radius:var(--r2);padding:14px 16px;background:var(--s1)}
.achado.pii{border-color:var(--piibd);background:#2A1518}.achado.erro{border-color:var(--erbd);background:#1d1416}.achado.atencao{border-color:var(--atbd);background:#19160f}
.achado header{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}.achado header b{font-size:14px}
details summary{cursor:pointer;color:var(--tx2);font-size:13px}details[open] summary{margin-bottom:10px}

@media (max-width:1180px){.c3{grid-column:span 6}.c4,.c5,.c6,.c7,.c8,.c9{grid-column:span 12}.gx{grid-template-columns:1fr;height:auto}.gx-tela{height:62vh}.gx-lado{border-left:0;border-top:1px solid var(--bd);max-height:380px}.detalhe,.leitor{position:static}}
@media (max-width:900px){.app{grid-template-columns:1fr}.lado{position:sticky;top:0;height:auto;z-index:9;padding:10px 10px 8px;border-right:0;border-bottom:1px solid var(--bd);flex-direction:column}
.marca small{display:none}.lado nav{flex-direction:row;overflow-x:auto;margin-top:8px;gap:4px;scrollbar-width:none;-webkit-mask-image:linear-gradient(90deg,#000 85%,transparent);mask-image:linear-gradient(90deg,#000 85%,transparent);padding-right:40px}.lado nav::-webkit-scrollbar{display:none}
.lado .grupo-nav,.legenda{display:none}.lado nav button{white-space:nowrap;min-height:40px}
main{padding:0 14px 48px}.topo{position:static;margin:0 -14px;padding:10px 14px;flex-wrap:wrap;gap:6px}.topo>span{border:0;padding:0 10px 0 0}.topo .tit{max-width:100%}
.c3{grid-column:span 12}.alerta{grid-template-columns:auto 1fr}.alerta .btn{grid-column:span 2;grid-row:auto;justify-self:start}.gx-busca input{width:100%}.gx-busca{flex:1}}
.so-movel{display:none}@media (max-width:900px){.so-movel{display:block}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = r"""
const D=DADOS,P=D.perguntas,T=D.textos,REG=D.registro,A=D.achados;
const esc=s=>(s===null||s===undefined?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $=id=>document.getElementById(id);
const PII_RE=/pii|scrubber|sanitiz|security|dados pessoais|clinic/i;
function marcarRolar(){document.querySelectorAll('.rolar').forEach(d=>d.classList.toggle('tem-mais',d.scrollWidth-d.clientWidth-d.scrollLeft>4))}
addEventListener('resize',marcarRolar);document.addEventListener('scroll',e=>{if(e.target.classList&&e.target.classList.contains('rolar'))marcarRolar()},true);
function ir(n){setTimeout(marcarRolar,60);if(n=='pipeline')setTimeout(()=>typeof fxSetas=='function'&&fxSetas(),480);document.querySelectorAll('section.sec').forEach(s=>s.classList.toggle('on',s.id=='sec-'+n));
document.querySelectorAll('.lado nav button').forEach(b=>{const on=b.dataset.s==n;b.classList.toggle('on',on);if(on)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
document.body.classList.toggle('compacto',n!='visao');{const s=document.getElementById('sec-'+n);if(s){s.querySelectorAll('.g12').forEach(g=>[...g.children].forEach((c,k)=>c.style.setProperty('--i',Math.min(k,10))));s.querySelectorAll('table').forEach(tb=>{if(!tb.closest('.rolar')){const w=document.createElement('div');w.className='rolar';tb.parentNode.insertBefore(w,tb);w.appendChild(tb)}})}}history.replaceState(null,'','#'+n);window.scrollTo({top:0});if(n=='grafo')gxIniciar()}
function marca(t,vz){let h=esc(t);for(const v of vz){if(!v)continue;const e=esc(v).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');h=h.replace(new RegExp(e,'g'),m=>`<mark>${m}</mark>`)}return h}
function quando(iso){if(!iso)return'';const s=(Date.now()-new Date(iso))/1000;if(s<90)return'agora';if(s<3600)return'há '+Math.round(s/60)+' min';if(s<86400)return'há '+Math.round(s/3600)+' h';return new Date(iso).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})}
function dataCurta(iso){if(!iso)return'';const d=new Date(iso);return d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})+' '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}
function ic(k){return `<span class="ic ${k}" aria-hidden=true>${{ok:'✓',er:'✕',at:'!',neu:'–',pii:'!'}[k]||'·'}</span>`}
function issues(t){return esc(t).replace(/#(\d+)(?:\s*\(([^)]*)\))?\s+(CLOSED|OPEN)/g,(m,n,_,s)=>`<span class="iss ${s.toLowerCase()}">#${n} ${s=='OPEN'?'aberta':'fechada'}</span>`).replace(/#(\d+)(?![^<]*<\/span>)/g,'<span class=iss>#$1</span>')}
function cab(t,sub,dir=''){return `<div class=cab><div><h1>${t}</h1><p class=sub>${sub}</p></div>${dir}</div>`}

/* ---------- portões ---------- */
const CURTO={'CI do grupo (GitHub Actions)':'CI','rastro do pipeline':'pipeline','bateria adversarial':'adversarial','ablação':'ablação','mapa do código':'mapa','reprodutibilidade':'repetição','custo':'custo','fila de revisão':'revisão','registro das métricas':'registro','validação das saídas':'validação','regressão das métricas':'regressão','infraestrutura da rodada':'infra','publicação':'publicação'};
const RODADAS=(D.commits&&D.commits.rodadas)||[];
const PORTOES=(()=>{const o=[];RODADAS.forEach(r=>(r.portoes||[]).forEach(p=>{if(!o.includes(p.portao))o.push(p.portao)}));return o.length?o:Object.keys(CURTO).slice(0,11)})();
function estadoPortao(r,nome){const p=(r.portoes||[]).find(x=>x.portao==nome);if(!p)return 'nr';return p.ok===false?'er':p.ok?'ok':'neu'}
let ROD_AB=null;
/* portões agrupados por fase: o cabeçalho fica legível (texto na horizontal) e cada fase mostra seus quadrados */
const FASES=[
 ['CI','CI do GitHub do grupo',n=>/^CI do grupo/.test(n)],
 ['pipeline','o Íris inteiro roda, ablação e orçamento de tempo',n=>/rastro do pipeline|ablação|orçamento/i.test(n)],
 ['dados pessoais','filtro de dados pessoais, ataque em massa e rastro de produção',n=>/adversarial|ataque|rastro de produção/i.test(n)],
 ['RAG','busca, fidelidade, citação, juízes e regressão das métricas',n=>/RAG|juiz|juízes|revisão|registro das métricas|regressão/i.test(n)],
 ['avaliação','conjunto de avaliação lacrado',n=>/conjunto de avaliação/i.test(n)],
 ['código','mapa e grafo do código',n=>/mapa do código|grafo do código/i.test(n)],
 ['bancada','a própria bancada: reprodutibilidade, custo, saídas válidas, publicação',n=>true]];
function faseDe(n){return FASES.findIndex(f=>f[2](n))}
const PF=FASES.map((_,k)=>PORTOES.filter(n=>faseDe(n)==k));
const NOME_P=n=>n.replace(/^qualidade: /,'regra: ');
function celFase(r,k){const ns=PF[k];if(!ns.length)return '';const es=ns.map(n=>estadoPortao(r,n));
const er=ns.filter((n,i)=>es[i]=='er'),ok=es.filter(e=>e=='ok').length,rod=es.filter(e=>e!='nr').length;
return `<span class=fase-cel title="${esc(FASES[k][0])}: ${ok} de ${ns.length} passaram${er.length?' · reprovou: '+esc(er.map(NOME_P).join(', ')):''}">`+
`<span class=fq>`+ns.map((n,i)=>`<i class=${es[i]}></i>`).join('')+`</span>`+
`<span class="fn ${er.length?'er':''}">${er.length?'✕ '+er.length:rod?ok+'/'+ns.length:'—'}</span></span>`}
function matriz(r){return `<span class=mat>`+FASES.map((_,k)=>PF[k].length?`<span class=fase style="--n:${PF[k].length}">${celFase(r,k)}</span>`:'').join('')+`</span>`}
function matrizCab(){return `<span class="mat mat-cab">`+FASES.map((f,k)=>PF[k].length?`<span class=fase style="--n:${PF[k].length}" title="${esc(f[1])}">${esc(f[0])}<small>${PF[k].length}</small></span>`:'').join('')+`</span>`}
function detalheRodada(r){return `<div class=rod-det>`+FASES.map((f,k)=>PF[k].length?`<div><b>${esc(f[0])}</b>`+PF[k].map(n=>{const p=(r.portoes||[]).find(x=>x.portao==n);const e=estadoPortao(r,n);
return `<div class="gate-l ${e}">${ic(e=='er'?'er':e=='ok'?'ok':'neu')}<span>${esc(NOME_P(n))}</span><em>${p&&p.segundos!=null?p.segundos+' s':e=='nr'?'não rodou':e=='neu'?'sem dado':''}</em></div>`}).join('')+`</div>`:'').join('')+`</div>`}
function legMatriz(){const q=(st,s,l)=>`<span style="display:inline-flex;gap:6px;align-items:center"><span class=fq><i class=${st}${s?'':''}></i></span>${l}</span>`;return `<span class="leg-mat mut3">`+q('ok','','passou')+q('er','','reprovado')+q('neu','','sem dado (não decide)')+q('nr','','não rodou')+`</span>`}

/* ---------- topo e alertas ---------- */
function topo(st){const tem=st&&st.commit_grupo,ok=tem&&st.aprovado;
$('topo-estado').innerHTML=tem?`<span class="estado-pill ${ok?'ok':'er'}"><span class=ponto></span>${ok?'último commit aprovado':'último commit reprovado'}</span>`:`<span class="estado-pill neu"><span class=ponto></span>gerado à mão</span>`;
$('topo-grupo').innerHTML=tem?`grupo <code>${esc(st.commit_grupo)}</code><span class=tit title="${esc(st.commit_grupo_titulo)}">${esc(st.commit_grupo_titulo||'')}</span>`:`gerado em ${esc(D.gerado)}`;
$('topo-priv').innerHTML='';$('topo-priv').style.display='none';
$('topo-quando').innerHTML=tem?`verificado <b>${esc(quando(st.verificado_em))}</b>`:'';$('topo-quando').style.display=tem?'':'none'}
function alertas(){const G=A.filter(a=>a.nivel=='grave');let h='';
for(const tipo of ['pii','erro']){const xs=G.filter(a=>a.tipo==tipo);if(!xs.length)continue;const por={};xs.forEach(a=>(por[a.area]=por[a.area]||[]).push(a));
const itens=Object.entries(por).map(([ar,ys])=>`<li><b>${esc(ar)}</b>: ${ys.length} ${ys.length==1?'caso':'casos'} (${esc(ys.slice(0,3).map(x=>x.titulo).join('; '))}${ys.length>3?'; …':''})</li>`).join('');
h+=`<div class="alerta ${tipo=='pii'?'pii':'er'}" role=alert><div class=n>${xs.length}</div><h2>${tipo=='pii'?`${xs.length==1?'dado pessoal passou':'dados pessoais passaram'} pelo filtro <span class="selo pii">LGPD</span>`:(xs.length==1?'achado grave aberto':'achados graves abertos')}</h2><button class="btn claro" onclick="ir('achados')">ver ${xs.length==1?'o caso':'os casos'}</button><ul>${itens}</ul></div>`}
$('alerta').innerHTML=h}

/* ---------- visão geral ---------- */
function trilha(){const M=D.mapa;if(!M||!M.etapas_pipeline)return '<p class=vazio>Rode make mapa.</p>';
return `<div class=trilha>`+M.etapas_pipeline.map(e=>{const pii=PII_RE.test(e.etapa+e.modulo);const k=e.status=='implementada'?'ok':e.status=='parcial'?'at':'neu';
return `<div class="passo ${esc(e.status)} ${pii?'pii':''}" title="${esc(e.evidencia)}"><span class=n>${String(e.ordem).padStart(2,'0')} ${pii?'<span class="selo pii">dados pessoais</span>':ic(k)}</span><b>${esc(e.etapa.replace(/\s*\(.*\)/,''))}</b><small>${esc(e.status.replace('_',' '))}</small></div>`}).join('')+`</div>`}
function visao(){const st=D.status||{};const g=A.filter(a=>a.nivel=='grave');
const pii=(D.adversarial_casos||[]).filter(c=>c.categoria=='pii'),piiok=pii.filter(c=>c.aprovado).length,piivaz=A.filter(a=>a.tipo=='pii').length;
const busca=REG.find(r=>r.experimento.startsWith('16')&&r.variante=='qwen3+rerank'),melhor=[...REG].filter(r=>r.camada=='busca'&&r.metricas['recall@5']).sort((a,b)=>b.metricas['recall@5'].v-a.metricas['recall@5'].v)[0];
const hk=REG.find(r=>r.variante.startsWith('Claude Haiku 5.5, rodada 1'));
let h=cab('Visão geral','O estado do Íris no último commit verificado: se passou nos portões, o que está grave e onde o pipeline está. Números do gabarito rascunho (sem conferência humana) são provisórios.');
const np=(st.portoes||[]).length,pok=(st.portoes||[]).filter(p=>p.ok!==false).length;
h+=`<div class=g12>
<div class="c3 kpi ${st.portoes?(st.aprovado?'ok':'er'):''}"><span>Portões da última rodada</span><b class="${st.portoes?(st.aprovado?'ok':'er'):'mut'}">${st.portoes?pok+'/'+np:'—'}</b><em>${st.portoes?(st.aprovado?'publicado · CI do grupo sem check conta como “sem dado”':'painel mantém o último bom'):'a verificação automática ainda não rodou'}</em></div>
<div class="c3 kpi ${piivaz?'pii':'ok'}"><span>Filtro de dados pessoais <span class="selo pii" style="margin-left:4px">LGPD</span></span><b class="${piivaz?'pii':'ok'}">${piiok}/${pii.length}</b><em>casos sintéticos bloqueados · ${piivaz} vazaram</em></div>
<div class="c3 kpi"><span>Busca do sistema atual</span><b>${busca?busca.metricas['recall@5'].v.toFixed(2):'—'}</b><em>recall@5 (qwen3+rerank) · melhor medida ${melhor?melhor.metricas['recall@5'].v.toFixed(2):''}</em></div>
<div class="c3 kpi"><span>Fidelidade da resposta</span><b>${hk?hk.metricas.fidelidade.v.toFixed(2):'—'}</b><em>juiz mais estrito (Haiku) · 0,95 nos gpt-oss</em></div>`;
const rs=RODADAS.slice(-8).reverse();
h+=`<div class="c12 painel"><div class=ph><h3>Verificações automáticas recentes</h3><button class="btn sec mini" onclick="ir('commits')">grafo de commits →</button><p>Cada linha é uma verificação automática. Os portões estão agrupados por fase; cada quadrado é um portão e o número diz quantos passaram. <b>Clique numa linha</b> para ver o nome e o tempo de cada portão.</p></div>`+
(rs.length?`<div class=rolar><table><thead><tr><th>quando</th><th>alvo</th><th>commit do grupo</th><th>${matrizCab()}</th><th></th></tr></thead><tbody>`+rs.map((r,i)=>`<tr class="rod ${ROD_AB===i?'rod-aberta':''}" tabindex=0 onclick="ROD_AB=ROD_AB===${i}?null:${i};visao()" onkeydown="if(event.key=='Enter'){ROD_AB=ROD_AB===${i}?null:${i};visao()}"><td class=mut style="white-space:nowrap">${ROD_AB===i?'▾':'▸'} ${esc(dataCurta(r.rodada_em))}</td><td class=mut style="white-space:nowrap">${r.pr?'PR #'+r.pr:'dev'}</td><td><code>${esc(r.commit_grupo)}</code></td><td>${matriz(r)}</td><td>${r.aprovado?'<span class="selo ok">aprovado</span>':'<span class="selo er">reprovado</span>'}</td></tr>`+(ROD_AB===i?`<tr class=rod-aberta><td colspan=6>${detalheRodada(r)}</td></tr>`:'')).join('')+`</tbody></table></div><p style="margin:10px 0 0">${legMatriz()}</p>`
:`<div class=vazio-bloco><b>A atualização automática ainda não rodou.</b><br>Cada commit novo aparece aqui com o resultado de cada portão. Para ligar: <code>bash ../bancada/atualizar/instalar.sh</code>.</div>`)+`</div>`;
h+=`<div class="c12 painel"><div class=ph><h3>Achados abertos</h3>${A.length?`<button class="btn sec mini" onclick="ir('achados')">ver os ${A.length} →</button>`:''}</div>`;
if(A.length){const gr={};A.forEach(a=>{const k=a.tipo+'|'+a.nivel+'|'+a.area;(gr[k]=gr[k]||[]).push(a)});
h+=Object.entries(gr).map(([k,xs])=>{const [tp,nv,ar]=k.split('|');const vz=[...new Set(xs.flatMap(x=>x.vazou))];const cls=tp=='pii'?'pii':nv=='grave'?'er':'at';
return `<div style="display:grid;grid-template-columns:92px 1fr;gap:10px;padding:10px 0;border-top:1px solid var(--bd)"><span><span class="selo ${cls}">${tp=='pii'?'dado pessoal':nv=='grave'?'grave':'atenção'}</span></span><div><b>${esc(ar)}</b> <span class=mut>· ${xs.length} ${xs.length==1?'caso':'casos'}</span><div class=mut3 style="font-size:12.5px;margin-top:2px">${esc(xs.slice(0,3).map(x=>x.titulo).join(' · '))}${xs.length>3?' · …':''}</div>${vz.length?`<div style="font-size:12.5px;margin-top:6px;display:flex;gap:4px;flex-wrap:wrap;align-items:center"><span class=mut3>passou:</span> ${vz.slice(0,6).map(v=>`<mark>${esc(v)}</mark>`).join(' ')}</div>`:''}</div></div>`}).join('')}
else h+=`<p class=vazio>Nenhum achado aberto.</p>`;
h+=`</div><div class="c12 painel"><div class=ph><h3>Onde o pipeline está</h3><button class="btn sec mini" onclick="ir('grafo')">grafo do código →</button><p>As etapas do Íris no código do grupo (commit <code>${esc(((D.mapa||{}).commit_grupo||'').slice(0,7))}</code>): contínua = implementada, âmbar = parcial, tracejada = ainda não existe. A etapa do filtro de dados pessoais fica em vermelho.</p></div>${trilha()}</div></div>`;
$('visao').innerHTML=h}

/* ---------- commits ---------- */
let CREPO='grupo',CSEL=null;const COR_FAIXA=['#A68BFF','#5FB8C8','#D9A066','#9FB3C8','#8FBF7A','#7FA7D9','#C3B07A'];
function rodadasDe(sha,repo){return RODADAS.filter(r=>(repo=='grupo'?r.commit_grupo:r.commit_privado)==sha)}
function svgLinha(c,larg){const H=46,X=i=>10+i*14,m=H/2;let s=`<svg width=${larg} height=${H} aria-hidden=true>`;
const linha=(x1,y1,x2,y2,cor)=>`<path d="M${x1} ${y1} C${x1} ${(y1+y2)/2} ${x2} ${(y1+y2)/2} ${x2} ${y2}" stroke="${cor}" stroke-width=2 fill=none opacity=.85 />`;
c.entrada.forEach((v,i)=>{if(!v)return;if(v==c.sha)s+=linha(X(i),0,X(c.col),m,COR_FAIXA[i%7]);else{const j=c.saida.indexOf(v);if(j>=0)s+=linha(X(i),0,X(j),H,COR_FAIXA[j%7])}});
c.pais.forEach(p=>{const j=c.saida.indexOf(p);if(j>=0)s+=linha(X(c.col),m,X(j),H,COR_FAIXA[j%7])});
const rs=rodadasDe(c.sha,CREPO),ult=rs[rs.length-1];const cor=ult?(ult.aprovado?'#34D399':'#ff6b6b'):null;
s+=cor?`<circle cx=${X(c.col)} cy=${m} r=6 fill="${cor}" stroke="#18181C" stroke-width=2 />`:`<circle cx=${X(c.col)} cy=${m} r=4.5 fill="#18181C" stroke="${COR_FAIXA[c.col%7]}" stroke-width=2 />`;
if(c.pais.length>1)s+=`<circle cx=${X(c.col)} cy=${m} r=2 fill="#18181C" />`;return s+`</svg>`}
function commitsSec(){const C=D.commits||{};const L=C[CREPO]||[];
let h=cab('Commits e portões','O grafo dos commits do repositório do grupo (dev e PRs abertos, como o <code>git log --graph</code>) com o veredito de cada verificação automática. Só commit do grupo dispara verificação. Ponto cheio verde = passou em todos os portões e foi publicado; vermelho = reprovado (o painel ficou na última versão boa); vazado = entrou antes de a verificação automática existir, sem veredito.',
'');
if(!L.length){$('commits').innerHTML=h+`<div class=vazio-bloco><b>Sem histórico de commits.</b> O painel lê o <code>git log</code> do clone do grupo ao ser gerado.</div>`;return}
if(!CSEL){const v=L.find(c=>rodadasDe(c.sha,CREPO).length);CSEL=(v||L[0]).sha}
const larg=Math.max(...L.map(c=>Math.max(c.entrada.length,c.saida.length,c.col+1)))*14+8;
const ver=L.filter(c=>rodadasDe(c.sha,CREPO).length).length;
h+=`<div class=g12><div class="c8 painel plano"><div class=ph style="padding:14px 16px 0"><h3>challenge-2-residencia-ia-grupo-3/Iris · dev</h3><span class=mut3 style="font-size:12.5px">${L.length} commits mais recentes · ${ver} com veredito</span></div><div class=rolar><table class=commits><thead><tr><th></th><th>commit</th><th>mensagem</th><th>${matrizCab()}</th><th>veredito</th></tr></thead><tbody>`+
L.map(c=>{const rs=rodadasDe(c.sha,CREPO),u=rs[rs.length-1];return `<tr class="${c.sha==CSEL?'sel':''}" onclick="CSEL='${c.sha}';commitsSec()" tabindex=0 onkeydown="if(event.key=='Enter'){CSEL='${c.sha}';commitsSec()}"><td class=g>${svgLinha(c,larg)}</td><td style="white-space:nowrap"><code>${esc(c.sha)}</code>${c.pr?` <span class="iss open">PR #${c.pr}</span>`:''}</td><td><div class=t title="${esc(c.titulo)}">${esc(c.titulo)}</div><div class=meta>${esc(c.autor)} · ${esc(dataCurta(c.data))}</div></td><td title="${u?'':'sem veredito: entrou antes de a verificação automática existir'}">${u?matriz(u):matriz({portoes:[]})}</td><td>${u?(u.aprovado?'<span class="selo ok">aprovado</span>':'<span class="selo er">reprovado</span>')+(rs.length>1?` <span class=mut3 style="font-size:11px">×${rs.length}</span>`:''):''}</td></tr>`}).join('')+`</tbody></table></div><p style="margin:0;padding:10px 16px 14px">${legMatriz()}</p></div>`;
const c=L.find(x=>x.sha==CSEL)||L[0],rs=rodadasDe(c.sha,CREPO);
h+=`<div class="c4 painel detalhe"><span class=mut3 style="font:11px 'IBM Plex Mono',monospace">COMMIT ${esc(c.sha)}${c.pais.length>1?' · merge':''}</span><h3 style="margin:6px 0 4px;line-height:1.35">${esc(c.titulo)}</h3><p class=mut style="margin:0 0 12px;font-size:12.5px">${esc(c.autor)} · ${esc(dataCurta(c.data))} · pais ${c.pais.map(p=>`<code>${esc(p)}</code>`).join(' ')}</p>`;
if(!rs.length)h+=`<div class=vazio-bloco><b>Sem veredito para este commit.</b><br>${CREPO=='grupo'?'A verificação automática confere a ponta do <code>dev</code> a cada 10 minutos; commits que entraram antes de ele ser ligado (12/11) não foram verificados um a um.':'Este commit do iris-rag entrou antes da verificação automática ou nunca foi a ponta da branch quando ela rodou.'}</div>`;
else rs.slice().reverse().forEach((r,i)=>{h+=(i==1?`<details style="margin-top:14px"><summary class=mut style="cursor:pointer;font-size:12.5px">${rs.length-1} rodada(s) anterior(es) deste commit</summary>`:'')+`<div style="margin-top:${i?16:0}px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><span class=mut style="font-size:12.5px">rodada de ${esc(dataCurta(r.rodada_em))}</span>${r.aprovado?'<span class="selo ok">aprovado</span>':'<span class="selo er">reprovado</span>'}</div>`+
(r.portoes||[]).map(p=>`<div class=gate>${ic(p.ok===false?'er':p.ok?'ok':'neu')}<div>${esc(p.portao)}${p.ok===null?`<div class=mut3 style="font-size:12px">${esc(p.detalhe)}</div>`:''}${p.ok===false&&p.detalhe?`<pre style="margin-top:6px;max-height:160px">${esc(p.detalhe)}</pre>`:''}</div><span class="mono mut3" style="font-size:12px">${p.segundos!=null?p.segundos+' s':''}</span></div>`).join('')+`</div>`+(i>0&&i==rs.length-1?'</details>':'')});
$('commits').innerHTML=h+`</div></div><div class=g12 style="margin-top:16px"><div class="c12 painel"><div class=ph><h3>Tendência por commit do dev</h3><p>Os números que dependem do código do grupo, rodada a rodada. Tracejado = primeira rodada (linha de base); ponto verde = rodada aprovada, vermelho = reprovada.</p></div>${tendencia()}</div></div>`}

/* ---------- achados ---------- */
function achadosSec(){let h=cab('Achados','Gerados por regra, não escolhidos à mão. Dado pessoal ou clínico que passa pelo filtro é <b class=pii>grave · dado pessoal</b>; portão reprovado e regressão de métrica são <b class=er>grave · erro</b>; falso positivo que apaga conteúdo e instrução injetada que sobrevive são <b class=at>atenção</b>. Os casos são sintéticos (nomes e números falsos).');
if(!A.length){$('achados').innerHTML=h+`<p class=vazio>Nenhum achado.</p>`;return}
h+=`<div class=g12>`+A.map(a=>{const cls=a.tipo=='pii'?'pii':a.nivel=='grave'?'erro':'atencao';return `<article class="achado ${cls} ${a.texto?'c6':'c12'}"><header><span class="selo ${a.tipo=='pii'?'pii':a.nivel=='grave'?'er':'at'}">${a.tipo=='pii'?'grave · dado pessoal':a.nivel=='grave'?'grave':'atenção'}</span>${a.tipo=='pii'?'<span class="selo pii">LGPD</span>':''}<b>${esc(a.titulo)}</b><span class=mut3 style="margin-left:auto;font-size:12px">${esc(a.area)} · <code>${esc(a.id)}</code></span></header>
${a.texto?`<pre>${marca(a.texto,a.vazou)}</pre>`:''}${a.motivos.length?`<p class=mut style="margin:8px 0 0;font-size:12.5px">${a.motivos.map(esc).join('<br>')}</p>`:''}</article>`}).join('')+`</div>`;
$('achados').innerHTML=h}

/* ---------- rastro ---------- */
function leitor(cid,el){const t=T[cid]||{};document.querySelectorAll('.chip.sel').forEach(x=>x.classList.remove('sel'));if(el)el.classList.add('sel');
$('leitor').innerHTML=`<div class=ph><h3><code>${esc(cid)}</code></h3><span class=mut3 style="font-size:12px">${esc(t.idioma||'')} ${t.secao?'· '+esc(t.secao):''}</span></div>${t.aviso?`<p class=at style="margin:0 0 8px;font-size:12.5px">Aviso da curadoria: ${esc(t.aviso)}</p>`:''}<pre style="max-height:calc(100vh - 220px)">${esc(t.texto||'(texto não disponível)')}</pre>`}
function rastro(){const p=P.find(x=>x.id==$('q').value);const rel=new Set(p.relevantes),par=new Set(p.parciais);
let h=`<div class=g12><div class="c12 painel"><div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px"><span class=selo>${esc(p.tipo)}</span>${p.barreira?`<span class=selo>${esc(p.barreira)}</span>`:''}</div><p style="margin:0 0 6px;font-size:16px">${esc(p.pergunta)}</p>
${p.parafrase?`<p class=mut style="margin:0;font-size:12.5px">Paráfrase leiga: ${esc(p.parafrase)}</p>`:''}${p.traducao?`<p class=mut style="margin:0;font-size:12.5px">Tradução da busca bilíngue: ${esc(p.traducao)}</p>`:''}</div>`;
h+=`<div class="c8 painel"><div class=ph><h3>Busca: os 5 primeiros de cada configuração</h3><p>Verde responde, âmbar ajuda em parte (gabarito rascunho: ${rel.size} e ${par.size}). Clique num trecho para ler ao lado.</p></div><div class=rolar><table><thead><tr><th>configuração</th><th>top-5</th><th class=num>certos</th></tr></thead><tbody>`;
for(const b of p.buscas){const ac=b.top5.filter(c=>rel.has(c)).length;h+=`<tr><td style="width:240px"><b>${esc(b.config)}</b><br><span class=mut3 style="font-size:12px">${esc(b.desc)}</span></td><td>`+b.top5.map((c,i)=>`<span class="chip ${rel.has(c)?'R':par.has(c)?'p':''}" title="${esc(c)}" onclick="leitor('${c}',this)">${i+1} ${esc(c.split('#')[0].slice(0,16))}</span>`).join('')+`</td><td class="num ${ac?'ok':'mut3'}">${ac}/${rel.size}</td></tr>`}
h+=`</tbody></table></div></div><div class="c4 painel leitor" id=leitor><div class=vazio-bloco><b>Leitor de trechos.</b><br>Clique num trecho da tabela para ler o texto que a busca trouxe.</div></div>`;
const nr=Object.keys(p.respostas).length,cr=nr>=3?'c4':'c6';
for(const [v,r] of Object.entries(p.respostas))h+=`<div class="${cr} painel"><div class=ph><h3>Resposta, prompt ${v}</h3><span>${r.absteve?'<span class=selo>absteve</span>':''} ${r.copia_aviso?'<span class="selo at">copia o aviso</span>':''}</span></div><pre style="max-height:280px">${esc(r.texto)}</pre></div>`;
const nj=Object.keys(p.juizes).length,cj=nj>=3?'c4':'c6';
for(const [n,j] of Object.entries(p.juizes))h+=`<div class="${cj} painel"><div class=ph><h3>${esc(n)}</h3><span class=selo>útil: ${esc(j.util)}</span></div>`+j.frases.map(f=>{const k=f.sust=='sim'?'ok':f.sust=='parcial'?'at':'er';return `<div class=frase><span class=${k} style="font-weight:600;display:flex;gap:6px;align-items:flex-start">${ic(k)}${esc(f.sust)}</span><div>${esc(f.frase)}${f.sust!='sim'?`<div class=mut3 style="font-size:12px">${esc(f.motivo)}</div>`:''}</div></div>`}).join('')+`</div>`;
$('rastro').innerHTML=h+`</div>`}

/* ---------- qualidade ---------- */
function grafico(rs,k){const W=640,L=210,lin=26,H=rs.length*lin+30,x=v=>L+v*(W-L-44);let h=`<svg width=100% viewBox="0 0 ${W} ${H}" role=img aria-label="média e intervalo de confiança de ${esc(k)}">`;
for(let t=0;t<=1.0001;t+=0.2)h+=`<line x1=${x(t)} x2=${x(t)} y1=0 y2=${H-22} stroke=#262d37 /><text x=${x(t)} y=${H-6} text-anchor=middle>${t.toFixed(1)}</text>`;
rs.forEach((r,i)=>{const m=r.metricas[k],y=i*lin+15;h+=`<text class=rot x=${L-10} y=${y+4} text-anchor=end>${esc(r.variante.slice(0,30))}</text><line class=barra style="--cx:${x(m.v)}px;animation-delay:${i*25}ms" x1=${x(m.ic[0])} x2=${x(m.ic[1])} y1=${y} y2=${y} stroke=#A68BFF stroke-width=4 stroke-linecap=round opacity=.5 /><circle cx=${x(m.v)} cy=${y} r=5 fill=#A68BFF /><text x=${x(m.ic[1])+8} y=${y+4}>${m.v.toFixed(2)}</text>`});
return h+`</svg>`}
function qualidade(){const g={};REG.forEach(r=>(g[r.experimento]=g[r.experimento]||[]).push(r));
let h=cab('Qualidade por versão','Cada configuração medida, com o arquivo e o commit que a produziram. Ponto é a média; a barra é o intervalo de confiança de 95%. Barras que se sobrepõem muito não mostram diferença.')+`<div class=g12>`;
if(D.regressao){const caiu=/FALHOU/.test(D.regressao);h+=`<div class="c12 painel"><details ${caiu?'open':''}><summary><b style="color:var(--tx)">Regressão contra a linha de base</b> ${caiu?'<span class="selo er">caiu</span>':'<span class="selo ok">nenhuma métrica caiu</span>'}</summary><pre style="max-height:240px">${esc(D.regressao)}</pre></details></div>`}
for(const [e,rs] of Object.entries(g)){const k=Object.keys(rs[0].metricas)[0];const comG=rs.every(r=>r.metricas[k].ic);
h+=`<div class="${rs.length>4?'c12':'c6'} painel"><div class=ph><h3>${esc(e)}</h3><p>${esc(rs[0].descricao)} · <code>${esc(rs[0].fonte)}</code> · commit <code>${esc(rs[0].commit)}</code> ${esc(rs[0].data)}</p></div>`;
h+=`<div class=g12><div class="${comG&&rs.length>4?'c6':'c12'}">${comG?grafico(rs,k):''}</div><div class="${comG&&rs.length>4?'c6':'c12'} rolar"><table><thead><tr><th>variante</th>`+Object.keys(rs[0].metricas).map(m=>`<th class=num>${esc(m)}</th>`).join('')+`<th class=num>n</th></tr></thead><tbody>`;
rs.forEach(r=>{h+=`<tr><td><b>${esc(r.variante)}</b>${r.extra?`<br><span class=mut3 style="font-size:12px">${esc(Object.entries(r.extra).map(([a,b])=>a+': '+b).join(' · '))}</span>`:''}</td>`+Object.values(r.metricas).map(m=>`<td class=num>${m.ic?`${m.v.toFixed(2)} <span class=mut3>[${m.ic[0].toFixed(2)}–${m.ic[1].toFixed(2)}]</span>`:m.k!==undefined?`${m.k}${m.n!==undefined?'/'+m.n:''}`:m.v}</td>`).join('')+`<td class=num>${r.n}</td></tr>`});
h+=`</tbody></table></div></div></div>`}$('qualidade').innerHTML=h+`</div>`}

/* ---------- pipeline ---------- */
function pipeline(){const R=D.pipeline;let h=cab('Pipeline inteiro','Um material passando por todas as etapas do Íris, com o que entrou, o que saiu e quanto levou. Sem modelo, um substituto determinístico (provedor eco) faz o papel do LLM: mostra o caminho, não mede qualidade.');
h+=`<div style="margin-bottom:16px">${fluxoEtapas()}${chamadas()}</div>`;
if(!R){$('pipeline').innerHTML=h+`<div class=vazio-bloco><b>Ainda sem rastro.</b> Rode <code>make rastro-pipeline</code>.</div>`;return}
h+=`<div class=g12>`;
for(const ex of R.execucoes||[]){const et=ex.etapas||[],ni=et.filter(e=>e.status=='nao_implementada').length,er=et.filter(e=>e.status=='erro').length,tt=et.reduce((s,e)=>s+(e.latencia_s||0),0);
h+=`<div class="c12 painel"><div class=ph><h3>${esc(ex.material_id)}</h3><span style="display:flex;gap:6px"><span class=selo>${et.length} etapas</span>${er?`<span class="selo er">${er} com erro</span>`:''}${ni?`<span class=selo>${ni} não implementadas</span>`:''}<span class=selo>${tt.toFixed(2)} s</span></span><p>Código do grupo <code>${esc(R.commit_grupo)}</code> · provedor ${esc(R.provedor)}</p></div><div class=rolar><table><thead><tr><th class=num>#</th><th>etapa</th><th>questão</th><th>status</th><th class=num>tempo</th><th style="width:160px">linha do tempo</th><th class=num>entrada → saída</th><th>o que saiu</th></tr></thead><tbody>`;
let acum=0;for(const e of et){const ini=acum;acum+=(e.latencia_s||0);const k=e.status=='ok'?'ok':e.status=='erro'?'er':e.status=='parcial'?'at':'neu';const pii=PII_RE.test(e.etapa+e.funcao);
h+=`<tr style="${pii?'background:#2A1518':''}"><td class="num mut3">${e.ordem}</td><td><b>${esc(e.etapa.replace(/_/g,' '))}</b>${pii?' <span class="selo pii">dados pessoais</span>':''}<div class=mut3 style="font:11.5px 'IBM Plex Mono',monospace">${esc(e.funcao)}</div></td><td class=mut3>${esc(e.questao||'')}</td><td style="white-space:nowrap"><span style="display:inline-flex;gap:6px;align-items:center">${ic(k)}<span class=${k=='neu'?'mut3':k}>${esc(e.status.replace('_',' '))}</span></span></td><td class=num>${e.latencia_s!=null?Number(e.latencia_s).toFixed(3)+' s':''}</td><td><div style="position:relative;height:10px;background:var(--s2);border-radius:3px"><i style="position:absolute;top:0;bottom:0;left:${tt?100*ini/tt:0}%;width:max(2px,${tt?100*(e.latencia_s||0)/tt:0}%);background:${pii?'var(--pii)':k=='er'?'var(--er)':/agente|extrator|busca/.test(e.etapa)?'var(--ac)':'#4a5260'};border-radius:2px"></i></div></td><td class="num mut">${esc(e.tamanho_entrada)} → ${esc(e.tamanho_saida)}</td><td style="font-size:12.5px">${esc(e.resumo_saida)}</td></tr>`}
h+=`</tbody></table></div></div>`}$('pipeline').innerHTML=h+`</div>`}

/* ---------- confiança, revisão, segurança ---------- */
function confianca(){let h=cab('Reprodutibilidade e custo','Se a mesma configuração dá o mesmo resultado quando roda de novo, e quanto cada peça custa em tempo e dinheiro.')+`<div class=g12>`;
h+=D.repeticao?`<div class="c6 painel"><div class=ph><h3>Reprodutibilidade</h3></div><pre style="max-height:520px">${esc(D.repeticao)}</pre></div>`:`<div class="c6 vazio-bloco">Rode <code>make repetir</code>.</div>`;
h+=D.custo?`<div class="c6 painel"><div class=ph><h3>Custo e latência por peça</h3></div><div class=rolar><table><thead><tr><th>peça</th><th>onde</th><th class=num>n</th><th class=num>mediana</th></tr></thead><tbody>`+D.custo.map(c=>`<tr><td><b>${esc(c.peca)}</b><div class=mut3 style="font-size:12px">${esc(c.extra)}</div></td><td class=mut>${esc(c.onde)}</td><td class=num>${c.n}</td><td class=num>${c.mediana_s} s</td></tr>`).join('')+`</tbody></table></div></div>`:`<div class="c6 vazio-bloco">Rode <code>make custo</code>.</div>`;
$('confianca').innerHTML=h+`</div>`}
function revisao(){const V=D.divergencias;let h=cab('Revisão humana','Frases em que os juízes discordam. A decisão de uma pessoa nelas diz qual juiz serve de régua.',V?`<span class=selo>${V.n} frases na fila</span>`:'');
if(!V){$('revisao').innerHTML=h+`<div class=vazio-bloco>Rode <code>make revisao</code>.</div>`;return}
h+=`<div class=g12>`+V.itens.map(i=>`<div class="c6 painel"><p class=mut3 style="margin:0 0 4px;font-size:12px"><code>${esc(i.id)}</code> ${esc(i.pergunta)}</p><p style="margin:0 0 10px">${esc(i.frase)} ${i.refs.length?`<span class=selo>${esc(i.refs.join(' '))}</span>`:''}</p>`+Object.entries(i.votos).map(([n,v])=>{const k=v.sustentada=='sim'?'ok':v.sustentada=='parcial'?'at':'er';return `<div class=frase style="grid-template-columns:120px 84px 1fr"><span class=mut>${esc(n)}</span><span class=${k} style="font-weight:600;display:flex;gap:6px">${ic(k)}${esc(v.sustentada)}</span><span class=mut3 style="font-size:12.5px">${esc(v.motivo)}</span></div>`}).join('')+`</div>`).join('')+`</div>`;
$('revisao').innerHTML=h}
function seguranca(){const C=D.adversarial_casos||[];let h=cab('Segurança e ablação','Materiais sintéticos com dados pessoais, injeção de prompt e formatos difíceis; e o adaptador com e sem cada peça. Em vermelho, tudo que é do filtro de dados pessoais; a parte que vazou fica marcada dentro do texto.');
const cats=['pii','injecao','formato'],nome={pii:'Dados pessoais',injecao:'Injeção de prompt',formato:'Formatos difíceis'};
h+=`<div class=g12>`+cats.map(c=>{const g=C.filter(x=>x.categoria==c),k=g.filter(x=>x.aprovado).length;const ruim=k<g.length;return `<div class="c4 kpi ${c=='pii'&&ruim?'pii':''}"><span>${nome[c]}${c=='pii'?' <span class="selo pii" style="margin-left:4px">LGPD</span>':''}</span><b class="${!ruim?'ok':c=='pii'?'pii':'at'}">${k}/${g.length}</b><div class=barra-cob><i style="width:${g.length?100*k/g.length:0}%;background:${!ruim?'var(--ok)':c=='pii'?'var(--pii)':'var(--at)'}"></i></div><em>${c=='pii'?'sem LLM: regra do grupo, roda igual no PC e na VPS':'na VPS só prova que não quebra'}</em></div>`}).join('');
for(const c of cats){const g=C.filter(x=>x.categoria==c);if(!g.length)continue;
h+=`<div class="c12 painel plano"><div class=ph style="padding:14px 16px 0"><h3>${nome[c]}</h3><span class=mut3 style="font-size:12.5px">${g.filter(x=>!x.aprovado).length} de ${g.length} falharam</span></div><div class=rolar><table><thead><tr><th style="padding-left:16px">resultado</th><th>caso</th><th>o que saiu do filtro</th></tr></thead><tbody>`+g.map(x=>{const vz=(x.motivos||[]).filter(m=>m.includes('sobrou:')&&m.split("'").length>2).map(m=>m.split("'")[1]);const fp=(x.descricao||'').includes('falso positivo');const vazou=!x.aprovado&&c=='pii'&&!fp;
return `<tr style="${vazou?'background:#2A1518':''}"><td style="width:120px;padding-left:16px">${x.aprovado?'<span class="selo ok">ok</span>':vazou?'<span class="selo pii">vazou</span>':'<span class="selo at">falhou</span>'}</td><td style="width:320px"><code>${esc(x.id)}</code> ${esc(x.descricao)}</td><td style="font-size:12.5px">${x.saida_sanitizada?marca(x.saida_sanitizada.slice(0,300),vz):esc((x.motivos||[]).join('; '))}${!x.aprovado&&x.motivos&&x.motivos.length&&x.saida_sanitizada?`<div class=mut3 style="font-size:12px;margin-top:4px">${esc(x.motivos.join('; '))}</div>`:''}</td></tr>`}).join('')+`</tbody></table></div></div>`}
if(D.ablacao)h+=`<div class="c12 painel"><div class=ph><h3>Ablação</h3><p>O adaptador com e sem cada peça, no golden benchmark do grupo.</p></div><pre style="max-height:520px">${esc(D.ablacao)}</pre></div>`;
$('seguranca').innerHTML=h+`</div>`}

/* ---------- grafo do código (estilo GitNexus) ---------- */
const GX={on:false,camada:'funcoes',T:{x:0,y:0,k:1},hover:-1,sel:-1,proc:null,semTeste:true,soLig:true,off:new Set()};
const PAL=['#A68BFF','#5FB8C8','#D9A066','#E5B443','#C9B6FF','#5FD0E0','#8FBF7A','#7FA7D9','#9FB3C8','#C3B07A','#8E7CC3','#6FA3A6'];
function gxDados(){const G=D.gitnexus,M=D.mapa;let nos=[],lig=[],grupos=[];
if(GX.camada=='funcoes'&&G){const S=G.simbolos;const grau=new Array(S.length).fill(0);G.chamadas.forEach(([a,b])=>{grau[a]++;grau[b]++});
const procNos=GX.proc?new Set(GX.proc.passos):null;
const cs=G.comunidades;const corC={};cs.slice(0,PAL.length).forEach((c,i)=>corC[c.id]=PAL[i]);
const nomeC={};{const arqs={};S.forEach(s=>{if(!s.comunidade)return;const a=s.arquivo.split('/').pop();(arqs[s.comunidade]=arqs[s.comunidade]||{})[a]=(arqs[s.comunidade][a]||0)+1});
cs.forEach(c=>{const t=Object.entries(arqs[c.id]||{}).sort((a,b)=>b[1]-a[1])[0];nomeC[c.id]=c.nome+(t?' · '+t[0]:'')})}
const rep={};S.forEach((s,i)=>{const pass=(procNos&&procNos.has(i))||((!GX.semTeste||!s.teste)&&(!GX.soLig||grau[i]>0)&&!GX.off.has(s.comunidade||'_'));if(pass){rep[i]=nos.length;nos.push({i,nome:s.nome,qual:s.qual,tipo:s.tipo,arq:s.arquivo,linha:s.linha,linhas:s.linhas,teste:s.teste,g:s.comunidade||'_',cor:corC[s.comunidade]||'#59626f',grau:grau[i],pii:PII_RE.test(s.arquivo)})}});
G.chamadas.forEach(([a,b])=>{if(a in rep&&b in rep)lig.push({source:rep[a],target:rep[b]})});
const cont={};S.forEach(s=>{if(!s.teste||!GX.semTeste)cont[s.comunidade||'_']=(cont[s.comunidade||'_']||0)+1});
grupos=cs.slice(0,PAL.length).map(c=>({id:c.id,nome:nomeC[c.id],cor:corC[c.id],n:c.n}))}
else if(M){const mods=M.modulos||[];const pastas=[...new Set(mods.map(m=>m.pasta))];const corP={};pastas.forEach((p,i)=>corP[p]=PAL[i%PAL.length]);const rep={};
mods.forEach((m,i)=>{if(GX.off.has(m.pasta))return;rep[m.id]=nos.length;nos.push({i,nome:m.id,qual:m.id,tipo:'módulo',arq:m.caminho,linhas:m.linhas,g:m.pasta,cor:corP[m.pasta],grau:(m.importa||[]).length+(m.importado_por||[]).length,semTeste:!(m.testado_por||[]).length,llm:m.usa_llm,pii:PII_RE.test(m.id),mod:m})});
(M.arestas||[]).forEach(a=>{if(a.de in rep&&a.para in rep)lig.push({source:rep[a.de],target:rep[a.para]})});
grupos=pastas.map(p=>({id:p,nome:p,cor:corP[p],n:mods.filter(m=>m.pasta==p).length}))}
nos.forEach(n=>n.r=GX.camada=='funcoes'?2.6+Math.sqrt(n.grau)*1.5:4+Math.sqrt(n.linhas||1)/3.2);
return {nos,lig,grupos}}
function gxIniciar(){if(GX.on){gxTamanho();return}if(!D.gitnexus&&!D.mapa)return;GX.on=true;
const cv=$('gx-canvas');GX.cv=cv;GX.ctx=cv.getContext('2d');gxTamanho();window.addEventListener('resize',()=>{gxTamanho();gxDesenha()});
gxEventos();gxMontar()}
function gxTamanho(){const cv=GX.cv;if(!cv)return;const r=cv.getBoundingClientRect(),d=window.devicePixelRatio||1;cv.width=Math.max(1,r.width*d);cv.height=Math.max(1,r.height*d);GX.W=r.width;GX.H=r.height;GX.dpr=d}
function gxMontar(){if(GX.sim)GX.sim.stop();const dd=gxDados();GX.nos=dd.nos;GX.lig=dd.lig;GX.grupos=dd.grupos;GX.hover=-1;
GX.viz=GX.nos.map(()=>[]);GX.ent=GX.nos.map(()=>[]);GX.sai=GX.nos.map(()=>[]);GX.lig.forEach(l=>{GX.viz[l.source].push(l.target);GX.viz[l.target].push(l.source);GX.sai[l.source].push(l.target);GX.ent[l.target].push(l.source)});
const gc={};GX.nos.forEach(n=>gc[n.g]=(gc[n.g]||0)+1);const gs=Object.keys(gc).sort((a,b)=>gc[b]-gc[a]);const ang={};const asp=Math.max(1,(GX.W||1000)/(GX.H||600));gs.forEach((g,i)=>{const a=i*2.399963,rr=Math.sqrt(i)*(GX.camada=='funcoes'?70:60);ang[g]=[Math.cos(a)*rr*asp,Math.sin(a)*rr]});
GX.nos.forEach(n=>{const c=ang[n.g];n.x=c[0]+(Math.random()-.5)*60;n.y=c[1]+(Math.random()-.5)*60});
const red=matchMedia('(prefers-reduced-motion: reduce)').matches;
GX.sim=d3.forceSimulation(GX.nos).force('link',d3.forceLink(GX.lig).distance(GX.camada=='funcoes'?26:60).strength(.35))
.force('carga',d3.forceManyBody().strength(GX.camada=='funcoes'?-34:-160).distanceMax(380))
.force('gx',d3.forceX(n=>ang[n.g][0]).strength(.12)).force('gy',d3.forceY(n=>ang[n.g][1]).strength(.12))
.force('col',d3.forceCollide(n=>n.r+1.5)).alphaDecay(.028).on('tick',()=>{GX.ticks=(GX.ticks||0)+1;if(GX.ticks==60||GX.ticks==160)gxEnquadrar();gxDesenha()}).on('end',()=>{gxEnquadrar();gxDesenha()});
GX.ticks=0;if(red){GX.sim.stop();for(let i=0;i<300;i++)GX.sim.tick();gxEnquadrar();gxDesenha()}
gxLegenda();gxStats();if(GX.sel>=0&&!GX.nos[GX.sel])GX.sel=-1;gxPainel()}
function gxEnquadrar(){if(!GX.nos.length)return;const xs=GX.nos.map(n=>n.x).sort((p,q)=>p-q),ys=GX.nos.map(n=>n.y).sort((p,q)=>p-q),pc=(v,f)=>v[Math.min(v.length-1,Math.max(0,Math.round(f*(v.length-1))))];
const a=pc(xs,.02),c=pc(xs,.98),b=pc(ys,.02),d=pc(ys,.98);const W=GX.W,H=GX.H,k=Math.min((W-80)/Math.max(1,c-a),(H-150)/Math.max(1,d-b),2.4);GX.T={k,x:W/2-k*(a+c)/2,y:H/2+8-k*(b+d)/2}}
function gxDesenha(){const ctx=GX.ctx;if(!ctx)return;const {k,x,y}=GX.T;ctx.setTransform(GX.dpr,0,0,GX.dpr,0,0);ctx.clearRect(0,0,GX.W,GX.H);
ctx.save();ctx.translate(x,y);ctx.scale(k,k);
const foco=GX.hover>=0?GX.hover:GX.sel;const vz=foco>=0?new Set([foco,...GX.viz[foco]]):null;const pr=GX.proc?GX.proc.mapa:null;const ativo=i=>pr?pr.has(i):vz?vz.has(i):true;
ctx.lineWidth=.7/k;
for(const l of GX.lig){const s=l.source,t=l.target;const on=pr?(pr.has(s.index)&&pr.has(t.index)&&Math.abs(pr.get(s.index)-pr.get(t.index))==1):vz?(s.index==foco||t.index==foco):false;
if(on)continue;ctx.strokeStyle=(pr||vz)?'rgba(90,100,115,.10)':'rgba(120,132,150,.22)';ctx.beginPath();ctx.moveTo(s.x,s.y);ctx.lineTo(t.x,t.y);ctx.stroke()}
ctx.lineWidth=1.6/k;
for(const l of GX.lig){const s=l.source,t=l.target;const on=pr?(pr.has(s.index)&&pr.has(t.index)&&Math.abs(pr.get(s.index)-pr.get(t.index))==1):vz?(s.index==foco||t.index==foco):false;if(!on)continue;
ctx.strokeStyle=pr?'#A68BFF':(s.index==foco?'rgba(108,182,255,.95)':'rgba(181,156,255,.9)');ctx.beginPath();ctx.moveTo(s.x,s.y);ctx.lineTo(t.x,t.y);ctx.stroke();
const ang=Math.atan2(t.y-s.y,t.x-s.x),ex=t.x-Math.cos(ang)*(t.r+2),ey=t.y-Math.sin(ang)*(t.r+2),a=5/k;ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(ex,ey);ctx.lineTo(ex-a*Math.cos(ang-.45),ey-a*Math.sin(ang-.45));ctx.lineTo(ex-a*Math.cos(ang+.45),ey-a*Math.sin(ang+.45));ctx.fill()}
for(const n of GX.nos){const on=ativo(n.index);ctx.globalAlpha=on?1:.13;ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.fillStyle=n.teste?'#4a5260':n.cor;ctx.fill();
if(n.pii){ctx.lineWidth=2.2/k;ctx.strokeStyle='#FF6B6B';ctx.stroke()}else if(n.semTeste){ctx.lineWidth=1.6/k;ctx.strokeStyle='#e5b443';ctx.stroke()}
if(n.index==GX.sel){ctx.lineWidth=2.5/k;ctx.strokeStyle='#fff';ctx.beginPath();ctx.arc(n.x,n.y,n.r+3/k,0,6.283);ctx.stroke()}}
ctx.globalAlpha=1;ctx.textBaseline='middle';
const mostraTodos=k>2.2,lim=GX.camada=='funcoes'?(k>1.2?4:k>.6?8:14):(k>.9?0:4);const caixas=[];
const ordem=[...GX.nos].sort((p,q)=>{const e=n=>(n.index==foco||n.index==GX.sel)?2:((vz&&vz.has(n.index))||(pr&&pr.has(n.index)))?1:0;return e(q)-e(p)||q.grau-p.grau});
for(const n of ordem){const esp=n.index==foco||n.index==GX.sel||(vz&&vz.has(n.index))||(pr&&pr.has(n.index));
if(!(esp||mostraTodos||n.grau>=lim))continue;if((pr||vz)&&!esp)continue;
const fs=(esp?12:11)/k;ctx.font=`${esp?600:500} ${fs}px "IBM Plex Mono",monospace`;let t=n.nome;if(pr&&pr.has(n.index))t=(pr.get(n.index)+1)+'. '+t;
const tx=n.x+n.r+4/k,w=ctx.measureText(t).width,bx=[tx,n.y-fs*.6,tx+w,n.y+fs*.6];
if(caixas.some(c=>bx[0]<c[2]&&bx[2]>c[0]&&bx[1]<c[3]&&bx[3]>c[1]))continue;caixas.push(bx);
ctx.lineWidth=3/k;ctx.strokeStyle='rgba(10,13,17,.9)';ctx.strokeText(t,tx,n.y);ctx.fillStyle=esp?'#fff':'#c3cbd6';ctx.fillText(t,tx,n.y)}
ctx.restore()}
function gxMundo(ev){const r=GX.cv.getBoundingClientRect();return [(ev.clientX-r.left-GX.T.x)/GX.T.k,(ev.clientY-r.top-GX.T.y)/GX.T.k,ev.clientX-r.left,ev.clientY-r.top]}
function gxAcha(wx,wy){let m=-1,md=1e9;for(const n of GX.nos){const d=(n.x-wx)**2+(n.y-wy)**2,rr=(n.r+4/GX.T.k)**2;if(d<rr&&d<md){md=d;m=n.index}}return m}
function gxZoom(f,cx,cy){const T=GX.T,k2=Math.max(.08,Math.min(8,T.k*f));T.x=cx-(cx-T.x)*k2/T.k;T.y=cy-(cy-T.y)*k2/T.k;T.k=k2;gxDesenha()}
function gxEventos(){const cv=GX.cv;let arr=null;
cv.addEventListener('wheel',e=>{e.preventDefault();const [,, sx,sy]=gxMundo(e);gxZoom(Math.exp(-e.deltaY*.0015),sx,sy)},{passive:false});
cv.addEventListener('pointerdown',e=>{const [wx,wy,sx,sy]=gxMundo(e);const i=gxAcha(wx,wy);cv.setPointerCapture(e.pointerId);cv.classList.add('arrastando');
arr={i,sx,sy,x0:GX.T.x,y0:GX.T.y,mov:false};if(i>=0){const n=GX.nos[i];n.fx=n.x;n.fy=n.y;GX.sim.alphaTarget(.15).restart()}});
cv.addEventListener('pointermove',e=>{const [wx,wy,sx,sy]=gxMundo(e);
if(arr){if(Math.abs(sx-arr.sx)+Math.abs(sy-arr.sy)>3)arr.mov=true;if(arr.i>=0){const n=GX.nos[arr.i];n.fx=wx;n.fy=wy}else{GX.T.x=arr.x0+sx-arr.sx;GX.T.y=arr.y0+sy-arr.sy;gxDesenha()}return}
const i=gxAcha(wx,wy);if(i!=GX.hover){GX.hover=i;gxDesenha()}const dc=$('gx-dica');
if(i>=0){const n=GX.nos[i];dc.style.display='block';dc.style.left=Math.min(sx+14,GX.W-330)+'px';dc.style.top=(sy+14)+'px';dc.innerHTML=`<b>${esc(n.nome)}</b><small>${esc(n.tipo)} · ${esc(n.arq)}${n.linha?':'+n.linha:''}</small><small>${GX.camada=='funcoes'?`chama ${GX.sai[i].length} · chamada por ${GX.ent[i].length}`:`importa ${GX.sai[i].length} · importado por ${GX.ent[i].length}`}${n.pii?' · <span style="color:#FF6B6B">dados pessoais</span>':''}</small>`}else dc.style.display='none'});
const fim=e=>{if(!arr)return;cv.classList.remove('arrastando');if(arr.i>=0){const n=GX.nos[arr.i];n.fx=null;n.fy=null;GX.sim.alphaTarget(0)}
if(!arr.mov){GX.sel=arr.i;GX.proc=null;$('gx-proc').value='';gxPainel();gxDesenha()}arr=null};
cv.addEventListener('pointerup',fim);cv.addEventListener('pointercancel',fim);cv.addEventListener('pointerleave',()=>{GX.hover=-1;$('gx-dica').style.display='none';gxDesenha()});
const bu=$('gx-q'),res=$('gx-res');let foco=0;
bu.addEventListener('input',()=>{const q=bu.value.trim().toLowerCase();if(!q){res.style.display='none';return}
const ms=GX.nos.filter(n=>n.nome.toLowerCase().includes(q)||n.arq.toLowerCase().includes(q)).sort((a,b)=>(a.nome.toLowerCase().startsWith(q)?0:1)-(b.nome.toLowerCase().startsWith(q)?0:1)||b.grau-a.grau).slice(0,8);foco=0;
res.innerHTML=ms.length?ms.map((n,j)=>`<button class="${j==0?'foco':''}" onclick="gxFoca(${n.index})"><b class=mono>${esc(n.nome)}</b><small>${esc(n.arq)}${n.linha?':'+n.linha:''}</small></button>`).join(''):'<div style="padding:8px 10px" class=mut3>nada encontrado nesta camada</div>';res.style.display='block'});
bu.addEventListener('keydown',e=>{const bs=[...res.querySelectorAll('button')];if(e.key=='ArrowDown'||e.key=='ArrowUp'){e.preventDefault();foco=(foco+(e.key=='ArrowDown'?1:-1)+bs.length)%bs.length;bs.forEach((b,j)=>b.classList.toggle('foco',j==foco))}
if(e.key=='Enter'&&bs[foco])bs[foco].click();if(e.key=='Escape'){bu.value='';res.style.display='none'}});
document.addEventListener('keydown',e=>{if(e.key=='/'&&$('sec-grafo').classList.contains('on')&&document.activeElement!=bu){e.preventDefault();bu.focus()}
if(e.key=='Escape'&&$('sec-grafo').classList.contains('on')){GX.sel=-1;GX.proc=null;$('gx-proc').value='';gxPainel();gxDesenha()}})}
function gxFoca(i){$('gx-res').style.display='none';$('gx-q').value='';GX.sel=i;GX.proc=null;$('gx-proc').value='';const n=GX.nos[i];const k=Math.max(GX.T.k,1.8);GX.T={k,x:GX.W/2-n.x*k,y:GX.H/2-n.y*k};gxPainel();gxDesenha()}
function gxCamada(c){GX.camada=c;GX.sel=-1;GX.proc=null;GX.off.clear();document.querySelectorAll('#gx-camada button').forEach(b=>b.classList.toggle('on',b.dataset.c==c));
$('gx-proc').disabled=c!='funcoes';$('gx-proc').value='';$('gx-filtros').style.display=c=='funcoes'?'contents':'none';gxMontar()}
function gxProc(v){if(v===''){GX.proc=null;gxDesenha();gxPainel();return}const p=D.gitnexus.processos[+v];
const faltam=p.passos.some(i=>!GX.nos.some(n=>n.i==i));if(faltam){gxMontarCom(p)}else gxAplicaProc(p)}
function gxMontarCom(p){GX.proc={passos:p.passos};gxMontar();gxAplicaProc(p)}
function gxAplicaProc(p){const mapa=new Map();p.passos.forEach((i,j)=>{const n=GX.nos.find(x=>x.i==i);if(n&&!mapa.has(n.index))mapa.set(n.index,j)});GX.proc={passos:p.passos,mapa,nome:p.nome};GX.sel=-1;
const ns=[...mapa.keys()].map(i=>GX.nos[i]);if(ns.length){let a=1e9,b=1e9,c=-1e9,d=-1e9;ns.forEach(n=>{a=Math.min(a,n.x);b=Math.min(b,n.y);c=Math.max(c,n.x);d=Math.max(d,n.y)});const k=Math.min(2.4,(GX.W-360)/Math.max(80,c-a),(GX.H-200)/Math.max(80,d-b));GX.T={k,x:GX.W/2-k*(a+c)/2,y:GX.H/2-k*(b+d)/2}}
gxPainel();gxDesenha()}
function gxFiltro(k,v){GX[k]=v;GX.proc=null;$('gx-proc').value='';gxMontar()}
function gxGrupo(id){GX.off.has(id)?GX.off.delete(id):GX.off.add(id);gxMontar()}
function gxLegenda(){$('gx-leg').innerHTML=GX.grupos.map(g=>`<button class="${GX.off.has(g.id)?'off':''}" onclick="gxGrupo('${esc(g.id)}')" title="mostrar/esconder"><i class=sw style="background:${g.cor}"></i>${esc(g.nome)} <span class=mut3>${g.n}</span></button>`).join('')+
`<button style="cursor:default"><i class=sw style="background:transparent;box-shadow:inset 0 0 0 2px #FF6B6B;border-radius:50%"></i>dados pessoais</button>`+(GX.camada=='modulos'?`<button style="cursor:default"><i class=sw style="background:transparent;box-shadow:inset 0 0 0 2px #e5b443;border-radius:50%"></i>sem teste</button>`:`<button style="cursor:default"><i class=sw style="background:#4a5260;border-radius:50%"></i>teste</button>`)}
function gxStats(){const G=D.gitnexus,M=D.mapa;const s=GX.camada=='funcoes'&&G?`${GX.nos.length} de ${G.metricas.simbolos} símbolos · ${GX.lig.length} chamadas · commit <code>${esc(G.commit_grupo)}</code>`:M?`${GX.nos.length} módulos · ${GX.lig.length} imports · commit <code>${esc((M.commit_grupo||'').slice(0,7))}</code>`:'';$('gx-stats').innerHTML=s}
function gxLista(t,ids){if(!ids.length)return `<p class=k>${t}</p><p class=mut3 style="font-size:12px;margin:0">nenhum</p>`;
const u=[...new Set(ids)].sort((a,b)=>GX.nos[b].grau-GX.nos[a].grau);return `<p class=k>${t} · ${u.length}</p><ul>`+u.slice(0,40).map(i=>`<li><button onclick="gxFoca(${i})" title="${esc(GX.nos[i].arq)}"><span style="color:${GX.nos[i].cor}">●</span> ${esc(GX.nos[i].nome)}</button></li>`).join('')+(u.length>40?`<li class=mut3 style="font-size:12px;padding:4px 6px">+${u.length-40}</li>`:'')+`</ul>`}
function gxPainel(){const el=$('gx-lado');if(!el)return;
if(GX.proc&&GX.proc.mapa){const ps=[...GX.proc.mapa.entries()].sort((a,b)=>a[1]-b[1]);el.innerHTML=`<span class="selo ac">fluxo de execução</span><h3 style="margin-top:10px">${esc(GX.proc.nome)}</h3><p class=mut style="font-size:12.5px">Caminho que o GitNexus traçou a partir de um ponto de entrada, seguindo as chamadas. ${ps.length} passos.</p><ul>`+ps.map(([i,j])=>`<li><button onclick="gxFoca(${i})"><span class=mut3>${j+1}.</span> ${esc(GX.nos[i].nome)} <span class=mut3>${esc(GX.nos[i].arq.split('/').pop())}</span></button></li>`).join('')+`</ul>`;return}
if(GX.sel<0){const G=D.gitnexus;el.innerHTML=`<h3 style="font-family:'IBM Plex Sans'">Como ler</h3><p class=mut style="font-size:13px">${GX.camada=='funcoes'?'Cada ponto é uma função, método ou classe do código do grupo; cada linha, uma chamada. A cor é a comunidade (grupo de funções que se chamam muito entre si, achado pelo GitNexus). Tamanho = quantas ligações.':'Cada ponto é um módulo Python ou arquivo do frontend; cada linha, um import. Cor = pasta, tamanho = linhas de código, anel âmbar = nenhum teste importa o módulo.'}</p>
<p class=k>COMO USAR</p><ul class=mut style="font-size:12.5px;line-height:1.7;list-style:none;padding:0"><li>passe o mouse: vizinhos acendem</li><li>clique: detalhes e quem chama quem</li><li>arraste o fundo para mover · roda do mouse para zoom</li><li><kbd>/</kbd> busca · <kbd>Esc</kbd> limpa</li><li>“fluxo”: um caminho de execução passo a passo</li></ul>
${G?`<p class=k>DE ONDE VEM</p><p class=mut3 style="font-size:12px">${esc(G.ferramenta)}. ${G.simbolos?esc((G.simbolos||[]).length+' símbolos exportados'):''}. A camada “módulos” vem do <code>make mapa</code> (ast do Python). Análise estática: chamada dinâmica não aparece.</p>`:''}`;return}
const n=GX.nos[GX.sel];el.innerHTML=`<span class=selo>${esc(n.tipo)}</span>${n.pii?' <span class="selo pii">dados pessoais</span>':''}${n.teste?' <span class=selo>teste</span>':''}${n.semTeste?' <span class="selo at">sem teste</span>':''}${n.llm?' <span class="selo ac">usa LLM</span>':''}
<h3 style="margin-top:10px">${esc(n.qual)}</h3><p class=mut3 style="font:12px 'IBM Plex Mono',monospace;margin:6px 0 0;word-break:break-all">${esc(n.arq)}${n.linha?':'+n.linha:''}${n.linhas?' · '+n.linhas+' linhas':''}</p>
<p class=k>GRUPO</p><p style="margin:0;font-size:13px"><i class=sw style="background:${n.cor};margin-right:6px"></i>${esc((GX.grupos.find(g=>g.id==n.g)||{}).nome||n.g)}</p>`+
gxLista(GX.camada=='funcoes'?'CHAMA':'IMPORTA',GX.sai[n.index])+gxLista(GX.camada=='funcoes'?'É CHAMADA POR':'É IMPORTADO POR',GX.ent[n.index])+
(GX.camada=='funcoes'&&D.gitnexus?(()=>{const fs=D.gitnexus.processos.map((p,j)=>[p,j]).filter(([p])=>p.passos.includes(n.i));return fs.length?`<p class=k>FLUXOS QUE PASSAM AQUI · ${fs.length}</p><ul>`+fs.slice(0,12).map(([p,j])=>`<li><button onclick="$('gx-proc').value='${j}';gxProc('${j}')">${esc(p.nome)}</button></li>`).join('')+`</ul>`:''})():'')+
(n.mod?`<p class=k>TESTES</p>${(n.mod.testado_por||[]).length?'<ul>'+n.mod.testado_por.map(t=>`<li class=mut style="font:12px 'IBM Plex Mono',monospace;padding:2px 6px">${esc(t.split('/').pop())}</li>`).join('')+'</ul>':'<p class=at style="font-size:12.5px;margin:0">nenhum arquivo de teste importa este módulo</p>'}`:'')}
function grafoSec(){const G=D.gitnexus,M=D.mapa;const me=(M||{}).metricas||{};
let h=cab('Grafo do código','O código do grupo como um mapa navegável, no estilo do GitNexus: funções e quem chama quem, agrupadas por comunidade, com os fluxos de execução. Serve para achar onde mexer e o que pode quebrar junto.',
`<div class=seg id=gx-camada><button data-c=funcoes class="${G?'on':''}" onclick="gxCamada('funcoes')" ${G?'':'disabled'}>funções (GitNexus)</button><button data-c=modulos class="${G?'':'on'}" onclick="gxCamada('modulos')">módulos (imports)</button></div>`);
if(!G&&!M){$('grafo').innerHTML=h+`<div class=vazio-bloco><b>Sem dados de grafo.</b> Rode <code>make mapa</code> (módulos) e <code>make gitnexus</code> (funções).</div>`;return}
if(!G)GX.camada='modulos';
const cob=me.modulos?Math.round(100*(me.modulos-me.modulos_sem_teste)/me.modulos):0;
h+=`<div class=gx><div class=gx-tela><canvas id=gx-canvas role=img aria-label="grafo do código do grupo: nós são funções ou módulos, linhas são chamadas ou imports"></canvas>
<div class=gx-barra><div class=gx-busca><input id=gx-q placeholder="buscar função ou arquivo  ( / )" autocomplete=off aria-label="buscar no grafo"><div class=gx-res id=gx-res></div></div>
<select id=gx-proc onchange="gxProc(this.value)" aria-label="fluxo de execução" ${G?'':'disabled'}><option value="">fluxo de execução…</option>${G?G.processos.map((p,j)=>`<option value=${j}>${esc(p.nome)} (${p.passos.length})</option>`).join(''):''}</select>
<span id=gx-filtros style="display:contents"><label class=tg><input type=checkbox checked onchange="gxFiltro('semTeste',this.checked)"> esconder testes</label><label class=tg><input type=checkbox checked onchange="gxFiltro('soLig',this.checked)"> só ligados</label></span>
<span id=gx-stats class=mut3 style="font-size:12px;margin-left:auto;background:rgba(10,13,17,.8);padding:4px 8px;border-radius:6px"></span></div>
<div class=gx-leg id=gx-leg></div><div class=gx-zoom><button onclick="gxZoom(1.3,GX.W/2,GX.H/2)" aria-label="aproximar">+</button><button onclick="gxZoom(1/1.3,GX.W/2,GX.H/2)" aria-label="afastar">−</button><button onclick="gxEnquadrar();gxDesenha()" aria-label="enquadrar tudo">⤢</button></div><div class=gx-dica id=gx-dica></div></div>
<aside class=gx-lado id=gx-lado></aside></div>`;
h+=`<div class=g12 style="margin-top:16px">
<div class="c3 kpi"><span>Símbolos no grafo</span><b>${G?G.metricas.simbolos:'—'}</b><em>funções, métodos e classes · ${G?G.metricas.chamadas+' chamadas':'rode make gitnexus'}</em></div>
<div class="c3 kpi"><span>Comunidades e fluxos</span><b>${G?G.metricas.comunidades+' · '+G.metricas.processos:'—'}</b><em>agrupamentos por coesão · caminhos de execução</em></div>
<div class="c3 kpi"><span>Módulos</span><b>${me.modulos??'—'}</b><em>${me.funcoes??''} funções pela análise do ast</em></div>
<div class="c3 kpi"><span>Módulos com teste</span><b class="${cob>=80?'ok':'at'}">${me.modulos?(me.modulos-me.modulos_sem_teste)+'/'+me.modulos:'—'}</b><div class=barra-cob><i style="width:${cob}%"></i></div><em>${me.modulos_sem_teste??''} sem nenhum teste que os importe</em></div></div>`;
h+=`<div class=g12 style="margin-top:16px"><div class="c12 painel"><div class=ph><h3>Etapas do pipeline no código</h3><p>Onde cada etapa do Íris mora e a evidência de que uma rota da API chega até ela. Issues em âmbar estão abertas.</p></div><div class=rolar><table><thead><tr><th class=num>#</th><th>etapa</th><th>status</th><th>onde</th><th>evidência</th></tr></thead><tbody>`+((M&&M.etapas_pipeline)||[]).map(e=>{const k=e.status=='implementada'?'ok':e.status=='parcial'?'at':'neu';const pii=PII_RE.test(e.etapa+e.modulo);
return `<tr style="${pii?'background:#2A1518':''}"><td class="num mut3">${e.ordem}</td><td style="min-width:200px"><b>${esc(e.etapa)}</b>${pii?' <span class="selo pii">dados pessoais</span>':''}</td><td style="white-space:nowrap"><span style="display:inline-flex;gap:6px;align-items:center">${ic(k)}<span class=${k=='neu'?'mut3':k}>${esc(e.status.replace('_',' '))}</span></span></td><td><code style="font-size:12px;word-break:break-all">${esc(e.modulo)}${e.funcao?':'+esc(e.funcao):''}</code></td><td class=mut style="font-size:12.5px;line-height:1.7">${issues(e.evidencia)}</td></tr>`}).join('')+`</tbody></table></div></div>`;
const mods=[...((M&&M.modulos)||[])].sort((a,b)=>(b.importado_por||[]).length-(a.importado_por||[]).length);
h+=`<div class="c12 painel"><details><summary><b style="color:var(--tx)">Tabela dos ${mods.length} módulos</b> · ordenados por quantos outros dependem deles</summary><div class=rolar><table><thead><tr><th>módulo</th><th class=num>linhas</th><th class=num>funções</th><th class=num>usado por</th><th class=num>usa</th><th>LLM</th><th class=num>testes</th></tr></thead><tbody>`+mods.map(m=>`<tr><td><code style="font-size:12px">${esc(m.id)}</code>${PII_RE.test(m.id)?' <span class="selo pii">dados pessoais</span>':''}</td><td class=num>${m.linhas}</td><td class=num>${(m.funcoes||[]).length}</td><td class=num>${(m.importado_por||[]).length}</td><td class=num>${(m.importa||[]).length}</td><td>${m.usa_llm?'<span class="selo ac">LLM</span>':''}</td><td class="num ${(m.testado_por||[]).length?'ok':'at'}">${(m.testado_por||[]).length||'nenhum'}</td></tr>`).join('')+`</tbody></table></div></details></div></div>`;
$('grafo').innerHTML=h;gxPainel()}


/* ---------- GitHub: PRs, issues, tendência, comparação PR x dev ---------- */
const GH=D.github||null;const ISS={};((GH&&GH.issues)||[]).forEach(i=>ISS[i.numero]=i);
const PIOR_SUBINDO=/erro|sem_teste|nao_implementad|latencia|falh|vaz/;
const NOME_M={adversarial_ok:'adversarial ok',pii_ok:'dados pessoais bloqueados',injecao_ok:'injeção barrada',formato_ok:'formatos ok',etapas_ok:'etapas ok',etapas_nao_implementadas:'etapas não implementadas',etapas_erro:'etapas com erro',latencia_pipeline_s:'latência do pipeline (s)',modulos:'módulos',modulos_sem_teste:'módulos sem teste',funcoes:'funções',simbolos:'símbolos',chamadas:'chamadas',ablacao_trcc_micro:'retenção curricular (ablação)',ablacao_comando_conj_pct:'comandos separados (%)',ablacao_falhas:'falhas na ablação',
avaliacao_nota:'nota do conjunto lacrado',avaliacao_trcc_aprovado:'retenção ≥ 0,95',avaliacao_aderencia_nivel:'segue o nível de apoio',avaliacao_conjugado_resolvido:'comandos separados',
ataque_vazamento_pct:'vazamento no ataque (%)',ataque_vaza_nome_pct:'vaza nome (%)',ataque_vaza_documento_pct:'vaza documento (%)',ataque_vaza_contato_pct:'vaza contato (%)',ataque_vaza_clinico_pct:'vaza dado clínico (%)',
ataque_falso_positivo_pct:'falso alarme do filtro (%)',ataque_padroes:'padrões de vazamento',orcamento_estouros_duros:'estouros de orçamento',adversarial_ok:'ataques planejados barrados',adversarial_total:'ataques planejados',pii_total:'casos de dado pessoal',injecao_total:'casos de injeção',formato_total:'formatos testados'};
function nomeM(k){return NOME_M[k]||k.replace(/_/g,' ')}
function devRodadas(){return RODADAS.filter(r=>r.alvo!=='pr')}
function ultimaDev(){const d=devRodadas().filter(r=>r.metricas);return d[d.length-1]}
function rodadaPR(n,sha){const xs=RODADAS.filter(r=>r.alvo==='pr'&&r.pr==n&&(!sha||r.commit_grupo==sha.slice(0,7)));return xs[xs.length-1]}
function delta(k,a,b){if(a==null||b==null||typeof a!='number'||typeof b!='number')return null;const d=+(b-a).toFixed(3);if(!d)return {d,cls:'mut3'};const ruim=PIOR_SUBINDO.test(k)?d>0:d<0;return {d,cls:ruim?(/pii/.test(k)?'pii':'er'):'ok'}}
function comparaPR(r){const dv=ultimaDev();if(!r||!r.metricas||!dv||!dv.metricas)return '';const ms=[];for(const k of Object.keys(r.metricas)){const x=delta(k,dv.metricas[k],r.metricas[k]);if(x&&x.d)ms.push(`<span class="${x.cls}" title="${esc(nomeM(k))}: dev ${dv.metricas[k]} → PR ${r.metricas[k]}">${x.d>0?'+':''}${x.d} ${esc(nomeM(k))}</span>`)}
return ms.length?ms.join('<br>'):'<span class=mut3>sem mudança nas métricas</span>'}
function etapaDoArquivo(p){const M=D.mapa;if(!M)return null;for(const e of M.etapas_pipeline||[]){const m=(e.modulo||'').replace(/\./g,'/');if(m&&p.includes(m))return e}return null}
function etapasDaIssue(n){const M=D.mapa,s=new Set();if(!M)return [];(M.etapas_pipeline||[]).forEach(e=>{if(new RegExp('#'+n+'\\b').test(e.evidencia||''))s.add(e.ordem)});
((GH&&GH.prs)||[]).filter(p=>(p.issues||[]).includes(n)).forEach(p=>(p.arquivos||[]).forEach(f=>{const e=etapaDoArquivo(f);if(e)s.add(e.ordem)}));return [...s].sort((a,b)=>a-b)}
function issueChip(n){const i=ISS[n];return `<span class=iss title="${esc(i?i.titulo:'issue fechada ou fora da lista')}">#${n}${i?'':' ✓'}</span>`}
function lgpd(i){return (i.rotulos||[]).some(l=>/privacy|lgpd/i.test(l))}
function ciSelo(c){return {sucesso:'<span class="selo ok">CI ok</span>',falha:'<span class="selo er">CI falhou</span>',pendente:'<span class=selo>CI na fila</span>',sem_check:'<span class=selo>sem CI</span>'}[c]||''}
function idade(d){return d==null?'':d<1?'hoje':Math.round(d)+(Math.round(d)==1?' dia':' dias')}
function prsSec(){let h=cab('PRs e issues','O que está aberto no repositório do grupo: cada PR com idade, dono, o que ele resolve e o resultado dos mesmos portões rodados na cabeça do PR, comparado com o dev. As issues aparecem ligadas à etapa do pipeline que tocam.');
if(!GH){$('prs').innerHTML=h+`<div class=vazio-bloco><b>Ainda sem dados do GitHub.</b> Rode <code>make github</code> (lê PRs e issues abertos com o <code>gh</code>, só leitura).</div>`;return}
if(GH.erro)h+=`<div class=vazio-bloco style="margin-bottom:16px"><b>Não deu para ler o GitHub agora:</b> ${esc(GH.erro)}</div>`;
const prs=GH.prs||[];const dv=ultimaDev();
h+=`<div class=g12><div class="c12 painel plano"><div class=ph style="padding:14px 16px 0"><h3>PRs abertos · ${prs.length}</h3><p>“vs dev” compara as métricas da verificação automática na cabeça do PR com a última rodada do dev${dv?` (<code>${esc(dv.commit_grupo)}</code>)`:''}. Vermelho = piora; vermelho com cadeado = piora no filtro de dados pessoais.</p></div><div class=rolar><table><thead><tr><th style="padding-left:16px">PR</th><th>dono</th><th class=num>idade</th><th>CI do grupo</th><th>resolve / avança</th><th>etapas tocadas</th><th>portões no PR</th><th>vs dev</th></tr></thead><tbody>`+
prs.map(p=>{const r=rodadaPR(p.numero,p.sha);const ets=[...new Set((p.arquivos||[]).map(f=>{const e=etapaDoArquivo(f);return e?e.ordem:null}).filter(x=>x))];
return `<tr><td style="padding-left:16px;min-width:300px"><a href="${esc(p.url)}" target=_blank rel=noopener><b>#${p.numero}</b></a> ${esc(p.titulo)}${p.rascunho?' <span class=selo>rascunho</span>':''}<div class=mut3 style="font:11.5px 'IBM Plex Mono',monospace">${esc(p.branch)} → ${esc(p.base)} · <code>${esc(p.sha)}</code> · ${(p.arquivos||[]).length} arquivos</div></td><td class=mut>${esc(p.autor)}</td><td class="num ${p.idade_dias>3?'at':''}">${idade(p.idade_dias)}</td><td>${ciSelo(p.ci)}</td>
<td>${(p.issues||[]).map(n=>{const i=ISS[n];return `<div style="font-size:12.5px;margin-bottom:2px">${issueChip(n)} ${i?esc(i.titulo.slice(0,60)):''}${i&&lgpd(i)?' <span class="selo pii">LGPD</span>':''}</div>`}).join('')||'<span class=mut3>nenhuma citada</span>'}</td>
<td>${ets.map(o=>`<span class=iss>${o}</span>`).join(' ')||'<span class=mut3>—</span>'}</td>
<td>${r?matriz(r)+' '+(r.aprovado?'<span class="selo ok">aprovado</span>':'<span class="selo er">reprovado</span>'):'<span class=mut3 style="font-size:12px">na fila da verificação</span>'}</td><td style="font-size:12.5px;white-space:nowrap">${comparaPR(r)||'<span class=mut3>—</span>'}</td></tr>`}).join('')+`</tbody></table></div></div>`;
const iss=[...(GH.issues||[])].filter(i=>!/epic|theme/.test(i.tipo||'')).sort((a,b)=>(b.prs||[]).length-(a.prs||[]).length||b.idade_dias-a.idade_dias);
const macro=[...(GH.issues||[])].filter(i=>/epic|theme/.test(i.tipo||'')).length;
h+=`<div class="c12 painel plano"><div class=ph style="padding:14px 16px 0"><h3>Issues abertas · ${iss.length} histórias e bugs</h3><span class=mut3 style="font-size:12.5px">${macro} épicos e temas fora da lista</span><p>“Etapa” sai da evidência do mapa do código e dos arquivos dos PRs que citam a issue; sem dono aparece em âmbar.</p></div><div class=rolar><table><thead><tr><th style="padding-left:16px">issue</th><th>dono</th><th class=num>idade</th><th>etapas do pipeline</th><th>PRs abertos</th><th>rótulos</th></tr></thead><tbody>`+
iss.map(i=>{const ets=etapasDaIssue(i.numero);return `<tr style="${lgpd(i)?'box-shadow:inset 3px 0 0 var(--pii)':''}"><td style="padding-left:16px;min-width:320px"><a href="${esc(i.url)}" target=_blank rel=noopener><b>#${i.numero}</b></a> ${esc(i.titulo)}${lgpd(i)?' <span class="selo pii">LGPD</span>':''}</td><td class="${(i.donos||[]).length?'mut':'at'}">${(i.donos||[]).map(esc).join(', ')||'sem dono'}</td><td class="num mut">${idade(i.idade_dias)}</td><td>${ets.map(o=>{const e=(D.mapa.etapas_pipeline||[]).find(x=>x.ordem==o);return `<span class=iss title="${esc(e?e.etapa:'')}">${o} ${esc(e?e.etapa.split(/[ /(]/)[0]:'')}</span>`}).join(' ')||'<span class=mut3>—</span>'}</td><td>${(i.prs||[]).map(n=>`<span class="iss open">PR #${n}</span>`).join(' ')||'<span class=mut3>—</span>'}</td><td class=mut3 style="font-size:11.5px">${(i.rotulos||[]).filter(l=>!/^type/.test(l)).map(esc).join(' · ')}</td></tr>`}).join('')+`</tbody></table></div></div>`;
const inst=GH.instaveis||[];
h+=`<div class="c6 painel"><div class=ph><h3>CI instável</h3><p>Commit em que o mesmo CI deu sucesso e falha (rodou de novo e mudou). Teste que muda sem mudar o código esconde bug de verdade.</p></div>${inst.length?inst.map(x=>`<div class=gate>${ic('at')}<div><code>${esc(x.sha)}</code> ${esc(x.branch)}</div><span class=mut3 style="font-size:12px">${esc(x.conclusoes.join(' → '))}</span></div>`).join(''):`<p class=mut style="margin:0">Nenhum nas últimas ${(GH.ci_historico||[]).length} execuções do CI.</p>`}</div>`;
const M=D.mapa;
h+=`<div class="c6 painel"><div class=ph><h3>Testes por etapa do pipeline</h3><p>Quantos arquivos de teste importam o módulo de cada etapa (análise do <code>make mapa</code>). Zero = a etapa muda sem nenhum teste avisar.</p></div>`+(M?`<table><tbody>`+(M.etapas_pipeline||[]).map(e=>{const mod=(M.modulos||[]).find(m=>m.id==e.modulo);const n=mod?(mod.testado_por||[]).length:null;return `<tr><td class="num mut3" style="width:28px">${e.ordem}</td><td>${esc(e.etapa.replace(/\s*\(.*\)/,''))}</td><td class="num ${n?'ok':'at'}">${n==null?'—':n||'nenhum'}</td><td style="width:40%"><div class=barra-cob><i style="width:${Math.min(100,(n||0)*20)}%;background:${n?'var(--ok)':'var(--at)'}"></i></div></td></tr>`}).join('')+`</tbody></table>`:'<p class=vazio>Rode make mapa.</p>')+`</div></div>`;
$('prs').innerHTML=h}

function tendencia(){const rs=devRodadas().filter(r=>r.metricas);if(rs.length<2)return `<div class=vazio-bloco><b>Tendência por commit.</b> Aparece a partir da segunda verificação automática com métricas (${rs.length} até agora): cada número do código do grupo, commit a commit, com a primeira rodada como linha de base.</div>`;
const ks=Object.keys(rs[rs.length-1].metricas).filter(k=>typeof rs[rs.length-1].metricas[k]=='number');const base=rs[0].metricas;
return `<div class=g12>`+ks.map(k=>{const vs=rs.map(r=>r.metricas[k]).filter(v=>typeof v=='number');if(!vs.length)return '';const mn=Math.min(...vs,base[k]??vs[0]),mx=Math.max(...vs,base[k]??vs[0]),W=220,H=48,X=i=>6+i*(W-12)/Math.max(1,rs.length-1),Y=v=>mx==mn?H/2:H-6-(v-mn)*(H-12)/(mx-mn);
const atual=rs[rs.length-1].metricas[k],dd=delta(k,base[k],atual);
let s=`<svg viewBox="0 0 ${W} ${H}" width=100% height=${H} aria-hidden=true>`+(base[k]!=null?`<line x1=0 x2=${W} y1=${Y(base[k])} y2=${Y(base[k])} stroke=#4a5260 stroke-dasharray=3,3 />`:'')+`<polyline fill=none stroke=#A68BFF stroke-width=1.6 points="${rs.map((r,i)=>r.metricas[k]!=null?X(i)+','+Y(r.metricas[k]):'').filter(Boolean).join(' ')}"/>`+rs.map((r,i)=>r.metricas[k]!=null?`<circle cx=${X(i)} cy=${Y(r.metricas[k])} r=3 fill="${r.aprovado?'#34D399':'#ff6b6b'}"><title>${esc(r.commit_grupo)} · ${r.metricas[k]}</title></circle>`:'').join('')+`</svg>`;
return `<div class="c3 kpi" style="min-height:0"><span>${esc(nomeM(k))}</span><b style="font-size:20px">${atual}${dd&&dd.d?` <small class=${dd.cls} style="font-size:12px">${dd.d>0?'+':''}${dd.d} desde a base</small>`:''}</b>${s}</div>`}).join('')+`</div>`}

/* ---------- etapas explicadas e chamadas dos agentes ---------- */
let ETSEL=null,CHSEL=null;
/* fluxo vertical da aba Pipeline inteiro: estrutura (ids de etapa do 31-etapas.json) */
const FLUXO=[
{fase:'Entrada do material',quando:'uma vez por material',itens:[
 {ramo:[['upload_tamanho','extracao_documento'],['entrada_texto']],rotulos:['arquivo .pdf, .docx ou .txt','texto colado']},
 'filtro_pii','validacao_conteudo']},
{fase:'Estrutura da atividade',quando:'uma vez por material',itens:['decomposicao_estrutural','organizacao_texto_corrido']},
{fase:'Quem é o aluno',quando:'uma vez por material',itens:['selecao_caracteristicas','perfil_pedagogico']},
{fase:'Adaptação',quando:'repete para cada questão',laco:true,itens:[
 {porta:'agentes',texto:'questão com menos de 15 caracteres: pula os agentes'},
 'extrator_curricular','busca_rag','contexto_rag',
 {par:['agente_estrategista','diretiva_substituta_arnes'],rotulos:['previsto: ainda não existe no grupo','hoje, no lugar dele (bancada)']},
 'conferencia_citacoes','agente_adaptador',
 {no:'laudo_isolamento_escopo',lado:'reprovado: entrega a saída de reserva'},
 {no:'agente_auditor',lado:'reprova: volta ao Adaptador (máx. 2 vezes)'},
 'ciclo_rnf07']}
];
function fxIdx(id){return (D.etapas.etapas||[]).findIndex(e=>e.etapa==id)}
function fxSeg(t){if(t==null)return '';t=Number(t);return t<0.01?'<0,01 s':t.toFixed(2).replace('.',',')+' s'}
function fxNo(id){const j=fxIdx(id);if(j<0)return '';const e=D.etapas.etapas[j];
const sts=Object.values(e.status_por_material||{});const ni=sts.length&&sts.every(x=>x=='nao_implementada');
const banc=/bancada/i.test(e.nome);const par=!ni&&!banc&&e.macro_status=='parcial';
const cls=['fx-no',ni?'ni':'',e.dados_pessoais?'fx-pii':'',par?'par':'',banc?'banc':'',ETSEL===j?'sel':''].join(' ');
const sel=[e.dados_pessoais?'<span class="selo pii">dados pessoais</span>':'',e.agente&&!banc?'<span class="selo ac">agente</span>':'',
banc?'<span class=selo>bancada</span>':'',ni?'<span class=selo>não existe ainda</span>':par?'<span class="selo at">parcial</span>':''].join('');
return `<button class="${cls}" data-id="${id}" onclick="ETSEL=${ETSEL===j?'null':j};pipeline()" aria-pressed="${ETSEL===j}"><span class=fx-t><b>${esc(e.nome.replace(/ \(não existe ainda\)| \(bancada\)/,''))}</b><em>${ni?'':fxSeg((e.exemplo||{}).latencia_s)}</em></span>${sel?`<span class=fx-s>${sel}</span>`:''}</button>`}
function fxItem(it){
if(typeof it=='string')return `<div class=fx-seta></div>${fxNo(it)}`;
if(it.ramo)return `<div class=fx-seta></div><div class=fx-ramo>`+it.ramo.map((r,k)=>`<div class=fx-col><span class=fx-rot>${esc(it.rotulos[k])}</span>${r.map((id,m)=>(m?'<div class=fx-seta></div>':'')+fxNo(id)).join('')}<div class=fx-desce></div></div>`).join('')+`<div class=fx-junta></div></div>`;
if(it.par)return `<div class=fx-seta></div><div class="fx-ramo fx-alt">`+it.par.map((id,k)=>`<div class=fx-col><span class=fx-rot>${esc(it.rotulos[k])}</span>${fxNo(id)}<div class=fx-desce></div></div>`).join('')+`<div class=fx-junta></div></div>`;
if(it.porta){const j=fxIdx(it.porta);return `<div class=fx-porta><button data-id="porta" class="fx-lado ${ETSEL===j?'sel':''}" onclick="ETSEL=${ETSEL===j?'null':j};pipeline()">↳ ${esc(it.texto)}</button></div>`}
if(it.no)return `<div class=fx-seta></div><div class=fx-comlado>${fxNo(it.no)}<span class=fx-lado>${/volta/.test(it.lado)?'↩':'↳'} ${esc(it.lado)}</span></div>`;return ''}
function fxDetalhe(){const E=D.etapas;if(ETSEL===null||!E.etapas[ETSEL])return `<div class="fx-det vazio"><b>Clique numa etapa</b><p class=mut>Aqui aparece o que ela faz, por que existe, o que o professor vê se ela falhar e um exemplo real do que entrou e do que saiu.</p></div>`;
const e=E.etapas[ETSEL],x=e.exemplo||{};
return `<div class="fx-det ${e.dados_pessoais?'fx-pii':''}"><div class=ph><h3>${esc(e.nome)}</h3><button class="btn sec mini" onclick="ETSEL=null;pipeline()">fechar</button></div>
<p style="margin:0 0 10px">${esc(e.o_que_faz)}</p>
<p class=k>POR QUE EXISTE</p><p>${esc(e.por_que_existe)}</p>
<p class=k>SE FALHAR, O PROFESSOR VÊ</p><p>${esc(e.se_falhar)}</p>
<p class=k>ENTROU <span class=mut3>· ${esc(x.material||'')}${x.questao?' · '+esc(x.questao):''}</span></p><pre>${esc(x.entrada||'')}</pre>
<p class=k>SAIU <span class=mut3>· ${fxSeg(x.latencia_s)} · ${esc(x.status||'')}</span></p><pre>${esc(x.saida||'')}</pre>
<p class=mut3 style="font:11.5px 'IBM Plex Mono',monospace;margin:10px 0 0;overflow-wrap:anywhere">${esc(e.funcao||'')}</p></div>`}
function fluxoEtapas(){const E=D.etapas;if(!E)return `<div class=vazio-bloco><b>O que cada etapa faz.</b> Rode <code>make etapas</code>.</div>`;
const leg=`<p class=fx-leg><span><i class=sw style="border:1.5px solid var(--bd2);background:var(--s2)"></i>existe no código do grupo</span><span><i class=sw style="border:1.5px solid var(--atbd);background:var(--atbg)"></i>parcial</span><span><i class=sw style="border:1.5px dashed var(--bd2)"></i>ainda não existe</span><span><i class=sw style="border:1.5px solid var(--piibd);background:var(--piibg)"></i>mexe com dados pessoais</span></p>`;
let h=`<div class=ph><h3>O caminho de um material · ${E.etapas.length} etapas</h3><p>De cima para baixo, na ordem em que o código do grupo roda (commit <code>${esc(E.commit_grupo||'')}</code>). O tempo é do exemplo nesta máquina, com o modelo substituto. Clique numa etapa para ver o exemplo real.</p>${leg}</div>`;
h+=`<div class=fx-grade><div class=fx>`+FLUXO.map((f,k)=>`<section class="fx-fase ${f.laco?'laco':''}"><header><span class=fx-num>${k+1}</span><b>${esc(f.fase)}</b><em>${esc(f.quando)}</em></header><div class=fx-corpo>${f.itens.map(fxItem).join('').replace(/^<div class=fx-seta><\/div>/,'')}</div>${f.laco?'<span class=fx-volta>↺ próxima questão</span>':''}</section>`).join('<div class="fx-seta grande"></div>')+`<div class="fx-seta grande"></div><div class=fx-fim>adaptação entregue ao professor</div></div>${fxDetalhe()}</div>`;
setTimeout(fxSetas,0);setTimeout(fxSetas,480);
return h}
function fxSetas(){const f=document.querySelector('#sec-pipeline .fx-fase.laco');if(!f)return;f.querySelectorAll('svg.fx-svg').forEach(x=>x.remove());
f.classList.add('com-setas');
const R=f.getBoundingClientRect(),no=id=>{const e=f.querySelector(`[data-id="${id}"]`);if(!e)return null;const r=e.getBoundingClientRect();return {l:r.left-R.left,r:r.right-R.left,t:r.top-R.top,b:r.bottom-R.top,m:(r.top+r.bottom)/2-R.top}};
const ad0=f.querySelector('[data-id="agente_adaptador"]');if(!ad0)return;{const r=ad0.getBoundingClientRect(),R0=f.getBoundingClientRect();if(r.left-R0.left<112||R0.right-r.right<104){f.classList.remove('com-setas');return}}
const ad=no('agente_adaptador'),la=no('laudo_isolamento_escopo'),au=no('agente_auditor'),tt=no('ciclo_rnf07'),ex=no('extrator_curricular'),po=no('porta');if(!(ad&&la&&au&&tt&&ex))return;
const AM='#E5B443',RX='#A68BFF',CZ='#8A8A9A';
const seta=(d,c,tr)=>`<path d="${d}" fill="none" stroke="${c}" stroke-width="1.8" ${tr?'stroke-dasharray="5 4"':''} marker-end="url(#fxp-${c.slice(1)})"/>`;
const rot=(x,y,t,c,anc)=>`<text x="${x}" y="${y}" fill="${c}" font-size="11.5" font-family="IBM Plex Sans,sans-serif" paint-order="stroke" stroke="#1F1F25" stroke-width="4" text-anchor="${anc||'start'}">${t}</text>`;
const D1=ad.r+30,D2=ad.r+84,E1=ad.l-28,E2=Math.max(6,ad.l-120);let p='';
p+=seta(`M${au.r} ${au.m} H${D1} V${ad.m} H${ad.r+7}`,AM,1)+rot(D1+6,(au.m+ad.m)/2,'reprova',AM)+rot(D1+6,(au.m+ad.m)/2+14,'(máx. 2×)',AM);
p+=seta(`M${la.l} ${la.m} H${E1} V${tt.t+10} H${tt.l-7}`,AM,1)+rot(E1-5,(la.m+tt.t)/2,'reprovado',AM,'end')+rot(E1-5,(la.m+tt.t)/2+14,'→ reserva',AM,'end');
p+=seta(`M${tt.l} ${tt.b-8} H${E2} V${ex.m} H${ex.l-7}`,RX,0)+rot(E2+5,ex.m-8,'↺ próxima questão',RX);
if(po)p+=seta(`M${po.r} ${po.m} H${D2} V${tt.m} H${tt.r+7}`,CZ,1);
const mk=[AM,RX,CZ].map(c=>`<marker id="fxp-${c.slice(1)}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${c}"/></marker>`).join('');
f.insertAdjacentHTML('beforeend',`<svg class=fx-svg width="${f.clientWidth}" height="${f.clientHeight}" aria-hidden="true"><defs>${mk}</defs>${p}</svg>`)}
window.addEventListener('resize',()=>{clearTimeout(window.__fxT);window.__fxT=setTimeout(fxSetas,120)});

function etapasExplicadas(){const E=D.etapas;if(!E)return `<div class=vazio-bloco><b>O que cada etapa faz.</b> Rode <code>make etapas</code>: gera a explicação de cada etapa e agente, com um exemplo real de entrada e saída e o rastro de cada chamada ao modelo.</div>`;
let h=`<div class=ph><h3>O que cada etapa faz · ${E.etapas.length} etapas</h3><p>Clique numa etapa para ver um exemplo real do que entrou e do que saiu. Vermelho = mexe com dados pessoais; tracejada = ainda não existe no código do grupo.</p></div><div class=g12>`;
h+=E.etapas.map((e,j)=>{const sts=Object.values(e.status_por_material||{});const ni=sts.length&&sts.every(s=>s=='nao_implementada');const er=sts.some(s=>s=='erro');
return `<button class="c3 passo ${ni?'nao_implementada':''} ${e.dados_pessoais?'pii':''}" style="all:unset;box-sizing:border-box;cursor:pointer;min-width:0;${ETSEL===j?'outline:2px solid var(--ac);':''}" onclick="ETSEL=${ETSEL===j?'null':j};pipeline()"><div class="passo ${ni?'nao_implementada':''} ${e.dados_pessoais?'pii':''}" style="height:100%"><span class=n style="flex-wrap:wrap;gap:4px">${e.macro?'etapa '+e.macro:''}<span style="display:flex;gap:4px;flex-wrap:wrap">${e.agente?'<span class="selo ac">agente</span>':''}${e.dados_pessoais?'<span class="selo pii">dados pessoais</span>':''}${er?'<span class="selo er">erro</span>':ni?'<span class=selo>não existe ainda</span>':''}</span></span><b>${esc(e.nome)}</b><span class=mut style="font-size:12.5px">${esc(e.o_que_faz)}</span><small>${esc(e.funcao||'')}</small></div></button>`}).join('')+`</div>`;
if(ETSEL!==null&&E.etapas[ETSEL]){const e=E.etapas[ETSEL],x=e.exemplo||{};h+=`<div class="painel" style="margin-top:16px;border-color:${e.dados_pessoais?'var(--piibd)':'var(--bd2)'}"><div class=ph><h3>${esc(e.nome)} <span class=mut3 style="font:12px 'IBM Plex Mono',monospace">${esc(e.etapa)}</span></h3><button class="btn sec mini" onclick="ETSEL=null;pipeline()">fechar</button></div>
<div class=g12><div class=c4><p class=k style="margin:0 0 4px;color:var(--tx3);font-size:12px">POR QUE EXISTE</p><p style="margin:0 0 12px">${esc(e.por_que_existe)}</p><p style="margin:0 0 4px;color:var(--tx3);font-size:12px">SE FALHAR, O PROFESSOR VÊ</p><p style="margin:0 0 12px">${esc(e.se_falhar)}</p><p class=mut3 style="font-size:12px;margin:0">exemplo: ${esc(x.material||'')} ${x.questao?'· '+esc(x.questao):''} · ${x.latencia_s!=null?Number(x.latencia_s).toFixed(3)+' s':''} · ${esc(x.status||'')}</p></div>
<div class=c4><p style="margin:0 0 4px;color:var(--tx3);font-size:12px">ENTROU</p><pre style="max-height:300px">${esc(x.entrada||'')}</pre></div><div class=c4><p style="margin:0 0 4px;color:var(--tx3);font-size:12px">SAIU</p><pre style="max-height:300px">${esc(x.saida||'')}</pre></div></div></div>`}
return h}
function chamadas(){const E=D.etapas;if(!E||!(E.chamadas||[]).length)return '';const C=E.chamadas;
let h=`<div class="painel plano" style="margin-top:16px"><div class=ph style="padding:14px 16px 0"><h3>Chamadas dos agentes · ${C.length}</h3><p>Cada vez que um agente chamou o modelo: o que mandou (prompt), o que voltou, tokens e tempo, como num Langfuse. ${esc(E.aviso||'')}</p></div><div class=g12 style="gap:0"><div class="${CHSEL!==null?'c6':'c12'} rolar" style="border-right:${CHSEL!==null?'1px solid var(--bd)':'0'}"><table><thead><tr><th style="padding-left:16px">material · questão</th><th>agente</th><th>modelo</th><th class=num>tokens</th><th class=num>tempo</th><th>status</th></tr></thead><tbody>`+
C.map((c,j)=>`<tr class="${CHSEL===j?'sel':''}" style="cursor:pointer;${CHSEL===j?'background:var(--acbg)':''}" onclick="CHSEL=${CHSEL===j?'null':j};pipeline()"><td style="padding-left:16px">${esc(c.material)} <span class=mut3>${esc(c.questao||'')}</span></td><td><b>${esc((c.etapa||'').replace(/_/g,' '))}</b></td><td class=mut style="font-size:12px">${esc(c.modelo||'')} <span class=mut3>${esc(c.provedor||'')}</span></td><td class=num>${c.tokens_entrada??'—'} → ${c.tokens_saida??'—'}</td><td class=num>${c.latencia_s!=null?Number(c.latencia_s).toFixed(3)+' s':''}</td><td>${c.erro?'<span class="selo er">erro</span>':c.status=='ok'?'<span class="selo ok">ok</span>':`<span class=selo>${esc(c.status||'')}</span>`}</td></tr>`).join('')+`</tbody></table></div>`;
if(CHSEL!==null&&C[CHSEL]){const c=C[CHSEL],pr=c.prompt;const prT=typeof pr=='object'&&pr?`<p class=mut3 style="font-size:12px;margin:0 0 4px">SISTEMA</p><pre style="max-height:220px;margin-bottom:10px">${esc(pr.sistema||'')}</pre><p class=mut3 style="font-size:12px;margin:0 0 4px">USUÁRIO</p><pre style="max-height:260px">${esc(pr.usuario||'')}</pre>`:`<pre style="max-height:420px">${esc(pr||'')}</pre>`;
h+=`<div class=c6 style="padding:14px 16px"><div class=ph><h3>${esc((c.etapa||'').replace(/_/g,' '))} · ${esc(c.material)} ${esc(c.questao||'')}</h3><button class="btn sec mini" onclick="CHSEL=null;pipeline()">fechar</button></div><p class=mut3 style="font:12px 'IBM Plex Mono',monospace;margin:0 0 10px">${esc(c.run_id||'')} · ${esc(c.modelo||'')} · ${c.tokens_entrada??'?'} tokens entrada · ${c.tokens_saida??'?'} saída · ${c.latencia_s!=null?Number(c.latencia_s).toFixed(3)+' s':''}</p><p class=mut3 style="font-size:12px;margin:0 0 4px">PROMPT</p>${prT}<p class=mut3 style="font-size:12px;margin:12px 0 4px">RESPOSTA</p><pre style="max-height:300px">${esc(c.saida||'')}</pre>${c.erro?`<p class=er style="font-size:12.5px">${esc(c.erro)}</p>`:''}</div>`}
return h+`</div></div>`}

/* ---------- modo local: rodar os make pela página ---------- */
let LOCAL=null,JOB=null;
async function detectarLocal(){try{const r=await fetch('/api/ping',{cache:'no-store'});if(!r.ok)return;const j=await r.json();if(!j.local)return;LOCAL=j;
$('topo-local').innerHTML=`<span class="selo ac" title="servidor local em 127.0.0.1: os botões rodam os make nesta máquina">modo local · grupo ${esc(j.grupo_commit||'')}</span><span id=topo-novos></span>`;$('topo-local').style.display='';comandosLocal();checarNovidades();setInterval(checarNovidades,300000)}catch(e){}}
async function pingLocal(){try{const j=await (await fetch('/api/ping',{cache:'no-store'})).json();if(LOCAL&&j.grupo_commit!==LOCAL.grupo_commit){LOCAL=j;const s=document.querySelector('#topo-local .selo');if(s)s.textContent='modo local · grupo '+j.grupo_commit;checarNovidades()}}catch(e){}}
let NOV=null;
async function checarNovidades(){if(!LOCAL)return;try{const r=await fetch('/api/novidades',{cache:'no-store'});if(!r.ok)return;NOV=await r.json();const n=(NOV.grupo||0)+(NOV.bancada||0);
const t=$('topo-novos');if(t)t.innerHTML=n?` <button class="selo at" style="cursor:pointer;border:0" onclick="ir('comandos');rodar('atualizar')" title="o GitHub tem commits que o seu computador ainda não tem">${n} commit(s) novo(s) no GitHub · atualizar</button>`:'';
const b=$('novidades-txt');if(b)b.innerHTML=novTxt()}catch(e){}}
function novTxt(){if(!NOV)return 'conferindo o GitHub…';if(NOV.erro)return `não consegui falar com o GitHub (${esc(NOV.erro)}); o painel segue com o que está no seu computador.`;
const g=NOV.grupo||0,b=NOV.bancada||0;if(!g&&!b)return 'Seu computador está em dia com o GitHub (código do grupo e bancada).';
return `O GitHub tem <b>${g}</b> commit(s) novo(s) no código do grupo e <b>${b}</b> na bancada.`}
function comandosLocal(){const el=$('rodar');if(!el)return;
if(!LOCAL){el.innerHTML=`<div class=vazio-bloco><b>Para rodar os comandos por aqui, abra o painel no modo local.</b><br>Na pasta <code>pacote</code> do seu computador: <code>make qualidade-painel</code> (na raiz do repositório) e abra <code>http://127.0.0.1:8777</code>. O servidor só aceita a própria máquina. Uma cópia só leitura pode ser publicada por uma verificação automática a cada commit do grupo. Passo a passo, inclusive Windows sem make, em <code>rag/iris-rag/bancada/README.md</code>.</div>`;return}
el.innerHTML=`<div class="painel" style="margin-bottom:16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;border-color:var(--bd2)"><div style="flex:1;min-width:260px"><h3 style="margin:0 0 4px">Atualizar do GitHub</h3><p id=novidades-txt class=mut style="margin:0;font-size:13px">${novTxt()}</p><p class=mut3 style="margin:6px 0 0;font-size:12px">Traz o código novo do grupo e da bancada (só avança: se você tiver arquivo modificado ou commit seu não enviado, ele não mexe e explica) e roda de novo as verificações que leem o código. Leva alguns minutos.</p></div><button class="btn" onclick="rodar('atualizar')" ${JOB?'disabled':''}>atualizar do GitHub</button></div>
<div class=g12><div class="c5 painel plano"><div class=ph style="padding:14px 16px 0"><h3>Rodar nesta máquina</h3><p>Clone do grupo: <code>${esc(LOCAL.grupo)}</code> (<code>${esc(LOCAL.grupo_commit||'')}</code>) · Python ${esc(LOCAL.python||'')}. Um comando por vez; quando termina bem, o painel é gerado de novo.</p></div><table><tbody>`+
LOCAL.alvos.filter(a=>a.alvo!='atualizar').map(a=>`<tr><td style="padding-left:16px"><code>make ${esc(a.alvo)}</code>${a.pesado?' <span class="selo at" title="usa bastante CPU/memória">pesado</span>':''}<div class=mut3 style="font-size:12px">${esc(a.descricao)}</div></td><td style="text-align:right;padding-right:16px">${a.alvo=='rastro'?`<input id=rq value=Q07 size=4 style="background:var(--s2);border:1px solid var(--bd2);color:var(--tx);border-radius:6px;height:28px;padding:0 6px;font:12px 'IBM Plex Mono',monospace;margin-right:6px">`:''}<button class="btn sec mini" onclick="rodar('${esc(a.alvo)}')" ${JOB?'disabled':''}>rodar</button></td></tr>`).join('')+`</tbody></table></div>
<div class="c7 painel" style="position:sticky;top:76px"><div class=ph><h3 id=job-tit>Saída</h3><span id=job-st></span></div><pre id=job-out style="max-height:calc(100vh - 220px);min-height:320px">Escolha um comando à esquerda.</pre></div></div>`}
async function rodar(alvo){if(JOB)return;const corpo={alvo};if(alvo=='rastro'){const q=($('rq')||{}).value||'Q07';if(!/^Q\d{2}$/.test(q)){alert('pergunta no formato Q07');return}corpo.q=q}
const r=await fetch('/api/rodar',{method:'POST',headers:{'Content-Type':'application/json','X-Bancada':'1'},body:JSON.stringify(corpo)});
if(r.status==409){$('job-st').innerHTML='<span class="selo at">já tem um comando rodando</span>';return}if(!r.ok){$('job-st').innerHTML=`<span class="selo er">recusado (${r.status})</span>`;return}
const {id}=await r.json();JOB=id;comandosLocal();$('job-tit').textContent=alvo=='atualizar'?'atualizar do GitHub':'make '+alvo;$('job-st').innerHTML='<span class="selo ac">rodando…</span>';const out=$('job-out');out.textContent='';
const ev=new EventSource('/api/saida/'+id);ev.onmessage=m=>{let t=m.data;try{const j=JSON.parse(t);if(typeof j=='string')t=j}catch(e){}out.textContent+=t+'\n';out.scrollTop=out.scrollHeight};
ev.addEventListener('fim',m=>{const f=JSON.parse(m.data);if(alvo=='atualizar'){NOV=null;pingLocal();checarNovidades()}$('job-st').innerHTML=f.codigo==0?`<span class="selo ok">terminou bem · ${f.segundos} s</span>`:`<span class="selo er">falhou (código ${f.codigo}) · ${f.segundos} s</span>`;JOB=null;if(f.codigo!=0){ev.close();comandosLocal();$('job-out').textContent=out.textContent}});
ev.addEventListener('painel',()=>{ev.close();$('job-st').innerHTML+=' <button class="btn sec mini" onclick="location.reload()">painel atualizado: recarregar</button>'});
ev.onerror=()=>{ev.close();JOB=null}}

/* ---------- vigia ---------- */
async function vigiar(){try{const r=await fetch('status.json',{cache:'no-store'});if(!r.ok)return;const st=await r.json();topo(st);const rep=(st.portoes||[]).find(p=>p.ok===false);
$('reprovado').innerHTML=(st.aprovado===false&&rep)?`<div class="alerta er" role=alert><div class=n>!</div><h2>Último commit reprovado no portão “${esc(rep.portao)}”</h2><button class="btn claro" onclick="ir('commits')">ver portões</button><ul><li>commit do grupo <code>${esc(st.commit_grupo)}</code> ${esc((st.commit_grupo_titulo||'').slice(0,70))}</li><li>este painel continua mostrando a última versão aprovada (${esc(st.publicado&&st.publicado.grupo||'')}, ${esc(quando(st.publicado&&st.publicado.em))})</li><li class=mono style="font-size:12px">${esc((rep.detalhe||'').slice(0,220))}</li></ul></div>`:'';
if(D.status&&st.publicado&&D.status.publicado&&st.publicado.em&&st.publicado.em!==D.status.publicado.em){$('novo').style.display='inline-block'}}catch(e){}}

$('q').innerHTML=P.map(p=>`<option value=${p.id}>${p.id} · ${p.tipo} · ${esc(p.pergunta.slice(0,110))}</option>`).join('');
topo(D.status);alertas();visao();commitsSec();prsSec();achadosSec();rastro();qualidade();pipeline();confianca();revisao();seguranca();grafoSec();
const ini=(location.hash||'#visao').slice(1);ir(document.getElementById('sec-'+ini)?ini:'visao');vigiar();setInterval(vigiar,60000);detectarLocal();comandosLocal();
"""

SECOES = [("Estado", [("visao", "Visão geral", None), ("commits", "Commits e portões", "commits"), ("prs", "PRs e issues", "prs"),
                      ("achados", "Achados", "achados")]),
          ("Código", [("grafo", "Grafo do código", None), ("pipeline", "Pipeline inteiro", None),
                      ("arquitetura", "Arquitetura com LangGraph", None)]),
          ("RAG", [("rastro-sec", "Rastro do RAG", None), ("llmxrag", "LLM x RAG", None), ("qualidade", "Qualidade por versão", None),
                   ("confianca", "Reprodutibilidade e custo", None), ("revisao", "Revisão humana", "revisao")]),
          ("Qualidade", [("q-avaliacao", "Conjunto de avaliação", None), ("q-rag", "RAG: os quatro elos", None),
                         ("q-ataque", "Ataque em massa", "q-ataque"), ("q-juiz", "Juízes x pessoas", None),
                         ("q-orcamento", "Orçamento RNF-07", None), ("q-producao", "Produção", None)]),
          ("Testes", [("seguranca", "Segurança e ablação", "seguranca"), ("comandos", "Comandos", None)]),
          ("Guia", [("mapa-painel", "Mapa do painel", None), ("ferramentas", "Ferramentas", None)])]


def _fonte(arq: str, familia: str, peso: int) -> str:
    p = VENDOR / "fontes" / arq
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return (f"@font-face{{font-family:'{familia}';font-weight:{peso};font-style:normal;font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def _fonte_var(arq: str, familia: str) -> str:
    """Fonte variável (peso de 300 a 700 num arquivo só)."""
    p = VENDOR / "fontes" / arq
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return (f"@font-face{{font-family:'{familia}';font-weight:300 700;font-style:normal;font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def _qualidade_js() -> str:
    """Telas do grupo Qualidade (pacote/qualidade.js), separadas para o painel.py não crescer mais."""
    aqui = Path(__file__).resolve().parent
    return "\n".join((aqui / a).read_text(encoding="utf-8") for a in ("qualidade.js", "langgraph.js", "llmxrag.js", "glossario.js"))


def _vendor_js() -> str:
    partes = []
    for nome in ("d3-dispatch", "d3-timer", "d3-quadtree", "d3-force"):
        p = VENDOR / f"{nome}.min.js"
        if p.exists():
            partes.append(p.read_text(encoding="utf-8"))
    return "\n".join(partes)


def gerar(dados: dict, testes: list[tuple[str, str, str]]) -> str:
    dados["achados"] = achados(dados)
    A = dados["achados"]
    pii_g = sum(a["nivel"] == "grave" and a["tipo"] == "pii" for a in A)
    err_g = sum(a["nivel"] == "grave" and a["tipo"] == "erro" for a in A)
    rodadas = (dados.get("commits") or {}).get("rodadas") or []
    reprov = sum(1 for r in rodadas if r.get("aprovado") is False)
    pii_casos = [c for c in dados.get("adversarial_casos") or [] if c.get("categoria") == "pii"]

    def contador(sid: str) -> str:
        if sid == "achados" and A:
            s = ""
            if pii_g:
                s += f"<span class='cont pii' title='dados pessoais que vazaram'>{pii_g}</span>"
            if err_g:
                s += f"<span class='cont er' title='erros graves'>{err_g}</span>"
            return s or f"<span class=cont>{len(A)}</span>"
        if sid == "commits" and rodadas:
            return f"<span class='cont er'>{reprov}</span>" if reprov else f"<span class=cont>{len(rodadas)}</span>"
        if sid == "prs" and (dados.get("github") or {}).get("prs"):
            return f"<span class=cont>{len(dados['github']['prs'])}</span>"
        if sid == "revisao" and (dados.get("divergencias") or {}).get("n"):
            return f"<span class=cont>{dados['divergencias']['n']}</span>"
        if sid == "seguranca" and pii_g:
            return f"<span class='cont pii'>{sum(1 for c in pii_casos if not c.get('aprovado'))}</span>"
        if sid == "q-ataque" and (dados.get("q_ataque") or {}).get("padroes"):
            return f"<span class='cont pii'>{len(dados['q_ataque']['padroes'])}</span>"
        return ""

    nav = []
    for grupo, itens in SECOES:
        nav.append(f"<div class=grupo-nav>{grupo.upper()}</div>")
        for sid, rot, _ in itens:
            nav.append(f"<button data-s={sid} onclick=\"ir('{sid}')\"><span class=r>{rot}</span>{contador(sid)}</button>")
    linhas = "".join(
        f"<tr><td><code>{html.escape(c)}</code></td><td>{html.escape(o)}</td>"
        f"<td><span class='selo {'ok' if s.startswith('existe') else 'at' if s.startswith('proposta') else 'ac'}'>{html.escape(s)}</span></td></tr>"
        for c, o, s in testes)
    comandos = ("<div class=cab><div><h1>Comandos</h1><p class=sub>O que já existe no repositório do grupo (incluindo os comandos do Ian), "
                "o que é deste protótipo e o que é proposta. Rode na pasta <code>pacote</code>; <code>make tudo</code> faz tudo sem modelo.</p></div></div>"
                f"<div class='painel plano'><div class=rolar><table><thead><tr><th style='padding-left:18px'>comando</th><th>o que faz</th><th>situação</th></tr></thead>"
                f"<tbody>{linhas}</tbody></table></div></div><div id=rodar style='margin-top:16px'></div>")

    def conteudo(sid: str) -> str:
        if sid == "rastro-sec":
            return ("<div class=cab><div><h1>Rastro do RAG</h1><p class=sub>Uma pergunta do gabarito do começo ao fim: o que cada "
                    "busca trouxe, as respostas de cada versão do prompt e o veredito de cada juiz, frase a frase.</p></div></div>"
                    "<div style='margin-bottom:16px'><select id=q class=q onchange=rastro() aria-label='pergunta'></select></div><div id=rastro></div>")
        if sid == "comandos":
            return comandos
        if sid == "arquitetura":
            return "<div id=lg-arq></div>"
        if sid == "mapa-painel":
            return guia.mapa_html()
        if sid == "ferramentas":
            return guia.ferramentas_html()
        return f"<div id={sid}></div>"

    corpo = "".join(f"<section class=sec id=sec-{sid}>{conteudo(sid)}</section>" for _, itens in SECOES for sid, _, _ in itens)
    fontes = "".join(_fonte(a, f, p) for a, f, p in (
        ("ibm-plex-sans-latin-400-normal.woff2", "IBM Plex Sans", 400), ("ibm-plex-sans-latin-500-normal.woff2", "IBM Plex Sans", 500),
        ("ibm-plex-sans-latin-600-normal.woff2", "IBM Plex Sans", 600), ("ibm-plex-mono-latin-400-normal.woff2", "IBM Plex Mono", 400),
        ("ibm-plex-mono-latin-600-normal.woff2", "IBM Plex Mono", 600)))
    fontes += "".join(_fonte_var(a, "Space Grotesk") for a in ("space-grotesk-latin-wght-normal.woff2",
                                                              "space-grotesk-latin-ext-wght-normal.woff2"))
    legenda = ("<div class=legenda><b>CORES</b><span><i class='sw er'></i>erro, portão reprovado, regressão</span>"
               "<span><i class='sw pii'></i>dados pessoais (LGPD)</span><span><i class='sw at'></i>atenção, parcial, sem teste</span>"
               "<span><i class='sw ok'></i>passou</span><span><i class='sw ac'></i>seleção</span>"
               "<p>Abrir não roda nada: o painel só lê o que as verificações gravaram. Contém texto de documentos sem licença aberta: não publicar.</p></div>")
    dados_json = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html><html lang=pt-BR><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta name=color-scheme content=dark><meta name=referrer content=no-referrer><title>Bancada do Íris</title>
<style>{fontes}{CSS}{guia.CSS}</style></head><body><div class=app>
<aside class=lado><div class=marca><i></i><div><b>Íris</b><small>bancada de acompanhamento</small></div></div><nav aria-label=seções>{''.join(nav)}</nav>{legenda}</aside>
<main><div class=topo><span id=topo-estado></span><span id=topo-grupo></span><span id=topo-priv></span><span id=topo-quando></span><span id=topo-local style="display:none"></span>
<button id=novo class=novo onclick="location.reload()">nova versão publicada: recarregar</button></div><div id=reprovado></div><div id=alerta></div>{corpo}</main></div>
<script>{_vendor_js()}</script><script>const DADOS={dados_json};</script><script>{JS}\n{_qualidade_js()}\nqualidadeTudo();langgraphSec();llmxragSec();glAplicar();</script></body></html>"""
