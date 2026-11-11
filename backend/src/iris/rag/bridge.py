"""Ponte de integração (Adapter) entre o pacote principal `src/iris` e `rag/iris-rag/pacote`.

Permite que qualquer módulo da API FastAPI, dos Agentes ou da suíte de testes invoque
a ingestão, a busca (`consultar.buscar`) e a geração fundamentada (`gerar.responder`)
independentemente do diretório de trabalho atual (`cwd`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from iris.config import RAG_BASE_DIR, RAG_PACOTE_DIR


def _ensure_rag_path() -> None:
    """Registra `rag/iris-rag/pacote` no `sys.path` se ainda não estiver presente."""
    pacote_str = str(RAG_PACOTE_DIR)
    if pacote_str not in sys.path:
        sys.path.insert(0, pacote_str)


def carregar_modulos_rag() -> tuple[Any, Any, Any]:
    """Importa e retorna os módulos `(ingestao, consultar, gerar)` do pacote RAG."""
    _ensure_rag_path()
    import consultar  # type: ignore[import-not-found]
    import gerar  # type: ignore[import-not-found]
    import ingestao  # type: ignore[import-not-found]

    return ingestao, consultar, gerar


def garantir_chunks_locais(verbose: bool = False) -> Path:
    """Garante que `chunks.jsonl` exista localmente, gerando-o se ausente."""
    ingestao, _, _ = carregar_modulos_rag()
    saida: Path = ingestao.SAIDA_CHUNKS
    if not saida.exists():
        ingestao.rodar(salvar=True, verbose=verbose, permitir_ausentes=True)
    return saida


def obter_trechos_base() -> list[dict[str, Any]]:
    """Retorna a lista de todos os trechos (`chunks.jsonl`) carregados na base."""
    ingestao, _, _ = carregar_modulos_rag()
    return ingestao.carregar_chunks()


def listar_barreiras_rag() -> list[str]:
    """Lista todas as tags de barreiras funcionais indexadas nos trechos do RAG."""
    chunks = obter_trechos_base()
    barreiras: set[str] = set()
    for c in chunks:
        for b in c.get("barreiras", []):
            if b:
                barreiras.add(b)
    return sorted(barreiras)


def carregar_catalogo_fontes() -> dict[str, Any]:
    """Lê o catálogo científico `rag/iris-rag/fontes.json`."""
    caminho = RAG_BASE_DIR / "fontes.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def formatar_pagina_trecho(pagina_inicio: Any, pagina_fim: Any = None) -> str | None:
    """Formata intervalo de páginas (`'7'` ou `'7-8'`) a partir dos metadados do chunk."""
    if pagina_inicio is None and pagina_fim is None:
        return None
    if pagina_inicio is None:
        return str(pagina_fim)
    if pagina_fim is None or pagina_fim == pagina_inicio:
        return str(pagina_inicio)
    return f"{pagina_inicio}-{pagina_fim}"


def normalizar_trecho_ui(
    trecho: dict[str, Any],
    ref: str,
    chunk_meta: dict[str, Any] | None = None,
    status_gabarito: str | None = None,
) -> dict[str, Any]:
    """Padroniza um trecho recuperado/registrado com todos os metadados para leitura na UI."""
    meta = chunk_meta or {}
    chunk_id = trecho.get("chunk_id") or meta.get("chunk_id", "")
    texto = (
        trecho.get("texto")
        or trecho.get("trecho")
        or meta.get("texto")
        or "(texto de licença restrita não distribuído no repositório)"
    )
    pagina = trecho.get("pagina")
    if pagina is None:
        pagina = formatar_pagina_trecho(
            meta.get("pagina_inicio", meta.get("pagina_inicial")),
            meta.get("pagina_fim"),
        )
    n_palavras = trecho.get("n_palavras")
    if n_palavras is None:
        n_palavras = meta.get("n_palavras")
    if n_palavras is None and isinstance(texto, str):
        n_palavras = 0 if "restrição de licença" in texto.lower() else len(texto.split())

    texto_lower = str(texto).lower()
    licenca_restrita = (
        "restrição de licença" in texto_lower
        or "licença restrita" in texto_lower
        or n_palavras == 0
    )

    return {
        "ref": ref,
        "chunk_id": chunk_id,
        "doc": trecho.get("doc") or meta.get("doc_id") or (chunk_id.split("#")[0] if chunk_id else ""),
        "titulo": trecho.get("titulo") or meta.get("titulo", ""),
        "orgao": trecho.get("orgao") or meta.get("orgao", ""),
        "ano": trecho.get("ano") or meta.get("ano", ""),
        "url": trecho.get("url") or meta.get("url", ""),
        "licenca": trecho.get("licenca") or meta.get("licenca", ""),
        "parte": trecho.get("parte") or meta.get("parte", ""),
        "idioma": trecho.get("idioma") or meta.get("idioma", ""),
        "tipo_evidencia": trecho.get("tipo_evidencia") or meta.get("tipo_evidencia", ""),
        "pagina": pagina,
        "secao": trecho.get("secao") or meta.get("secao", ""),
        "n_palavras": n_palavras,
        "nao_usar_para": list(trecho.get("nao_usar_para") or meta.get("nao_usar_para") or []),
        "nota_uso": trecho.get("nota_uso") or meta.get("nota_uso", ""),
        "licenca_restrita": licenca_restrita,
        "status_gabarito": status_gabarito or trecho.get("status_gabarito") or "Contexto Adicional",
        "score": trecho.get("score"),
        "texto": texto,
    }


def _enriquecer_trechos_busca(trechos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Complementa os resultados de `consultar.buscar` com metadados extras de `chunks.jsonl`."""
    if not trechos:
        return trechos
    chunks_map = {c["chunk_id"]: c for c in obter_trechos_base()}
    enriquecidos: list[dict[str, Any]] = []
    for item in trechos:
        meta = chunks_map.get(item.get("chunk_id", ""), {})
        copia = dict(item)
        copia.setdefault("orgao", meta.get("orgao", ""))
        copia.setdefault("ano", meta.get("ano", ""))
        copia.setdefault("licenca", meta.get("licenca", ""))
        copia.setdefault("n_palavras", meta.get("n_palavras"))
        texto_lower = str(copia.get("trecho") or "").lower()
        copia["licenca_restrita"] = (
            "restrição de licença" in texto_lower
            or "licença restrita" in texto_lower
            or copia.get("n_palavras") == 0
        )
        enriquecidos.append(copia)
    return enriquecidos


