"""Agente Adaptador Pedagógico (História 2.1.3 / Issue #18).

Recebe o enunciado original, a característica funcional, o nível de andaime, as travas do Agente
Extrator e, quando houver, a diretiva do Agente Estrategista RAG. Devolve a minuta adaptada com o
laudo de isolamento de escopo e a telemetria da chamada.

Regra de Isolamento de Escopo: toda saída do modelo passa por ``verificar_escopo`` antes de ser
devolvida. Se o laudo reprova, ou se o modelo falha, o agente entrega a saída de reserva, montada
por regras e sem modelo. A saída de reserva só existe para a característica de comandos múltiplos;
nas demais, sem modelo, o enunciado original é devolvido sem alteração.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Optional

from iris.core.llm_client import HybridLLMClient, LLMResponse, get_llm_client, strip_thinking_tags
from iris.eval.escopo import ID_COMANDOS_MULTIPLOS, localizar_comandos, verificar_escopo
from iris.schemas.adaptation import (
    LIMITE_LATENCIA_MS,
    AdaptationRequest,
    AdaptationResult,
    AdaptationTelemetry,
    ScopeReport,
)
from iris.schemas.catalog import get_characteristic_by_id
from iris.schemas.curriculum import CurriculumInvariants

if TYPE_CHECKING:
    from iris.eval.benchmark import GoldenQuestion

logger = logging.getLogger(__name__)

# Prompt de sistema estável (as diretrizes do nível vão no prompt do usuário) para reaproveitar o KV-cache
SYSTEM_PROMPT_ADAPTADOR = """Você é o Agente Adaptador Pedagógico da plataforma Íris (BNCC e DUA).
Reescreva a APRESENTAÇÃO de uma questão escolar para reduzir uma barreira funcional, sem alterar o que ela avalia.

REGRA DE ISOLAMENTO DE ESCOPO:
1. Aplique somente as AÇÕES PERMITIDAS do nível informado. Nada além delas.
2. Mantenha todas as palavras, números, expressões e termos técnicos do enunciado original, na mesma ordem.
3. Não troque palavras por sinônimos, não simplifique o vocabulário e não resuma.
4. Não acrescente dica, exemplo, explicação, fórmula ou resposta.
5. Não retire nem junte comandos: a quantidade de comandos avaliados é a mesma do original.
6. Os CONCEITOS OBRIGATÓRIOS e os TERMOS INTOCÁVEIS devem aparecer exatamente como no original.

Formato permitido: negrito com **, item numerado "1.", caixa de seleção "[ ]" e linha de resposta "____".

