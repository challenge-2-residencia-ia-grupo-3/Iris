"""Logger operacional Zero-PII e Zero-Retention (História 4.1.4 / Issue #37, RNF-01, RNF-02).

Garante que logs e telemetria emitidos em execução pela API e pelos agentes registrem
exclusivamente métricas operacionais (status HTTP, latência, tokens, TRCC e códigos
fechados de categoria), impedindo a retenção ou exibição de enunciados, perfis
pedagógicos, dados pessoais (PII) ou termos clínicos (RNF-03).

Opera 100% em memória via `logging` padrão e `contextvars` (sem escrita em disco).
"""
from __future__ import annotations

import contextlib
import contextvars
import io
import json
import logging
import re
import threading
import unicodedata
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional, Sequence

from iris.security.pii_scrubber import sanitize_pii

OPERATIONAL_LOGGER_NAME = "iris.operational"
IRIS_ROOT_LOGGER_NAME = "iris"

# Chaves de payload sensível que nunca devem aparecer em logs estruturados
SENSITIVE_PAYLOAD_KEYS = frozenset(
    {
        "text",
        "raw_text",
        "texto",
        "texto_bruto",
        "texto_sanitizado",
        "texto_adaptado",
        "texto_minuta",
        "texto_final",
        "enunciado",
        "enunciado_original",
        "original",
        "adaptado",
        "minuta",
        "minuta_anterior",
        "observacao",
        "anotacoes_pedagogicas",
        "potencialidades",
        "barreiras_observadas",
        "historico_estrategias",
        "prompt",
        "system_prompt",
        "contexto_apoio",
        "diretiva",
        "diretiva_psicopedagogica",
        "feedback_auditor",
        "feedback_gerado",
        "justificativas",
        "recomendacao_docente",
        "conceitos_obrigatorios",
        "conceitos_retidos",
        "conceitos_ausentes",
        "termos_tecnicos_intocaveis",
        "trava_manual_docente",
        "alerta_anti_muleta",
        "filename",
        "file",
    }
)

# Termos de sistema / protocolo preservados mesmo que coincidam com palavras do material
_SYSTEM_SAFE_WORDS = frozenset(
    {
        "http",
        "json",
        "status",
        "code",
        "error",
        "erro",
        "falha",
        "timeout",
        "latencia",
        "latency",
        "tokens",
        "prompt",
        "completion",
        "total",
        "trcc",
        "escopo",
        "scope",
        "nivel",
        "questao",
        "questoes",
        "material",
        "adaptacao",
        "adaptado",
        "original",
        "modelo",
        "model",
        "provedor",
        "provider",
        "ollama",
        "anthropic",
        "claude",
        "sonnet",
        "haiku",
        "groq",
        "extractive",
        "llama",
        "llama3",
        "qwen",
        "qwen3",
        "extrator",
        "estrategista",
        "adaptador",
        "auditor",
        "orquestrador",
        "agente",
        "agentes",
        "fallback",
        "reserva",
        "revisao",
        "humana",
        "aprovado",
        "reprovado",
        "aplicada",
        "nenhum",
        "ausente",
        "perdida",
        "alterada",
        "evidencia",
        "comandos",
        "multiplos",
        "palavra",
        "palavras",
        "execucao",
        "execution",
        "request",
        "response",
        "method",
        "path",
        "event",
        "detalhes",
        "suprimido",
        "suprimidos",
        "operacional",
        "excecao",
        "runtimeerror",
        "valueerror",
        "keyerror",
        "validationerror",
        "httpexception",
        "deterministic",
        "memory",
        "local",
        "success",
        "post",
        "get",
    }
)

