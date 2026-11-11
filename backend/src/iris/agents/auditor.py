"""Agente Auditor (História 2.1.4 / Issue #19, Épico #15; RF-12, RNF-04, RNF-05).

Avalia a minuta de questão adaptada contra o material original e as Travas Curriculares:

  1. TRCC (determinística, `iris.eval.trcc`): conceitos-chave retidos / conceitos esperados;
  2. resolução indevida: sinais determinísticos (marca de gabarito nova, cálculo já resolvido,
     alternativas eliminadas até sobrar uma) + juiz LLM para pistas sutis;
  3. modificações intrusivas: o juiz LLM recebe só as características que o professor NÃO
     selecionou e aponta adaptações típicas delas;
  4. ciclo de auto-correção: se algo falhar, devolve o feedback ao Adaptador antes de exibir.

O juiz LLM só vê os TRECHOS ACRESCENTADOS/ALTERADOS (diff determinístico) e toda acusação precisa
citar literalmente um desses trechos; acusação sem citação é descartada. Minuta sem acréscimos nem
chama o juiz. (Medido com llama3.1:8b: sem isso ele acusava todas as características em toda minuta.)

Princípio: falhar fechado. Resposta inválida do juiz, trava vazia ou ciclo esgotado NUNCA
resultam em aprovação silenciosa; o ciclo esgotado pede revisão humana.

As travas podem ser uma lista de conceitos (str) ou os invariantes do Extrator (#17,
`CurriculumInvariants`): então `conceitos_obrigatorios` vira a trava, `alerta_anti_muleta` entra no
prompt do juiz e `termos_tecnicos_intocaveis` ausentes reprovam (sem tolerância de 5%).

O juiz é qualquer objeto com `generate(prompt, temperature, max_tokens)` cujo retorno tenha
`.text` (ex.: `iris.core.llm_client.HybridLLMClient`) ou seja uma string.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from iris.core.llm_client import strip_thinking_tags
from iris.eval.trcc import LIMIAR_PADRAO, ResultadoTRCC, avaliar_trcc, normalizar

MAX_TENTATIVAS_PADRAO = 3


class JuizLLM(Protocol):
    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500) -> Any: ...


@dataclass(frozen=True)
class Caracteristica:
    """Característica funcional do catálogo (id + descrição observável em sala)."""

    id: str
    descricao: str = ""


def caracteristicas_nao_selecionadas(
    selecionadas: Iterable[str], catalogos: Mapping[str, Any] | None = None
) -> list[Caracteristica]:
    """Características do catálogo que o professor NÃO escolheu (insumo da checagem de intrusão).

    `catalogos` segue o formato de `iris.schemas.catalog.load_all_catalogs()` (padrão): objetos
    com `.caracteristicas`, cada uma com `id_caracteristica`, `nome` e `descricao_observavel`.
    Id selecionado que não existe em nenhum catálogo é erro (KeyError), nunca ignorado: o
    professor acharia que a característica foi aplicada.
    """
    if catalogos is None:
        from iris.schemas.catalog import load_all_catalogs

        catalogos = load_all_catalogs()
    todas: dict[str, Caracteristica] = {}
    for cat in catalogos.values():
        for c in cat.caracteristicas:
            todas.setdefault(
                c.id_caracteristica,
                Caracteristica(c.id_caracteristica, f"{c.nome}. {c.descricao_observavel}".strip()),
            )
    sel = list(dict.fromkeys(selecionadas))
    desconhecidos = [i for i in sel if i not in todas]
    if desconhecidos:
        raise KeyError(f"Características selecionadas não encontradas no catálogo: {desconhecidos}")
    return [c for i, c in todas.items() if i not in set(sel)]


# Conceito que o Extrator grava quando o enunciado não oferece candidatos (não é literal do texto).
_CONCEITO_GENERICO = "conteudo_curricular"


def resolver_travas(travas: Any) -> tuple[list[str] | str | None, str | None, list[str]]:
    """(travas, alerta_anti_muleta, termos_intocaveis). Aceita lista/str/None ou invariantes do Extrator."""
    if hasattr(travas, "conceitos_obrigatorios"):
        conceitos = [c for c in travas.conceitos_obrigatorios if c != _CONCEITO_GENERICO]
        intoc = [t for t in (getattr(travas, "termos_tecnicos_intocaveis", None) or []) if t != _CONCEITO_GENERICO]
        return conceitos, getattr(travas, "alerta_anti_muleta", None) or None, intoc
    return travas, None, []


# ---------------------------------------------------------------- sinais determinísticos

_MARCAS_RESPOSTA = tuple(
    re.compile(p)
    for p in (
        r"\bgabarito\b",
        r"\b(resposta|alternativa|opcao) (correta|certa)\b",
        r"\ba (resposta|alternativa|opcao) (e|eh|certa e|correta e)\b",
        r"\b(correta|certa)\s*[:)\]]",
        r"[✔✅]",
        r"\(correta\)|\(certa\)",
    )
)
_CALCULO = re.compile(r"\d+(?:[.,]\d+)?[×x*+\-÷/]\d+(?:[.,]\d+)?=(?:r\$ ?)?\d")
_ALTERNATIVA = re.compile(r"(?m)^\s*\(?([A-Ea-e])[\).]\s+(\S.*?)\s*$")


def _contagem_marcas(texto: str) -> int:
    t = normalizar(texto)
    return sum(len(p.findall(t)) for p in _MARCAS_RESPOSTA)


def _contagem_calculos(texto: str) -> int:
    return len(_CALCULO.findall(normalizar(texto)))


def _alternativas(texto: str) -> dict[str, str]:
    """Letra -> conteúdo normalizado de cada alternativa ("A) R$ 300" -> {"A": "r$300"})."""
    return {m.group(1).upper(): normalizar(m.group(2)) for m in _ALTERNATIVA.finditer(texto)}


def _alternativas_mantidas(original: str, adaptada: str) -> int:
    """Quantas alternativas do original continuam na minuta, pelo conteúdo e não pela letra: a adaptação pode
    renumerar ("1." no lugar de "a)") ou pôr caixa de seleção sem eliminar nenhuma."""
    base = normalizar(adaptada)
    return sum(1 for conteudo in _alternativas(original).values() if conteudo and conteudo in base)


def sinais_resolucao_deterministicos(original: str, adaptada: str) -> list[str]:
    """Motivos objetivos de resolução indevida. "Assinale a alternativa correta" no enunciado
    original é normal; só conta marca nova, ausente do original."""
    motivos: list[str] = []
    if _contagem_marcas(adaptada) > _contagem_marcas(original):
        motivos.append("a minuta contém marca de gabarito/resposta correta que não existia no original")
    if _contagem_calculos(adaptada) > _contagem_calculos(original):
        motivos.append("a minuta traz cálculo já resolvido (ex.: 12 × 25 = 300) que não existia no original")
    n_orig, n_adap = len(_alternativas(original)), _alternativas_mantidas(original, adaptada)
    if n_orig >= 2 and n_adap <= 1:
        motivos.append(f"alternativas eliminadas até sobrar {n_adap} (original tinha {n_orig})")
    return motivos


def _unidades(texto: str) -> list[str]:
    out = []
    for linha in texto.splitlines():
        out += [x.strip() for x in re.split(r"(?<=[.!?;])\s+", linha.strip()) if x.strip()]
    return out


def trechos_novos(original: str, adaptada: str) -> list[str]:
    """Frases/linhas da minuta que não existem no original (acrescentadas ou alteradas)."""
    base = normalizar(original)
    novos: list[str] = []
    for u in _unidades(adaptada):
        if normalizar(u) not in base and u not in novos:
            novos.append(u)
    return novos


def _evidencia_valida(evidencia: str, base_normalizada: str) -> bool:
    e = normalizar(evidencia).strip(" \"'“”")
    return len(e) >= 6 and e in base_normalizada


# ---------------------------------------------------------------- juiz LLM

def montar_prompt_juiz(
    original: str,
    adaptada: str,
    nao_selecionadas: Sequence[Caracteristica],
    alerta_anti_muleta: str | None = None,
) -> str:
    novos = trechos_novos(original, adaptada)
    trechos = "\n".join(f"- {t}" for t in novos) or "- (nenhum)"
    bloco = ""
    if alerta_anti_muleta:
        bloco += f"\nALERTA ANTI-MULETA (o que NÃO pode ser entregue ao aluno): {alerta_anti_muleta}\n"
    if nao_selecionadas:
        linhas = "\n".join(f"- {c.id}: {c.descricao[:200]}".rstrip(": ") for c in nao_selecionadas)
        bloco += (
            "\nCARACTERÍSTICAS NÃO SELECIONADAS PELO PROFESSOR (a minuta NÃO deve conter adaptações "
            f"típicas delas):\n{linhas}\n"
        )
    return (
        "Você é um auditor pedagógico. Uma questão escolar foi ADAPTADA. Abaixo estão a QUESTÃO "
        "ORIGINAL e SOMENTE os trechos que a adaptação ACRESCENTOU OU ALTEROU. Julgue apenas esses trechos.\n\n"
        f"QUESTÃO ORIGINAL:\n{original}\n\nMINUTA ADAPTADA:\n{adaptada}\n\n"
        f"TRECHOS ACRESCENTADOS OU ALTERADOS:\n{trechos}\n{bloco}\n"
        "Responda SOMENTE com um JSON, sem texto extra, neste formato:\n"
        '{"resolveu_questao": true|false, "evidencia_resolucao": "<citação exata>", '
        '"modificacoes_intrusivas": [{"caracteristica": "<id>", "evidencia": "<citação exata>"}]}\n\n'
        "Regras:\n"
        "- resolveu_questao = true só se um trecho entrega a resposta, indica a alternativa correta, "
        "faz um cálculo ou dá o resultado que o aluno deveria encontrar. Reformular, dividir em etapas, "
        "numerar passos e destacar palavras NÃO é resolver.\n"
        "- modificacoes_intrusivas: acuse uma característica NÃO selecionada somente se um trecho acima "
        "aplica a adaptação típica dela, e CITE esse trecho exato em \"evidencia\". Não acuse uma "
        "característica só porque ela está na lista. Sem trecho para citar, use lista vazia [].\n"
        '- Exemplo sem problemas: {"resolveu_questao": false, "evidencia_resolucao": "", '
        '"modificacoes_intrusivas": []}'
    )


@dataclass(frozen=True)
class VereditoJuiz:
    valido: bool
    resolveu: bool = False
    evidencia_resolucao: str = ""
    intrusoes: tuple[tuple[str, str], ...] = ()  # (id, evidência)


def _texto(resp: Any) -> str:
    # Modelos de raciocínio (Qwen3) abrem com <think>...</think>; chaves dentro do raciocínio confundiriam o parser.
    return strip_thinking_tags(resp if isinstance(resp, str) else str(getattr(resp, "text", "")))


def parsear_veredito(texto: str, ids_validos: set[str]) -> VereditoJuiz:
    """Extrai o JSON do juiz (tolera cercas ```json e texto em volta). Inválido => valido=False."""
    m = re.search(r"\{.*\}", texto, flags=re.DOTALL)
    if not m:
        return VereditoJuiz(valido=False)
    try:
        d = json.loads(m.group(0))
        resolveu = d["resolveu_questao"]
        lista = d.get("modificacoes_intrusivas", [])
        if not isinstance(resolveu, bool) or not isinstance(lista, list):
            return VereditoJuiz(valido=False)
        intr = []
        for it in lista:
            cid = str(it["caracteristica"])
            if cid in ids_validos:  # ignora ids inventados pelo modelo
                intr.append((cid, str(it.get("evidencia", ""))))
    except (ValueError, KeyError, TypeError):
        return VereditoJuiz(valido=False)
    return VereditoJuiz(True, resolveu, str(d.get("evidencia_resolucao", "")), tuple(intr))


# ---------------------------------------------------------------- resultado

@dataclass(frozen=True)
class ResultadoAuditoria:
    trcc: ResultadoTRCC
    limiar: float
    resolucao_indevida: bool
    intrusoes: tuple[str, ...]
    juiz_valido: bool
    motivos: tuple[str, ...]
    intocaveis_ausentes: tuple[str, ...] = ()
    intrusao_bloqueia: bool = True  # False: intrusão vira aviso (em `intrusoes`/`motivos`), não reprova

    @property
    def aprovado(self) -> bool:
        return (
            self.trcc.aprovado(self.limiar)
            and not self.resolucao_indevida
            and not (self.intrusoes and self.intrusao_bloqueia)
            and not self.intocaveis_ausentes
            and self.juiz_valido
        )

    def feedback(self) -> str:
        """Instrução objetiva para o Adaptador refazer a minuta."""
        partes = []
        if self.trcc.ausentes:
            partes.append(
                "Reinclua os conceitos-chave ausentes, exatamente como no original: "
                + "; ".join(self.trcc.ausentes) + "."
            )
        if self.intocaveis_ausentes:
            partes.append("Mantenha intactos os termos técnicos: " + "; ".join(self.intocaveis_ausentes) + ".")
        if self.resolucao_indevida:
            partes.append("Remova qualquer resposta pronta, marca de gabarito ou pista que revele a resposta.")
        if self.intrusoes and self.intrusao_bloqueia:
            partes.append(
                "Desfaça as adaptações de características que o professor não selecionou: "
                + ", ".join(self.intrusoes) + "."
            )
        if not partes:
            partes.append("; ".join(self.motivos) or "Revisar a minuta.")
        return " ".join(partes)


@dataclass(frozen=True)
class RelatorioCiclo:
    aprovado: bool
    texto_final: str
    tentativas: tuple[ResultadoAuditoria, ...]

    @property
    def requer_revisao_humana(self) -> bool:
        return not self.aprovado


# ---------------------------------------------------------------- agente

class AgenteAuditor:
    def __init__(
        self,
        juiz: JuizLLM,
        limiar: float = LIMIAR_PADRAO,
        max_tokens: int = 900,
        intrusao_bloqueia: bool = True,
    ) -> None:
        """`intrusao_bloqueia=False` faz a intrusão apontada pelo juiz virar só aviso. Útil enquanto o
        juiz em uso não tiver precisão validada (veja `iris.eval.juiz_auditor`)."""
        self.juiz = juiz
        self.limiar = limiar
        self.max_tokens = max_tokens
        self.intrusao_bloqueia = intrusao_bloqueia

    def _consultar_juiz(
        self, original: str, adaptada: str, nao_sel: Sequence[Caracteristica], alerta: str | None = None
    ) -> VereditoJuiz:
        prompt = montar_prompt_juiz(original, adaptada, nao_sel, alerta)
        ids = {c.id for c in nao_sel}
        for tentativa in range(2):
            # 2ª tentativa varia a temperatura e dobra o limite: repetir o mesmo pedido a temperatura 0
            # devolveria a mesma resposta inválida (ex.: JSON truncado).
            resp = self.juiz.generate(
                prompt, temperature=0.0 if tentativa == 0 else 0.3, max_tokens=self.max_tokens * (tentativa + 1)
            )
            v = parsear_veredito(_texto(resp), ids)
            if v.valido:
                return v
        return VereditoJuiz(valido=False)

    def auditar(
        self,
        original: str,
        adaptada: str,
        travas: Any,
        nao_selecionadas: Sequence[Caracteristica] = (),
    ) -> ResultadoAuditoria:
        travas, alerta, intocaveis = resolver_travas(travas)
        trcc = avaliar_trcc(travas, adaptada)
        motivos: list[str] = []
        if trcc.trcc is None:
            motivos.append("questão sem Trava Curricular: TRCC não pode ser medida")
        elif not trcc.aprovado(self.limiar):
            motivos.append(f"TRCC {trcc.trcc:.0%} abaixo de {self.limiar:.0%}; ausentes: {list(trcc.ausentes)}")

        det = sinais_resolucao_deterministicos(original, adaptada)
        motivos += det
        faltam = tuple(avaliar_trcc(intocaveis, adaptada).ausentes) if intocaveis else ()
        if faltam:
            motivos.append(f"termos técnicos intocáveis ausentes: {list(faltam)}")
        novos = trechos_novos(original, adaptada)
        # Sem acréscimos/alterações não há o que julgar: o juiz nem é chamado.
        v = self._consultar_juiz(original, adaptada, nao_selecionadas, alerta) if novos else VereditoJuiz(True)
        base = normalizar(" ".join(novos))
        intr = [(cid, ev) for cid, ev in v.intrusoes if _evidencia_valida(ev, base)]
        resolveu = v.resolveu and _evidencia_valida(v.evidencia_resolucao, base)
        descartadas = (len(v.intrusoes) - len(intr)) + (1 if v.resolveu and not resolveu else 0)
        if not v.valido:
            motivos.append("resposta do juiz LLM inválida: auditoria inconclusiva (bloqueado)")
        if descartadas:
            motivos.append(f"juiz: {descartadas} acusação(ões) sem citação literal dos trechos novos, descartada(s)")
        if resolveu:
            motivos.append(f"juiz: resolução indevida. {v.evidencia_resolucao}".strip())
        motivos += [f"juiz: intrusão em {cid}. {ev}".strip() for cid, ev in intr]

        return ResultadoAuditoria(
            trcc=trcc,
            limiar=self.limiar,
            resolucao_indevida=bool(det) or resolveu,
            intrusoes=tuple(dict.fromkeys(cid for cid, _ in intr)),
            juiz_valido=v.valido,
            motivos=tuple(motivos),
            intocaveis_ausentes=faltam,
            intrusao_bloqueia=self.intrusao_bloqueia,
        )

    def executar_ciclo(
        self,
        original: str,
        travas: Any,
        adaptar: Callable[[str | None, str | None], str],
        nao_selecionadas: Sequence[Caracteristica] = (),
        max_tentativas: int = MAX_TENTATIVAS_PADRAO,
    ) -> RelatorioCiclo:
        """Ciclo de auto-correção. `adaptar(feedback, minuta_anterior)` gera a minuta; na
        1ª chamada ambos são None. Aprova assim que uma minuta passa; ao esgotar as tentativas,
        devolve a última minuta com `requer_revisao_humana=True` (nunca como aprovada)."""
        if max_tentativas < 1:
            raise ValueError("max_tentativas deve ser >= 1")
        historico: list[ResultadoAuditoria] = []
        minuta: str | None = None
        feedback: str | None = None
        for _ in range(max_tentativas):
            minuta = adaptar(feedback, minuta)
            r = self.auditar(original, minuta, travas, nao_selecionadas)
            historico.append(r)
            if r.aprovado:
                return RelatorioCiclo(True, minuta, tuple(historico))
            feedback = r.feedback()
        return RelatorioCiclo(False, minuta or "", tuple(historico))