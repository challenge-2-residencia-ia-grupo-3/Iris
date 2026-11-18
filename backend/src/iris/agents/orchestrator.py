"""Orquestrador do Sistema Multiagentes (Semana 4 — Issues #15, #16, #17, #18 e #19).

Conecta os quatro agentes especializados em um fluxo único e rastreável:
  1. Agente Extrator Curricular (Issue #17) -> invariantes e travas da BNCC;
  2. Agente Estrategista RAG (Issue #16)     -> diretiva fundamentada com citações [T1..Tn];
  3. Agente Adaptador Pedagógico (Issue #18) -> minuta com isolamento estrito de escopo;
  4. Agente Auditor (Issue #19)              -> TRCC, prevenção anti-muleta e auto-correção.

Opera 100% em memória sobre entrada já sanitizada pelo gateway de PII (RNF-01 / RNF-02) e devolve
tanto o histórico completo de colaboração entre agentes quanto o pacote pronto para a Etapa 5.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from iris.agents.adapter_agent import AdapterAgent, CicloComAuditor, resumir_ciclo
from iris.agents.auditor import (
    AgenteAuditor,
    ResultadoAuditoria,
    caracteristicas_nao_selecionadas,
)
from iris.agents.curriculum_extractor import CurriculumExtractorAgent
from iris.agents.strategist_agent import StrategistAgent
from iris.core.llm_client import HybridLLMClient, LLMResponse, get_llm_client
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS, verificar_escopo
from iris.parsers.structural_decomposer import decompose_material
from iris.schemas.adaptation import AdaptationRequest, ScopeReport
from iris.schemas.curriculum import CurriculumInvariants, ExtractionResult
from iris.schemas.strategy import StrategyRequest, StrategyResult
from iris.security.operational_logger import (
    categorizar_violacoes_escopo,
    log_agent_operational_event,
    sentinel_context,
)
from iris.security.pii_scrubber import sanitize_pii

logger = logging.getLogger(__name__)

PROVEDORES_SEM_MODELO = frozenset({"extractive", "mock", "offline"})
PROVEDORES_ACEITOS = frozenset(
    {"auto", "extractive", "mock", "offline", "ollama", "groq", "anthropic", "claude", "sonnet"}
)
_CONCEITO_GENERICO = "conteudo_curricular"


class AuditAttemptTrace(BaseModel):
    """Registro de uma tentativa de adaptação avaliada pelo Agente Auditor."""

    tentativa: int
    texto_minuta: str
    justificativas: list[str] = Field(default_factory=list)
    escopo_aprovado: bool
    violacoes_escopo: list[str] = Field(default_factory=list)
    trcc: Optional[float] = None
    conceitos_retidos: list[str] = Field(default_factory=list)
    conceitos_ausentes: list[str] = Field(default_factory=list)
    intocaveis_ausentes: list[str] = Field(default_factory=list)
    resolucao_indevida: bool = False
    intrusoes: list[str] = Field(default_factory=list)
    aprovado_auditor: bool = False
    motivos_auditor: list[str] = Field(default_factory=list)
    feedback_gerado: Optional[str] = None
    total_ms: float = 0.0


class QuestionMultiAgentTrace(BaseModel):
    """Rastreamento completo da colaboração dos 4 agentes em uma questão."""

    id: str
    numero_original: str
    original: str
    adaptado: str
    justificativas: list[str] = Field(default_factory=list)
    id_caracteristica: str
    caracteristicas_selecionadas: list[str] = Field(default_factory=list)
    nivel: int
    adaptacao_aplicada: bool
    aprovado_final: bool
    requer_revisao_humana: bool
    extrator: ExtractionResult
    estrategista: StrategyResult
    tentativas: list[AuditAttemptTrace] = Field(default_factory=list)
    ciclo_resumo: dict[str, Any] = Field(default_factory=dict)


class MultiAgentMaterialRequest(BaseModel):
    """Requisição unificada para rodar o Sistema Multiagentes sobre um material didático."""

    text: str = Field(..., min_length=15, description="Texto integral ou questão a adaptar.")
    titulo: Optional[str] = Field(default=None, description="Título opcional da atividade.")
    selected_ids: list[str] = Field(
        default_factory=lambda: [ID_COMANDOS_MULTIPLOS],
        min_length=1,
        description="Características funcionais atômicas selecionadas na Etapa 2.",
    )
    nivel: int = Field(default=2, ge=1, le=3, description="Nível de andaime (1, 2 ou 3).")
    disciplina: Optional[str] = None
    ano_escolar: Optional[str] = None
    trava_manual_docente: Optional[list[str]] = None
    invariantes_etapa3: Optional[dict[str, Any]] = Field(
        default=None,
        description="Contrato AuditorInvariantsContract validado na Etapa 3 (termos intocáveis, BNCC e alerta anti-muleta).",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Provedor LLM ('auto', 'anthropic', 'claude', 'sonnet', 'ollama', 'groq', 'extractive').",
    )
    model: Optional[str] = None
    metodo_rag: str = Field(default="bm25", description="Método de busca no RAG ('bm25', 'qwen3+rerank50', 'hibrido').")
    max_tentativas: int = Field(default=3, ge=1, le=3)
    intrusao_bloqueia: bool = Field(
        default=False,
        description="Se True, acusação de intrusão pelo juiz LLM reprova a tentativa e dispara auto-correção.",
    )
    simular_autocorrecao: bool = Field(
        default=False,
        description="Demonstração controlada: injeta falha curricular na 1ª tentativa para exibir o Auditor corrigindo o Adaptador na 2ª.",
    )

    @field_validator("selected_ids")
    @classmethod
    def _normalizar_ids(cls, valor: list[str]) -> list[str]:
        limpos = list(dict.fromkeys(str(v).strip() for v in valor if str(v).strip()))
        if not limpos:
            raise ValueError("Informe pelo menos 1 característica funcional em selected_ids.")
        return limpos

    @field_validator("provider")
    @classmethod
    def _validar_provider(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        norm = valor.strip().lower()
        if not norm:
            return None
        if norm not in PROVEDORES_ACEITOS:
            raise ValueError(
                f"Provedor inválido: {valor!r}. Valores aceitos: auto, anthropic, ollama, groq, extractive."
            )
        return norm

    @field_validator("trava_manual_docente", mode="before")
    @classmethod
    def _normalizar_trava_manual(cls, valor: Any) -> Optional[list[str]]:
        if valor is None:
            return None
        if isinstance(valor, str):
            itens = [p.strip() for p in re.split(r"[;\n,]", valor) if p.strip()]
            return itens or None
        if isinstance(valor, (list, tuple, set)):
            itens = [str(p).strip() for p in valor if str(p).strip()]
            return itens or None
        return None


class MultiAgentMaterialResponse(BaseModel):
    """Resposta consolidada do pipeline multiagentes (telemetria, trace por questão e payload Etapa 5)."""

    status: str = "success"
    titulo: str
    provider: str
    model: str
    nivel: int
    selected_ids: list[str]
    pii_substituicoes: int
    total_questoes: int
    aprovadas_auditor: int
    requerem_revisao_humana: int
    total_ms: float
    total_tokens: int
    etapa5_entrada: dict[str, Any]
    questoes_trace: list[QuestionMultiAgentTrace]


class _JuizDeterministicoOffline:
    """Juiz estruturado para modo offline/extractive sem dependência de LLM externo."""

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900) -> LLMResponse:
        veredito = json.dumps(
            {
                "resolveu_questao": False,
                "evidencia_resolucao": "",
                "modificacoes_intrusivas": [],
            }
        )
        return LLMResponse(text=veredito, provider="extractive", model="deterministic-judge")


class _JuizResiliente:
    """Encapsula um HybridLLMClient para falhar fechado (sem exceção não tratada) em erros de rede."""

    def __init__(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 900) -> Any:
        try:
            return self.llm_client.generate(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - falha fechada no Auditor sem derrubar a API
            logger.warning("Falha na consulta ao juiz LLM (%s); Auditor falhará fechado.", type(exc).__name__)
            return ""


def _resolver_cliente_llm(
    provider: Optional[str],
    model: Optional[str],
    explicit_client: Optional[HybridLLMClient],
) -> HybridLLMClient:
    if explicit_client is not None:
        return explicit_client

    if provider is None or provider == "auto":
        # Prioriza Anthropic Claude quando ANTHROPIC_API_KEY está configurada no .env
        try:
            claude = get_llm_client(provider="anthropic", model=model)
            if claude.status().get("primary_available"):
                return claude
        except Exception:  # noqa: BLE001
            pass

        candidato = get_llm_client(model=model)
        try:
            status = candidato.status()
            if status.get("primary_available"):
                return candidato
        except Exception:  # noqa: BLE001
            pass
        return get_llm_client(provider="extractive")

    return get_llm_client(provider=provider, model=model)


def _construir_juiz(llm_client: Any) -> Any:
    provider_name = str(getattr(llm_client, "provider_name", "custom")).lower()
    if provider_name in PROVEDORES_SEM_MODELO:
        return _JuizDeterministicoOffline()
    return _JuizResiliente(llm_client)


def _montar_texto_questao(
    statement: str,
    options: list[Any],
    raw_text: str,
    original_number: str,
    contexto_apoio: Optional[str],
) -> str:
    partes = [statement.strip()]
    if options:
        partes.extend(f"{opt.letter}) {opt.text}".strip() for opt in options)
    texto = "\n".join(p for p in partes if p).strip()
    if len(texto) >= 15:
        return texto
    if raw_text.strip() and len(raw_text.strip()) >= 15:
        return raw_text.strip()
    if contexto_apoio and len(f"{contexto_apoio}\n{texto}".strip()) >= 15:
        return f"{contexto_apoio}\n{texto}".strip()
    prefixado = f"Questão {original_number}: {texto}".strip()
    return prefixado if len(prefixado) >= 15 else (texto or raw_text).ljust(15)


def _sabotar_para_demonstracao(minuta: str, conceitos: list[str]) -> str:
    """Produz uma violação objetiva na 1ª tentativa para demonstrar a auto-correção pelo Auditor."""
    for conceito in conceitos:
        c = conceito.strip()
        if not c or c == _CONCEITO_GENERICO:
            continue
        padrao = re.compile(re.escape(c), flags=re.IGNORECASE)
        if padrao.search(minuta):
            alterado = padrao.sub("[termo omitido]", minuta)
            if alterado != minuta:
                return alterado
    return f"{minuta.rstrip()}\nGabarito: A"


def _escolher_caracteristica_principal(selected_ids: list[str]) -> str:
    if ID_COMANDOS_MULTIPLOS in selected_ids:
        return ID_COMANDOS_MULTIPLOS
    return selected_ids[0]


def _extrair_titulo_padrao(titulo_solicitado: Optional[str], header: Optional[str]) -> str:
    if titulo_solicitado and titulo_solicitado.strip():
        return titulo_solicitado.strip()[:120]
    if header and header.strip():
        primeira_linha = next((ln.strip() for ln in header.splitlines() if ln.strip()), "")
        if primeira_linha:
            return primeira_linha[:120]
    return "Atividade Pedagógica Adaptada"


class MultiAgentOrchestrator:
    """Coordena Extrator Curricular, Estrategista RAG, Adaptador e Auditor em sequência."""

    def __init__(
        self,
        llm_client: Optional[HybridLLMClient] = None,
        juiz_client: Optional[Any] = None,
    ) -> None:
        self._explicit_llm = llm_client
        self._explicit_juiz = juiz_client

    def run(self, request: MultiAgentMaterialRequest | dict[str, Any]) -> MultiAgentMaterialResponse:
        """Executa o fluxo completo multiagentes sobre um material e retorna trace + entrada da Etapa 5."""
        req = (
            request
            if isinstance(request, MultiAgentMaterialRequest)
            else MultiAgentMaterialRequest.model_validate(request)
        )

        # Valida previamente as características contra o catálogo oficial (SSOT)
        nao_selecionadas = caracteristicas_nao_selecionadas(req.selected_ids)

        llm_client = _resolver_cliente_llm(req.provider, req.model, self._explicit_llm)
        juiz = self._explicit_juiz if self._explicit_juiz is not None else _construir_juiz(llm_client)

        extrator = CurriculumExtractorAgent(llm_client=llm_client)
        estrategista = StrategistAgent(llm_client=llm_client)
        adaptador = AdapterAgent(llm_client=llm_client)
        auditor = AgenteAuditor(
            juiz=juiz,
            limiar=0.95,
            intrusao_bloqueia=req.intrusao_bloqueia,
        )

        t_inicio = time.perf_counter()

        with sentinel_context(req.text):
            # 1. Sanitização preventiva de PII antes de qualquer processamento ou chamada de IA
            texto_sanitizado, pii_substituicoes = sanitize_pii(req.text)
            texto_limpo = texto_sanitizado.strip()
            if len(texto_limpo) < 15:
                raise ValueError("Após sanitização, o texto ficou abaixo do mínimo de 15 caracteres.")

            # 2. Decomposição estrutural determinística do material em questões e textos de apoio
            estrutura = decompose_material(texto_limpo)
            ctx_por_id = {cb.id: cb for cb in estrutura.context_blocks}
            id_carac_principal = _escolher_caracteristica_principal(req.selected_ids)
            titulo_final = _extrair_titulo_padrao(req.titulo, estrutura.header)

            itens_questoes: list[tuple[str, str, str, Optional[str]]] = []
            if estrutura.questions:
                for idx, q in enumerate(estrutura.questions, start=1):
                    contextos = [
                        ctx_por_id[cid].text
                        for cid in (q.context_refs or [])
                        if cid in ctx_por_id and ctx_por_id[cid].text.strip()
                    ]
                    ctx_apoio = "\n\n".join(contextos) if contextos else None
                    enunciado_q = _montar_texto_questao(
                        statement=q.statement,
                        options=list(q.options or []),
                        raw_text=q.raw_text,
                        original_number=q.original_number,
                        contexto_apoio=ctx_apoio,
                    )
                    itens_questoes.append((q.id or f"q_{idx}", q.original_number or str(idx), enunciado_q, ctx_apoio))
            else:
                itens_questoes.append(("q_1", "1", texto_limpo, None))

            traces: list[QuestionMultiAgentTrace] = []
            etapa5_questoes: list[dict[str, Any]] = []
            modelos_usados: list[str] = []
            total_tokens = 0
            prompt_tokens_total = 0
            completion_tokens_total = 0
            trcc_scores: list[float] = []
            fallbacks_ocorridos: list[str] = []
            violacoes_ocorridas: list[str] = []

            for qid, num_orig, enunciado_q, ctx_apoio in itens_questoes:
                # --- Agente 1: Extrator Curricular (#17) ---
                extracao = extrator.extract_with_telemetry(
                    request=enunciado_q,
                    contexto_apoio=ctx_apoio,
                    disciplina=req.disciplina,
                    ano_escolar=req.ano_escolar,
                    trava_manual_docente=req.trava_manual_docente,
                    question_id=qid,
                )

                if req.invariantes_etapa3 and req.invariantes_etapa3.get("blindagem_ativa"):
                    inv = extracao.invariants
                    conceitos_etapa3 = [
                        str(c).strip()
                        for c in (req.invariantes_etapa3.get("conceitos_obrigatorios") or [])
                        if str(c).strip()
                    ]
                    if conceitos_etapa3:
                        inv.conceitos_obrigatorios = list(
                            dict.fromkeys([*inv.conceitos_obrigatorios, *conceitos_etapa3])
                        )
                    intocaveis_etapa3 = [
                        str(t).strip()
                        for t in (req.invariantes_etapa3.get("termos_tecnicos_intocaveis") or [])
                        if str(t).strip()
                    ]
                    if intocaveis_etapa3:
                        inv.termos_tecnicos_intocaveis = list(
                            dict.fromkeys([*inv.termos_tecnicos_intocaveis, *intocaveis_etapa3])
                        )
                    habilidade_etapa3 = str(req.invariantes_etapa3.get("habilidade_bncc") or "").strip()
                    if habilidade_etapa3 and not inv.habilidade_bncc_sugerida:
                        inv.habilidade_bncc_sugerida = habilidade_etapa3
                    alerta_etapa3 = str(req.invariantes_etapa3.get("alerta_anti_muleta_auditor") or "").strip()
                    if alerta_etapa3:
                        inv.alerta_anti_muleta = (
                            f"{inv.alerta_anti_muleta} | {alerta_etapa3}"
                            if inv.alerta_anti_muleta
                            else alerta_etapa3
                        )

                # --- Agente 2: Estrategista RAG (#16) ---
                estrategia = estrategista.strategize(
                    StrategyRequest(
                        caracteristicas=req.selected_ids,
                        nivel=req.nivel,
                        invariantes=extracao.invariants,
                        enunciado=enunciado_q,
                        metodo=req.metodo_rag,
                        question_id=qid,
                    )
                )

                # --- Agente 3 (Adaptador #18) <-> Agente 4 (Auditor #19) ---
                pedido_adapt = AdaptationRequest(
                    enunciado=enunciado_q,
                    id_caracteristica=id_carac_principal,
                    nivel=req.nivel,
                    invariantes=extracao.invariants,
                    diretiva_psicopedagogica=estrategia.diretiva or None,
                    question_id=qid,
                )
                ciclo = CicloComAuditor(adaptador, pedido_adapt)
                textos_avaliados: list[str] = []
                simulado_na_primeira = False

                def _adaptar_com_rastreio(
                    feedback: Optional[str],
                    minuta_anterior: Optional[str],
                    _ciclo: CicloComAuditor = ciclo,
                    _invariantes: CurriculumInvariants = extracao.invariants,
                    _textos: list[str] = textos_avaliados,
                ) -> str:
                    nonlocal simulado_na_primeira
                    minuta = _ciclo(feedback, minuta_anterior)
                    if req.simular_autocorrecao and feedback is None and not simulado_na_primeira:
                        simulado_na_primeira = True
                        minuta = _sabotar_para_demonstracao(minuta, _invariantes.conceitos_obrigatorios)
                    _textos.append(minuta)
                    return minuta

                relatorio = auditor.executar_ciclo(
                    original=enunciado_q,
                    travas=extracao.invariants,
                    adaptar=_adaptar_com_rastreio,
                    nao_selecionadas=nao_selecionadas,
                    max_tentativas=req.max_tentativas,
                )

                trava_lista = [
                    *extracao.invariants.conceitos_obrigatorios,
                    *extracao.invariants.termos_tecnicos_intocaveis,
                ]
                tentativas_trace: list[AuditAttemptTrace] = []
                for idx_t, (res_aud, res_adap, texto_aval) in enumerate(
                    zip(relatorio.tentativas, ciclo.resultados, textos_avaliados), start=1
                ):
                    escopo_eval: ScopeReport = (
                        verificar_escopo(enunciado_q, texto_aval, id_carac_principal, req.nivel, trava_lista)
                        if texto_aval != res_adap.texto_adaptado
                        else res_adap.escopo
                    )
                    violacoes_ocorridas.extend(categorizar_violacoes_escopo(escopo_eval))
                    tentativas_trace.append(
                        AuditAttemptTrace(
                            tentativa=idx_t,
                            texto_minuta=texto_aval,
                            justificativas=list(res_adap.justificativas),
                            escopo_aprovado=escopo_eval.aprovado,
                            violacoes_escopo=list(escopo_eval.violacoes),
                            trcc=res_aud.trcc.trcc,
                            conceitos_retidos=list(res_aud.trcc.encontrados),
                            conceitos_ausentes=list(res_aud.trcc.ausentes),
                            intocaveis_ausentes=list(res_aud.intocaveis_ausentes),
                            resolucao_indevida=res_aud.resolucao_indevida,
                            intrusoes=list(res_aud.intrusoes),
                            aprovado_auditor=res_aud.aprovado,
                            motivos_auditor=list(res_aud.motivos),
                            feedback_gerado=None if res_aud.aprovado else res_aud.feedback(),
                            total_ms=res_adap.telemetry.total_ms,
                        )
                    )

                if relatorio.tentativas and relatorio.tentativas[-1].trcc.trcc is not None:
                    trcc_scores.append(float(relatorio.tentativas[-1].trcc.trcc))

                resumo_q = resumir_ciclo(
                    [extracao.telemetry, estrategia.telemetry, *ciclo.telemetrias],
                    req.nivel,
                )
                total_tokens += int(resumo_q["total_tokens"])
                prompt_tokens_total += int(resumo_q.get("prompt_tokens", 0))
                completion_tokens_total += int(resumo_q.get("completion_tokens", 0))

                for tel in (extracao.telemetry, estrategia.telemetry, *ciclo.telemetrias):
                    if tel.model and tel.model != "deterministic-fallback":
                        modelos_usados.append(tel.model)
                    if getattr(tel, "used_fallback", False) and getattr(tel, "motivo_fallback", None):
                        fallbacks_ocorridos.append(str(tel.motivo_fallback))

                ultimo_adap = ciclo.resultados[-1]
                adaptacao_aplicada = relatorio.texto_final.strip() != enunciado_q.strip()

                traces.append(
                    QuestionMultiAgentTrace(
                        id=qid,
                        numero_original=num_orig,
                        original=enunciado_q,
                        adaptado=relatorio.texto_final,
                        justificativas=list(ultimo_adap.justificativas),
                        id_caracteristica=id_carac_principal,
                        caracteristicas_selecionadas=list(req.selected_ids),
                        nivel=req.nivel,
                        adaptacao_aplicada=adaptacao_aplicada,
                        aprovado_final=relatorio.aprovado,
                        requer_revisao_humana=relatorio.requer_revisao_humana,
                        extrator=extracao,
                        estrategista=estrategia,
                        tentativas=tentativas_trace,
                        ciclo_resumo=resumo_q,
                    )
                )
                etapa5_questoes.append(
                    {
                        "id": qid,
                        "original": enunciado_q,
                        "adaptado": relatorio.texto_final,
                        "justificativas": list(ultimo_adap.justificativas),
                        "id_caracteristica": id_carac_principal,
                        "nivel": req.nivel,
                        "adaptacao_aplicada": adaptacao_aplicada,
                    }
                )

            total_ms = round((time.perf_counter() - t_inicio) * 1000, 2)
            aprovadas = sum(1 for t in traces if t.aprovado_final)
            revisao_humana = sum(1 for t in traces if t.requer_revisao_humana)
            provider_str = str(getattr(llm_client, "provider_name", "custom"))
            model_str = modelos_usados[0] if modelos_usados else "deterministic-fallback"

            log_agent_operational_event(
                nivel=req.nivel,
                selected_ids=req.selected_ids,
                total_questoes=len(traces),
                pii_substituicoes=pii_substituicoes,
                total_tokens=total_tokens,
                prompt_tokens=prompt_tokens_total,
                completion_tokens=completion_tokens_total,
                latency_s=total_ms / 1000.0,
                trcc_scores=trcc_scores,
                aprovadas_auditor=aprovadas,
                requerem_revisao_humana=revisao_humana,
                provider=provider_str,
                model=model_str,
                fallbacks=fallbacks_ocorridos,
                violacoes=violacoes_ocorridas,
            )

        return MultiAgentMaterialResponse(
            status="success",
            titulo=titulo_final,
            provider=provider_str,
            model=model_str,
            nivel=req.nivel,
            selected_ids=list(req.selected_ids),
            pii_substituicoes=pii_substituicoes,
            total_questoes=len(traces),
            aprovadas_auditor=aprovadas,
            requerem_revisao_humana=revisao_humana,
            total_ms=total_ms,
            total_tokens=total_tokens,
            etapa5_entrada={
                "titulo": titulo_final,
                "questoes": etapa5_questoes,
            },
            questoes_trace=traces,
        )


def run_multiagent_adaptation(
    request: MultiAgentMaterialRequest | dict[str, Any],
    llm_client: Optional[HybridLLMClient] = None,
    juiz_client: Optional[Any] = None,
) -> MultiAgentMaterialResponse:
    """Atalho funcional para executar o fluxo completo dos 4 agentes."""
    return MultiAgentOrchestrator(llm_client=llm_client, juiz_client=juiz_client).run(request)