_SAFE_TECHNICAL_IDENTIFIERS = frozenset(
    {
        "event",
        "http_request",
        "agent_execution",
        "method",
        "path",
        "status_code",
        "trace_id",
        "rag_backend",
        "rag_metodo_efetivo",
        "rerank_top1_score",
        "pgvector",
        "bm25",
        "fallback_bm25",
        "desconhecido",
        "latency_s",
        "latency_ms",
        "error_code",
        "nivel",
        "selected_ids",
        "total_questoes",
        "pii_substituicoes",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "trcc_scores",
        "trcc_mean",
        "trcc_min",
        "aprovadas_auditor",
        "requerem_revisao_humana",
        "provider",
        "model",
        "fallbacks",
        "violacoes",
        "provedor_sem_modelo",
        "regra_comandos_multiplos",
        "conferente_palavra_perdida",
        "escopo_reprovado",
        "sem_evidencia",
        "nenhuma_intervencao_aprovada",
        "falha_llm",
        "conceito_ausente",
        "palavra_ausente",
        "palavra_fora_vocabulario",
        "ordem_alterada",
        "texto_alterado_alem_destaque",
        "deterministic-fallback",
        "sobrecarga_memoria_trabalho_comandos_multiplos",
        "retencao_dados_intermediarios_problemas_multietapas",
        "atencao_sustentada_textos_longos",
        "distratibilidade_poluicao_visual_layout",
        "impulsividade_leitura_superficial_negacoes",
        "organizacao_sequencial_expressao_escrita",
        "fadiga_executiva_autorregulacao_provas_extensas",
        "flexibilidade_cognitiva_alternancia_topicos",
        "bloqueio_iniciacao_tarefas_abertas",
        "ritmo_processamento_pressao_temporal",
    }
)

_RE_CLINICAL_LOG = re.compile(
    r"(?i)\b(?:CID[-\s]?1?[01]?|F9\d(?:\.\d)?|laudo\s+m[eé]dico|metilfenidato|ritalina|venvans[ei]|concerta|risperidona|atomoxetina)\b"
)
_RE_SENTINEL_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]{4,}")
_RE_SENSITIVE_ASSIGN = re.compile(
    r"""(?i)(['"]?(?:"""
    + "|".join(sorted(SENSITIVE_PAYLOAD_KEYS, key=len, reverse=True))
    + r""")['"]?\s*[:=]\s*)(?:(['"])(?:(?=(\\?))\3.)*?\2|\[[^\]]*\]|\{[^\}]*\})"""
)

_ACTIVE_SENTINEL: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "iris_operational_log_sentinel",
    default=frozenset(),
)
_TRACE_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "iris_trace_id",
    default=None,
)
_RECENT_AGENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
_OPS_LOCK = threading.Lock()


def generate_trace_id() -> str:
    """Gera identificador anônimo curto de correlação por requisição."""
    return uuid.uuid4().hex[:12]


def current_trace_id() -> Optional[str]:
    """Retorna o `trace_id` ativo no contexto da requisição atual, se houver."""
    return _TRACE_ID_CTX.get()


@contextlib.contextmanager
def trace_context(trace_id: Optional[str] = None) -> Iterator[str]:
    """Associa um `trace_id` anônimo ao contexto atual durante a requisição em memória."""
    tid = (
        str(trace_id).strip()[:32]
        if trace_id and re.fullmatch(r"[A-Za-z0-9_\-]{4,32}", str(trace_id).strip())
        else generate_trace_id()
    )
    token = _TRACE_ID_CTX.set(tid)
    try:
        yield tid
    finally:
        _TRACE_ID_CTX.reset(token)


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def extract_sentinel_words(*textos: Optional[str]) -> frozenset[str]:
    """Extrai tokens >= 4 chars normalizados para bloqueio temporário em memória."""
    palavras: set[str] = set()
    for t in textos:
        if not t:
            continue
        for tok in re.findall(r"[a-z]{4,}", _normalizar(str(t))):
            if tok not in _SYSTEM_SAFE_WORDS:
                palavras.add(tok)
    return frozenset(palavras)


@contextlib.contextmanager
def sentinel_context(*textos: Optional[str]) -> Iterator[frozenset[str]]:
    """Mantém palavras do material apenas durante a requisição em memória (Zero-Retention)."""
    atual = _ACTIVE_SENTINEL.get()
    novas = extract_sentinel_words(*textos)
    combinadas = atual | novas
    token = _ACTIVE_SENTINEL.set(combinadas)
    try:
        yield combinadas
    finally:
        _ACTIVE_SENTINEL.reset(token)


