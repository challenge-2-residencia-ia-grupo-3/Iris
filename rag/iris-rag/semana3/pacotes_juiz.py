"""pacotes_juiz.py: monta os pacotes cegos para o juiz (humano ou modelo) em semana3/juiz/.

Cada linha de um lote = uma resposta, com id cego (não revela teste nem modelo), a pergunta, os trechos que a
busca trouxe (com texto) e a resposta dividida em frases numeradas. As respostas de A, B, C e D de todos os
modelos gerados até agora entram misturadas, embaralhadas com semente fixa, em lotes de ~40.
A chave para desembaralhar fica em juiz/chave.json (não entregar ao juiz).
30 respostas sorteadas (misturando condições) vão para juiz/ficha-humana.jsonl.

Para A, os trechos mostrados são os que a busca teria trazido (o modelo não os viu); para C, os que o modelo
recebeu; para B, os próprios trechos da resposta. Antes de mostrar a resposta de C ao juiz, as marcas [Tn]
ficam como estão (o juiz precisa saber qual trecho foi citado). A de A não tem marcas.

Uso: python3 semana3/pacotes_juiz.py   (rodar de novo quando chegarem as respostas do Llama, do PC)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

import comum as C

TAM_LOTE = 40
N_FICHA = 30


def _trechos(ids_textos: list[dict]) -> list[dict]:
    return [{"ref": f"T{i}", "documento": t["titulo"], "pagina": t.get("pagina"), "idioma": t.get("idioma"),
             "tipo_de_fonte": t.get("tipo_evidencia"), "texto": t["trecho"]} for i, t in enumerate(ids_textos, 1)]


def itens_ac_b(busca: dict) -> list[dict]:
    itens = []
    for arq in sorted(C.SAIDAS.glob("respostas_[AC]_*.jsonl")):
        vistos = {}
        for l in C.ler_jsonl(arq):
            if not l.get("erro") and (l.get("resposta") or "").strip():
                vistos[(l["id"], l["repeticao"])] = l
        for l in vistos.values():
            itens.append({"tipo_tarefa": "resposta_ao_professor", "teste": l["teste"], "modelo": l["modelo"],
                          "id_pergunta": l["id"], "repeticao": l["repeticao"], "pergunta": l["pergunta"],
                          "trechos": _trechos(busca[l["id"]]["trechos_top5"]), "resposta": l["resposta"]})
    b = C.SAIDAS / "respostas_B.jsonl"
    for l in C.ler_jsonl(b):
        n = 1 if l["variante"] == "top1" else 3
        ts = busca[l["id"]]["trechos_top5"][:n]
        # a resposta de B é o próprio texto dos trechos; o juiz avalia utilidade e se responde à pergunta
        resposta = "\n".join(t["trecho"] for t in ts)
        itens.append({"tipo_tarefa": "resposta_ao_professor", "teste": "B", "modelo": f"busca-{l['variante']}",
                      "id_pergunta": l["id"], "repeticao": 1, "pergunta": l["pergunta"],
                      "trechos": _trechos(ts), "resposta": resposta, "resposta_eh_trecho_cru": True})
    return itens


def itens_d() -> list[dict]:
    itens = []
    for arq in sorted(C.SAIDAS.glob("respostas_D_*.jsonl")):
        vistos = {}
        for l in C.ler_jsonl(arq):
            if not l.get("erro") and (l.get("adaptado") or "").strip():
                vistos[(l["config"], l["id"], l["repeticao"])] = l
        for l in vistos.values():
            itens.append({"tipo_tarefa": "adaptacao_de_questao", "teste": "D", "modelo": l["modelo"],
                          "config": l["config"], "id_pergunta": l["id"], "repeticao": l["repeticao"],
                          "disciplina": l["disciplina"], "ano": l["ano"], "nivel": l["nivel"],
                          "enunciado_original": l["enunciado"], "resposta": l["adaptado"]})
    return itens


def linha_cega(it: dict, id_cego: str) -> dict:
    fr = C.frases(it["resposta"]) if not it.get("resposta_eh_trecho_cru") else None
    if it["tipo_tarefa"] == "adaptacao_de_questao":
        return {"id_cego": id_cego, "tipo_tarefa": it["tipo_tarefa"], "disciplina": it["disciplina"], "ano": it["ano"],
                "nivel_de_apoio_pedido": it["nivel"], "enunciado_original": it["enunciado_original"],
                "adaptacao": it["resposta"]}
    out = {"id_cego": id_cego, "tipo_tarefa": it["tipo_tarefa"], "pergunta": it["pergunta"],
           "trechos_da_base": it["trechos"], "resposta": it["resposta"]}
    if fr is not None:
        out["frases"] = [{"n": i, "texto": f} for i, f in enumerate(fr, 1)]
    else:
        out["frases"] = None
        out["observacao"] = "A resposta é um trecho de documento devolvido sem reescrita: avaliar só a resposta inteira."
    return out


def agrupar_repeticoes_iguais(itens: list[dict]) -> list[dict]:
    """Repetições com texto idêntico (mesmo teste, modelo, config e pergunta) vão ao juiz uma vez só.

    O julgamento vale para todas as repetições listadas em 'repeticoes' na chave. Textos diferentes
    entre repetições viram itens separados. Configs diferentes nunca se juntam (são condições).
    """
    grupos: dict[tuple, dict] = {}
    for it in itens:
        k = (it["tipo_tarefa"], it["teste"], it["modelo"], it.get("config") or "", it["id_pergunta"], it["resposta"])
        if k in grupos:
            grupos[k]["repeticoes"].append(it["repeticao"])
        else:
            grupos[k] = it | {"repeticoes": [it["repeticao"]]}
    return list(grupos.values())


def _chave_item(it: dict) -> str:
    return f"{it['teste']}|{it['modelo']}|{it.get('config') or ''}|{it['id_pergunta']}|{it['repeticao']}"


def main() -> None:
    import argparse
    import random

    ap = argparse.ArgumentParser()
    ap.add_argument("--do-zero", action="store_true",
                    help="apaga lotes e chave e refaz tudo (só antes de qualquer julgamento)")
    args = ap.parse_args()

    busca = {l["id"]: l for l in C.ler_jsonl(C.TRECHOS_BUSCA)}
    itens = itens_ac_b(busca) + itens_d()
    if not itens:
        raise SystemExit("nenhuma resposta em saidas/")
    itens.sort(key=_chave_item)
    itens = agrupar_repeticoes_iguais(itens)
    C.JUIZ.mkdir(parents=True, exist_ok=True)
    arq_chave = C.JUIZ / "chave.json"
    if args.do_zero:
        for velho in [*C.JUIZ.glob("*lote-*.jsonl"), arq_chave, C.JUIZ / "ficha-humana.jsonl"]:
            if velho.exists():
                velho.unlink()
    # Rodar de novo NÃO muda o que já foi para o juiz: respostas já na chave mantêm id e lote; só as novas
    # (por exemplo, as do Llama vindas do PC) ganham ids novos, em lotes novos.
    antiga = json.loads(arq_chave.read_text(encoding="utf-8"))["chave"] if arq_chave.exists() else {}
    ja = {_chave_item(v | {"id_pergunta": v["id_pergunta"]}): k for k, v in antiga.items()}
    chave = dict(antiga)
    n_global = max([int(k[1:]) for k in antiga] or [0])
    novos_lotes = Counter()
    for prefixo, tipo in (("resp", "resposta_ao_professor"), ("adapt", "adaptacao_de_questao")):
        novos = [x for x in itens if x["tipo_tarefa"] == tipo and _chave_item(x) not in ja]
        ordem = C.embaralhar(novos, C.SEMENTE + n_global)
        ultimo = max([int(v["lote"].rsplit("-", 1)[1]) for v in antiga.values() if v["lote"].startswith(prefixo)] or [0])
        for i, it in enumerate(ordem):
            n_global += 1
            id_cego = f"R{n_global:04d}"
            lote = f"{prefixo}-lote-{ultimo + i // TAM_LOTE + 1:02d}"
            chave[id_cego] = ({k: it.get(k) for k in ("teste", "modelo", "config", "id_pergunta", "repeticao")}
                              | {"repeticoes": it.get("repeticoes", [it["repeticao"]]), "lote": lote})
            C.acrescentar_jsonl(C.JUIZ / f"{lote}.jsonl", linha_cega(it, id_cego))
            novos_lotes[lote] += 1
    C.escrever_json(arq_chave, {"semente": C.SEMENTE, "gerado_em": C.agora_iso(), "n": len(chave),
                                "aviso": "NÃO entregar ao juiz.", "chave": chave})

    # ficha humana: 30 sorteadas com semente, misturando as condições (rodízio entre teste+modelo+config).
    # Só é sorteada uma vez; se já existir, não muda.
    ficha = C.JUIZ / "ficha-humana.jsonl"
    if not ficha.exists():
        por_cond: dict[str, list[str]] = {}
        for idc, k in sorted(chave.items()):
            por_cond.setdefault(f"{k['teste']}|{k['modelo']}|{k.get('config') or ''}", []).append(idc)
        conds = sorted(por_cond)
        rng = random.Random(C.SEMENTE + 1)
        for c in conds:
            rng.shuffle(por_cond[c])
        sorteados: list[str] = []
        while len(sorteados) < min(N_FICHA, len(chave)):
            for c in conds:
                if por_cond[c] and len(sorteados) < N_FICHA:
                    sorteados.append(por_cond[c].pop())
        rng.shuffle(sorteados)
        linhas_por_id = {l["id_cego"]: l for p in sorted(C.JUIZ.glob("*lote-*.jsonl")) for l in C.ler_jsonl(p)}
        C.escrever_jsonl(ficha, [linhas_por_id[i] | {"conferencia_humana": None} for i in sorteados])
        print(f"ficha humana: {len(sorteados)} respostas sorteadas")

    resumo = Counter(f"{k['teste']}|{k['modelo']}|{k.get('config') or ''}" for k in chave.values())
    print(f"{len(chave)} respostas na chave; novas nesta rodada: {sum(novos_lotes.values())} em {len(novos_lotes)} lotes")
    for c, n in sorted(resumo.items()):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
