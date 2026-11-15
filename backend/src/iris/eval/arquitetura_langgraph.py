"""Arquitetura dos agentes do Íris escrita como grafo do LangGraph, para a aba "Arquitetura" do playground.

Analogia: o pipeline de hoje é uma receita lida de cima para baixo. O LangGraph é um fluxograma que o
computador executa: cada caixa (nó) faz um passo, as setas (arestas) dizem para onde ir e uma ficha (o
"estado") passa de caixa em caixa. Algumas setas têm condição (a volta do Auditor ao Adaptador) e uma caixa
pode parar e esperar uma pessoa (a revisão da professora).

O que este módulo faz:
- monta o grafo com um nó por etapa; cada nó chama a função REAL do grupo (filtro de dado pessoal,
  decomposição, Extrator, Estrategista, Adaptador, Auditor);
- roda quatro cenários sobre um material sintético, com um provedor determinístico (sem rede e sem modelo);
- devolve o desenho do grafo (nós, setas e posições) e o caminho que cada cenário percorreu.

O que ele NÃO mede: qualidade de modelo. O provedor "eco" devolve o andaime por regras do próprio grupo; o
que se exercita aqui é o fluxo (laço, limite de voltas, pausa, retomada), não o texto adaptado.

`langgraph` é dependência opcional: sem ela, `obter_arquitetura()` devolve `disponivel: False` e o comando
para instalar, e nada mais no backend é afetado.
"""
from __future__ import annotations

import json
import operator
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Annotated, Any, TypedDict

# Limite de voltas do Auditor ao Adaptador: o grupo decidiu max_retries = 2 (docs/arquitetura.md, ADR-06).
LIMITE_VOLTAS = 2
CARACTERISTICA_PADRAO = "sobrecarga_memoria_trabalho_comandos_multiplos"
NIVEL_PADRAO = 2
MAX_QUESTOES = 3
NOME_PLANTADO = "Fulano Ficticio"

# Material sintético: cabeçalho com um nome inventado e duas questões com mais de um comando.
MATERIAL_SINTETICO = (
    "Atividade de Ciências - 6º ano B\n"
    f"Aluno: {NOME_PLANTADO}\n\n"
    "Questão 1: Leia o texto sobre o ciclo da água, identifique suas etapas principais e explique o papel "
    "da evaporação.\n\n"
    "Questão 2: Observe a tabela de temperaturas, calcule a média da semana e justifique por que a "
    "quinta-feira foi o dia mais quente.\n"
)

try:  # dependência opcional
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.runtime import Runtime
    from langgraph.types import Command, interrupt

    LANGGRAPH_DISPONIVEL = True
    ERRO_IMPORTACAO: str | None = None
except ImportError as exc:  # pragma: no cover - exercitado por teste com o módulo escondido
    LANGGRAPH_DISPONIVEL = False
    ERRO_IMPORTACAO = str(exc)


# ---------------------------------------------------------------- o estado (a "ficha" que passa entre os nós)
class EstadoIris(TypedDict, total=False):
    """Estado do grafo. Regra: o texto bruto do material nunca entra aqui; só o texto já filtrado.

    O texto bruto fica no Contexto (abaixo), que o LangGraph entrega aos nós mas não salva a cada passo.
    """

    material_id: str
    n_caracteres: int
    texto_sanitizado: str
    n_pii_removidos: int
    questoes: list[dict]
    caracteristica: str
    nivel: int
    n_caracteristicas_bloqueadas: int
    indice_questao: int
    questao_id: str | None
    enunciado: str
    invariantes: dict
    chunk_ids: list[str]
    diretiva: str
    estrategista_reserva: str | None
    tentativa: int
    minuta: str
    minuta_anterior: str | None
    feedback_auditor: str | None
    auditoria: dict
    voltas_auditor: int
    rota: str
    texto_proposto: str
    alerta_professora: str | None
    decisao_professora: str | None
    texto_final: str
    resultados: Annotated[list[dict], operator.add]
    caminho: Annotated[list[list], operator.add]
    barradas_pelo_adaptador: Annotated[list[dict], operator.add]


@dataclass
class Contexto:
    """O que os nós recebem mas o grafo NÃO salva: texto bruto, clientes e o resultado da busca.

    É a mesa de trabalho: o que está nela some quando a requisição termina. O estado é a ficha que fica
    arquivada a cada passo; por isso o texto com dado pessoal fica na mesa e não na ficha.
    """

    texto_bruto: str | None = None
    cliente: Any = None
    juiz: Any = None
    buscas: dict = field(default_factory=dict)
    falhar_adaptador_uma_vez: bool = False
    chamadas: dict = field(default_factory=dict)


