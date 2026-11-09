"""Agente Extrator Curricular (História 2.1.2 / Issue #17).

Responsável por analisar questões didáticas originais e identificar seus invariantes
curriculares inegociáveis (núcleo conceitual, vocabulário técnico intocável, verbo de comando
da BNCC e alertas anti-muleta), impedindo o empobrecimento cognitivo da avaliação.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Optional

from iris.core.llm_client import HybridLLMClient, get_llm_client, strip_thinking_tags
from iris.schemas.curriculum import CurriculumInvariants, ExtractionRequest

if TYPE_CHECKING:
    from iris.eval.benchmark import GoldenQuestion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_EXTRATOR = """Você é o Agente Extrator Curricular da plataforma Íris (Copiloto Pedagógico Baseado em Evidências).
Sua missão é atuar como autoridade em currículo escolar brasileiro (BNCC) e Desenho Universal para a Aprendizagem (DUA).

Ao analisar uma questão ou atividade didática, você DEVE extrair com precisão cirúrgica os INVARIANTES CURRICULARES:
1. conceitos_obrigatorios: lista dos termos nucleares e conceitos científicos inegociáveis. Se a questão avalia fotossíntese, termos como "fotossíntese", "oxigênio" e "glicose" são invariantes.
2. termos_tecnicos_intocaveis: termos próprios da matéria que NÃO podem ser simplificados ou substituídos por linguagem infantil/gírias.
3. verbo_comando_bncc: verbo taxonômico (ex.: 'identificar', 'calcular', 'analisar', 'inferir', 'comparar', 'diferenciar') que indica o nível de exigência cognitiva da questão.
4. operacao_cognitiva: descrição clara do raciocínio que o estudante DEVE realizar para solucionar a atividade.
5. habilidade_bncc_sugerida: código BNCC inferido (ex: 'EF06CI05', 'EF08MA03', 'EM13LP01') ou null se não identificável.
6. alerta_anti_muleta: instrução clara e imperativa para o Agente Adaptador proibindo que ele resolva a questão, dê dicas que entreguem a resposta ou suprima o esforço cognitivo do aluno.
7. justificativa_preservacao: fundamentação pedagógica sucinta da importância de manter essa trava.

Retorne EXCLUSIVAMENTE um objeto JSON válido no formato:
{
  "conceitos_obrigatorios": ["conceito 1", "conceito 2"],
  "termos_tecnicos_intocaveis": ["termo 1", "termo 2"],
  "verbo_comando_bncc": "verbo",
  "operacao_cognitiva": "descrição da operação cognitiva",
  "habilidade_bncc_sugerida": "EFxxYYzz",
  "alerta_anti_muleta": "O que NÃO pode ser entregue ou simplificado",
  "justificativa_preservacao": "Por que a trava é inegociável"
}
"""

FEW_SHOT_EXEMPLOS = """
Exemplo 1 (Ciências):
ENUNCIADO: "Explique como os cloroplastos utilizam a luz solar para produzir glicose e oxigênio na fotossíntese."
RESPOSTA:
{
  "conceitos_obrigatorios": ["fotossíntese", "cloroplastos", "glicose", "oxigênio"],
  "termos_tecnicos_intocaveis": ["cloroplastos", "energia solar", "glicose"],
  "verbo_comando_bncc": "explicar",
  "operacao_cognitiva": "explicar o processo biológico de transformação de energia luminosa em energia química",
  "habilidade_bncc_sugerida": "EF06CI05",
  "alerta_anti_muleta": "Não explique a função do cloroplasto nem descreva a reação química pelo aluno; limite a intervenção à organização visual do enunciado.",
  "justificativa_preservacao": "A habilidade exige que o próprio estudante articule a relação entre organela e síntese de nutrientes."
}

