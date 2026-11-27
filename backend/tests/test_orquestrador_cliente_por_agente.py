"""Orquestrador: no modo automático, cada agente usa o seu cliente (padrão do agente, Anthropic se o padrão estiver
fora do ar e houver chave, senão o modo sem modelo). Sem rede: get_llm_client é substituído por clientes de teste."""

import json
import unittest
from unittest import mock

from iris.agents import orchestrator as O
from iris.core.llm_client import LLMResponse


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
    def _resolver(self, provider="auto", externo_ok=True, **kw):
        with mock.patch.object(O, "external_adaptation_allowed", return_value=externo_ok):
            with mock.patch.object(O, "get_llm_client", _fabrica(PADROES, **kw)):
                return {a: c.provider_name for a, c in O._resolver_clientes_por_agente(provider, None, None).items()}

    def test_cada_agente_no_seu_padrao(self):
        self.assertEqual(self._resolver(externo_ok=True), PADROES)

    def test_sem_opt_in_nao_cai_para_anthropic_mesmo_com_ollama_offline(self):
        r = self._resolver(externo_ok=False, fora_do_ar={"ollama"}, tem_chave=True)
        self.assertEqual(set(r.values()), {"extractive"})

    def test_sem_ollama_e_com_chave_os_locais_vao_para_a_anthropic(self):
        r = self._resolver(externo_ok=True, fora_do_ar={"ollama"})
        self.assertEqual(r, {"extrator": "anthropic", "estrategista": "anthropic", "adaptador": "anthropic", "auditor": "anthropic"})

    def test_sem_ollama_e_sem_chave_cai_no_modo_sem_modelo(self):
        r = self._resolver(externo_ok=True, fora_do_ar={"ollama"}, tem_chave=False)
        self.assertEqual(set(r.values()), {"extractive"})

    def test_provedor_pedido_vale_para_os_quatro(self):
        with mock.patch.object(O, "_resolver_cliente_llm", return_value=_Cliente("groq", True)):
            r = {a: c.provider_name for a, c in O._resolver_clientes_por_agente("groq", None, None).items()}
        self.assertEqual(set(r.values()), {"groq"})

    def test_provedor_externo_explicito_bloqueado_sem_opt_in(self):
        with mock.patch.object(O, "external_adaptation_allowed", return_value=False):
            with self.assertRaises(O.ExternalLLMDisabledError):
                O._resolver_clientes_por_agente("anthropic", None, None)
            with self.assertRaises(O.ExternalLLMDisabledError):
                O._resolver_clientes_por_agente("groq", None, None)

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

    def test_modo_misto_ollama_e_anthropic_informa_modelo_do_adaptador(self):
        class _ClienteComGeracao:
            def __init__(self, provider: str, model: str) -> None:
                self.provider_name = provider
                self.model = model

            def status(self) -> dict:
                return {"primary_available": True}

            def generate(
                self,
                prompt: str,
                temperature: float = 0.0,
                max_tokens: int = 900,
                system_prompt: str | None = None,
                json_mode: bool = False,
            ) -> LLMResponse:
                sistema = system_prompt or ""
                if "Agente Extrator Curricular" in sistema:
                    dados = {
                        "conceitos_obrigatorios": ["valor total"],
                        "termos_tecnicos_intocaveis": ["R$ 25"],
                        "verbo_comando_bncc": "identificar",
                        "operacao_cognitiva": "identificar a alternativa incorreta",
                        "habilidade_bncc_sugerida": "EF05MA01",
                        "alerta_anti_muleta": "",
                        "justificativa_preservacao": "ok",
                    }
                elif "Agente Estrategista" in sistema:
                    dados = {
                        "intervencoes": [
                            {
                                "id_caracteristica": "impulsividade_leitura_superficial_negacoes",
                                "texto": "Destacar a negação no comando [T1]",
                            }
                        ]
                    }
                elif "Agente Adaptador Pedagógico" in sistema:
                    dados = {
                        "texto_adaptado": (
                            "Uma loja vende 12 camisetas por R$ 25 cada.\n\n"
                            "**ATENÇÃO:** Qual alternativa **NÃO** apresenta o **valor total** correto?"
                        ),
                        "justificativas": ["Negação destacada em negrito."],
                    }
                else:
                    dados = {"resolveu_questao": False, "evidencia_resolucao": "", "modificacoes_intrusivas": []}
                return LLMResponse(
                    text=json.dumps(dados),
                    provider=self.provider_name,
                    model=self.model,
                    prompt_tokens=10,
                    completion_tokens=10,
                )

        def get_cliente_misto(provider=None, model=None, agente=None, **kw):
            if agente in ("extrator", "estrategista"):
                return _ClienteComGeracao("ollama", "llama3.1:8b")
            return _ClienteComGeracao("anthropic", "claude-haiku-5-5")

        with mock.patch.object(O, "get_llm_client", get_cliente_misto):
            res = O.MultiAgentOrchestrator().run(
                {
                    "text": "Uma loja vende 12 camisetas por R$ 25 cada. Qual alternativa NÃO apresenta o valor total correto?",
                    "selected_ids": ["impulsividade_leitura_superficial_negacoes"],
                    "nivel": 2,
                    "provider": "auto",
                }
            )
        self.assertEqual(res.provedores_por_agente, PADROES)
        self.assertEqual(res.questoes_trace[0].extrator.telemetry.model, "llama3.1:8b")
        self.assertEqual(res.provider, "anthropic")
        self.assertEqual(res.model, "claude-haiku-5-5")

    def test_disponivel_prioriza_primary_sem_chamar_status(self):
        class _Primario:
            def __init__(self, ok: bool) -> None:
                self._ok = ok

            def is_available(self) -> bool:
                return self._ok

        class _ComPrimario:
            def __init__(self, ok: bool) -> None:
                self._primary = _Primario(ok)

            def status(self) -> dict:
                raise AssertionError("status() não deve ser chamado quando _primary.is_available existe")

        self.assertTrue(O._disponivel(_ComPrimario(True)))
        self.assertFalse(O._disponivel(_ComPrimario(False)))


if __name__ == "__main__":
    unittest.main()
