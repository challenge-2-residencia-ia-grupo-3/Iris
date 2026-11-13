"""Confere o rastro do pipeline contra o orçamento (bancada/orcamento/orcamento.json).

Analogia: é como conferir o extrato do mês contra o orçamento da casa. O "extrato" são os rastros
que o arnês grava quando roda o código do grupo (pacote/reports/pipeline/*.jsonl e o resumo
pacote/outputs/26-rastro-pipeline-resumo.json). O "orçamento" tem tetos de tempo, tokens
(pedaços de texto que o modelo lê e escreve), chamadas ao modelo e dólares, cada um com a fonte
(RNF-07/RNF-08 do grupo ou proposta da bancada).

Grava pacote/outputs/36-orcamento.json com, por etapa e por material: medido, limite, folga e
estouros; e uma PROJEÇÃO do tempo com modelo real, feita a partir das medições reais que o grupo
já gravou (llama3.1:8b no Adaptador, cb2a510; llama3 no Extrator, 1db2dd8) e do 23-custo.json.

Importante: no provedor eco a latência de modelo é praticamente zero. Então, na VPS, o orçamento
de tempo só INFORMA; ele vira portão de verdade quando o pipeline rodar com modelo real no PC.

Uso (só biblioteca padrão; lê o clone do grupo sem importar nada dele):
    nice -n 19 python3 bancada/orcamento/conferir.py [--grupo CAMINHO] [--saida ARQUIVO]
Código de saída: 0 = portão aprovado; 1 = estouro de limite 'duro'; 2 = faltou arquivo de entrada.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent  # .../iris-rag
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("onde", Path(__file__).resolve().parents[1] / "onde.py")
_onde = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_onde)
GRUPO_PADRAO = _onde.grupo()

AVISO_ECO = "provedor determinístico: mede o encanamento, não a qualidade de um modelo"
AVISO_TEMPO = ("Com o modelo substituto, o tempo de modelo é quase zero (ele responde na hora, sem gerar texto). "
               "Por isso o tempo medido na VPS só informa e não reprova. O orçamento de tempo passa a reprovar "
               "quando o pipeline rodar com modelo real. A projeção ao lado estima esse tempo a partir de "
               "medições já feitas pelo grupo.")
ETAPAS_MODELO_GRUPO = ("extrator_curricular", "agente_adaptador")
ETAPAS_MODELO_ARNES = ("diretiva_substituta_arnes",)


# ------------------------------------------------------------------ estatística simples
def percentil(valores: list[float], p: float) -> float | None:
    """Percentil com interpolação linear (p entre 0 e 100)."""
    v = sorted(valores)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * p / 100.0
    i = int(math.floor(pos))
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (pos - i)


def ic_bootstrap(valores: list[float], estat, reamostras: int, rng: random.Random) -> list[float] | None:
    """Intervalo de 95% por bootstrap (sorteia com reposição e recalcula a estatística)."""
    if len(valores) < 2:
        return None
    res = sorted(estat([rng.choice(valores) for _ in valores]) for _ in range(reamostras))
    return [round(percentil(res, 2.5), 4), round(percentil(res, 97.5), 4)]


def ic_wilson(acertos: int, n: int) -> list[float] | None:
    """Intervalo de Wilson 95% para uma proporção."""
    if n == 0:
        return None
    z = 1.959964
    p = acertos / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, centro - meia), 4), round(min(1.0, centro + meia), 4)]


def r4(x):
    return None if x is None else round(x, 4)


# ------------------------------------------------------------------ leitura
def ler_jsonl(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def runs_principais(pasta: Path) -> dict[str, list[dict]]:
    """Rastros das rodadas normais (sem adversarial nem ablação): run_id -> linhas."""
    runs = {}
    for f in sorted(pasta.glob("*.jsonl")):
        if re.match(r"^\d{8}-\d{6}-", f.name):
            runs[f.stem] = ler_jsonl(f)
    return runs


def runs_adversariais(pasta: Path) -> dict[str, list[dict]]:
    return {f.stem: ler_jsonl(f) for f in sorted(pasta.glob("adv-*.jsonl"))}


def palavras_do_material(linhas: list[dict]) -> int | None:
    for l in linhas:
        if l["etapa"] == "validacao_conteudo" and isinstance(l.get("saida"), list) and len(l["saida"]) == 2:
            return int(l["saida"][1])
        if l["etapa"] == "validacao_conteudo":
            m = re.search(r"(\d+) palavras", l.get("resumo_saida") or "")
            if m:
                return int(m.group(1))
    return None


def custo_usd(tok_in: float, tok_out: float, preco: dict) -> float:
    return tok_in / 1e6 * preco["entrada"] + tok_out / 1e6 * preco["saida"]


def commit_curto(grupo: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(grupo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


# ------------------------------------------------------------------ conferência por etapa
def conferir_etapas(runs: dict[str, list[dict]], orc: dict, rng: random.Random, reamostras: int) -> tuple[list, list]:
    lim_etapas = orc["limites_por_etapa"]
    padrao = lim_etapas["_padrao_deterministica"]
    por_etapa: dict[str, dict] = {}
    for linhas in runs.values():
        for l in linhas:
            e = por_etapa.setdefault(l["etapa"], {"lat": [], "tin": [], "tout": [], "status": {}, "primeira_busca": []})
            e["status"][l["status"]] = e["status"].get(l["status"], 0) + 1
            if l["status"] != "ok":
                continue
            e["lat"].append(float(l.get("latencia_s") or 0.0))
            if l.get("modelo") or (l.get("tokens_entrada") or 0) > 0:
                e["tin"].append(int(l.get("tokens_entrada") or 0))
                e["tout"].append(int(l.get("tokens_saida") or 0))
    # chamadas ao modelo por questão e por etapa (1 etapa com tokens = pelo menos 1 chamada)
    chamadas_q: dict[tuple, int] = {}
    for rid, linhas in runs.items():
        for l in linhas:
            if l["status"] == "ok" and (l.get("tokens_entrada") or 0) > 0:
                chave = (rid, l.get("questao"), l["etapa"])
                chamadas_q[chave] = chamadas_q.get(chave, 0) + 1

    saida, estouros = [], []
    for etapa, d in por_etapa.items():
        lim = None if etapa == "ciclo_rnf07" else lim_etapas.get(etapa, padrao)
        item = {"etapa": etapa, "n": len(d["lat"]), "status": d["status"]}
        if not d["lat"]:
            item["observacao"] = "sem execução 'ok' (etapa não implementada no commit do grupo)"
            saida.append(item)
            continue
        p95 = percentil(d["lat"], 95)
        item.update(latencia_p50_s=r4(percentil(d["lat"], 50)), latencia_p95_s=r4(p95),
                    ic95_latencia_p95_s=ic_bootstrap(d["lat"], lambda v: percentil(v, 95), reamostras, rng),
                    latencia_max_s=r4(max(d["lat"])))
        if lim is None:
            item["observacao"] = lim_etapas["ciclo_rnf07"]["observacao"]
            saida.append(item)
            continue
        item["limite_latencia_p95_s"] = lim["latencia_p95_s"]
        item["folga_latencia_s"] = r4(lim["latencia_p95_s"] - p95)
        item["tipo_portao_latencia"] = lim.get("tipo_portao_latencia", "informativo")
        item["fonte_limite"] = lim["fonte"]
        if p95 > lim["latencia_p95_s"]:
            estouros.append({"onde": f"etapa:{etapa}", "medida": "latencia_p95_s", "medido": r4(p95),
                             "limite": lim["latencia_p95_s"], "tipo": "informativo",
                             "nota": "tempo medido na VPS com eco: só informa"})
        n_cham = [v for (rid, q, e), v in chamadas_q.items() if e == etapa]
        item["chamadas_modelo_por_questao_max"] = max(n_cham) if n_cham else 0
        item["limite_chamadas_por_questao"] = lim.get("chamadas_modelo_por_questao")
        if lim.get("chamadas_modelo_por_questao") is not None and item["chamadas_modelo_por_questao_max"] > lim["chamadas_modelo_por_questao"]:
            estouros.append({"onde": f"etapa:{etapa}", "medida": "chamadas_por_questao",
                             "medido": item["chamadas_modelo_por_questao_max"],
                             "limite": lim["chamadas_modelo_por_questao"], "tipo": "duro"})
        if d["tin"]:
            item.update(tokens_entrada_media=r4(statistics.mean(d["tin"])),
                        ic95_tokens_entrada_media=ic_bootstrap(d["tin"], statistics.mean, reamostras, rng),
                        tokens_entrada_max=max(d["tin"]), tokens_saida_max=max(d["tout"]),
                        limite_tokens_entrada=lim.get("tokens_entrada_max"),
                        limite_tokens_saida=lim.get("tokens_saida_max"))
            for chave, medido in (("tokens_entrada_max", max(d["tin"])), ("tokens_saida_max", max(d["tout"]))):
                if lim.get(chave) is not None:
                    item["folga_" + chave] = lim[chave] - medido
                    if medido > lim[chave]:
                        estouros.append({"onde": f"etapa:{etapa}", "medida": chave, "medido": medido,
                                         "limite": lim[chave], "tipo": lim.get("tipo_portao_tokens", "alerta")})
        if etapa == "busca_rag":
            item["nota"] = ("a 1ª busca de cada processo carrega o índice (partida a frio) e puxa o p95 para cima; "
                            "as demais ficam em ~0,02 s")
        saida.append(item)
    saida.sort(key=lambda x: x["etapa"])
    return saida, estouros


# ------------------------------------------------------------------ conferência por material
def conferir_material(run_id: str, linhas: list[dict], nivel: int, orc: dict, fator_tok: float,
                      saida_real_q: dict) -> tuple[dict, list]:
    lim = orc["limites_por_adaptacao"]
    lim_q = orc["limites_por_questao"]
    precos = orc["tabela_precos"]["modelos"]
    padrao = orc["atividade_padrao"]
    material = linhas[0]["material_id"] if linhas else run_id
    questoes = sorted({l["questao"] for l in linhas if l.get("questao")})
    nq = len(questoes)
    palavras = palavras_do_material(linhas)
    lat_total = sum(float(l.get("latencia_s") or 0.0) for l in linhas)
    lim_lat = lim["latencia_total_s"][f"nivel_{nivel}"]

    def soma(etapas, campo):
        return sum(int(l.get(campo) or 0) for l in linhas if l["etapa"] in etapas and l["status"] == "ok")

    tok_grupo = soma(ETAPAS_MODELO_GRUPO, "tokens_entrada") + soma(ETAPAS_MODELO_GRUPO, "tokens_saida")
    tok_arnes = soma(ETAPAS_MODELO_ARNES, "tokens_entrada") + soma(ETAPAS_MODELO_ARNES, "tokens_saida")
    ciclos = [l for l in linhas if l["etapa"] == "ciclo_rnf07" and isinstance(l.get("saida"), dict)]
    chamadas_grupo = sum(int(c["saida"].get("chamadas", 0)) for c in ciclos)
    chamadas_arnes = sum(1 for l in linhas if l["etapa"] in ETAPAS_MODELO_ARNES and l["status"] == "ok")
    chamadas = chamadas_grupo + chamadas_arnes
    por_q = {q: sum(1 for l in linhas if l.get("questao") == q and (l.get("tokens_entrada") or 0) > 0) for q in questoes}
    fator5 = padrao["max_questoes"] / nq if nq else 0.0

    # tokens estimados com modelo real: entrada do eco (palavras) x fator medido; saída = mediana real medida
    tin_g = soma(ETAPAS_MODELO_GRUPO, "tokens_entrada") * fator_tok
    tin_a = soma(ETAPAS_MODELO_ARNES, "tokens_entrada") * fator_tok
    tout_g = nq * (saida_real_q["extrator"] + saida_real_q[f"adaptador_n{nivel}"])
    tout_a = nq * saida_real_q["diretiva_teto"]
    custo = {}
    for nome, preco in precos.items():
        custo[nome] = {
            "medido_tokens_eco_usd": round(custo_usd(soma(ETAPAS_MODELO_GRUPO + ETAPAS_MODELO_ARNES, "tokens_entrada"),
                                                     soma(ETAPAS_MODELO_GRUPO + ETAPAS_MODELO_ARNES, "tokens_saida"), preco), 6),
            "estimado_modelo_real_5q_usd": round(custo_usd((tin_g + tin_a) * fator5, (tout_g + tout_a) * fator5, preco), 6),
        }
    ref = "claude-haiku-5.5"
    custo_ref = custo[ref]["estimado_modelo_real_5q_usd"]

    m = {
        "material_id": material, "run_id": run_id, "nivel": nivel, "n_questoes": nq, "palavras": palavras,
        "dentro_da_atividade_padrao": (nq <= padrao["max_questoes"]) and (palavras is None or palavras <= padrao["max_palavras"]),
        "latencia": {"medido_s": r4(lat_total), "limite_s": lim_lat, "folga_s": r4(lim_lat - lat_total),
                     "tipo_portao": "informativo (eco)", "fonte_limite": lim["latencia_total_s"]["fonte"]},
        "tokens_cadeia_grupo": {"medido": tok_grupo, "projetado_5_questoes": round(tok_grupo * fator5),
                                "limite_5_questoes": lim["tokens_total_cadeia"]["max"],
                                "folga": lim["tokens_total_cadeia"]["max"] - round(tok_grupo * fator5),
                                "tipo_portao": "duro", "fonte_limite": "RNF-08 literal",
                                "unidade": "palavras contadas pelo eco (um modelo real conta mais tokens)"},
        "tokens_cadeia_com_arnes": {"medido": tok_grupo + tok_arnes,
                                    "projetado_5_questoes": round((tok_grupo + tok_arnes) * fator5),
                                    "limite_5_questoes": lim["tokens_total_cadeia"]["max"],
                                    "folga": lim["tokens_total_cadeia"]["max"] - round((tok_grupo + tok_arnes) * fator5),
                                    "tipo_portao": "alerta",
                                    "nota": "inclui a diretiva do arnês (substituta do Estrategista, que não existe no commit)"},
        "tokens_estimados_modelo_real_5q": {
            "cadeia_grupo": round((tin_g + tout_g) * fator5), "cadeia_com_arnes": round((tin_g + tin_a + tout_g + tout_a) * fator5),
            "limite": lim["tokens_total_cadeia"]["max"], "tipo_portao": "alerta",
            "como": f"entrada do eco x {fator_tok:.2f} (tokens reais por palavra, medido no Adaptador cb2a510); "
                    "saída = mediana real do Extrator e do Adaptador no nível; diretiva = teto max_tokens 500"},
        "chamadas_modelo": {"medido": chamadas, "do_grupo": chamadas_grupo, "do_arnes": chamadas_arnes,
                            "projetado_5_questoes": round(chamadas * fator5), "limite_5_questoes": lim["chamadas_modelo"]["max"],
                            "por_questao_max": max(por_q.values()) if por_q else 0,
                            "limite_por_questao": lim_q["chamadas_modelo"]["max"],
                            "fonte_limite": lim["chamadas_modelo"]["fonte"], "tipo_portao": "duro"},
        "custo_usd_por_modelo": custo,
        "custo_referencia": {"modelo": ref, "estimado_5q_usd": custo_ref, "limite_usd": lim["custo_usd"]["max"],
                             "folga_usd": round(lim["custo_usd"]["max"] - custo_ref, 6),
                             "tipo_portao": "alerta", "fonte_limite": lim["custo_usd"]["fonte"]},
        "ciclo_rnf07_do_grupo": [{"questao": next((l.get("questao") for l in linhas if l is c), None),
                                  "total_ms": c["saida"].get("total_ms"), "limite_ms": c["saida"].get("limite_ms"),
                                  "dentro_do_limite": c["saida"].get("dentro_do_limite")} for c in ciclos],
        "nota_ciclo_rnf07": ("o resumir_ciclo do grupo compara UMA questão (2 chamadas) com o teto que o RNF-07 dá para a "
                             "atividade inteira (até 5 questões); a bancada soma o material todo"),
    }
    est = []
    if nq > padrao["max_questoes"] or (palavras or 0) > padrao["max_palavras"]:
        est.append({"onde": f"material:{material}", "medida": "tamanho_atividade", "medido": [nq, palavras],
                    "limite": [padrao["max_questoes"], padrao["max_palavras"]], "tipo": "informativo",
                    "nota": "material fora da atividade padrão do RNF-07"})
    if lat_total > lim_lat:
        est.append({"onde": f"material:{material}", "medida": "latencia_total_s", "medido": r4(lat_total), "limite": lim_lat, "tipo": "informativo"})
    regras = [("tokens_cadeia_grupo_5q", m["tokens_cadeia_grupo"]["projetado_5_questoes"], lim["tokens_total_cadeia"]["max"], "duro"),
              ("tokens_cadeia_com_arnes_5q", m["tokens_cadeia_com_arnes"]["projetado_5_questoes"], lim["tokens_total_cadeia"]["max"], "alerta"),
              ("tokens_modelo_real_grupo_5q", m["tokens_estimados_modelo_real_5q"]["cadeia_grupo"], lim["tokens_total_cadeia"]["max"], "alerta"),
              ("tokens_modelo_real_com_arnes_5q", m["tokens_estimados_modelo_real_5q"]["cadeia_com_arnes"], lim["tokens_total_cadeia"]["max"], "alerta"),
              ("chamadas_5q", m["chamadas_modelo"]["projetado_5_questoes"], lim["chamadas_modelo"]["max"], "duro"),
              ("chamadas_por_questao", m["chamadas_modelo"]["por_questao_max"], lim_q["chamadas_modelo"]["max"], "duro"),
              ("custo_usd_5q_" + ref, custo_ref, lim["custo_usd"]["max"], "alerta")]
    for nome, medido, limite, tipo in regras:
        if medido > limite:
            est.append({"onde": f"material:{material}", "medida": nome, "medido": medido, "limite": limite, "tipo": tipo})
    m["estouros"] = est
    return m, est


# ------------------------------------------------------------------ projeção com modelo real
def projetar(grupo: Path, runs: dict[str, list[dict]], orc: dict, custo23: list, rng: random.Random) -> tuple[dict, dict, float]:
    """Monte Carlo: sorteia uma medição real por chamada e soma as etapas de N questões em sequência."""
    cfg = orc["projecao_modelo_real"]
    adapt = json.load(open(grupo / "reports" / "adaptador_com_modelo.json", encoding="utf-8"))
    extr = ler_jsonl(grupo / "reports" / "extractor_telemetry.jsonl")
    ad_ms = {n: [r["total_ms"] / 1000 for r in adapt["registros"] if r["nivel"] == n] for n in (1, 2, 3)}
    ad_pt = [r["prompt_tokens"] for r in adapt["registros"]]
    ad_out = {n: statistics.median(r["completion_tokens"] for r in adapt["registros"] if r["nivel"] == n) for n in (1, 2, 3)}
    ex_ms = [r["total_ms"] / 1000 for r in extr]
    ex_out = statistics.median(r["completion_tokens"] for r in extr)
    # velocidade de leitura do prompt (tokens/s) medida no Extrator: serve para estimar a diretiva (prompt grande)
    leitura = statistics.median(r["prompt_tokens"] / (r["prompt_eval_ms"] / 1000) for r in extr if r.get("prompt_eval_ms"))
    geracao = statistics.median(r["tokens_per_sec"] for r in adapt["registros"] if r.get("tokens_per_sec"))

    # fator tokens reais por "token" do eco (palavras): mesmo agente (Adaptador), prompts equivalentes
    eco_ad_in = [l["tokens_entrada"] for ls in runs.values() for l in ls if l["etapa"] == "agente_adaptador" and l["status"] == "ok"]
    fator_tok = statistics.median(ad_pt) / statistics.median(eco_ad_in) if eco_ad_in else 2.0
    eco_dir_in = [l["tokens_entrada"] for ls in runs.values() for l in ls if l["etapa"] == "diretiva_substituta_arnes" and l["status"] == "ok"]
    dir_in_real = (statistics.median(eco_dir_in) if eco_dir_in else 2200) * fator_tok
    dir_out = orc["limites_por_etapa"]["diretiva_substituta_arnes"]["tokens_saida_max"]

    # etapas sem modelo: tempo real medido na VPS (código do grupo); busca pela linha do 23-custo quando houver
    det_por_q, det_fixo = [], []
    for ls in runs.values():
        fixo = sum(float(l["latencia_s"] or 0) for l in ls if not l.get("questao"))
        det_fixo.append(fixo)
        for q in {l["questao"] for l in ls if l.get("questao")}:
            det_por_q.append(sum(float(l["latencia_s"] or 0) for l in ls if l.get("questao") == q
                                 and l["etapa"] not in ETAPAS_MODELO_GRUPO + ETAPAS_MODELO_ARNES + ("busca_rag",)))
    busca_vps = [float(l["latencia_s"]) for ls in runs.values() for l in ls if l["etapa"] == "busca_rag" and l["status"] == "ok"]
    busca_pc = next((c["mediana_s"] for c in custo23 if "bge-m3" in c["peca"] and "4b" not in c["peca"]), None)

    def diretiva_s(ad_amostra: float) -> float:
        # sem medição real da diretiva: leitura do prompt grande + geração de até 500 tokens na velocidade medida
        return dir_in_real / leitura + dir_out / geracao

    cenarios = {
        "grupo_hoje": "Extrator + Adaptador (o que existe no commit do grupo)",
        "com_estrategista": "Extrator + diretiva/Estrategista (prompt do RAG, até 500 tokens de saída) + Adaptador",
        "completo_com_auditor": "como 'com_estrategista' + Auditor (hipótese: custa como mais uma chamada do Adaptador)",
    }
    sims, reams, seed = cfg["simulacoes"], cfg["reamostras_ic"], cfg["semente"]

    def simular(nivel: int, nq: int, cen: str, fontes: dict, n: int, rr: random.Random) -> list[float]:
        tot = []
        for _ in range(n):
            t = rr.choice(fontes["fixo"])
            for _q in range(nq):
                a = rr.choice(fontes["ad"][nivel])
                t += rr.choice(fontes["ex"]) + a + rr.choice(fontes["detq"]) + rr.choice(fontes["busca"])
                if cen != "grupo_hoje":
                    t += diretiva_s(a)
                if cen == "completo_com_auditor":
                    t += rr.choice(fontes["ad"][nivel])
            tot.append(t)
        return tot

    fontes = {"fixo": det_fixo, "ad": ad_ms, "ex": ex_ms, "detq": det_por_q,
              "busca": [busca_pc] if busca_pc is not None else busca_vps}
    resultado = []
    for nivel in (1, 2, 3):
        limite = orc["limites_por_adaptacao"]["latencia_total_s"][f"nivel_{nivel}"]
        for nq in (1, 5):
            for cen in cenarios:
                rr = random.Random(f"{seed}-{nivel}-{nq}-{cen}")
                tot = simular(nivel, nq, cen, fontes, sims, rr)
                dentro = sum(1 for t in tot if t <= limite)
                # IC: reamostra as próprias medições (bootstrap das fontes) e recalcula o p95
                p95s = []
                for _ in range(reams):
                    fb = {"fixo": [rr.choice(det_fixo) for _ in det_fixo],
                          "ad": {k: [rr.choice(v) for _ in v] for k, v in ad_ms.items()},
                          "ex": [rr.choice(ex_ms) for _ in ex_ms], "detq": det_por_q, "busca": fontes["busca"]}
                    p95s.append(percentil(simular(nivel, nq, cen, fb, 300, rr), 95))
                p95 = percentil(tot, 95)
                resultado.append({
                    "nivel": nivel, "n_questoes": nq, "cenario": cen, "limite_s": limite,
                    "p50_s": round(percentil(tot, 50), 2), "p95_s": round(p95, 2),
                    "ic95_p95_s": [round(percentil(p95s, 2.5), 2), round(percentil(p95s, 97.5), 2)],
                    "folga_p95_s": round(limite - p95, 2),
                    "fracao_simulacoes_dentro": round(dentro / sims, 4),
                    "veredito_projetado": "dentro do RNF-07" if p95 <= limite else "estoura o RNF-07",
                })
    proj = {
        "aviso": ("projeção, não medição: soma medições reais feitas em momentos e máquinas diferentes, supondo "
                  "chamadas em sequência (uma questão depois da outra, como no código do grupo hoje)"),
        "maquina_das_medicoes_de_modelo": "PC do grupo com Ollama (a mesma do cb2a510); tempo de modelo na VPS não foi medido",
        "medicoes": {
            "adaptador_llama3.1_8b": {"fonte": "grupo reports/adaptador_com_modelo.json (cb2a510)", "n_por_nivel": {k: len(v) for k, v in ad_ms.items()},
                                      "mediana_s_por_nivel": {k: round(statistics.median(v), 2) for k, v in ad_ms.items()},
                                      "max_s_por_nivel": {k: round(max(v), 2) for k, v in ad_ms.items()}},
            "extrator_llama3": {"fonte": "grupo reports/extractor_telemetry.jsonl (1db2dd8)", "n": len(ex_ms),
                                "mediana_s": round(statistics.median(ex_ms), 2), "max_s": round(max(ex_ms), 2)},
            "busca": {"fonte": "pacote/outputs/23-custo.json (qwen3 + bge-m3, PC RTX)" if busca_pc is not None else "rastro VPS",
                      "mediana_s": busca_pc if busca_pc is not None else round(statistics.median(busca_vps), 4)},
            "etapas_sem_modelo": {"fonte": "pacote/reports/pipeline/*.jsonl (VPS, código do grupo)", "n_questoes": len(det_por_q),
                                  "mediana_s_por_questao": r4(statistics.median(det_por_q)) if det_por_q else None},
            "diretiva_estimada": {"tokens_entrada_estimados": round(dir_in_real), "tokens_saida_teto": dir_out,
                                  "leitura_tokens_por_s": round(leitura, 1), "geracao_tokens_por_s": round(geracao, 1),
                                  "segundos": round(diretiva_s(0), 2),
                                  "nota": "não há medição real do Estrategista; é conta a partir das velocidades medidas"},
            "fator_tokens_reais_por_palavra_eco": round(fator_tok, 3),
        },
        "cenarios": cenarios,
        "n_simulacoes": sims, "reamostras_ic": reams, "semente": seed,
        "resultado": resultado,
    }
    saida_real_q = {"extrator": ex_out, "adaptador_n1": ad_out[1], "adaptador_n2": ad_out[2], "adaptador_n3": ad_out[3],
                    "diretiva_teto": dir_out}
    return proj, saida_real_q, fator_tok


# ------------------------------------------------------------------ principal
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grupo", type=Path, default=GRUPO_PADRAO, help="clone do grupo (só leitura)")
    ap.add_argument("--orcamento", type=Path, default=AQUI / "orcamento.json")
    ap.add_argument("--pacote", type=Path, default=RAIZ / "pacote")
    ap.add_argument("--saida", type=Path, default=None)
    a = ap.parse_args()
    saida = a.saida or a.pacote / "outputs" / "36-orcamento.json"

    # 23-custo.json é opcional: sem ele, o tempo da busca vem do rastro desta máquina
    necessarios = [a.orcamento, a.pacote / "outputs" / "26-rastro-pipeline-resumo.json",
                   a.grupo / "reports" / "adaptador_com_modelo.json", a.grupo / "reports" / "extractor_telemetry.jsonl"]
    faltando = [str(p) for p in necessarios if not p.exists()]
    if faltando:
        print("faltam arquivos de entrada:", *faltando, sep="\n  ", file=sys.stderr)
        return 2

    orc = json.load(open(a.orcamento, encoding="utf-8"))
    resumo = json.load(open(a.pacote / "outputs" / "26-rastro-pipeline-resumo.json", encoding="utf-8"))
    c23 = a.pacote / "outputs" / "23-custo.json"
    custo23 = json.load(open(c23, encoding="utf-8")) if c23.exists() else []
    pasta = a.pacote / "reports" / "pipeline"
    runs = runs_principais(pasta)
    adv = runs_adversariais(pasta)
    if not runs:
        print(f"faltam os rastros do pipeline em {pasta}: rode antes  make rastro-pipeline  (o orçamento confere esses rastros)",
              file=sys.stderr)
        return 2
    rng = random.Random(orc["projecao_modelo_real"]["semente"])
    reams = orc["projecao_modelo_real"]["reamostras_ic"]
    nivel = int(resumo.get("config", {}).get("nivel", 2))

    proj, saida_real_q, fator_tok = projetar(a.grupo, runs, orc, custo23, rng)
    por_etapa, estouros = conferir_etapas(runs, orc, rng, reams)

    por_material = []
    for ex in resumo.get("execucoes", []):
        linhas = runs.get(ex["run_id"])
        if linhas is None:  # o jsonl foi apagado: usa as linhas do resumo (sem 'saida' do ciclo)
            linhas = [dict(l, run_id=ex["run_id"], material_id=ex["material_id"]) for l in ex["etapas"]]
        m, est = conferir_material(ex["run_id"], linhas, nivel, orc, fator_tok, saida_real_q)
        por_material.append(m)
        estouros += est

    # adversariais: só contam chamadas por questão (são entradas maliciosas, não atividade padrão)
    lim_cq = orc["limites_por_questao"]["chamadas_modelo"]["max"]
    adv_q = []
    for rid, ls in adv.items():
        for q in {l.get("questao") for l in ls if l.get("questao")}:
            adv_q.append(sum(1 for l in ls if l.get("questao") == q and (l.get("tokens_entrada") or 0) > 0))
    adv_dentro = sum(1 for v in adv_q if v <= lim_cq)
    if adv_q and max(adv_q) > lim_cq:
        estouros.append({"onde": "adversariais", "medida": "chamadas_por_questao", "medido": max(adv_q), "limite": lim_cq, "tipo": "duro"})

    # resumo por questão nas rodadas normais (proporção dentro do teto de chamadas e de tokens por questão)
    lim_tq = orc["limites_por_questao"]["tokens_total"]["max"]
    qs = []
    for rid, ls in runs.items():
        for q in {l.get("questao") for l in ls if l.get("questao")}:
            lq = [l for l in ls if l.get("questao") == q and l["status"] == "ok"]
            qs.append({"tok_grupo": sum((l.get("tokens_entrada") or 0) + (l.get("tokens_saida") or 0) for l in lq if l["etapa"] in ETAPAS_MODELO_GRUPO),
                       "tok_total": sum((l.get("tokens_entrada") or 0) + (l.get("tokens_saida") or 0) for l in lq),
                       "lat": sum(float(l.get("latencia_s") or 0) for l in lq)})
    n_q = len(qs)
    dentro_g = sum(1 for q in qs if q["tok_grupo"] <= lim_tq)
    dentro_t = sum(1 for q in qs if q["tok_total"] <= lim_tq)
    por_questao = {
        "n": n_q, "rodadas": len(runs),
        "tokens_cadeia_grupo": {"media": r4(statistics.mean(q["tok_grupo"] for q in qs)) if qs else None,
                                "ic95_media": ic_bootstrap([q["tok_grupo"] for q in qs], statistics.mean, reams, rng),
                                "limite": lim_tq, "fracao_dentro": r4(dentro_g / n_q) if n_q else None,
                                "ic95_fracao_wilson": ic_wilson(dentro_g, n_q)},
        "tokens_com_arnes": {"media": r4(statistics.mean(q["tok_total"] for q in qs)) if qs else None,
                             "ic95_media": ic_bootstrap([q["tok_total"] for q in qs], statistics.mean, reams, rng),
                             "limite": lim_tq, "fracao_dentro": r4(dentro_t / n_q) if n_q else None,
                             "ic95_fracao_wilson": ic_wilson(dentro_t, n_q)},
        "latencia_s": {"media": r4(statistics.mean(q["lat"] for q in qs)) if qs else None,
                       "ic95_media": ic_bootstrap([q["lat"] for q in qs], statistics.mean, reams, rng),
                       "p95": r4(percentil([q["lat"] for q in qs], 95)), "tipo_portao": "informativo (eco)"},
        "adversariais_chamadas": {"n_questoes": len(adv_q), "max": max(adv_q) if adv_q else None, "limite": lim_cq,
                                  "fracao_dentro": r4(adv_dentro / len(adv_q)) if adv_q else None,
                                  "ic95_fracao_wilson": ic_wilson(adv_dentro, len(adv_q))},
    }

    duros = [e for e in estouros if e["tipo"] == "duro"]
    alertas = [e for e in estouros if e["tipo"] == "alerta"]
    info = [e for e in estouros if e["tipo"] == "informativo"]
    proj_estoura = [f"nível {r['nivel']}, {r['n_questoes']} questão(ões), {r['cenario']}: p95 {r['p95_s']} s > {r['limite_s']} s"
                    for r in proj["resultado"] if r["veredito_projetado"] != "dentro do RNF-07"]
    provedor = resumo.get("provedor")
    commits = sorted({l.get("commit_grupo") for ls in runs.values() for l in ls if l.get("commit_grupo")})
    out = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit_grupo": resumo.get("commit_grupo"),
        "commits_grupo_nos_rastros": commits,
        "commit_grupo_clone_lido": commit_curto(a.grupo),
        "provedor": provedor, "modelo": resumo.get("modelo"),
        "aviso": AVISO_ECO if provedor == "eco" else None,
        "aviso_tempo": AVISO_TEMPO if provedor == "eco" else "provedor real: o orçamento de tempo vale como portão",
        "orcamento": str(a.orcamento.relative_to(RAIZ)) if a.orcamento.is_relative_to(RAIZ) else str(a.orcamento),
        "orcamento_versao": orc.get("versao"),
        "tabela_precos_data": orc["tabela_precos"]["data_consulta"],
        "entradas": {"resumo": "pacote/outputs/26-rastro-pipeline-resumo.json", "rastros_normais": len(runs),
                     "rastros_adversariais": len(adv), "custo": "pacote/outputs/23-custo.json",
                     "grupo": ["reports/adaptador_com_modelo.json", "reports/extractor_telemetry.jsonl"]},
        "portao": {
            "status": "reprovado" if duros else "aprovado",
            "regra": ("reprova se algum limite 'duro' estourar: chamadas ao modelo por questão (> 3) ou por atividade de 5 questões (> 15), "
                      "ou tokens da cadeia do grupo projetados para 5 questões (> 8.000, RNF-08). Tempo: informativo com eco; "
                      "com provedor real (fora do eco), o p95 do material acima do RNF-07 também reprova. 'alerta' só avisa."),
            "n_duros": len(duros), "n_alertas": len(alertas), "n_informativos": len(info),
            "projecao_modelo_real_estoura": proj_estoura,
        },
        "por_etapa": por_etapa,
        "por_material": por_material,
        "por_questao": por_questao,
        "projecao_modelo_real": proj,
        "estouros": estouros,
    }
    # com modelo real o tempo vira duro
    if provedor != "eco":
        for m in por_material:
            if m["latencia"]["folga_s"] < 0:
                out["estouros"].append({"onde": f"material:{m['material_id']}", "medida": "latencia_total_s",
                                        "medido": m["latencia"]["medido_s"], "limite": m["latencia"]["limite_s"], "tipo": "duro"})
                out["portao"]["status"] = "reprovado"
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp = saida.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(saida)

    print(f"orçamento: {out['portao']['status']} | duros {len(duros)} | alertas {len(alertas)} | informativos {len(info)} | {saida}")
    for m in por_material:
        print(f"  {m['material_id']}: {m['n_questoes']} q, {m['latencia']['medido_s']} s (limite {m['latencia']['limite_s']}), "
              f"tokens grupo 5q {m['tokens_cadeia_grupo']['projetado_5_questoes']}, com arnês 5q {m['tokens_cadeia_com_arnes']['projetado_5_questoes']}, "
              f"real estimado 5q {m['tokens_estimados_modelo_real_5q']['cadeia_grupo']}/{m['tokens_estimados_modelo_real_5q']['cadeia_com_arnes']}, "
              f"US$ haiku 5q {m['custo_referencia']['estimado_5q_usd']}, estouros {len(m['estouros'])}")
    for r in proj["resultado"]:
        print(f"  projeção n{r['nivel']} {r['n_questoes']}q {r['cenario']}: p50 {r['p50_s']} s, p95 {r['p95_s']} s {r['ic95_p95_s']} "
              f"(limite {r['limite_s']}) -> {r['veredito_projetado']}")
    return 1 if out["portao"]["status"] == "reprovado" else 0


if __name__ == "__main__":
    sys.exit(main())
