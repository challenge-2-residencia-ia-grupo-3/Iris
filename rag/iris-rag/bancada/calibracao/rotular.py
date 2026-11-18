"""Ficha para PESSOAS rotularem frases + importador dos rótulos.

Analogia: é a "prova de conferência" do corretor automático. A professora lê a pergunta,
a frase da resposta e os trechos que a frase cita, e diz se a frase está sustentada.

Dois comandos:

  1) gerar a ficha (HTML estático, abre direto no navegador, sem internet e sem servidor):
       PYTHONDONTWRITEBYTECODE=1 nice -n 19 python3 bancada/calibracao/rotular.py ficha
     -> pacote/reports/calibracao-juiz-ficha.html   (pasta ignorada pelo git: a ficha leva o
        texto dos trechos, que tem licença restrita e não pode ir para o repositório)
     -> bancada/calibracao/amostra.json            (só ids, estrato e peso; sem texto)
     Opções: --sim N (quantas frases unânimes "sim" sortear; padrão 40), --tudo (todas as frases).

  2) importar o JSON que o navegador baixou:
       python3 bancada/calibracao/rotular.py importar ~/Downloads/rotulos-juiz-XXXX.json
     -> acrescenta em bancada/calibracao/rotulos-humanos.jsonl (uid, rotulo, motivo, avaliador, data)
     Depois rode calibrar.py de novo.

A amostra é ESTRATIFICADA e FIXA (semente): entra toda frase em que os 3 juízes principais
discordam (é onde a pessoa mais informa), toda frase que os 3 deram "parcial"/"nao", e um sorteio
fixo das frases em que os 3 deram "sim" (para medir o erro caro: aprovar o que a pessoa reprova).
Cada estrato leva um peso (total do estrato / sorteados), para o calibrar.py poder corrigir o
exagero de frases difíceis na amostra. A ordem na ficha é embaralhada e os votos dos juízes NÃO
aparecem, para não puxar a resposta da pessoa.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (rel, AQUI, CLASSES, OUT, PRINCIPAIS, RAIZ, REPORTS, ROTULOS, SEMENTE,  # noqa: E402
                   carregar_votos, jl, voto)

AMOSTRA = AQUI / "amostra.json"
FICHA = REPORTS / "calibracao-juiz-ficha.html"
FUSO = timezone(timedelta(hours=-3))


def estrato(votos: dict, u: str) -> str:
    vs = {votos[j][u] for j in PRINCIPAIS if u in votos[j]}
    if len(vs) > 1:
        return "desacordo"
    if vs == {"sim"}:
        return "unanime_sim"
    if vs:
        return "unanime_parcial_ou_nao"
    return "fora"   # frase que só a rodada 2 julgou


def montar_amostra(n_sim: int, tudo: bool) -> tuple[dict, dict]:
    votos, info = carregar_votos()
    grupos: dict[str, list[str]] = defaultdict(list)
    for u in sorted(info):
        e = estrato(votos, u)
        if e != "fora":
            grupos[e].append(u)
    rng = random.Random(SEMENTE)
    escolhidos: dict[str, list[str]] = {}
    for e, us in sorted(grupos.items()):
        if e == "unanime_sim" and not tudo:
            # sorteio espalhado por pergunta: primeiro uma frase de cada pergunta, depois o resto
            por_q: dict[str, list[str]] = defaultdict(list)
            for u in us:
                por_q[u.split("-")[0]].append(u)
            ordem = []
            for q in sorted(por_q):
                rng.shuffle(por_q[q])
            while any(por_q.values()):
                qs = [q for q in sorted(por_q) if por_q[q]]
                rng.shuffle(qs)
                ordem += [por_q[q].pop() for q in qs]
            escolhidos[e] = sorted(ordem[:n_sim])
        else:
            escolhidos[e] = list(us)
    itens = []
    for e, us in escolhidos.items():
        peso = round(len(grupos[e]) / len(us), 4) if us else 0
        itens += [{"uid": u, "id": info[u]["id"], "estrato": e, "peso": peso} for u in us]
    rng.shuffle(itens)   # ordem de apresentação fixa e misturada
    assinatura = hashlib.sha1(json.dumps([i["uid"] for i in itens]).encode()).hexdigest()[:12]
    return {
        "versao": assinatura, "semente": SEMENTE, "n": len(itens),
        "estratos": {e: {"total": len(grupos[e]), "na_amostra": len(escolhidos[e])} for e in sorted(grupos)},
        "regra": "desacordo e unanime_parcial_ou_nao: todas; unanime_sim: sorteio fixo espalhado por pergunta",
        "itens": itens,
    }, info


def trechos_por_pergunta() -> dict[str, dict[str, dict]]:
    """Texto dos trechos [T1..T5] de cada resposta. SÓ vai para a ficha HTML em pacote/reports/."""
    out = {}
    for r in jl(OUT / "17-respostas.jsonl"):
        out[r["id"]] = {"pergunta": r["pergunta"],
                        "trechos": {t["ref"]: {"doc": t.get("doc", ""), "chunk_id": t.get("chunk_id", ""),
                                               "texto": t.get("texto", "")} for t in (r.get("trechos") or [])}}
    return out


PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Íris - conferência do juiz (ficha {versao})</title>
<style>
 body{{background:#14161a;color:#e6e6e6;font:16px/1.5 system-ui,sans-serif;margin:0;padding:0 1rem 6rem}}
 header{{position:sticky;top:0;background:#14161a;border-bottom:1px solid #333;padding:.6rem 0;z-index:2}}
 h1{{font-size:1.15rem;margin:.3rem 0}} .ajuda{{color:#aab;font-size:.92rem;max-width:60rem}}
 .item{{border:1px solid #333;border-radius:8px;margin:1rem 0;padding:.8rem 1rem;max-width:60rem;background:#1b1e24}}
 .item.feito{{border-color:#3d6b4a}} .q{{color:#9ab;font-size:.9rem}}
 .frase{{font-size:1.08rem;margin:.5rem 0;padding:.5rem .7rem;background:#232733;border-left:4px solid #6b8cff}}
 details{{margin:.4rem 0}} summary{{cursor:pointer;color:#9bd}}
 .trecho{{white-space:pre-wrap;font-size:.9rem;color:#ccd;background:#101215;padding:.5rem;border-radius:4px;max-height:20rem;overflow:auto}}
 button{{font:inherit;padding:.4rem .9rem;margin:.2rem .3rem .2rem 0;border-radius:6px;border:1px solid #555;background:#2a2e38;color:#eee;cursor:pointer}}
 button.on[data-v=sim]{{background:#1f5a34;border-color:#4c9}} button.on[data-v=parcial]{{background:#6a5a12;border-color:#dc4}}
 button.on[data-v=nao]{{background:#6a1f1f;border-color:#e66}}
 textarea,input{{font:inherit;width:100%;box-sizing:border-box;background:#101215;color:#eee;border:1px solid #444;border-radius:6px;padding:.4rem}}
 #barra{{position:fixed;bottom:0;left:0;right:0;background:#0f1114;border-top:1px solid #333;padding:.6rem 1rem}}
 #baixar{{background:#2d4f8f;border-color:#6b8cff}}
</style></head><body>
<header><h1>Conferência do juiz automático — {n} frases</h1>
<div class="ajuda">Para cada frase: leia a pergunta, a frase e os trechos que ela cita (clique para abrir).
Escolha <b>sustentada</b> (tudo o que a frase afirma está nos trechos citados), <b>parcial</b> (parte está,
parte não, ou ela exagera) ou <b>não sustentada</b>. O motivo é opcional, mas ajuda muito quando a resposta
for parcial ou não. Seu progresso fica guardado neste navegador. No fim, clique em <b>Baixar rótulos</b> e
mande o arquivo .json para o time. Nada é enviado pela internet.</div>
<p><label>Seu código de avaliador (ex.: prof-A; evite nome completo):
<input id="avaliador" maxlength="40" placeholder="prof-A"></label></p></header>
<main id="lista"></main>
<div id="barra"><span id="prog"></span> <button id="baixar">Baixar rótulos (.json)</button></div>
<script id="dados" type="application/json">{dados}</script>
<script>
const D = JSON.parse(document.getElementById('dados').textContent);
const CHAVE = 'iris-calib-' + D.versao;
const est = JSON.parse(localStorage.getItem(CHAVE) || '{{"avaliador":"","r":{{}}}}');
const salvar = () => {{ localStorage.setItem(CHAVE, JSON.stringify(est)); progresso(); }};
const nomes = {{sim:'Sustentada', parcial:'Parcial', nao:'Não sustentada'}};
function el(tag, attrs, txt) {{ const e = document.createElement(tag); Object.assign(e, attrs||{{}}); if (txt!=null) e.textContent = txt; return e; }}
function progresso() {{
  const feitos = D.itens.filter(i => est.r[i.uid] && est.r[i.uid].rotulo).length;
  document.getElementById('prog').textContent = feitos + ' de ' + D.itens.length + ' rotuladas';
}}
const av = document.getElementById('avaliador'); av.value = est.avaliador || '';
av.oninput = () => {{ est.avaliador = av.value.trim(); salvar(); }};
const lista = document.getElementById('lista');
D.itens.forEach((it, k) => {{
  const box = el('section', {{className:'item', id:'i'+k}});
  box.append(el('div', {{className:'q'}}, '#' + (k+1) + ' · ' + it.id + ' · ' + it.pergunta));
  box.append(el('div', {{className:'frase'}}, it.frase));
  if (!it.trechos.length) box.append(el('div', {{className:'q'}}, 'Esta frase não cita trecho nenhum.'));
  it.trechos.forEach(t => {{
    const d = el('details'); d.append(el('summary', {{}}, t.ref + ' — ' + t.doc));
    d.append(el('div', {{className:'trecho'}}, t.texto || '(texto indisponível)')); box.append(d);
  }});
  const r = est.r[it.uid] || (est.r[it.uid] = {{rotulo:'', motivo:''}});
  const bts = el('div');
  ['sim','parcial','nao'].forEach(v => {{
    const b = el('button', {{type:'button'}}, nomes[v]); b.dataset.v = v;
    if (r.rotulo === v) b.classList.add('on');
    b.onclick = () => {{ r.rotulo = v; bts.querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.v===v));
                        box.classList.add('feito'); salvar(); }};
    bts.append(b);
  }});
  box.append(bts);
  const m = el('textarea', {{rows:2, placeholder:'Motivo (opcional): o que falta ou sobra nos trechos?'}}); m.value = r.motivo || '';
  m.oninput = () => {{ r.motivo = m.value; salvar(); }};
  box.append(m);
  if (r.rotulo) box.classList.add('feito');
  lista.append(box);
}});
progresso();
document.getElementById('baixar').onclick = () => {{
  const rot = D.itens.filter(i => est.r[i.uid] && est.r[i.uid].rotulo)
    .map(i => ({{uid:i.uid, id:i.id, rotulo:est.r[i.uid].rotulo, motivo:(est.r[i.uid].motivo||'').trim()}}));
  if (!est.avaliador && !confirm('Sem código de avaliador. Baixar assim mesmo?')) return;
  const saida = {{formato:'iris-calibracao-juiz/1', versao_amostra:D.versao, avaliador:est.avaliador||'anonimo',
                 data:new Date().toISOString(), n:rot.length, rotulos:rot}};
  const a = el('a', {{href:URL.createObjectURL(new Blob([JSON.stringify(saida, null, 1)], {{type:'application/json'}})),
                     download:'rotulos-juiz-' + D.versao + '-' + (est.avaliador||'anonimo') + '.json'}});
  document.body.append(a); a.click(); a.remove();
}};
</script></body></html>
"""


