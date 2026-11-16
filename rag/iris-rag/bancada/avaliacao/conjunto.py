"""conjunto.py: conjunto de avaliação VERSIONADO do pipeline do Íris, com nota por commit.

Analogia: é uma prova com gabarito que fica guardada num envelope lacrado. Toda vez que o código do grupo
muda (novo commit ou PR), o pipeline faz a MESMA prova e recebe uma nota. Se alguém trocar uma questão
da prova, o lacre (o hash sha256 do arquivo) muda, e a nota nova deixa de ser comparável com as antigas.

Três passos:
  1. congelar  monta o conjunto a partir dos benchmarks do grupo (só leitura) e grava
               bancada/avaliacao/conjunto-v1.jsonl + conjunto-v1.manifesto.json (hash, origem de cada item,
               critério de seleção, contagem por disciplina). Se o arquivo já existe, NÃO é refeito: só conferido.
  2. rodar     passa cada item pelo pipeline do grupo com o arnês da bancada
               (bancada/pipeline/rastro_pipeline.py: adaptar_questao + instrumentar; trace.py: provedor 'eco').
  3. dar nota  mede cada saída com as funções determinísticas do grupo (iris.eval: trcc, readability,
               escopo/isolamento_escopo, metrics, benchmark) e agrega com média e IC95, no total e por disciplina.

Saída: pacote/outputs/32-avaliacao.json (só números, ids e tamanhos; nenhum trecho do RAG).

Uso (VPS, ~1 a 3 min):
    nice -n 19 env PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python \\
        bancada/avaliacao/conjunto.py
    ... conjunto.py --so-congelar      # só monta/confere o conjunto, não roda o pipeline
    ... conjunto.py --limite 5         # teste rápido (a nota sai marcada como parcial)

Aviso: o provedor 'eco' é um stub determinístico. A nota mede o encanamento (o pipeline roda? perde a trava?
o laudo aprova?), não a qualidade de um modelo de linguagem.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # nada de __pycache__ (nem aqui nem no clone do grupo)

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "pipeline"))

import rastro_pipeline as RP  # noqa: E402  (carrega trace.py e põe o código do grupo no sys.path)

T = RP.T

VERSAO = "v1"
CONJUNTO = AQUI / f"conjunto-{VERSAO}.jsonl"
MANIFESTO = AQUI / f"conjunto-{VERSAO}.manifesto.json"
SAIDA = T.OUTPUTS / "32-avaliacao.json"

FONTE_GOLDEN = "data/golden_benchmark.json"
FONTE_ESCOLAR = "data/benchmarks/questoes_escolares_v1.json"
SEMENTE = 20261112
POR_DISCIPLINA_ESCOLAR: int | None = None  # None = todos. Medido: ~0,15 s/item com eco -> 166 itens em ~30 s
# (cabe folgado nos ~3 min da VPS). Se o banco crescer muito, troque por um número (amostra estratificada fixa).
NIVEL = 2
CARACTERISTICA = RP.ID_COMANDOS_MULTIPLOS
LIMIAR_TRCC = 0.95
# Versão da FÓRMULA da nota: se a fórmula mudar, a nota também deixa de ser comparável (mesmo com o mesmo conjunto).
VERSAO_NOTA = "nota-1"
N_BOOTSTRAP = 2000
AVISO_ECO = "provedor determinístico: mede o encanamento, não a qualidade de um modelo"

# Os dois arquivos do grupo escrevem a mesma disciplina de jeitos diferentes.
NOMES_DISCIPLINA = {"Português": "Língua Portuguesa"}


# ====================================================================== 1. montar e congelar
def _sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _sha256_arquivo(caminho: Path) -> str:
    return _sha256_bytes(caminho.read_bytes())


def _linha_canonica(item: dict) -> str:
    # chaves ordenadas e sem espaço: o mesmo item sempre vira os mesmos bytes
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _enunciado_escolar(q: dict) -> str:
    """Enunciado + alternativas, uma por linha (é assim que a questão chega ao aluno)."""
    partes = [q["enunciado_original"].strip()]
    for alt in q.get("alternativas") or []:
        partes.append(f"{alt['letra']}) {alt['texto']}")
    return "\n".join(partes)


def montar_itens() -> tuple[list[dict], dict]:
    """Lê os dois benchmarks do grupo e devolve os itens selecionados + o critério usado."""
    golden = json.loads((T.GRUPO / FONTE_GOLDEN).read_text(encoding="utf-8"))
    escolar = json.loads((T.GRUPO / FONTE_ESCOLAR).read_text(encoding="utf-8"))

    itens: list[dict] = []
    # (a) Golden Benchmark: entram TODOS (30). É o único com comando_conjugado_esperado.
    for q in golden:
        itens.append({
            "id": f"golden:{q['id']}",
            "id_original": q["id"],
            "fonte": FONTE_GOLDEN,
            "origem_externa": None,
            "disciplina": NOMES_DISCIPLINA.get(q["disciplina"], q["disciplina"]),
            "ano": q.get("ano"),
            "enunciado": q["enunciado"],
            "trava_curricular": list(q.get("trava_curricular") or []),
            "comando_conjugado_esperado": bool(q.get("comando_conjugado_esperado")),
            "id_caracteristica_alvo": None,
            "status_no_grupo": q.get("status"),
        })

    # (b) Questões escolares v1: amostra estratificada fixa (mesmo número por disciplina, semente fixa).
    por_disc: dict[str, list[dict]] = {}
    for q in escolar:
        if not q.get("conceitos_trava_curricular"):
            continue  # sem trava não há TRCC para medir
        d = NOMES_DISCIPLINA.get(q["disciplina"], q["disciplina"])
        por_disc.setdefault(d, []).append(q)
    sorteio = random.Random(SEMENTE)
    disponiveis = {}
    for d in sorted(por_disc):
        candidatos = sorted(por_disc[d], key=lambda q: q["id"])  # ordem total antes do sorteio
        disponiveis[d] = len(candidatos)
        escolhidos = (candidatos if POR_DISCIPLINA_ESCOLAR is None
                      else sorteio.sample(candidatos, min(POR_DISCIPLINA_ESCOLAR, len(candidatos))))
        for q in sorted(escolhidos, key=lambda q: q["id"]):
            itens.append({
                "id": f"escolar:{q['id']}",
                "id_original": q["id"],
                "fonte": FONTE_ESCOLAR,
                "origem_externa": (q.get("fonte") or {}).get("origem"),
                "disciplina": d,
                "ano": q.get("ano_escolar"),
                "enunciado": _enunciado_escolar(q),
                "trava_curricular": list(q["conceitos_trava_curricular"]),
                "comando_conjugado_esperado": None,  # este banco não tem o campo
                "id_caracteristica_alvo": q.get("id_caracteristica_alvo"),
                "status_no_grupo": q.get("status"),
            })

    criterio = {
        FONTE_GOLDEN: "todos os itens (30); é o único banco com comando_conjugado_esperado",
        FONTE_ESCOLAR: (("todos os itens com conceitos_trava_curricular" if POR_DISCIPLINA_ESCOLAR is None else
                         f"amostra estratificada: {POR_DISCIPLINA_ESCOLAR} por disciplina, random.Random({SEMENTE})"
                         f".sample sobre os itens ordenados por id; só itens com conceitos_trava_curricular")
                        + "; enunciado = enunciado_original + alternativas (uma por linha)"),
        "itens_disponiveis_por_disciplina_escolar": disponiveis,
        "normalizacao_disciplina": NOMES_DISCIPLINA,
        "orcamento": ("alvo de ~3 min na VPS compartilhada; medido ~0,15 s por item com o provedor eco, "
                      "então os 166 itens cabem (~30 s) e não foi preciso amostrar"),
    }
    return itens, criterio


def congelar(forcar_conferencia: bool = True) -> dict:
    """Grava o conjunto se ele não existe; se existe, só confere o lacre. Devolve o manifesto."""
    if CONJUNTO.exists() and MANIFESTO.exists():
        manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
        sha_atual = _sha256_arquivo(CONJUNTO)
        manifesto["_conferencia"] = {
            "sha256_arquivo_atual": sha_atual,
            "lacre_intacto": sha_atual == manifesto["sha256"],
        }
        # As fontes do grupo mudaram desde o congelamento? Não muda o conjunto, mas avisa.
        fontes_mudaram = {}
        for f, sha in manifesto["fontes"].items():
            p = T.GRUPO / f
            fontes_mudaram[f] = (not p.exists()) or _sha256_arquivo(p) != sha["sha256"]
        manifesto["_conferencia"]["fontes_do_grupo_mudaram"] = fontes_mudaram
        return manifesto

    itens, criterio = montar_itens()
    linhas = [_linha_canonica(i) for i in itens]
    dados = ("\n".join(linhas) + "\n").encode("utf-8")
    CONJUNTO.write_bytes(dados)
    sha = _sha256_bytes(dados)
    contagem: dict[str, dict[str, int]] = {}
    for i in itens:
        c = contagem.setdefault(i["disciplina"], {"total": 0, FONTE_GOLDEN: 0, FONTE_ESCOLAR: 0})
        c["total"] += 1
        c[i["fonte"]] += 1
    manifesto = {
        "versao": VERSAO,
        "arquivo": CONJUNTO.name,
        "sha256": sha,
        "n_itens": len(itens),
        "congelado_em": T.agora_iso(),
        "commit_grupo_no_congelamento": T.commit_grupo(),
        "fontes": {f: {"sha256": _sha256_arquivo(T.GRUPO / f)} for f in (FONTE_GOLDEN, FONTE_ESCOLAR)},
        "criterio_selecao": criterio,
        "por_disciplina": dict(sorted(contagem.items())),
        "itens": [{"id": i["id"], "fonte": i["fonte"], "id_original": i["id_original"],
                   "disciplina": i["disciplina"], "origem_externa": i["origem_externa"],
                   "n_conceitos_trava": len(i["trava_curricular"]), "caracteres_enunciado": len(i["enunciado"])}
                  for i in itens],
        "regra": ("o conjunto não é refeito se o arquivo existir. Para mudar uma questão, crie conjunto-v2 "
                  "(mude VERSAO); notas de versões diferentes não são comparáveis."),
    }
    T.escrever_json(MANIFESTO, manifesto)
    manifesto["_conferencia"] = {"sha256_arquivo_atual": sha, "lacre_intacto": True,
                                 "fontes_do_grupo_mudaram": {FONTE_GOLDEN: False, FONTE_ESCOLAR: False},
                                 "recem_congelado": True}
    return manifesto


def ler_conjunto() -> list[dict]:
    return [json.loads(x) for x in CONJUNTO.read_text(encoding="utf-8").splitlines() if x.strip()]


# ====================================================================== 2. rodar pelo pipeline do grupo
def rodar_item(item: dict, cliente, commit: str) -> dict:
    """Um item pelo pipeline (Extrator -> RAG bm25 -> diretiva -> Adaptador + laudo), com as funções da bancada."""
    cfg = {"caracteristica": CARACTERISTICA, "nivel": NIVEL, "k": 5}
    r = T.Rastreador(f"avaliacao-{VERSAO}", item["id"], cliente.provider_name, T.nome_modelo(cliente), commit)
    cliente.rastreador = r
    desfazer = RP.instrumentar(r)
    t0 = time.perf_counter()
    try:
        out = RP.adaptar_questao(r, cliente, item["enunciado"], cfg, item["disciplina"], item["ano"],
                                 item["id_original"], trava_referencia=item["trava_curricular"])
        erro = None
    except Exception as exc:  # noqa: BLE001 - item com erro recebe nota zero, não derruba a rodada
        out, erro = {}, f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        for d in reversed(desfazer):
            d()
        cliente.rastreador = None
    out["latencia_s"] = round(time.perf_counter() - t0, 3)
    out["erro"] = erro
    out["etapas_com_erro"] = sorted({l["etapa"] for l in r.linhas if l["status"] == "erro"})
    return out


# ====================================================================== 3. nota por item
_SABOTAGENS: dict = {}


def _sabotagens_do_grupo():
    """SABOTAGENS de iris.eval.isolamento_escopo (as 6 formas de estragar uma adaptação).

    No commit 65e1f09 o módulo tem, na função de relatório _texto, uma f-string com barra invertida que só o
    Python 3.12+ aceita; a venv da bancada é 3.11. Plano B, sem alterar o arquivo do grupo: lê o código-fonte
    do grupo, troca SÓ aquela linha de cabeçalho de relatório (não usada aqui) por um texto fixo e executa em
    memória. Se nem assim importar, a sensibilidade fica None e o motivo vai para o JSON.
    """
    if "v" in _SABOTAGENS:
        return _SABOTAGENS["v"]
    _SABOTAGENS["erro"] = None
    try:
        from iris.eval.isolamento_escopo import SABOTAGENS

        _SABOTAGENS["v"], _SABOTAGENS["modo"] = SABOTAGENS, "import normal"
        return SABOTAGENS
    except SyntaxError as exc:
        motivo = f"SyntaxError linha {exc.lineno} em Python {sys.version_info.major}.{sys.version_info.minor}"
    try:
        import types

        caminho = T.GRUPO / "backend/src/iris/eval/isolamento_escopo.py"
        linhas = caminho.read_text(encoding="utf-8").splitlines()
        trocadas = [i for i, l in enumerate(linhas) if "retirados':>15}" in l]
        if len(trocadas) != 1:
            raise RuntimeError(f"linha a contornar não encontrada de forma única ({len(trocadas)})")
        recuo = linhas[trocadas[0]][: len(linhas[trocadas[0]]) - len(linhas[trocadas[0]].lstrip())]
        linhas[trocadas[0]] = recuo + '"(cabeçalho omitido pela bancada)"'
        mod = types.ModuleType("iris.eval.isolamento_escopo")
        mod.__file__ = str(caminho)
        exec(compile("\n".join(linhas) + "\n", str(caminho), "exec"), mod.__dict__)  # noqa: S102
        _SABOTAGENS["v"] = mod.SABOTAGENS
        _SABOTAGENS["modo"] = (f"{motivo}: carregado do código-fonte do grupo em memória, com a linha "
                               f"{trocadas[0] + 1} (cabeçalho de relatório) trocada por texto fixo; arquivo intacto")
    except Exception as exc:  # noqa: BLE001
        _SABOTAGENS["v"] = None
        _SABOTAGENS["erro"] = f"{motivo}; contorno falhou: {type(exc).__name__}: {exc}"
        _SABOTAGENS["modo"] = "indisponível"
    return _SABOTAGENS["v"]


def _nota(m: dict) -> float:
    """NOTA do item (0 a 1) = (retenção da trava + laudo de escopo aprovado) / 2.

    Retenção = dos conceitos da trava que EXISTEM no enunciado original, quantos continuam no adaptado.
    Assim um defeito do gabarito (conceito que nem está no original) não derruba a nota do pipeline;
    esse defeito aparece à parte em conceitos_ausentes_no_original.
    """
    ret = m.get("trcc_retencao")
    ret = m.get("trcc_adaptado") if ret is None else ret
    return round(((ret or 0.0) + m["escopo_gabarito_aprovado"]) / 2, 4)


def nota_item(item: dict, out: dict) -> dict:
    """Métricas determinísticas do grupo sobre a saída de um item."""
    from iris.eval.escopo import verificar_escopo
    from iris.eval.metrics import verificar_aderencia_nivel
    from iris.eval.readability import count_conjugated_commands, flesch_ptbr
    from iris.eval.trcc import avaliar_trcc

    original, trava = item["enunciado"], item["trava_curricular"]
    adaptado = out.get("adaptado") or ""
    m: dict = {"id": item["id"], "disciplina": item["disciplina"], "fonte": item["fonte"],
               "erro": out.get("erro"), "latencia_s": out.get("latencia_s")}
    if out.get("erro") or not adaptado.strip():
        m.update(roda_sem_erro=0, nota=0.0)
        return m

    trcc_o = avaliar_trcc(trava, original)
    trcc_a = avaliar_trcc(trava, adaptado)
    # laudo de escopo do grupo, com a trava do GABARITO (não a do Extrator): mede perda de palavra, ordem e trava
    laudo = verificar_escopo(original, adaptado, CARACTERISTICA, NIVEL, trava)
    fl_o, fl_a = flesch_ptbr(original), flesch_ptbr(adaptado)
    conj_o, conj_a = count_conjugated_commands(original), count_conjugated_commands(adaptado)
    m.update(
        roda_sem_erro=1,
        trcc_original=trcc_o.trcc,
        trcc_adaptado=trcc_a.trcc,
        # conceito da trava que existia no original e sumiu na adaptação (o que importa de verdade)
        trcc_retencao=(None if not trcc_o.n_encontrados else
                       round(sum(1 for c in trcc_o.encontrados if c in trcc_a.encontrados) / trcc_o.n_encontrados, 4)),
        trcc_aprovado=int(trcc_a.aprovado(LIMIAR_TRCC)),
        conceitos_ausentes_no_original=len(trcc_o.ausentes),
        escopo_gabarito_aprovado=int(laudo.aprovado),
        escopo_pipeline_aprovado=int(bool(out.get("escopo_aprovado"))),
        n_violacoes_escopo=len(laudo.violacoes),
        flesch_original=None if fl_o is None else round(fl_o, 2),
        flesch_adaptado=None if fl_a is None else round(fl_a, 2),
        flesch_delta=None if fl_o is None or fl_a is None else round(fl_a - fl_o, 2),
        comandos_conjugados_original=conj_o,
        comandos_conjugados_adaptado=conj_a,
        conjugado_resolvido=(None if conj_o == 0 else int(conj_a == 0)),
        # detector do grupo (readability) contra o rótulo do gabarito (benchmark.py: comando_conjugado_esperado)
        detector_conjugado_acerta=(None if item["comando_conjugado_esperado"] is None
                                   else int((conj_o > 0) == item["comando_conjugado_esperado"])),
        aderencia_nivel=int(bool(verificar_aderencia_nivel(NIVEL, adaptado)["valido"])),
        adaptacao_aplicada=int(bool(out.get("adaptacao_aplicada"))),
        mudou_texto=int(adaptado.strip() != original.strip()),
        usou_reserva=int(bool(out.get("used_fallback"))),
        trava_recall_extrator=out.get("trava_recall"),
        rag_chunk_ids=out.get("chunk_ids") or [],
        caracteres_original=len(original),
        caracteres_adaptado=len(adaptado),
        sha16_adaptado=hashlib.sha256(adaptado.encode("utf-8")).hexdigest()[:16],
        etapas_com_erro=out.get("etapas_com_erro") or [],
    )
    # Sensibilidade do laudo (isolamento_escopo.py do grupo): estraga a saída de 6 jeitos e conta quantas o
    # laudo acusa. Um laudo que aprova tudo acusaria 0.
    from iris.eval.benchmark import GoldenQuestion
    from iris.eval.escopo import palavras

    SABOTAGENS = _sabotagens_do_grupo()
    if SABOTAGENS is None:
        m.update(sabotagens_aplicadas=None, sabotagens_acusadas=None, laudo_sensibilidade=None)
        m["nota"] = _nota(m)
        return m
    gq = GoldenQuestion(id=item["id_original"], disciplina=item["disciplina"], ano=str(item["ano"]), tema="",
                        enunciado=original, comando_conjugado_esperado=bool(item["comando_conjugado_esperado"]),
                        trava_curricular=tuple(trava))
    aplicadas = acusadas = 0
    for sabotar in SABOTAGENS.values():
        estragado = sabotar(adaptado, gq)
        if estragado is None or palavras(estragado) == palavras(adaptado):
            continue
        aplicadas += 1
        acusadas += int(not verificar_escopo(original, estragado, CARACTERISTICA, NIVEL, trava).aprovado)
    m.update(sabotagens_aplicadas=aplicadas, sabotagens_acusadas=acusadas,
             laudo_sensibilidade=round(acusadas / aplicadas, 4) if aplicadas else None)

    m["nota"] = _nota(m)
    return m


# ====================================================================== agregação com IC95
BINARIAS = ["roda_sem_erro", "trcc_aprovado", "escopo_gabarito_aprovado", "escopo_pipeline_aprovado",
            "conjugado_resolvido", "detector_conjugado_acerta", "aderencia_nivel", "adaptacao_aplicada",
            "mudou_texto", "usou_reserva"]
CONTINUAS = ["nota", "trcc_adaptado", "trcc_original", "trcc_retencao", "flesch_original", "flesch_adaptado",
             "flesch_delta", "trava_recall_extrator", "laudo_sensibilidade", "latencia_s"]


def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, centro - meia), 4), round(min(1.0, centro + meia), 4)]


def bootstrap(valores: list[float], semente: int = SEMENTE) -> list[float] | None:
    if len(valores) < 2:
        return None
    rng = random.Random(semente)
    n = len(valores)
    medias = sorted(sum(rng.choice(valores) for _ in range(n)) / n for _ in range(N_BOOTSTRAP))
    return [round(medias[int(0.025 * N_BOOTSTRAP)], 4), round(medias[int(0.975 * N_BOOTSTRAP) - 1], 4)]


def resumir(notas: list[dict]) -> dict:
    res: dict = {"n_itens": len(notas)}
    for k in BINARIAS:
        v = [x[k] for x in notas if x.get(k) is not None]
        res[k] = {"n": len(v), "proporcao": round(sum(v) / len(v), 4) if v else None,
                  "ic95": wilson(sum(v), len(v)), "metodo_ic": "Wilson"}
    for k in CONTINUAS:
        v = [float(x[k]) for x in notas if x.get(k) is not None]
        res[k] = {"n": len(v), "media": round(statistics.fmean(v), 4) if v else None,
                  "ic95": bootstrap(v), "metodo_ic": f"bootstrap percentil, {N_BOOTSTRAP} reamostras"}
    return res


def comparar_com_anterior(sha: str, nota_media: float | None) -> dict:
    """Lê o 32-avaliacao.json anterior (se houver) e diz se as notas são comparáveis."""
    if not SAIDA.exists():
        return {"existe": False, "comparavel": None, "motivo": "sem rodada anterior"}
    try:
        ant = json.loads(SAIDA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"existe": True, "comparavel": False, "motivo": "arquivo anterior ilegível"}
    sha_ant = (ant.get("conjunto") or {}).get("sha256")
    nota_ant = ((ant.get("agregado") or {}).get("nota") or {}).get("media")
    mesma_formula = ant.get("versao_nota") == VERSAO_NOTA
    comparavel = sha_ant == sha and mesma_formula and not ant.get("parcial") and ant.get("provedor") == "eco"
    motivo = ("mesmo conjunto (hash igual), mesma fórmula de nota, mesmo provedor" if comparavel else
              "conjunto diferente (hash mudou): notas NÃO comparáveis" if sha_ant != sha else
              f"fórmula da nota diferente ({ant.get('versao_nota')} -> {VERSAO_NOTA}): notas NÃO comparáveis"
              if not mesma_formula else "rodada anterior parcial ou com outro provedor")
    return {
        "existe": True, "comparavel": comparavel, "motivo": motivo,
        "sha256_conjunto_anterior": sha_ant, "commit_grupo_anterior": ant.get("commit_grupo"),
        "gerado_em_anterior": ant.get("gerado_em"), "nota_media_anterior": nota_ant,
        "diferenca_nota_media": (round(nota_media - nota_ant, 4)
                                 if comparavel and nota_media is not None and nota_ant is not None else None),
        "ic95_nota_anterior": ((ant.get("agregado") or {}).get("nota") or {}).get("ic95"),
    }


# ====================================================================== principal
def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so-congelar", action="store_true", help="só monta/confere o conjunto")
    ap.add_argument("--limite", type=int, default=None, help="roda só os N primeiros itens (nota parcial)")
    args = ap.parse_args(argv)

    manifesto = congelar()
    conf = manifesto["_conferencia"]
    print(f"conjunto {VERSAO}: {manifesto['n_itens']} itens, sha256={manifesto['sha256'][:16]}..., "
          f"lacre intacto={conf['lacre_intacto']}, fontes do grupo mudaram={conf['fontes_do_grupo_mudaram']}")
    if args.so_congelar:
        return

    itens = ler_conjunto()
    if args.limite:
        itens = itens[: args.limite]
    commit = T.commit_grupo()
    cliente = T.criar_cliente("eco")
    t0 = time.perf_counter()
    notas = []
    for i, item in enumerate(itens, 1):
        cliente.prompts.clear()
        cliente.respostas.clear()
        out = rodar_item(item, cliente, commit)
        n = nota_item(item, out)
        notas.append(n)
        print(f"  {i:>2}/{len(itens)} {item['id']:<28} nota={n['nota']:.3f} "
              f"trcc={n.get('trcc_adaptado')} escopo={n.get('escopo_gabarito_aprovado')} "
              f"{out['latencia_s']:.2f}s{'  ERRO ' + out['erro'] if out.get('erro') else ''}", flush=True)
    duracao = round(time.perf_counter() - t0, 1)

    agregado = resumir(notas)
    disciplinas = sorted({n["disciplina"] for n in notas})
    por_disciplina = {d: resumir([n for n in notas if n["disciplina"] == d]) for d in disciplinas}
    por_fonte = {f: resumir([n for n in notas if n["fonte"] == f]) for f in (FONTE_GOLDEN, FONTE_ESCOLAR)}
    parcial = bool(args.limite) or len(notas) != manifesto["n_itens"]
    sha_valido = conf["lacre_intacto"]

    resultado = {
        "artefato": "32-avaliacao",
        "aviso": AVISO_ECO,
        "gerado_em": T.agora_iso(),
        "commit_grupo": commit,
        "provedor": "eco",
        "modelo": T.nome_modelo(cliente),
        "config": {"caracteristica": CARACTERISTICA, "nivel": NIVEL, "rag": "bm25, k=5",
                   "chunks_sha16": T.sha16(T.CHUNKS), "limiar_trcc": LIMIAR_TRCC},
        "conjunto": {"versao": VERSAO, "arquivo": f"bancada/avaliacao/{CONJUNTO.name}",
                     "sha256": manifesto["sha256"], "n_itens": manifesto["n_itens"],
                     "lacre_intacto": sha_valido,
                     "fontes_do_grupo_mudaram_desde_congelamento": conf["fontes_do_grupo_mudaram"],
                     "por_disciplina": manifesto["por_disciplina"]},
        "parcial": parcial,
        "n_avaliados": len(notas),
        "peso_de_1_item_pct": round(100 / len(notas), 2) if notas else None,
        "duracao_s": duracao,
        "versao_nota": VERSAO_NOTA,
        "definicao_nota": ("Nota de 0 a 1 por questão: zero se o pipeline deu erro; senão, a média de duas coisas: quanto da trava "
                           "curricular do gabarito ficou na saída e se o laudo de escopo do grupo aprovou. Atenção: a nota "
                           "também dá 1,0 quando o pipeline devolve o texto sem mudar; por isso olhe junto o número de questões que mudaram."),
        "isolamento_escopo_sabotagens": {"modo": _SABOTAGENS.get("modo"), "erro": _SABOTAGENS.get("erro")},
        "comparabilidade": comparar_com_anterior(manifesto["sha256"], agregado["nota"]["media"]),
        "agregado": agregado,
        "por_fonte": por_fonte,
        "por_disciplina": por_disciplina,
        "itens": notas,
        "limitacoes": [
            "provedor eco: a adaptação vem das regras do próprio grupo (destacar_comandos/decompor_em_etapas); "
            "a nota mostra se o encanamento preserva a trava, não se um modelo adapta bem",
            "travas e rótulos dos benchmarks têm status 'rascunho' no grupo (sem revisão pedagógica)",
            "por disciplina n = 25 a 47: IC95 ainda largo nas proporções; leia como tendência",
            "característica fixa (comandos múltiplos, nível 2) para todos os itens, inclusive os escolares cuja "
            "característica-alvo é outra",
        ],
    }
    if not sha_valido:
        resultado["comparabilidade"]["comparavel"] = False
        resultado["comparabilidade"]["motivo"] = "arquivo do conjunto foi alterado depois do lacre: nota inválida"
    T.escrever_json(SAIDA, resultado)
    a = agregado
    print(f"\nnota média {a['nota']['media']} IC95 {a['nota']['ic95']} (n={len(notas)}, {duracao}s); "
          f"roda sem erro {a['roda_sem_erro']['proporcao']}; TRCC>=0,95 {a['trcc_aprovado']['proporcao']}; "
          f"escopo {a['escopo_gabarito_aprovado']['proporcao']}")
    print(f"comparável com a anterior: {resultado['comparabilidade']['comparavel']} "
          f"({resultado['comparabilidade']['motivo']})")
    print(f"gravado: {SAIDA}")


if __name__ == "__main__":
    main()
