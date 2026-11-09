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
    _, consultar, _ = carregar_modulos_rag()
    metodo_efetivo = metodo or consultar.METODO_PADRAO
    try:
        return consultar.buscar(
            pergunta=pergunta,
            metodo=metodo_efetivo,
            k=k,
            filtro_barreira=filtro_barreira,
            filtro_parte=filtro_parte,
            sinonimos=sinonimos,
        )
    except Exception:
        if fallback_bm25_se_sem_banco and metodo_efetivo != "bm25":
            return consultar.buscar(
                pergunta=pergunta,
                metodo="bm25",
                k=k,
                filtro_barreira=filtro_barreira,
                filtro_parte=filtro_parte,
                sinonimos=sinonimos,
            )
        raise


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

    trechos = buscar_evidencias(
        pergunta=consulta_composta,
        metodo=metodo,
        k=k,
        filtro_barreira=carac.barreira_rag_associada,
        sinonimos=True,
    )

    return {
        "id_caracteristica": carac.id_caracteristica,
        "nome_caracteristica": carac.nome,
        "barreira_rag_associada": carac.barreira_rag_associada,
        "principio_dua_primario": carac.principio_dua_primario,
        "nivel_selecionado": nivel,
        "diretriz_andaime": diretriz.to_dict(),
        "referencias_catalogo": [r.to_dict() for r in carac.referencias_bibliograficas],
        "trechos_rag": trechos,
    }