def buscar_evidencias_com_meta(
    pergunta: str,
    metodo: str | None = None,
    k: int = 5,
    filtro_barreira: str | None = None,
    filtro_parte: str | None = None,
    sinonimos: bool = False,
    fallback_bm25_se_sem_banco: bool = True,
) -> dict[str, Any]:
    """Executa a recuperação no RAG informando método solicitado, método efetivo e eventual fallback."""
    _, consultar, _ = carregar_modulos_rag()
    metodo_solicitado = metodo or consultar.METODO_PADRAO
    try:
        resultados = consultar.buscar(
            pergunta=pergunta,
            metodo=metodo_solicitado,
            k=k,
            filtro_barreira=filtro_barreira,
            filtro_parte=filtro_parte,
            sinonimos=sinonimos,
        )
        return {
            "trechos": _enriquecer_trechos_busca(resultados),
            "metodo_solicitado": metodo_solicitado,
            "metodo_efetivo": metodo_solicitado,
            "fallback_aplicado": False,
        }
    except Exception:
        if fallback_bm25_se_sem_banco and metodo_solicitado != "bm25":
            resultados = consultar.buscar(
                pergunta=pergunta,
                metodo="bm25",
                k=k,
                filtro_barreira=filtro_barreira,
                filtro_parte=filtro_parte,
                sinonimos=sinonimos,
            )
            return {
                "trechos": _enriquecer_trechos_busca(resultados),
                "metodo_solicitado": metodo_solicitado,
                "metodo_efetivo": "bm25",
                "fallback_aplicado": True,
            }
        raise


