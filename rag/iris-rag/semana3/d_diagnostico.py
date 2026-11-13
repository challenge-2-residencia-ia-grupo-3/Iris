"""d_diagnostico.py: por que o teste D cai na saída de reserva, e o que o modelo escreveu antes de cair.

Registrado no PREREG em 13/11/2026 (item c). O rastro do arnês (saidas/d_execucao/<modelo>-r<n>/rastro-*.jsonl)
guarda cada chamada do laudo de escopo do grupo, com o texto avaliado e as violações. A primeira chamada de
cada questão é o texto do modelo (a minuta); se ela reprova, a segunda é a reserva determinística.
Este script lê esses rastros (não gera nada) e responde:
  - em quantas questões a minuta do modelo passa no laudo, por configuração;
  - por que reprova (tipos de violação);
  - se a diretiva do RAG muda a minuta (completo x sem_rag);
  - as métricas do grupo (TRCC, comando conjugado, Flesch) na minuta e no texto entregue.

Subcomandos:
  analisar            lê os rastros das execuções já feitas e os da execução corrigida, se existir
  corrigido-gptoss    roda o D do gpt-oss (1 rodada) com think="low" e teto de 4.000 tokens, acrescentados
                      na chamada HTTP sem tocar no código do grupo; saídas em saidas_d_corrigido/     [Ollama]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import comum as C
import metricas as M

CORRIGIDO = C.AQUI / "saidas_d_corrigido"
CONFIGS = ("completo", "sem_rag")


def preparar_grupo():
    sys.path.insert(0, str(C.IRIS_RAG / "bancada" / "pipeline"))
    import ablacao  # noqa: F401  (põe o código do grupo no sys.path)
    return ablacao.T


def minutas(pasta: Path, config: str) -> dict[str, dict]:
    """Por questão: a minuta do modelo (se houve), o laudo dela e o motivo da reserva."""
    por_q: dict[str, list[dict]] = {}
    for l in C.ler_jsonl(pasta / f"rastro-{config}.jsonl"):
        por_q.setdefault(l["material_id"], []).append(l)
    out = {}
    for qid, linhas in por_q.items():
        linhas.sort(key=lambda l: l["ordem"])
        ad = next((l for l in linhas if l["etapa"] == "agente_adaptador"), None)
        if ad is None:
            continue
        tel = (ad.get("saida") or {}).get("telemetry") or {}
        motivo = tel.get("motivo_fallback")
        laudos = [l for l in linhas if l["etapa"] == "laudo_isolamento_escopo"]
        tem_minuta = motivo in (None, "escopo_reprovado") and laudos
        m = laudos[0] if tem_minuta else None
        out[qid] = {"motivo_reserva": motivo, "entregue": (ad.get("saida") or {}).get("texto_adaptado"),
                    "original": ad["entrada"]["enunciado"],
                    "minuta": m["entrada"]["adaptado"] if m else None, "laudo": m["saida"] if m else None}
    return out


def tipos_de_violacao(laudo: dict) -> list[str]:
    t = []
    if laudo.get("palavras_novas"):
        t.append("acrescentou palavras fora do andaime")
    if laudo.get("palavras_perdidas"):
        t.append("tirou palavras do original")
    if laudo.get("ordem_alterada"):
        t.append("mudou a ordem das palavras")
    if laudo.get("estrutura_alterada"):
        t.append("alterou o texto além do destaque")
    if laudo.get("conceitos_perdidos"):
        t.append("perdeu conceito da trava curricular")
    return t


def analisar() -> None:
    T = preparar_grupo()
    from iris.eval.benchmark import carregar_golden_benchmark
    from iris.eval.readability import analyze_question
    from iris.eval.trcc import avaliar_trcc
    qs = {q.id: q for q in carregar_golden_benchmark(T.GRUPO / "data" / "golden_benchmark.json")}
    res, L = {}, ["TESTE D - DIAGNÓSTICO DA SAÍDA DE RESERVA (lido dos rastros; nenhum juiz)",
                  f"gerado em {C.agora_iso()} | commit {C.commit_atual()}", "",
                  "minuta = texto que o modelo escreveu, antes do laudo de escopo do grupo", ""]
    execucoes = sorted((C.SAIDAS / "d_execucao").glob("*-r*")) + sorted(CORRIGIDO.glob("d_execucao/*-r*"))
    por_modelo: dict[str, list[Path]] = {}
    for p in execucoes:
        nome = p.name.rsplit("-r", 1)[0] + (" (cliente corrigido)" if CORRIGIDO in p.parents else "")
        por_modelo.setdefault(nome, []).append(p)
    for modelo, pastas in por_modelo.items():
        res[modelo] = {}
        L.append(f"== {modelo}: {len(pastas)} rodada(s)")
        linhas_m: dict[str, list[dict]] = {c: [] for c in CONFIGS}
        for pasta in pastas:
            rodada = int(pasta.name.rsplit("-r", 1)[1])
            for config in CONFIGS:
                for qid, m in minutas(pasta, config).items():
                    q = qs[qid]
                    linha = {"id": qid, "rodada": rodada, "config": config, **m}
                    for nome, txt in (("minuta", m["minuta"]), ("entregue", m["entregue"])):
                        if txt:
                            a = analyze_question(qid, txt)
                            linha |= {f"trcc_{nome}": avaliar_trcc(q.trava_curricular, txt).trcc, f"flesch_{nome}": a.flesch,
                                      f"cmd_{nome}": a.n_conjugated_commands, f"palavras_{nome}": len(txt.split())}
                    orig = analyze_question(qid, m["original"])
                    linha |= {"cmd_original": orig.n_conjugated_commands, "flesch_original": orig.flesch,
                              "palavras_original": len(m["original"].split())}
                    linhas_m[config].append(linha)
        for config in CONFIGS:
            ls = linhas_m[config]
            com = [l for l in ls if l["minuta"]]
            aprov = [l for l in com if l["laudo"]["aprovado"]]
            viol = Counter(t for l in com if not l["laudo"]["aprovado"] for t in tipos_de_violacao(l["laudo"]))
            razao = sorted(l["palavras_minuta"] / max(1, l["palavras_original"]) for l in com)
            r = {"execucoes": len(ls), "motivo_reserva": dict(Counter(str(l["motivo_reserva"]) for l in ls)),
                 "com_minuta": len(com), "minuta_aprovada_no_laudo": len(aprov),
                 "questoes_com_minuta_aprovada_em_todas_as_rodadas": sorted(
                     q for q in {l["id"] for l in com} if all(l["laudo"]["aprovado"] for l in com if l["id"] == q)),
                 "violacoes_nas_reprovadas": dict(viol.most_common()),
                 "palavras_minuta_sobre_original_mediana": round(razao[len(razao) // 2], 2) if razao else None,
                 "trcc_minuta": M._media([l.get("trcc_minuta") for l in com]),
                 "trcc_entregue": M._media([l.get("trcc_entregue") for l in ls]),
                 "flesch_original": M._media([l["flesch_original"] for l in ls]),
                 "flesch_minuta": M._media([l.get("flesch_minuta") for l in com]),
                 "flesch_entregue": M._media([l.get("flesch_entregue") for l in ls]),
                 "cmd_conjugado_resolvido_minuta": M._media([float(l["cmd_minuta"] == 0) for l in com if l["cmd_original"]]),
                 "cmd_conjugado_resolvido_entregue": M._media([float(l.get("cmd_entregue") == 0) for l in ls if l["cmd_original"]])}
            res[modelo][config] = r
            L += [f"  {config}: {r['execucoes']} execuções | motivo da reserva {r['motivo_reserva']}",
                  f"      minuta do modelo existe em {r['com_minuta']}; passa no laudo em {r['minuta_aprovada_no_laudo']}",
                  f"      por que reprova: {r['violacoes_nas_reprovadas']}",
                  f"      tamanho da minuta / original (mediana): {r['palavras_minuta_sobre_original_mediana']}",
                  f"      TRCC: minuta {r['trcc_minuta']} | entregue {r['trcc_entregue']}",
                  f"      Flesch: original {r['flesch_original']} | minuta {r['flesch_minuta']} | entregue {r['flesch_entregue']}",
                  f"      comando conjugado resolvido: minuta {r['cmd_conjugado_resolvido_minuta']} | entregue {r['cmd_conjugado_resolvido_entregue']}",
                  f"      questões com minuta aprovada em todas as rodadas: {r['questoes_com_minuta_aprovada_em_todas_as_rodadas']}"]
        # a diretiva do RAG muda a minuta?
        a = {(l["id"], l["rodada"]): l for l in linhas_m["sem_rag"] if l["minuta"]}
        b = {(l["id"], l["rodada"]): l for l in linhas_m["completo"] if l["minuta"]}
        comuns = sorted(set(a) & set(b))
        iguais = sum(a[k]["minuta"].strip() == b[k]["minuta"].strip() for k in comuns)
        par = {}
        for nome, f in (("minuta aprovada no laudo", lambda l: float(l["laudo"]["aprovado"])), ("TRCC da minuta", lambda l: l.get("trcc_minuta")),
                        ("Flesch da minuta", lambda l: l.get("flesch_minuta"))):
            pa = M.media_por_pergunta([l for l in linhas_m["sem_rag"] if l["minuta"]], f)
            pb = M.media_por_pergunta([l for l in linhas_m["completo"] if l["minuta"]], f)
            p = M.pareado(pa, pb, {})
            par[nome] = {"n": p["n"], "dif_media_ic95": p["dif_media_ic95"], "wilcoxon_p": p["wilcoxon_p"]}
        res[modelo]["completo_x_sem_rag"] = {"pares_com_minuta_nas_duas": len(comuns), "minuta_identica": iguais, "pareado": par}
        L += [f"  completo x sem_rag: pares com minuta nas duas {len(comuns)}; minuta idêntica em {iguais}"]
        L += [f"      completo - sem_rag, {k}: n={v['n']} dif={v['dif_media_ic95']} Wilcoxon p={v['wilcoxon_p']}" for k, v in par.items()]
        L.append("")
    destino = C.SAIDAS / "d_diagnostico"
    C.escrever_json(destino.with_suffix(".json"), res)
    destino.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def corrigido_gptoss() -> None:
    """Acrescenta think="low" e teto de 4.000 tokens ao corpo da chamada /api/generate do gpt-oss.

    O código do grupo não é alterado: o embrulho fica em urllib.request.urlopen, só nesta execução.
    """
    import urllib.request
    original = urllib.request.urlopen
    cont = Counter()

    def urlopen(req, *a, **k):
        if isinstance(req, urllib.request.Request) and req.full_url.endswith("/api/generate") and req.data:
            corpo = json.loads(req.data.decode("utf-8"))
            if str(corpo.get("model", "")).startswith("gpt-oss") and "options" in corpo:
                corpo["think"] = "low"
                corpo["options"]["num_predict"] = 4000
                req.data = json.dumps(corpo).encode("utf-8")
                cont["chamadas_corrigidas"] += 1
        return original(req, *a, **k)

    urllib.request.urlopen = urlopen
    C.SAIDAS = CORRIGIDO
    CORRIGIDO.mkdir(exist_ok=True)
    import teste_d
    try:
        teste_d.main(["--provedor", "ollama", "--modelo", "gpt-oss:20b", "--rodadas", "1"])
    finally:
        urllib.request.urlopen = original
    print(dict(cont), flush=True)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    {"analisar": analisar, "corrigido-gptoss": corrigido_gptoss}.get(acao, lambda: sys.exit("use: analisar | corrigido-gptoss"))()
