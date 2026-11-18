"""ablacao.py: o que muda no resultado quando cada peça do pipeline do Íris é desligada.

Pergunta que responde: "quanto cada peça (Extrator, RAG, laudo de escopo, modelo) contribui nas métricas
que o grupo já usa?". Roda o executor do grupo (iris.eval.executar:executar_sistema) sobre o Golden
Benchmark do grupo (data/golden_benchmark.json, 30 questões) e mede com as funções do grupo
(iris.eval.relatorio:metricas_sistema -> TRCC micro/macro, Flesch PT-BR antes/depois, comando conjugado;
iris.eval.metrics:verificar_aderencia_nivel -> SAEN; comparar_pareado -> Wilcoxon contra 'completo').

Configurações:
    completo                Extrator + busca RAG (bm25) + contexto + diretiva + Adaptador com modelo + laudo
    sem_rag                 igual, sem busca/contexto/diretiva (o Adaptador só recebe o catálogo)
    sem_extrator            igual ao completo, com trava genérica no lugar do Extrator
    sem_laudo_escopo        igual ao completo, mas o laudo de escopo sempre aprova (mostra o que o modelo
                            entregaria sem a guarda; o laudo real fica registrado)
    reserva_deterministica  provedor 'extractive': Extrator e Adaptador usam só as regras de reserva do grupo
    grupo_adaptador_benchmark  a função do próprio grupo (iris.agents.adapter_agent:adaptador_benchmark),
                            Extrator + Adaptador sem RAG, com o mesmo provedor da rodada
    identidade              iris.eval.executar:adaptador_identidade (devolve o enunciado; piso de adaptação,
                            teto de TRCC)

Na VPS o provedor é o stub 'eco' (determinístico): os números NÃO medem qualidade de modelo, só o encanamento
(se cada configuração roda, quanto cai na reserva, se o laudo aprova). No PC, --provedor ollama.

Uso:
    python ablacao.py                         # VPS, eco, nível 2
    python ablacao.py --provedor ollama       # PC, llama3:latest
    python ablacao.py --limite 5 --configs completo,sem_rag
Saídas: pacote/outputs/25-ablacao.txt e 25-ablacao.jsonl (números e ids);
        pacote/reports/pipeline/ablacao-<carimbo>/ (saídas do executor e rastros completos)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rastro_pipeline as RP  # noqa: E402

T = RP.T
CONFIGS = ["completo", "sem_rag", "sem_extrator", "sem_laudo_escopo", "reserva_deterministica",
           "grupo_adaptador_benchmark", "identidade"]


def _laudo_sempre_aprova(registro: list):
    """Troca verificar_escopo no módulo do Adaptador por um que guarda o laudo real e devolve aprovado."""
    import iris.agents.adapter_agent as aa

    original = aa.verificar_escopo

    def falso(*args, **kwargs):
        real = original(*args, **kwargs)
        registro.append(real.aprovado)
        return real.model_copy(update={"aprovado": True, "violacoes": []})

    aa.verificar_escopo = falso
    return lambda: setattr(aa, "verificar_escopo", original)


def montar_adaptador(config: str, cliente_padrao, cliente_reserva, nivel: int, pasta: Path, commit: str):
    """Devolve f(questao) no formato do executor do grupo e o arquivo de rastro desta configuração."""
    from iris.eval.executar import adaptador_identidade

    rastro_arq = pasta / f"rastro-{config}.jsonl"
    if rastro_arq.exists():
        rastro_arq.unlink()
    if config == "identidade":
        return adaptador_identidade, None
    if config == "grupo_adaptador_benchmark":
        from iris.agents.adapter_agent import adaptador_benchmark

        def f_grupo(q):
            os.environ["IRIS_ADAPTADOR_NIVEL"] = str(nivel)
            desfazer = T.instalar_cliente_nos_agentes(cliente_padrao)
            try:
                return adaptador_benchmark(q)
            finally:
                desfazer()

        return f_grupo, None

    cfg = {"caracteristica": RP.ID_COMANDOS_MULTIPLOS, "nivel": nivel, "k": 5,
           "usar_rag": config not in ("sem_rag",), "usar_extrator": config != "sem_extrator"}
    cliente = cliente_reserva if config == "reserva_deterministica" else cliente_padrao

    def f(q):
        r = T.Rastreador(f"ablacao-{config}", q.id, cliente.provider_name, T.nome_modelo(cliente), commit)
        cliente.rastreador = r
        desfazer = RP.instrumentar(r)
        laudos_reais: list = []
        if config == "sem_laudo_escopo":
            desfazer.append(_laudo_sempre_aprova(laudos_reais))
        try:
            out = RP.adaptar_questao(r, cliente, q.enunciado, cfg, q.disciplina, q.ano, q.id,
                                     trava_referencia=q.trava_curricular)
        finally:
            for d in reversed(desfazer):
                d()
            cliente.rastreador = None
            with rastro_arq.open("a", encoding="utf-8") as fh:
                for linha in r.linhas:
                    fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
        tokens = sum(l["tokens_entrada"] + l["tokens_saida"] for l in r.linhas if l["etapa"] in
                     ("extrator_curricular", "agente_adaptador", "diretiva_substituta_arnes"))
        return {
            "adaptado": out["adaptado"],
            "contextos": out["contextos"],
            "chunk_ids": out["chunk_ids"],
            "escopo_aprovado": out["escopo_aprovado"],
            "escopo_real_aprovado": laudos_reais[0] if laudos_reais else out["escopo_aprovado"],
            "used_fallback": out["used_fallback"],
            "motivo_fallback": out["motivo_fallback"],
            "extrator_fallback": out.get("extrator_fallback"),
            "adaptacao_aplicada": out["adaptacao_aplicada"],
            "trava_recall_extrator": out.get("trava_recall"),
            "citacoes": out.get("citacoes"),
            "tokens": tokens,
            "ciclo_ms": out["ciclo"]["total_ms"],
            "dentro_rnf07": out["ciclo"]["dentro_do_limite"],
        }

    return f, rastro_arq


def _media(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 4) if v else None


def _pct(v):
    v = [bool(x) for x in v if x is not None]
    return round(100 * sum(v) / len(v), 1) if v else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provedor", default="eco", choices=["eco", "extractive", "ollama"])
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--nivel", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--limite", type=int, default=None, help="só as N primeiras questões (teste rápido)")
    ap.add_argument("--configs", default=",".join(CONFIGS))
    args = ap.parse_args(argv)

    from iris.eval.benchmark import carregar_golden_benchmark
    from iris.eval.executar import executar_sistema, ler_saidas
    from iris.eval.metrics import verificar_aderencia_nivel
    from iris.eval.relatorio import comparar_pareado, metricas_sistema

    commit = T.commit_grupo()
    questoes = carregar_golden_benchmark(T.GRUPO / "data" / "golden_benchmark.json")
    if args.limite:
        questoes = questoes[: args.limite]
    cliente = T.criar_cliente(args.provedor, args.modelo)
    reserva = T.criar_cliente("extractive")
    if args.provedor == "ollama":
        print("aquecendo o modelo:", cliente.warmup())
    pasta = T.REPORTS / f"ablacao-{T.carimbo()}-{args.provedor}-n{args.nivel}"
    pasta.mkdir(parents=True, exist_ok=True)

    configs = [c for c in args.configs.split(",") if c]
    metricas, linhas_jsonl = {}, []
    for config in configs:
        f, _ = montar_adaptador(config, cliente, reserva, args.nivel, pasta, commit)
        chamadas_antes = cliente.chamadas + reserva.chamadas
        res = executar_sistema(f, questoes, config, pasta=pasta, refazer=True, progresso=None)
        saidas = ler_saidas(pasta / f"{config}.jsonl")
        m = metricas_sistema(questoes, saidas)
        validas = [saidas[q.id] for q in questoes if q.id in saidas and not saidas[q.id].get("erro")]
        saen = [verificar_aderencia_nivel(args.nivel, s["adaptado"])["valido"] for s in validas]
        alterou = [s["adaptado"].strip() != q.enunciado.strip() for q in questoes for s in [saidas.get(q.id)] if s and not s.get("erro")]
        m_extra = {
            "executadas": res["executadas"], "falhas": res["falhas"],
            "pct_alterou_texto": _pct(alterou),
            "pct_saen_nivel": _pct(saen),
            "pct_reserva": _pct([s.get("used_fallback") for s in validas]),
            "pct_escopo_aprovado_final": _pct([s.get("escopo_aprovado") for s in validas]),
            "pct_escopo_aprovado_real": _pct([s.get("escopo_real_aprovado", s.get("escopo_aprovado")) for s in validas]),
            "pct_extrator_reserva": _pct([s.get("extrator_fallback") for s in validas]),
            "trava_recall_extrator_media": _media([s.get("trava_recall_extrator") for s in validas]),
            "tokens_media": _media([s.get("tokens") for s in validas]),
            "ciclo_ms_media": _media([s.get("ciclo_ms") for s in validas]),
            "chamadas_modelo": cliente.chamadas + reserva.chamadas - chamadas_antes,
        }
        metricas[config] = {**m, **m_extra}
        for q in questoes:
            s = saidas.get(q.id, {})
            linhas_jsonl.append({
                "config": config, "id": q.id, "provedor": args.provedor, "nivel": args.nivel, "commit_grupo": commit,
                "erro": s.get("erro"), "trcc": m["trcc_por_questao"].get(q.id),
                "ausentes": m["ausentes_por_questao"].get(q.id, []),
                "alterou_texto": (s.get("adaptado", "").strip() != q.enunciado.strip()) if s and not s.get("erro") else None,
                "used_fallback": s.get("used_fallback"), "motivo_fallback": s.get("motivo_fallback"),
                "escopo_aprovado": s.get("escopo_aprovado"), "escopo_real_aprovado": s.get("escopo_real_aprovado"),
                "chunk_ids": s.get("chunk_ids", []), "tokens": s.get("tokens"), "latencia_s": s.get("latencia_s"),
            })
        t = m["trcc"] or {}
        print(f"{config:<26} ok={res['executadas']:>2} falhas={res['falhas']} TRCC micro={t.get('trcc_micro')} "
              f"alterou={m_extra['pct_alterou_texto']}% reserva={m_extra['pct_reserva']}% "
              f"escopo_real={m_extra['pct_escopo_aprovado_real']}%")

    pareado = {}
    if "completo" in metricas:
        for c in configs:
            if c != "completo":
                pareado[c] = comparar_pareado(metricas[c], metricas["completo"])

    L = ["# 25 - Ablação do pipeline do Íris sobre o Golden Benchmark do grupo", "",
         f"commit do grupo: {commit} | provedor: {args.provedor} | modelo: {T.nome_modelo(cliente)} | nível {args.nivel} | "
         f"característica {RP.ID_COMANDOS_MULTIPLOS} | gerado em {T.agora_iso()}",
         f"questões: {len(questoes)} (peso de 1 questão = {1 / len(questoes):.1%}); benchmark com status 'rascunho' "
         f"(sem revisão pedagógica); RAG só bm25 sobre chunks.jsonl sha16={T.sha16(T.CHUNKS)}", ""]
    if args.provedor != "ollama":
        L += ["AVISO: provedor determinístico. Estes números NÃO medem qualidade de modelo; medem o encanamento:",
              "se cada configuração roda nas 30 questões, quanto cai na reserva, se o laudo aprova, e como as",
              "métricas do grupo se comportam com o andaime por regras. A comparação que importa roda no PC.", ""]
    L += ["## Métricas do grupo por configuração", "",
          "| config | saídas | TRCC micro | TRCC macro | % questões TRCC>=0,95 | Flesch antes->depois | cmd. conjugado % antes->depois | alterou % | SAEN nível % |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in configs:
        m = metricas[c]
        t = m["trcc"] or {}
        L.append(f"| {c} | {m['n_com_saida']}/{m['n_questoes_benchmark']} | {t.get('trcc_micro')} | {t.get('trcc_macro')} | "
                 f"{t.get('pct_questoes_aprovadas')} | {m['flesch_antes']}->{m['flesch_depois']} | "
                 f"{m['comando_conjugado_antes_pct']}->{m['comando_conjugado_depois_pct']} | {m['pct_alterou_texto']} | {m['pct_saen_nivel']} |")
    L += ["", "## Operação (o que cada peça fez)", "",
          "| config | reserva do Adaptador % | escopo aprovado (final) % | escopo aprovado (laudo real) % | Extrator na reserva % | recall da trava pelo Extrator | chamadas ao provedor | tokens/questão | ciclo ms/questão |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in configs:
        m = metricas[c]
        L.append(f"| {c} | {m['pct_reserva']} | {m['pct_escopo_aprovado_final']} | {m['pct_escopo_aprovado_real']} | "
                 f"{m['pct_extrator_reserva']} | {m['trava_recall_extrator_media']} | {m['chamadas_modelo']} | "
                 f"{m['tokens_media']} | {m['ciclo_ms_media']} |")
    if pareado:
        L += ["", "## TRCC por questão contra 'completo' (Wilcoxon pareado do grupo)", "",
              "| config | pares | média config | média completo | p-valor | nota |", "|---|---|---|---|---|---|"]
        for c, p in pareado.items():
            L.append(f"| {c} | {p['n_pares']} | {p['media_alvo']} | {p['media_referencia']} | {p['p_valor']} | {p['nota']} |")
    L += ["", "## Leitura", "",
          "- TRCC alto com 'identidade' é esperado: devolver o enunciado retém tudo e não adapta nada. TRCC sozinho não",
          "  separa adaptação boa de ausência de adaptação; ler junto com 'alterou %' e 'SAEN nível %'.",
          "- 'sem_laudo_escopo' só difere de 'completo' quando o modelo erra o escopo; com provedor determinístico os",
          "  dois tendem a coincidir. A coluna 'laudo real' mostra quantas saídas a guarda teria barrado.",
          "- Faithfulness (RAGAS) não foi medida: o grupo mede com juiz LLM (iris.eval.faithfulness) e isso exige modelo.",
          "- Com o stub 'eco', 'completo' e 'sem_rag' coincidem porque o stub ignora a diretiva; a diferença entre",
          "  eles só aparece com modelo de verdade. O stub também numera questões de comando único (o andaime por",
          "  regras do grupo não numera), por isso 'alterou %' do eco passa o da reserva no nível 2: é artefato do stub."]
    texto = "\n".join(L) + "\n"
    print("\n" + texto)
    (T.OUTPUTS / "25-ablacao.txt").write_text(texto, encoding="utf-8")
    resumo = {"tipo": "resumo", "commit_grupo": commit, "provedor": args.provedor, "modelo": T.nome_modelo(cliente),
              "nivel": args.nivel, "n_questoes": len(questoes), "gerado_em": T.agora_iso(),
              "metricas": {c: {k: v for k, v in m.items() if k not in ("trcc_por_questao", "ausentes_por_questao")}
                           for c, m in metricas.items()},
              "pareado_contra_completo": pareado}
    T.escrever_jsonl(T.OUTPUTS / "25-ablacao.jsonl", [resumo] + linhas_jsonl)
    print(f"gravado: {T.OUTPUTS / '25-ablacao.txt'} e .jsonl; saídas e rastros em {pasta}")


if __name__ == "__main__":
    main()
