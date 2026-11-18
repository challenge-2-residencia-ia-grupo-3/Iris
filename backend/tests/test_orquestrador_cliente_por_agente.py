"""Orquestrador: no modo automático, cada agente usa o seu cliente (padrão do agente, Anthropic se o padrão estiver
fora do ar e houver chave, senão o modo sem modelo). Sem rede: get_llm_client é substituído por clientes de teste."""

import unittest
from unittest import mock

from iris.agents import orchestrator as O


class _Cliente:
    def __init__(self, provider: str, disponivel: bool) -> None:
        self.provider_name = provider
        self._disponivel = disponivel

    def status(self) -> dict:
        return {"primary_available": self._disponivel}


def _fabrica(padroes: dict[str, str], fora_do_ar: set[str] = frozenset(), tem_chave: bool = True):
    """Substituto de get_llm_client: `padroes` diz o provedor padrão de cada agente."""
    def get_llm_client(provider=None, model=None, agente=None, **kw):
        nome = provider or padroes.get(agente, "ollama")
        disponivel = nome not in fora_do_ar and (nome != "anthropic" or tem_chave)
        return _Cliente(nome, disponivel or nome == "extractive")
    return get_llm_client


PADROES = {"extrator": "ollama", "estrategista": "ollama", "adaptador": "anthropic", "auditor": "anthropic"}


class TestClientePorAgente(unittest.TestCase):
    def _resolver(self, provider="auto", **kw):
        with mock.patch.object(O, "get_llm_client", _fabrica(PADROES, **kw)):
            return {a: c.provider_name for a, c in O._resolver_clientes_por_agente(provider, None, None).items()}

    def test_cada_agente_no_seu_padrao(self):
        self.assertEqual(self._resolver(), PADROES)

    def test_sem_ollama_e_com_chave_os_locais_vao_para_a_anthropic(self):
        r = self._resolver(fora_do_ar={"ollama"})
        self.assertEqual(r, {"extrator": "anthropic", "estrategista": "anthropic", "adaptador": "anthropic", "auditor": "anthropic"})

    def test_sem_ollama_e_sem_chave_cai_no_modo_sem_modelo(self):
        r = self._resolver(fora_do_ar={"ollama"}, tem_chave=False)
        self.assertEqual(set(r.values()), {"extractive"})

    def test_provedor_pedido_vale_para_os_quatro(self):
        with mock.patch.object(O, "_resolver_cliente_llm", return_value=_Cliente("groq", True)):
            r = {a: c.provider_name for a, c in O._resolver_clientes_por_agente("groq", None, None).items()}
        self.assertEqual(set(r.values()), {"groq"})

    def test_cliente_explicito_vale_para_os_quatro(self):
        explicito = _Cliente("mock", True)
        r = O._resolver_clientes_por_agente(None, None, explicito)
        self.assertTrue(all(c is explicito for c in r.values()))

    def test_resposta_informa_o_provedor_de_cada_agente(self):
        res = O.MultiAgentOrchestrator().run(
            {"text": "Leia o texto e explique o conteúdo da fotossíntese.", "selected_ids": ["impulsividade_leitura_superficial_negacoes"],
             "nivel": 2, "provider": "extractive"})
        self.assertEqual(set(res.provedores_por_agente), set(O.AGENTES_DA_CORRENTE))
        self.assertEqual(set(res.provedores_por_agente.values()), {"extractive"})


if __name__ == "__main__":
    unittest.main()
