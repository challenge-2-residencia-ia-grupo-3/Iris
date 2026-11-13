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
from iris.rag.contexto import conferir_citacoes, montar_contexto_estrategista

from iris.rag.engagement_context import (
    MotivationalContext,
    build_motivational_context,
    inject_motivational_context_into_prompt,
    verify_motivational_adaptation_preserves_curriculum,
)

__all__ = [
    "buscar_evidencias",
    "buscar_evidencias_com_meta",
    "buscar_por_caracteristica_atomica",
    "carregar_catalogo_fontes",
    "carregar_modulos_rag",
    "conferir_citacoes",
    "formatar_pagina_trecho",
    "garantir_chunks_locais",
    "listar_barreiras_rag",
    "montar_contexto_estrategista",
    "normalizar_trecho_ui",
    "obter_trechos_base",
    "responder_fundamentado",
    "MotivationalContext",
    "build_motivational_context",
    "inject_motivational_context_into_prompt",
    "verify_motivational_adaptation_preserves_curriculum",
]

try:
    from iris.rag.contexto import conferir_citacoes, montar_contexto_estrategista

    __all__.extend(["conferir_citacoes", "montar_contexto_estrategista"])
except ModuleNotFoundError:
    pass

