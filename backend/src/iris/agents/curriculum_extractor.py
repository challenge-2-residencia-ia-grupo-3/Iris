"""Agente Extrator Curricular (História 2.1.2 / Issue #17).

Responsável por analisar questões didáticas originais e identificar seus invariantes
curriculares inegociáveis (núcleo conceitual, vocabulário técnico intocável, verbo de comando
da BNCC e alertas anti-muleta), impedindo o empobrecimento cognitivo da avaliação.
"""
from __future__ import annotations

import inspect
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Optional

from iris.core.llm_client import HybridLLMClient, LLMResponse, get_llm_client, strip_thinking_tags
from iris.eval.trcc import avaliar_trcc
from iris.schemas.curriculum import (
    IMPERATIVO_PARA_INFINITIVO,
    CurriculumInvariants,
    ExtractionRequest,
    ExtractionResult,
    ExtractionTelemetry,
    classificar_faixa_etaria,
)

if TYPE_CHECKING:
    from iris.eval.benchmark import GoldenQuestion

logger = logging.getLogger(__name__)

# Prompt de sistema enxuto e estável para maximizar reaproveitamento de KV-cache no Ollama
SYSTEM_PROMPT_EXTRATOR = """Você é o Agente Extrator Curricular da plataforma Íris (BNCC e DUA).
Extraia os INVARIANTES CURRICULARES de uma questão escolar em JSON estrito.
REGRA CRÍTICA PARA TRCC: em "conceitos_obrigatorios", liste TERMOS LITERAIS exatamente como aparecem no enunciado (incluindo nomes próprios, dados numéricos, equações, elementos da frase analisada e termos-chave com o mesmo plural/flexão do texto original). NUNCA use rótulos genéricos ausentes do texto (como "personagem" ou "ação").

Campos JSON:
- conceitos_obrigatorios: termos literais do enunciado essenciais para preservar a questão.
- termos_tecnicos_intocaveis: vocabulário disciplinar ou dados que NÃO podem ser trocados.
- verbo_comando_bncc: verbo principal no infinitivo (ex: calcular, explicar, identificar, circular, ler).
- operacao_cognitiva: 1 frase curta com o raciocínio exigido do aluno.
- habilidade_bncc_sugerida: código BNCC (ex: EF06CI05, EF07MA18) ou null.
- alerta_anti_muleta: 1 frase proibindo entregar a resposta ou resolver pelo aluno.
- justificativa_preservacao: 1 frase curta justificando a trava.

Ex1 (Ciências): "Explique como os cloroplastos utilizam a luz solar para produzir glicose e oxigênio na fotossíntese."
-> {"conceitos_obrigatorios":["fotossíntese","cloroplastos","luz solar","glicose","oxigênio"],"termos_tecnicos_intocaveis":["cloroplastos","glicose"],"verbo_comando_bncc":"explicar","operacao_cognitiva":"explicar a conversão de energia solar em glicose","habilidade_bncc_sugerida":"EF06CI05","alerta_anti_muleta":"Não explique a função do cloroplasto nem dê a reação pronta.","justificativa_preservacao":"Exige articulação causal."}

Ex2 (Matemática): "Determine o valor da incógnita na equação 2x + 6 = 14."
-> {"conceitos_obrigatorios":["equação","incógnita","2x + 6 = 14"],"termos_tecnicos_intocaveis":["2x + 6 = 14","incógnita"],"verbo_comando_bncc":"determinar","operacao_cognitiva":"isolar a incógnita aplicando operações inversas","habilidade_bncc_sugerida":"EF07MA18","alerta_anti_muleta":"Proibido antecipar x = 4 ou resolver 14 - 6 = 8.","justificativa_preservacao":"Avalia resolução algébrica."}

Ex3 (Português): "Identifique o sujeito: Maria e João foram ao mercado."
-> {"conceitos_obrigatorios":["sujeito","Maria","João","mercado"],"termos_tecnicos_intocaveis":["sujeito","Maria","João"],"verbo_comando_bncc":"identificar","operacao_cognitiva":"reconhecer o sujeito da oração dada","habilidade_bncc_sugerida":"EF06LP06","alerta_anti_muleta":"Não aponte quem é o sujeito da frase.","justificativa_preservacao":"Preserva os elementos literais avaliados."}

Retorne APENAS o JSON válido."""

