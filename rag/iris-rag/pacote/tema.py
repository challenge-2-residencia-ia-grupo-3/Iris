"""tema.py: tema claro para o painel da bancada, sem reescrever as cores uma a uma.

Como funciona (usado por painel.py ao gerar a página):
1. Toda cor fixa do CSS e do JavaScript da página (``#A68BFF``, ``rgba(0,0,0,.45)``) vira uma variável
   (``var(--c-A68BFF)``). O tema escuro, o original, define cada variável com a própria cor; nada muda nele.
2. O tema claro redefine as mesmas variáveis em ``html.tema-claro``:
   - as cores de base (fundo, superfícies, texto, bordas, os pares de erro, atenção, passou e seleção) seguem a
     paleta do playground do backend, para o painel parecer um só;
   - as demais invertem a luminosidade e mantêm o matiz e a saturação: o que era claro sobre escuro fica escuro
     sobre claro, e vermelho continua vermelho (o significado das cores não muda).
3. O canvas do grafo do código não entende ``var()``; a página resolve a variável na hora de pintar.

Alternativa descartada: inverter a tela inteira com ``filter: invert()``. É rápida, mas distorce as cores com
significado e os desenhos, e não passa numa conferência de contraste.
"""
from __future__ import annotations

import colorsys
import re

RE_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RE_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)")

# Cores de base: escuro (original) -> claro (paleta do playground: papel, superfície, tinta, linhas)
BASE_CLARA = {
    "18181C": "EEF3F3", "1F1F25": "FFFFFF", "26262E": "F4F7F7", "2F2F39": "E4ECEC", "2F2F38": "D1DDDD",
    "3E3E4A": "B6C7C7", "EDEDF2": "132325", "B4B4C2": "2A3E40", "8A8A9A": "4B6163",
    "A68BFF": "5A3FC0", "723BFA": "5A2EE0", "251B40": "ECE7FB",
    "34D399": "0F5C3F", "0F2A20": "E8F5F0", "1F6B4A": "9FD2BD",
    "E5B443": "9E5B08", "2E260F": "FEF5E7", "5C4A17": "E6C58D",
    "FF6B6B": "B83523", "35171B": "FBEAE7", "6B2A33": "EAB1A7", "8A3340": "E2A399",
    # faixa de alerta (erro e dado pessoal): fundo claro rosado, para o texto vermelho ler bem
    "4A1F26": "FBE3DF", "2A1518": "FDF1EF",
}


# Ajustes do tema escuro (o original), decididos pelo Matheus em 16/11/2026: só o que fica abaixo do contraste mínimo de
# leitura (4,5 para 1, WCAG). O cinza do texto secundário dava 4,42 sobre os fundos de cartão; #9696A6 é o menor tom do
# mesmo cinza que passa em todos os fundos onde ele aparece (o pior caso, #2F2F39, dá 4,54).
ESCURO_AJUSTADO = {"8A8A9A": "9696A6"}


def _hex6(h: str) -> str:
    h = h.upper()
    return "".join(c * 2 for c in h) if len(h) == 3 else h


