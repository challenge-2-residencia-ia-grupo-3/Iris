"""Juiz de Auditoria RAG via API Claude Sonnet (Regra v2 + Conferência Mecânica Literal).

Aplica em tempo real (ou em lote sobre as 136 questões escolares e as 40 perguntas do gabarito)
a mesma regra de avaliação do relatório oficial (`rag/iris-rag/pacote/regra_juiz_respostas_v2.md`):

1. Segmenta a resposta gerada pelo LLM local (ex.: Llama 3) em frases numeradas `S1..Sn`;
2. Envia ao Claude Sonnet via API (`ANTHROPIC_API_KEY` configurada no `.env`) os 5 trechos `[T1]..[T5]`
   entregues ao gerador (incluindo cabeçalho, idioma, tipo de evidência e AVISO DE USO);
3. Classifica cada frase (`apoiada`, `parcial`, `nao_apoiada`, `comentario_correto`, `comentario_errado`),
   reconhecendo traduções fiéis Inglês -> Português e paráfrases legítimas;
4. Exige cópia literal da passagem (`citacao`) do trecho `[Tn]` e executa a conferência mecânica
   determinística (`veredito_conferido_v2`) para descartar citações inventadas pelo próprio juiz;
5. Mantém cache persistente por hash SHA-256 em `reports/sonnet_judge_cache.jsonl` para evitar
   chamadas repetidas à API para a mesma resposta.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from iris.config import RAG_PACOTE_DIR, REPO_ROOT, get_settings

REGRA_JUIZ_V2_PATH = RAG_PACOTE_DIR / "regra_juiz_respostas_v2.md"
CACHE_JUIZ_PADRAO = REPO_ROOT / "reports" / "sonnet_judge_cache.jsonl"
FRASE_SEM_RESPOSTA_PADRAO = "Não encontrei nos documentos da base informação suficiente para responder."

SISTEMA_JUIZ_SONNET = (
    "Você é um avaliador científico rigoroso do Projeto Íris. "
    "Siga estritamente a regra da mensagem e devolva APENAS o objeto JSON solicitado, sem cercas markdown."
)

MODELOS_SONNET_FALLBACK = (
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-sonnet-5-5",
)

ABREVIACAO_RE = re.compile(r"(?:\bet al|\bart|\barts|\bcf|\bvs|\bDr|\bDra|\bProf|\bn[ºo]?)\.$")

# Tipo para injeção em testes unitários: (modelo, system_prompt, user_prompt, temperature) -> (texto_json, uso_dict)
ChamarSonnetFn = Callable[[str, str, str, float], tuple[str, dict[str, Any]]]


def sonnet_judge_status() -> dict[str, Any]:
    """Verifica se a chave `ANTHROPIC_API_KEY` está configurada no `.env` ou ambiente."""
    settings = get_settings()
    key = (settings.anthropic_api_key or "").strip()
    return {
        "ready": bool(key),
        "model": settings.judge_model or "claude-sonnet-4-5-20250929",
        "key_configured": bool(key),
        "cache_path": str(CACHE_JUIZ_PADRAO),
    }


def carregar_regra_juiz_v2() -> str:
    """Lê a regra oficial `regra_juiz_respostas_v2.md` do pacote RAG."""
    if REGRA_JUIZ_V2_PATH.exists():
        return REGRA_JUIZ_V2_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Arquivo de regra do juiz não encontrado em {REGRA_JUIZ_V2_PATH}")


def segmentar_frases_resposta(resposta: str, juntar: bool = True) -> list[str]:
    """Divide a resposta em frases seguindo a mesma regra de `medir_respostas.py`."""
    texto = re.sub(r"(?:(?<=\s)|^)(\d{1,2})\.\s+(?=[A-ZÀ-Ú\"“])", r"\1) ", resposta.strip())
    pedacos = [p for p in re.split(r"(?<=[.!?])\s+", texto) if p.strip()]
    saida: list[str] = []
    for p in pedacos:
        m = re.match(r"((?:\[T\d+\]\s*)+)(.*)", p, flags=re.S)
        if m and saida:
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
            if junto and ABREVIACAO_RE.search(junto[-1].strip()):
                junto[-1] += " " + p
            else:
                junto.append(p)
        saida = junto
    return saida


def extrair_citacoes_frase(frase: str) -> list[int]:
    """Retorna os índices inteiros `[Tn]` citados na frase."""
    return sorted({int(n) for n in re.findall(r"\[T(\d+)\]", frase)})


def resposta_eh_recusa(resposta: str, frase_sem_resposta: str = FRASE_SEM_RESPOSTA_PADRAO) -> bool:
    """Verifica se a resposta corresponde à declaração padrão de insuficiência da base."""
    return frase_sem_resposta.lower()[:40] in (resposta or "").lower()


def formatar_bloco_trecho(idx: int, trecho: dict[str, Any]) -> str:
    """Formata o bloco `[Tn]` exatamente como entregue ao modelo gerador e ao juiz."""
    ref = trecho.get("ref") or f"T{idx}"
    if not str(ref).startswith("T"):
        ref = f"T{ref}"
    titulo = trecho.get("titulo") or trecho.get("doc") or trecho.get("chunk_id") or f"Documento {idx}"
    pag = f", p. {trecho['pagina']}" if trecho.get("pagina") else ""
    idioma = trecho.get("idioma") or "pt"
    tipo_ev = f" | {trecho['tipo_evidencia']}" if trecho.get("tipo_evidencia") else ""
    nota_uso = trecho.get("nota_uso") or trecho.get("nao_usar_para") or ""
    aviso = f"\nAVISO DE USO: {nota_uso}" if trecho.get("nao_usar_para") else ""
    corpo = trecho.get("trecho") or trecho.get("texto") or ""
    return f"[{ref}] {titulo}{pag} ({idioma}{tipo_ev}){aviso}\n{corpo}"


def montar_prompt_juiz_v2(
    pergunta: str,
    trechos: list[dict[str, Any]],
    resposta: str,
    frase_sem_resposta: str = FRASE_SEM_RESPOSTA_PADRAO,
) -> str:
    """Constrói o prompt completo do Juiz Claude Sonnet conforme `regra_juiz_respostas_v2.md`."""
    regra = carregar_regra_juiz_v2()
    blocos = [formatar_bloco_trecho(i, t) for i, t in enumerate(trechos, start=1)]
    if resposta_eh_recusa(resposta, frase_sem_resposta):
        frases_str = "A resposta é a recusa. Não há frases a julgar: preencha `abstencao`."
    else:
        frases_lista = segmentar_frases_resposta(resposta, juntar=True)
        frases_str = "\n".join(f"S{n}: {f}" for n, f in enumerate(frases_lista, start=1))

    return (
        f"{regra}\n\n---\n\n"
        f"PERGUNTA: {pergunta}\n\n"
        f"TRECHOS ENTREGUES AO SISTEMA:\n\n"
        + "\n\n".join(blocos)
        + f"\n\nRESPOSTA (inteira):\n{resposta}\n\n"
        f"FRASES A JULGAR:\n{frases_str}\n"
    )


def limpar_texto_conferencia(texto: str) -> str:
    """Normaliza espaços, pontuação tipográfica e caixa para conferência literal da citação."""
    x = (
        (texto or "")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    return re.sub(r"\s+", " ", x).strip().strip('."\'').lower()


def verificar_citacao_literal_no_trecho(
    citacao: str,
    indices_citados: list[int],
    trechos: list[dict[str, Any]],
) -> bool:
    """Confere se a passagem copiada pelo juiz em `citacao` consta literalmente nos trechos `[Tn]` citados.

    Considera todo o bloco do trecho (cabeçalho, aviso de uso e corpo), conforme a Regra v2.
    Também tolera reticências (`...` ou `[...]`) caso o juiz tenha omitido o miolo de uma frase longa,
    desde que os segmentos tenham ao menos 3 palavras ao todo e constem no mesmo trecho citado.
    """
    cit_limpa = limpar_texto_conferencia(citacao)
    if len(cit_limpa.split()) < 3:
        return False

    refs_validas = [n for n in indices_citados if 1 <= n <= len(trechos)]
    if not refs_validas:
        return False

    segmentos = [
        limpar_texto_conferencia(seg)
        for seg in re.split(r"\[\.\.\.\]|…|\.{3,}", citacao)
        if limpar_texto_conferencia(seg)
    ]
    if not segmentos:
        return False

    for n in refs_validas:
        bloco_completo = limpar_texto_conferencia(formatar_bloco_trecho(n, trechos[n - 1]))
        if cit_limpa in bloco_completo:
            return True
        if len(segmentos) > 1 and all(seg in bloco_completo for seg in segmentos):
            return True
    return False


def conferir_veredito_frase_v2(
    veredito_item: dict[str, Any] | None,
    frase: str,
    trechos: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aplica a conferência mecânica sobre o veredito de uma frase emitido pelo juiz Sonnet."""
    refs = extrair_citacoes_frase(frase)
    if not refs:
        return {
            "tipo": (veredito_item or {}).get("tipo", "conteudo"),
            "veredito_bruto": (veredito_item or {}).get("veredito", "sem_citacao"),
            "veredito": "sem_citacao",
            "citacao_verificada": False,
            "trecho": None,
            "citacao": None,
            "motivo": "Frase não contém citação [Tn].",
            "outro_trecho": None,
            "rotulo_errado": False,
        }

    if not veredito_item:
        return {
            "tipo": "conteudo",
            "veredito_bruto": "sem_veredito",
            "veredito": "sem_veredito",
            "citacao_verificada": False,
            "trecho": None,
            "citacao": None,
            "motivo": "Juiz não retornou avaliação para esta frase.",
            "outro_trecho": None,
            "rotulo_errado": False,
        }

    tipo = veredito_item.get("tipo") or "conteudo"
    ver_bruto = veredito_item.get("veredito") or "sem_veredito"
    citacao = veredito_item.get("citacao")
    trecho_ref = veredito_item.get("trecho")
    motivo = veredito_item.get("motivo") or ""
    outro_trecho = veredito_item.get("outro_trecho")
    rotulo_errado = bool(veredito_item.get("rotulo_errado", False))

    if tipo == "comentario" or ver_bruto in ("comentario_correto", "comentario_errado"):
        ver_final = ver_bruto if ver_bruto in ("comentario_correto", "comentario_errado") else "comentario_correto"
        return {
            "tipo": "comentario",
            "veredito_bruto": ver_bruto,
            "veredito": ver_final,
            "citacao_verificada": True,
            "trecho": trecho_ref,
            "citacao": citacao,
            "motivo": motivo,
            "outro_trecho": outro_trecho,
            "rotulo_errado": rotulo_errado,
        }

    if ver_bruto not in ("apoiada", "parcial", "nao_apoiada"):
        return {
            "tipo": "conteudo",
            "veredito_bruto": ver_bruto,
            "veredito": "sem_veredito",
            "citacao_verificada": False,
            "trecho": trecho_ref,
            "citacao": citacao,
            "motivo": motivo,
            "outro_trecho": outro_trecho,
            "rotulo_errado": rotulo_errado,
        }

    if ver_bruto == "nao_apoiada":
        return {
            "tipo": "conteudo",
            "veredito_bruto": "nao_apoiada",
            "veredito": "nao_apoiada",
            "citacao_verificada": True,
            "trecho": trecho_ref,
            "citacao": citacao,
            "motivo": motivo,
            "outro_trecho": outro_trecho,
            "rotulo_errado": rotulo_errado,
        }

    cit_ok = verificar_citacao_literal_no_trecho(citacao or "", refs, trechos)
    ver_final = ver_bruto if cit_ok else "rejeitado"
    return {
        "tipo": "conteudo",
        "veredito_bruto": ver_bruto,
        "veredito": ver_final,
        "citacao_verificada": cit_ok,
        "trecho": trecho_ref,
        "citacao": citacao,
        "motivo": motivo if cit_ok else f"{motivo} [Passagem não localizada literalmente no trecho citado]".strip(),
        "outro_trecho": outro_trecho,
        "rotulo_errado": rotulo_errado,
    }


