"""Busca de reserva com aviso: só falha de infraestrutura cai na busca por palavras, toda queda é avisada no log,
o modo estrito (IRIS_RAG_ESTRITO=1) transforma a queda em erro, e o servidor avisa ao ligar se a busca por vetores
está indisponível. Sem banco e sem modelo: a busca é substituída por funções de teste."""

import os
import unittest
from unittest import mock

from iris.rag import bridge
from iris.rag.bridge import buscar_evidencias_com_meta, carregar_modulos_rag

_, consultar, gerar = carregar_modulos_rag()
TRECHO = {"posicao": 1, "chunk_id": "doc#1", "doc": "doc", "titulo": "t", "pagina": "1", "secao": "s", "score": 1.0,
          "idioma": "pt", "parte": "A", "tipo_evidencia": "orientacao", "url": "", "nao_usar_para": None,
          "nota_uso": None, "trecho": "Dividir o enunciado em etapas reduz a carga da memória de trabalho."}


def _busca_que_falha_no_denso(erro: BaseException):
    """Substituto de consultar.buscar: o método por vetores levanta `erro`; o bm25 responde."""
    def buscar(pergunta, metodo="hibrido", k=5, **kw):
        if metodo != "bm25":
            raise erro
        return [dict(TRECHO)]
    return buscar


def _ambiente(**extra):
    limpo = {k: v for k, v in os.environ.items() if k != "IRIS_RAG_ESTRITO"}
    return mock.patch.dict(os.environ, {**limpo, **extra}, clear=True)


class TestPonteDaBusca(unittest.TestCase):
    def test_banco_fora_do_ar_cai_no_bm25_com_aviso(self):
        with _ambiente(), mock.patch.object(consultar, "buscar", _busca_que_falha_no_denso(OSError("conexão recusada"))), \
                self.assertLogs("iris.rag.bridge", level="WARNING") as log:
            r = buscar_evidencias_com_meta("Como adaptar?", metodo="hibrido")
        self.assertTrue(r["fallback_aplicado"])
        self.assertEqual(r["metodo_efetivo"], "bm25")
        self.assertIn("OSError", r["fallback_motivo"])
        self.assertIn("modo reduzido", log.output[0])
        self.assertNotIn("conexão recusada", log.output[0])         # a mensagem do erro não vai para o log (#37)

    def test_indice_dessincronizado_cai_na_reserva(self):
        erro = consultar.IndiceDessincronizado("o índice do banco tem trechos que o chunks.jsonl não tem")
        with _ambiente(), mock.patch.object(consultar, "buscar", _busca_que_falha_no_denso(erro)), \
                self.assertLogs("iris.rag.bridge", level="WARNING"):
            r = buscar_evidencias_com_meta("Como adaptar?", metodo="hibrido")
        self.assertTrue(r["fallback_aplicado"])
        self.assertIn("IndiceDessincronizado", r["fallback_motivo"])

    def test_defeito_de_codigo_nao_e_escondido(self):
        with _ambiente(), mock.patch.object(consultar, "buscar", _busca_que_falha_no_denso(ValueError("método desconhecido"))):
            with self.assertRaises(ValueError):
                buscar_evidencias_com_meta("Como adaptar?", metodo="hibrido")

    def test_modo_estrito_transforma_a_queda_em_erro(self):
        with _ambiente(IRIS_RAG_ESTRITO="1"), \
                mock.patch.object(consultar, "buscar", _busca_que_falha_no_denso(OSError("conexão recusada"))):
            with self.assertRaises(OSError):
                buscar_evidencias_com_meta("Como adaptar?", metodo="hibrido")

    def test_erros_de_infraestrutura_incluem_os_esperados(self):
        erros = bridge.erros_de_infraestrutura()
        for tipo in (ImportError, OSError, ConnectionError, TimeoutError):
            self.assertTrue(issubclass(tipo, erros))
        self.assertFalse(issubclass(ValueError, erros))


class TestGerador(unittest.TestCase):
    def _responder(self, erro):
        with mock.patch.object(consultar, "buscar", _busca_que_falha_no_denso(erro)), \
                mock.patch.object(gerar, "gerar", return_value=("resposta", {})):
            return gerar.responder("Como adaptar?", metodo="hibrido")

    def test_queda_aparece_na_resposta_e_no_log(self):
        with _ambiente(), self.assertLogs("iris.rag.gerar", level="WARNING"):
            r = self._responder(OSError("conexão recusada"))
        self.assertEqual(r["metodo"], "bm25")
        self.assertIn("OSError", r["fallback_motivo"])

    def test_sem_queda_o_motivo_e_vazio(self):
        with _ambiente(), mock.patch.object(consultar, "buscar", return_value=[dict(TRECHO)]), \
                mock.patch.object(gerar, "gerar", return_value=("resposta", {})):
            r = gerar.responder("Como adaptar?", metodo="hibrido")
        self.assertIsNone(r["fallback_motivo"])

    def test_modo_estrito_e_defeito_de_codigo_sobem(self):
        with _ambiente(IRIS_RAG_ESTRITO="1"), self.assertRaises(OSError):
            self._responder(OSError("conexão recusada"))
        with _ambiente(), self.assertRaises(ValueError):
            self._responder(ValueError("método desconhecido"))


class TestAvisoAoLigar(unittest.TestCase):
    def test_avisa_quando_so_resta_a_busca_por_palavras(self):
        from iris import main
        saude = {"rag_backend": "pgvector", "available_search_methods": ["bm25"], "vector_db_online": False,
                 "vector_deps_missing": []}
        with mock.patch.object(main, "get_health_status", return_value=saude), \
                self.assertLogs("iris.main", level="WARNING") as log:
            main.avisar_saude_da_busca()
        self.assertIn("banco pgvector fora do ar", log.output[0])

    def test_nao_avisa_com_a_busca_por_vetores_disponivel(self):
        from iris import main
        saude = {"rag_backend": "pgvector", "available_search_methods": ["bm25", "qwen3+rerank50", "hibrido"]}
        with mock.patch.object(main, "get_health_status", return_value=saude), \
                mock.patch("logging.Logger.warning") as aviso:
            main.avisar_saude_da_busca()
        aviso.assert_not_called()


if __name__ == "__main__":
    unittest.main()
