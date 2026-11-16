"""Agente Estrategista RAG (História 2.1.1 / Issue #16).

Recebe as características ativadas pelo docente, o nível de andaime e, quando houver, as travas do
Agente Extrator. Para cada característica busca evidências na base científica com filtro estrito pela
barreira associada, monta o contexto numerado ``[T1]..[Tn]`` e pede ao modelo uma diretiva
psicopedagógica em que toda intervenção cita o trecho que a sustenta.

Duas conferências determinísticas cercam o modelo:
  * antes do prompt, todo trecho recuperado precisa trazer a barreira da característica; o que não
    trouxer é descartado e registrado em ``trechos_fora_do_filtro``;
  * depois da resposta, cada intervenção precisa citar trechos existentes que sirvam à própria
    característica, a característica precisa estar entre as ativadas, o texto não passa de 40
    palavras, não copia 12 ou mais palavras seguidas de um trecho (há documentos de licença
    restrita) e cada característica fica com no máximo 3 intervenções. A intervenção reprovada é
    descartada com o motivo.

Se a resposta do modelo for cortada no limite de tokens, as intervenções completas antes do corte
são aproveitadas e passam pela mesma conferência.

Sem modelo, com falha do modelo ou sem nenhuma intervenção aprovada, o agente devolve a diretiva de
reserva: as ações do catálogo para o nível, seguidas dos trechos recuperados para a característica.
A diretiva sai pronta para ``AdaptationRequest.diretiva_psicopedagogica``.
"""
from __future__ import annotations

import inspect
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from iris.core.llm_client import HybridLLMClient, LLMResponse, get_llm_client, strip_thinking_tags
from iris.rag.bridge import buscar_por_caracteristica_atomica, obter_trechos_base
from iris.rag.contexto import montar_contexto_estrategista
from iris.schemas.strategy import (
    StrategyIntervention,
    StrategyRequest,
    StrategyResult,
    StrategySource,
    StrategyTelemetry,
)

logger = logging.getLogger(__name__)

# Prompt de sistema estável (contexto e características vão no prompt do usuário) para reaproveitar o KV-cache
SYSTEM_PROMPT_ESTRATEGISTA = """Você é o Agente Estrategista Psicopedagógico da plataforma Íris (DUA, MEC e Funções Executivas).
Proponha intervenções de apoio para as características funcionais ativadas, fundamentadas somente nos TRECHOS fornecidos.

REGRAS:
1. Proponha de 1 a 3 intervenções por característica ativada, cada uma com no máximo 40 palavras.
2. Cada intervenção termina com a citação dos trechos que a sustentam, no formato [T1] ou [T1][T3].
3. Cite somente trechos indicados para a mesma característica da intervenção.
4. Não proponha intervenção para característica que não esteja em CARACTERÍSTICAS ATIVADAS.
5. Não resolva a questão, não dê a resposta e não altere os invariantes curriculares.
6. Respeite o AVISO DE USO de cada trecho.
7. Escreva com suas próprias palavras: não copie frases dos trechos.

Retorne APENAS um JSON válido no formato:
{"intervencoes": [{"id_caracteristica": "<id>", "texto": "<intervenção> [T1]"}]}"""

PROVEDORES_SEM_MODELO = frozenset({"extractive", "mock", "offline"})

LIMITE_PALAVRAS = 40
MAX_POR_CARACTERISTICA = 3
# 12 palavras seguidas iguais às de um trecho contam como cópia literal
JANELA_COPIA = 12
TOKENS_POR_CARACTERISTICA = 350
TOKENS_MAXIMO = 1400

_RE_CITACAO = re.compile(r"\[(T\d+)\]")
_RE_PALAVRA = re.compile(r"\w+")


def _janelas(texto: str, n: int = JANELA_COPIA) -> set[tuple[str, ...]]:
    palavras = _RE_PALAVRA.findall(_RE_CITACAO.sub(" ", texto).lower())
    return {tuple(palavras[i : i + n]) for i in range(len(palavras) - n + 1)}


def _ordenar_rotulos(rotulos: set[str]) -> list[str]:
    return sorted(rotulos, key=lambda r: int(r[1:]))


