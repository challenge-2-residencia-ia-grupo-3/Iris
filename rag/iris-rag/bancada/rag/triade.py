"""triade.py: as três perguntas do RAG num lugar só (no estilo do Ragas, sem usar a biblioteca Ragas).

Analogia: o RAG é uma corrente de três elos, como um aluno fazendo prova com consulta.
  1. BUSCA      - ele abriu o livro na página certa?            (recall@5 / hit@5 contra o gabarito)
  2. FIDELIDADE - ele escreveu só o que a página diz?             (juízes-modelo, frase a frase)
  3. CITAÇÃO    - ele disse de que página tirou cada frase?       (conta [Tn] no texto, sem modelo)
  +1. ABSTENÇÃO - quando a resposta não está no livro, ele admitiu? (sem modelo)

Para cada pergunta do gabarito (40) e cada configuração já medida (versão do prompt / busca), o script
diz qual elo quebrou primeiro. Não roda modelo nenhum: só lê o que já está em pacote/outputs/.

    python3 bancada/rag/triade.py            # grava pacote/outputs/34-rag-triade.json e imprime o resumo

O que é determinístico (contado por código, repete igual) e o que vem de juiz-modelo (opinião de um LLM,
ainda NÃO calibrada contra humano) vai marcado em cada métrica no campo "origem".
Nenhum texto de trecho vai para a saída: só ids de pergunta e contagens.
Só biblioteca padrão do Python.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True          # não deixar __pycache__ em pacote/
RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "pacote"
# Carrega pacote/bancada.py pelo caminho (a pasta bancada/ tem o mesmo nome e confundiria o "import bancada").
# Reaproveita: leitura dos jsonl, gabarito, IC bootstrap, fração de frases sustentadas e commit de origem.
_spec = importlib.util.spec_from_file_location("pacote_bancada", PACOTE / "bancada.py")
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

SAIDA = bc.OUT / "34-rag-triade.json"
COMMIT_GRUPO = "65e1f09"   # commit do repo do grupo usado na bancada; estas respostas vêm do protótipo pacote/

# Configurações já medidas: (nome, arquivo de respostas, descrição, juízes que julgaram ESTE arquivo)
CONFIGS = [
    ("v1", "17-respostas.jsonl", "prompt v1, busca qwen3+rerank (sistema atual)",
     [("gpt-oss-120b r1", "17-juiz-r1.jsonl"), ("gpt-oss-120b r2", "17-juiz-r2.jsonl"),
      ("gpt-oss-20b local", "17-juiz-local.jsonl"), ("Haiku 5.5 r1", "17-juiz-haiku.jsonl"),
      ("Haiku 5.5 r2", "17-juiz-haiku-r2.jsonl")]),
    ("v2", "17-respostas-v2.jsonl", "prompt v2, mesmos 5 trechos da v1", []),
    ("v3", "17-respostas-v3.jsonl", "prompt v3, mesmos 5 trechos da v1", []),
    ("v2-busca-nova", "17-respostas-v2-busca-nova.jsonl", "prompt v2 com a busca rodada de novo (33 de 40, posta de lado)",
     [("gpt-oss-120b r1", "17-juiz-v2-busca-nova-r1.jsonl")]),
]

# Mesma regra de frase e de citação que pacote/gerar.py usa em conferir() (copiada aqui porque importar
# gerar.py puxa o buscador; o resultado é conferido contra o campo 'conferencia' gravado, ver _conferir_bate).
CITA = re.compile(r"\[T(\d+)\]")


def frases_de(resposta: str) -> list[str]:
    return [f for f in re.split(r"(?<=[.!?])\s+", resposta.strip()) if len(f.split()) >= 4]


# ---------------------------------------------------------------- estatística
def wilson(k: int, n: int) -> dict:
    """Proporção com intervalo de Wilson 95% (melhor que o 'normal' quando n é pequeno ou p perto de 0/1)."""
    if n == 0:
        return {"k": 0, "n": 0, "v": None, "ic95": None, "metodo_ic": "wilson"}
    z, p = 1.959964, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"k": k, "n": n, "v": round(p, 3), "ic95": [round(max(0, c - m), 3), round(min(1, c + m), 3)],
            "metodo_ic": "wilson"}


def media(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "v": None, "ic95": None, "metodo_ic": "bootstrap"}
    m, lo, hi = bc.ic(vals)       # bootstrap por pergunta, 2000 reamostragens, semente fixa da bancada
    return {"n": len(vals), "v": m, "ic95": [lo, hi], "metodo_ic": "bootstrap por pergunta (2000, semente 20261106)"}


# ---------------------------------------------------------------- elos por pergunta
def elo_busca(g: dict, r: dict | None) -> dict:
    rel = set(g.get("trechos_relevantes", []))
    if g["tipo"] == "sem_resposta" or not rel:
        return {"estado": "nao_se_aplica", "motivo": "pergunta sem resposta no corpus"}
    if r is None:
        return {"estado": "sem_medida", "motivo": "configuração não rodou esta pergunta"}
    top5 = [t["chunk_id"] for t in r["trechos"]][:5]
    certos = len(rel & set(top5))
    rec = certos / len(rel)
    return {"estado": "ok" if certos else "quebrou", "recall5": round(rec, 4), "hit5": bool(certos),
            "certos_no_top5": certos, "relevantes_no_gabarito": len(rel),
            **({} if certos else {"motivo": "nenhum trecho do gabarito entre os 5 trazidos"})}


def elo_citacao(r: dict | None) -> dict:
    if r is None:
        return {"estado": "sem_medida"}
    if r["conferencia"]["absteve"]:
        return {"estado": "nao_se_aplica", "motivo": "absteve"}
    n_tr = len(r["trechos"])
    fr = frases_de(r["resposta"])
    com_valida = sem = so_invalida = 0
    for f in fr:
        ns = [int(x) for x in CITA.findall(f)]
        if not ns:
            sem += 1
        elif any(1 <= x <= n_tr for x in ns):
            com_valida += 1
        else:
            so_invalida += 1
    invalidas = sorted({int(x) for x in CITA.findall(r["resposta"]) if not 1 <= int(x) <= n_tr})
    prop = com_valida / len(fr) if fr else None
    quebrou = sem > 0 or invalidas
    return {"estado": "quebrou" if quebrou else "ok", "frases": len(fr), "frases_com_citacao_valida": com_valida,
            "frases_sem_citacao": sem, "frases_so_com_citacao_invalida": so_invalida,
            "citacoes_a_trecho_inexistente": len(invalidas), "prop_frases_citadas": None if prop is None else round(prop, 4),
            **({"motivo": f"{sem} frase(s) sem [Tn], {len(invalidas)} citação(ões) a trecho que não existe"} if quebrou else {})}


def elo_fidelidade(q: str, r: dict | None, juizes: dict[str, dict]) -> dict:
    """Juiz-modelo. 'quebrou' = a maioria dos juízes achou ao menos uma frase NÃO sustentada (inventou);
    'duvida' = só parte dos juízes achou, ou só houve 'parcial' (esticou o trecho)."""
    if r is None:
        return {"estado": "sem_medida"}
    if r["conferencia"]["absteve"]:
        return {"estado": "nao_se_aplica", "motivo": "absteve"}
    por_juiz = {}
    for nome, J in juizes.items():
        if q not in J:
            continue
        fr = J[q].get("veredito", {}).get("frases") or []
        f = bc._fidelidade(J[q].get("veredito", {}))
        if f is None:
            continue
        por_juiz[nome] = {"fid": round(f["fid"], 4), "frases": len(fr),
                          "nao": sum(x.get("sustentada") == "nao" for x in fr),
                          "parcial": sum(x.get("sustentada") == "parcial" for x in fr)}
    if not por_juiz:
        return {"estado": "sem_medida", "motivo": "nenhum juiz julgou esta resposta"}
    inventou = sum(v["nao"] > 0 for v in por_juiz.values())
    esticou = sum(v["parcial"] > 0 for v in por_juiz.values())
    if inventou * 2 > len(por_juiz):
        est, mot = "quebrou", f"{inventou} de {len(por_juiz)} juízes viram frase não sustentada"
    elif inventou or esticou:
        est, mot = "duvida", f"{inventou} juiz(es) viram frase não sustentada, {esticou} viram só 'parcial'"
    else:
        est, mot = "ok", None
    return {"estado": est, "juizes": por_juiz, **({"motivo": mot} if mot else {})}


def elo_abstencao(g: dict, r: dict | None, busca: dict) -> dict:
    if r is None:
        return {"estado": "sem_medida"}
    abst = bool(r["conferencia"]["absteve"])
    if g["tipo"] == "sem_resposta":
        return {"estado": "ok" if abst else "quebrou", "absteve": abst,
                **({} if abst else {"motivo": "respondeu pergunta sem resposta no corpus"})}
    if not abst:
        return {"estado": "ok", "absteve": False}
    if busca.get("hit5"):
        return {"estado": "quebrou", "absteve": True, "motivo": "absteve mesmo com trecho certo no top-5"}
    return {"estado": "ok", "absteve": True, "motivo": "absteve porque a busca falhou (coerente; o elo quebrado é a busca)"}


ORDEM = ["busca", "abstencao", "fidelidade", "citacao"]


def primeiro_quebrado(elos: dict) -> str | None:
    for e in ORDEM:
        if elos[e]["estado"] == "quebrou":
            return e
    return None


# ---------------------------------------------------------------- por configuração
def resumo_config(nome, arq, desc, juizes_cfg, G) -> tuple[dict, list[dict]]:
    R = bc.por_id(bc.jl(arq))
    juizes = {n: bc.por_id(bc.jl(a)) for n, a in juizes_cfg if bc.jl(a)}
    linhas = []
    for q, g in sorted(G.items()):
        r = R.get(q)
        b = elo_busca(g, r)
        elos = {"busca": b, "abstencao": elo_abstencao(g, r, b),
                "fidelidade": elo_fidelidade(q, r, juizes), "citacao": elo_citacao(r)}
        linhas.append({"id": q, "tipo": g["tipo"], "elos": elos, "primeiro_elo_quebrado": primeiro_quebrado(elos)})

    com_resp = [l for l in linhas if l["elos"]["busca"]["estado"] in ("ok", "quebrou")]
    respondidas = [l for l in linhas if l["elos"]["citacao"]["estado"] in ("ok", "quebrou")]
    sem_resp = [l for l in linhas if l["tipo"] == "sem_resposta" and l["elos"]["abstencao"]["estado"] != "sem_medida"]
    cit = [l["elos"]["citacao"] for l in respondidas]
    fid = {}
    for n in juizes:
        vals = [l["elos"]["fidelidade"]["juizes"][n]["fid"] for l in respondidas
                if n in l["elos"]["fidelidade"].get("juizes", {})]
        fid[n] = {**media(vals), "cobertura": f"{len(vals)} de {len(respondidas)} respostas julgadas",
                  "toda_sustentada": wilson(sum(v == 1.0 for v in vals), len(vals))}
    metricas = {
        "1_busca": {
            "origem": "deterministico (gabarito rascunho, 1 marcador-modelo)",
            "recall@5": media([l["elos"]["busca"]["recall5"] for l in com_resp]),
            "hit@5": wilson(sum(l["elos"]["busca"]["hit5"] for l in com_resp), len(com_resp))},
        "2_fidelidade": {
            "origem": "juiz-modelo NÃO calibrado contra humano (fração de frases 'sim', média por resposta)",
            "por_juiz": fid or None,
            **({} if fid else {"aviso": "nenhum juiz rodou nesta configuração: fidelidade não medida"})},
        "3_citacao": {
            "origem": "deterministico (regex [Tn] por frase, mesma regra de pacote/gerar.py conferir())",
            "prop_frases_citadas": media([c["prop_frases_citadas"] for c in cit if c["prop_frases_citadas"] is not None]),
            "respostas_100pct_citadas": wilson(sum(c["estado"] == "ok" for c in cit), len(cit)),
            "frases_total": sum(c["frases"] for c in cit),
            "frases_sem_citacao_total": sum(c["frases_sem_citacao"] for c in cit),
            "citacoes_a_trecho_inexistente_total": sum(c["citacoes_a_trecho_inexistente"] for c in cit)},
        "4_abstencao": {
            "origem": "deterministico (frase-padrão de abstenção detectada pelo código)",
            "absteve_certo_sem_resposta": wilson(sum(l["elos"]["abstencao"]["absteve"] for l in sem_resp), len(sem_resp)),
            "absteve_com_trecho_certo": wilson(sum(l["elos"]["abstencao"]["estado"] == "quebrou" for l in com_resp),
                                               len(com_resp)),
            "cobertura_respondeu": wilson(len(respondidas) - sum(l["tipo"] == "sem_resposta" for l in respondidas),
                                          len(com_resp))},
    }
    quebras = {}
    for l in linhas:
        k = l["primeiro_elo_quebrado"] or "nenhum"
        quebras[k] = quebras.get(k, 0) + 1
    fontes = [arq] + [a for _, a in juizes_cfg]
    # Portão: só com números determinísticos (o juiz não calibrado não reprova nada, só avisa).
    motivos = []
    a4, c3 = metricas["4_abstencao"], metricas["3_citacao"]
    if a4["absteve_certo_sem_resposta"]["k"] < a4["absteve_certo_sem_resposta"]["n"]:
        motivos.append("respondeu pergunta sem resposta no corpus")
    if c3["citacoes_a_trecho_inexistente_total"] > 0:
        motivos.append("citou trecho que não existe")
    p = c3["prop_frases_citadas"]
    if p["v"] is not None and p["v"] < 0.95:
        motivos.append(f"só {p['v']} das frases citam a fonte (mínimo 0,95)")
    if a4["absteve_com_trecho_certo"]["k"] > 3:
        motivos.append("absteve em mais de 3 perguntas que tinham o trecho certo no top-5")
    portao = {"aprovado": not motivos, "motivos": motivos,
              "regra": "reprova se: abstenção certa < 100% nas sem_resposta; >=1 citação a trecho inexistente; "
                       "frases citadas < 0,95; ou >3 abstenções com trecho certo no top-5. Fidelidade (juiz) só avisa."}
    cfg = {"config": nome, "descricao": desc, "arquivo_respostas": arq, "llm_gerador": next(iter(R.values()))["llm"] if R else None,
           "perguntas_rodadas": len(R), "perguntas_no_gabarito": len(G), "metricas": metricas,
           "primeiro_elo_quebrado_contagem": quebras, "portao": portao,
           "fontes": {f: bc.origem(bc.OUT / f) for f in fontes if (bc.OUT / f).exists()}}
    return cfg, linhas


def _conferir_bate(arq: str) -> dict:
    """Confere a minha contagem de frases/sem citação contra a que pacote/gerar.py gravou na hora."""
    dif = []
    for r in bc.jl(arq):
        if r["conferencia"]["absteve"]:
            continue
        c = elo_citacao(r)
        if c["frases"] != r["conferencia"]["frases"] or c["frases_sem_citacao"] != len(r["conferencia"]["frases_sem_citacao"]):
            dif.append(r["id"])
    return {"arquivo": arq, "diverge_de_gerar_conferir": dif}


def _conferir_recall() -> dict:
    """Confere o recall@5 recalculado aqui (v1) contra o gravado em 17-hyde.jsonl (variante 'pergunta')."""
    H = bc.por_id(bc.jl("17-hyde.jsonl"))
    G = bc.gabarito()
    R = bc.por_id(bc.jl("17-respostas.jsonl"))
    dif = [q for q in H if q in R and abs(elo_busca(G[q], R[q]).get("recall5", -1) - H[q]["pergunta"]["recall5"]) > 1e-3]
    return {"comparado_com": "17-hyde.jsonl[pergunta].recall5 (tolerância 0,001: aqui é arredondado em 4 casas)",
            "n": len(H), "diverge": dif}


def main() -> None:
    G = bc.gabarito()
    configs, matriz = [], []
    for nome, arq, desc, js in CONFIGS:
        if not (bc.OUT / arq).exists():
            continue
        cfg, linhas = resumo_config(nome, arq, desc, js, G)
        configs.append(cfg)
        for l in linhas:
            matriz.append({"config": nome, "id": l["id"], "tipo": l["tipo"],
                           **{e: l["elos"][e]["estado"] for e in ORDEM},
                           "primeiro_elo_quebrado": l["primeiro_elo_quebrado"], "detalhe": l["elos"]})
    saida = {
        "titulo": "Tríade do RAG: busca -> fidelidade -> citação (+ abstenção), por configuração e por pergunta",
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit_bancada": bc.origem(Path(__file__)), "commit_grupo": COMMIT_GRUPO,
        "nota_commit_grupo": "as respostas medidas aqui vêm do protótipo pacote/ (gerar.py), não do código do grupo",
        "gabarito": {"arquivo": "gabarito/gabarito_rascunho_v0.json", "n_perguntas": len(G),
                     "sem_resposta": sorted(q for q, g in G.items() if g["tipo"] == "sem_resposta"),
                     "aviso": "gabarito rascunho de 1 marcador (modelo): recall pode estar subestimado"},
        "provedor": "respostas geradas por groq:qwen/qwen3.8-27b (temperatura 0), não pelo provedor 'eco'; "
                    "nada foi gerado nem julgado nesta execução (só leitura de outputs/)",
        "origem_dos_numeros": {
            "deterministico": ["1_busca", "3_citacao", "4_abstencao"],
            "juiz_modelo_nao_calibrado": ["2_fidelidade"],
            "aviso": "juízes discordam muito entre si (kappa 0,16-0,29 em '100% sustentada', ver 17-juizes-comparados.txt); "
                     "fidelidade serve para observar, não para reprovar"},
        "estados": {"ok": "elo segurou", "quebrou": "elo falhou", "duvida": "juízes divididos ou só 'parcial'",
                    "nao_se_aplica": "não cabe (ex.: abstenção não tem citação)", "sem_medida": "não há dado"},
        "ordem_dos_elos": ORDEM,
        "regra_primeiro_elo": "percorre busca, abstenção, fidelidade, citação e devolve o primeiro 'quebrou'",
        "conferencias": {"recall": _conferir_recall(),
                         "citacao": [_conferir_bate(a) for _, a, _, _ in CONFIGS if (bc.OUT / a).exists()]},
        "configuracoes": configs,
        "matriz": matriz,
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{SAIDA.relative_to(RAIZ)}: {len(configs)} configurações x {len(G)} perguntas = {len(matriz)} células")
    for c in configs:
        m = c["metricas"]
        f = lambda d: f"{d['v']} [{d['ic95'][0]}-{d['ic95'][1]}]" if d.get("ic95") else "-"
        fid = "; ".join(f"{n} {f(v)}" for n, v in (m["2_fidelidade"]["por_juiz"] or {}).items()) or "sem juiz"
        print(f"\n[{c['config']}] {c['descricao']} ({c['perguntas_rodadas']} rodadas)")
        print(f"  1 busca      recall@5 {f(m['1_busca']['recall@5'])}  hit@5 {m['1_busca']['hit@5']['k']}/{m['1_busca']['hit@5']['n']}")
        print(f"  2 fidelidade (juiz) {fid}")
        print(f"  3 citação    frases citadas {f(m['3_citacao']['prop_frases_citadas'])}  sem citação "
              f"{m['3_citacao']['frases_sem_citacao_total']}/{m['3_citacao']['frases_total']}  a trecho inexistente "
              f"{m['3_citacao']['citacoes_a_trecho_inexistente_total']}")
        a = m["4_abstencao"]
        print(f"  4 abstenção  certa {a['absteve_certo_sem_resposta']['k']}/{a['absteve_certo_sem_resposta']['n']}  "
              f"absteve com trecho certo {a['absteve_com_trecho_certo']['k']}/{a['absteve_com_trecho_certo']['n']}")
        print(f"  primeiro elo quebrado: {c['primeiro_elo_quebrado_contagem']}")
        print(f"  portão: {'APROVADO' if c['portao']['aprovado'] else 'REPROVADO: ' + '; '.join(c['portao']['motivos'])}")
    cf = saida["conferencias"]
    print(f"\nconferência recall vs 17-hyde: {len(cf['recall']['diverge'])} divergências em {cf['recall']['n']}")
    print("conferência citação vs gerar.conferir: " + ", ".join(f"{x['arquivo']}={len(x['diverge_de_gerar_conferir'])}"
                                                             for x in cf["citacao"]))
    # --portao: sai com código 1 se a configuração padrão (v1) reprovar, para o Makefile/vigia barrar
    if "--portao" in sys.argv:
        padrao = next((c for c in configs if c["config"] == "v1"), None)
        if padrao is None or not padrao["portao"]["aprovado"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