# Conceito gravado pela salvaguarda quando o enunciado não oferece nenhum candidato
CONCEITO_GENERICO = "conteudo_curricular"

VERBOS_BNCC_COMUNS = (
    "analisar", "analise", "avalie", "avaliar", "calcular", "calcule",
    "classificar", "classifique", "comparar", "compare", "concluir", "conclua",
    "deduzir", "deduza", "demonstrar", "demonstre", "descrever", "descreva",
    "determinar", "determine", "diferenciar", "diferencie", "distinguir", "distinga",
    "esboçar", "esboce", "escrever", "escreva", "estimar", "estime", "examinar", "examine",
    "explicar", "explique", "identificar", "identifique", "ilustrar", "ilustre",
    "indicar", "indique", "inferir", "infira", "interpretar", "interprete",
    "justificar", "justifique", "localizar", "localize", "medir", "meça",
    "nomear", "nomeie", "ordenar", "ordene", "organizar", "organize",
    "reconhecer", "reconheça", "relacionar", "relacione", "representar", "represente",
    "resolver", "resolva", "responder", "responda", "selecionar", "selecione",
    "sintetizar", "sintetize", "verificar", "verifique",
)


class CurriculumExtractorAgent:
    """Agente de IA especializado na identificação e blindagem de invariantes curriculares."""

    def __init__(self, llm_client: Optional[HybridLLMClient] = None, max_tokens: int = 500) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.max_tokens = max_tokens

    def extract(
        self,
        request: ExtractionRequest | str,
        contexto_apoio: Optional[str] = None,
        disciplina: Optional[str] = None,
        ano_escolar: Optional[str] = None,
        trava_manual_docente: Optional[list[str]] = None,
    ) -> CurriculumInvariants:
        """Extrai os invariantes curriculares inegociáveis do insumo pedagógico."""
        return self.extract_with_telemetry(
            request=request,
            contexto_apoio=contexto_apoio,
            disciplina=disciplina,
            ano_escolar=ano_escolar,
            trava_manual_docente=trava_manual_docente,
        ).invariants

    def extract_with_telemetry(
        self,
        request: ExtractionRequest | str,
        contexto_apoio: Optional[str] = None,
        disciplina: Optional[str] = None,
        ano_escolar: Optional[str] = None,
        trava_manual_docente: Optional[list[str]] = None,
        question_id: Optional[str] = None,
        tema: Optional[str] = None,
        comando_conjugado: Optional[bool] = None,
        trava_referencia: Optional[Iterable[str]] = None,
    ) -> ExtractionResult:
        """Extrai invariantes curriculares retornando métricas operacionais de execução."""
        req = self._normalizar_request(
            request,
            contexto_apoio=contexto_apoio,
            disciplina=disciplina,
            ano_escolar=ano_escolar,
            trava_manual_docente=trava_manual_docente,
        )
        prompt_usuario = self._montar_prompt_usuario(req)

        t0 = time.perf_counter()
        used_fallback = False
        json_valido_direto = True
        resposta_llm: Optional[LLMResponse] = None

        provider_configurado = getattr(self.llm_client, "provider_name", "custom")
        if provider_configurado in {"extractive", "mock", "offline"}:
            used_fallback = True
            json_valido_direto = False
            invariantes = self._extracao_deterministica_fallback(req)
        else:
            try:
                resposta_llm = self._chamar_llm(prompt_usuario)
                invariantes, json_valido_direto = self._parse_json_response(resposta_llm.text, req)
            except Exception as e:
                logger.warning(
                    "Falha na chamada ou parsing do LLM para o Agente Extrator (%s). "
                    "Aplicando extração determinística de salvaguarda.",
                    type(e).__name__,
                )
                used_fallback = True
                json_valido_direto = False
                invariantes = self._extracao_deterministica_fallback(req)

        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        usage = resposta_llm.raw_usage if resposta_llm else {}
        load_ms = float(usage.get("load_ms") or 0.0)
        prompt_eval_ms = float(usage.get("prompt_eval_ms") or 0.0)
        eval_ms = float(usage.get("eval_ms") or 0.0)
        inference_ms = float(
            usage.get("inference_ms")
            or (round(max(0.0, total_ms - load_ms), 2) if resposta_llm else total_ms)
        )
        tokens_per_sec = float(usage.get("tokens_per_sec") or 0.0)

        trava_recall: Optional[float] = None
        if trava_referencia:
            texto_extraido = " ".join(
                invariantes.conceitos_obrigatorios + invariantes.termos_tecnicos_intocaveis
            )
            trava_recall = avaliar_trcc(trava_referencia, texto_extraido).trcc

        telemetria = ExtractionTelemetry(
            question_id=question_id,
            disciplina=(req.disciplina or "Não informada").strip(),
            ano_escolar=(req.ano_escolar or "Não informado").strip(),
            faixa_etaria=classificar_faixa_etaria(req.ano_escolar),
            tema=(tema or "Não informado").strip(),
            comando_conjugado=comando_conjugado,
            tamanho_enunciado_chars=len(req.enunciado),
            provider=resposta_llm.provider if resposta_llm else str(provider_configurado),
            model=resposta_llm.model if resposta_llm else "deterministic-fallback",
            used_fallback=used_fallback,
            json_valido_direto=json_valido_direto,
            total_ms=total_ms,
            load_ms=load_ms,
            prompt_eval_ms=prompt_eval_ms,
            eval_ms=eval_ms,
            inference_ms=inference_ms,
            prompt_tokens=resposta_llm.prompt_tokens if resposta_llm else 0,
            completion_tokens=resposta_llm.completion_tokens if resposta_llm else 0,
            tokens_per_sec=tokens_per_sec,
            trava_recall=trava_recall,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        return ExtractionResult(invariants=invariantes, telemetry=telemetria)

    def extract_from_golden_question(
        self, question: GoldenQuestion, include_trava_hint: bool = True
    ) -> CurriculumInvariants:
        """Atalho de extração para itens do Golden Benchmark oficial."""
        return self.extract_golden_with_telemetry(
            question, include_trava_hint=include_trava_hint
        ).invariants

    def extract_golden_with_telemetry(
        self, question: GoldenQuestion, include_trava_hint: bool = False
    ) -> ExtractionResult:
        """Extrai invariantes e telemetria para uma GoldenQuestion (padrão Zero-Hint para eval)."""
        trava_lista = list(question.trava_curricular) if (include_trava_hint and question.trava_curricular) else None
        return self.extract_with_telemetry(
            request=question.enunciado,
            disciplina=question.disciplina,
            ano_escolar=question.ano,
            trava_manual_docente=trava_lista,
            question_id=question.id,
            tema=question.tema,
            comando_conjugado=question.comando_conjugado_esperado,
            trava_referencia=question.trava_curricular,
        )

    @staticmethod
    def _normalizar_request(
        request: ExtractionRequest | str,
        *,
        contexto_apoio: Optional[str],
        disciplina: Optional[str],
        ano_escolar: Optional[str],
        trava_manual_docente: Optional[list[str]],
    ) -> ExtractionRequest:
        if isinstance(request, str):
            return ExtractionRequest(
                enunciado=request,
                contexto_apoio=contexto_apoio,
                disciplina=disciplina,
                ano_escolar=ano_escolar,
                trava_manual_docente=trava_manual_docente,
            )
        return request

    def _chamar_llm(self, prompt_usuario: str) -> LLMResponse:
        sig = inspect.signature(self.llm_client.generate)
        params = sig.parameters
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if accepts_kwargs or ("system_prompt" in params and "json_mode" in params):
            return self.llm_client.generate(
                prompt=prompt_usuario,
                temperature=0.0,
                max_tokens=self.max_tokens,
                system_prompt=SYSTEM_PROMPT_EXTRATOR,
                json_mode=True,
            )
        prompt_legado = f"{SYSTEM_PROMPT_EXTRATOR}\n\n{prompt_usuario}"
        return self.llm_client.generate(prompt=prompt_legado, temperature=0.0, max_tokens=self.max_tokens)

    def _montar_prompt_usuario(self, req: ExtractionRequest) -> str:
        partes: list[str] = []
        if req.disciplina:
            partes.append(f"DISCIPLINA: {req.disciplina}")
        if req.ano_escolar:
            partes.append(f"ANO/ETAPA: {req.ano_escolar}")
        if req.contexto_apoio:
            partes.append(f"CONTEXTO DE APOIO: {req.contexto_apoio}")
        partes.append(f"ENUNCIADO:\n{req.enunciado}")
        if req.trava_manual_docente:
            partes.append(
                f"TRAVAS DO PROFESSOR (INCLUIR EM conceitos_obrigatorios): {req.trava_manual_docente}"
            )
        return "\n".join(partes)

    def _parse_json_response(self, text: str, req: ExtractionRequest) -> tuple[CurriculumInvariants, bool]:
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
            # Mais de um objeto na resposta: aproveita o primeiro objeto JSON completo
            inicio = limpo.find("{")
            if inicio < 0:
                raise
            dados, _ = json.JSONDecoder().raw_decode(limpo[inicio:])
            json_direto = False

        # Se o professor já havia definido travas manuais, garante que estejam nos conceitos obrigatórios
        if req.trava_manual_docente:
            conceitos = dados.get("conceitos_obrigatorios")
            if isinstance(conceitos, str):  # o contrato aceita texto separado por ";", "," ou quebra de linha
                conceitos = re.split(r"[;\n,]", conceitos)
            elif not isinstance(conceitos, list):
                conceitos = []
            existentes = {str(c).strip().lower() for c in conceitos}
            for t in req.trava_manual_docente:
                if t.lower() not in existentes:
                    conceitos.append(t)
            dados["conceitos_obrigatorios"] = conceitos

        return CurriculumInvariants.model_validate(dados), json_direto

    def _extracao_deterministica_fallback(self, req: ExtractionRequest) -> CurriculumInvariants:
        """Gera invariantes determinísticos a partir de regex e regras léxicas em caso de falha de IA."""
        texto = req.enunciado
        palavras = re.findall(r"[a-zA-ZÀ-ÿ0-9_+\-=/²³]{3,}", texto)

        # Localiza verbo de comando BNCC
        verbo_encontrado = "identificar"
        for p in palavras:
            if p.lower() in VERBOS_BNCC_COMUNS:
                # Mesma forma (infinitivo) que o contrato grava em `verbo_comando_bncc`
                verbo_encontrado = IMPERATIVO_PARA_INFINITIVO.get(p.lower(), p.lower())
                break

        # Conceitos do enunciado: equações ou expressões entre aspas
        do_enunciado: list[str] = []
        destaques = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\d+[a-zA-Z]?\s*[=+\-*/]\s*\d+)', texto)
        for g1, g2, g3 in destaques:
            val = (g1 or g2 or g3 or "").strip()
            if val and len(val) >= 2 and val not in do_enunciado:
                do_enunciado.append(val)

        if not do_enunciado:
            # Pega palavras substantivas mais longas
            stopwords = {"para", "como", "qual", "quais", "onde", "quando", "sobre", "texto", "abaixo", "leia", "responda"}
            # O verbo de comando já vai em `verbo_comando_bncc`; não é conceito do enunciado
            candidatos = [
                p for p in palavras
                if p.lower() not in stopwords and p.lower() not in VERBOS_BNCC_COMUNS and len(p) >= 5
            ]
            do_enunciado = candidatos[:3]

        # As travas manuais se somam aos conceitos do enunciado, como no caminho com LLM
        conceitos: list[str] = list(req.trava_manual_docente or [])
        existentes = {c.lower() for c in conceitos}
        for c in do_enunciado:
            if c.lower() not in existentes:
                existentes.add(c.lower())
                conceitos.append(c)

        termos_tecnicos = [c for c in conceitos if any(ch in c for ch in "=+-/*0123456789") or len(c) >= 7]
        if not conceitos:
            # O contrato exige ao menos um conceito; o marcador genérico não é termo técnico
            conceitos = [CONCEITO_GENERICO]

        return CurriculumInvariants(
            conceitos_obrigatorios=conceitos,
            termos_tecnicos_intocaveis=termos_tecnicos,
            verbo_comando_bncc=verbo_encontrado,
            operacao_cognitiva=f"Executar operação cognitiva orientada ao comando '{verbo_encontrado}' sobre o conteúdo pedagógico.",
            habilidade_bncc_sugerida=None,
            alerta_anti_muleta=f"Proibido fornecer a resposta pronta ou resolver o comando '{verbo_encontrado}' pelo estudante.",
            justificativa_preservacao="Garantia de retenção curricular determinística e prevenção de empobrecimento cognitivo.",
        )


def get_curriculum_extractor(llm_client: Optional[HybridLLMClient] = None) -> CurriculumExtractorAgent:
    """Factory padrão para obter o Agente Extrator Curricular."""
    return CurriculumExtractorAgent(llm_client=llm_client)