def ficha(n_sim: int, tudo: bool) -> int:
    amostra, info = montar_amostra(n_sim, tudo)
    tr = trechos_por_pergunta()
    itens = []
    for i in amostra["itens"]:
        q = tr.get(i["id"], {"pergunta": "", "trechos": {}})
        refs = info[i["uid"]]["refs"]
        itens.append({"uid": i["uid"], "id": i["id"], "pergunta": q["pergunta"], "frase": info[i["uid"]]["frase"],
                      "trechos": [{"ref": r, **q["trechos"][r]} for r in refs if r in q["trechos"]]})
    dados = json.dumps({"versao": amostra["versao"], "itens": itens}, ensure_ascii=False).replace("</", "<\\/")
    REPORTS.mkdir(parents=True, exist_ok=True)
    FICHA.write_text(PAGINA.format(versao=html.escape(amostra["versao"]), n=len(itens), dados=dados), encoding="utf-8")
    AMOSTRA.write_text(json.dumps(amostra, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sem_ref = sum(1 for i in itens if not i["trechos"])
    print(f"ficha: {rel(FICHA)} ({len(itens)} frases, versao {amostra['versao']}; {sem_ref} sem trecho citado)")
    print(f"amostra (so ids): {rel(AMOSTRA)}  estratos: {amostra['estratos']}")
    return 0


def importar(arquivo: Path, avaliador: str | None) -> int:
    d = json.loads(arquivo.read_text(encoding="utf-8"))
    if d.get("formato") != "iris-calibracao-juiz/1":
        sys.exit(f"formato desconhecido: {d.get('formato')!r} (esperado iris-calibracao-juiz/1)")
    amostra = json.loads(AMOSTRA.read_text(encoding="utf-8")) if AMOSTRA.exists() else None
    if amostra and d.get("versao_amostra") != amostra["versao"]:
        print(f"aviso: ficha de outra versao ({d.get('versao_amostra')} != {amostra['versao']}); importo os uids que existirem")
    _, info = carregar_votos()
    quem = (avaliador or d.get("avaliador") or "anonimo").strip()[:40]
    agora = datetime.now(FUSO).isoformat(timespec="seconds")
    novos, ignorados = [], 0
    for r in d.get("rotulos", []):
        c = voto(r.get("rotulo"))
        if not c or r.get("uid") not in info:
            ignorados += 1
            continue
        novos.append({"uid": r["uid"], "id": info[r["uid"]]["id"], "rotulo": c,
                      "motivo": str(r.get("motivo", ""))[:1000], "avaliador": quem,
                      "versao_amostra": d.get("versao_amostra"), "data_rotulo": d.get("data"), "importado_em": agora})
    with ROTULOS.open("a", encoding="utf-8") as f:
        for n in novos:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"importados {len(novos)} rotulos de '{quem}' -> {rel(ROTULOS)} (ignorados {ignorados}); "
          f"classes: { {c: sum(n['rotulo'] == c for n in novos) for c in CLASSES} }")
    print("agora rode: python3 bancada/calibracao/calibrar.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("ficha")
    f.add_argument("--sim", type=int, default=40, help="frases unanimes 'sim' sorteadas (padrao 40)")
    f.add_argument("--tudo", action="store_true", help="todas as frases julgadas")
    i = sub.add_parser("importar")
    i.add_argument("arquivo", type=Path)
    i.add_argument("--avaliador", help="sobrescreve o codigo de avaliador do arquivo")
    a = ap.parse_args()
    return ficha(a.sim, a.tudo) if a.cmd == "ficha" else importar(a.arquivo, a.avaliador)


if __name__ == "__main__":
    sys.exit(main())