def buscar_evidencias(
    pergunta: str,
    metodo: str | None = None,
    k: int = 5,
    filtro_barreira: str | None = None,
    filtro_parte: str | None = None,
    sinonimos: bool = False,
    fallback_bm25_se_sem_banco: bool = True,
) -> list[dict[str, Any]]:
    """Executa a recuperação de trechos científicos no RAG de forma resiliente.

    Se o banco vetorial (`pgvector`/`chroma`) não estiver acessível no ambiente local
    e `fallback_bm25_se_sem_banco=True`, utiliza automaticamente o método lexical `bm25`
    sobre os trechos carregados em memória.
    """
    return buscar_evidencias_com_meta(
        pergunta=pergunta,
        metodo=metodo,
        k=k,
        filtro_barreira=filtro_barreira,
        filtro_parte=filtro_parte,
        sinonimos=sinonimos,
        fallback_bm25_se_sem_banco=fallback_bm25_se_sem_banco,
    )["trechos"]


def responder_fundamentado(
    pergunta: str,
    metodo: str | None = None,
    k: int = 5,
    filtro_barreira: str | None = None,
) -> dict[str, Any]:
    """Gera uma resposta fundamentada com citações `[T1]..[Tk]` via módulo `gerar.py`."""
    _, consultar, gerar = carregar_modulos_rag()
    metodo_efetivo = metodo or consultar.METODO_PADRAO
    return gerar.responder(
        pergunta=pergunta,
        metodo=metodo_efetivo,
        k=k,
        filtro_barreira=filtro_barreira,
    )


def buscar_por_caracteristica_atomica(
    id_caracteristica: str,
    nivel: int = 2,
    pergunta_adicional: str = "",
    metodo: str | None = None,
    k: int = 5,
) -> dict[str, Any]:
    """Conecta o Catálogo Modular (#39) à busca determinística do RAG (#16).

    Dado um `id_caracteristica` atômico selecionado pelo professor e o `nivel` (1, 2 ou 3),
    recupera a diretriz de andaime correspondente no catálogo e executa a busca no RAG
    filtrando estritamente pela `barreira_rag_associada`.
    """
    from iris.schemas.catalog import get_characteristic_by_id

    carac = get_characteristic_by_id(id_caracteristica)
    chave_nivel = f"nivel_{nivel}"
    if chave_nivel not in carac.diretrizes_andaime:
        raise ValueError(f"Nível de andaime inválido: {nivel!r}. Use 1, 2 ou 3.")

    diretriz = carac.diretrizes_andaime[chave_nivel]
    termos_query = " ".join(carac.palavras_chave_busca[:3])
    consulta_composta = (
        f"{carac.nome}. {diretriz.objetivo_andaime}. {termos_query}. {pergunta_adicional}".strip()
    )

    busca = buscar_evidencias_com_meta(
        pergunta=consulta_composta,
        metodo=metodo,
        k=k,
        filtro_barreira=carac.barreira_rag_associada,
        sinonimos=True,
    )

    return {
        "id_caracteristica": carac.id_caracteristica,
        "nome_caracteristica": carac.nome,
        "descricao_observavel": carac.descricao_observavel,
        "exemplos_manifestacao_sala": list(carac.exemplos_manifestacao_sala),
        "barreira_rag_associada": carac.barreira_rag_associada,
        "principio_dua_primario": carac.principio_dua_primario,
        "nivel_selecionado": nivel,
        "diretriz_andaime": diretriz.to_dict(),
        "referencias_catalogo": [r.to_dict() for r in carac.referencias_bibliograficas],
        "metodo_solicitado": busca["metodo_solicitado"],
        "metodo_efetivo": busca["metodo_efetivo"],
        "fallback_aplicado": busca["fallback_aplicado"],
        "trechos_rag": busca["trechos"],
    }


