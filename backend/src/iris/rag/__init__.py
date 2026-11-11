"""Subpacote de integração com a Base de Conhecimento Científica (RAG) do Íris."""
from iris.rag.bridge import (
    buscar_evidencias,
    buscar_evidencias_com_meta,
    buscar_por_caracteristica_atomica,
    carregar_catalogo_fontes,
    carregar_modulos_rag,
    formatar_pagina_trecho,
    garantir_chunks_locais,
    listar_barreiras_rag,
    normalizar_trecho_ui,
    obter_trechos_base,
    responder_fundamentado,
)

__all__ = [
    "buscar_evidencias",
    "buscar_evidencias_com_meta",
    "buscar_por_caracteristica_atomica",
    "carregar_catalogo_fontes",
    "carregar_modulos_rag",
    "formatar_pagina_trecho",
    "garantir_chunks_locais",
    "listar_barreiras_rag",
    "normalizar_trecho_ui",
    "obter_trechos_base",
    "responder_fundamentado",
]