def _inverte(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Inverte a luminosidade (HLS), mantém matiz e saturação."""
    hh, ll, ss = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    ll = 1 - ll
    # o que vira texto (era claro) fica escuro o bastante para ler sobre fundo claro
    if ll < 0.5:
        ll = min(ll, 0.36)
    rr, gg, bb = colorsys.hls_to_rgb(hh, ll, ss)
    return round(rr * 255), round(gg * 255), round(bb * 255)


def claro_hex(h6: str) -> str:
    if h6 in BASE_CLARA:
        return BASE_CLARA[h6]
    r, g, b = (int(h6[i:i + 2], 16) for i in (0, 2, 4))
    rr, gg, bb = _inverte(r, g, b)
    return f"{rr:02X}{gg:02X}{bb:02X}"


def _nome_rgba(r: int, g: int, b: int, a: str | None) -> str:
    return f"--c-rgba-{r}-{g}-{b}-" + (a or "1").replace(".", "p")


def claro_rgba(r: int, g: int, b: int, a: str | None) -> str:
    alfa = float(a) if a is not None else 1.0
    if (r, g, b) == (0, 0, 0):  # sombra: mais leve e puxada para o tom do playground
        return f"rgba(16,40,42,{round(alfa * 0.35, 3)})"
    if (r, g, b) == (255, 255, 255):  # brilho interno de borda: some no claro
        return f"rgba(255,255,255,{alfa})"
    if f"{r:02X}{g:02X}{b:02X}" in BASE_CLARA:
        h = BASE_CLARA[f"{r:02X}{g:02X}{b:02X}"]
        rr, gg, bb = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    else:
        rr, gg, bb = _inverte(r, g, b)
    return f"rgba({rr},{gg},{bb},{alfa})"


def tematizar(textos: list[str]) -> tuple[list[str], str]:
    """Troca as cores fixas por variáveis nos textos (CSS e JS) e devolve o bloco CSS dos dois temas."""
    hexes: set[str] = set()
    rgbas: dict[str, tuple[int, int, int, str | None]] = {}

    def troca_hex(m: re.Match) -> str:
        h = _hex6(m.group(1))
        hexes.add(h)
        return f"var(--c-{h})"

    def troca_rgba(m: re.Match) -> str:
        r, g, b, a = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        nome = _nome_rgba(r, g, b, a)
        rgbas[nome] = (r, g, b, a)
        return f"var({nome})"

    saida = [RE_RGBA.sub(troca_rgba, RE_HEX.sub(troca_hex, t)) for t in textos]
    escuro = [f"--c-{h}:#{ESCURO_AJUSTADO.get(h, h)}" for h in sorted(hexes)]
    escuro += [f"{n}:rgba({r},{g},{b},{a if a is not None else 1})" for n, (r, g, b, a) in sorted(rgbas.items())]
    claro = [f"--c-{h}:#{claro_hex(h)}" for h in sorted(hexes)]
    claro += [f"{n}:{claro_rgba(r, g, b, a)}" for n, (r, g, b, a) in sorted(rgbas.items())]
    bloco = (":root{" + ";".join(escuro) + "}\n"
             "html.tema-claro{color-scheme:light;" + ";".join(claro) + "}\n"
             "html.tema-claro body{background:var(--bg)}\n")
    return saida, bloco


# Escolha do tema na página: ?tema=claro|escuro, ou a escolha guardada pelo playground (mesma origem);
# sem nada guardado, embutido abre claro (como o playground) e solto abre escuro (o original).
JS_TEMA = r"""
(function(){const q=new URLSearchParams(location.search);let t=q.get('tema');
if(!t){try{t=localStorage.getItem('iris-tema')}catch(e){}}
if(!t)t=q.has('embutido')?'claro':'escuro';
document.documentElement.classList.toggle('tema-claro',t==='claro')})();
/* o canvas não entende var(): resolve a variável na hora de pintar */
(function(){const P=CanvasRenderingContext2D.prototype,cache={};
function res(v){if(typeof v!=='string'||v.indexOf('var(')<0)return v;const k=(document.documentElement.classList.contains('tema-claro')?'c':'e')+v;
if(cache[k])return cache[k];const st=getComputedStyle(document.documentElement);
const r=v.replace(/var\((--[\w-]+)\)/g,(m,n)=>st.getPropertyValue(n).trim()||m);cache[k]=r;return r}
['fillStyle','strokeStyle'].forEach(p=>{const d=Object.getOwnPropertyDescriptor(P,p);
Object.defineProperty(P,p,{configurable:true,get(){return d.get.call(this)},set(v){d.set.call(this,res(v))}})})})();
function aplicarTema(t){document.documentElement.classList.toggle('tema-claro',t==='claro');
if(typeof GX!=='undefined'&&GX.on&&typeof gxDesenha==='function')gxDesenha()}
addEventListener('storage',e=>{if(e.key==='iris-tema'&&e.newValue)aplicarTema(e.newValue)});
addEventListener('message',e=>{if(e.origin===location.origin&&e.data&&e.data.bancadaTema)aplicarTema(e.data.bancadaTema)});
"""
