"""Janela de contexto nas chamadas ao Ollama (Issue #89): `num_ctx` sempre enviado e corte silencioso acusado."""
from __future__ import annotations

import io
import json
import os
import unittest
from unittest import mock

from iris.core import llm_client
from iris.core.llm_client import (
    JANELA_PISO_PADRAO,
    JANELAS_OLLAMA,
    OllamaLLMProvider,
    PromptCortadoError,
    escolher_janela,
    estimar_tokens,
    prompt_foi_cortado,
)


class _ServidorFalso:
    """Substitui `urllib.request.urlopen`: guarda o corpo enviado e devolve a resposta combinada."""

    def __init__(self, tokens_lidos: int | None = None, done_reason: str = "stop") -> None:
        self.tokens_lidos = tokens_lidos
        self.done_reason = done_reason
        self.corpos: list[dict] = []

    def __call__(self, req, timeout=None):  # noqa: ANN001 - assinatura do urlopen
        if req.full_url.endswith("/api/tags"):
            return _Resposta({"models": [{"name": "modelo-falso"}]})
        corpo = json.loads(req.data.decode("utf-8"))
        self.corpos.append(corpo)
        texto = corpo["prompt"] + corpo.get("system", "")
        lidos = self.tokens_lidos if self.tokens_lidos is not None else max(1, len(texto) // 4)
        return _Resposta({"response": "ok", "prompt_eval_count": lidos, "eval_count": 3, "done_reason": self.done_reason})


class _Resposta(io.BytesIO):
    status = 200

    def __init__(self, dados: dict) -> None:
        super().__init__(json.dumps(dados).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _gerar(servidor: _ServidorFalso, prompt: str, **kw):
    with mock.patch.object(llm_client.urllib.request, "urlopen", servidor):
        provedor = OllamaLLMProvider(model="modelo-falso", **kw.pop("provedor", {}))
        return provedor.generate(prompt, **kw)


class TestEscolhaDaJanela(unittest.TestCase):
    def test_prompt_curto_fica_no_piso(self):
        self.assertEqual(escolher_janela("a" * 1000, None, 900), JANELA_PISO_PADRAO)

    def test_janela_sobe_quando_prompt_mais_resposta_nao_cabem_no_piso(self):
        prompt = "a" * 30000  # ~12.000 tokens na estimativa conservadora
        self.assertEqual(escolher_janela(prompt, None, 1500), 16384)

    def test_janela_sempre_cobre_a_estimativa_ate_o_teto_da_escada(self):
        for n in (10, 5_000, 18_000, 35_000, 70_000):
            for max_tokens in (100, 900, 1500):
                janela = escolher_janela("a" * n, "s" * 500, max_tokens)
                self.assertIn(janela, JANELAS_OLLAMA)
                necessario = estimar_tokens("a" * n) + estimar_tokens("s" * 500) + max_tokens
                if necessario <= JANELAS_OLLAMA[-1]:
                    self.assertGreaterEqual(janela, necessario)

    def test_prompt_do_sistema_entra_na_conta(self):
        self.assertEqual(escolher_janela("a" * 10000, None, 900), 8192)
        self.assertEqual(escolher_janela("a" * 10000, "s" * 10000, 900), 16384)

    def test_piso_menor_e_respeitado(self):
        self.assertEqual(escolher_janela("a" * 100, None, 100, piso=4096), 4096)


class TestChamadaEnviaNumCtx(unittest.TestCase):
    def test_toda_chamada_envia_num_ctx(self):
        servidor = _ServidorFalso()
        resposta = _gerar(servidor, "Explique frações.", max_tokens=200)
        self.assertEqual(servidor.corpos[0]["options"]["num_ctx"], JANELA_PISO_PADRAO)
        self.assertEqual(resposta.raw_usage["num_ctx"], JANELA_PISO_PADRAO)
        self.assertEqual(resposta.raw_usage["done_reason"], "stop")

    def test_prompt_longo_envia_janela_maior(self):
        servidor = _ServidorFalso()
        _gerar(servidor, "palavra " * 4000, max_tokens=1500, system_prompt="regra " * 300)
        self.assertEqual(servidor.corpos[0]["options"]["num_ctx"], 16384)

    def test_piso_vem_da_variavel_de_ambiente(self):
        servidor = _ServidorFalso()
        with mock.patch.dict(os.environ, {"OLLAMA_NUM_CTX": "16384"}):
            _gerar(servidor, "Explique frações.", max_tokens=200)
        self.assertEqual(servidor.corpos[0]["options"]["num_ctx"], 16384)

    def test_variavel_invalida_cai_no_padrao(self):
        for ruim in ("abc", "0", "-1", ""):
            servidor = _ServidorFalso()
            with mock.patch.dict(os.environ, {"OLLAMA_NUM_CTX": ruim}):
                _gerar(servidor, "Explique frações.", max_tokens=200)
            self.assertEqual(servidor.corpos[0]["options"]["num_ctx"], JANELA_PISO_PADRAO, ruim)


class TestCorteSilencioso(unittest.TestCase):
    PROMPT = "REGRA-7Q2X: responda apenas com base nos trechos.\n" + "contexto de apoio " * 1200  # ~21.600 caracteres

    def test_corte_vira_erro_explicito(self):
        # 2.050 tokens lidos é o que o Ollama devolve quando descarta o começo de um prompt maior que 4.096.
        with self.assertRaises(PromptCortadoError) as ctx:
            _gerar(_ServidorFalso(tokens_lidos=2050), self.PROMPT, max_tokens=900)
        mensagem = str(ctx.exception)
        self.assertIn("2050", mensagem)
        self.assertNotIn("REGRA-7Q2X", mensagem)  # a mensagem pode ir para log: não repete o prompt
        self.assertNotIn("contexto de apoio", mensagem)

    def test_prompt_lido_inteiro_nao_acusa_corte(self):
        resposta = _gerar(_ServidorFalso(), self.PROMPT, max_tokens=900)
        self.assertEqual(resposta.text, "ok")

    def test_contagem_ausente_nao_acusa_corte(self):
        self.assertFalse(prompt_foi_cortado(self.PROMPT, None, 0))
        self.assertEqual(_gerar(_ServidorFalso(tokens_lidos=0), self.PROMPT, max_tokens=900).text, "ok")

    def test_limiar_do_corte(self):
        texto = "a" * 6000
        self.assertTrue(prompt_foi_cortado(texto, None, 900))    # 6,7 caracteres por token lido: cortado
        self.assertFalse(prompt_foi_cortado(texto, None, 1500))  # 4 caracteres por token: plausível

    def test_medicoes_reais_do_llama31_ficam_do_lado_certo(self):
        # (caracteres enviados, tokens lidos) medidos no Ollama local em 16/11/2026.
        lidos_inteiros = [(4000, 1322), (12000, 3629), (30000, 9128), (4000, 1110), (30000, 8334), (40171, 12842)]
        cortados = [(16171, 2050), (24171, 2050), (40171, 2050)]
        for caracteres, tokens in lidos_inteiros:
            self.assertFalse(prompt_foi_cortado("a" * caracteres, None, tokens), (caracteres, tokens))
            self.assertGreaterEqual(estimar_tokens("a" * caracteres), tokens)  # a estimativa nunca fica abaixo do real
        for caracteres, tokens in cortados:
            self.assertTrue(prompt_foi_cortado("a" * caracteres, None, tokens), (caracteres, tokens))


if __name__ == "__main__":
    unittest.main()
