"""Calibra o juiz por modelo contra rótulos de pessoas -> pacote/outputs/33-juiz-calibracao.json

Analogia: o juiz por modelo é um corretor automático de prova. Antes de usar a nota dele,
uma professora corrige as mesmas frases e a gente mede quantas vezes os dois batem.

O que este script faz:
 1. Lê os votos já gravados dos juízes (17-juiz-*.jsonl): cada frase de cada resposta
    recebeu "sim" (sustentada pelos trechos), "parcial" ou "nao".
 2. Lê os rótulos humanos de bancada/calibracao/rotulos-humanos.jsonl (gerados pela ficha
    do rotular.py). Procura também em gabarito/, avaliacao/ e pacote/outputs/ e registra o
    que achou: hoje NÃO existe rótulo humano de frase em nenhum desses lugares (o gabarito/
    marca trechos relevantes por pergunta, feito por agente, não frases sustentadas).
 3. Por juiz, contra a pessoa: concordância bruta, kappa de Cohen com IC 95% (bootstrap por
    pergunta), matriz de confusão e a taxa do ERRO CARO = o juiz aprovou ("sim") uma frase
    que a pessoa reprovou.
 4. Entre juízes: concordância e kappa par a par, separando mesmo modelo (repetição),
    mesma família e família diferente.
 5. Calcula quantas frases rotuladas faltam para o IC do kappa ter meia-largura ~0,15.

Rodar (só biblioteca padrão; nenhuma chamada de rede ou de modelo):
    PYTHONDONTWRITEBYTECODE=1 nice -n 19 python3 bancada/calibracao/calibrar.py
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone, timedelta
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import (rel, CLASSES, GRUPO, JUIZES, N_BOOT, OUT, PRINCIPAIS, RAIZ, ROTULOS, SEMENTE,  # noqa: E402
                   bootstrap_por_pergunta, carregar_rotulos, carregar_votos, commit, kappa,
                   kappa_de_matriz, matriz, n_para_meia_largura, wilson)

DESTINO = OUT / "33-juiz-calibracao.json"
MEIA_LARGURA = 0.15
MIN_ROTULOS_PARA_CALIBRAR = 30      # abaixo disso o kappa vira sorteio; não calcula por juiz


def procurar_rotulos_humanos() -> list[dict]:
    """Varre gabarito/, avaliacao/ e pacote/outputs/ atrás de arquivo com rótulo HUMANO de frase.
    Critério: JSON/JSONL com campo 'rotulo' e 'uid' (formato do rotular.py) ou que se declare
    feito por humano E tenha veredito de frase. Devolve o que achou, para registrar no JSON."""
    achados = []
    for pasta in ("gabarito", "avaliacao", "pacote/outputs", "bancada/calibracao"):
        for p in sorted((RAIZ / pasta).glob("*.json*")):
            if p.name.startswith("33-"):
                continue
            try:
                txt = p.read_text(encoding="utf-8")[:200000]
            except Exception:
                continue
            tem_frase_rotulada = '"rotulo"' in txt and '"uid"' in txt
            autor_humano = ("não conferido por humano" not in txt) and ('"avaliador"' in txt)
            if tem_frase_rotulada and autor_humano:
                achados.append({"arquivo": rel(p), "tipo": "rotulo humano de frase"})
    return achados


def par_tipo(a: str, b: str) -> str:
    ma, mb = JUIZES[a]["modelo"], JUIZES[b]["modelo"]
    if ma == mb:
        return "mesmo modelo (repeticao)"
    if JUIZES[a]["familia"] == JUIZES[b]["familia"]:
        return "mesma familia"
    return "familia diferente"


def pesos_da_amostra() -> dict[str, float]:
    """Peso de cada frase na amostra estratificada do rotular.py (total do estrato / sorteados).
    Serve para corrigir o fato de a ficha ter mais frases difíceis do que a população."""
    p = Path(__file__).resolve().parent / "amostra.json"
    if not p.exists():
        return {}
    return {i["uid"]: float(i["peso"]) for i in json.loads(p.read_text(encoding="utf-8"))["itens"]}


def comparar(ref: dict[str, str], outro: dict[str, str], pesos: dict[str, float] | None = None) -> dict:
    """Compara dois conjuntos de votos nas frases que os dois têm. ref = linha da matriz.
    Com pesos, acrescenta o kappa corrigido para a população (frases fora da amostra pesam 1)."""
    uids = sorted(set(ref) & set(outro))
    a = [ref[u] for u in uids]
    b = [outro[u] for u in uids]
    m = matriz(a, b)
    k, po, pe = kappa_de_matriz(m)
    iguais = sum(x == y for x, y in zip(a, b))
    ic_k = bootstrap_por_pergunta(uids, lambda us: kappa([ref[u] for u in us], [outro[u] for u in us]))
    ic_po = bootstrap_por_pergunta(uids, lambda us: sum(ref[u] == outro[u] for u in us) / len(us))
    perguntas = len({u.split("-")[0] for u in uids})
    extra = {}
    if pesos:
        w = lambda us: [pesos.get(u, 1.0) for u in us]  # noqa: E731
        kp = kappa([ref[u] for u in uids], [outro[u] for u in uids], w(uids))
        extra = {"kappa_ponderado_populacao": round(kp, 3) if kp == kp else None,
                 "kappa_ponderado_ic95": bootstrap_por_pergunta(
                     uids, lambda us: kappa([ref[u] for u in us], [outro[u] for u in us], w(us)))}
    return {**extra,
        "n_frases": len(uids), "n_perguntas": perguntas,
        "concordancia_bruta": round(po, 3) if po == po else None,
        "concordancia_ic95_bootstrap": ic_po,
        "concordancia_ic95_wilson_ingenuo": wilson(iguais, len(uids)),
        "kappa": round(k, 3) if k == k else None,
        "kappa_ic95": ic_k,
        "acaso_pe": round(pe, 3) if pe == pe else None,
        "matriz_confusao": {"linhas": "referencia", "colunas": "comparado", "ordem": CLASSES,
                            "valores": [[int(x) for x in linha] for linha in m]},
    }


def erro_caro(humano: dict[str, str], juiz: dict[str, str]) -> dict:
    """O erro que custa caro: a pessoa reprovou, o juiz aprovou. Dois cortes:
    estrito = pessoa 'nao' e juiz 'sim'; amplo = pessoa 'nao' ou 'parcial' e juiz 'sim'."""
    uids = sorted(set(humano) & set(juiz))
    out = {}
    for nome, reprova in (("estrito_nao_virou_sim", {"nao"}), ("amplo_nao_ou_parcial_virou_sim", {"nao", "parcial"})):
        base = [u for u in uids if humano[u] in reprova]
        k = sum(juiz[u] == "sim" for u in base)
        out[nome] = {"n_reprovadas_pela_pessoa": len(base), "aprovadas_pelo_juiz": k,
                     "taxa": round(k / len(base), 3) if base else None, "ic95_wilson": wilson(k, len(base))}
    return out


def distribuicao(v: dict[str, str]) -> dict:
    n = len(v)
    out: dict = {"n": n}
    for c in CLASSES:
        k = sum(x == c for x in v.values())
        out[c] = {"k": k, "prop": round(k / n, 3) if n else None, "ic95_wilson": wilson(k, n)}
    return out


def main() -> int:
    votos, info = carregar_votos()
    humano, por_pessoa = carregar_rotulos()
    humano = {u: c for u, c in humano.items() if u in info}   # só frases que existem nos votos
    achados = procurar_rotulos_humanos()

    # ---------------- entre juízes
    pares = []
    for a, b in combinations(JUIZES, 2):
        r = comparar(votos[a], votos[b])
        if r["n_frases"] == 0:
            continue
        pares.append({"a": a, "b": b, "tipo": par_tipo(a, b), **r})
    por_tipo = {}
    for t in sorted({p["tipo"] for p in pares}):
        ks = [p["kappa"] for p in pares if p["tipo"] == t and p["kappa"] is not None]
        pos = [p["concordancia_bruta"] for p in pares if p["tipo"] == t]
        por_tipo[t] = {"pares": [f"{p['a']} x {p['b']}" for p in pares if p["tipo"] == t],
                       "kappa_medio": round(statistics.mean(ks), 3) if ks else None,
                       "concordancia_media": round(statistics.mean(pos), 3) if pos else None}

    # Frases em que os 3 juízes principais concordam / discordam (o desacordo é onde a pessoa mais ajuda)
    comuns = sorted(set.intersection(*(set(votos[j]) for j in PRINCIPAIS)))
    unanimes = sum(len({votos[j][u] for j in PRINCIPAIS}) == 1 for u in comuns)

    # ---------------- quantos rótulos faltam
    principais = [p for p in pares if p["a"] in PRINCIPAIS and p["b"] in PRINCIPAIS]
    pe_med = statistics.mean(p["acaso_pe"] for p in principais if p["acaso_pe"] is not None)
    # efeito de desenho: quanto o bootstrap por pergunta alarga o IC em relação à fórmula de frase solta
    deffs = []
    for p in principais:
        if p["kappa"] is None or not p["kappa_ic95"]:
            continue
        po = p["concordancia_bruta"]
        se_formula = (po * (1 - po) / (p["n_frases"] * (1 - p["acaso_pe"]) ** 2)) ** 0.5
        se_boot = (p["kappa_ic95"][1] - p["kappa_ic95"][0]) / (2 * 1.96)
        if se_formula > 0:
            deffs.append((se_boot / se_formula) ** 2)
    deff = round(max(1.0, statistics.median(deffs)), 2) if deffs else 1.0
    cenarios = []
    for k_alvo in (0.4, 0.6, 0.8):
        n_ind = n_para_meia_largura(k_alvo, pe_med, MEIA_LARGURA)
        n_cl = n_para_meia_largura(k_alvo, pe_med, MEIA_LARGURA, deff)
        cenarios.append({"kappa_esperado": k_alvo, "n_frases_se_independentes": n_ind,
                         "n_frases_com_efeito_de_desenho": n_cl,
                         "cabe_no_total_disponivel": n_cl <= len(info)})
    n_rec = next(c["n_frases_com_efeito_de_desenho"] for c in cenarios if c["kappa_esperado"] == 0.6)
    calculo_n = {
        "meta_meia_largura_ic95_kappa": MEIA_LARGURA,
        "formula": "n = 1,96^2 * po(1-po) / ((1-pe)^2 * h^2) * deff, com po = kappa(1-pe)+pe",
        "pe_usado": round(pe_med, 3),
        "pe_origem": "media do acaso (pe) dos 3 pares de juizes principais; a pessoa deve ter distribuicao parecida",
        "efeito_de_desenho_deff": deff,
        "deff_origem": "mediana de (EP bootstrap por pergunta / EP formula)^2 nos pares principais; minimo 1",
        "cenarios": cenarios,
        "recomendado_kappa_0_6": n_rec,
        "rotulados_ate_agora": len(humano),
        "faltam": max(0, n_rec - len(humano)),
        "total_frases_disponiveis": len(info),
        "aviso": ("se a pessoa der quase tudo 'sim' (como os juizes), pe sobe e o kappa fica instavel: "
                  "por isso a amostra do rotular.py puxa a mais as frases com voto 'parcial'/'nao' e com desacordo"),
    }

    # ---------------- contra a pessoa
    por_juiz = {}
    if len(humano) >= MIN_ROTULOS_PARA_CALIBRAR:
        estado = "calibrado" if len(humano) >= n_rec else "calibracao parcial (IC ainda largo)"
        for j in JUIZES:
            r = comparar(humano, votos[j], pesos_da_amostra())
            if r["n_frases"] == 0:
                continue
            r["erro_caro_aprovou_o_que_a_pessoa_reprovou"] = erro_caro(humano, votos[j])
            por_juiz[j] = r
    elif humano:
        estado = f"aguardando rotulos (so {len(humano)} de no minimo {MIN_ROTULOS_PARA_CALIBRAR})"
    else:
        estado = "aguardando rotulos"

    agora = datetime.now(timezone(timedelta(hours=-3)))
    saida = {
        "estado": estado,
        "data": agora.isoformat(timespec="seconds"),
        "commit_grupo": commit(GRUPO),
        "commit_bancada": commit(RAIZ),
        "origem_dos_votos": ("votos REAIS de juizes por modelo ja gravados (rodadas anteriores), nao do provedor "
                             "deterministico 'eco'; este script nao chama nenhum modelo"),
        "unidade": "frase de resposta (prompt v1, 17-respostas.jsonl), casada entre juizes por texto normalizado",
        "classes": CLASSES,
        "ic95": f"bootstrap por pergunta ({N_BOOT} reamostragens, semente {SEMENTE}); proporcoes simples com Wilson",
        "juizes": {j: {**JUIZES[j], "distribuicao_votos": distribuicao(votos[j])} for j in JUIZES},
        "fora_da_conta": {"17-juiz-v2-busca-nova-r1.jsonl": "julga outras respostas (v2), 4 perguntas, sem outro juiz nas mesmas frases",
                          "17-juizes-comparados.txt": "relatorio por RESPOSTA (100% sustentada), refeito aqui por FRASE",
                          "28-divergencias-juizes.json": "subconjunto (so frases com desacordo) dos mesmos votos; usado como conferencia"},
        "rotulos_humanos": {
            "arquivo": rel(ROTULOS),
            "existe": ROTULOS.exists(),
            "n_frases_rotuladas": len(humano),
            "avaliadores": {p: len(d) for p, d in sorted(por_pessoa.items())},
            "busca_em_gabarito_avaliacao_outputs": achados or (
                "nenhum rotulo humano de frase encontrado. gabarito/ tem trechos relevantes por pergunta marcados por "
                "agente (Claude Opus), 'nao conferido por humano'; avaliacao/ so tem documentos .md; outputs/ so tem "
                "votos de modelo"),
            "distribuicao": distribuicao(humano) if humano else None,
        },
        "contra_a_pessoa_por_juiz": por_juiz or None,
        "entre_juizes": {
            "pares": pares,
            "por_tipo_de_par": por_tipo,
            "tres_principais": {"juizes": PRINCIPAIS, "n_frases_comuns": len(comuns), "unanimes": unanimes,
                                "unanimes_ic95_wilson": wilson(unanimes, len(comuns)),
                                "com_desacordo": len(comuns) - unanimes},
            "leitura": ("Dois juízes concordarem não prova que acertam: podem errar igual "
                        "(mesma família de modelo, mesma tendência a aprovar). Só a pessoa diz quem acerta."),
        },
        "rotulos_necessarios": calculo_n,
    }
    if achados and not humano:
        saida["rotulos_humanos"]["nota"] = "arquivos candidatos encontrados, mas nenhum uid casou com as frases julgadas"
    DESTINO.write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---------------- resumo legível no terminal
    print(f"estado: {estado} | frases julgadas: {len(info)} | rotuladas por pessoa: {len(humano)}")
    print("entre juizes (kappa [IC95]):")
    for p in pares:
        print(f"  {p['a']:>16} x {p['b']:<16} {p['tipo']:<26} n={p['n_frases']:3d}  "
              f"igual={p['concordancia_bruta']}  kappa={p['kappa']} {p['kappa_ic95']}")
    print(f"tres principais: {unanimes}/{len(comuns)} frases unanimes")
    print(f"para meia-largura {MEIA_LARGURA} no kappa (kappa~0,6, pe={pe_med:.2f}, deff={deff}): "
          f"{n_rec} frases; faltam {calculo_n['faltam']}")
    for j, r in (por_juiz or {}).items():
        ec = r["erro_caro_aprovou_o_que_a_pessoa_reprovou"]["amplo_nao_ou_parcial_virou_sim"]
        print(f"  {j}: igual={r['concordancia_bruta']} kappa={r['kappa']} {r['kappa_ic95']} erro caro={ec['taxa']} {ec['ic95_wilson']}")
    print(f"-> {rel(DESTINO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
