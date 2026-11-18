"""gerar.py: a resposta fundamentada, com citação de fonte (etapa "G" do RAG).

    responder(pergunta, metodo="hibrido+rerank", k=5) -> dict com resposta, citações, trechos e conferência

Como funciona:
1. busca os k trechos (consultar.buscar);
2. monta o prompt: regras + trechos numerados [T1]..[Tk] com documento e página + pergunta;
3. o LLM responde SÓ com o que está nos trechos, citando [Tn] em cada frase; se os trechos não
   bastam, responde exatamente FRASE_SEM_RESPOSTA;
4. conferência automática (sem LLM): cada [Tn] citado existe? toda frase tem citação? aviso de
   uso (nao_usar_para) foi citado como evidência?

LLM: Qwen (qwen/qwen3.8-27b) pelo Groq, plano gratuito, só com documentos públicos e perguntas de
teste (nada de dado de aluno). Troca por Ollama local com RAG_LLM=ollama (modelo em RAG_LLM_MODELO,
padrão qwen3:8b), para quando houver dado sensível.
Com RAG_LLM=anthropic o gerador usa a API da Anthropic: Haiku no esforço baixo por padrão (issue #86);
outro modelo Claude em RAG_LLM_MODELO, esforço em RAG_ANTHROPIC_ESFORCO. Só a pergunta e os trechos
de documentos públicos saem da máquina.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import consultar

AQUI = Path(__file__).resolve().parent
FRASE_SEM_RESPOSTA = "Não encontrei nos documentos da base informação suficiente para responder."
LLM = os.environ.get("RAG_LLM", "groq")
MODELO = os.environ.get("RAG_LLM_MODELO", "qwen/qwen3.8-27b" if LLM == "groq" else "qwen3:8b")

INSTRUCOES = f"""Você é o Agente Estrategista do Íris, que apoia professores a adaptar atividades para alunos
com TDAH sem reduzir a habilidade avaliada. Responda em português do Brasil.

