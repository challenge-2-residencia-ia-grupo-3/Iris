"""demonstrar_resposta.py: demonstração do fluxo completo do protótipo.

    consulta -> trechos recuperados -> resposta fundamentada -> evidência das fontes

    python demonstrar_resposta.py            7 consultas, com respostas registradas (outputs/05-consulta-resposta-fonte.txt)
    python demonstrar_resposta.py --todas    as 40 consultas do conjunto de avaliação
    python demonstrar_resposta.py --ao-vivo  geração da resposta pelo modelo configurado em gerar.py
    python demonstrar_resposta.py --registrar-passagens   regrava respostas_passagens_v2.json a partir do cache

Origem de cada parte:
1. Consulta: gabarito/perguntas_v0.json (40 consultas elaboradas antes da execução da busca).
   Por padrão são apresentadas 7: a primeira consulta de cada tipo, na ordem do arquivo.
2. Trechos: os 5 retornados pelo método de recuperação padrão (consultar.buscar).
3. Resposta: gerada por modelo de linguagem a partir da consulta e dos 5 trechos, com as
   instruções de gerar.montar_prompt. Cada frase termina com a citação [T1]..[T5].
   As respostas registradas (respostas_medidas.json) foram geradas em 05/11/2026 por modelo Claude.
   A opção --ao-vivo executa a geração com o modelo configurado em gerar.py.
4. Evidência: para cada frase, o trecho citado, a classificação de dois avaliadores automáticos
   e a passagem do trecho que sustenta a frase; em seguida, as fontes e a verificação das citações.

Nenhum modelo é treinado. Os avaliadores são duas instâncias independentes de modelo de linguagem
(regra_juiz_respostas_v2.md); não houve validação humana.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import consultar                                   # recuperação no pgvector
import gerar                                       # instruções, verificação das citações e modelo gerador
# De medir_respostas são reutilizadas três funções de texto.
from medir_respostas import citados, frases_da_resposta, limpar

AQUI = Path(__file__).resolve().parent
PERGUNTAS = AQUI.parent / "gabarito" / "perguntas_v0.json"
GRAVADAS = AQUI / "respostas_medidas.json"                 # respostas registradas e identificadores dos trechos
VEREDITOS = AQUI / "respostas_vereditos_v2.json"           # classificação de cada frase pelos dois avaliadores
PASSAGENS = AQUI / "respostas_passagens_v2.json"           # passagem verificada de cada frase (texto de licença restrita omitido)
SAIDAS_DOS_AVALIADORES = AQUI / "cache" / "respostas"      # saídas completas dos avaliadores (não versionadas)
SAIDA = AQUI / "outputs" / "05-consulta-resposta-fonte.txt"
GERADOR = "haiku"                # conjunto de respostas registradas utilizado por padrão
LARGURA = 220                    # caracteres exibidos do início de cada trecho

TIPOS = {"estrategia": "prática docente", "dua": "Desenho Universal para a Aprendizagem",
         "norma": "norma", "evidencia": "evidência de pesquisa", "mito": "neuromito",
         "so_ingles": "resposta disponível apenas em inglês", "sem_resposta": "sem resposta na base"}
VEREDITO = {"apoiada": "sustentada", "parcial": "parcialmente sustentada", "nao_apoiada": "não sustentada",
            "rejeitado": "classificação descartada (passagem transcrita não consta no trecho)",
            "sem_veredito": "sem classificação", "comentario_correto": "comentário correto sobre a fonte",
            "comentario_errado": "comentário incorreto sobre a fonte"}


def ler(caminho: Path, padrao=None):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


# ---------------------------------------------------------------- o banco
def ligar_banco() -> str | None:
    """Conecta a recuperação ao banco e retorna a identificação do banco. None = banco indisponível.

    A demonstração abre conexão própria, somente de leitura: banco_pg.conectar
    executa CREATE EXTENSION, que é comando de escrita."""
    try:
        import psycopg
        from pgvector.psycopg import register_vector
        import banco_pg
        con = psycopg.connect(banco_pg.DSN, autocommit=True, connect_timeout=5)
        register_vector(con)                                       # habilita o tipo vector no psycopg
        consultar._pg = lambda: (banco_pg, con)                    # a recuperação passa a utilizar esta conexão
        pg = con.execute("show server_version").fetchone()[0].split()[0]
        ext = con.execute("select extversion from pg_extension where extname='vector'").fetchone()[0]
        n = con.execute(f"select count(*) from {banco_pg.TABELA}").fetchone()[0]
        return f"PostgreSQL {pg} com pgvector {ext}, tabela {banco_pg.TABELA}, {n} trechos"
    except Exception as e:                                         # sem banco, as respostas registradas ainda são exibidas
        print(f"[banco indisponível: {type(e).__name__}] a recuperação não será reproduzida; --ao-vivo requer o banco")
        return None


# ---------------------------------------------------------------- os trechos
def fechados() -> set[str]:
    """Documentos sem licença aberta: os textos listados em ../textos_nao_distribuidos.txt."""
    ignorados = [l.strip().split("/", 1)[1] for l in (AQUI.parent / "textos_nao_distribuidos.txt").read_text(encoding="utf-8").splitlines()
                 if l.strip().startswith("texto/")]
    docs = ler(AQUI.parent / "fontes.json")["documentos"]
    return {d["id"] for d in docs if any(str(d.get("arquivo_texto") or "").endswith(i) for i in ignorados)}


def trecho(chunk_id: str, posicao: int) -> dict:
    """Trecho com os metadados de citação, nos mesmos campos retornados por consultar.buscar."""
    c = consultar._base()[1][chunk_id]
    pag = (None if c["pagina_inicio"] is None else str(c["pagina_inicio"]) if c["pagina_inicio"] == c["pagina_fim"]
           else f"{c['pagina_inicio']}-{c['pagina_fim']}")
    return {"posicao": posicao, "chunk_id": chunk_id, "doc": c["doc_id"], "titulo": c["titulo"], "pagina": pag,
            "secao": c["secao"], "idioma": c["idioma"], "tipo_evidencia": c["tipo_evidencia"], "url": c["url"],
            "nao_usar_para": c["nao_usar_para"], "nota_uso": c["nota_uso"], "trecho": c["texto"]}


def inicio_do_trecho(t: dict, fech: set[str], largura: int = LARGURA) -> str:
    """Início do texto do trecho. Texto de documento sem licença aberta não é reproduzido."""
    if t["doc"] in fech:
        return "(texto não reproduzido por restrição de licença; consultar o endereço de origem)"
    return '"' + re.sub(r"\s+", " ", t["trecho"])[:largura] + '..."'


# ---------------------------------------------------------------- uma consulta
def escolher(todas: bool = False) -> list[dict]:
    itens = ler(PERGUNTAS)["itens"]
    if todas:
        return itens
    primeira = {}
    for q in itens:
        primeira.setdefault(q["tipo"], q)                          # primeira consulta de cada tipo, na ordem do arquivo
    return list(primeira.values())


def registrar_passagens() -> None:
    """Grava respostas_passagens_v2.json a partir das saídas completas dos avaliadores (cache).

    Para cada frase, registra a primeira passagem transcrita por um avaliador (A, depois B) que consta
    literalmente em um dos trechos citados. Quando o trecho é de documento sem licença aberta, registra
    somente que a passagem foi verificada, sem o texto. Para recusas, registra o trecho indicado por
    cada avaliador."""
    fech = fechados()
    gravadas = ler(GRAVADAS)["geradores"]
    registro: dict = {}
    for gerador, respostas in gravadas.items():
        saidas = {j: ler(SAIDAS_DOS_AVALIADORES / f"juiz2-{j}-{gerador}.json") for j in "AB"}
        assert all(saidas.values()), f"saídas dos avaliadores ausentes para {gerador}"
        registro[gerador] = {}
        for qid, g in respostas.items():
            trechos = [trecho(c, i) for i, c in enumerate(g["fontes"], 1)]
            por_juiz = {j: (saidas[j].get(qid) or {}).get("json") or {} for j in "AB"}
            frases = {}
            for n, f in enumerate(frases_da_resposta(g["resposta"]), 1):
                refs = [r for r in citados(f) if 1 <= r <= len(trechos)]
                achada = None
                for j in "AB":
                    fr = {x["n"]: x for x in por_juiz[j].get("frases", [])}.get(n)
                    cit = (fr or {}).get("citacao") or ""
                    if len(limpar(cit).split()) < 3:
                        continue
                    for r in refs:
                        if limpar(cit) in limpar(trechos[r - 1]["trecho"]):
                            achada = ({"trecho": r, "restrita": True} if trechos[r - 1]["doc"] in fech
                                      else {"trecho": r, "passagem": re.sub(r"\s+", " ", cit).strip()})
                            break
                    if achada:
                        break
                if achada:
                    frases[str(n)] = achada
            recusa = {j: por_juiz[j].get("trecho_abstencao") for j in "AB" if por_juiz[j].get("trecho_abstencao")}
            registro[gerador][qid] = {"frases": frases, **({"abstencao": recusa} if recusa else {})}
    PASSAGENS.write_text(json.dumps(registro, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    n = sum(len(q["frases"]) for g in registro.values() for q in g.values())
    r = sum(1 for g in registro.values() for q in g.values() for f in q["frases"].values() if f.get("restrita"))
    print(f"{PASSAGENS.name}: {n} frases com passagem verificada; {r} com texto omitido por restrição de licença")


def uma_consulta(q: dict, banco: str | None, ao_vivo: bool = False, gerador: str = GERADOR) -> dict:
    """Monta a demonstração de uma consulta. Retorna um dicionário, formatado por texto_da_consulta()."""
    item = {"id": q["id"], "tipo": q["tipo"], "pergunta": q["pergunta"], "ao_vivo": ao_vivo, "juizes": None,
            "busca_agora": None}
    if ao_vivo:                                                    # recuperação e geração nesta execução
        metodo_busca = consultar.METODO_PADRAO if banco else "bm25"
        r = gerar.responder(q["pergunta"], metodo=metodo_busca)
        ids, item["resposta"], item["modelo"] = [f["chunk_id"] for f in r["fontes"]], r["resposta"], r["llm"]
    else:                                                          # resposta registrada e trechos utilizados na geração
        g = ler(GRAVADAS)["geradores"][gerador][q["id"]]
        ids, item["resposta"], item["modelo"] = g["fontes"], g["resposta"], g["modelo"]
        if banco:                                                  # reproduz a recuperação e compara as listas
            agora = [t["chunk_id"] for t in consultar.buscar(q["pergunta"])]
            item["busca_agora"] = {"iguais": agora == ids, "em_comum": len(set(agora) & set(ids)),
                                   "sairam": [c for c in ids if c not in agora],
                                   "entraram": [c for c in agora if c not in ids]}
        v = (ler(VEREDITOS) or {}).get(gerador, {}).get(q["id"])
        passagens = (ler(PASSAGENS, {}).get(gerador) or {}).get(q["id"]) or {}
        item["juizes"] = {"vereditos": v, "passagens": passagens} if v else None
    item["trechos"] = [trecho(c, i) for i, c in enumerate(ids, 1)]
    item["frases"] = frases_da_resposta(item["resposta"])
    c = gerar.conferir(item["resposta"], item["trechos"])          # verificação automática das citações, sem modelo
    item["conferencia"] = {"recusou": c["absteve"], "citacoes_invalidas": c["citacoes_invalidas"],
                           "citou_trecho_com_aviso": c["citou_trecho_com_aviso"],
                           "frases_sem_citacao": 0 if c["absteve"] else sum(1 for f in item["frases"] if not citados(f)),
                           "trechos_citados": c["trechos_citados"]}
    return item


def _passagem(item: dict, n: int) -> str | None:
    """Passagem verificada da frase n, conforme respostas_passagens_v2.json."""
    p = (item["juizes"]["passagens"].get("frases") or {}).get(str(n))
    if not p:
        return None
    if p.get("restrita"):
        return f"(verificada no T{p['trecho']}; não reproduzida por restrição de licença)"
    return f'no T{p["trecho"]}: "{p["passagem"]}"'


def texto_da_consulta(item: dict, fech: set[str] | None = None, largura: int = LARGURA) -> str:
    fech = fechados() if fech is None else fech
    L = [f"CONSULTA {item['id']} ({TIPOS.get(item['tipo'], item['tipo'])})", "",
         "1. CONSULTA SUBMETIDA", f"   {item['pergunta']}", "",
         f"2. TRECHOS RECUPERADOS (método {consultar.METODO_PADRAO}; 5 trechos entregues ao modelo gerador)"]
    for t in item["trechos"]:
        rotulo = ", ".join(x for x in (t["idioma"], t["tipo_evidencia"]) if x)
        L.append(f"   [T{t['posicao']}] {t['doc']} | p. {t['pagina'] or '-'} | {t['secao'][:60]} [{rotulo}]")
        L.append(f"        {t['url']}")
        if t["nao_usar_para"]:
            L.append(f"        AVISO DE USO: {t['nota_uso'][:200]}")
        L.append("        " + inicio_do_trecho(t, fech, largura))
    b = item["busca_agora"]
    if b and b["iguais"]:
        L.append("   Recuperação reproduzida nesta execução: lista idêntica.")
    elif b:
        L.append(f"   Recuperação reproduzida nesta execução: {b['em_comum']} de 5 trechos coincidem. Ausente: {', '.join(b['sairam'])}; "
                 f"incluído: {', '.join(b['entraram'])}.")
        L.append("   A resposta registrada foi gerada a partir dos 5 trechos listados acima.")
    L += ["", f"3. RESPOSTA FUNDAMENTADA (modelo gerador: {item['modelo']}; entrada: consulta e 5 trechos)"]
    L += [f"   {f}" for f in item["frases"]] or [f"   {item['resposta']}"]
    L += ["", "4. EVIDÊNCIA DAS FONTES"]
    c, j = item["conferencia"], item["juizes"]
    if c["recusou"]:
        L.append("   Recusa: o modelo gerador declarou insuficiência de informação nos trechos.")
        for k in "AB":
            indicado = (((j or {}).get("passagens") or {}).get("abstencao") or {}).get(k)
            ab = ((j or {}).get("vereditos") or {}).get("abstencao", {}).get(k)
            if ab:
                if ab == "indevida":                               # algum trecho responde, ao menos parcialmente
                    qual = indicado or "um dos trechos"
                    L.append(f"   Avaliador {k}: recusa classificada como indevida ({qual} responde parcialmente à consulta).")
                else:
                    L.append(f"   Avaliador {k}: recusa classificada como correta (nenhum dos 5 trechos responde à consulta).")
    else:
        vs = {v["n"]: v for v in ((j or {}).get("vereditos") or {}).get("frases", [])}
        alinhado = len(vs) == len(item["frases"])                  # mesma divisão em frases utilizada na avaliação
        for n, f in enumerate(item["frases"], 1):
            refs = [r for r in citados(f) if 1 <= r <= len(item["trechos"])]
            onde = "; ".join(f"T{r} = {item['trechos'][r - 1]['doc']}, p. {item['trechos'][r - 1]['pagina'] or '-'}" for r in refs)
            L.append(f"   frase {n}: citação {onde or 'ausente'}")
            if alinhado:
                v = vs[n]
                L.append(f"            avaliador A: {VEREDITO.get(v['A'], v['A'])} | avaliador B: {VEREDITO.get(v['B'], v['B'])}")
                p = _passagem(item, n)
                if p:
                    L.append(f"            passagem {p}")
        if not j:
            L.append("   (resposta gerada nesta execução; não avaliada)")
    cit = c["trechos_citados"]
    usadas = ", ".join(f"T{n}" for n in cit) or "nenhuma"
    sobras = ", ".join(f"T{t['posicao']}" for t in item["trechos"] if t["posicao"] not in cit) or "nenhuma"
    L.append(f"   Trechos citados na resposta: {usadas}; entregues e não citados: {sobras}.")
    L.append(f"   Verificação automática: citações de trecho inexistente: {len(c['citacoes_invalidas'])}; "
             f"frases sem citação: {c['frases_sem_citacao']} de {len(item['frases']) if not c['recusou'] else 0}; "
             f"trechos com aviso de uso citados: {', '.join(c['citou_trecho_com_aviso']) or 'nenhum'}.")
    return "\n".join(L)


def resumo(itens: list[dict]) -> list[str]:
    """Uma linha por consulta: frases, classificação pelos avaliadores e verificação automática.
    Contagem dos dados apresentados em cada consulta."""
    L = ["RESUMO",
         "sustentadas: frases classificadas como sustentadas pelos dois avaliadores",
         "demais: parcialmente sustentadas, classificações divergentes ou classificação descartada",
         "",
         f"{'consulta':9s} {'tipo':38s} {'frases':>7s} {'sustentadas':>12s} {'demais':>8s} {'comentário':>11s} "
         f"{'citação de trecho':>18s} {'frases sem':>11s} {'recuperação':>12s}",
         f"{'':9s} {'':38s} {'':>7s} {'':>12s} {'':>8s} {'da fonte':>11s} {'inexistente':>18s} "
         f"{'citação':>11s} {'reproduzida':>12s}"]
    for i in itens:
        c, b = i["conferencia"], i["busca_agora"]
        vs = ((i["juizes"] or {}).get("vereditos") or {}).get("frases", [])
        igual = "-" if b is None else "idêntica" if b["iguais"] else f"{b['em_comum']} de 5"
        if c["recusou"]:
            L.append(f"{i['id']:9s} {TIPOS.get(i['tipo'], i['tipo'])[:38]:38s} {'recusa':>7s} {'-':>12s} {'-':>8s} {'-':>11s} "
                     f"{len(c['citacoes_invalidas']):>18d} {'-':>11s} {igual:>12s}")
            continue
        apo = sum(1 for v in vs if v["comum"] == "apoiada")
        com = sum(1 for v in vs if v["tipo"] == "comentario")
        resto = len(vs) - apo - com
        j = (lambda x: f"{x:d}") if vs else (lambda x: "-")
        L.append(f"{i['id']:9s} {TIPOS.get(i['tipo'], i['tipo'])[:38]:38s} {len(i['frases']):>7d} {j(apo):>12s} {j(resto):>8s} "
                 f"{j(com):>11s} {len(c['citacoes_invalidas']):>18d} {c['frases_sem_citacao']:>11d} {igual:>12s}")
    todos = [v for i in itens for v in ((i["juizes"] or {}).get("vereditos") or {}).get("frases", [])]
    if todos:
        nao = sum(1 for v in todos if "nao_apoiada" in (v["A"], v["B"]))
        L.append("")
        L.append(f"Frases classificadas como não sustentadas por ao menos um avaliador: {nao} de {len(todos)}.")
    return L


# ---------------------------------------------------------------- execução
def demonstrar(todas: bool = False, ao_vivo: bool = False, caminho: Path | None = SAIDA) -> list[dict]:
    """Executa a demonstração e grava o texto em caminho, quando informado. Retorna os itens."""
    banco = ligar_banco()
    if ao_vivo and not banco:
        print("[demonstrar] banco vetorial indisponível; usando busca lexical BM25 em memória para --ao-vivo.")
    itens = [uma_consulta(q, banco, ao_vivo) for q in escolher(todas)]
    fech = fechados()
    refeitas = [i for i in itens if i["busca_agora"]]
    L = ["ÍRIS - DEMONSTRAÇÃO DO FLUXO COMPLETO DO PROTÓTIPO DE RAG",
         "consulta -> trechos recuperados -> resposta fundamentada -> evidência das fontes", "",
         f"Consultas: {len(itens)} de {len(ler(PERGUNTAS)['itens'])} ({'conjunto completo' if todas else 'primeira consulta de cada tipo'}), "
         "elaboradas antes da execução da busca.",
         f"Recuperação: {consultar.METODO_PADRAO} (50 candidatos por busca vetorial; reordenação por cross-encoder; 5 trechos entregues).",
         f"Banco: {banco or 'indisponível nesta execução; trechos lidos de chunks.jsonl pelo identificador registrado'}."]
    if ao_vivo:
        L.append(f"Respostas: geradas nesta execução pelo modelo configurado ({gerar.LLM}:{gerar.MODELO}); instruções de gerar.py; não avaliadas.")
    else:
        L += [f"Respostas: registradas em 05/11/2026; modelo gerador {itens[0]['modelo']}; instruções de gerar.py.",
              "           O modelo configurado no protótipo (Qwen, via Groq) não foi utilizado; a opção --ao-vivo executa a geração",
              "           com esse modelo.",
              "Avaliadores: duas instâncias independentes de modelo de linguagem (Claude Sonnet); regra em regra_juiz_respostas_v2.md;",
              "             sem validação humana. A classificação exige a transcrição da passagem do trecho, conferida literalmente."]
        if refeitas:
            L.append(f"Recuperação reproduzida nesta execução: lista de 5 trechos idêntica à utilizada na geração em "
                     f"{sum(i['busca_agora']['iguais'] for i in refeitas)} de {len(refeitas)} consultas.")
    L += ["Texto de documento sem licença aberta não é reproduzido; são indicados documento, seção, página e endereço de origem.",
          "Resultados do conjunto completo: ../../outputs/23-respostas-conferencia.txt e ../../outputs/26-respostas-juizes-v2.txt.",
          "Nenhum modelo foi treinado.", ""]
    L += resumo(itens) + [""]
    for i in itens:
        L += ["=" * 110, texto_da_consulta(i, fech), ""]
    texto_final = "\n".join(L) + "\n"
    if caminho and (banco or ao_vivo or not caminho.exists()):
        caminho.parent.mkdir(exist_ok=True)
        caminho.write_text(texto_final, encoding="utf-8")
    if __name__ == "__main__":
        print(texto_final, end="")
    return itens


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--todas", action="store_true", help="as 40 consultas do conjunto de avaliação")
    ap.add_argument("--ao-vivo", action="store_true", help="gera as respostas com o modelo configurado (GROQ_API_KEY ou RAG_LLM=ollama)")
    ap.add_argument("--registrar-passagens", action="store_true", help="regrava respostas_passagens_v2.json a partir do cache dos avaliadores")
    a = ap.parse_args()
    if a.registrar_passagens:
        registrar_passagens()
        raise SystemExit(0)
    destino = SAIDA.with_name(SAIDA.stem + ("-todas" if a.todas else "") + ("-ao-vivo" if a.ao_vivo else "") + ".txt")
    demonstrar(a.todas, a.ao_vivo, destino)