Exemplo 2 (Matemática):
ENUNCIADO: "Determine o valor da incógnita na equação 2x + 6 = 14."
RESPOSTA:
{
  "conceitos_obrigatorios": ["equação", "incógnita", "2x + 6 = 14"],
  "termos_tecnicos_intocaveis": ["2x + 6 = 14", "incógnita"],
  "verbo_comando_bncc": "determinar",
  "operacao_cognitiva": "resolver equação polinomial de 1º grau aplicando operações inversas para isolar a incógnita",
  "habilidade_bncc_sugerida": "EF07MA18",
  "alerta_anti_muleta": "Proibido antecipar a resposta x = 4 ou realizar os passos aritméticos (14 - 6 = 8); o aluno deve efetuar os cálculos.",
  "justificativa_preservacao": "A avaliação afere o domínio procedimental de resolução de equações."
}
"""

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

    def __init__(self, llm_client: Optional[HybridLLMClient] = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def extract(
        self,
        request: ExtractionRequest | str,
        contexto_apoio: Optional[str] = None,
        disciplina: Optional[str] = None,
        ano_escolar: Optional[str] = None,
        trava_manual_docente: Optional[list[str]] = None,
    ) -> CurriculumInvariants:
        """Extrai os invariantes curriculares inegociáveis do insumo pedagógico."""
        if isinstance(request, str):
            req = ExtractionRequest(
                enunciado=request,
                contexto_apoio=contexto_apoio,
                disciplina=disciplina,
                ano_escolar=ano_escolar,
                trava_manual_docente=trava_manual_docente,
            )
        else:
            req = request

        # Monta prompt contextualizado
        prompt = self._montar_prompt(req)

        # Invoca modelo de linguagem
        try:
            resposta_llm = self.llm_client.generate(prompt=prompt, temperature=0.0, max_tokens=1000)
            invariantes = self._parse_json_response(resposta_llm.text, req)
            return invariantes
        except Exception as e:
            logger.warning("Falha na chamada ou parsing do LLM para o Agente Extrator: %s. Aplicando extração determinística de salvaguarda.", e)
            return self._extracao_deterministica_fallback(req)

    def extract_from_golden_question(self, question: GoldenQuestion) -> CurriculumInvariants:
        """Atalho de extração para itens do Golden Benchmark oficial."""
        trava_lista = list(question.trava_curricular) if question.trava_curricular else None
        return self.extract(
            request=question.enunciado,
            disciplina=question.disciplina,
            ano_escolar=question.ano,
            trava_manual_docente=trava_lista,
        )

    def _montar_prompt(self, req: ExtractionRequest) -> str:
        partes = [
            SYSTEM_PROMPT_EXTRATOR,
            FEW_SHOT_EXEMPLOS,
            "--- AGORA ANALISE A SEGUINTE QUESTÃO ---",
        ]
        if req.disciplina:
            partes.append(f"DISCIPLINA: {req.disciplina}")
        if req.ano_escolar:
            partes.append(f"ANO/ETAPA: {req.ano_escolar}")
        if req.contexto_apoio:
            partes.append(f"TEXTO OU CONTEXTO DE APOIO: {req.contexto_apoio}")
        partes.append(f"ENUNCIADO DA QUESTÃO:\n{req.enunciado}")
        if req.trava_manual_docente:
            partes.append(
                f"TRAVAS CURRICULARES JÁ FORNECIDAS PELO PROFESSOR (DEVE INCORPORÁ-LAS): {req.trava_manual_docente}"
            )
        partes.append("\nRESPOSTA JSON:")
        return "\n\n".join(partes)

    def _parse_json_response(self, text: str, req: ExtractionRequest) -> CurriculumInvariants:
        limpo = strip_thinking_tags(text).strip()
        # Busca bloco delimitado por ```json ... ``` ou primeiro objeto JSON {...}
        match_code = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", limpo, flags=re.DOTALL)
        if match_code:
            json_str = match_code.group(1)
        else:
            match_brace = re.search(r"(\{.*\})", limpo, flags=re.DOTALL)
            json_str = match_brace.group(1) if match_brace else limpo

        dados = json.loads(json_str)

        # Se o professor já havia definido travas manuais, garante que estejam nos conceitos obrigatórios
        if req.trava_manual_docente:
            existentes = set(c.lower() for c in dados.get("conceitos_obrigatorios", []))
            for t in req.trava_manual_docente:
                if t.lower() not in existentes:
                    dados.setdefault("conceitos_obrigatorios", []).append(t)

        return CurriculumInvariants.model_validate(dados)

    def _extracao_deterministica_fallback(self, req: ExtractionRequest) -> CurriculumInvariants:
        """Gera invariantes determinísticos a partir de regex e regras léxicas em caso de falha de IA."""
        texto = req.enunciado
        palavras = re.findall(r"[a-zA-ZÀ-ÿ0-9_+\-=/²³]{3,}", texto)

        # Localiza verbo de comando BNCC
        verbo_encontrado = "identificar"
        for p in palavras:
            if p.lower() in VERBOS_BNCC_COMUNS:
                verbo_encontrado = p.lower()
                break

        # Conceitos obrigatórios a partir de travas manuais ou termos de destaque
        conceitos: list[str] = []
        if req.trava_manual_docente:
            conceitos.extend(req.trava_manual_docente)

        # Extrai equações ou expressões entre aspas/maiúsculas
        destaques = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\d+[a-zA-Z]?\s*[=+\-*/]\s*\d+)', texto)
        for g1, g2, g3 in destaques:
            val = (g1 or g2 or g3 or "").strip()
            if val and len(val) >= 2 and val not in conceitos:
                conceitos.append(val)

        if not conceitos:
            # Pega palavras substantivas mais longas
            stopwords = {"para", "como", "qual", "quais", "onde", "quando", "sobre", "texto", "abaixo", "leia", "responda"}
            candidatos = [p for p in palavras if p.lower() not in stopwords and len(p) >= 5]
            conceitos = candidatos[:3] if candidatos else ["conteudo_curricular"]

        termos_tecnicos = [c for c in conceitos if any(ch in c for ch in "=+-/*0123456789") or len(c) >= 7]

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
