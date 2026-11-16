"""exportar.py: grava em bancada/referencia/ um retrato dos resultados com modelo, para o painel mostrar as abas cheias
em qualquer máquina. Cada arquivo leva a data e o commit em que foi medido (MANIFESTO.json); o painel avisa quando um
número vem do retrato e não do commit que está rodando.

Só copia saídas que NÃO têm texto de documento sem licença aberta: compara cada arquivo com os textos listados em
rag/iris-rag/textos_nao_distribuidos.txt (janelas de 15 palavras) e recusa o que tiver trecho deles. Por isso precisa
rodar numa máquina que tenha esses textos (TEXTOS=pasta).

Uso:  python exportar.py --origem PASTA/pacote/outputs --textos PASTA/texto --destino bancada/referencia
      [--status status.json] [--historico historico.jsonl] [--commit-privado SHA]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LISTA = AQUI.parents[1] / "textos_nao_distribuidos.txt"
# saídas que o painel lê; as de texto integral (respostas com os 5 trechos) ficam de fora de propósito
NUNCA = re.compile(r"^17-respostas|^40-llm-x-rag-textos|^03-demonstracao|^01-chunking")
JANELA = 15


def palavras(t: str) -> list[str]:
    return re.findall(r"\w+", t.lower())


def janelas_restritas(pasta: Path) -> set[str]:
    nomes = [l.strip().replace("texto/", "") for l in LISTA.read_text(encoding="utf-8").splitlines() if l.startswith("texto/")]
    faltam = [n for n in nomes if not (pasta / n).exists()]
    if faltam:
        raise SystemExit(f"faltam textos restritos em {pasta} (sem eles não dá para conferir): {faltam}")
    js: set[str] = set()
    for n in nomes:
        p = palavras((pasta / n).read_text(encoding="utf-8", errors="ignore"))
        js.update(" ".join(p[i:i + JANELA]) for i in range(len(p) - JANELA))
    return js


def tem_restrito(texto: str, js: set[str]) -> int:
    p = palavras(texto)
    return sum(1 for i in range(len(p) - JANELA) if " ".join(p[i:i + JANELA]) in js)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", type=Path, required=True)
    ap.add_argument("--textos", type=Path, required=True)
    ap.add_argument("--destino", type=Path, default=AQUI)
    ap.add_argument("--status", type=Path)
    ap.add_argument("--historico", type=Path)
    ap.add_argument("--commit-privado", default="")
    a = ap.parse_args()
    js = janelas_restritas(a.textos)
    saida = a.destino / "outputs"
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    manifesto = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "commit_bancada": a.commit_privado,
                 "aviso": "retrato de resultados medidos antes, com modelo; não é deste commit", "arquivos": {}, "recusados": {}}
    for p in sorted(a.origem.iterdir()):
        if not p.is_file() or p.suffix not in (".json", ".jsonl", ".txt") or NUNCA.search(p.name):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        n = tem_restrito(t, js)
        if n:
            manifesto["recusados"][p.name] = f"{n} trechos de documento sem licença aberta"
            continue
        if "/home/" in t:
            t = re.sub(r"/home/[^\s\"']*?/(challenges|pacote|bancada|iris-rag)/", r"\1/", t)
        (saida / p.name).write_text(t, encoding="utf-8")
        manifesto["arquivos"][p.name] = {"sha256": hashlib.sha256(t.encode()).hexdigest()[:16],
                                         "modificado_em": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).date().isoformat()}
    for nome, arq in (("status.json", a.status), ("historico.jsonl", a.historico)):
        if arq and arq.exists():
            t = arq.read_text(encoding="utf-8")
            if tem_restrito(t, js):
                manifesto["recusados"][nome] = "trecho de documento sem licença aberta"
                continue
            (a.destino / nome).write_text(t, encoding="utf-8")
            manifesto["arquivos"][nome] = {"sha256": hashlib.sha256(t.encode()).hexdigest()[:16]}
    if a.status and a.status.exists():
        st = json.loads(a.status.read_text(encoding="utf-8"))
        manifesto["commit_grupo"] = st.get("commit_grupo")
        manifesto["rodada_em"] = st.get("rodada_em")
    (a.destino / "MANIFESTO.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(manifesto['arquivos'])} arquivos no retrato; recusados: {manifesto['recusados'] or 'nenhum'}")


if __name__ == "__main__":
    main()