class StrategistAgent:
    """Agente de IA que transforma evidências filtradas por característica em diretiva citada."""

    def __init__(self, llm_client: Optional[HybridLLMClient] = None) -> None:
        self.llm_client = llm_client or get_llm_client()
        self._barreiras_por_trecho: Optional[dict[str, set[str]]] = None

    def strategize(self, request: StrategyRequest) -> StrategyResult:
        """Busca, monta o contexto, gera a diretiva e devolve diretiva, fontes, conferência e telemetria."""
        t0 = time.perf_counter()
        buscas, fora_do_filtro, sem_evidencia = self._buscar(request)
        busca_ms = round((time.perf_counter() - t0) * 1000, 2)

        metodo_solicitado = buscas[0]["metodo_solicitado"] if buscas else (request.metodo or "")
        metodo_efetivo = buscas[0]["metodo_efetivo"] if buscas else (request.metodo or "")
        fallback_busca = any(b["fallback_aplicado"] for b in buscas)
        com_evidencia = [b for b in buscas if b["trechos_rag"]]

        resposta_llm: Optional[LLMResponse] = None
        json_valido_direto = True
        json_recuperado = False
        motivo_fallback: Optional[str] = None
        intervencoes: list[StrategyIntervention] = []
        descartadas: list[dict[str, str]] = []
        n_propostas = 0
        fontes: list[dict[str, Any]] = []
        llm_ms = 0.0

        if not com_evidencia:
            motivo_fallback = "sem_evidencia"
        else:
            invariantes = self._invariantes_em_lista(request)
            contexto = montar_contexto_estrategista(com_evidencia, invariantes)
            fontes = contexto["fontes"]
            provider_configurado = getattr(self.llm_client, "provider_name", "custom")
            if provider_configurado in PROVEDORES_SEM_MODELO:
                motivo_fallback = "provedor_sem_modelo"
            else:
                t_llm = time.perf_counter()
                try:
                    resposta_llm = self._chamar_llm(
                        self._montar_prompt_usuario(request, contexto["contexto"]),
                        max_tokens=min(TOKENS_MAXIMO, TOKENS_POR_CARACTERISTICA * len(com_evidencia)),
                    )
                    propostas, json_valido_direto, json_recuperado = self._parse_json_response(resposta_llm.text)
                    n_propostas = len(propostas)
                    intervencoes, descartadas = self._conferir(propostas, fontes, contexto["caracteristicas"])
                    if not intervencoes:
                        motivo_fallback = "nenhuma_intervencao_aprovada"
                except Exception as e:
                    logger.warning(
                        "Falha na chamada ou parsing do LLM para o Agente Estrategista (%s). "
                        "Aplicando a diretiva de reserva.",
                        type(e).__name__,
                    )
                    motivo_fallback = f"falha_llm:{type(e).__name__}"
                    json_valido_direto = False
                llm_ms = round((time.perf_counter() - t_llm) * 1000, 2)
            if motivo_fallback:
                intervencoes = self._diretiva_de_reserva(com_evidencia, fontes, request.nivel)

        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        prompt_tokens = resposta_llm.prompt_tokens if resposta_llm else 0
        completion_tokens = resposta_llm.completion_tokens if resposta_llm else 0
        telemetria = StrategyTelemetry(
            question_id=request.question_id,
            caracteristicas=list(request.caracteristicas),
            nivel=request.nivel,
            metodo_solicitado=metodo_solicitado,
            metodo_efetivo=metodo_efetivo,
            fallback_busca=fallback_busca,
            provider=resposta_llm.provider if resposta_llm else str(getattr(self.llm_client, "provider_name", "custom")),
            model=resposta_llm.model if resposta_llm else "deterministic-fallback",
            used_fallback=motivo_fallback is not None,
            motivo_fallback=motivo_fallback,
            json_valido_direto=json_valido_direto and resposta_llm is not None,
            json_recuperado=json_recuperado,
            busca_ms=busca_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            n_trechos=len(fontes),
            n_intervencoes_propostas=n_propostas,
            n_intervencoes_aprovadas=sum(1 for i in intervencoes if i.origem == "modelo"),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        return StrategyResult(
            diretiva=self._renderizar(intervencoes),
            intervencoes=intervencoes,
            fontes=[StrategySource(**{k: v for k, v in f.items() if k != "trecho"}) for f in fontes],
            caracteristicas_sem_evidencia=sem_evidencia,
            trechos_fora_do_filtro=fora_do_filtro,
            intervencoes_descartadas=descartadas,
            telemetry=telemetria,
        )

    def _buscar(self, req: StrategyRequest) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        """Uma busca filtrada por característica; descarta trecho sem a barreira da característica."""
        barreiras = self._barreiras()
        buscas: list[dict[str, Any]] = []
        fora_do_filtro: list[str] = []
        sem_evidencia: list[str] = []
        for id_carac in req.caracteristicas:
            busca = buscar_por_caracteristica_atomica(
                id_caracteristica=id_carac,
                nivel=req.nivel,
                pergunta_adicional=req.enunciado or "",
                metodo=req.metodo,
                k=req.k,
            )
            barreira = busca["barreira_rag_associada"]
            dentro = []
            for t in busca["trechos_rag"]:
                if barreira in barreiras.get(t["chunk_id"], set()):
                    dentro.append(t)
                else:
                    fora_do_filtro.append(t["chunk_id"])
            busca["trechos_rag"] = dentro
            if not dentro:
                sem_evidencia.append(id_carac)
            buscas.append(busca)
        return buscas, fora_do_filtro, sem_evidencia

    def _barreiras(self) -> dict[str, set[str]]:
        if self._barreiras_por_trecho is None:
            self._barreiras_por_trecho = {
                c["chunk_id"]: set(c.get("barreiras") or []) for c in obter_trechos_base()
            }
        return self._barreiras_por_trecho

    @staticmethod
    def _invariantes_em_lista(req: StrategyRequest) -> list[str]:
        if req.invariantes is None:
            return []
        inv = req.invariantes
        return [*inv.conceitos_obrigatorios, *inv.termos_tecnicos_intocaveis]

    def _chamar_llm(self, prompt_usuario: str, max_tokens: int = TOKENS_POR_CARACTERISTICA) -> LLMResponse:
        sig = inspect.signature(self.llm_client.generate)
        params = sig.parameters
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if accepts_kwargs or ("system_prompt" in params and "json_mode" in params):
            return self.llm_client.generate(
                prompt=prompt_usuario,
                temperature=0.0,
                max_tokens=max_tokens,
                system_prompt=SYSTEM_PROMPT_ESTRATEGISTA,
                json_mode=True,
            )
        prompt_legado = f"{SYSTEM_PROMPT_ESTRATEGISTA}\n\n{prompt_usuario}"
        return self.llm_client.generate(prompt=prompt_legado, temperature=0.0, max_tokens=max_tokens)

    @staticmethod
    def _montar_prompt_usuario(req: StrategyRequest, contexto: str) -> str:
        partes = [contexto]
        if req.enunciado:
            partes.append(f"QUESTÃO (apenas para situar as intervenções; não a resolva):\n{req.enunciado}")
        return "\n\n".join(partes)

    @staticmethod
    def _parse_json_response(text: str) -> tuple[list[dict[str, Any]], bool, bool]:
        """Devolve (propostas, JSON direto, recuperado de resposta cortada)."""
        limpo = strip_thinking_tags(text).strip()
        json_direto = limpo.startswith("{") and limpo.endswith("}")
        match_code = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", limpo, flags=re.DOTALL)
        if match_code:
            json_str = match_code.group(1)
            json_direto = False
        else:
            match_brace = re.search(r"(\{.*\})", limpo, flags=re.DOTALL)
            json_str = match_brace.group(1) if match_brace else limpo

        try:
            dados = json.loads(json_str)
        except json.JSONDecodeError:
            recuperadas = StrategistAgent._recuperar_de_resposta_cortada(limpo)
            if not recuperadas:
                raise
            return recuperadas, False, True
        propostas = dados.get("intervencoes")
        if not isinstance(propostas, list):
            raise ValueError("intervencoes ausente ou fora do formato de lista na resposta do modelo.")
        return [p for p in propostas if isinstance(p, dict)], json_direto, False

    @staticmethod
    def _recuperar_de_resposta_cortada(texto: str) -> list[dict[str, Any]]:
        """Lê, um a um, os objetos completos da lista ``intervencoes`` até o ponto do corte."""
        inicio = re.search(r'"intervencoes"\s*:\s*\[', texto)
        if not inicio:
            return []
        decoder = json.JSONDecoder()
        pos, objetos = inicio.end(), []
        while True:
            while pos < len(texto) and texto[pos] in " \t\r\n,":
                pos += 1
            if pos >= len(texto) or texto[pos] != "{":
                return objetos
            try:
                obj, pos = decoder.raw_decode(texto, pos)
            except json.JSONDecodeError:
                return objetos
            if isinstance(obj, dict):
                objetos.append(obj)

    @staticmethod
    def _conferir(
        propostas: list[dict[str, Any]],
        fontes: list[dict[str, Any]],
        ativadas: list[str],
    ) -> tuple[list[StrategyIntervention], list[dict[str, str]]]:
        """Aprova a intervenção curta, sem cópia, que cita trechos existentes da própria característica."""
        por_rotulo = {f["rotulo"]: f for f in fontes}
        janelas_dos_trechos = set().union(*(_janelas(f.get("trecho", "")) for f in fontes)) if fontes else set()
        aprovadas: list[StrategyIntervention] = []
        descartadas: list[dict[str, str]] = []
        por_caracteristica: dict[str, int] = {}
        for p in propostas:
            id_carac = str(p.get("id_caracteristica", "")).strip()
            texto = str(p.get("texto", "")).strip()
            citados = set(_RE_CITACAO.findall(texto))
            n_palavras = len(_RE_CITACAO.sub("", texto).split())
            motivo: Optional[str] = None
            if id_carac not in ativadas:
                motivo = "caracteristica_nao_ativada"
            elif n_palavras < 4:
                motivo = "texto_vazio"
            elif n_palavras > LIMITE_PALAVRAS:
                motivo = "texto_longo"
            elif not citados:
                motivo = "sem_citacao"
            elif any(r not in por_rotulo for r in citados):
                motivo = "citacao_inexistente"
            elif any(id_carac not in por_rotulo[r]["caracteristicas"] for r in citados):
                motivo = "citacao_de_outra_caracteristica"
            elif _janelas(texto) & janelas_dos_trechos:
                motivo = "copia_do_trecho"
            elif por_caracteristica.get(id_carac, 0) >= MAX_POR_CARACTERISTICA:
                motivo = "excede_limite_por_caracteristica"
            if motivo:
                descartadas.append({"id_caracteristica": id_carac, "texto": texto, "motivo": motivo})
                continue
            por_caracteristica[id_carac] = por_caracteristica.get(id_carac, 0) + 1
            aprovadas.append(
                StrategyIntervention(
                    id_caracteristica=id_carac,
                    texto=texto,
                    citacoes=_ordenar_rotulos(citados),
                    origem="modelo",
                )
            )
        return aprovadas, descartadas

    @staticmethod
    def _diretiva_de_reserva(
        buscas: list[dict[str, Any]],
        fontes: list[dict[str, Any]],
        nivel: int,
    ) -> list[StrategyIntervention]:
        """Ações do catálogo para o nível, seguidas dos trechos recuperados para cada característica."""
        intervencoes = []
        for busca in buscas:
            id_carac = busca["id_caracteristica"]
            acoes = (busca.get("diretriz_andaime") or {}).get("acoes_permitidas", [])
            rotulos = [f["rotulo"] for f in fontes if id_carac in f["caracteristicas"]]
            citacoes = "".join(f"[{r}]" for r in rotulos)
            texto = f"Ações do catálogo para o nível {nivel}: {'; '.join(acoes)}. Evidências recuperadas: {citacoes}"
            intervencoes.append(
                StrategyIntervention(id_caracteristica=id_carac, texto=texto, citacoes=rotulos, origem="catalogo")
            )
        return intervencoes

    @staticmethod
    def _renderizar(intervencoes: list[StrategyIntervention]) -> str:
        return "\n".join(f"Para {i.id_caracteristica}: {i.texto}" for i in intervencoes)


def get_strategist_agent(llm_client: Optional[HybridLLMClient] = None) -> StrategistAgent:
    """Factory padrão para obter o Agente Estrategista RAG."""
    return StrategistAgent(llm_client=llm_client)
