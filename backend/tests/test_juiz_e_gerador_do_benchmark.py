"""Juiz do RAG nos modelos atuais da Anthropic e separação entre quem escreve e quem julga no Benchmark Escolar.

Nenhuma chamada externa: a rede é trocada por um objeto que guarda o corpo do pedido."""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
for p in (str(SRC_DIR), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris import config
from iris.eval import rag_escolar_benchmark as bench
from iris.eval import sonnet_judge

APOSENTADOS = ("claude-sonnet-4-5-20250929", "claude-sonnet-4-20250514")


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _corpo_enviado(modelo: str) -> dict:
    """Chama o juiz com a rede trocada e devolve o corpo JSON do pedido que sairia."""
    pedidos = []

    def falso_urlopen(req, timeout=0):  # noqa: ARG001
        pedidos.append(json.loads(req.data.decode("utf-8")))
        return _Resposta(json.dumps({"model": modelo, "content": [{"type": "text", "text": "{}"}], "usage": {}}).encode())

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "chave-de-teste"}), \
            patch.object(sonnet_judge.urllib.request, "urlopen", falso_urlopen):
        sonnet_judge.chamar_claude_sonnet_api(modelo, "sistema de teste", "pergunta de teste")
    return pedidos[0]


class TestModeloPadraoDoJuiz(unittest.TestCase):
    def test_padrao_e_reserva_sem_modelo_aposentado(self) -> None:
        self.assertNotIn(config.JUIZ_MODELO_PADRAO, APOSENTADOS)
        self.assertEqual(config.IrisSettings().judge_model, config.JUIZ_MODELO_PADRAO)
        self.assertEqual(sonnet_judge.MODELOS_SONNET_FALLBACK[0], config.JUIZ_MODELO_PADRAO)
        for modelo in sonnet_judge.MODELOS_SONNET_FALLBACK:
            self.assertNotIn(modelo, APOSENTADOS)

    def test_exemplo_de_ambiente_sem_modelo_aposentado(self) -> None:
        exemplo = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        for modelo in APOSENTADOS:
            self.assertNotIn(modelo, exemplo)
        self.assertIn(f"IRIS_JUDGE_MODEL={config.JUIZ_MODELO_PADRAO}", exemplo)
        self.assertIn("IRIS_GENERATOR_MODEL=", exemplo)


class TestJuizNosModelosQuePensam(unittest.TestCase):
    def test_modelo_novo_vai_sem_temperature_e_com_limite_maior(self) -> None:
        for modelo in ("claude-sonnet-5-5", "claude-haiku-5-5"):
            corpo = _corpo_enviado(modelo)
            self.assertNotIn("temperature", corpo, modelo)
            self.assertEqual(corpo["max_tokens"], sonnet_judge.MAX_TOKENS_JUIZ_QUE_PENSA, modelo)

    def test_modelo_anterior_continua_com_temperature(self) -> None:
        corpo = _corpo_enviado("claude-sonnet-4-6")
        self.assertIn("temperature", corpo)
        self.assertEqual(corpo["max_tokens"], 2048)


class TestGeradorDoBenchmarkNaoEOJuiz(unittest.TestCase):
    """Com chave, a bateria escrevia as respostas com o modelo do juiz. Agora o gerador só recebe um modelo quando
    IRIS_GENERATOR_MODEL está definida; sem ela vale o padrão do gerador, o mesmo do produto."""

    def _modelo_visto_pelo_gerador(self, gerador: str) -> str | None:
        visto: dict[str, str | None] = {}

        def falso_responder(**_):
            visto["provedor"] = os.environ.get("RAG_LLM")
            visto["modelo"] = os.environ.get("RAG_LLM_MODELO")
            return {"resposta": "ok", "llm": "anthropic:teste", "trechos_entregues": [], "fontes": []}

        ambiente = {"ANTHROPIC_API_KEY": "chave-de-teste", "IRIS_JUDGE_MODEL": "claude-sonnet-5-5",
                    "IRIS_GENERATOR_MODEL": gerador, "RAG_LLM": "ollama", "RAG_LLM_MODELO": "llama3.1:8b"}
        with patch.dict(os.environ, ambiente), patch.object(bench.rag_bridge, "responder_fundamentado", falso_responder):
            bench._executar_geracao_segura("pergunta", "bm25", 5, None)
            self.assertEqual(os.environ.get("RAG_LLM_MODELO"), "llama3.1:8b")   # o ambiente volta ao que era
        self.assertEqual(visto["provedor"], "anthropic")
        return visto["modelo"]

    def test_sem_variavel_o_gerador_nao_recebe_o_modelo_do_juiz(self) -> None:
        self.assertIsNone(self._modelo_visto_pelo_gerador(""))

    def test_com_variavel_o_gerador_recebe_o_modelo_pedido(self) -> None:
        self.assertEqual(self._modelo_visto_pelo_gerador("claude-haiku-5-5"), "claude-haiku-5-5")


if __name__ == "__main__":
    unittest.main()


class TestRegistroDoJuiz(unittest.TestCase):
    """Issue #108, parte 1: todo julgamento registra modelo, esforço, temperatura, limite e respostas por chamada."""

    def _julgar(self, modelo: str, n_juizes: int = 1) -> dict:
        from iris.eval.sonnet_judge import julgar_resposta_sonnet

        def falso(mod, sistema, prompt, temp):
            texto = '{"responde": "sim", "motivo_responde": "ok", "frases": []}'
            return texto, {"modelo": mod + "-respondeu", "input_tokens": 10, "output_tokens": 5}

        return julgar_resposta_sonnet("Pergunta?", [{"texto": "trecho", "titulo": "Doc"}], "Resposta curta.",
                                      modelo=modelo, n_juizes=n_juizes, usar_cache=False, chamar_api_fn=falso)

    def test_registro_completo_em_modelo_que_pensa(self) -> None:
        r = self._julgar("claude-sonnet-5-5")["registro_juiz"]
        self.assertEqual(r["modelo_pedido"], "claude-sonnet-5-5")
        self.assertEqual(r["modelo_efetivo"], "claude-sonnet-5-5-respondeu")
        self.assertEqual(r["respostas_por_chamada"], 1)
        self.assertEqual(r["temperatura"], {"A": None})
        self.assertGreater(r["max_tokens"], 2048)
        self.assertIn("esforco", r)
        self.assertEqual(r["regra"], "regra_juiz_respostas_v2.md")
        self.assertTrue(r["regra_sha256"])

    def test_dois_juizes_com_temperaturas_diferentes_em_modelo_que_nao_pensa(self) -> None:
        r = self._julgar("claude-sonnet-4-6", n_juizes=2)["registro_juiz"]
        self.assertEqual(r["temperatura"], {"A": 0.0, "B": 0.15})
        self.assertEqual(r["max_tokens"], 2048)
        self.assertEqual(r["chamadas"], 2)
