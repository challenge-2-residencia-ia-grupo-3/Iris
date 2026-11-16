"""rastro_pipeline.py: o caminho de um material pelo pipeline do Íris, etapa por etapa.

Pergunta que responde: "o que cada peça do código do grupo recebeu, devolveu, quanto demorou e onde
quebrou, para este material?". Usa só funções do grupo (commit 65e1f09), envolvidas por wrappers em
tempo de execução; nenhum arquivo do grupo é alterado.

Uso (na VPS, determinístico):
    python rastro_pipeline.py                         # 3 materiais sintéticos, provedor eco
    python rastro_pipeline.py --provedor extractive   # força as saídas de reserva do grupo
No PC (Ollama):
    python rastro_pipeline.py --provedor ollama --modelo llama3:latest

Saídas:
    pacote/reports/pipeline/<run_id>.jsonl         rastro completo (pode ter trecho de licença restrita)
    pacote/outputs/26-rastro-pipeline-resumo.json  resumo versionável (sem texto de documento restrito)
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True


def _carregar_trace():
    """Carrega o trace.py deste arnês pelo caminho (o nome colide com o módulo trace da biblioteca padrão)."""
    import importlib.util

    if "bancada_trace" in sys.modules:
        return sys.modules["bancada_trace"]
    spec = importlib.util.spec_from_file_location("bancada_trace", Path(__file__).resolve().with_name("trace.py"))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["bancada_trace"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


T = _carregar_trace()
T.preparar_ambiente()

ID_COMANDOS_MULTIPLOS = "sobrecarga_memoria_trabalho_comandos_multiplos"

# ---------------------------------------------------------------- materiais sintéticos
# Tudo inventado: nomes, escola, CPF e telefone são falsos de propósito.
MATERIAIS: list[dict] = [
    {
        "material_id": "M1-ciencias-docx",
        "formato": "docx",
        "disciplina": "Ciências",
        "ano": "6º ano",
        "texto": (
            "Escola Estadual Ficticia do Teste\n"
            "Aluno: Fulano Ficticio da Silva\n"
            "Matrícula: 2026-TESTE-001\n"
            "CPF do responsável: 111.111.111-11\n\n"
            "Leia o texto a seguir para responder às questões 1 e 2.\n"
            "Texto 1: A fotossíntese\n"
            "As plantas usam a luz solar, a água e o gás carbônico para produzir glicose e liberar oxigênio. "
            "Esse processo acontece nos cloroplastos das folhas.\n\n"
            "1) Leia o texto e explique como os cloroplastos produzem glicose. Em seguida, cite dois fatores "
            "que influenciam a fotossíntese.\n"
            "2) Observe o texto e responda: qual gás é liberado na fotossíntese?\n"
            "a) oxigênio\nb) nitrogênio\nc) hélio\n"
        ),
        "tabela": [["Fator", "Efeito"], ["luz solar", "fonte de energia"], ["água", "matéria-prima"]],
        "pii_plantado": ["Fulano Ficticio da Silva", "2026-TESTE-001", "111.111.111-11", "Escola Estadual Ficticia do Teste"],
    },
    {
        "material_id": "M2-matematica-pdf",
        "formato": "pdf",
        "disciplina": "Matemática",
        "ano": "7º ano",
        "texto": (
            "Escola Municipal Exemplo Inventado\n"
            "Professor: Beltrano Teste Inventado\n"
            "Contato da coordenação: (61) 99999-0000\n\n"
            "Atividade de Matemática\n\n"
            "1. Leia o problema, calcule o total de lápis e explique como você chegou ao resultado. "
            "Uma caixa tem 12 lápis e Ana comprou 4 caixas.\n"
            "2. Resolva a equação 3x + 12 = 30 e verifique se a resposta está correta.\n"
        ),
        "pii_plantado": ["Beltrano Teste Inventado", "(61) 99999-0000", "Escola Municipal Exemplo Inventado"],
    },
    {
        "material_id": "M3-historia-txt",
        "formato": "txt",
        "disciplina": "História",
        "ano": "8º ano",
        "texto": (
            "A Independência do Brasil\n\n"
            "1. Contexto\n"
            "No início do século XIX, a família real portuguesa se mudou para o Rio de Janeiro. "
            "A abertura dos portos mudou o comércio da colônia.\n\n"
            "2. O processo\n"
            "Em 1822, Dom Pedro declarou a independência. A aluna Ciclana Exemplo Falso deve apresentar "
            "este tópico na sexta-feira.\n\n"
            "Questão 1: Leia o texto, identifique duas mudanças causadas pela vinda da família real e "
            "explique por que a abertura dos portos foi importante.\n"
        ),
        "pii_plantado": ["Ciclana Exemplo Falso"],
    },
]

PERFIL_SINTETICO = {
    "codigo_anonimo": "SINT-0001",
    "barreiras_observadas": [
        {"id_caracteristica": ID_COMANDOS_MULTIPLOS, "observacao": "Perde etapas quando o enunciado tem vários comandos."}
    ],
    "historico_estrategias": [],
    "anotacoes_pedagogicas": [],
}


def expandir_texto(material: dict) -> dict:
    """Resolve os atalhos de texto gerado ('repetir', 'repetir_numerado') usados nos casos longos."""
    m = dict(material)
    if "repetir" in m:
        m["texto"] = m["repetir"]["bloco"] * int(m["repetir"]["vezes"])
    if "repetir_numerado" in m:
        b, n = m["repetir_numerado"]["bloco"], int(m["repetir_numerado"]["vezes"])
        m["texto"] = "Atividade longa\n\n" + "\n".join(f"{i}. {b}" for i in range(1, n + 1))
    return m


def montar_arquivo(material: dict) -> tuple[str, bytes]:
    """Gera em memória o arquivo do material no formato pedido (txt, docx ou pdf)."""
    material = expandir_texto(material)
    fmt = material.get("formato", "txt")
    texto = material.get("texto", "")
    nome = f"{material['material_id']}.{fmt}"
    if fmt == "txt":
        return nome, texto.encode(material.get("codificacao", "utf-8"))
    if fmt == "docx":
        import docx

        d = docx.Document()
        for par in texto.split("\n"):
            d.add_paragraph(par)
        if material.get("tabela"):
            linhas = material["tabela"]
            t = d.add_table(rows=len(linhas), cols=len(linhas[0]))
            for i, linha in enumerate(linhas):
                for j, cel in enumerate(linha):
                    t.cell(i, j).text = cel
        buf = io.BytesIO()
        d.save(buf)
        return nome, buf.getvalue()
    if fmt == "pdf":
        import fitz

        doc = fitz.open()
        linhas = texto.split("\n")
        por_pagina = 40
        for ini in range(0, max(1, len(linhas)), por_pagina):
            pagina = doc.new_page()
            pagina.insert_textbox(fitz.Rect(40, 40, 555, 810), "\n".join(linhas[ini:ini + por_pagina]),
                                  fontsize=9, fontname="helv")
        dados = doc.tobytes()
        doc.close()
        return nome, dados
    if fmt == "pdf_sem_texto":  # página em branco: simula digitalização sem camada de texto
        import fitz

        doc = fitz.open()
        doc.new_page()
        dados = doc.tobytes()
        doc.close()
        return f"{material['material_id']}.pdf", dados
    if fmt == "bytes":  # conteúdo bruto (para casos adversariais de arquivo corrompido)
        bruto = material.get("bytes") or material.get("bytes_texto", "").encode("utf-8")
        return material.get("nome_arquivo", nome), bruto
    raise ValueError(f"formato desconhecido: {fmt}")


# ---------------------------------------------------------------- resumos sem texto restrito
def _r_texto(s: Any) -> str:
    if isinstance(s, tuple) and len(s) == 2 and isinstance(s[1], int):
        return f"{s[1]} substituição(ões) de PII; {len(s[0])} caracteres"
    if isinstance(s, tuple) and len(s) == 2 and isinstance(s[1], str):
        return f"formato {s[1]}; {len(s[0])} caracteres extraídos"
    if isinstance(s, tuple):
        return f"{s}"
    return str(s)[:200]


def _r_estrutura(s: Any) -> str:
    return (f"{s.total_questions} questão(ões), {len(s.context_blocks)} texto(s) de apoio, "
            f"{len(s.unclassified_blocks)} bloco(s) não classificado(s), cabeçalho={'sim' if s.header else 'não'}")


def _r_prosa(s: Any) -> str:
    return f"{s.total_elements} elemento(s), profundidade {s.max_depth}"


def _r_selecao(s: Any) -> str:
    d = s.model_dump()
    return f"{d['selected_count']} ativada(s), {d['blocked_count']} bloqueada(s)"


def _r_perfil(s: Any) -> str:
    return f"perfil válido; {len(s.barreiras_observadas)} barreira(s) observada(s)"


def _r_extracao(s: Any) -> str:
    inv, t = s.invariants, s.telemetry
    return (f"verbo={inv.verbo_comando_bncc}; {len(inv.conceitos_obrigatorios)} conceito(s); "
            f"fallback={t.used_fallback}; json_direto={t.json_valido_direto}")


def _r_busca(s: Any) -> str:
    docs = sorted({t.get("doc", "?") for t in s.get("trechos_rag", [])})
    return (f"{len(s.get('trechos_rag', []))} trecho(s) via {s.get('metodo_efetivo')} "
            f"(barreira {s.get('barreira_rag_associada')}); docs: {', '.join(docs)}")


def _r_contexto(s: Any) -> str:
    return f"{len(s['fontes'])} fonte(s) rotulada(s) [T1..T{len(s['fontes'])}]; prompt de {len(s['contexto'])} caracteres"


def _r_citacoes(s: Any) -> str:
    return (f"citados={s['citados']}; inexistentes={s['citacoes_inexistentes']}; "
            f"frases sem citação={len(s['frases_sem_citacao'])}")


def _r_escopo(s: Any) -> str:
    return f"aprovado={s.aprovado}; regra={s.regra_aplicada}; violações={len(s.violacoes)}"


def _r_adapt(s: Any) -> str:
    t = s.telemetry
    return (f"adaptou={s.adaptacao_aplicada}; escopo={s.escopo.aprovado}; fallback={t.used_fallback}"
            f" ({t.motivo_fallback}); {len(s.texto_adaptado)} caracteres")


def _r_reserva(s: Any) -> str:
    return f"{len(s[0])} caracteres; {len(s[1])} justificativa(s)"


def _r_ciclo(s: Any) -> str:
    return f"{s['chamadas']} chamada(s); {s['total_ms']} ms; dentro do RNF-07={s['dentro_do_limite']}"


# ---------------------------------------------------------------- instrumentação
def instrumentar(r: T.Rastreador) -> list:
    """Envolve as funções do grupo que o pipeline chama. Devolve a lista de 'desfazer'."""
    import iris.agents.adapter_agent as aa
    import iris.parsers.structural_decomposer as sd

    desfazer = [
        r.envolver(sd, "organize_prose_structure", "organizacao_texto_corrido", _r_prosa,
                   entrada=lambda t: t),
        r.envolver(aa, "verificar_escopo", "laudo_isolamento_escopo", _r_escopo,
                   entrada=lambda o, a, c, n, trava=None: {"original": o, "adaptado": a, "caracteristica": c,
                                                           "nivel": n, "trava": trava}),
    ]
    # _saida_de_reserva é staticmethod: precisa voltar como staticmethod para não receber self
    original = aa.AdapterAgent.__dict__["_saida_de_reserva"]
    fn = original.__func__

    def reserva(req):
        with r.etapa("saida_de_reserva", "iris.agents.adapter_agent:AdapterAgent._saida_de_reserva",
                     {"enunciado": req.enunciado, "nivel": req.nivel, "caracteristica": req.id_caracteristica},
                     _r_reserva) as cx:
            out = fn(req)
            cx["saida"] = out
        return out

    aa.AdapterAgent._saida_de_reserva = staticmethod(reserva)
    desfazer.append(lambda: setattr(aa.AdapterAgent, "_saida_de_reserva", original))
    return desfazer


# ---------------------------------------------------------------- etapas por questão
def enunciado_da_questao(q: Any) -> str:
    partes = [q.statement.strip()]
    for op in q.options or []:
        partes.append(f"{op.letter}) {op.text}")
    return "\n".join(p for p in partes if p)


def adaptar_questao(r: T.Rastreador, cliente: T.ClienteRastreado, enunciado: str, cfg: dict,
                    disciplina: str | None = None, ano: str | None = None, question_id: str | None = None,
                    trava_referencia: Any = None) -> dict:
    """Extrator -> RAG (busca + contexto) -> diretiva -> Adaptador (+ laudo) -> ciclo. Devolve o que a bancada mede."""
    from iris.agents.adapter_agent import AdapterAgent, resumir_ciclo
    from iris.agents.curriculum_extractor import CurriculumExtractorAgent
    from iris.schemas.adaptation import AdaptationRequest
    from iris.schemas.curriculum import CurriculumInvariants

    carac, nivel = cfg["caracteristica"], cfg["nivel"]
    out: dict = {"question_id": question_id, "contextos": [], "chunk_ids": [], "diretiva": None,
                 "citacoes": None, "trava_recall": None}
    telemetrias = []

    # 1. Agente Extrator Curricular
    if cfg.get("usar_extrator", True):
        extrator = CurriculumExtractorAgent(llm_client=cliente)  # type: ignore[arg-type]
        with r.etapa("extrator_curricular", "iris.agents.curriculum_extractor:CurriculumExtractorAgent.extract_with_telemetry",
                     {"enunciado": enunciado, "disciplina": disciplina, "ano": ano}, _r_extracao) as cx:
            res = extrator.extract_with_telemetry(enunciado, disciplina=disciplina, ano_escolar=ano,
                                                  question_id=question_id, trava_referencia=trava_referencia)
            cx["saida"] = res
        invariantes = res.invariants
        telemetrias.append(res.telemetry)
        out["trava_recall"] = res.telemetry.trava_recall
        out["extrator_fallback"] = res.telemetry.used_fallback
    else:
        invariantes = CurriculumInvariants(conceitos_obrigatorios=["conteudo_curricular"], verbo_comando_bncc="identificar",
                                           operacao_cognitiva="Sem Extrator (ablação): trava genérica.")
        r.nao_implementada("extrator_curricular", "desligado nesta configuração (ablação)")
        r.linhas[-1]["status"] = "ok"
        r.linhas[-1]["funcao"] = "ablacao:sem_extrator"
        r.linhas[-1]["resumo_saida"] = "desligado na ablação: trava genérica ['conteudo_curricular']"
        out["extrator_fallback"] = None
    out["invariantes"] = invariantes.model_dump()

    # 2. RAG: busca por característica (só bm25), contexto e diretiva
    diretiva = None
    if cfg.get("usar_rag", True):
        T.preparar_rag()
        from iris.rag import bridge, contexto as ctx

        with r.etapa("busca_rag", "iris.rag.bridge:buscar_por_caracteristica_atomica",
                     {"id_caracteristica": carac, "nivel": nivel, "pergunta_adicional": enunciado,
                      "metodo": "bm25", "k": cfg.get("k", 5)}, _r_busca) as cx:
            busca = bridge.buscar_por_caracteristica_atomica(carac, nivel=nivel, pergunta_adicional=enunciado,
                                                            metodo="bm25", k=cfg.get("k", 5))
            cx["saida"] = busca
        out["chunk_ids"] = [t["chunk_id"] for t in busca["trechos_rag"]]
        out["contextos"] = [t.get("trecho", "") for t in busca["trechos_rag"]]
        trava = [*invariantes.conceitos_obrigatorios, *invariantes.termos_tecnicos_intocaveis]
        with r.etapa("contexto_rag", "iris.rag.contexto:montar_contexto_estrategista",
                     {"buscas": "[resultado da busca_rag]", "invariantes": trava}, _r_contexto) as cx:
            contexto = ctx.montar_contexto_estrategista([busca], invariantes=trava)
            cx["saida"] = contexto
        r.nao_implementada("agente_estrategista", "não há agente que transforme o contexto em diretiva; o arnês usa um substituto")

        # Substituto do arnês: o cliente de LLM do grupo + as instruções do Estrategista do pacote RAG do grupo
        _, _, gerar = bridge.carregar_modulos_rag()
        nome_c = contexto["fontes"] and busca["nome_caracteristica"]
        pergunta = (f"Que orientação de andaime de nível {nivel} ajuda o estudante com {nome_c} nesta questão, "
                    f"sem alterar o que ela avalia? Questão: {enunciado[:600]}")
        prompt = f"{contexto['contexto']}\n\nPERGUNTA: {pergunta}\n\nRESPOSTA:"
        with r.etapa("diretiva_substituta_arnes", "bancada:cliente.generate(gerar.INSTRUCOES + contexto)",
                     {"prompt": prompt}, lambda s: f"diretiva de {len(s)} caracteres") as cx:
            resp = cliente.generate(prompt=prompt, temperature=0.0, max_tokens=500, system_prompt=gerar.INSTRUCOES)
            diretiva = resp.text
            cx["saida"] = diretiva
        with r.etapa("conferencia_citacoes", "iris.rag.contexto:conferir_citacoes",
                     {"diretiva": diretiva}, _r_citacoes) as cx:
            confere = ctx.conferir_citacoes(diretiva, contexto["fontes"])
            cx["saida"] = confere
        out["diretiva"] = diretiva
        out["citacoes"] = {k: confere[k] for k in ("citados", "citacoes_inexistentes")} | {
            "n_frases_sem_citacao": len(confere["frases_sem_citacao"])}
    else:
        for e in ("busca_rag", "contexto_rag", "agente_estrategista"):
            r.nao_implementada(e, "desligado nesta configuração (ablação)")
            r.linhas[-1].update(status="ok", funcao="ablacao:sem_rag", resumo_saida="desligado na ablação")

    # 3. Agente Adaptador (o laudo e a reserva aparecem como subetapas pelos wrappers)
    agente = AdapterAgent(llm_client=cliente)  # type: ignore[arg-type]
    pedido = AdaptationRequest(enunciado=enunciado, id_caracteristica=carac, nivel=nivel, invariantes=invariantes,
                               diretiva_psicopedagogica=diretiva or None, question_id=question_id)
    n_antes = cliente.chamadas
    with r.etapa("agente_adaptador", "iris.agents.adapter_agent:AdapterAgent.adapt",
                 {"enunciado": enunciado, "caracteristica": carac, "nivel": nivel,
                  "tem_diretiva": bool(diretiva)}, _r_adapt) as cx:
        resultado = agente.adapt(pedido)
        cx["saida"] = resultado
    telemetrias.append(resultado.telemetry)
    out["prompt_adaptador"] = cliente.prompts[-1] if cliente.chamadas > n_antes else None
    out["resposta_bruta_adaptador"] = cliente.respostas[-1] if cliente.chamadas > n_antes else None

    r.nao_implementada("agente_auditor", "Agente Auditor (História 2.1.4, issue #19 aberta) não existe no código")

    with r.etapa("ciclo_rnf07", "iris.agents.adapter_agent:resumir_ciclo", {"nivel": nivel}, _r_ciclo) as cx:
        ciclo = resumir_ciclo(telemetrias, nivel)
        cx["saida"] = ciclo

    out.update(
        adaptado=resultado.texto_adaptado,
        adaptacao_aplicada=resultado.adaptacao_aplicada,
        escopo_aprovado=resultado.escopo.aprovado,
        violacoes=list(resultado.escopo.violacoes),
        used_fallback=resultado.telemetry.used_fallback,
        motivo_fallback=resultado.telemetry.motivo_fallback,
        ciclo=ciclo,
    )
    return out


# ---------------------------------------------------------------- material inteiro
def executar_material(material: dict, cliente: T.ClienteRastreado, cfg: dict, run_id: str, commit: str) -> tuple[T.Rastreador, dict]:
    """Roda o material pelas etapas do grupo, na ordem de process_material_file_service/text_service."""
    from iris.api.routes.catalogs import select_surgical_characteristics_service
    from iris.parsers.document_extractor import extract_text_from_file
    from iris.parsers.structural_decomposer import decompose_material
    from iris.schemas.materials import validate_file_size_limit, validate_material_content
    from iris.security.pii_scrubber import sanitize_pii
    try:  # o Perfil Pedagógico Portátil (#77) só existe a partir de 9bf8163; PRs abertos antes dele não têm o módulo
        from iris.schemas.profile import validar_perfil
    except ModuleNotFoundError:
        validar_perfil = None

    material = expandir_texto(material)
    r = T.Rastreador(run_id, material["material_id"], cliente.provider_name, T.nome_modelo(cliente), commit)
    cliente.rastreador = r
    desfazer = instrumentar(r)
    estado: dict = {"questoes": [], "erro": None, "texto_sanitizado": None, "n_questoes": 0}
    try:
        if material.get("formato", "texto") != "texto":
            nome, dados = montar_arquivo(material)
            with r.etapa("upload_tamanho", "iris.schemas.materials:validate_file_size_limit",
                         {"arquivo": nome, "bytes": len(dados)}, lambda s: f"{s} bytes aceitos") as cx:
                cx["saida"] = validate_file_size_limit(dados)
            with r.etapa("extracao_documento", "iris.parsers.document_extractor:extract_text_from_file",
                         {"arquivo": nome, "bytes": dados}, _r_texto) as cx:
                texto, _fmt = extract_text_from_file(nome, dados)
                cx["saida"] = (texto, _fmt)
        else:
            texto = material.get("texto", "")
            if not isinstance(texto, str) or not texto.strip():
                # mesma regra de process_material_text_service (materials.py), antes do filtro de PII
                from iris.schemas.materials import MaterialValidationError

                with r.etapa("entrada_texto", "iris.api.routes.materials:process_material_text_service (checagem de vazio)",
                             {"texto": texto}):
                    raise MaterialValidationError(message="O texto fornecido está vazio ou contém apenas espaços em branco.",
                                                  code="EMPTY_TEXT", field="text")
        estado["texto_extraido"] = texto
        with r.etapa("filtro_pii", "iris.security.pii_scrubber:sanitize_pii", {"texto": texto}, _r_texto) as cx:
            sanitizado, n_pii = sanitize_pii(texto)
            cx["saida"] = (sanitizado, n_pii)
        estado["texto_sanitizado"], estado["n_pii"] = sanitizado, n_pii
        with r.etapa("validacao_conteudo", "iris.schemas.materials:validate_material_content",
                     {"caracteres": len(sanitizado)}, lambda s: f"{s[0]} caracteres, {s[1]} palavras") as cx:
            cx["saida"] = validate_material_content(sanitizado)
        with r.etapa("decomposicao_estrutural", "iris.parsers.structural_decomposer:decompose_material",
                     {"texto": sanitizado}, _r_estrutura) as cx:
            estrutura = decompose_material(sanitizado)
            cx["saida"] = estrutura
        with r.etapa("selecao_caracteristicas", "iris.api.routes.catalogs:select_surgical_characteristics_service",
                     {"selected_ids": [cfg["caracteristica"]]}, _r_selecao) as cx:
            cx["saida"] = select_surgical_characteristics_service({"selected_ids": [cfg["caracteristica"]]})
        perfil = dict(PERFIL_SINTETICO)
        perfil["barreiras_observadas"] = [{"id_caracteristica": cfg["caracteristica"],
                                           "observacao": "Perde etapas quando o enunciado tem vários comandos."}]
        if validar_perfil is None:
            r.nao_implementada("perfil_pedagogico", "iris.schemas.profile não existe nesta versão do código (entrou no #77)")
        else:
            with r.etapa("perfil_pedagogico", "iris.schemas.profile:validar_perfil", perfil, _r_perfil) as cx:
                cx["saida"] = validar_perfil(perfil)

        questoes = [(q.id, enunciado_da_questao(q)) for q in estrutura.questions]
        if not questoes:
            # decisão do arnês (o grupo ainda não liga a decomposição aos agentes): texto inteiro como uma questão
            questoes = [("texto_inteiro", sanitizado)]
        estado["n_questoes"] = len(estrutura.questions)
        for qid, enunciado in questoes[: cfg.get("max_questoes", 3)]:
            r.questao = qid
            if len(enunciado) < 15:
                r.nao_implementada("agentes", "enunciado com menos de 15 caracteres: o contrato dos agentes recusa")
                r.linhas[-1].update(status="erro", resumo_saida="enunciado < 15 caracteres; agentes não chamados")
                continue
            try:
                estado["questoes"].append(adaptar_questao(r, cliente, enunciado, cfg, material.get("disciplina"),
                                                          material.get("ano"), qid))
            except Exception as exc:  # noqa: BLE001 - registra e segue para a próxima questão
                estado["questoes"].append({"question_id": qid, "erro": f"{type(exc).__name__}: {exc}"})
        r.questao = None
    except Exception as exc:  # noqa: BLE001 - erro de etapa já registrado no rastro
        estado["erro"] = {"tipo": type(exc).__name__, "codigo": getattr(exc, "code", None), "mensagem": str(exc)[:300]}
    finally:
        for d in reversed(desfazer):
            d()
        cliente.rastreador = None
    estado["prompts"] = list(cliente.prompts)
    return r, estado


def pii_no_caminho(material: dict, estado: dict) -> dict:
    """Quais dados pessoais plantados chegaram ao texto sanitizado e aos prompts enviados ao modelo."""
    plantado = material.get("pii_plantado", [])
    sanit = (estado.get("texto_sanitizado") or "").casefold()
    prompts = "\n".join(estado.get("prompts", [])).casefold()
    saidas = "\n".join(q.get("adaptado", "") or "" for q in estado.get("questoes", [])).casefold()
    return {
        "plantados": len(plantado),
        "no_texto_sanitizado": [p for p in plantado if p.casefold() in sanit],
        "nos_prompts_do_modelo": [p for p in plantado if p.casefold() in prompts],
        "na_saida_adaptada": [p for p in plantado if p.casefold() in saidas],
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provedor", default="eco", choices=["eco", "extractive", "ollama"])
    ap.add_argument("--modelo", default=None, help="só para ollama (padrão llama3:latest)")
    ap.add_argument("--nivel", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--caracteristica", default=ID_COMANDOS_MULTIPLOS)
    ap.add_argument("--max-questoes", type=int, default=3)
    ap.add_argument("--materiais", default=None, help="ids separados por vírgula (padrão: todos)")
    args = ap.parse_args(argv)

    commit = T.commit_grupo()
    cliente = T.criar_cliente(args.provedor, args.modelo)
    if args.provedor == "ollama":
        print("aquecendo o modelo:", cliente.warmup())
    cfg = {"caracteristica": args.caracteristica, "nivel": args.nivel, "max_questoes": args.max_questoes, "k": 5}
    escolhidos = [m for m in MATERIAIS if not args.materiais or m["material_id"] in args.materiais.split(",")]
    base = f"{T.carimbo()}-{args.provedor}"
    execucoes, arquivos = [], []
    for m in escolhidos:
        cliente.prompts.clear()
        cliente.respostas.clear()
        run_id = f"{base}-{m['material_id']}"
        r, estado = executar_material(m, cliente, cfg, run_id, commit)
        arquivos.append(r.gravar())
        resumo = r.resumo()
        resumo["n_questoes_detectadas"] = estado["n_questoes"]
        resumo["pii"] = pii_no_caminho(m, estado)
        resumo["erro_material"] = estado["erro"]
        execucoes.append(resumo)
        print(f"\n== {m['material_id']} ({m['formato']}) run_id={run_id}")
        for e in resumo["etapas"]:
            q = f"[{e['questao']}] " if e["questao"] else ""
            print(f"  {e['ordem']:>2} {q}{e['etapa']:<28} {e['status']:<16} {e['latencia_s']:>8.4f}s  {e['resumo_saida'][:110]}")
        print(f"  PII plantado: {resumo['pii']}")

    resumo_geral = {
        "commit_grupo": commit,
        "provedor": args.provedor,
        "modelo": T.nome_modelo(cliente),
        "gerado_em": T.agora_iso(),
        "chunks_sha16": T.sha16(T.CHUNKS),
        "config": cfg,
        "aviso": ("provedor determinístico: latências e saídas medem o encanamento, não a qualidade de um modelo"
                  if args.provedor != "ollama" else "LLM local via Ollama"),
        "execucoes": execucoes,
    }
    destino = T.OUTPUTS / "26-rastro-pipeline-resumo.json"
    T.escrever_json(destino, resumo_geral)
    print(f"\nrastros completos: {[str(a) for a in arquivos]}")
    print(f"resumo: {destino}")


if __name__ == "__main__":
    main()
