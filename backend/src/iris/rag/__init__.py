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

__all__ = [
    "buscar_evidencias",
    "buscar_por_caracteristica_atomica",
    "carregar_catalogo_fontes",
    "carregar_modulos_rag",
    "garantir_chunks_locais",
    "listar_barreiras_rag",
    "obter_trechos_base",
    "responder_fundamentado",
]

