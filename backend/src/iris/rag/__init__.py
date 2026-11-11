"""Subpacote de integração com a Base de Conhecimento Científica (RAG) do Íris."""
from iris.rag.bridge import (
    buscar_evidencias,
    buscar_por_caracteristica_atomica,
    carregar_catalogo_fontes,
    carregar_modulos_rag,
    garantir_chunks_locais,
    listar_barreiras_rag,
    obter_trechos_base,
    responder_fundamentado,
)
from iris.rag.contexto import conferir_citacoes, montar_contexto_estrategista

__all__ = [
    "buscar_evidencias",
    "buscar_por_caracteristica_atomica",
    "carregar_catalogo_fontes",
    "carregar_modulos_rag",
    "conferir_citacoes",
    "garantir_chunks_locais",
    "listar_barreiras_rag",
    "montar_contexto_estrategista",
    "obter_trechos_base",
    "responder_fundamentado",
]