Regras:
1. Use SOMENTE os trechos em TRECHOS. Não use conhecimento próprio, nem para completar, nem crie questões ou alternativas fora dos trechos.
2. TODA frase da resposta deve terminar obrigatoriamente com a citação do trecho que a sustenta antes do ponto final, no formato [T1], [T2] etc. Exemplo: "A segmentação do enunciado reduz a sobrecarga da memória de trabalho [T1]." Uma frase pode citar mais de um trecho: [T1][T3].
3. Nunca escreva uma frase de introdução, transição ou recomendação sem [Tn] explícito no final.
4. Se um trecho estiver em inglês, use o conteúdo dele e responda em português, mantendo a citação [Tn] fiel ao texto original sem extrapolar detalhes ausentes.
5. Se um trecho tiver AVISO DE USO, respeite o aviso (ex.: não use cartilha sem referências como prova de eficácia; não use norma revogada como regra vigente).
6. A base reúne evidências sobre barreiras do TDAH, carga cognitiva e DUA (sem citar disciplinas ou séries escolares específicas). Se os trechos trouxerem estratégias aplicáveis à barreira ou ao tipo de atividade perguntada, responda aplicando-as com base estrita nos trechos [Tn]; só responda exatamente: "{FRASE_SEM_RESPOSTA}" e nada mais quando nenhum trecho trouxer evidência aplicável à barreira/tema ou quando faltar o fato/norma pedido. É melhor não inventar.
7. Diferencie o que é evidência de pesquisa, o que é norma e o que é orientação prática.
8. No máximo 6 frases. Sem introdução, sem conclusão genérica."""

# Duas regras a mais, medidas só com o Haiku (issue #86, 17/11/2026): pedir esclarecimento quando a pergunta é
# vaga e recusar quando os trechos só rodeiam o que foi pedido. Em 15 perguntas vagas, o pedido de esclarecimento
# foi de 0 para 14, sem nenhum pedido indevido em 63 perguntas claras. Ressalva medida: nas 21 perguntas de
# reserva, as respostas úteis foram de 8 para 6 de 11 e as recusas certas de 6 para 8 de 10.
# Com outros modelos as regras não foram medidas; por isso entram, por padrão, só com o gerador da Anthropic.
REGRAS_ESCLARECIMENTO = f"""
9. Se a pergunta não disser qual é a barreira ou a dificuldade do aluno, nem qual é a atividade ou o que o professor quer fazer, não dê orientação geral: responda só com uma ou duas perguntas curtas pedindo o que falta, sem citar trechos. Esta é a única exceção às regras 2 e 3. Se a pergunta já traz a barreira ou a atividade, responda normalmente.
10. Se os trechos falam do tema mas não trazem o fato, a norma, o número ou a recomendação específica que a pergunta pede, responda exatamente: "{FRASE_SEM_RESPOSTA}" e nada mais. Não responda com informação vizinha no lugar da que foi pedida."""


def usar_regras_de_esclarecimento() -> bool:
    """RAG_PROMPT_ESCLARECIMENTO: `on`, `off` ou `auto` (padrão: ligado só com o gerador da Anthropic)."""
    modo = os.environ.get("RAG_PROMPT_ESCLARECIMENTO", "auto").strip().lower()
    if modo in {"on", "1", "true", "sim"}:
        return True
    if modo in {"off", "0", "false", "nao", "não"}:
        return False
    return os.environ.get("RAG_LLM", LLM).lower() in {"anthropic", "claude", "sonnet"}


def instrucoes() -> str:
    return INSTRUCOES + (REGRAS_ESCLARECIMENTO if usar_regras_de_esclarecimento() else "")


def montar_prompt(pergunta: str, trechos: list[dict]) -> str:
    blocos = []
    for i, t in enumerate(trechos, 1):
        pag = f", p. {t['pagina']}" if t.get("pagina") else ""
        aviso = f"\nAVISO DE USO: {t['nota_uso']}" if t.get("nao_usar_para") else ""
        tipo = f" | {t['tipo_evidencia']}" if t.get("tipo_evidencia") else ""
        blocos.append(f"[T{i}] {t['titulo']}{pag} ({t['idioma']}{tipo}){aviso}\n{t['trecho']}")
    return f"{instrucoes()}\n\nTRECHOS:\n\n" + "\n\n".join(blocos) + f"\n\nPERGUNTA: {pergunta}\n\nRESPOSTA:"


def _chamar_groq(prompt: str) -> tuple[str, dict]:
    chave = os.environ["GROQ_API_KEY"]
    corpo = json.dumps({"model": MODELO, "temperature": 0, "max_tokens": 1500,
                        "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=corpo,
                                 headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json",
                                          "User-Agent": "iris-rag/0.1"})
    for tentativa in range(4):
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=120).read())
            return r["choices"][0]["message"]["content"], r.get("usage", {})
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < 3:      # limite do plano grátis: espera e tenta de novo
                time.sleep(20 * (tentativa + 1))
                continue
            raise


# Gerador pela API da Anthropic. Padrão: Haiku no esforço baixo.
# Medido em 13 a 17/11/2026 (issue #86): nas perguntas do gabarito, o Haiku responde melhor que o Llama local
# e não se separa do Sonnet em respostas úteis, por cerca de um décimo do custo por consulta.
MODELO_ANTHROPIC_PADRAO = "claude-haiku-5-5"
MODELO_ANTHROPIC_RESERVA = "claude-sonnet-5-5"    # reserva se o modelo pedido não existir (o Sonnet 4.5 anterior sai do ar em 30/11/2026)
ESFORCO_ANTHROPIC = os.environ.get("RAG_ANTHROPIC_ESFORCO", "low")


def _modelo_anthropic() -> str:
    """Modelo do gerador: RAG_LLM_MODELO se for um modelo Claude, depois CLAUDE_SONNET_MODEL (compatibilidade), depois o padrão.

    O servidor grava em RAG_LLM_MODELO o modelo do provedor ativo (por exemplo `llama3.1:8b`); um nome que não é
    de modelo Claude não pode ir para a API da Anthropic.
    """
    pedido = (os.environ.get("RAG_LLM_MODELO") or "").strip()
    if pedido.startswith("claude"):
        return pedido
    return (os.environ.get("CLAUDE_SONNET_MODEL") or "").strip() or MODELO_ANTHROPIC_PADRAO


def _modelo_legado(modelo: str) -> bool:
    """Modelos das famílias 3 e 4 aceitam `temperature`; os mais novos recusam e usam `output_config.effort`."""
    return bool(re.search(r"claude-(?:3|(?:sonnet|opus|haiku)-4)", modelo))


def _corpo_anthropic(modelo: str, prompt: str, com_temperatura: bool) -> dict:
    corpo: dict = {"model": modelo, "messages": [{"role": "user", "content": prompt}]}
    if com_temperatura:
        corpo |= {"temperature": 0, "max_tokens": 1500}
    else:
        # Nos modelos novos o raciocínio conta como saída: com 1.500 a resposta chegava cortada (medido: ~1.500 tokens por resposta).
        esforco = (os.environ.get("RAG_ANTHROPIC_ESFORCO") or ESFORCO_ANTHROPIC).strip() or ESFORCO_ANTHROPIC
        corpo |= {"max_tokens": 4000, "output_config": {"effort": esforco}}
    return corpo


def _chamar_anthropic(prompt: str) -> tuple[str, dict]:
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada para geração.")
    modelo_alvo = _modelo_anthropic()
    modelos_tentar = [modelo_alvo]
    if modelo_alvo != MODELO_ANTHROPIC_RESERVA:
        modelos_tentar.append(MODELO_ANTHROPIC_RESERVA)

    for idx_m, mod in enumerate(modelos_tentar):
        com_temperatura = _modelo_legado(mod)
        tentativa = 0
        while tentativa < 4:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(_corpo_anthropic(mod, prompt, com_temperatura)).encode(),
                headers={
                    "x-api-key": chave,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "User-Agent": "iris-rag/0.1",
                },
            )
            try:
                r = json.loads(urllib.request.urlopen(req, timeout=120).read())
                partes = [
                    bloco.get("text", "")
                    for bloco in (r.get("content") or [])
                    if isinstance(bloco, dict) and bloco.get("type") == "text"
                ]
                texto = "\n".join(p for p in partes if p).strip()
                if not texto or r.get("stop_reason") == "max_tokens":
                    # resposta vazia ou cortada não vai ao professor: quem chamou cai para o gerador sem modelo
                    raise RuntimeError(f"resposta do modelo {mod} vazia ou cortada (stop_reason={r.get('stop_reason')})")
                uso_raw = r.get("usage") or {}
                uso = {
                    "prompt_tokens": uso_raw.get("input_tokens"),
                    "completion_tokens": uso_raw.get("output_tokens"),
                    "modelo": r.get("model") or mod,
                    "cortada": r.get("stop_reason") == "max_tokens",
                }
                return texto, uso
            except urllib.error.HTTPError as e:
                if e.code == 400 and com_temperatura:
                    # Modelo que não aceita `temperature` e não foi reconhecido pelo nome: tenta de novo sem ela.
                    detalhe = e.read().decode("utf-8", "replace")
                    if "temperature" in detalhe:
                        com_temperatura = False
                        continue
                    raise
                if e.code == 404 and idx_m + 1 < len(modelos_tentar):
                    break
                if e.code in (429, 529) and tentativa < 3:
                    time.sleep(5 * (tentativa + 1))
                    tentativa += 1
                    continue
                raise
    raise RuntimeError(f"Nenhum modelo da Anthropic respondeu ({', '.join(modelos_tentar)}).")


def _chamar_ollama(prompt: str) -> tuple[str, dict]:
    modelo_alvo = os.environ.get("RAG_LLM_MODELO", MODELO if LLM == "ollama" else "llama3.1:8b")
    url_base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    # Issue #89: sem `num_ctx` vale a janela padrão do Ollama (4.096) e o começo do prompt é descartado sem aviso
    # quando ele não cabe; sem `num_predict` uma resposta em laço só para no teto interno do servidor.
    opcoes = {"temperature": 0,
              "num_ctx": int(os.environ.get("RAG_NUM_CTX", "8192")),
              "num_predict": int(os.environ.get("RAG_NUM_PREDICT", "1024"))}
    corpo = json.dumps({"model": modelo_alvo, "prompt": prompt, "stream": False, "options": opcoes}).encode()
    req = urllib.request.Request(url_base + "/api/generate",
                                 data=corpo, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return r["response"], {"prompt_tokens": r.get("prompt_eval_count"), "completion_tokens": r.get("eval_count"),
                           "num_ctx": opcoes["num_ctx"], "done_reason": r.get("done_reason")}


def _chamar_extractive(prompt: str) -> tuple[str, dict]:
    """Fallback extrativo determinístico quando nem Ollama nem Groq estão ativos."""
    q_match = re.search(r"PERGUNTA:\s*(.+?)\s*\n\nRESPOSTA:", prompt, flags=re.S)
    pergunta = q_match.group(1).strip() if q_match else ""
    partes = re.split(r"\n(?=\[T\d+\]\s)", prompt)
    q_tokens = {w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", pergunta)
                if w.lower() not in {"como", "para", "qual", "quais", "aluno", "sobre", "fazer"}}
    candidatas: list[tuple[float, str]] = []
    for p in partes:
        m = re.match(r"\[T(\d+)\]\s*([^\n]+)\n(.*)", p.strip(), flags=re.S)
        if not m:
            continue
        idx = int(m.group(1))
        corpo = m.group(3).split("\n\nPERGUNTA:")[0].strip()
        if "AVISO DE USO:" in corpo:
            continue
        for pos, f in enumerate(re.split(r"(?<=[.!?])\s+|\n+", corpo)):
            f = f.strip()
            if 35 <= len(f) <= 320 and not f.startswith("#"):
                f_tokens = {w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", f)}
                inter = len(q_tokens & f_tokens)
                if inter > 0:
                    score = inter * 2.0 + 1.0 / (idx + pos * 0.2)
                    candidatas.append((score, f"{f.rstrip('.!?')} [T{idx}]."))
    candidatas.sort(key=lambda x: x[0], reverse=True)
    escolhidas = []
    vistas: set[str] = set()
    for sc, txt in candidatas:
        ch = txt[:50].lower()
        if ch not in vistas and sc >= 1.5:
            vistas.add(ch)
            escolhidas.append(txt)
        if len(escolhidas) >= 3:
            break
    resp = " ".join(escolhidas) if escolhidas else FRASE_SEM_RESPOSTA
    return resp, {"prompt_tokens": len(prompt.split()), "completion_tokens": len(resp.split())}


def gerar(prompt: str) -> tuple[str, dict]:
    provedor = os.environ.get("RAG_LLM", LLM).lower()
    if provedor in {"anthropic", "claude", "sonnet"}:
        fn = _chamar_anthropic
    elif provedor == "groq":
        fn = _chamar_groq
    elif provedor in {"extractive", "mock", "offline"}:
        fn = _chamar_extractive
    else:
        fn = _chamar_ollama
    texto, uso = fn(prompt)
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()   # Qwen3 pode "pensar em voz alta"
    return texto, uso


def pediu_esclarecimento(resposta: str) -> bool:
    """A resposta é uma pergunta de volta ao professor: não é recusa, não cita trecho e tem interrogação."""
    return (FRASE_SEM_RESPOSTA.lower()[:40] not in resposta.lower()
            and not re.search(r"\[T\d+\]", resposta) and "?" in resposta)


def conferir(resposta: str, trechos: list[dict]) -> dict:
    """Conferência mecânica (não mede se o conteúdo está certo; isso é o juiz/humano da semana 3)."""
    absteve = FRASE_SEM_RESPOSTA.lower()[:40] in resposta.lower()
    esclarecimento = pediu_esclarecimento(resposta)
    citados = sorted({int(n) for n in re.findall(r"\[T(\d+)\]", resposta)})
    invalidas = [n for n in citados if not 1 <= n <= len(trechos)]
    frases = [f for f in re.split(r"(?<=[.!?])\s+", resposta.strip()) if len(f.split()) >= 4]
    # Recusa e pedido de esclarecimento não afirmam nada sobre a base: não se cobra citação deles.
    sem_citacao = [f for f in frases if not re.search(r"\[T\d+\]", f)] if not (absteve or esclarecimento) else []
    aviso_citado = [n for n in citados if 1 <= n <= len(trechos) and trechos[n - 1].get("nao_usar_para")]
    return {"absteve": absteve, "pediu_esclarecimento": esclarecimento, "trechos_citados": citados, "citacoes_invalidas": invalidas,
            "frases": len(frases), "frases_sem_citacao": sem_citacao,
            "citou_trecho_com_aviso": [trechos[n - 1]["doc"] for n in aviso_citado]}


def responder(
    pergunta: str,
    metodo: str = consultar.METODO_PADRAO,
    k: int = 5,
    filtro_barreira: str | None = None,
) -> dict:
    t0 = time.time()
    try:
        trechos = consultar.buscar(pergunta, metodo, k=k, filtro_barreira=filtro_barreira)
        metodo_efetivo = metodo
    except Exception:
        if metodo != "bm25":
            trechos = consultar.buscar(pergunta, "bm25", k=k, filtro_barreira=filtro_barreira)
            metodo_efetivo = "bm25"
        else:
            raise
    t_busca = time.time() - t0
    prompt = montar_prompt(pergunta, trechos)
    resposta, uso = gerar(prompt)
    provedor_atual = os.environ.get("RAG_LLM", LLM)
    modelo_atual = os.environ.get("RAG_LLM_MODELO", MODELO if provedor_atual == LLM else "llama3.1:8b")
    if provedor_atual.lower() in {"anthropic", "claude", "sonnet"}:
        modelo_atual = (uso or {}).get("modelo") or _modelo_anthropic()   # o modelo que de fato respondeu
    return {"pergunta": pergunta, "metodo": metodo_efetivo, "llm": f"{provedor_atual}:{modelo_atual}", "resposta": resposta,
            "trechos_entregues": trechos,
            "fontes": [{"ref": f"T{i}", "doc": t["doc"], "titulo": t["titulo"], "pagina": t["pagina"],
                        "secao": t["secao"], "url": t["url"], "idioma": t["idioma"], "chunk_id": t["chunk_id"]}
                       for i, t in enumerate(trechos, 1)],
            "conferencia": conferir(resposta, trechos), "uso_tokens": uso,
            "segundos_busca": round(t_busca, 1), "segundos_total": round(time.time() - t0, 1)}


def mostrar(r: dict) -> str:
    L = [f"PERGUNTA: {r['pergunta']}", f"(busca: {r['metodo']}; LLM: {r['llm']}; {r['segundos_total']} s)", "",
         "RESPOSTA:", r["resposta"], "", "FONTES (os trechos entregues ao LLM):"]
    citados = set(r["conferencia"]["trechos_citados"])
    for i, f in enumerate(r["fontes"], 1):
        marca = "citado" if i in citados else "não citado"
        L.append(f"  [T{i}] {f['titulo'][:70]} | p. {f['pagina'] or '-'} | {f['secao'][:45]} [{f['idioma']}] ({marca})")
        L.append(f"       {f['url']}")
    c = r["conferencia"]
    L.append("")
    L.append(f"CONFERÊNCIA: absteve={c['absteve']} | citações inválidas={c['citacoes_invalidas']} | "
             f"frases sem citação={len(c['frases_sem_citacao'])} de {c['frases']} | "
             f"citou trecho com aviso={c['citou_trecho_com_aviso'] or 'não'}")
    return "\n".join(L)


PERGUNTAS_GERACAO = consultar.PERGUNTAS_DEMO + [
    "Qual a dose de metilfenidato para uma criança de 6 anos com TDAH?",   # fora da base: deve abster
]


def demonstracao(caminho: Path = AQUI / "outputs" / "04-respostas.txt") -> list[dict]:
    rs = []
    for p in PERGUNTAS_GERACAO:
        rs.append(responder(p))
    L = ["RESPOSTAS FUNDAMENTADAS (busca + geração) - Íris, semana 2",
         f"LLM: {LLM}:{MODELO}, temperatura 0. Busca: {consultar.METODO_PADRAO} (padrão provisório), top-5.",
         "ATENÇÃO: demonstração, não avaliação. A conferência abaixo de cada resposta é mecânica (citação",
         "existe, frase tem citação); se o conteúdo está certo, só o juiz/humano dirá (semana 3).", ""]
    for r in rs:
        L += ["=" * 100, mostrar(r), ""]
    caminho.parent.mkdir(exist_ok=True)
    caminho.write_text("\n".join(L) + "\n", encoding="utf-8")
    (caminho.with_suffix(".jsonl")).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rs) + "\n",
                                               encoding="utf-8")
    return rs


if __name__ == "__main__":
    demonstracao()
    print((AQUI / "outputs" / "04-respostas.txt").read_text(encoding="utf-8"))
