"""Gerador do RAG pela API da Anthropic: modelo padrão, parâmetros por família de modelo e reservas.

Nenhum teste chama a API: `urllib.request.urlopen` é trocado por um dublê que guarda o corpo enviado.
"""

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from iris.rag.bridge import carregar_modulos_rag

_, _, gerar = carregar_modulos_rag()


def _resposta(modelo: str, texto: str = "Resposta [T1].", parada: str = "end_turn"):
    corpo = {"model": modelo, "stop_reason": parada, "content": [{"type": "text", "text": texto}],
             "usage": {"input_tokens": 10, "output_tokens": 5}}
    return io.BytesIO(json.dumps(corpo).encode())


def _erro(codigo: int, mensagem: str = ""):
    return urllib.error.HTTPError("https://api.anthropic.com/v1/messages", codigo, mensagem, {}, io.BytesIO(mensagem.encode()))


class TestGeradorAnthropic(unittest.TestCase):
    def setUp(self):
        self.enviados: list[dict] = []
        limpo = {k: v for k, v in os.environ.items() if k not in ("RAG_LLM_MODELO", "CLAUDE_SONNET_MODEL")}
        self._env = mock.patch.dict(os.environ, {**limpo, "ANTHROPIC_API_KEY": "chave-de-teste"}, clear=True)
        self._env.start()
        self.addCleanup(self._env.stop)

    def _chamar(self, respostas):
        fila = list(respostas)

        def urlopen(req, timeout=None):
            self.enviados.append(json.loads(req.data))
            r = fila.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(gerar.urllib.request, "urlopen", urlopen), mock.patch.object(gerar.time, "sleep", lambda s: None):
            return gerar._chamar_anthropic("PERGUNTA: x")

    def test_padrao_e_haiku_no_esforco_baixo_sem_temperatura(self):
        texto, uso = self._chamar([_resposta("claude-haiku-5-5")])
        corpo = self.enviados[0]
        self.assertEqual(corpo["model"], "claude-haiku-5-5")
        self.assertNotIn("temperature", corpo)                    # o modelo recusa `temperature` (erro 400)
        self.assertEqual(corpo["output_config"], {"effort": "low"})
        self.assertGreaterEqual(corpo["max_tokens"], 4000)         # o raciocínio conta como saída
        self.assertEqual(texto, "Resposta [T1].")
        self.assertEqual(uso["modelo"], "claude-haiku-5-5")
        self.assertFalse(uso["cortada"])

    def test_modelo_local_em_rag_llm_modelo_nao_vai_para_a_anthropic(self):
        os.environ["RAG_LLM_MODELO"] = "llama3.1:8b"              # é o que o servidor grava com o Ollama ativo
        self._chamar([_resposta("claude-haiku-5-5")])
        self.assertEqual(self.enviados[0]["model"], "claude-haiku-5-5")

    def test_modelo_claude_pedido_e_respeitado(self):
        os.environ["RAG_LLM_MODELO"] = "claude-sonnet-5-5"
        self._chamar([_resposta("claude-sonnet-5-5")])
        self.assertEqual(self.enviados[0]["model"], "claude-sonnet-5-5")
        self.assertNotIn("temperature", self.enviados[0])

    def test_modelo_legado_mantem_temperatura_zero(self):
        os.environ["RAG_LLM_MODELO"] = "claude-sonnet-4-5-20250929"
        self._chamar([_resposta("claude-sonnet-4-5-20250929")])
        self.assertEqual(self.enviados[0]["temperature"], 0)
        self.assertNotIn("output_config", self.enviados[0])

    def test_modelo_inexistente_cai_na_reserva(self):
        os.environ["RAG_LLM_MODELO"] = "claude-que-nao-existe"
        _, uso = self._chamar([_erro(404), _resposta("claude-sonnet-4-5-20250929")])
        self.assertEqual([c["model"] for c in self.enviados], ["claude-que-nao-existe", "claude-sonnet-4-5-20250929"])
        self.assertEqual(uso["modelo"], "claude-sonnet-4-5-20250929")

    def test_recusa_de_temperatura_refaz_sem_ela(self):
        os.environ["RAG_LLM_MODELO"] = "claude-opus-4-novo"       # reconhecido como legado pelo nome, mas a API recusa
        self._chamar([_erro(400, "`temperature` is deprecated for this model."), _resposta("claude-opus-4-novo")])
        self.assertIn("temperature", self.enviados[0])
        self.assertNotIn("temperature", self.enviados[1])

    def test_resposta_cortada_e_sinalizada(self):
        _, uso = self._chamar([_resposta("claude-haiku-5-5", parada="max_tokens")])
        self.assertTrue(uso["cortada"])

    def test_sem_chave_falha_com_mensagem(self):
        os.environ["ANTHROPIC_API_KEY"] = ""
        with self.assertRaises(RuntimeError):
            gerar._chamar_anthropic("x")


if __name__ == "__main__":
    unittest.main()