def extrair_json_juiz(texto: str) -> dict[str, Any] | None:
    """Extrai o objeto JSON da resposta textual do Claude Sonnet."""
    if not texto:
        return None
    limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.I)
    m = re.search(r"\{.*\}", limpo, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def chamar_claude_sonnet_api(
    modelo: str,
    sistema: str,
    prompt: str,
    temperature: float = 0.0,
) -> tuple[str, dict[str, Any]]:
    """Chama a API Messages da Anthropic (`https://api.anthropic.com/v1/messages`) usando `ANTHROPIC_API_KEY`."""
    settings = get_settings()
    chave = (settings.anthropic_api_key or "").strip()
    if not chave:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no arquivo .env. "
            "Cole sua chave em iris/.env (ANTHROPIC_API_KEY=sk-ant-...) para usar o Juiz Claude Sonnet."
        )

    candidatos = [modelo] + [m for m in MODELOS_SONNET_FALLBACK if m != modelo]
    ultimo_erro: Exception | None = None

    for mod_tentativa in candidatos:
        corpo = json.dumps(
            {
                "model": mod_tentativa,
                "max_tokens": 2048,
                "temperature": temperature,
                "system": sistema,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=corpo,
            headers={
                "x-api-key": chave,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "user-agent": "iris-rag-judge/1.0",
            },
        )

        for tentativa in range(3):
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    dados = json.loads(resp.read().decode("utf-8"))
                blocos = dados.get("content") or []
                texto = "".join(b.get("text", "") for b in blocos if b.get("type") == "text").strip()
                uso = dados.get("usage") or {}
                return texto, {
                    "modelo": dados.get("model", mod_tentativa),
                    "input_tokens": uso.get("input_tokens", 0),
                    "output_tokens": uso.get("output_tokens", 0),
                    "duration_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                }
            except urllib.error.HTTPError as exc:
                detalhe = ""
                try:
                    detalhe = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                ultimo_erro = RuntimeError(f"HTTP {exc.code} ao chamar Anthropic ({mod_tentativa}): {detalhe[:300]}")
                # Se o modelo específico não existir na conta (404), tenta o próximo alias Sonnet
                if exc.code == 404:
                    break
                if exc.code in (429, 500, 502, 503, 529) and tentativa < 2:
                    time.sleep(2.5 * (tentativa + 1))
                    continue
                raise ultimo_erro from exc
            except Exception as exc:
                ultimo_erro = exc
                if tentativa < 2:
                    time.sleep(1.5 * (tentativa + 1))
                    continue
                raise

    raise RuntimeError(f"Não foi possível executar o Juiz Claude Sonnet: {ultimo_erro}")


def _calcular_chave_cache(
    pergunta: str,
    trechos: list[dict[str, Any]],
    resposta: str,
    modelo: str,
    n_juizes: int,
) -> str:
    payload = {
        "v": "regra_v2",
        "modelo": modelo,
        "n_juizes": n_juizes,
        "pergunta": pergunta.strip(),
        "resposta": (resposta or "").strip(),
        "trechos": [
            {
                "chunk_id": t.get("chunk_id", ""),
                "nao_usar_para": t.get("nao_usar_para"),
                "texto": (t.get("trecho") or t.get("texto") or "")[:600],
            }
            for t in trechos
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ler_cache_juiz(cache_key: str, caminho_cache: Path = CACHE_JUIZ_PADRAO) -> dict[str, Any] | None:
    if not caminho_cache.exists():
        return None
    try:
        for linha in reversed(caminho_cache.read_text(encoding="utf-8").splitlines()):
            if not linha.strip():
                continue
            item = json.loads(linha)
            if item.get("cache_key") == cache_key and isinstance(item.get("resultado"), dict):
                res = dict(item["resultado"])
                res["cache_hit"] = True
                return res
    except Exception:
        return None
    return None


def _gravar_cache_juiz(
    cache_key: str,
    resultado: dict[str, Any],
    caminho_cache: Path = CACHE_JUIZ_PADRAO,
) -> None:
    try:
        caminho_cache.parent.mkdir(parents=True, exist_ok=True)
        registro = {"cache_key": cache_key, "resultado": resultado}
        with caminho_cache.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _calcular_kappa(pares: list[tuple[str, str]]) -> tuple[float, float]:
    if not pares:
        return 1.0, 1.0
    n = len(pares)
    po = sum(1 for a, b in pares if a == b) / n
    ca = Counter(a for a, _ in pares)
    cb = Counter(b for _, b in pares)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if pe >= 1.0:
        return round(po, 4), 1.0
    return round(po, 4), round((po - pe) / (1.0 - pe), 4)


def julgar_resposta_sonnet(
    pergunta: str,
    trechos: list[dict[str, Any]],
    resposta: str,
    *,
    modelo: str | None = None,
    n_juizes: int = 1,
    usar_cache: bool = True,
    caminho_cache: Path = CACHE_JUIZ_PADRAO,
    chamar_api_fn: ChamarSonnetFn | None = None,
) -> dict[str, Any]:
    """Avalia uma resposta gerada (ex.: pelo Llama 3) usando o Juiz Claude Sonnet e a Regra v2."""
    settings = get_settings()
    modelo_alvo = modelo or settings.judge_model or "claude-sonnet-4-20250514"
    cache_key = _calcular_chave_cache(pergunta, trechos, resposta, modelo_alvo, n_juizes)

    if usar_cache and chamar_api_fn is None:
        cached = _ler_cache_juiz(cache_key, caminho_cache)
        if cached is not None:
            return cached

    t0 = time.perf_counter()
    caller = chamar_api_fn or chamar_claude_sonnet_api
    prompt = montar_prompt_juiz_v2(pergunta, trechos, resposta)
    recusou = resposta_eh_recusa(resposta)
    frases_texto = [] if recusou else segmentar_frases_resposta(resposta, juntar=True)

    # Executa 1 juiz (padrão rápido) ou 2 juízes independentes (Juiz A + Juiz B)
    julgamentos_brutos: dict[str, dict[str, Any]] = {}
    usos: list[dict[str, Any]] = []
    etiquetas = ["A"] if n_juizes <= 1 else ["A", "B"]

    for idx_j, etq in enumerate(etiquetas):
        temp = 0.0 if idx_j == 0 else 0.15
        parsed: dict[str, Any] | None = None
        uso_j: dict[str, Any] = {}
        for _ in range(2):
            bruto_str, uso_j = caller(modelo_alvo, SISTEMA_JUIZ_SONNET, prompt, temp)
            parsed = extrair_json_juiz(bruto_str)
            if parsed is not None:
                break
        julgamentos_brutos[etq] = parsed or {}
        usos.append(uso_j)

    frases_avaliadas: list[dict[str, Any]] = []
    contagem = {
        "apoiada": 0,
        "parcial": 0,
        "divergem": 0,
        "nao_apoiada": 0,
        "rejeitado": 0,
        "comentario": 0,
        "total_conteudo": 0,
    }
    pares_kappa: list[tuple[str, str]] = []
    pontos_confirmados = 0.0
    pontos_brutos = 0.0

    for n_idx, frase_str in enumerate(frases_texto, start=1):
        por_juiz: dict[str, dict[str, Any]] = {}
        for etq in etiquetas:
            lista_f = julgamentos_brutos[etq].get("frases") or []
            item_f = next((x for x in lista_f if x.get("n") == n_idx), None)
            if item_f is None and n_idx <= len(lista_f):
                item_f = lista_f[n_idx - 1]
            por_juiz[etq] = conferir_veredito_frase_v2(item_f, frase_str, trechos)

        ja = por_juiz["A"]
        jb = por_juiz.get("B", ja)

        if ja["tipo"] == "comentario" or jb["tipo"] == "comentario":
            contagem["comentario"] += 1
            comum = ja["veredito"] if ja["veredito"] == jb["veredito"] else "comentario_correto"
            frases_avaliadas.append(
                {
                    "n": n_idx,
                    "frase": frase_str,
                    "tipo": "comentario",
                    "A": ja["veredito"],
                    "B": jb["veredito"],
                    "comum": comum,
                    "veredito_bruto": ja["veredito_bruto"],
                    "citacao_verificada": True,
                    "trecho": ja.get("trecho"),
                    "citacao": ja.get("citacao"),
                    "motivo": ja.get("motivo") or jb.get("motivo") or "",
                }
            )
            continue

        contagem["total_conteudo"] += 1
        va = ja["veredito"]
        vb = jb["veredito"]
        pares_kappa.append((va, vb))

        # Pontuação bruta (antes de rejeição por substring literal)
        for v_bruto in (ja["veredito_bruto"], jb["veredito_bruto"]):
            if v_bruto == "apoiada":
                pontos_brutos += 0.5
            elif v_bruto == "parcial":
                pontos_brutos += 0.25

        if va == vb and va in ("apoiada", "parcial", "nao_apoiada", "rejeitado"):
            comum = va
        elif va == vb == "sem_citacao":
            comum = "nao_apoiada"
        elif n_juizes <= 1:
            comum = va if va in ("apoiada", "parcial", "nao_apoiada", "rejeitado") else "nao_apoiada"
        else:
            comum = "divergem"

        if comum in contagem:
            contagem[comum] += 1

        if comum == "apoiada":
            pontos_confirmados += 1.0
        elif comum in ("parcial", "divergem"):
            pontos_confirmados += 0.5

        frases_avaliadas.append(
            {
                "n": n_idx,
                "frase": frase_str,
                "tipo": "conteudo",
                "A": va,
                "B": vb,
                "comum": comum,
                "veredito_bruto": ja["veredito_bruto"],
                "citacao_verificada": bool(ja["citacao_verificada"] and jb["citacao_verificada"]),
                "trecho": ja.get("trecho") or jb.get("trecho"),
                "citacao": ja.get("citacao") or jb.get("citacao"),
                "motivo": ja.get("motivo") or jb.get("motivo") or "",
                "outro_trecho": ja.get("outro_trecho") or jb.get("outro_trecho"),
                "rotulo_errado": bool(ja.get("rotulo_errado") or jb.get("rotulo_errado")),
            }
        )

    po, kappa = _calcular_kappa(pares_kappa)
    resp_a = str(julgamentos_brutos["A"].get("responde") or ("nao" if recusou else "sim"))
    resp_b = str(julgamentos_brutos.get("B", julgamentos_brutos["A"]).get("responde") or resp_a)
    motivo_resp = str(
        julgamentos_brutos["A"].get("motivo_responde")
        or julgamentos_brutos.get("B", {}).get("motivo_responde")
        or ""
    )
    abst_a = julgamentos_brutos["A"].get("abstencao")
    abst_b = julgamentos_brutos.get("B", julgamentos_brutos["A"]).get("abstencao", abst_a)

    mapa_nota_resp = {"sim": 1.0, "em_parte": 0.65, "nao": 0.0}
    if recusou:
        relevancia_sonnet = 1.0 if abst_a == "correta" else 0.0
        fidelidade_sonnet = 1.0 if abst_a == "correta" else 0.5
        fidelidade_bruta = fidelidade_sonnet
    elif contagem["total_conteudo"] > 0:
        fidelidade_sonnet = round(min(1.0, pontos_confirmados / contagem["total_conteudo"]), 4)
        fidelidade_bruta = round(min(1.0, pontos_brutos / contagem["total_conteudo"]), 4)
        relevancia_sonnet = round(
            (mapa_nota_resp.get(resp_a, 0.5) + mapa_nota_resp.get(resp_b, 0.5)) / 2.0,
            4,
        )
    else:
        fidelidade_sonnet = 1.0
        fidelidade_bruta = 1.0
        relevancia_sonnet = round(mapa_nota_resp.get(resp_a, 0.5), 4)

    modelo_efetivo = next((u.get("modelo") for u in usos if u.get("modelo")), modelo_alvo)
    resultado = {
        "disponivel": True,
        "avaliador": "claude_sonnet",
        "modelo": modelo_efetivo,
        "n_juizes": len(etiquetas),
        "cache_hit": False,
        "latencia_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        "tokens_entrada": sum(int(u.get("input_tokens") or 0) for u in usos),
        "tokens_saida": sum(int(u.get("output_tokens") or 0) for u in usos),
        "recusou": recusou,
        "responde": {"A": resp_a, "B": resp_b},
        "motivo_responde": motivo_resp,
        "abstencao": {"A": abst_a, "B": abst_b} if recusou else {},
        "fidelidade_sonnet": fidelidade_sonnet,
        "fidelidade_sonnet_bruta": fidelidade_bruta,
        "relevancia_sonnet": relevancia_sonnet,
        "concordancia_bruta_pct": round(po * 100.0, 1),
        "kappa_cohen": kappa,
        "resumo_frases": contagem,
        "frases": frases_avaliadas,
    }

    if usar_cache and chamar_api_fn is None:
        _gravar_cache_juiz(cache_key, resultado, caminho_cache)

    return resultado
