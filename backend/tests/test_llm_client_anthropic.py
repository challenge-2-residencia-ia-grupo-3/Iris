"""Provedor da Anthropic no cliente dos agentes e escolha de modelo por agente (sem rede: a chamada HTTP é simulada)."""
from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from iris.core import llm_client as L


def _resposta(modelo: str = "claude-haiku-5-5", texto: str = '{"ok": true}', parada: str = "end_turn"):
    corpo = {"model": modelo, "stop_reason": parada, "content": [{"type": "text", "text": texto}],
             "usage": {"input_tokens": 10, "output_tokens": 5}}
    return io.BytesIO(json.dumps(corpo).encode())


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestAnthropicProvider(unittest.TestCase):
    def setUp(self):
        limpo = {k: v for k, v in os.environ.items() if not k.startswith(("IRIS_LLM", "IRIS_ANTHROPIC", "RAG_LLM"))}
        self._env = mock.patch.dict(os.environ, {**limpo, "ANTHROPIC_API_KEY": "chave-de-teste"}, clear=True)
        self._env.start()
        self.addCleanup(self._env.stop)
        self.enviados: list[dict] = []

    def _gerar(self, respostas, **kw):
        fila = list(respostas)

        def urlopen(req, timeout=None):
            self.enviados.append(json.loads(req.data))
            r = fila.pop(0)
            if isinstance(r, Exception):
                raise r
            return _Resp(r.getvalue())
        prov = L.AnthropicLLMProvider(model=kw.pop("model", None))
        with mock.patch.object(L.urllib.request, "urlopen", urlopen), mock.patch.object(L.time, "sleep", lambda s: None):
            return prov.generate("PERGUNTA", **kw)

    def test_padrao_e_haiku_sem_temperatura_com_piso_de_tokens(self):
        r = self._gerar([_resposta()], max_tokens=500)
        corpo = self.enviados[0]
        self.assertEqual(corpo["model"], "claude-haiku-5-5")
        self.assertNotIn("temperature", corpo)
        self.assertEqual(corpo["max_tokens"], L.PISO_TOKENS_ANTHROPIC)
        self.assertEqual(corpo["output_config"], {"effort": "low"})
        self.assertEqual(r.provider, "anthropic")
        self.assertEqual((r.prompt_tokens, r.completion_tokens), (10, 5))

    def test_modelo_legado_usa_temperatura(self):
        self._gerar([_resposta("claude-sonnet-4-5-20250929")], model="claude-sonnet-4-5-20250929", max_tokens=500)
        corpo = self.enviados[0]
        self.assertEqual(corpo["temperature"], 0.0)
        self.assertEqual(corpo["max_tokens"], 500)
        self.assertNotIn("output_config", corpo)

    def test_nome_de_modelo_local_cai_no_padrao(self):
        os.environ["IRIS_LLM_MODEL"] = "llama3.1:8b"
        self._gerar([_resposta()])
        self.assertEqual(self.enviados[0]["model"], "claude-haiku-5-5")

    def test_json_mode_vai_na_instrucao_de_sistema(self):
        self._gerar([_resposta()], system_prompt="Você é o Adaptador.", json_mode=True)
        self.assertIn("Você é o Adaptador.", self.enviados[0]["system"])
        self.assertIn("JSON", self.enviados[0]["system"])

    def test_resposta_vazia_ou_cortada_vira_erro(self):
        with self.assertRaises(RuntimeError):
            self._gerar([_resposta(texto="")])
        with self.assertRaises(RuntimeError):
            self._gerar([_resposta(parada="max_tokens")])

    def test_limite_de_taxa_tenta_de_novo(self):
        erro = urllib.error.HTTPError("u", 429, "limite", {}, None)
        r = self._gerar([erro, _resposta()])
        self.assertEqual(len(self.enviados), 2)
        self.assertEqual(r.text, '{"ok": true}')

    def test_sem_chave_falha_com_mensagem(self):
        os.environ["ANTHROPIC_API_KEY"] = ""
        with self.assertRaises(RuntimeError):
            L.AnthropicLLMProvider().generate("x")


class TestModeloPorAgente(unittest.TestCase):
    def setUp(self):
        limpo = {k: v for k, v in os.environ.items() if not k.startswith(("IRIS_LLM", "RAG_LLM"))}
        self._env = mock.patch.dict(os.environ, limpo, clear=True)
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_variavel_do_agente_escolhe_provedor_e_modelo(self):
        os.environ["IRIS_LLM_PROVIDER"] = "ollama"
        os.environ["IRIS_LLM_PROVIDER_ADAPTADOR"] = "anthropic"
        os.environ["IRIS_LLM_MODEL_ADAPTADOR"] = "claude-haiku-5-5"
        c = L.get_llm_client(agente="adaptador")
        self.assertEqual(c.provider_name, "anthropic")
        self.assertIsInstance(c._primary, L.AnthropicLLMProvider)
        self.assertEqual(c._primary.model, "claude-haiku-5-5")

    def test_sem_variavel_do_agente_vale_o_geral(self):
        os.environ["IRIS_LLM_PROVIDER"] = "ollama"
        c = L.get_llm_client(agente="extrator")
        self.assertEqual(c.provider_name, "ollama")

    def test_adaptador_vai_para_o_haiku_quando_ha_chave(self):
        os.environ["IRIS_LLM_PROVIDER"] = "ollama"
        os.environ["ANTHROPIC_API_KEY"] = "chave-de-teste"
        self.assertEqual(L.get_llm_client(agente="adaptador").provider_name, "anthropic")
        self.assertEqual(L.get_llm_client(agente="extrator").provider_name, "ollama")

    def test_sem_chave_o_adaptador_fica_no_geral(self):
        os.environ["IRIS_LLM_PROVIDER"] = "ollama"
        os.environ["ANTHROPIC_API_KEY"] = ""
        with mock.patch.object(L, "get_settings", return_value=mock.Mock(anthropic_api_key="", llm_provider="ollama",
                                                                          ollama_url="http://127.0.0.1:11434", groq_api_key="")):
            self.assertEqual(L.get_llm_client(agente="adaptador").provider_name, "ollama")

    def test_variavel_do_agente_vence_o_padrao(self):
        os.environ["ANTHROPIC_API_KEY"] = "chave-de-teste"
        os.environ["IRIS_LLM_PROVIDER_ADAPTADOR"] = "ollama"
        self.assertEqual(L.get_llm_client(agente="adaptador").provider_name, "ollama")

    def test_esforco_por_agente(self):
        os.environ["ANTHROPIC_API_KEY"] = "chave-de-teste"
        os.environ["IRIS_ANTHROPIC_ESFORCO_ESTRATEGISTA"] = "medium"
        os.environ["IRIS_LLM_PROVIDER_ESTRATEGISTA"] = "anthropic"
        self.assertEqual(L.get_llm_client(agente="estrategista")._primary.esforco, "medium")
        self.assertEqual(L.get_llm_client(agente="adaptador")._primary.esforco, "low")

    def test_agente_desconhecido_falha(self):
        with self.assertRaises(ValueError):
            L.get_llm_client(agente="revisor")

    def test_adaptador_usa_o_cliente_do_seu_agente(self):
        os.environ["IRIS_LLM_PROVIDER_ADAPTADOR"] = "extractive"
        from iris.agents.adapter_agent import AdapterAgent
        self.assertEqual(AdapterAgent().llm_client.provider_name, "extractive")


if __name__ == "__main__":
    unittest.main()
