"""Quantos trechos o gerador do RAG recebe: 20 com a API da Anthropic, 5 com os demais, e RAG_K fixa a mão."""

import os
import unittest
from unittest import mock

from iris.rag.bridge import carregar_modulos_rag

_, consultar, gerar = carregar_modulos_rag()


def _ambiente(**extra):
    limpo = {k: v for k, v in os.environ.items() if k not in ("RAG_LLM", "RAG_K")}
    return mock.patch.dict(os.environ, {**limpo, **extra}, clear=True)


class TestKPadrao(unittest.TestCase):
    def test_vinte_com_a_api_e_cinco_com_os_demais(self):
        with _ambiente(RAG_LLM="anthropic"):
            self.assertEqual(gerar.k_padrao(), 20)
        for provedor in ("ollama", "groq", "extractive"):
            with _ambiente(RAG_LLM=provedor):
                self.assertEqual(gerar.k_padrao(), 5, provedor)

    def test_rag_k_fixa_o_numero(self):
        with _ambiente(RAG_LLM="anthropic", RAG_K="5"):
            self.assertEqual(gerar.k_padrao(), 5)
        with _ambiente(RAG_LLM="ollama", RAG_K="8"):
            self.assertEqual(gerar.k_padrao(), 8)


class TestResponderUsaOPadrao(unittest.TestCase):
    """`responder` sem k pede à busca o número do padrão; com k explícito, respeita quem chamou."""

    def _k_pedido(self, **kw):
        pedidos = []

        def buscar(pergunta, metodo, k, filtro_barreira=None):
            pedidos.append(k)
            return []
        with mock.patch.object(consultar, "buscar", side_effect=buscar), \
                mock.patch.object(gerar, "gerar", return_value=("resposta", {})):
            gerar.responder("Como adaptar a prova?", **kw)
        return pedidos[0]

    def test_sem_k(self):
        with _ambiente(RAG_LLM="anthropic"):
            self.assertEqual(self._k_pedido(), 20)
        with _ambiente(RAG_LLM="ollama"):
            self.assertEqual(self._k_pedido(), 5)

    def test_k_explicito(self):
        with _ambiente(RAG_LLM="anthropic"):
            self.assertEqual(self._k_pedido(k=5), 5)


if __name__ == "__main__":
    unittest.main()
