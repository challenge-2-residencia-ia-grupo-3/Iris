"""teste_d.py: aderência ao produto. O Adaptador do Íris nas 30 questões do Golden Benchmark do grupo,
config 'completo' (Extrator + RAG bm25 + diretiva + Adaptador + laudo) x 'sem_rag' (mesmo pipeline sem busca).

Reaproveita o arnês da bancada (bancada/pipeline/ablacao.py:montar_adaptador e rastro_pipeline.py), com o
código do grupo sem alteração. Métricas do grupo: TRCC (avaliar_trcc via metricas_sistema), comando conjugado
(antes/depois), Flesch PT-BR (antes/depois), aderência ao nível (verificar_aderencia_nivel), laudo de escopo,
taxa de reserva; e o tempo do ciclo contra o RNF-07.

Provedor:
  groq   só com BANCADA_PERMITIR_EXTERNO=benchmark-publico (as 30 questões são públicas, sem dado de aluno);
         a liberação fica registrada em cada linha de saída.
  ollama no PC (llama3.1:8b), igual à produção.

Uso:
  BANCADA_PERMITIR_EXTERNO=benchmark-publico python semana3/teste_d.py --provedor groq --modelo qwen/qwen3.8-27b
  python semana3/teste_d.py --provedor ollama --modelo llama3.1:8b
Saídas: saidas/respostas_D_<apelido>.jsonl (uma linha por questão, config e rodada) e
        saidas/d_execucao/<apelido>-r<n>/ (saídas do executor do grupo e rastros).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import comum as C

sys.path.insert(0, str(C.IRIS_RAG / "bancada" / "pipeline"))
import ablacao  # noqa: E402  (carrega trace.py e põe o código do grupo no sys.path)

T = ablacao.T
CONFIGS = ["completo", "sem_rag"]


def apelido_de(provedor: str, modelo: str) -> str:
    for ap, (prov, mid) in C.MODELOS.items():
        if prov == provedor and mid == modelo:
            return ap
    if provedor == "groq" and modelo == "qwen/qwen3.8-27b":
        return "qwen3.8-27b"
    return f"{provedor}-{modelo}".replace("/", "_").replace(":", "_")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provedor", required=True, choices=["groq", "ollama", "eco"])
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--nivel", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--rodadas", type=int, default=1, help="até qual rodada")
    ap.add_argument("--rodada-inicial", type=int, default=1)
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args(argv)

    from iris.eval.benchmark import carregar_golden_benchmark
    from iris.eval.executar import executar_sistema, ler_saidas
    from iris.eval.metrics import verificar_aderencia_nivel
    from iris.eval.readability import analyze_question

    if args.provedor == "groq" and not T.externo_liberado():
        raise SystemExit("Groq recusado: defina BANCADA_PERMITIR_EXTERNO=benchmark-publico (só benchmark público).")
    commit_grupo = T.commit_grupo()
    commit = C.commit_atual()
    questoes = carregar_golden_benchmark(T.GRUPO / "data" / "golden_benchmark.json")
    if args.limite:
        questoes = questoes[: args.limite]
    cliente = T.criar_cliente(args.provedor, args.modelo)
    reserva = T.criar_cliente("extractive")
    modelo_efetivo = T.nome_modelo(cliente)
    apelido = apelido_de(args.provedor, modelo_efetivo)
    if args.provedor == "ollama":
        print("aquecendo o modelo:", cliente.warmup(), flush=True)
    liberacao = os.environ.get(T.ENV_LIBERACAO_EXTERNA) if args.provedor == "groq" else None
    destino = C.SAIDAS / f"respostas_D_{apelido}.jsonl"
    ja = {(l["config"], l["id"], l["repeticao"]) for l in C.ler_jsonl(destino) if not l.get("erro")}

    for rodada in range(args.rodada_inicial, args.rodadas + 1):
        pasta = C.SAIDAS / "d_execucao" / f"{apelido}-r{rodada}"
        pasta.mkdir(parents=True, exist_ok=True)
        for config in CONFIGS:
            f, _ = ablacao.montar_adaptador(config, cliente, reserva, args.nivel, pasta, commit_grupo)
            # o executor do grupo retoma pelas questões já gravadas em <pasta>/<config>.jsonl
            res = executar_sistema(f, questoes, config, pasta=pasta, refazer=False,
                                   progresso=lambda m, c=config, r=rodada: print(f"D {apelido} r{r} {c}: {m}", flush=True))
            saidas = ler_saidas(pasta / f"{config}.jsonl")
            for q in questoes:
                if (config, q.id, rodada) in ja or q.id not in saidas:
                    continue
                s = saidas[q.id]
                ok = not s.get("erro") and s.get("adaptado")
                antes = analyze_question(q.id, q.enunciado)
                depois = analyze_question(q.id, s["adaptado"]) if ok else None
                from iris.eval.trcc import avaliar_trcc
                tr = avaliar_trcc(q.trava_curricular, s["adaptado"]) if ok else None
                C.acrescentar_jsonl(destino, {
                    "teste": "D", "config": config, "id": q.id, "repeticao": rodada, "disciplina": q.disciplina,
                    "ano": q.ano, "enunciado": q.enunciado, "adaptado": s.get("adaptado"), "erro": s.get("erro"),
                    "provedor": args.provedor, "modelo": apelido, "id_modelo": modelo_efetivo, "nivel": args.nivel,
                    "liberacao_externa": liberacao, "dado_de_aluno": False,
                    "commit": commit, "commit_grupo": commit_grupo, "data_hora": C.agora_iso(),
                    "trcc": None if tr is None else tr.trcc, "trcc_ausentes": None if tr is None else list(tr.ausentes),
                    "flesch_antes": antes.flesch, "flesch_depois": None if depois is None else depois.flesch,
                    "cmd_conjugados_antes": antes.n_conjugated_commands,
                    "cmd_conjugados_depois": None if depois is None else depois.n_conjugated_commands,
                    "aderencia_nivel": None if not ok else bool(verificar_aderencia_nivel(args.nivel, s["adaptado"])["valido"]),
                    "alterou_texto": None if not ok else s["adaptado"].strip() != q.enunciado.strip(),
                    "escopo_aprovado": s.get("escopo_aprovado"), "reserva": s.get("used_fallback"),
                    "motivo_reserva": s.get("motivo_fallback"), "extrator_reserva": s.get("extrator_fallback"),
                    "chunk_ids": s.get("chunk_ids", []), "citacoes_diretiva": s.get("citacoes"),
                    "tokens": s.get("tokens"), "ciclo_ms": s.get("ciclo_ms"), "dentro_rnf07": s.get("dentro_rnf07"),
                    "latencia_s": s.get("latencia_s")})
            print(f"D {apelido} r{rodada} {config}: ok={res['executadas']} falhas={res['falhas']}", flush=True)
    print("fim", flush=True)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