def _redact_sentinel(texto: str, sentinela: frozenset[str]) -> str:
    if not sentinela or not texto:
        return texto

    def _substituir(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok in _SAFE_TECHNICAL_IDENTIFIERS or tok.casefold() in _SAFE_TECHNICAL_IDENTIFIERS:
            return tok
        if "_" in tok:
            partes = [_normalizar(p) for p in tok.split("_") if len(p) >= 4]
            if any(p in sentinela and p not in _SYSTEM_SAFE_WORDS for p in partes):
                return "[CONTEUDO_SUPRIMIDO]"
            return tok
        norm = _normalizar(tok)
        if norm in sentinela and norm not in _SYSTEM_SAFE_WORDS:
            return "[CONTEUDO_SUPRIMIDO]"
        return tok

    return _RE_SENTINEL_WORD.sub(_substituir, texto)


def sanitize_log_message(message: Any) -> str:
    """Remove PII, termos clínicos, trechos inline de payload e palavras da sentinela."""
    bruto = message if isinstance(message, str) else json.dumps(sanitize_log_value(message), ensure_ascii=False, default=str)
    # 1. Remove atribuições inline do tipo text='...' / enunciado: "..."
    limpo = _RE_SENSITIVE_ASSIGN.sub(r"\1'[PAYLOAD_SUPRIMIDO]'", bruto)
    # 2. Gateway local de PII
    limpo, _ = sanitize_pii(limpo)
    # 3. Termos clínicos restritos (RNF-03)
    limpo = _RE_CLINICAL_LOG.sub("[DADO_CLINICO_SUPRIMIDO]", limpo)
    # 4. Sentinela ativa da requisição em memória
    limpo = _redact_sentinel(limpo, _ACTIVE_SENTINEL.get())
    return limpo


def sanitize_log_value(val: Any) -> Any:
    """Sanitiza recursivamente dicionários e sequências para nunca reter campos de payload."""
    if val is None or isinstance(val, (bool, int, float)):
        return val
    if isinstance(val, str):
        return sanitize_log_message(val)
    if isinstance(val, Mapping):
        out: dict[str, Any] = {}
        for k, v in val.items():
            chave_norm = str(k).strip().casefold()
            if chave_norm in SENSITIVE_PAYLOAD_KEYS:
                out[str(k)] = "[PAYLOAD_SUPRIMIDO]"
            else:
                out[sanitize_log_message(str(k))] = sanitize_log_value(v)
        return out
    if isinstance(val, (list, tuple, set, frozenset)):
        return [sanitize_log_value(item) for item in val]
    return sanitize_log_message(str(val))


class ZeroPiiLogFilter(logging.Filter):
    """Filtro aplicável a loggers/handlers bloqueando payloads e PII antes da emissão."""

    _is_iris_zero_pii_filter = True

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args:
                args_limpos = sanitize_log_value(record.args)
                if isinstance(args_limpos, list):
                    args_limpos = tuple(args_limpos)
                rendered = str(record.msg) % args_limpos
            else:
                rendered = sanitize_log_value(record.msg) if isinstance(record.msg, (Mapping, list, tuple)) else str(record.msg)
        except Exception:  # noqa: BLE001
            rendered = f"{record.msg}"

        record.msg = sanitize_log_message(rendered)
        record.args = None

        if record.exc_info:
            exc_type = record.exc_info[0]
            exc_name = exc_type.__name__ if exc_type is not None else "Exception"
            record.exc_info = None
            record.exc_text = None
            record.msg = f"{record.msg} [exc={exc_name}]"
        elif record.exc_text:
            record.exc_text = sanitize_log_message(record.exc_text)

        return True


class ZeroPiiLogFormatter(logging.Formatter):
    """Formatter com barreira final anti-vazamento sobre qualquer linha serializada."""

    def format(self, record: logging.LogRecord) -> str:
        linha = super().format(record)
        return sanitize_log_message(linha)


def categorizar_violacoes_escopo(escopo: Any) -> list[str]:
    """Extrai apenas categorias fechadas de violação do escopo, sem palavras literais."""
    if escopo is None:
        return []
    cats: list[str] = []
    if getattr(escopo, "conceitos_perdidos", None):
        cats.append("conceito_ausente")
    if getattr(escopo, "numeros_perdidos", None):
        cats.append("numero_ausente")
    if getattr(escopo, "negacoes_perdidas", None):
        cats.append("negacao_ausente")
    if getattr(escopo, "palavras_perdidas", None):
        cats.append("palavra_ausente")
    if getattr(escopo, "palavras_novas", None):
        cats.append("palavra_fora_vocabulario")
    if getattr(escopo, "ordem_alterada", False):
        cats.append("ordem_alterada")
    if getattr(escopo, "estrutura_alterada", False):
        cats.append("texto_alterado_alem_destaque")
    if not cats and not getattr(escopo, "aprovado", True):
        cats.append("outra")
    return cats


def categoria_fallback(motivo: Optional[str]) -> str:
    """Normaliza o motivo de fallback para uma enumeração fechada segura."""
    if not motivo:
        return "nenhum"
    norm = str(motivo).strip()
    if norm.startswith("falha_llm"):
        return "falha_llm"
    fechados = {
        "provedor_sem_modelo",
        "regra_comandos_multiplos",
        "conferente_palavra_perdida",
        "escopo_reprovado",
        "sem_evidencia",
        "nenhuma_intervencao_aprovada",
    }
    return norm if norm in fechados else "outro"


class _IrisNamespaceZeroPiiFilter(ZeroPiiLogFilter):
    """Aplica filtragem Zero-PII apenas a registros do namespace `iris` em handlers compartilhados."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == IRIS_ROOT_LOGGER_NAME or record.name.startswith(f"{IRIS_ROOT_LOGGER_NAME}."):
            return super().filter(record)
        return True


def _attach_filter_idempotent(target: logging.Filterer) -> None:
    if not any(getattr(f, "_is_iris_zero_pii_filter", False) for f in target.filters):
        target.addFilter(ZeroPiiLogFilter())


def _attach_namespace_filter_idempotent(target: logging.Filterer) -> None:
    if not any(getattr(f, "_is_iris_zero_pii_filter", False) for f in target.filters):
        target.addFilter(_IrisNamespaceZeroPiiFilter())


def configure_zero_pii_logging(level: int = logging.INFO) -> logging.Logger:
    """Instala filtros e formatter Zero-PII nos loggers do namespace `iris` e handlers ativos."""
    iris_logger = logging.getLogger(IRIS_ROOT_LOGGER_NAME)
    op_logger = logging.getLogger(OPERATIONAL_LOGGER_NAME)
    root_logger = logging.getLogger()

    _attach_filter_idempotent(iris_logger)
    _attach_filter_idempotent(op_logger)

    for nome, lg in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(lg, logging.Logger) and (nome == IRIS_ROOT_LOGGER_NAME or nome.startswith(f"{IRIS_ROOT_LOGGER_NAME}.")):
            _attach_filter_idempotent(lg)

    if not iris_logger.handlers and not root_logger.handlers:
        iris_logger.addHandler(logging.StreamHandler())

    for h in root_logger.handlers:
        _attach_namespace_filter_idempotent(h)

    for h in iris_logger.handlers:
        _attach_filter_idempotent(h)
        if not isinstance(h.formatter, ZeroPiiLogFormatter):
            h.setFormatter(ZeroPiiLogFormatter("%(levelname)s:%(name)s:%(message)s"))

    for h in op_logger.handlers:
        _attach_filter_idempotent(h)
        if not isinstance(h.formatter, ZeroPiiLogFormatter):
            h.setFormatter(ZeroPiiLogFormatter("%(message)s"))

    if iris_logger.level == logging.NOTSET:
        iris_logger.setLevel(level)
    return op_logger


def _sanitize_http_path(path: str) -> str:
    base = str(path or "").split("?", 1)[0].strip()
    return base[:120] if re.fullmatch(r"/[A-Za-z0-9_./\-]*", base) else "/rota_invalida"


def log_http_operational_event(
    *,
    method: str,
    path: str,
    status_code: int,
    latency_s: float,
    error_code: Optional[str] = None,
) -> dict[str, Any]:
    """Emite evento JSON de execução HTTP contendo exclusivamente metadados operacionais."""
    configure_zero_pii_logging()
    clean_method = str(method or "UNKNOWN").upper()[:12]
    clean_path = _sanitize_http_path(path)
    clean_err = (
        str(error_code).strip()
        if error_code and re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", str(error_code).strip())
        else None
    )
    payload: dict[str, Any] = {
        "event": "http_request",
        "trace_id": current_trace_id(),
        "method": clean_method,
        "path": clean_path,
        "status_code": int(status_code),
        "latency_s": round(float(latency_s), 4),
        "latency_ms": round(float(latency_s) * 1000.0, 2),
        "error_code": clean_err,
    }
    logging.getLogger(OPERATIONAL_LOGGER_NAME).info(json.dumps(payload, ensure_ascii=False))
    return payload


def log_agent_operational_event(
    *,
    nivel: int,
    selected_ids: Sequence[str],
    total_questoes: int,
    pii_substituicoes: int,
    total_tokens: int,
    prompt_tokens: int,
    completion_tokens: int,
    latency_s: float,
    trcc_scores: Sequence[float],
    aprovadas_auditor: int,
    requerem_revisao_humana: int,
    provider: str,
    model: str,
    fallbacks: Sequence[str] = (),
    violacoes: Sequence[str] = (),
    rag_backend: str = "desconhecido",
    rag_metodo_efetivo: str = "desconhecido",
    rerank_top1_score: Optional[float] = None,
) -> dict[str, Any]:
    """Emite evento JSON operacional do pipeline multiagentes sem conteúdo textual."""
    configure_zero_pii_logging()
    scores = [round(float(s), 4) for s in trcc_scores if s is not None]
    trcc_mean = round(sum(scores) / len(scores), 4) if scores else None
    trcc_min = round(min(scores), 4) if scores else None

    safe_selected = [
        str(cid) for cid in selected_ids if re.fullmatch(r"[a-z0-9_]{3,80}", str(cid))
    ]
    safe_provider = str(provider or "unknown")[:32]
    safe_model = (
        str(model)
        if model and re.fullmatch(r"[A-Za-z0-9._:/\-]{1,64}", str(model))
        else "modelo_suprimido"
    )
    safe_fallbacks = list(dict.fromkeys(categoria_fallback(f) for f in fallbacks if f and f != "nenhum"))
    safe_violacoes = list(dict.fromkeys(str(v) for v in violacoes if str(v) in {
        "conceito_ausente",
        "palavra_ausente",
        "palavra_fora_vocabulario",
        "ordem_alterada",
        "texto_alterado_alem_destaque",
        "outra",
    }))
    backend_norm = str(rag_backend or "desconhecido").strip().lower()
    safe_rag_backend = (
        backend_norm
        if backend_norm in {"pgvector", "bm25", "fallback_bm25", "desconhecido"}
        else "desconhecido"
    )
    metodo_norm = str(rag_metodo_efetivo or "desconhecido").strip()
    safe_rag_metodo = (
        metodo_norm
        if re.fullmatch(r"[A-Za-z0-9_+:\-]{1,40}", metodo_norm)
        else "desconhecido"
    )
    safe_top1_score = round(float(rerank_top1_score), 4) if rerank_top1_score is not None else None

    payload: dict[str, Any] = {
        "event": "agent_execution",
        "trace_id": current_trace_id(),
        "status_code": 200,
        "nivel": int(nivel),
        "selected_ids": safe_selected,
        "total_questoes": int(total_questoes),
        "pii_substituicoes": int(pii_substituicoes),
        "total_tokens": int(total_tokens),
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "latency_s": round(float(latency_s), 4),
        "latency_ms": round(float(latency_s) * 1000.0, 2),
        "trcc_scores": scores,
        "trcc_mean": trcc_mean,
        "trcc_min": trcc_min,
        "aprovadas_auditor": int(aprovadas_auditor),
        "requerem_revisao_humana": int(requerem_revisao_humana),
        "provider": safe_provider,
        "model": safe_model,
        "fallbacks": safe_fallbacks,
        "violacoes": safe_violacoes,
        "rag_backend": safe_rag_backend,
        "rag_metodo_efetivo": safe_rag_metodo,
        "rerank_top1_score": safe_top1_score,
    }
    with _OPS_LOCK:
        _RECENT_AGENT_EVENTS.append(dict(payload))
    logging.getLogger(OPERATIONAL_LOGGER_NAME).info(json.dumps(payload, ensure_ascii=False))
    return payload


def reset_operational_metrics() -> None:
    """Limpa o buffer circular em memória de telemetria operacional (uso em testes)."""
    with _OPS_LOCK:
        _RECENT_AGENT_EVENTS.clear()


def _percentile(sorted_vals: list[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 4)
    idx = min(len(sorted_vals) - 1, max(0, int(round((len(sorted_vals) - 1) * pct))))
    return round(sorted_vals[idx], 4)


def summarize_operational_metrics() -> dict[str, Any]:
    """Consolida métricas operacionais recentes em memória (100% Zero-PII e Zero-Database)."""
    with _OPS_LOCK:
        eventos = list(_RECENT_AGENT_EVENTS)

    total = len(eventos)
    if total == 0:
        return {
            "window_capacity": _RECENT_AGENT_EVENTS.maxlen,
            "total_executions": 0,
            "fallback_executions": 0,
            "fallback_rate": 0.0,
            "fallbacks_by_category": {},
            "human_review_questions": 0,
            "total_questions": 0,
            "human_review_rate": 0.0,
            "latency_p50_s": None,
            "latency_p95_s": None,
            "trcc_mean": None,
            "trcc_min": None,
            "rag_backends": {},
            "recent_trace_ids": [],
        }

    fallbacks_by_cat: dict[str, int] = {}
    rag_backends: dict[str, int] = {}
    fallback_execs = 0
    total_questions = 0
    human_review_questions = 0
    latencies: list[float] = []
    all_trcc: list[float] = []
    trace_ids: list[str] = []

    for ev in eventos:
        fbs = [str(f) for f in (ev.get("fallbacks") or []) if f]
        if fbs:
            fallback_execs += 1
            for cat in fbs:
                fallbacks_by_cat[cat] = fallbacks_by_cat.get(cat, 0) + 1
        bk = str(ev.get("rag_backend") or "desconhecido")
        rag_backends[bk] = rag_backends.get(bk, 0) + 1
        total_questions += int(ev.get("total_questoes") or 0)
        human_review_questions += int(ev.get("requerem_revisao_humana") or 0)
        latencies.append(float(ev.get("latency_s") or 0.0))
        for s in ev.get("trcc_scores") or []:
            if s is not None:
                all_trcc.append(float(s))
        tid = ev.get("trace_id")
        if tid:
            trace_ids.append(str(tid))

    latencies.sort()
    return {
        "window_capacity": _RECENT_AGENT_EVENTS.maxlen,
        "total_executions": total,
        "fallback_executions": fallback_execs,
        "fallback_rate": round(fallback_execs / total, 4),
        "fallbacks_by_category": fallbacks_by_cat,
        "human_review_questions": human_review_questions,
        "total_questions": total_questions,
        "human_review_rate": round(human_review_questions / max(total_questions, 1), 4),
        "latency_p50_s": _percentile(latencies, 0.50),
        "latency_p95_s": _percentile(latencies, 0.95),
        "trcc_mean": round(sum(all_trcc) / len(all_trcc), 4) if all_trcc else None,
        "trcc_min": round(min(all_trcc), 4) if all_trcc else None,
        "rag_backends": rag_backends,
        "recent_trace_ids": trace_ids[-10:],
    }


@dataclass
class CapturedOperationalLogs:
    """Buffer em memória com linhas e eventos estruturados capturados durante testes."""

    stream: io.StringIO = field(default_factory=io.StringIO)
    messages: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.stream.getvalue()

    @property
    def events(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for linha in self.text.splitlines():
            s = linha.strip()
            if s.startswith("{") and s.endswith("}"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, dict) and "event" in parsed:
                        out.append(parsed)
                except ValueError:
                    continue
        return out


class _CaptureMemoryHandler(logging.Handler):
    def __init__(self, captured: CapturedOperationalLogs) -> None:
        super().__init__(level=logging.INFO)
        self.captured = captured
        self.addFilter(ZeroPiiLogFilter())
        self.setFormatter(ZeroPiiLogFormatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.captured.messages.append(msg)
            self.captured.stream.write(msg + "\n")
        except Exception:  # noqa: BLE001
            self.handleError(record)


@contextlib.contextmanager
def capture_operational_logs() -> Iterator[CapturedOperationalLogs]:
    """Captura em memória os logs de `iris.*` com filtros Zero-PII ativos (para auditoria e testes)."""
    configure_zero_pii_logging(logging.INFO)
    iris_logger = logging.getLogger(IRIS_ROOT_LOGGER_NAME)
    prev_level = iris_logger.level
    iris_logger.setLevel(logging.INFO)
    captured = CapturedOperationalLogs()
    handler = _CaptureMemoryHandler(captured)
    iris_logger.addHandler(handler)
    try:
        yield captured
    finally:
        iris_logger.removeHandler(handler)
        iris_logger.setLevel(prev_level)
