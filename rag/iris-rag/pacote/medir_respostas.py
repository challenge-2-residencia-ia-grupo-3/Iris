"""Mede as respostas do Íris, não só a busca: cada frase está apoiada no trecho que cita? a resposta responde?

    .venv/bin/python medir_respostas.py preparar          busca padrão + prompt do pacote para as 40 perguntas (cache/)
    .venv/bin/python medir_respostas.py gerar haiku       gera uma resposta por chamada (haiku | opus | produto)
    .venv/bin/python medir_respostas.py conferir          conferência mecânica, sem modelo (outputs/23)
    .venv/bin/python medir_respostas.py julgar haiku A    juiz A ou B julga cada resposta, uma por chamada (cache/)
    .venv/bin/python medir_respostas.py medir             junta os juízes e dá a nota (outputs/24)
    .venv/bin/python medir_respostas.py ancora            sorteia a amostra que uma pessoa julga (não sorteia de novo)
    .venv/bin/python medir_respostas.py medir-ancora      compara a pessoa com os juízes (outputs/25)
    .venv/bin/python medir_respostas.py julgar2 haiku A   segunda rodada: regra versão 2 (regra_juiz_respostas_v2.md)
    .venv/bin/python medir_respostas.py medir2            nota da segunda rodada, em cinco caixas (outputs/26)
    .venv/bin/python medir_respostas.py praticas          as 10 perguntas práticas em três camadas: base, busca, gerador (outputs/27)

Técnica: nenhum modelo é treinado. Modelos prontos geram e julgam; o resto é contagem e sorteio de perguntas.
Regra do juiz: regra_juiz_respostas.md. Expectativa e critério: RESPOSTAS.md, commitados antes de gerar.
O texto dos trechos e as passagens copiadas pelos juízes ficam em cache/ (fora do Git). O que é versionado:
as respostas, os chunk_id entregues e os vereditos, sem o texto dos trechos.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("RAG_BANCO", "chroma")       # no Mac a base está no Chroma; os vetores são os mesmos do pgvector
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

PERGUNTAS = AQUI.parent / "gabarito" / "perguntas_v0.json"
GABARITO = AQUI.parent / "gabarito" / "gabarito_rascunho_v0.json"
PASTA = AQUI / "cache" / "respostas"               # fora do Git: tem o texto dos trechos
SAIDAS = AQUI.parents[1] / "outputs"
VERSIONADO = AQUI / "respostas_medidas.json"       # respostas e chunk_id, sem o texto dos trechos
REGRA = AQUI / "regra_juiz_respostas.md"
GERADORES = {"haiku": "haiku", "opus": "opus"}     # apelido -> modelo pedido ao Claude; "produto" usa gerar.gerar
JUIZ_MODELO = "sonnet"
SISTEMA_GERADOR = "Você é um assistente. Siga as instruções da mensagem."
SISTEMA_JUIZ = "Você é um avaliador cuidadoso. Siga a regra da mensagem e devolva só o JSON pedido."
N_BOOT, SEMENTE = 2000, 20261105
EM_PARALELO = 4


# ---------------------------------------------------------------- utilidades
def ler(caminho: Path, padrao=None):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


def gravar(caminho: Path, dado) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")


def chamar_claude(modelo: str, sistema: str, texto: str) -> tuple[str, dict]:
    """Uma chamada isolada: sem ferramentas, sem contexto de projeto, sem memória de outra pergunta."""
    vazio = tempfile.mkdtemp(prefix="iris-")       # pasta vazia: nenhum CLAUDE.md é lido
    cmd = ["claude", "-p", "--model", modelo, "--system-prompt", sistema, "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence", "--output-format", "json"]
    for tentativa in range(3):
        r = subprocess.run(cmd, input=texto, capture_output=True, text=True, cwd=vazio, timeout=600)
        try:
            d = json.loads(r.stdout)
            if not d.get("is_error"):
                uso = d.get("usage") or {}
                return d["result"].strip(), {"modelo": ", ".join((d.get("modelUsage") or {}).keys()),
                                             "entrada": sum(uso.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
                                             "saida": uso.get("output_tokens", 0), "ms": d.get("duration_ms")}
        except (json.JSONDecodeError, KeyError):
            pass
        time.sleep(5 * (tentativa + 1))
    raise RuntimeError(f"chamada ao modelo {modelo} falhou: {r.stdout[:300]} {r.stderr[:300]}")


ABREVIACAO = re.compile(r"(?:\bet al|\bart|\barts|\bcf|\bvs|\bDr|\bDra|\bProf|\bn[ºo]?)\.$")


def frases_da_resposta(resposta: str, juntar: bool = True) -> list[str]:
    """Divide a resposta em frases. Citação que ficou depois do ponto final ("Frase. [T1]") volta para a frase dela;
    pedaço com menos de 4 palavras é colado na frase anterior.
    juntar=True (padrão desde a segunda rodada): pedaço que termina em abreviação ("o art.", "Pashler et al.") não é fim
    de frase e é colado no pedaço seguinte. juntar=False reproduz a divisão que os juízes da primeira rodada receberam."""
    # "1. Ofereça..." é item de lista, não fim de frase: troca "1." por "1)" antes de dividir
    texto = re.sub(r"(?:(?<=\s)|^)(\d{1,2})\.\s+(?=[A-ZÀ-Ú\"“])", r"\1) ", resposta.strip())
    pedacos = [p for p in re.split(r"(?<=[.!?])\s+", texto) if p.strip()]
    saida: list[str] = []
    for p in pedacos:
        m = re.match(r"((?:\[T\d+\]\s*)+)(.*)", p, flags=re.S)
        if m and saida:                                    # começa com [T2]: a citação é da frase anterior
            saida[-1] += " " + m.group(1).strip()
            p = m.group(2).strip()
            if not p:
                continue
        if saida and len(re.sub(r"\[T\d+\]", "", p).split()) < 4:
            saida[-1] += " " + p
        else:
            saida.append(p)
    if juntar:
        junto: list[str] = []
        for p in saida:
            if junto and ABREVIACAO.search(junto[-1].strip()):       # o pedaço anterior parou numa abreviação
                junto[-1] += " " + p
            else:
                junto.append(p)
        saida = junto
    return saida


def citados(frase: str) -> list[int]:
    return sorted({int(n) for n in re.findall(r"\[T(\d+)\]", frase)})


def media(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def intervalo(valores: list[float]) -> tuple[float, float]:
    """Intervalo de 95% por sorteio de perguntas (bootstrap), semente fixa."""
    rnd = random.Random(SEMENTE)
    m = len(valores)
    medias = sorted(sum(rnd.choice(valores) for _ in range(m)) / m for _ in range(N_BOOT))
    return medias[int(.025 * N_BOOT)], medias[int(.975 * N_BOOT) - 1]


def so(ids: list[str]) -> list[str]:
    """--so Q01,Q39 restringe a rodada a algumas perguntas (para testar antes de gastar)."""
    if "--so" in sys.argv:
        quero = sys.argv[sys.argv.index("--so") + 1].split(",")
        return [i for i in ids if i in quero]
    return ids


# ---------------------------------------------------------------- 1. busca e prompt
def preparar() -> None:
    import consultar
    import gerar
    itens = []
    for q in ler(PERGUNTAS)["itens"]:
        trechos = consultar.buscar(q["pergunta"])                     # método padrão do pacote, 5 trechos
        itens.append({"id": q["id"], "tipo": q["tipo"], "pergunta": q["pergunta"],
                      "prompt": gerar.montar_prompt(q["pergunta"], trechos),     # o prompt do pacote, sem mudar nada
                      "trechos": [{"ref": f"T{i}", **{k: t[k] for k in ("chunk_id", "doc", "titulo", "pagina", "idioma",
                                                                         "nao_usar_para", "nota_uso", "trecho")}}
                                  for i, t in enumerate(trechos, 1)]})
    gravar(PASTA / "prompts.json", {"metodo": consultar.METODO_PADRAO, "banco": consultar.BANCO,
                                    "frase_sem_resposta": gerar.FRASE_SEM_RESPOSTA, "itens": itens})
    tam = [len(i["prompt"].split()) for i in itens]
    print(f"{len(itens)} prompts montados com a busca {consultar.METODO_PADRAO} ({consultar.BANCO}); "
          f"palavras por prompt: mediana {sorted(tam)[len(tam) // 2]}, maior {max(tam)}")


# ---------------------------------------------------------------- 2. geração
def gerar_respostas(g: str) -> None:
    base = ler(PASTA / "prompts.json")
    destino = PASTA / f"respostas-{g}.json"
    feito = ler(destino, {})
    faltam = [i for i in base["itens"] if i["id"] in so([x["id"] for x in base["itens"]]) and i["id"] not in feito]

    def uma(item: dict) -> tuple[str, dict]:
        if g == "produto":                                             # o LLM do pacote (Groq ou Ollama)
            import gerar
            texto, uso = gerar.gerar(item["prompt"])
            return item["id"], {"resposta": texto, "uso": {"modelo": f"{gerar.LLM}:{gerar.MODELO}", **uso}}
        texto, uso = chamar_claude(GERADORES[g], SISTEMA_GERADOR, item["prompt"])
        return item["id"], {"resposta": texto, "uso": uso}

    with ThreadPoolExecutor(1 if g == "produto" else EM_PARALELO) as ex:
        for qid, r in ex.map(uma, faltam):
            feito[qid] = r
            gravar(destino, feito)                                     # grava a cada resposta: dá para retomar
            print(g, qid, "ok", len(r["resposta"].split()), "palavras", flush=True)
    print(f"{g}: {len(feito)} respostas em {destino.name}")


# ---------------------------------------------------------------- 3. conferência mecânica (sem modelo)
def carregar() -> tuple[dict, dict[str, dict], dict[str, set]]:
    """Os prompts, as respostas de cada gerador que já tem as 40, e os trechos certos (nota 2) do gabarito do Opus."""
    base = ler(PASTA / "prompts.json")
    resp = {}
    for g in [*GERADORES, "produto"]:
        r = ler(PASTA / f"respostas-{g}.json")
        if r and len(r) == len(base["itens"]):
            resp[g] = r
    certos = {i["id"]: set(i["trechos_relevantes"]) for i in ler(GABARITO)["itens"]}
    return base, resp, certos


def recusou(resposta: str, frase_sem: str) -> bool:
    return frase_sem.lower()[:40] in resposta.lower()


def conferir() -> None:
    base, resp, certos = carregar()
    itens = base["itens"]
    L = ["CONFERÊNCIA MECÂNICA DAS RESPOSTAS (sem modelo julgando: só contagem sobre o texto das respostas).",
         f"40 perguntas de perguntas_v0.json; busca {base['metodo']}, 5 trechos; prompt do pacote (gerar.montar_prompt).",
         "ATENÇÃO: os geradores são modelos Claude, não o modelo configurado no protótipo (Qwen, via Groq), que não pôde ser chamado.",
         "Nenhum modelo treinado. Esta conferência não diz se o conteúdo está certo; isso é o juiz e a pessoa.", ""]
    versionado = {"busca": base["metodo"], "geradores": {}}
    for g, r in resp.items():
        com = [i for i in itens if i["tipo"] != "sem_resposta"]
        sem = [i for i in itens if i["tipo"] == "sem_resposta"]
        rec = {i["id"]: recusou(r[i["id"]]["resposta"], base["frase_sem_resposta"]) for i in itens}
        fr = {i["id"]: ([] if rec[i["id"]] else frases_da_resposta(r[i["id"]]["resposta"])) for i in itens}
        todas = [f for v in fr.values() for f in v]
        sem_cit = [f for f in todas if not citados(f)]
        invalidas = [f for f in todas if any(not 1 <= n <= 5 for n in citados(f))]
        responde = [i for i in itens if not rec[i["id"]]]
        usados = [len({n for f in fr[i["id"]] for n in citados(f)}) for i in responde]
        aviso = sum(any(i["trechos"][n - 1]["nao_usar_para"] for f in fr[i["id"]] for n in citados(f) if 1 <= n <= 5) for i in responde)
        palavras = sorted(len(r[i["id"]]["resposta"].split()) for i in responde)
        L += [f"===== GERADOR {g.upper()} ({r[itens[0]['id']]['uso'].get('modelo', '?')}) =====",
              f"recusas nas {len(sem)} perguntas sem resposta de propósito: {sum(rec[i['id']] for i in sem)} de {len(sem)} "
              f"({', '.join(i['id'] + ('=recusou' if rec[i['id']] else '=respondeu') for i in sem)})",
              f"recusas nas {len(com)} perguntas com resposta na base: {sum(rec[i['id']] for i in com)} de {len(com)} "
              f"({', '.join(i['id'] for i in com if rec[i['id']]) or 'nenhuma'})",
              f"respostas dadas: {len(responde)}; frases: {len(todas)} (média {len(todas) / max(len(responde), 1):.1f} por resposta; "
              f"respostas com mais de 6 frases, o limite do prompt: {sum(len(fr[i['id']]) > 6 for i in responde)})",
              f"palavras por resposta: mediana {palavras[len(palavras) // 2]}, maior {palavras[-1]}",
              f"frases sem citação nenhuma: {len(sem_cit)} de {len(todas)} ({100 * len(sem_cit) / max(len(todas), 1):.1f}%)",
              f"frases com citação de trecho que não existe: {len(invalidas)} de {len(todas)}",
              f"trechos diferentes citados por resposta, dos 5 entregues: média {media(usados):.1f}",
              f"respostas que citam trecho com aviso de uso: {aviso} de {len(responde)}"]
        # cruzamento com a busca: o gerador recebeu algum trecho que o gabarito do Opus marca como certo?
        tem = {i["id"]: bool(certos[i["id"]] & {t["chunk_id"] for t in i["trechos"]}) for i in com}
        citou_certo = sum(bool(certos[i["id"]] & {i["trechos"][n - 1]["chunk_id"] for f in fr[i["id"]] for n in citados(f) if 1 <= n <= 5})
                          for i in com if not rec[i["id"]])
        L += ["", "Cruzamento com a busca (gabarito do Opus, de modelo), nas perguntas com resposta na base:",
              f"{'':46s}{'respondeu':>11s}{'recusou':>9s}",
              f"{'recebeu ao menos 1 trecho certo nos 5':46s}{sum(tem[k] and not rec[k] for k in tem):11d}{sum(tem[k] and rec[k] for k in tem):9d}",
              f"{'não recebeu nenhum trecho certo':46s}{sum(not tem[k] and not rec[k] for k in tem):11d}{sum(not tem[k] and rec[k] for k in tem):9d}",
              f"respostas que citam ao menos 1 trecho certo: {citou_certo} de {sum(not rec[i['id']] for i in com)}",
              f"tokens gastos na geração: entrada {sum(v['uso'].get('entrada') or v['uso'].get('prompt_tokens') or 0 for v in r.values())}, "
              f"saída {sum(v['uso'].get('saida') or v['uso'].get('completion_tokens') or 0 for v in r.values())}", ""]
        versionado["geradores"][g] = {i["id"]: {"resposta": r[i["id"]]["resposta"], "modelo": r[i["id"]]["uso"].get("modelo"),
                                                "fontes": [t["chunk_id"] for t in i["trechos"]]} for i in itens}
    gravar(VERSIONADO, versionado)
    destino = SAIDAS / "23-respostas-conferencia.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 4. juízes de modelo
def prompt_do_juiz(item: dict, resposta: str, frase_sem: str) -> str:
    blocos = []
    for t in item["trechos"]:
        pag = f", p. {t['pagina']}" if t.get("pagina") else ""
        aviso = f"\nAVISO DE USO: {t['nota_uso']}" if t.get("nao_usar_para") else ""
        blocos.append(f"[{t['ref']}] {t['titulo']}{pag} ({t['idioma']}){aviso}\n{t['trecho']}")
    if recusou(resposta, frase_sem):
        frases = "A resposta é a recusa. Não há frases a julgar: preencha `abstencao`."
    else:
        frases = "\n".join(f"S{n}: {f}" for n, f in enumerate(frases_da_resposta(resposta, juntar=False), 1))
    return (REGRA.read_text(encoding="utf-8") + f"\n\n---\n\nPERGUNTA: {item['pergunta']}\n\nTRECHOS ENTREGUES AO SISTEMA:\n\n"
            + "\n\n".join(blocos) + f"\n\nRESPOSTA (inteira):\n{resposta}\n\nFRASES A JULGAR:\n{frases}\n")


def extrair_json(texto: str) -> dict | None:
    m = re.search(r"\{.*\}", texto, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def julgar(g: str, juiz: str) -> None:
    base, resp, _ = carregar()
    r = resp[g]
    destino = PASTA / f"juiz-{juiz}-{g}.json"
    feito = ler(destino, {})
    ids = so([i["id"] for i in base["itens"]])
    faltam = [i for i in base["itens"] if i["id"] in ids and i["id"] not in feito]

    def um(item: dict) -> tuple[str, dict]:
        p = prompt_do_juiz(item, r[item["id"]]["resposta"], base["frase_sem_resposta"])
        for _ in range(2):                                              # uma segunda chance se o JSON vier quebrado
            bruto, uso = chamar_claude(JUIZ_MODELO, SISTEMA_JUIZ, p)
            d = extrair_json(bruto)
            if d is not None:
                break
        return item["id"], {"json": d, "bruto": bruto if d is None else None, "uso": uso}

    with ThreadPoolExecutor(EM_PARALELO) as ex:
        for qid, v in ex.map(um, faltam):
            feito[qid] = v
            gravar(destino, feito)
            print("juiz", juiz, g, qid, "ok" if v["json"] else "JSON INVÁLIDO", flush=True)
    print(f"juiz {juiz} / {g}: {len(feito)} julgamentos")


def limpar(x: str) -> str:
    """Para conferir se a passagem copiada existe no trecho: iguala espaços, aspas e traços, e ignora maiúsculas."""
    x = x.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", x).strip().strip('."\'').lower()


def veredito_conferido(v: dict, frase: str, item: dict) -> str:
    """O veredito do juiz para uma frase, depois de conferir a prova. 'rejeitado' = a passagem não está no trecho citado."""
    ver = v.get("veredito")
    if ver not in ("apoiada", "parcial", "nao_apoiada"):
        return "sem_veredito"
    if ver == "nao_apoiada":
        return ver
    cit = limpar(v.get("citacao") or "")
    refs = [n for n in citados(frase) if 1 <= n <= 5]
    if len(cit.split()) < 3 or not any(cit in limpar(item["trechos"][n - 1]["trecho"]) for n in refs):
        return "rejeitado"
    return ver


def kappa(pares: list[tuple[str, str]]) -> float:
    """Kappa de Cohen: concordância entre dois avaliadores descontando a que viria do acaso."""
    n = len(pares)
    if not n:
        return float("nan")
    po = sum(a == b for a, b in pares) / n
    ca, cb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def julgamentos(g: str, base: dict, resp: dict) -> dict:
    """Para cada pergunta: os vereditos conferidos dos dois juízes, frase a frase, e o veredito comum."""
    jz = {j: ler(PASTA / f"juiz-{j}-{g}.json", {}) for j in "AB"}
    saida = {}
    for item in base["itens"]:
        qid = item["id"]
        texto = resp[g][qid]["resposta"]
        rec = recusou(texto, base["frase_sem_resposta"])
        fr = [] if rec else frases_da_resposta(texto, juntar=False)      # a divisão que os juízes da 1ª rodada receberam
        d = {j: (jz[j].get(qid) or {}).get("json") or {} for j in "AB"}
        linhas = []
        for n, f in enumerate(fr, 1):
            v = {}
            for j in "AB":
                bruto = next((x for x in d[j].get("frases") or [] if x.get("n") == n), None)
                v[j] = "sem_citacao" if not citados(f) else veredito_conferido(bruto, f, item) if bruto else "sem_veredito"
                v[j + "_outro"] = bool(bruto and bruto.get("outro_trecho")) if bruto else False
                v[j + "_aviso"] = bool(bruto and bruto.get("desrespeitou_aviso")) if bruto else False
            comum = v["A"] if v["A"] == v["B"] and v["A"] in ("apoiada", "parcial", "nao_apoiada") else \
                "nao_apoiada" if v["A"] == v["B"] == "sem_citacao" else "divergem"
            linhas.append({"n": n, "frase": f, **v, "comum": comum})
        saida[qid] = {"tipo": item["tipo"], "recusou": rec, "frases": linhas,
                      "responde": {j: d[j].get("responde") for j in "AB"},
                      "abstencao": {j: d[j].get("abstencao") for j in "AB"}}
        s = saida[qid]
        if rec:
            s["aprovada"] = s["abstencao"]["A"] == s["abstencao"]["B"] == "correta"
        else:
            s["aprovada"] = (s["responde"]["A"] == s["responde"]["B"] == "sim"
                             and bool(linhas) and all(x["comum"] == "apoiada" for x in linhas))
    return saida


def medir() -> None:
    base, resp, certos = carregar()
    L = ["NOTA DAS RESPOSTAS SEGUNDO DOIS JUÍZES DE MODELO (Claude Sonnet, duas chamadas que não se veem).",
         f"40 perguntas; busca {base['metodo']}, 5 trechos; prompt do pacote. Regra do juiz: regra_juiz_respostas.md.",
         "ATENÇÃO: os geradores são modelos Claude, não o modelo configurado no protótipo. Juízes e geradores são do mesmo fabricante.",
         "Técnica: modelos prontos geram e julgam; contagem; sorteio de perguntas para o intervalo "
         f"({N_BOOT} sorteios, semente {SEMENTE}). Nenhum modelo treinado.",
         "Prova obrigatória: para dizer 'apoiada' ou 'parcial' o juiz copia a passagem do trecho citado; o script procura a",
         "passagem no trecho e marca 'rejeitado' se ela não estiver lá. Frase em que os juízes divergem não conta como apoiada.", ""]
    por_g, vers = {}, {}
    ordem = ["apoiada", "parcial", "nao_apoiada", "rejeitado", "sem_veredito", "sem_citacao"]
    for g in resp:
        if not all((PASTA / f"juiz-{j}-{g}.json").exists() for j in "AB"):
            continue
        J = julgamentos(g, base, resp)
        por_g[g] = J
        itens = base["itens"]
        com = [i["id"] for i in itens if i["tipo"] != "sem_resposta"]
        sem = [i["id"] for i in itens if i["tipo"] == "sem_resposta"]
        fr = [x for q in J.values() for x in q["frases"]]
        c = Counter(x["comum"] for x in fr)
        n = len(fr)
        L += [f"===== GERADOR {g.upper()} =====", "",
              f"1. Frases ({n}, das {sum(not q['recusou'] for q in J.values())} respostas que não recusaram)",
              f"{'veredito comum dos dois juízes':34s}{'frases':>8s}{'%':>7s}"]
        for k in ("apoiada", "parcial", "nao_apoiada", "divergem"):
            L.append(f"{k:34s}{c[k]:8d}{100 * c[k] / max(n, 1):7.1f}")
        L += ["", "Matriz de concordância entre os juízes, frase a frase (linhas = juiz A, colunas = juiz B):",
              f"{'':16s}" + "".join(f"{k:>14s}" for k in ordem)]
        m = Counter((x["A"], x["B"]) for x in fr)
        for a in ordem:
            if any(m[(a, b)] for b in ordem) or any(m[(b, a)] for b in ordem):
                L.append(f"{a:16s}" + "".join(f"{m[(a, b)]:14d}" for b in ordem))
        iguais = sum(x["A"] == x["B"] for x in fr)
        L += [f"mesmo veredito: {iguais} de {n} ({100 * iguais / max(n, 1):.1f}%); kappa de Cohen {kappa([(x['A'], x['B']) for x in fr]):.2f}",
              f"vereditos rejeitados por passagem que não existe no trecho citado: juiz A {sum(x['A'] == 'rejeitado' for x in fr)}, "
              f"juiz B {sum(x['B'] == 'rejeitado' for x in fr)}, de {n} cada",
              f"frases que os dois juízes dizem estar em outro trecho, não no citado (erro de citação): "
              f"{sum(x['A_outro'] and x['B_outro'] for x in fr)}",
              f"frases que os dois juízes dizem desrespeitar um aviso de uso: {sum(x['A_aviso'] and x['B_aviso'] for x in fr)}", ""]
        resp_ok = [q for q in com if not J[q]["recusou"]]
        todas = sum(all(x["comum"] == "apoiada" for x in J[q]["frases"]) for q in resp_ok)
        mr_ = Counter((J[q]["responde"]["A"], J[q]["responde"]["B"]) for q in resp_ok)
        L += [f"2. Respostas ({len(com)} perguntas com resposta na base; {len(resp_ok)} respondidas, {len(com) - len(resp_ok)} recusadas)",
              f"respostas com todas as frases apoiadas pelos dois juízes: {todas} de {len(resp_ok)}",
              "responde à pergunta? (linhas = juiz A, colunas = juiz B)",
              f"{'':12s}" + "".join(f"{k:>10s}" for k in ("sim", "em_parte", "nao"))]
        for a in ("sim", "em_parte", "nao"):
            L.append(f"{a:12s}" + "".join(f"{mr_[(a, b)]:10d}" for b in ("sim", "em_parte", "nao")))
        ind = [q for q in com if J[q]["recusou"]]
        L += [f"os dois dizem 'sim': {mr_[('sim', 'sim')]} de {len(resp_ok)} respondidas ({mr_[('sim', 'sim')]} de {len(com)} perguntas)", "",
              "3. Recusas",
              "perguntas sem resposta de propósito: " + ", ".join(
                  f"{q} {'recusou' if J[q]['recusou'] else 'RESPONDEU'}"
                  + (f" (juízes: {J[q]['abstencao']['A']}/{J[q]['abstencao']['B']})" if J[q]["recusou"] else "") for q in sem),
              f"recusas em perguntas com resposta na base: {len(ind)}" + ("".join(
                  f"\n   {q}: juízes {J[q]['abstencao']['A']}/{J[q]['abstencao']['B']}; "
                  f"recebeu trecho certo nos 5: {'sim' if certos[q] & {t['chunk_id'] for i in itens if i['id'] == q for t in i['trechos']} else 'não'}"
                  for q in ind)), ""]
        ap = [float(J[i["id"]]["aprovada"]) for i in itens]
        lo, hi = intervalo(ap)
        ap38 = [float(J[q]["aprovada"]) for q in com]
        lo2, hi2 = intervalo(ap38)
        L += ["4. A NOTA (critério escrito antes: aprovada = responde, segundo os dois juízes, e todas as frases apoiadas pelos dois;",
              "   ou recusa que os dois consideram correta)",
              f"aprovadas: {int(sum(ap))} de {len(ap)} ({100 * media(ap):.0f}%; intervalo de 95% de {100 * lo:.0f}% a {100 * hi:.0f}%)",
              f"só nas perguntas com resposta na base: {int(sum(ap38))} de {len(ap38)} ({100 * media(ap38):.0f}%; de {100 * lo2:.0f}% a {100 * hi2:.0f}%)",
              "por que as outras não foram aprovadas (uma resposta pode cair em mais de um motivo):",
              f"   alguma frase não apoiada ou com juízes divergindo: {sum(not J[q]['recusou'] and not all(x['comum'] == 'apoiada' for x in J[q]['frases']) for q in J)}",
              f"   não responde, ou responde em parte, para ao menos um juiz: {sum(not J[q]['recusou'] and not (J[q]['responde']['A'] == J[q]['responde']['B'] == 'sim') for q in J)}",
              f"   recusa que ao menos um juiz não considera correta: {sum(J[q]['recusou'] and not J[q]['aprovada'] for q in J)}", "",
              "4b. Sensibilidade (NÃO estava no critério; calculada depois de ver o resultado, para entender a nota)",
              f"frases que ao menos um juiz considera apoiada: {sum('apoiada' in (x['A'], x['B']) for x in fr)} de {n} "
              f"({100 * sum('apoiada' in (x['A'], x['B']) for x in fr) / max(n, 1):.1f}%)",
              f"frases que os dois juízes reprovam (não apoiada), tendo citação: {sum(x['A'] == x['B'] == 'nao_apoiada' for x in fr)} de {n}: "
              + ", ".join(f"{q} S{x['n']}" for q, v in J.items() for x in v["frases"] if x["A"] == x["B"] == "nao_apoiada"),
              f"frases sem citação nenhuma: {sum(x['A'] == 'sem_citacao' for x in fr)} de {n}",
              f"respostas aprovadas se bastasse um juiz dizer 'apoiada' em cada frase e 'sim' em responde (ou 'correta' na recusa): "
              f"{sum((v['recusou'] and 'correta' in v['abstencao'].values()) or (not v['recusou'] and 'sim' in v['responde'].values() and bool(v['frases']) and all('apoiada' in (x['A'], x['B']) for x in v['frases'])) for v in J.values())} de {len(J)}",
              f"respostas em que nenhuma frase é reprovada pelos dois juízes nem fica sem citação, e os dois dizem que responde: "
              f"{sum(not v['recusou'] and v['responde']['A'] == v['responde']['B'] == 'sim' and all(x['comum'] != 'nao_apoiada' for x in v['frases']) for v in J.values())} de {len(J)}", "",
              "5. Aprovadas por tipo de pergunta e por ter recebido trecho certo (gabarito do Opus)",
              f"{'recorte':40s}{'aprovadas':>12s}"]
        for t in dict.fromkeys(i["tipo"] for i in itens):
            ids = [i["id"] for i in itens if i["tipo"] == t]
            L.append(f"{'tipo ' + t:40s}{sum(J[q]['aprovada'] for q in ids):6d} de {len(ids)}")
        tem = {i["id"]: bool(certos[i["id"]] & {t["chunk_id"] for t in i["trechos"]}) for i in itens if i["tipo"] != "sem_resposta"}
        for rot, cond in (("recebeu ao menos 1 trecho certo nos 5", True), ("não recebeu nenhum trecho certo", False)):
            ids = [q for q in tem if tem[q] == cond]
            L.append(f"{rot:40s}{sum(J[q]['aprovada'] for q in ids):6d} de {len(ids)}")
        L += ["", "tokens gastos pelos juízes: " + "; ".join(
            f"juiz {j} entrada {sum(v['uso']['entrada'] for v in ler(PASTA / f'juiz-{j}-{g}.json').values())}, "
            f"saída {sum(v['uso']['saida'] for v in ler(PASTA / f'juiz-{j}-{g}.json').values())}" for j in "AB"), ""]
        vers[g] = {q: {"recusou": v["recusou"], "aprovada": v["aprovada"], "responde": v["responde"], "abstencao": v["abstencao"],
                       "frases": [{k: x[k] for k in ("n", "A", "B", "comum")} for x in v["frases"]]} for q, v in J.items()}
    if len(por_g) >= 2:
        a, b = list(por_g)[:2]
        ids = [q for q in por_g[a] if por_g[a][q]["frases"] and por_g[b][q]["frases"]]
        fa = [media(x["comum"] == "apoiada" for x in por_g[a][q]["frases"]) for q in ids]
        fb = [media(x["comum"] == "apoiada" for x in por_g[b][q]["frases"]) for q in ids]
        d = [y - x for x, y in zip(fa, fb)]
        lo, hi = intervalo(d)
        L += [f"===== {b.upper()} MENOS {a.upper()} =====",
              f"fração de frases apoiadas por pergunta, nas {len(ids)} perguntas que os dois responderam: "
              f"{a} {media(fa):.2f}, {b} {media(fb):.2f}; diferença {media(d):+.2f} [{lo:+.2f} a {hi:+.2f}]",
              f"aprovadas nas 40: {a} {sum(q['aprovada'] for q in por_g[a].values())}, {b} {sum(q['aprovada'] for q in por_g[b].values())}; "
              f"aprovadas nos dois: {sum(por_g[a][q]['aprovada'] and por_g[b][q]['aprovada'] for q in por_g[a])}; "
              f"só {a}: {sum(por_g[a][q]['aprovada'] and not por_g[b][q]['aprovada'] for q in por_g[a])}; "
              f"só {b}: {sum(por_g[b][q]['aprovada'] and not por_g[a][q]['aprovada'] for q in por_g[a])}", ""]
    gravar(AQUI / "respostas_vereditos.json", vers)
    destino = SAIDAS / "24-respostas-juizes.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 5. âncora humana
ANCORA = AQUI / "ancora_respostas.json"            # arquivo que uma pessoa preenche: criado uma vez, nunca regenerado
N_FRASES, N_RESPOSTAS = 24, 8
ROTULOS_FRASE = ("apoiada", "parcial", "nao_apoiada", "nao_sei")
ROTULOS_RESPOSTA = ("sim", "em_parte", "nao", "nao_sei")


def ancora() -> None:
    """Sorteia a amostra que a pessoa julga, sem gravar nela o veredito dos juízes. Metade vem dos itens que os dois
    juízes aprovaram e metade dos demais, para haver casos dos dois lados. Se o arquivo já existe, não sorteia de novo."""
    if ANCORA.exists():
        d = ler(ANCORA)
        print(f"{ANCORA.name} já existe ({sum(x['matheus'] is not None for x in d['itens'])} de {len(d['itens'])} respondidos); nada foi sorteado")
        return
    base, resp, _ = carregar()
    rnd = random.Random(SEMENTE)
    gs = [g for g in resp if all((PASTA / f"juiz-{j}-{g}.json").exists() for j in "AB")]
    itens = []
    for g in gs:
        J = julgamentos(g, base, resp)
        fr = [(q, x) for q, v in J.items() for x in v["frases"] if any(1 <= n <= 5 for n in citados(x["frase"]))]
        sim, resto = [f for f in fr if f[1]["comum"] == "apoiada"], [f for f in fr if f[1]["comum"] != "apoiada"]
        rnd.shuffle(sim), rnd.shuffle(resto)
        cota = N_FRASES // len(gs)
        pego = resto[:cota // 2]
        pego += sim[:cota - len(pego)]
        itens += [{"item": "frase", "gerador": g, "id": q, "n": x["n"], "texto": x["frase"],
                   "citados": [f"T{n}" for n in citados(x["frase"]) if 1 <= n <= 5], "matheus": None} for q, x in pego]
    frases = [x for x in itens]
    rnd.shuffle(frases)
    respostas = []
    for g in gs:
        J = julgamentos(g, base, resp)
        ok = [q for q, v in J.items() if not v["recusou"]]
        sim = [q for q in ok if J[q]["responde"]["A"] == J[q]["responde"]["B"] == "sim"]
        resto = [q for q in ok if q not in sim]
        rnd.shuffle(sim), rnd.shuffle(resto)
        cota = N_RESPOSTAS // len(gs)
        pego = resto[:cota // 2]
        pego += sim[:cota - len(pego)]
        respostas += [{"item": "resposta", "gerador": g, "id": q, "n": None, "texto": resp[g][q]["resposta"],
                       "citados": [], "matheus": None} for q in pego]
    rnd.shuffle(respostas)
    todos = [{"k": k, **x} for k, x in enumerate(frases + respostas, 1)]
    gravar(ANCORA, {"nota": "Âncora humana da medida das respostas. Sorteada uma vez por medir_respostas.py ancora (semente "
                            f"{SEMENTE}); o campo 'matheus' é preenchido pela pessoa e nunca é regenerado. Não contém o veredito dos juízes.",
                    "rotulos_frase": ROTULOS_FRASE, "rotulos_resposta": ROTULOS_RESPOSTA, "itens": todos})
    print(f"{len(todos)} itens sorteados: {len(frases)} frases e {len(respostas)} respostas")


def ancora_mostrar(a: int, b: int) -> None:
    """Imprime os itens a..b para a conversa: a pergunta, a frase e o texto dos trechos citados (ou a resposta inteira)."""
    base = ler(PASTA / "prompts.json")
    por = {i["id"]: i for i in base["itens"]}
    for x in ler(ANCORA)["itens"]:
        if not a <= x["k"] <= b:
            continue
        it = por[x["id"]]
        print(f"######## ITEM {x['k']} ({x['item']}) ########")
        print("PERGUNTA DO PROFESSOR:", it["pergunta"])
        if x["item"] == "frase":
            print("FRASE:", x["texto"])
            for ref in x["citados"]:
                t = it["trechos"][int(ref[1:]) - 1]
                print(f"--- TRECHO CITADO [{ref}]: {t['titulo']} | p. {t['pagina'] or '-'} | {t['idioma']}"
                      + (f" | AVISO DE USO: {t['nota_uso']}" if t["nao_usar_para"] else ""))
                print(t["trecho"])
        else:
            print("RESPOSTA INTEIRA:", x["texto"])
        print()


def ancora_gravar(pares: list[str]) -> None:
    """Grava as respostas da pessoa (k=rotulo). Não sobrescreve o que já foi respondido, a não ser com --corrigir."""
    d = ler(ANCORA)
    por = {x["k"]: x for x in d["itens"]}
    for par in pares:
        if par.startswith("--"):
            continue
        k, rot = par.split("=")
        x = por[int(k)]
        validos = ROTULOS_FRASE if x["item"] == "frase" else ROTULOS_RESPOSTA
        assert rot in validos, f"item {k}: rótulo {rot} não é um de {validos}"
        if x["matheus"] is not None and x["matheus"] != rot and "--corrigir" not in pares:
            raise SystemExit(f"item {k} já tem resposta ({x['matheus']}); use --corrigir para trocar")
        x["matheus"] = rot
    gravar(ANCORA, d)
    print(f"respondidos: {sum(x['matheus'] is not None for x in d['itens'])} de {len(d['itens'])}")


TERCEIRA = AQUI / "terceira_leitura_respostas.json"   # leitura da mesma amostra por um modelo; não é pessoa


def medir_ancora() -> None:
    base, resp, _ = carregar()
    d = ler(ANCORA)
    J = {g: julgamentos(g, base, resp) for g in {x["gerador"] for x in d["itens"]}}
    n_fr = sum(x["item"] == "frase" for x in d["itens"])
    humano = {x["k"]: x["matheus"] for x in d["itens"] if x["matheus"] is not None}
    terceira = {int(k): v["rotulo"] for k, v in (ler(TERCEIRA, {"itens": {}})["itens"]).items()}
    bandeira = {int(k): v.get("bandeira") or "" for k, v in (ler(TERCEIRA, {"itens": {}})["itens"]).items()}
    L = ["CONFERÊNCIA DA AMOSTRA: quem leu as 24 frases e 8 respostas sorteadas, e se concorda com os juízes de modelo.",
         f"Amostra sorteada com semente {SEMENTE}: metade entre os itens que os dois juízes aprovaram, metade entre os demais.",
         "Por isso as proporções abaixo NÃO são a nota do sistema: servem para ver se os juízes concordam com um terceiro leitor.",
         "Técnica: contagem e kappa de Cohen (concordância descontando o acaso). Nenhum modelo treinado.", "",
         f"ÂNCORA HUMANA: o avaliador humano respondeu {len(humano)} de {len(d['itens'])} itens "
         f"({', '.join(f'item {k} = {v}' for k, v in humano.items()) or 'nenhum'}) e pediu que a leitura fosse feita por modelo.",
         "CRITÉRIO (escrito antes): os juízes valem como medida se o avaliador humano concordar com o veredito comum em pelo menos 19 das 24",
         "frases e os erros não forem todos para o mesmo lado. Abaixo disso, a nota dos juízes é prata: compara geradores, não dá a nota.",
         f"RESULTADO DO CRITÉRIO: {'ÂNCORA HUMANA NÃO COLHIDA' if len([k for k in humano if k <= n_fr]) < n_fr else 'ver abaixo'}: "
         "A NOTA DOS JUÍZES FICA COMO PRATA.", ""]

    def do_juiz(x: dict) -> dict:
        return next(f for f in J[x["gerador"]][x["id"]]["frases"] if f["n"] == x["n"])

    def secao(nome: str, rot: dict[int, str]) -> None:
        fr = [x for x in d["itens"] if x["item"] == "frase" and x["k"] in rot]
        rs = [x for x in d["itens"] if x["item"] == "resposta" and x["k"] in rot]
        cols = ("apoiada", "parcial", "nao_apoiada", "divergem")
        m = Counter((rot[x["k"]], do_juiz(x)["comum"]) for x in fr)
        L.extend([f"===== {nome} =====",
                  f"1. FRASES ({len(fr)}): o trecho citado sustenta a frase? (linhas = {nome.split(':')[0].lower()}, colunas = veredito comum dos dois juízes)",
                  f"{'':14s}" + "".join(f"{c:>13s}" for c in cols) + f"{'total':>8s}"])
        for a in ROTULOS_FRASE:
            L.append(f"{a:14s}" + "".join(f"{m[(a, c)]:13d}" for c in cols) + f"{sum(m[(a, c)] for c in cols):8d}")
        conc = sum(rot[x["k"]] == do_juiz(x)["comum"] for x in fr)
        brando = sum(do_juiz(x)["comum"] == "apoiada" and rot[x["k"]] in ("parcial", "nao_apoiada") for x in fr)
        duro = sum(do_juiz(x)["comum"] in ("parcial", "nao_apoiada") and rot[x["k"]] == "apoiada" for x in fr)
        sabe = [x for x in fr if rot[x["k"]] != "nao_sei"]
        bin_ = [(rot[x["k"]] == "apoiada", do_juiz(x)["comum"] == "apoiada") for x in sabe]
        L.extend([f"igual ao veredito comum dos juízes: {conc} de {len(fr)}",
                  f"onde diferem: juízes aprovaram e o leitor não: {brando}; juízes reprovaram (parcial ou não apoiada) e o leitor aprovou: {duro}; "
                  f"juízes divergiram entre si: {sum(do_juiz(x)['comum'] == 'divergem' for x in fr)}; leitor não soube dizer: {len(fr) - len(sabe)}",
                  f"em duas classes (apoiada ou não), nas {len(sabe)} frases julgadas: iguais {sum(a == b for a, b in bin_)} de {len(bin_)}; "
                  f"kappa de Cohen {kappa(bin_):.2f}"])
        for j in "AB":
            L.append(f"igual ao juiz {j} sozinho: {sum(rot[x['k']] == do_juiz(x)[j] for x in fr)} de {len(fr)}")
        for g in sorted(J):
            sub = [x for x in fr if x["gerador"] == g]
            L.append(f"só nas frases geradas por {g}: {sum(rot[x['k']] == do_juiz(x)['comum'] for x in sub)} de {len(sub)}")
        av = [x for x in fr if "aviso" in bandeira.get(x["k"], "")]
        if av:
            L.append(f"frases que se apoiam no aviso de uso e não no texto do documento: {len(av)}; vereditos dos juízes nelas: "
                     + ", ".join(f"item {x['k']} {do_juiz(x)['A']}/{do_juiz(x)['B']}" for x in av))
        L.append("item a item (leitor | juiz A / juiz B): " + "; ".join(
            f"{x['k']} {rot[x['k']]} | {do_juiz(x)['A']}/{do_juiz(x)['B']}" for x in fr))

        def lado(x: dict) -> bool:
            r = J[x["gerador"]][x["id"]]["responde"]
            return r["A"] == r["B"] == "sim"

        mr_ = Counter((rot[x["k"]], "os dois sim" if lado(x) else "ao menos um não") for x in rs)
        L.extend(["", f"2. RESPOSTAS ({len(rs)}): a resposta responde ao que o professor perguntou? (colunas = juízes)",
                  f"{'':14s}{'os dois sim':>14s}{'ao menos um não':>18s}"])
        for a in ROTULOS_RESPOSTA:
            L.append(f"{a:14s}{mr_[(a, 'os dois sim')]:14d}{mr_[(a, 'ao menos um não')]:18d}")
        L.extend([f"leitor e juízes do mesmo lado (sim contra não-sim): "
                  f"{sum((rot[x['k']] == 'sim') == lado(x) for x in rs if rot[x['k']] != 'nao_sei')} de {sum(rot[x['k']] != 'nao_sei' for x in rs)}", ""])

    if terceira:
        secao("TERCEIRA LEITURA: modelo Claude Fable 5.1, não é pessoa", terceira)
        L.append("Limite: o terceiro leitor é um modelo do mesmo fabricante dos juízes e dos geradores. Concordar com ele não valida os juízes")
        L.append("como uma pessoa validaria; discordar mostra onde a regra do juiz admite duas leituras.")
    destino = SAIDAS / "25-respostas-ancora.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 6. segunda rodada dos juízes (regra versão 2)
REGRA2 = AQUI / "regra_juiz_respostas_v2.md"
CONTEUDO = ("apoiada", "parcial", "nao_apoiada", "rejeitado")
COMENTARIO = ("comentario_correto", "comentario_errado")


def blocos_do_gerador(item: dict) -> list[str]:
    """Os blocos [T1]..[T5] exatamente como o gerador recebeu: cabeçalho, aviso de uso e texto."""
    bloco = item["prompt"].split("TRECHOS:\n\n", 1)[1].rsplit("\n\nPERGUNTA: ", 1)[0]
    partes = re.split(r"\n\n(?=\[T\d+\] )", bloco)
    assert len(partes) == len(item["trechos"]), f"{item['id']}: {len(partes)} blocos para {len(item['trechos'])} trechos"
    return partes


def prompt_do_juiz2(item: dict, resposta: str, frase_sem: str) -> str:
    if recusou(resposta, frase_sem):
        frases = "A resposta é a recusa. Não há frases a julgar: preencha `abstencao`."
    else:
        frases = "\n".join(f"S{n}: {f}" for n, f in enumerate(frases_da_resposta(resposta), 1))
    return (REGRA2.read_text(encoding="utf-8") + f"\n\n---\n\nPERGUNTA: {item['pergunta']}\n\nTRECHOS ENTREGUES AO SISTEMA "
            "(como o sistema recebeu):\n\n" + "\n\n".join(blocos_do_gerador(item))
            + f"\n\nRESPOSTA (inteira):\n{resposta}\n\nFRASES A JULGAR:\n{frases}\n")


def julgar2(g: str, juiz: str) -> None:
    base, resp, _ = carregar()
    r = resp[g]
    destino = PASTA / f"juiz2-{juiz}-{g}.json"
    feito = ler(destino, {})
    ids = so([i["id"] for i in base["itens"]])
    faltam = [i for i in base["itens"] if i["id"] in ids and i["id"] not in feito]

    def um(item: dict) -> tuple[str, dict]:
        p = prompt_do_juiz2(item, r[item["id"]]["resposta"], base["frase_sem_resposta"])
        for _ in range(2):
            bruto, uso = chamar_claude(JUIZ_MODELO, SISTEMA_JUIZ, p)
            d = extrair_json(bruto)
            if d is not None:
                break
        return item["id"], {"json": d, "bruto": bruto if d is None else None, "uso": uso}

    with ThreadPoolExecutor(EM_PARALELO) as ex:
        for qid, v in ex.map(um, faltam):
            feito[qid] = v
            gravar(destino, feito)
            print("juiz2", juiz, g, qid, "ok" if v["json"] else "JSON INVÁLIDO", flush=True)
    print(f"juiz2 {juiz} / {g}: {len(feito)} julgamentos")


def veredito2(v: dict | None, frase: str, blocos: list[str]) -> str:
    """O veredito da versão 2, depois de conferir a prova. A passagem pode estar no texto, no cabeçalho ou no aviso."""
    if not v:
        return "sem_veredito"
    tipo, ver = v.get("tipo"), v.get("veredito")
    if tipo == "comentario" and ver in COMENTARIO:
        return ver
    if tipo != "conteudo" or ver not in ("apoiada", "parcial", "nao_apoiada"):
        return "sem_veredito"
    if ver == "nao_apoiada":
        return ver
    cit = limpar(v.get("citacao") or "")
    refs = [n for n in citados(frase) if 1 <= n <= len(blocos)]
    if len(cit.split()) < 3 or not any(cit in limpar(blocos[n - 1]) for n in refs):
        return "rejeitado"
    return ver


def julgamentos2(g: str, base: dict, resp: dict) -> dict:
    jz = {j: ler(PASTA / f"juiz2-{j}-{g}.json", {}) for j in "AB"}
    saida = {}
    for item in base["itens"]:
        qid = item["id"]
        texto = resp[g][qid]["resposta"]
        rec = recusou(texto, base["frase_sem_resposta"])
        fr = [] if rec else frases_da_resposta(texto)
        blocos = blocos_do_gerador(item)
        d = {j: (jz[j].get(qid) or {}).get("json") or {} for j in "AB"}
        linhas = []
        for n, f in enumerate(fr, 1):
            v = {}
            for j in "AB":
                bruto = next((x for x in d[j].get("frases") or [] if x.get("n") == n), None)
                v[j] = veredito2(bruto, f, blocos)
                v[j + "_outro"] = bool(bruto and bruto.get("outro_trecho"))
                v[j + "_rotulo"] = bool(bruto and bruto.get("rotulo_errado"))
            tipo = ("conteudo" if v["A"] in CONTEUDO and v["B"] in CONTEUDO else
                    "comentario" if v["A"] in COMENTARIO and v["B"] in COMENTARIO else "tipo_divergente")
            comum = v["A"] if v["A"] == v["B"] and v["A"] not in ("rejeitado", "sem_veredito") else "divergem"
            linhas.append({"n": n, "frase": f, **v, "tipo": tipo, "comum": comum, "citou": bool(citados(f))})
        resp_sim = d["A"].get("responde") == d["B"].get("responde") == "sim"
        if rec:
            caixa = "E"
        elif any(x["A"] == x["B"] and x["A"] in ("nao_apoiada", "comentario_errado") for x in linhas):
            caixa = "C"
        elif not resp_sim:
            caixa = "D"
        elif linhas and all(x["comum"] in ("apoiada", "comentario_correto") for x in linhas):
            caixa = "A"
        else:
            caixa = "B"
        saida[qid] = {"tipo": item["tipo"], "recusou": rec, "frases": linhas, "caixa": caixa,
                      "responde": {j: d[j].get("responde") for j in "AB"}, "abstencao": {j: d[j].get("abstencao") for j in "AB"}}
    return saida


def medir2() -> None:
    base, resp, certos = carregar()
    itens = base["itens"]
    com = [i["id"] for i in itens if i["tipo"] != "sem_resposta"]
    sem = [i["id"] for i in itens if i["tipo"] == "sem_resposta"]
    L = ["SEGUNDA RODADA DOS JUÍZES (regra versão 2: regra_juiz_respostas_v2.md). Mesmas 80 respostas da primeira rodada.",
         "Dois juízes de modelo (Claude Sonnet, duas chamadas que não se veem). Sem conferência humana: a nota é prata.",
         f"40 perguntas; busca {base['metodo']}, 5 trechos; prompt do pacote. Geradores Claude, não o modelo configurado no protótipo.",
         f"Técnica: modelos prontos geram e julgam; contagem; sorteio de perguntas ({N_BOOT} sorteios, semente {SEMENTE}). Nenhum modelo treinado.",
         "O que mudou da versão 1: o juiz diz primeiro se a frase é conteúdo ou comentário sobre as fontes; cabeçalho e aviso de uso",
         "contam como trecho; basta um trecho citado sustentar; e a resposta cai em uma de cinco caixas.",
         "A regra foi corrigida depois de ver a primeira rodada nas mesmas respostas: não é medida independente.", ""]
    por_g, vers = {}, {}
    for g in resp:
        if not all((PASTA / f"juiz2-{j}-{g}.json").exists() for j in "AB"):
            continue
        J = julgamentos2(g, base, resp)
        por_g[g] = J
        fr = [x for q in J.values() for x in q["frases"]]
        n = len(fr)
        tipos = Counter(x["tipo"] for x in fr)
        mesmo_tipo = tipos["conteudo"] + tipos["comentario"]
        cont = [x for x in fr if x["tipo"] == "conteudo"]
        come = [x for x in fr if x["tipo"] == "comentario"]
        c = Counter(x["comum"] for x in cont)
        L += [f"===== GERADOR {g.upper()} =====", "",
              f"1. Tipo das {n} frases",
              f"conteúdo para os dois juízes: {tipos['conteudo']} ({100 * tipos['conteudo'] / n:.1f}%); comentário para os dois: {tipos['comentario']} "
              f"({100 * tipos['comentario'] / n:.1f}%); juízes não concordam no tipo: {tipos['tipo_divergente']} ({100 * tipos['tipo_divergente'] / n:.1f}%)",
              f"juízes concordam no tipo: {mesmo_tipo} de {n} ({100 * mesmo_tipo / n:.1f}%)", "",
              f"2. Frases de conteúdo ({len(cont)}): o trecho citado sustenta a frase?",
              f"{'veredito comum dos dois juízes':34s}{'frases':>8s}{'%':>7s}"]
        for k in ("apoiada", "parcial", "nao_apoiada", "divergem"):
            L.append(f"{k:34s}{c[k]:8d}{100 * c[k] / max(len(cont), 1):7.1f}")
        m = Counter((x["A"], x["B"]) for x in cont)
        L += ["", "Matriz de concordância entre os juízes nas frases de conteúdo (linhas = juiz A, colunas = juiz B):",
              f"{'':14s}" + "".join(f"{k:>13s}" for k in CONTEUDO)]
        for a in CONTEUDO:
            L.append(f"{a:14s}" + "".join(f"{m[(a, b)]:13d}" for b in CONTEUDO))
        ig = sum(x["A"] == x["B"] for x in cont)
        um = sum("apoiada" in (x["A"], x["B"]) for x in cont)
        L += [f"mesmo veredito: {ig} de {len(cont)} ({100 * ig / max(len(cont), 1):.1f}%); kappa de Cohen {kappa([(x['A'], x['B']) for x in cont]):.2f}",
              f"apoiada para ao menos um juiz: {um} de {len(cont)} ({100 * um / max(len(cont), 1):.1f}%)",
              f"vereditos rejeitados por passagem que não existe no bloco do trecho citado: juiz A {sum(x['A'] == 'rejeitado' for x in fr)}, "
              f"juiz B {sum(x['B'] == 'rejeitado' for x in fr)}, de {n} cada",
              f"frases de conteúdo sem citação nenhuma: {sum(not x['citou'] for x in cont)}; erro de citação para os dois (está em outro trecho): "
              f"{sum(x['A_outro'] and x['B_outro'] for x in cont)}; rótulo errado para os dois: {sum(x['A_rotulo'] and x['B_rotulo'] for x in cont)}",
              "frases de conteúdo que os dois juízes reprovam (não apoiada):"]
        rep = [(q, x) for q, v in J.items() for x in v["frases"] if x["A"] == x["B"] == "nao_apoiada"]
        L += [f"   {q} S{x['n']}{'' if x['citou'] else ' (sem citação)'}{' (está em outro trecho, para os dois)' if x['A_outro'] and x['B_outro'] else ''}: {x['frase']}"
              for q, x in rep] or ["   nenhuma"]
        cc = Counter(x["comum"] for x in come)
        L += ["", f"3. Frases de comentário ({len(come)}): o que a frase diz das fontes confere?",
              f"correto para os dois: {cc['comentario_correto']}; errado para os dois: {cc['comentario_errado']}; juízes divergem: {cc['divergem']}",
              "comentários que os dois juízes consideram errados:"]
        err = [(q, x) for q, v in J.items() for x in v["frases"] if x["A"] == x["B"] == "comentario_errado"]
        L += [f"   {q} S{x['n']}: {x['frase']}" for q, x in err] or ["   nenhum"]
        cx = Counter(J[q]["caixa"] for q in com)
        ab = [float(J[q]["caixa"] in "AB") for q in com]
        lo, hi = intervalo(ab)
        so_a = [float(J[q]["caixa"] == "A") for q in com]
        lo_a, hi_a = intervalo(so_a)
        L += ["", f"4. AS CINCO CAIXAS (as {len(com)} perguntas com resposta na base)",
              f"{'caixa':58s}{'respostas':>10s}",
              f"{'A. responde e está inteira':58s}{cx['A']:10d}",
              f"{'B. responde, com frase que vai além do trecho ou em dúvida':58s}{cx['B']:10d}",
              f"{'C. tem frase que os dois juízes dizem não estar no trecho':58s}{cx['C']:10d}",
              f"{'D. responde só em parte, para ao menos um juiz':58s}{cx['D']:10d}",
              f"{'E. recusou':58s}{cx['E']:10d}",
              f"NOTA (A + B): {int(sum(ab))} de {len(com)} ({100 * media(ab):.0f}%; intervalo de 95% de {100 * lo:.0f}% a {100 * hi:.0f}%); "
              f"só A: {int(sum(so_a))} de {len(com)} ({100 * media(so_a):.0f}%; de {100 * lo_a:.0f}% a {100 * hi_a:.0f}%)",
              "caixa C: " + (", ".join(q for q in com if J[q]["caixa"] == "C") or "nenhuma"),
              "caixa E: " + (", ".join(f"{q} (juízes: {J[q]['abstencao']['A']}/{J[q]['abstencao']['B']})" for q in com if J[q]["caixa"] == "E") or "nenhuma"),
              "perguntas fora da base: " + ", ".join(
                  f"{q} {'recusou' if J[q]['recusou'] else 'RESPOSTA DADA'} (juízes: {J[q]['abstencao']['A']}/{J[q]['abstencao']['B']})" for q in sem), "",
              "5. Caixas por tipo de pergunta e por ter recebido trecho certo (gabarito do Opus, de modelo)",
              f"{'recorte':42s}" + "".join(f"{k:>5s}" for k in "ABCDE")]
        tem = {i["id"]: bool(certos[i["id"]] & {t["chunk_id"] for t in i["trechos"]}) for i in itens if i["tipo"] != "sem_resposta"}
        recortes = [(f"tipo {t}", [i["id"] for i in itens if i["tipo"] == t]) for t in dict.fromkeys(i["tipo"] for i in itens) if t != "sem_resposta"]
        recortes += [("recebeu ao menos 1 trecho certo nos 5", [q for q in tem if tem[q]]), ("não recebeu nenhum trecho certo", [q for q in tem if not tem[q]])]
        for rot, ids in recortes:
            k = Counter(J[q]["caixa"] for q in ids)
            L.append(f"{rot:42s}" + "".join(f"{k[x]:5d}" for x in "ABCDE"))
        v1 = julgamentos(g, base, resp)
        ap1 = sum(x["comum"] == "apoiada" for q in v1.values() for x in q["frases"])
        L += ["", "6. Da primeira para a segunda rodada",
              f"frases aprovadas pelos dois juízes: versão 1, {ap1} de {n} (apoiada); versão 2, {c['apoiada'] + cc['comentario_correto']} de {n} "
              f"({c['apoiada']} de conteúdo apoiadas e {cc['comentario_correto']} comentários corretos)",
              "tokens gastos pelos juízes: " + "; ".join(
                  f"juiz {j} entrada {sum(v['uso']['entrada'] for v in ler(PASTA / f'juiz2-{j}-{g}.json').values())}, "
                  f"saída {sum(v['uso']['saida'] for v in ler(PASTA / f'juiz2-{j}-{g}.json').values())}" for j in "AB"), ""]
        vers[g] = {q: {"recusou": v["recusou"], "caixa": v["caixa"], "responde": v["responde"], "abstencao": v["abstencao"],
                       "frases": [{k: x[k] for k in ("n", "A", "B", "tipo", "comum")} for x in v["frases"]]} for q, v in J.items()}
    if len(por_g) >= 2:
        a, b = list(por_g)[:2]

        def fid(J, q):
            cont = [x for x in J[q]["frases"] if x["tipo"] == "conteudo"]
            return media(x["comum"] == "apoiada" for x in cont) if cont else None

        ids = [q for q in por_g[a] if fid(por_g[a], q) is not None and fid(por_g[b], q) is not None]
        fa, fb = [fid(por_g[a], q) for q in ids], [fid(por_g[b], q) for q in ids]
        dd = [y - x for x, y in zip(fa, fb)]
        lo, hi = intervalo(dd)
        L += [f"===== {b.upper()} MENOS {a.upper()} =====",
              f"fração de frases de conteúdo apoiadas por pergunta, nas {len(ids)} perguntas que os dois responderam: "
              f"{a} {media(fa):.2f}, {b} {media(fb):.2f}; diferença {media(dd):+.2f} [{lo:+.2f} a {hi:+.2f}]",
              f"caixas A + B nas {len(com)}: {a} {sum(por_g[a][q]['caixa'] in 'AB' for q in com)}, {b} {sum(por_g[b][q]['caixa'] in 'AB' for q in com)}; "
              f"nos dois: {sum(por_g[a][q]['caixa'] in 'AB' and por_g[b][q]['caixa'] in 'AB' for q in com)}", ""]
    # a terceira leitura (modelo, não pessoa), refeita nas categorias da versão 2 antes de os juízes rodarem
    t = ler(TERCEIRA, {})
    if t.get("itens_v2") and por_g:
        anc = [x for x in ler(ANCORA)["itens"] if x["item"] == "frase" and x["gerador"] in por_g]
        rot = {int(k): v for k, v in t["itens_v2"].items()}

        def do_juiz(x: dict) -> dict:
            fr2 = por_g[x["gerador"]][x["id"]]["frases"]
            return next((f for f in fr2 if x["texto"] in f["frase"]), None) or next(f for f in fr2 if f["n"] == x["n"])

        cols = ("apoiada", "parcial", "nao_apoiada", "comentario_correto", "comentario_errado", "divergem")
        m = Counter((rot[x["k"]], do_juiz(x)["comum"]) for x in anc)
        L += [f"===== TERCEIRA LEITURA (modelo Claude Fable 5.1, NÃO é pessoa) nas {len(anc)} frases da amostra =====",
              "Gravada antes de os juízes da segunda rodada rodarem. Linhas = terceira leitura; colunas = veredito comum dos dois juízes.",
              f"{'':20s}" + "".join(f"{k[:11]:>12s}" for k in cols)]
        for r_ in ("apoiada", "parcial", "nao_apoiada", "comentario_correto", "comentario_errado"):
            if any(m[(r_, k)] for k in cols):
                L.append(f"{r_:20s}" + "".join(f"{m[(r_, k)]:12d}" for k in cols))
        ig = sum(rot[x["k"]] == do_juiz(x)["comum"] for x in anc)
        brando = sum(do_juiz(x)["comum"] in ("apoiada", "comentario_correto") and rot[x["k"]] not in ("apoiada", "comentario_correto") for x in anc)
        duro = sum(do_juiz(x)["comum"] in ("parcial", "nao_apoiada", "comentario_errado") and rot[x["k"]] in ("apoiada", "comentario_correto") for x in anc)
        L += [f"igual ao veredito comum dos juízes: {ig} de {len(anc)}; juízes aprovaram e o leitor não: {brando}; "
              f"juízes reprovaram e o leitor aprovou: {duro}; juízes divergiram entre si: {sum(do_juiz(x)['comum'] == 'divergem' for x in anc)}",
              "item a item (leitor | juiz A / juiz B): " + "; ".join(
                  f"{x['k']} {rot[x['k']]} | {do_juiz(x)['A']}/{do_juiz(x)['B']}" for x in anc), ""]
    gravar(AQUI / "respostas_vereditos_v2.json", vers)
    destino = SAIDAS / "26-respostas-juizes-v2.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 7. as perguntas práticas de professor, em três camadas
def praticas() -> None:
    """Para cada pergunta do tipo 'estrategia': o que a base tem (gabarito do Opus), onde os trechos certos ficaram na busca
    e o que o gerador fez. Regra de classificação e expectativa em RESPOSTAS.md, commitadas antes."""
    import consultar
    from ingestao import carregar_chunks
    base, resp, _ = carregar()
    por_chunk = {c["chunk_id"]: c for c in carregar_chunks()}
    gab = {i["id"]: i for i in ler(GABARITO)["itens"]}
    itens = [i for i in base["itens"] if i["tipo"] == "estrategia"]
    J = {g: julgamentos2(g, base, resp) for g in resp}
    L = ["AS 10 PERGUNTAS PRÁTICAS DE PROFESSOR (tipo 'estrategia'), EM TRÊS CAMADAS: a base, a busca, o gerador.",
         "Técnica: contagem. 'Trecho certo' = marcado com nota 2 (responde direto) no gabarito do Opus; 'parcial' = nota 1.",
         "O gabarito é de modelo, sem conferência humana, e avisa que pode ter deixado passar trechos. Nenhum modelo treinado.",
         f"Busca: {base['metodo']} ({base['banco']}): o Qwen3 traz 50 candidatos, o reranker reordena, os 5 primeiros vão ao gerador.",
         "Caixas da segunda rodada dos juízes: A inteira, B responde com frase além do trecho, C frase reprovada, D responde só em parte, E recusou.", ""]
    linhas, causas, vagas = [], Counter(), Counter()
    en_certos = tot_certos = 0
    sem_certo, sem_certo_nos50 = [], []
    for it in itens:
        q = it["id"]
        g2, g1 = set(gab[q]["trechos_relevantes"]), set(gab[q].get("trechos_parciais", []))
        cand = [cid for cid, _ in consultar.ranking(it["pergunta"], "qwen3", consultar.CANDIDATOS_RERANK_FUNDO)]   # os 50 que o reranker lê
        rr = [cid for cid, _ in consultar.reranquear(it["pergunta"], cand)]                                        # depois do reranker
        top5 = [t["chunk_id"] for t in it["trechos"]]                                                              # o que foi ao gerador
        pos_q = sorted(cand.index(c) + 1 for c in g2 if c in cand)
        pos_r = sorted(rr.index(c) + 1 for c in g2 if c in rr)
        n5 = len(g2 & set(top5))
        for c in top5:
            vagas["certo" if c in g2 else "parcial" if c in g1 else "nenhum"] += 1
            vagas["abda"] += c.startswith("ABDA")
            vagas["en"] += por_chunk[c]["idioma"] == "en"
        en_certos += sum(por_chunk[c]["idioma"] == "en" for c in g2)
        tot_certos += len(g2)
        if n5 == 0:
            sem_certo.append(q)
            if pos_q:
                sem_certo_nos50.append(q)
        docs = Counter(c.split("#")[0] for c in g2)
        L += [f"===== {q} ({gab[q]['barreira']}; confiança de quem marcou: {gab[q]['confianca']}) =====",
              f"pergunta: {it['pergunta']}",
              f"1. BASE: {len(g2)} trechos certos e {len(g1)} parciais; em inglês: {sum(por_chunk[c]['idioma'] == 'en' for c in g2)} de {len(g2)}; "
              f"documentos: {', '.join(f'{d} ({n})' for d, n in docs.most_common())}",
              f"2. BUSCA: trechos certos entre os 50 do Qwen3: {len(pos_q)} de {len(g2)} (posições {pos_q or '-'}); "
              f"depois do reranker: posições {pos_r or '-'}; entre os 5 entregues: {n5} de {len(g2)}",
              "   os 5 entregues: " + "; ".join(
                  f"{c} [{'CERTO' if c in g2 else 'parcial' if c in g1 else 'não marcado'}, {por_chunk[c]['idioma']}]" for c in top5)]
        for g in resp:
            v = J[g][q]
            cit = {top5[n - 1] for x in v["frases"] for n in citados(x["frase"]) if 1 <= n <= 5}
            cont = [x for x in v["frases"] if x["tipo"] == "conteudo"]
            L.append(f"3. GERADOR {g}: caixa {v['caixa']}; responde: {v['responde']['A']}/{v['responde']['B']}; "
                     + ("recusou" if v["recusou"] else
                        f"citou {len(cit & g2)} trecho(s) certo(s), {len(cit & g1)} parcial(is) e {len(cit - g2 - g1)} não marcado(s); "
                        f"frases de conteúdo apoiadas para os dois juízes: {sum(x['comum'] == 'apoiada' for x in cont)} de {len(cont)}"))
            if v["caixa"] in "DE":
                if n5 == 0:
                    causa = "a busca não entregou (segunda etapa: reranker)" if pos_q else "a busca não entregou (primeira etapa: Qwen3)"
                elif gab[q]["confianca"] == "baixa":
                    causa = "a base trata só de perto"
                elif n5 < len(g2) / 2:
                    causa = "entregou pouco"
                else:
                    causa = "entregou e não bastou"
                causas[causa] += 1
                L.append(f"   causa pela regra: {causa}")
        linhas.append((q, gab[q]["confianca"], len(g2), len(pos_q), n5, J["haiku"][q]["caixa"] if "haiku" in J else "-",
                       J["opus"][q]["caixa"] if "opus" in J else "-"))
        L.append("")
    L += ["===== RESUMO =====",
          f"{'pergunta':9s}{'confiança':>11s}{'certos':>8s}{'nos 50':>8s}{'nos 5':>7s}{'haiku':>7s}{'opus':>6s}"]
    for q, conf, n2, n50, n5, ch, co in linhas:
        L.append(f"{q:9s}{conf:>11s}{n2:8d}{n50:8d}{n5:7d}{ch:>7s}{co:>6s}")
    tot = sum(vagas[k] for k in ("certo", "parcial", "nenhum"))
    L += ["", f"perguntas sem nenhum trecho certo entre os 5 entregues: {len(sem_certo)} de {len(itens)} ({', '.join(sem_certo) or '-'}); "
              f"dessas, com trecho certo entre os 50 que o reranker lê: {len(sem_certo_nos50)} ({', '.join(sem_certo_nos50) or '-'})",
          f"vagas dos 5 entregues ({tot}): trecho certo {vagas['certo']}; parcial {vagas['parcial']}; não marcado {vagas['nenhum']} "
          f"({100 * vagas['nenhum'] / tot:.0f}%); da cartilha da ABDA {vagas['abda']} ({100 * vagas['abda'] / tot:.0f}%); em inglês {vagas['en']} ({100 * vagas['en'] / tot:.0f}%)",
          f"trechos certos das {len(itens)} perguntas que estão em inglês: {en_certos} de {tot_certos} ({100 * en_certos / tot_certos:.0f}%)",
          f"trechos certos que estão entre os 50 do Qwen3: {sum(x[3] for x in linhas)} de {tot_certos}; entre os 5 entregues: {sum(x[4] for x in linhas)} de {tot_certos}",
          "", f"CAUSAS, pela regra escrita antes, das {sum(causas.values())} respostas em D ou E (2 geradores × 10 perguntas):"]
    L += [f"   {n:2d}  {c}" for c, n in causas.most_common()]
    destino = SAIDAS / "27-perguntas-praticas.txt"
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "preparar":
        preparar()
    elif cmd == "gerar":
        gerar_respostas(sys.argv[2])
    elif cmd == "conferir":
        conferir()
    elif cmd == "julgar":
        julgar(sys.argv[2], sys.argv[3])
    elif cmd == "medir":
        medir()
    elif cmd == "ancora":
        ancora()
    elif cmd == "ancora-mostrar":
        ancora_mostrar(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "ancora-gravar":
        ancora_gravar(sys.argv[2:])
    elif cmd == "medir-ancora":
        medir_ancora()
    elif cmd == "julgar2":
        julgar2(sys.argv[2], sys.argv[3])
    elif cmd == "medir2":
        medir2()
    elif cmd == "praticas":
        praticas()
    else:
        raise SystemExit(f"comando desconhecido: {cmd}")
