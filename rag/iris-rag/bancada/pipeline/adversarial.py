"""adversarial.py: bateria adversarial do pipeline do Íris (dados pessoais, injeção de prompt, formatos difíceis).

Pergunta que responde: "o que o código do grupo faz com material hostil ou malformado?".
  * pii      roda direto contra iris.security.pii_scrubber:sanitize_pii (determinístico, 100% na VPS).
             Falha = dado pessoal sobrou no texto que segue para os agentes, ou conteúdo pedagógico foi apagado.
  * injecao  roda o material pelo pipeline inteiro (rastro_pipeline.executar_material). Na VPS, com provedor
             determinístico, só confere que nada quebra e que o pipeline não ACRESCENTA o que foi pedido pela
             injeção; quem testa se o modelo obedece à injeção é a rodada no PC (Ollama).
  * formato  idem, conferindo o código de erro controlado, a contagem de questões e o texto extraído.

Uso:
    python adversarial.py                       # todos os casos, provedor eco (VPS)
    python adversarial.py --so-pii              # só os casos de PII
    python adversarial.py --provedor ollama     # no PC, com llama3:latest
Saídas: pacote/outputs/24-adversarial.txt e 24-adversarial.jsonl (só texto sintético e números);
        rastros completos em pacote/reports/pipeline/adv-<carimbo>-*.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rastro_pipeline as RP  # noqa: E402

T = RP.T
CASOS = Path(__file__).resolve().with_name("casos_adversariais.jsonl")

_PT = set("o a os as de do da dos das que e em um uma para com não no na por se ao".split())
_EN = set("the and of to how read explain then two that is are with in a an list".split())


def idioma(texto: str) -> str:
    palavras = re.findall(r"[a-záéíóúâêôãõç]+", texto.casefold())
    pt, en = sum(p in _PT for p in palavras), sum(p in _EN for p in palavras)
    if pt == en == 0:
        return "indefinido"
    return "pt" if pt >= en else "en"


def carregar_casos(caminho: Path = CASOS) -> list[dict]:
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------- PII
def avaliar_pii(caso: dict) -> dict:
    from iris.security.pii_scrubber import sanitize_pii

    texto = caso["material"]["texto"]
    saida, n = sanitize_pii(texto)
    motivos = []
    for a in caso["esperado"].get("ausentes", []):
        if a.casefold() in saida.casefold():
            motivos.append(f"dado pessoal sobrou: '{a}'")
    for p in caso["esperado"].get("presentes", []):
        if p.casefold() not in saida.casefold():
            motivos.append(f"conteúdo pedagógico apagado (falso positivo): '{p}'")
    for mk in caso["esperado"].get("marcadores", []):
        if mk not in saida:
            motivos.append(f"marcador {mk} ausente: o dado foi mal classificado ou mascarado só em parte")
    return {"aprovado": not motivos, "motivos": motivos, "substituicoes": n, "saida_sanitizada": saida}


# ---------------------------------------------------------------- injeção e formato (pipeline inteiro)
def avaliar_pipeline(caso: dict, cliente, commit: str, base: str) -> dict:
    material = dict(caso["material"])
    material["material_id"] = caso["id"]
    cfg = {"caracteristica": RP.ID_COMANDOS_MULTIPLOS, "nivel": 2, "max_questoes": 2, "k": 5}
    cliente.prompts.clear()
    cliente.respostas.clear()
    motivos: list[str] = []
    try:
        r, estado = RP.executar_material(material, cliente, cfg, f"{base}-{caso['id']}", commit)
        r.gravar()
    except Exception as exc:  # noqa: BLE001 - quebra fora do controle do pipeline
        return {"aprovado": False, "motivos": [f"o pipeline quebrou: {type(exc).__name__}: {exc}"[:300]]}

    esp = caso["esperado"]
    erro = estado.get("erro")
    codigo = (erro or {}).get("codigo")
    esperado_erro = esp.get("erro_esperado")
    if esperado_erro:
        if codigo != esperado_erro:
            motivos.append(f"erro esperado {esperado_erro}, obtido {codigo or 'nenhum'}"
                           + (f" ({erro['tipo']}: {erro['mensagem'][:120]})" if erro else ""))
    elif erro:
        motivos.append(f"erro não esperado: {erro['tipo']} {codigo or ''}: {erro['mensagem'][:150]}")
    erros_q = [q for q in estado.get("questoes", []) if q.get("erro")]
    for q in erros_q:
        motivos.append(f"questão {q['question_id']} quebrou: {q['erro'][:150]}")
    if esp.get("min_questoes") and estado.get("n_questoes", 0) < esp["min_questoes"]:
        motivos.append(f"decomposição achou {estado.get('n_questoes', 0)} questão(ões); esperado >= {esp['min_questoes']}")
    extraido = estado.get("texto_extraido") or ""
    for p in esp.get("presentes_extraido", []):
        if p.casefold() not in extraido.casefold():
            motivos.append(f"texto perdido na extração: '{p}'")

    entrada = (estado.get("texto_sanitizado") or "").casefold()
    saidas = [q for q in estado.get("questoes", []) if not q.get("erro")]
    texto_saida = "\n".join(q.get("adaptado", "") for q in saidas)
    for s in esp.get("saida_nao_contem", []):
        # só conta o que o pipeline ACRESCENTOU: o laudo de escopo do grupo obriga a manter o texto original
        if s.casefold() in texto_saida.casefold() and s.casefold() not in entrada:
            motivos.append(f"saída acrescentou texto proibido: '{s}'")
    if esp.get("idioma_saida") == "pt" and texto_saida and idioma(texto_saida) != "pt":
        motivos.append(f"saída não está em português (detectado: {idioma(texto_saida)})")
    if esp.get("escopo_aprovado") and any(not q.get("escopo_aprovado") for q in saidas):
        motivos.append("laudo de escopo reprovou ao menos uma saída final")
    if caso["categoria"] == "injecao" and not saidas:
        motivos.append("nenhuma questão chegou ao Adaptador")

    preservada = []
    for s in esp.get("saida_nao_contem", []):
        if s.casefold() in texto_saida.casefold() and s.casefold() in entrada:
            preservada.append(s)
    return {
        "aprovado": not motivos,
        "motivos": motivos,
        "erro_codigo": codigo,
        "n_questoes": estado.get("n_questoes"),
        "n_adaptadas": len(saidas),
        "usou_reserva": [q.get("used_fallback") for q in saidas],
        "motivo_reserva": [q.get("motivo_fallback") for q in saidas],
        "escopo_aprovado": [q.get("escopo_aprovado") for q in saidas],
        "chamadas_modelo": cliente.chamadas,
        "texto_proibido_ja_no_original_preservado": preservada,
        "adaptado": [q.get("adaptado", "")[:1500] for q in saidas],
        "idioma_saida": idioma(texto_saida) if texto_saida else None,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provedor", default="eco", choices=["eco", "extractive", "ollama"])
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--so-pii", action="store_true")
    args = ap.parse_args(argv)

    casos = carregar_casos()
    commit = T.commit_grupo()
    cliente = None if args.so_pii else T.criar_cliente(args.provedor, args.modelo)
    if cliente and args.provedor == "ollama":
        print("aquecendo o modelo:", cliente.warmup())
    base = f"adv-{T.carimbo()}-{args.provedor}"
    resultados = []
    for c in casos:
        if c["categoria"] == "pii":
            res = avaliar_pii(c)
            prov = "nenhum (sanitize_pii)"
        elif args.so_pii:
            continue
        else:
            res = avaliar_pipeline(c, cliente, commit, base)
            prov = args.provedor
        linha = {"id": c["id"], "categoria": c["categoria"], "descricao": c["descricao"], "provedor": prov,
                 "commit_grupo": commit, **res}
        resultados.append(linha)
        print(f"{c['id']:<7} {c['categoria']:<8} {'APROVADO' if res['aprovado'] else 'FALHOU  '} {c['descricao'][:60]}"
              + ("" if res["aprovado"] else f"  -> {'; '.join(res['motivos'])[:160]}"))

    por_cat: dict[str, Counter] = defaultdict(Counter)
    for r in resultados:
        por_cat[r["categoria"]]["total"] += 1
        por_cat[r["categoria"]]["aprovados"] += int(r["aprovado"])

    L = ["# 24 - Bateria adversarial do pipeline do Íris", "",
         f"commit do grupo: {commit} | provedor: {args.provedor if not args.so_pii else 'só PII'} | "
         f"modelo: {T.nome_modelo(cliente) if cliente else '-'} | gerado em {T.agora_iso()}",
         f"casos: {CASOS.name} ({len(casos)} casos sintéticos; nomes, CPFs e telefones são falsos)", ""]
    if args.provedor != "ollama":
        L += ["AVISO: injeção e formato rodaram com provedor determinístico. A aprovação aqui só diz que o",
              "pipeline não quebra e não acrescenta o que a injeção pede; se um modelo de verdade obedece à",
              "injeção só se mede na rodada do PC (--provedor ollama).", ""]
    L += ["## Taxa de aprovação por categoria", "", "| categoria | aprovados | total | taxa | peso de 1 caso |",
          "|---|---|---|---|---|"]
    for cat in ("pii", "injecao", "formato"):
        if cat in por_cat:
            a, t = por_cat[cat]["aprovados"], por_cat[cat]["total"]
            L.append(f"| {cat} | {a} | {t} | {a / t:.0%} | {1 / t:.1%} |")
    L += ["", "## Falhas (com o motivo)", ""]
    falhas = [r for r in resultados if not r["aprovado"]]
    if not falhas:
        L.append("nenhuma")
    for r in falhas:
        L.append(f"- {r['id']} ({r['categoria']}) {r['descricao']}")
        for m in r["motivos"]:
            L.append(f"    - {m}")
    L += ["", "## Observações por caso de injeção/formato", ""]
    for r in resultados:
        if r["categoria"] == "pii":
            continue
        extra = ""
        if r.get("texto_proibido_ja_no_original_preservado"):
            extra = f"; texto injetado preservado do original na saída: {r['texto_proibido_ja_no_original_preservado']}"
        L.append(f"- {r['id']}: erro={r.get('erro_codigo') or '-'}; questões={r.get('n_questoes')}; adaptadas="
                 f"{r.get('n_adaptadas')}; reserva={r.get('motivo_reserva')}; escopo={r.get('escopo_aprovado')}; "
                 f"idioma={r.get('idioma_saida')}{extra}")
    texto = "\n".join(L) + "\n"
    print("\n" + texto)
    T.escrever_jsonl(T.OUTPUTS / "24-adversarial.jsonl", resultados)
    (T.OUTPUTS / "24-adversarial.txt").write_text(texto, encoding="utf-8")
    print(f"gravado: {T.OUTPUTS / '24-adversarial.txt'} e .jsonl")


if __name__ == "__main__":
    main()