# ---------------------------------------------------------------- provedores determinísticos (sem modelo)
class ProvedorEco:
    """Finge ser um modelo que obedece ao formato pedido, usando as regras do próprio grupo.

    - Extrator: devolve os invariantes calculados pela salvaguarda determinística do grupo.
    - Adaptador: devolve o andaime por regras do grupo (nível 1 negrito; níveis 2 e 3 etapas).
    - Qualquer outro pedido (diretiva do Estrategista): delega ao provedor extrativo do grupo.
    """

    provider_name = "eco"
    model = "eco-deterministico"

    def __init__(self) -> None:
        from iris.core.llm_client import ExtractiveFallbackLLMProvider

        self._extrativo = ExtractiveFallbackLLMProvider()

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        system_prompt: str | None = None,
        json_mode: bool = False,
    ) -> Any:
        from iris.core.llm_client import LLMResponse

        sistema = system_prompt or ""
        if "Agente Extrator Curricular" in sistema:
            from iris.agents.curriculum_extractor import CurriculumExtractorAgent
            from iris.schemas.curriculum import ExtractionRequest

            m = re.search(r"ENUNCIADO:\n(.*?)(?:\nTRAVAS DO PROFESSOR|\Z)", prompt, flags=re.DOTALL)
            enunciado = (m.group(1) if m else prompt).strip()
            inv = CurriculumExtractorAgent._extracao_deterministica_fallback(
                None,  # type: ignore[arg-type]
                ExtractionRequest(enunciado=enunciado if len(enunciado) >= 15 else enunciado.ljust(15)),
            )
            texto = json.dumps(inv.model_dump(), ensure_ascii=False)
        elif "Agente Adaptador Pedagógico" in sistema:
            from iris.agents.adapter_agent import decompor_em_etapas, destacar_comandos

            m = re.search(r"ENUNCIADO ORIGINAL:\n(.*)\Z", prompt, flags=re.DOTALL)
            enunciado = (m.group(1) if m else "").strip()
            achado = re.search(r"NÍVEL (\d)", prompt)
            nivel = int(achado.group(1)) if achado else NIVEL_PADRAO
            adaptado = (
                destacar_comandos(enunciado) if nivel == 1 else decompor_em_etapas(enunciado, com_registro=nivel == 3)
            )
            texto = json.dumps(
                {"texto_adaptado": adaptado, "justificativas": ["eco: andaime por regras"]}, ensure_ascii=False
            )
        else:
            r = self._extrativo.generate(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
            return replace(r, provider=self.provider_name, model=self.model)
        return LLMResponse(text=texto, provider=self.provider_name, model=self.model)


class JuizEco:
    """Substituto do juiz LLM do Auditor: sempre responde "nada a apontar" em JSON válido.

    As checagens determinísticas do Auditor (termos intocáveis, marca de gabarito, cálculo resolvido,
    alternativas eliminadas) são as do grupo e rodam de verdade. Só a parte do modelo é trocada.
    """

    provider_name = "eco"
    model = "juiz-eco-deterministico"

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1500, **_: Any) -> str:
        return json.dumps({"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []})


class ClienteForcado:
    """Embrulha o provedor eco e estraga a minuta do Adaptador, para exercitar o laço do Auditor.

    modo "uma_vez": acrescenta uma marca de gabarito na 1ª tentativa; quando o pedido traz a correção do
    Auditor, obedece e devolve a minuta limpa.
    modo "sempre": acrescenta a marca em todas as tentativas, para o laço bater no limite.
    """

    # Marca de gabarito sem palavra nova: passa pela checagem de escopo do próprio Adaptador (que barra
    # vocabulário fora do enunciado) e é acusada pelo Auditor, que procura sinais de resposta entregue.
    MARCA = "✔"
    # Marca com palavras novas: o próprio Adaptador barra antes do Auditor (cenário "frase de gabarito").
    MARCA_COM_PALAVRAS = "Resposta correta: a) evaporação"

    def __init__(self, base: Any, modo: str, marca: str | None = None) -> None:
        self.base = base
        self.modo = modo
        self.marca = marca or self.MARCA
        self.provider_name = base.provider_name
        self.model = base.model
        self.estragadas = 0

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        system_prompt: str | None = None,
        json_mode: bool = False,
    ) -> Any:
        r = self.base.generate(
            prompt=prompt, temperature=temperature, max_tokens=max_tokens, system_prompt=system_prompt, json_mode=json_mode
        )
        e_adaptador = "Agente Adaptador Pedagógico" in (system_prompt or "")
        corrigindo = "CORREÇÃO PEDIDA PELO AUDITOR" in prompt
        if e_adaptador and (self.modo == "sempre" or not corrigindo):
            d = json.loads(r.text)
            d["texto_adaptado"] = d["texto_adaptado"].rstrip() + " " + self.marca
            r = replace(r, text=json.dumps(d, ensure_ascii=False))
            self.estragadas += 1
        return r


# ---------------------------------------------------------------- descrição dos nós (vai para a tela)
NOS: list[dict[str, str]] = [
    {"id": "entrada", "nome": "Entrada", "faz": "recebe o texto colado e confere o tamanho",
     "funcao_do_grupo": "iris.schemas.materials.validate_material_content"},
    {"id": "filtro_pii", "nome": "Filtro de dado pessoal", "faz": "troca dado pessoal por marcador e descarta o texto bruto",
     "funcao_do_grupo": "iris.security.pii_scrubber.sanitize_pii"},
    {"id": "decomposicao", "nome": "Decomposição", "faz": "separa o material em questões",
     "funcao_do_grupo": "iris.parsers.structural_decomposer.decompose_material"},
    {"id": "selecao_caracteristica", "nome": "Seleção da característica", "faz": "trava a adaptação na característica escolhida",
     "funcao_do_grupo": "iris.api.routes.catalogs.select_surgical_characteristics_service"},
    {"id": "proxima_questao", "nome": "Próxima questão", "faz": "pega a questão da vez ou encerra",
     "funcao_do_grupo": "(controle do grafo)"},
    {"id": "extrator", "nome": "Extrator curricular", "faz": "lista o que não pode mudar no enunciado",
     "funcao_do_grupo": "iris.agents.curriculum_extractor.CurriculumExtractorAgent"},
    {"id": "busca_rag", "nome": "Busca na base", "faz": "busca trechos filtrados pela barreira da característica",
     "funcao_do_grupo": "iris.agents.strategist_agent.StrategistAgent._buscar"},
    {"id": "estrategista", "nome": "Estrategista", "faz": "escreve a diretiva com base nos trechos",
     "funcao_do_grupo": "iris.agents.strategist_agent.StrategistAgent.strategize"},
    {"id": "adaptador", "nome": "Adaptador", "faz": "escreve a minuta adaptada",
     "funcao_do_grupo": "iris.agents.adapter_agent.AdapterAgent.adapt"},
    {"id": "auditor", "nome": "Auditor", "faz": "confere se a minuta preservou o conteúdo e não entregou a resposta",
     "funcao_do_grupo": "iris.agents.auditor.AgenteAuditor.auditar"},
    {"id": "decisao", "nome": "Decisão", "faz": "aprovado segue; reprovado volta ao Adaptador, até o limite de voltas",
     "funcao_do_grupo": "(controle do grafo)"},
    {"id": "saida_de_reserva", "nome": "Saída de reserva", "faz": "no limite de voltas, usa a adaptação por regras e avisa a professora",
     "funcao_do_grupo": "iris.agents.adapter_agent.AdapterAgent._saida_de_reserva"},
    {"id": "revisao_professora", "nome": "Revisão da professora", "faz": "o grafo para e espera a decisão de uma pessoa",
     "funcao_do_grupo": "(pausa do LangGraph: interrupt)"},
]
ROTULO_SETA = {
    ("proxima_questao", "extrator"): "há questão",
    ("proxima_questao", "__end__"): "acabaram",
    ("decisao", "revisao_professora"): "aprovado",
    ("decisao", "adaptador"): "refazer",
    ("decisao", "saida_de_reserva"): "limite",
}

# Posição de cada caixa numa grade (coluna, linha). A coluna 1 é o tronco; a 2, os desvios.
GRADE: dict[str, tuple[int, int]] = {
    "__start__": (1, 0),
    "entrada": (1, 1),
    "filtro_pii": (1, 2),
    "decomposicao": (1, 3),
    "selecao_caracteristica": (1, 4),
    "proxima_questao": (1, 5),
    "__end__": (2, 5),
    "extrator": (1, 6),
    "busca_rag": (1, 7),
    "estrategista": (1, 8),
    "adaptador": (1, 9),
    "auditor": (1, 10),
    "decisao": (1, 11),
    "revisao_professora": (1, 12),
    "saida_de_reserva": (2, 12),
}
CAIXA_L, CAIXA_A = 190, 44
PASSO_X, PASSO_Y = 260, 70
MARGEM_X, MARGEM_Y = 110, 16
CALHA_1, CALHA_PASSO = 30, 60  # distância da 1ª calha de volta ao tronco e entre calhas
LARGURA_LETRA = 6.6  # largura média de uma letra do rótulo, em pixels, para conferir sobreposição


def _caixa(no_id: str) -> dict[str, float]:
    col, lin = GRADE[no_id]
    x = MARGEM_X + (col - 1) * PASSO_X
    y = MARGEM_Y + lin * PASSO_Y
    return {"x": x, "y": y, "l": CAIXA_L, "a": CAIXA_A}


def _rota_da_seta(origem: str, destino: str, n_volta: int) -> list[list[float]]:
    """Pontos da seta. Para baixo: reta. Para o lado: cotovelo. Para cima: contorna pela calha da esquerda."""
    a, b = _caixa(origem), _caixa(destino)
    ax, ay = a["x"] + a["l"] / 2, a["y"] + a["a"]
    bx, by = b["x"] + b["l"] / 2, b["y"]
    (ca, la), (cb, lb) = GRADE[origem], GRADE[destino]
    if ca == cb and lb > la:
        return [[ax, ay], [bx, by]]
    if lb == la and cb != ca:  # mesma linha, outra coluna: sai pela lateral
        return [[a["x"] + a["l"], a["y"] + a["a"] / 2], [b["x"], b["y"] + b["a"] / 2]]
    if lb > la:  # desce e muda de coluna
        meio = ay + (by - ay) / 2
        return [[ax, ay], [ax, meio], [bx, meio], [bx, by]]
    # volta para cima: sai pela esquerda da origem, sobe pela calha e entra pela esquerda do destino
    calha = MARGEM_X - CALHA_1 - CALHA_PASSO * n_volta
    saida_y, entrada_y = a["y"] + a["a"] / 2, b["y"] + b["a"] / 2
    if ca != cb:  # origem fora do tronco: desce por baixo da linha antes de ir à calha
        baixo = a["y"] + a["a"] + 14
        return [[ax, a["y"] + a["a"]], [ax, baixo], [calha, baixo], [calha, entrada_y], [b["x"], entrada_y]]
    return [[a["x"], saida_y], [calha, saida_y], [calha, entrada_y], [b["x"], entrada_y]]


def _posicao_do_rotulo(pontos: list[list[float]], volta: bool) -> dict[str, Any]:
    """Onde escrever o rótulo da seta condicional, escolhido para não cair em cima de caixa nem de outra seta."""
    if volta:  # à esquerda da calha, na altura do meio da subida
        x, y0, y1 = pontos[1][0], pontos[1][1], pontos[2][1]
        return {"x": x - 6, "y": (y0 + y1) / 2 + 4, "ancora": "end"}
    if len(pontos) == 2 and pontos[0][0] == pontos[1][0]:  # reta para baixo: à esquerda da linha
        return {"x": pontos[0][0] - 8, "y": (pontos[0][1] + pontos[1][1]) / 2 + 4, "ancora": "end"}
    if len(pontos) == 2:  # reta para o lado: acima da linha
        return {"x": (pontos[0][0] + pontos[1][0]) / 2, "y": pontos[0][1] - 6, "ancora": "middle"}
    # cotovelo: no vão entre as duas colunas, acima do trecho horizontal
    vao = MARGEM_X + CAIXA_L + (PASSO_X - CAIXA_L) / 2
    return {"x": vao, "y": pontos[1][1] - 5, "ancora": "middle"}


# ---------------------------------------------------------------- nós
def _medido(no_id: str) -> Callable:
    """Acrescenta o id do nó ao caminho do estado, com a questão da vez e o tempo gasto."""

    def deco(fn: Callable) -> Callable:
        # sem functools.wraps: ele faria o LangGraph ler a assinatura da função de dentro
        def no(estado: EstadoIris, runtime: Runtime[Contexto]) -> dict:
            ctx = runtime.context
            ctx.chamadas[no_id] = ctx.chamadas.get(no_id, 0) + 1
            t0 = time.perf_counter()
            saida = fn(estado, ctx) or {}
            idx = saida.get("indice_questao", estado.get("indice_questao", -1))
            return {**saida, "caminho": [[no_id, idx, round(time.perf_counter() - t0, 4)]]}

        no.__name__ = f"no_{no_id}"
        no.__doc__ = fn.__doc__
        return no

    return deco


@_medido("entrada")
def _no_entrada(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.schemas.materials import validate_material_content

    validate_material_content(ctx.texto_bruto or "")
    return {"n_caracteres": len(ctx.texto_bruto or ""), "indice_questao": -1, "voltas_auditor": 0}


@_medido("filtro_pii")
def _no_filtro_pii(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.security.pii_scrubber import sanitize_pii

    sanitizado, n = sanitize_pii(ctx.texto_bruto or "")
    ctx.texto_bruto = None  # descarta o bruto assim que filtrado (RNF-02)
    return {"texto_sanitizado": sanitizado, "n_pii_removidos": int(n)}


def _enunciado(questao: Any) -> str:
    partes = [questao.statement.strip()]
    for op in questao.options or []:
        partes.append(f"{op.letter}) {op.text}")
    return "\n".join(p for p in partes if p)


@_medido("decomposicao")
def _no_decomposicao(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.parsers.structural_decomposer import decompose_material

    texto = estado["texto_sanitizado"]
    estrutura = decompose_material(texto)
    questoes = [{"id": q.id, "enunciado": _enunciado(q)} for q in estrutura.questions]
    if not questoes:  # sem questão detectada, o texto inteiro vira uma questão
        questoes = [{"id": "texto_inteiro", "enunciado": texto}]
    return {"questoes": questoes[:MAX_QUESTOES]}


@_medido("selecao_caracteristica")
def _no_selecao(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.api.routes.catalogs import select_surgical_characteristics_service

    sel = select_surgical_characteristics_service({"selected_ids": [estado["caracteristica"]]}).model_dump()
    return {"n_caracteristicas_bloqueadas": int(sel["blocked_count"])}


@_medido("proxima_questao")
def _no_proxima_questao(estado: EstadoIris, ctx: Contexto) -> dict:
    i = estado.get("indice_questao", -1) + 1
    questoes = estado.get("questoes", [])
    pulados = []
    # o contrato dos agentes recusa enunciado com menos de 15 caracteres: pula e registra
    while i < len(questoes) and len(questoes[i]["enunciado"]) < 15:
        pulados.append({"questao": questoes[i]["id"], "resultado": "erro", "motivo": "enunciado < 15 caracteres"})
        i += 1
    if i >= len(questoes):
        return {"indice_questao": i, "rota": "fim", "resultados": pulados}
    q = questoes[i]
    return {
        "indice_questao": i,
        "questao_id": q["id"],
        "enunciado": q["enunciado"],
        "rota": "questao",
        "tentativa": 0,
        "voltas_auditor": 0,
        "minuta": "",
        "minuta_anterior": None,
        "feedback_auditor": None,
        "alerta_professora": None,
        "decisao_professora": None,
        "resultados": pulados,
    }


@_medido("extrator")
def _no_extrator(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.agents.curriculum_extractor import CurriculumExtractorAgent

    agente = CurriculumExtractorAgent(llm_client=ctx.cliente)
    res = agente.extract_with_telemetry(estado["enunciado"], question_id=estado.get("questao_id"))
    return {"invariantes": res.invariants.model_dump()}


def _pedido_estrategia(estado: EstadoIris) -> Any:
    from iris.schemas.curriculum import CurriculumInvariants
    from iris.schemas.strategy import StrategyRequest

    return StrategyRequest(
        caracteristicas=[estado["caracteristica"]],
        nivel=estado["nivel"],
        invariantes=CurriculumInvariants(**estado["invariantes"]),
        enunciado=estado["enunciado"],
        metodo="bm25",
        k=5,
        question_id=estado.get("questao_id"),
    )


@_medido("busca_rag")
def _no_busca_rag(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.agents.strategist_agent import StrategistAgent

    agente = StrategistAgent(llm_client=ctx.cliente)
    buscas, fora, sem_evidencia = agente._buscar(_pedido_estrategia(estado))
    ctx.buscas[estado["questao_id"]] = (buscas, fora, sem_evidencia)  # o texto dos trechos fica no Contexto
    return {"chunk_ids": [t["chunk_id"] for b in buscas for t in b["trechos_rag"]]}


@_medido("estrategista")
def _no_estrategista(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.agents.strategist_agent import StrategistAgent

    agente = StrategistAgent(llm_client=ctx.cliente)
    pronto = ctx.buscas.get(estado["questao_id"])
    if pronto is not None:  # reaproveita a busca do nó anterior, sem tocar na classe
        agente._buscar = lambda req: pronto  # type: ignore[method-assign]
    res = agente.strategize(_pedido_estrategia(estado))
    return {"diretiva": res.diretiva, "estrategista_reserva": res.telemetry.motivo_fallback}


def _pedido_adaptacao(estado: EstadoIris) -> Any:
    from iris.schemas.adaptation import AdaptationRequest
    from iris.schemas.curriculum import CurriculumInvariants

    return AdaptationRequest(
        enunciado=estado["enunciado"],
        id_caracteristica=estado["caracteristica"],
        nivel=estado["nivel"],
        invariantes=CurriculumInvariants(**estado["invariantes"]),
        diretiva_psicopedagogica=estado.get("diretiva") or None,
        feedback_auditor=estado.get("feedback_auditor"),
        minuta_anterior=estado.get("minuta_anterior"),
        question_id=estado.get("questao_id"),
    )


@_medido("adaptador")
def _no_adaptador(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.agents.adapter_agent import AdapterAgent

    if ctx.falhar_adaptador_uma_vez:
        ctx.falhar_adaptador_uma_vez = False
        raise RuntimeError("falha simulada do Adaptador (por exemplo, o servidor do modelo caiu)")
    tentativa = estado.get("tentativa", 0) + 1
    res = AdapterAgent(llm_client=ctx.cliente).adapt(_pedido_adaptacao(estado), tentativa=tentativa)
    saida: dict[str, Any] = {"tentativa": tentativa, "minuta": res.texto_adaptado}
    if res.telemetry.motivo_fallback == "escopo_reprovado":
        # O próprio Adaptador barrou a minuta do modelo (palavra fora do enunciado) e devolveu a adaptação por
        # regras antes de o Auditor ver qualquer coisa: uma proteção que nenhuma tela mostrava.
        saida["barradas_pelo_adaptador"] = [{"questao": estado.get("questao_id"), "tentativa": tentativa}]
    return saida


@_medido("auditor")
def _no_auditor(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.agents.auditor import AgenteAuditor, caracteristicas_nao_selecionadas
    from iris.schemas.curriculum import CurriculumInvariants

    auditor = AgenteAuditor(juiz=ctx.juiz)
    nao_sel = caracteristicas_nao_selecionadas([estado["caracteristica"]])
    r = auditor.auditar(estado["enunciado"], estado["minuta"], CurriculumInvariants(**estado["invariantes"]), nao_sel)
    return {
        "auditoria": {"aprovado": r.aprovado, "motivos": list(r.motivos)},
        "feedback_auditor": None if r.aprovado else r.feedback(),
    }


def _fabricar_no_decisao(limite: int) -> Callable:
    @_medido("decisao")
    def _no_decisao(estado: EstadoIris, ctx: Contexto) -> dict:
        voltas = estado.get("voltas_auditor", 0)
        if estado["auditoria"]["aprovado"]:
            return {"rota": "aprovado", "texto_proposto": estado["minuta"], "alerta_professora": None}
        if voltas < limite:  # volta ao Adaptador levando a correção e a minuta reprovada
            return {"rota": "refazer", "voltas_auditor": voltas + 1, "minuta_anterior": estado["minuta"]}
        return {"rota": "limite"}

    return _no_decisao


@_medido("saida_de_reserva")
def _no_reserva(estado: EstadoIris, ctx: Contexto) -> dict:
    from iris.agents.adapter_agent import AdapterAgent

    texto, _just = AdapterAgent._saida_de_reserva(_pedido_adaptacao(estado))
    motivos = "; ".join(estado["auditoria"]["motivos"])[:300]
    return {
        "texto_proposto": texto,
        "alerta_professora": f"O Auditor reprovou {estado.get('voltas_auditor', 0) + 1} tentativa(s). Motivos: {motivos}",
    }


@_medido("revisao_professora")
def _no_revisao(estado: EstadoIris, ctx: Contexto) -> dict:
    # O grafo PARA aqui. O que vai na pausa é salvo: só texto já filtrado.
    resposta = interrupt(
        {
            "questao_id": estado.get("questao_id"),
            "texto_proposto": estado["texto_proposto"],
            "alerta": estado.get("alerta_professora"),
        }
    )
    decisao = resposta.get("decisao", "aceitou")
    return {
        "decisao_professora": decisao,
        "texto_final": resposta.get("texto_editado") or estado["texto_proposto"],
        "resultados": [
            {
                "questao": estado.get("questao_id"),
                "resultado": "aprovado" if estado.get("rota") == "aprovado" else "reserva",
                "voltas_auditor": estado.get("voltas_auditor", 0),
                "tentativas_do_adaptador": estado.get("tentativa", 0),
                "decisao_professora": decisao,
            }
        ],
    }


def _rota_questao(estado: EstadoIris) -> str:
    return "extrator" if estado.get("rota") == "questao" else END


def _rota_decisao(estado: EstadoIris) -> str:
    return {"aprovado": "revisao_professora", "refazer": "adaptador", "limite": "saida_de_reserva"}[estado["rota"]]


def construir_grafo(limite_voltas: int = LIMITE_VOLTAS) -> Any:
    """Monta e compila o grafo. Cada execução guarda o estado a cada passo (checkpointer em memória)."""
    if not LANGGRAPH_DISPONIVEL:
        raise RuntimeError(f"langgraph não está instalado: {ERRO_IMPORTACAO}")
    g = StateGraph(EstadoIris, context_schema=Contexto)
    funcoes = {
        "entrada": _no_entrada,
        "filtro_pii": _no_filtro_pii,
        "decomposicao": _no_decomposicao,
        "selecao_caracteristica": _no_selecao,
        "proxima_questao": _no_proxima_questao,
        "extrator": _no_extrator,
        "busca_rag": _no_busca_rag,
        "estrategista": _no_estrategista,
        "adaptador": _no_adaptador,
        "auditor": _no_auditor,
        "decisao": _fabricar_no_decisao(limite_voltas),
        "saida_de_reserva": _no_reserva,
        "revisao_professora": _no_revisao,
    }
    for no in NOS:
        g.add_node(no["id"], funcoes[no["id"]])
    for a, b in [
        (START, "entrada"),
        ("entrada", "filtro_pii"),
        ("filtro_pii", "decomposicao"),
        ("decomposicao", "selecao_caracteristica"),
        ("selecao_caracteristica", "proxima_questao"),
        ("extrator", "busca_rag"),
        ("busca_rag", "estrategista"),
        ("estrategista", "adaptador"),
        ("adaptador", "auditor"),
        ("auditor", "decisao"),
        ("saida_de_reserva", "revisao_professora"),
        ("revisao_professora", "proxima_questao"),
    ]:
        g.add_edge(a, b)
    g.add_conditional_edges("proxima_questao", _rota_questao, {"extrator": "extrator", END: END})
    g.add_conditional_edges(
        "decisao",
        _rota_decisao,
        {"revisao_professora": "revisao_professora", "adaptador": "adaptador", "saida_de_reserva": "saida_de_reserva"},
    )
    return g.compile(checkpointer=InMemorySaver())


# ---------------------------------------------------------------- desenho
def descrever_grafo(grafo: Any) -> dict[str, Any]:
    """Nós e setas como o LangGraph os devolve, mais a posição de cada caixa e o traçado de cada seta."""
    desenho = grafo.get_graph()
    descricao = {no["id"]: no for no in NOS}
    nos = []
    for no_id in desenho.nodes:
        if no_id not in GRADE:
            raise ValueError(f"Nó sem posição na grade: {no_id!r}. Acrescente em GRADE.")
        info = descricao.get(no_id, {})
        nos.append(
            {
                "id": no_id,
                "nome": info.get("nome") or {"__start__": "Início", "__end__": "Fim"}.get(no_id, no_id),
                "faz": info.get("faz", ""),
                "funcao_do_grupo": info.get("funcao_do_grupo", ""),
                "tipo": "borda" if no_id.startswith("__") else ("pausa" if no_id == "revisao_professora" else "passo"),
                **_caixa(no_id),
            }
        )
    setas = []
    n_volta = 0
    for e in desenho.edges:
        sobe = GRADE[e.target][1] < GRADE[e.source][1]
        pontos = _rota_da_seta(e.source, e.target, n_volta)
        rotulo = ROTULO_SETA.get((e.source, e.target), "")
        setas.append(
            {
                "de": e.source,
                "para": e.target,
                "condicional": bool(e.conditional),
                "rotulo": rotulo,
                "rotulo_pos": _posicao_do_rotulo(pontos, sobe) if rotulo else None,
                "volta": sobe,
                "pontos": pontos,
            }
        )
        n_volta += sobe
    largura = MARGEM_X + PASSO_X + CAIXA_L + 20
    altura = MARGEM_Y * 2 + max(lin for _, lin in GRADE.values()) * PASSO_Y + CAIXA_A + 14
    return {"nos": nos, "setas": setas, "largura": largura, "altura": altura, "mermaid": desenho.draw_mermaid()}


# ---------------------------------------------------------------- execução dos cenários
def _decisao_sintetica(pausa: dict) -> dict:
    """Decisão da "professora" no protótipo: aceita o aprovado; edita o que veio com alerta."""
    if pausa.get("alerta"):
        return {"decisao": "editou", "texto_editado": pausa["texto_proposto"].rstrip() + "\n(Revisado pela professora.)"}
    return {"decisao": "aceitou"}


def _rodar(grafo: Any, ctx: Contexto, thread_id: str) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": thread_id}}
    entrada: Any = {"material_id": "sintetico", "caracteristica": CARACTERISTICA_PADRAO, "nivel": NIVEL_PADRAO}
    pausas: list[dict] = []
    falha = None
    try:
        saida = grafo.invoke(entrada, cfg, context=ctx)
    except RuntimeError as exc:  # só o cenário de retomada chega aqui
        falha = {"erro": str(exc), "proximo_no_salvo": list(grafo.get_state(cfg).next), "chamadas_ate_a_falha": dict(ctx.chamadas)}
        saida = grafo.invoke(None, cfg, context=ctx)  # retoma do último passo salvo
    while saida.get("__interrupt__"):
        pausa = saida["__interrupt__"][0].value
        pausas.append({"questao_id": pausa["questao_id"], "com_alerta": bool(pausa["alerta"])})
        saida = grafo.invoke(Command(resume=_decisao_sintetica(pausa)), cfg, context=ctx)

    final = grafo.get_state(cfg).values
    historico = list(grafo.get_state_history(cfg))
    salvo = json.dumps([h.values for h in historico], ensure_ascii=False, default=str)
    caminho = final.get("caminho", [])
    return {
        "caminho": [{"no": no, "questao": idx, "segundos": seg} for no, idx, seg in caminho],
        "passos": len(caminho),
        "questoes": len(final.get("questoes", [])),
        "resultados": final.get("resultados", []),
        "pausas": pausas,
        "voltas_ao_adaptador": sum(int(r.get("voltas_auditor", 0)) for r in final.get("resultados", [])),
        "barradas_pelo_adaptador": len(final.get("barradas_pelo_adaptador", [])),
        "chamadas_por_no": dict(ctx.chamadas),
        "estados_salvos": len(historico),
        "n_pii_removidos": final.get("n_pii_removidos"),
        "nome_plantado_no_estado_salvo": NOME_PLANTADO in salvo,
        "texto_bruto_descartado": ctx.texto_bruto is None,
        "segundos_total": round(sum(seg for _, _, seg in caminho), 3),
        "falha": falha,
    }


CENARIOS: list[dict[str, str]] = [
    {"id": "normal", "nome": "Fluxo normal", "o_que_mostra": "o Auditor aprova de primeira e o grafo para na revisão da professora, uma vez por questão"},
    {"id": "estragada_uma_vez", "nome": "Minuta ruim uma vez", "o_que_mostra": "a 1ª minuta traz a resposta; o Auditor reprova, o Adaptador corrige com o retorno e a 2ª passa"},
    {"id": "estragada_sempre", "nome": "Minuta ruim sempre", "o_que_mostra": f"toda minuta traz a resposta; depois de {LIMITE_VOLTAS} voltas o grafo desiste, usa a saída de reserva e avisa a professora"},
    {"id": "frase_de_gabarito", "nome": "Frase de gabarito", "o_que_mostra": "toda minuta traz a frase \"Resposta correta: a) evaporação\"; o próprio Adaptador barra a minuta por palavra fora do enunciado e devolve a adaptação por regras, e o Auditor nem chega a ver a frase"},
    {"id": "retomada", "nome": "Queda e retomada", "o_que_mostra": "o Adaptador falha uma vez; o grafo retoma do último passo salvo, sem refazer Extrator, busca e Estrategista"},
]


def executar_cenarios() -> dict[str, Any]:
    """Roda os quatro cenários sobre o material sintético. Determinístico: sem rede e sem modelo."""
    grafo = construir_grafo()
    eco = ProvedorEco()
    execucoes = []
    for cenario in CENARIOS:
        cid = cenario["id"]
        cliente: Any = eco
        if cid == "estragada_uma_vez":
            cliente = ClienteForcado(eco, "uma_vez")
        elif cid == "estragada_sempre":
            cliente = ClienteForcado(eco, "sempre")
        elif cid == "frase_de_gabarito":
            cliente = ClienteForcado(eco, "sempre", marca=ClienteForcado.MARCA_COM_PALAVRAS)
        ctx = Contexto(texto_bruto=MATERIAL_SINTETICO, cliente=cliente, juiz=JuizEco(), falhar_adaptador_uma_vez=cid == "retomada")
        execucoes.append({**cenario, **_rodar(grafo, ctx, f"cenario-{cid}")})
    return {"grafo": descrever_grafo(grafo), "execucoes": execucoes}


_CACHE: dict[str, Any] = {}


def obter_arquitetura(recalcular: bool = False) -> dict[str, Any]:
    """Devolve o grafo e os cenários; sem `langgraph`, diz que falta e como instalar."""
    if not LANGGRAPH_DISPONIVEL:
        return {
            "disponivel": False,
            "motivo": f"A biblioteca langgraph não está instalada neste ambiente ({ERRO_IMPORTACAO}).",
            "como_instalar": "uv pip install langgraph",
        }
    if recalcular or "dados" not in _CACHE:
        from importlib.metadata import version

        _CACHE["dados"] = {
            "disponivel": True,
            "versao_langgraph": version("langgraph"),
            "provedor": "eco (determinístico, sem modelo): exercita o fluxo, não mede a qualidade do texto",
            "limite_voltas": LIMITE_VOLTAS,
            "caracteristica": CARACTERISTICA_PADRAO,
            "nivel": NIVEL_PADRAO,
            "nome_plantado": NOME_PLANTADO,
            **executar_cenarios(),
        }
    return _CACHE["dados"]