Retorne APENAS um JSON válido com os campos:
- texto_adaptado: a questão adaptada, com quebras de linha.
- justificativas: lista curta, uma frase por ação aplicada."""

PROVEDORES_SEM_MODELO = frozenset({"extractive", "mock", "offline"})

LEMBRETE_DE_CONFERENCIA = "Revise se você preencheu todos os passos."
LINHA_DE_RESPOSTA = "Resposta: " + "_" * 30

# Comandos que não pedem registro escrito: no nível 3 recebem caixa de seleção em vez de linha de resposta.
_VERBOS_SEM_REGISTRO = frozenset({"leia", "observe"})

_RE_CONECTIVO_SEQUENCIAL = re.compile(r"\b(?:em seguida|por fim|depois|a seguir)\s*,?\s*$", re.IGNORECASE)
_RE_E_FINAL = re.compile(r"\s+e\s*$", re.IGNORECASE)


def segmentar_comandos(linha: str) -> tuple[str, list[tuple[str, tuple[int, int]]]]:
    """Divide uma linha em segmentos, um por verbo de comando.

    Retorna o texto anterior ao primeiro comando e a lista de (segmento, posição do verbo dentro
    do segmento). A fronteira fica no verbo ou no conectivo sequencial que o antecede ("Em seguida,").
    O "e" e a vírgula que ligavam um comando ao seguinte são retirados; o restante fica intacto.
    """
    verbos = localizar_comandos(linha)
    if not verbos:
        return linha, []
    fronteiras: list[tuple[int, bool]] = []
    for inicio, _ in verbos:
        conectivo = _RE_CONECTIVO_SEQUENCIAL.search(linha[:inicio])
        fronteiras.append((conectivo.start(), True) if conectivo else (inicio, False))

    segmentos: list[tuple[str, tuple[int, int]]] = []
    for i, ((inicio, _), (v_ini, v_fim)) in enumerate(zip(fronteiras, verbos)):
        if i + 1 < len(fronteiras):
            fim, proximo_tem_conectivo = fronteiras[i + 1]
            trecho = linha[inicio:fim].rstrip()
            # O "e" só é redundante quando o que vem depois dele é o próprio verbo do item seguinte.
            if not proximo_tem_conectivo:
                trecho = _RE_E_FINAL.sub("", trecho)
            trecho = trecho.rstrip().removesuffix(",").rstrip()
        else:
            trecho = linha[inicio:].rstrip()
        segmentos.append((trecho, (v_ini - inicio, v_fim - inicio)))
    return linha[: fronteiras[0][0]].rstrip(), segmentos


def _destacar(segmento: str, verbo: tuple[int, int], maiuscula_inicial: bool = True) -> str:
    ini, fim = verbo
    texto = f"{segmento[:ini]}**{segmento[ini:fim]}**{segmento[fim:]}"
    if not maiuscula_inicial:
        return texto
    # Primeira letra do item em maiúscula (pode estar depois do "**" de abertura).
    pos = next((i for i, ch in enumerate(texto) if ch.isalpha()), None)
    return texto if pos is None else texto[:pos] + texto[pos].upper() + texto[pos + 1 :]


def destacar_comandos(enunciado: str) -> str:
    """Nível 1: negrito nos verbos de comando, sem nenhuma outra alteração."""
    partes: list[str] = []
    cursor = 0
    for ini, fim in localizar_comandos(enunciado):
        partes.append(f"{enunciado[cursor:ini]}**{enunciado[ini:fim]}**")
        cursor = fim
    partes.append(enunciado[cursor:])
    return "".join(partes)


def decompor_em_etapas(enunciado: str, com_registro: bool = False) -> str:
    """Níveis 2 e 3: um item por comando; linhas sem comando (texto de apoio) ficam como estão.

    ``com_registro=False`` gera a lista de verificação do nível 2 ("1. [ ] **Leia** ...").
    ``com_registro=True`` gera os blocos do nível 3 ("**Passo 1**", o comando e o espaço de resposta).
    """
    saida: list[str] = []
    n = 0
    for linha in enunciado.splitlines():
        prefixo, segmentos = segmentar_comandos(linha)
        if not segmentos:
            saida.append(linha)
            continue
        if prefixo.strip():
            saida.append(prefixo)
        for segmento, verbo in segmentos:
            n += 1
            if not com_registro:
                saida.append(f"{n}. [ ] {_destacar(segmento, verbo)}")
                continue
            sem_registro = segmento[verbo[0] : verbo[1]].lower() in _VERBOS_SEM_REGISTRO
            saida.append(f"**Passo {n}**")
            saida.append(("[ ] " if sem_registro else "") + _destacar(segmento, verbo))
            if not sem_registro:
                saida.append(LINHA_DE_RESPOSTA)
            saida.append("")
    if com_registro:
        saida.append(LEMBRETE_DE_CONFERENCIA)
    return "\n".join(saida)


def resumir_ciclo(telemetrias: Iterable[object], nivel: int) -> dict:
    """Soma latência e tokens das chamadas de um ciclo multiagentes e compara com o limite do RNF-07.

    Aceita a telemetria de qualquer agente que exponha ``total_ms``, ``prompt_tokens`` e
    ``completion_tokens`` (Extrator, Adaptador e os que vierem).
    """
    itens = list(telemetrias)
    total_ms = round(sum(float(getattr(t, "total_ms", 0.0)) for t in itens), 2)
    prompt_tokens = sum(int(getattr(t, "prompt_tokens", 0)) for t in itens)
    completion_tokens = sum(int(getattr(t, "completion_tokens", 0)) for t in itens)
    limite_ms = LIMITE_LATENCIA_MS[nivel]
    return {
        "chamadas": len(itens),
        "chamadas_com_fallback": sum(1 for t in itens if getattr(t, "used_fallback", False)),
        "total_ms": total_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "nivel": nivel,
        "limite_ms": limite_ms,
        "dentro_do_limite": total_ms <= limite_ms,
    }


class AdapterAgent:
    """Agente de IA que aplica o andaime do nível escolhido sem sair do escopo permitido."""

    def __init__(self, llm_client: Optional[HybridLLMClient] = None, max_tokens: int = 900) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.max_tokens = max_tokens

    def adapt(self, request: AdaptationRequest, tentativa: int = 1) -> AdaptationResult:
        """Adapta o enunciado e devolve minuta, laudo de escopo e telemetria."""
        trava = [*request.invariantes.conceitos_obrigatorios, *request.invariantes.termos_tecnicos_intocaveis]

        t0 = time.perf_counter()
        resposta_llm: Optional[LLMResponse] = None
        json_valido_direto = True
        motivo_fallback: Optional[str] = None
        texto: Optional[str] = None
        justificativas: list[str] = []
        escopo: Optional[ScopeReport] = None

        provider_configurado = getattr(self.llm_client, "provider_name", "custom")
        if provider_configurado in PROVEDORES_SEM_MODELO:
            motivo_fallback = "provedor_sem_modelo"
        else:
            try:
                resposta_llm = self._chamar_llm(self._montar_prompt_usuario(request))
                texto, justificativas, json_valido_direto = self._parse_json_response(resposta_llm.text)
                escopo = verificar_escopo(
                    request.enunciado, texto, request.id_caracteristica, request.nivel, trava
                )
                if not escopo.aprovado:
                    logger.warning(
                        "Saída do Agente Adaptador reprovada no isolamento de escopo (%s). "
                        "Aplicando a saída de reserva.",
                        "; ".join(escopo.violacoes),
                    )
                    motivo_fallback = "escopo_reprovado"
            except Exception as e:
                logger.warning(
                    "Falha na chamada ou parsing do LLM para o Agente Adaptador (%s). "
                    "Aplicando a saída de reserva.",
                    type(e).__name__,
                )
                motivo_fallback = f"falha_llm:{type(e).__name__}"
                json_valido_direto = False

        if motivo_fallback:
            texto, justificativas = self._saida_de_reserva(request)
            escopo = verificar_escopo(
                request.enunciado, texto, request.id_caracteristica, request.nivel, trava
            )
            if not escopo.aprovado:
                # A reserva também passa pelo laudo: se reprovar, o original é o único texto garantido.
                texto = request.enunciado
                justificativas = ["Nenhuma adaptação pôde ser garantida; o enunciado original foi mantido."]
                escopo = verificar_escopo(
                    request.enunciado, texto, request.id_caracteristica, request.nivel, trava
                )

        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        usage = resposta_llm.raw_usage if resposta_llm else {}
        load_ms = float(usage.get("load_ms") or 0.0)
        prompt_tokens = resposta_llm.prompt_tokens if resposta_llm else 0
        completion_tokens = resposta_llm.completion_tokens if resposta_llm else 0
        limite_ms = LIMITE_LATENCIA_MS[request.nivel]

        telemetria = AdaptationTelemetry(
            question_id=request.question_id,
            id_caracteristica=request.id_caracteristica,
            nivel=request.nivel,
            tentativa=tentativa,
            tamanho_enunciado_chars=len(request.enunciado),
            provider=resposta_llm.provider if resposta_llm else str(provider_configurado),
            model=resposta_llm.model if resposta_llm else "deterministic-fallback",
            used_fallback=motivo_fallback is not None,
            motivo_fallback=motivo_fallback,
            json_valido_direto=json_valido_direto and resposta_llm is not None,
            total_ms=total_ms,
            load_ms=load_ms,
            prompt_eval_ms=float(usage.get("prompt_eval_ms") or 0.0),
            eval_ms=float(usage.get("eval_ms") or 0.0),
            inference_ms=float(
                usage.get("inference_ms")
                or (round(max(0.0, total_ms - load_ms), 2) if resposta_llm else total_ms)
            ),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            tokens_per_sec=float(usage.get("tokens_per_sec") or 0.0),
            limite_ms=limite_ms,
            dentro_do_limite=total_ms <= limite_ms,
            escopo_aprovado=escopo.aprovado,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        return AdaptationResult(
            texto_adaptado=texto,
            justificativas=justificativas,
            adaptacao_aplicada=texto.strip() != request.enunciado.strip(),
            escopo=escopo,
            telemetry=telemetria,
        )

    def _chamar_llm(self, prompt_usuario: str) -> LLMResponse:
        sig = inspect.signature(self.llm_client.generate)
        params = sig.parameters
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if accepts_kwargs or ("system_prompt" in params and "json_mode" in params):
            return self.llm_client.generate(
                prompt=prompt_usuario,
                temperature=0.0,
                max_tokens=self.max_tokens,
                system_prompt=SYSTEM_PROMPT_ADAPTADOR,
                json_mode=True,
            )
        prompt_legado = f"{SYSTEM_PROMPT_ADAPTADOR}\n\n{prompt_usuario}"
        return self.llm_client.generate(prompt=prompt_legado, temperature=0.0, max_tokens=self.max_tokens)

    def _montar_prompt_usuario(self, req: AdaptationRequest) -> str:
        caracteristica = get_characteristic_by_id(req.id_caracteristica)
        diretriz = caracteristica.diretrizes_andaime[f"nivel_{req.nivel}"]
        inv = req.invariantes
        partes = [
            f"CARACTERÍSTICA FUNCIONAL: {req.id_caracteristica}",
            f"NÍVEL {req.nivel}: {diretriz.rotulo}",
            f"OBJETIVO DO ANDAIME: {diretriz.objetivo_andaime}",
            "AÇÕES PERMITIDAS:\n" + "\n".join(f"- {a}" for a in diretriz.acoes_permitidas),
            "RESTRIÇÕES DE ESCOPO:\n" + "\n".join(f"- {r}" for r in diretriz.restricoes_escopo),
            f"CONCEITOS OBRIGATÓRIOS: {inv.conceitos_obrigatorios}",
            f"TERMOS INTOCÁVEIS: {inv.termos_tecnicos_intocaveis}",
        ]
        if inv.alerta_anti_muleta:
            partes.append(f"ALERTA ANTI-MULETA: {inv.alerta_anti_muleta}")
        if req.diretiva_psicopedagogica:
            partes.append(f"DIRETIVA PSICOPEDAGÓGICA:\n{req.diretiva_psicopedagogica}")
        partes.append(f"ENUNCIADO ORIGINAL:\n{req.enunciado}")
        return "\n".join(partes)

    @staticmethod
    def _parse_json_response(text: str) -> tuple[str, list[str], bool]:
        limpo = strip_thinking_tags(text).strip()
        json_direto = limpo.startswith("{") and limpo.endswith("}")
        match_code = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", limpo, flags=re.DOTALL)
        if match_code:
            json_str = match_code.group(1)
            json_direto = False
        else:
            match_brace = re.search(r"(\{.*\})", limpo, flags=re.DOTALL)
            json_str = match_brace.group(1) if match_brace else limpo

        dados = json.loads(json_str)
        texto = dados.get("texto_adaptado")
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("texto_adaptado ausente ou vazio na resposta do modelo.")
        justificativas = dados.get("justificativas") or []
        if isinstance(justificativas, str):
            justificativas = [justificativas]
        return texto.strip(), [str(j).strip() for j in justificativas if str(j).strip()], json_direto

    @staticmethod
    def _saida_de_reserva(req: AdaptationRequest) -> tuple[str, list[str]]:
        """Adaptação por regras, sem modelo. Só cobre a característica de comandos múltiplos."""
        enunciado = req.enunciado
        if req.id_caracteristica != ID_COMANDOS_MULTIPLOS:
            return enunciado, [
                "Sem modelo disponível, esta característica não tem adaptação por regras; "
                "o enunciado original foi mantido."
            ]
        n_comandos = len(localizar_comandos(enunciado))
        if n_comandos == 0:
            return enunciado, ["Nenhum verbo de comando reconhecido; o enunciado original foi mantido."]
        if req.nivel == 1:
            return destacar_comandos(enunciado), [
                f"Negrito aplicado a {n_comandos} verbo(s) de comando; nenhuma palavra alterada."
            ]
        if n_comandos < 2:
            return enunciado, ["O enunciado tem um único comando; não há etapas a separar."]
        if req.nivel == 2:
            return decompor_em_etapas(enunciado), [
                f"{n_comandos} comandos separados em lista de verificação numerada, na ordem original.",
                "Verbo de comando destacado em negrito no início de cada etapa.",
            ]
        return decompor_em_etapas(enunciado, com_registro=True), [
            f"{n_comandos} comandos separados em passos, cada um com espaço de registro próprio.",
            "Lembrete de conferência acrescentado ao final.",
        ]


def get_adapter_agent(llm_client: Optional[HybridLLMClient] = None) -> AdapterAgent:
    """Factory padrão para obter o Agente Adaptador Pedagógico."""
    return AdapterAgent(llm_client=llm_client)


def adaptador_benchmark(questao: GoldenQuestion) -> dict:
    """Adaptador no formato de ``iris.eval.executar``: Extrator (sem a trava do gabarito) e Adaptador.

    Característica e nível vêm de ``IRIS_ADAPTADOR_CARACTERISTICA`` e ``IRIS_ADAPTADOR_NIVEL``
    (padrão: comandos múltiplos, nível 2).
    """
    from iris.agents.curriculum_extractor import get_curriculum_extractor

    nivel = int(os.environ.get("IRIS_ADAPTADOR_NIVEL", "2"))
    extracao = get_curriculum_extractor().extract_golden_with_telemetry(questao)
    resultado = get_adapter_agent().adapt(
        AdaptationRequest(
            enunciado=questao.enunciado,
            id_caracteristica=os.environ.get("IRIS_ADAPTADOR_CARACTERISTICA", ID_COMANDOS_MULTIPLOS),
            nivel=nivel,
            invariantes=extracao.invariants,
            question_id=questao.id,
        )
    )
    return {
        "adaptado": resultado.texto_adaptado,
        "contextos": [],
        "escopo_aprovado": resultado.escopo.aprovado,
        "used_fallback": resultado.telemetry.used_fallback,
        "ciclo": resumir_ciclo([extracao.telemetry, resultado.telemetry], nivel),
    }
