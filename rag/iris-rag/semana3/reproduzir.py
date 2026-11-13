"""reproduzir.py: refaz a análise do relatório e confere se os números saem iguais aos que estão versionados.

Uso (nesta pasta):
    python reproduzir.py          refaz, a partir dos vereditos do juiz, as métricas, as diferenças pareadas, a regra
                                  de decisão, as hipóteses, a concordância do juiz e a rodada de 50 candidatos.
                                  Só biblioteca padrão do Python (3.10 ou mais novo); menos de 1 minuto.
    python reproduzir.py --tudo   refaz também o que depende das respostas geradas e dos trechos da busca
                                  (métricas por código, perguntas sem resposta, limiar de escore, busca certa x
                                  errada). Precisa dos arquivos não distribuídos (ver README.md) e do scipy.

O script roda cada análise, compara a saída nova com a versionada (ignorando a linha de data) e devolve os
arquivos ao estado em que estavam. Termina com erro se algum número mudar.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PASTAS = ("saidas", "saidas_r50", "saidas_fora")

# (comando, saídas de texto que ele grava e que entram no relatório)
BASE = [(["analise_juiz.py"], ["saidas/juiz_metricas.txt"]),
        (["concordancia_rejulgamento.py"], ["saidas/juiz_concordancia.txt"]),
        (["rodada_r50.py", "analise"], ["saidas_r50/juiz_r50.txt"])]
TUDO = [(["metricas.py"], ["saidas/metricas.txt"]),
        (["analise_complementar.py"], ["saidas/analise_complementar.txt"]),
        (["rodada_fora.py", "abstencao"], ["saidas_fora/abstencao.txt"]),
        (["rodada_fora.py", "limiar"], ["saidas_fora/limiar.txt"]),
        (["rodada_fora.py", "analise"], ["saidas_fora/juiz_fora.txt"])]


def sem_data(texto: str) -> list[str]:
    """As linhas do arquivo sem a de data e commit, que muda a cada execução."""
    return [l.rstrip() for l in texto.splitlines() if not l.startswith("gerado em")]


def main() -> None:
    passos = BASE + (TUDO if "--tudo" in sys.argv else [])
    # guarda o estado atual das pastas de saída, para devolver no fim (a conferência não deve sujar o git)
    antes = {p: p.read_bytes() for pasta in PASTAS for p in (AQUI / pasta).rglob("*") if p.is_file()}
    falhas = 0
    try:
        for comando, saidas in passos:
            r = subprocess.run([sys.executable, *comando], cwd=AQUI, capture_output=True, text=True, encoding="utf-8")
            nome = " ".join(comando)
            if r.returncode != 0:
                falhas += 1
                print(f"FALHOU  {nome}\n        {(r.stderr or r.stdout).strip().splitlines()[-1]}")
                continue
            for s in saidas:
                velho = sem_data(antes[AQUI / s].decode("utf-8")) if AQUI / s in antes else None
                novo = sem_data((AQUI / s).read_text(encoding="utf-8"))
                if velho == novo:
                    print(f"igual   {s}  ({len(novo)} linhas)")
                else:
                    falhas += 1
                    dif = [(a, b) for a, b in zip(velho or [], novo) if a != b][:3]
                    print(f"MUDOU   {s}  ({len(velho or [])} -> {len(novo)} linhas)")
                    for a, b in dif:
                        print(f"        versionado: {a[:110]}\n        refeito:    {b[:110]}")
    finally:
        for p, conteudo in antes.items():
            p.write_bytes(conteudo)
        for pasta in PASTAS:                       # apaga o que a conferência criou e não existia
            for p in (AQUI / pasta).rglob("*"):
                if p.is_file() and p not in antes:
                    p.unlink()
    print("\n" + ("Tudo igual: a análise refeita reproduz os números versionados." if not falhas
                  else f"{falhas} problema(s): ver as linhas FALHOU e MUDOU acima."))
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
