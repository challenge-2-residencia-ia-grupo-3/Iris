"""Testes das correções do fechamento das pendências (15/11/2026): variedade da busca (A3), modelo único do juiz
(B2), latência como informação (C1), intervalo e recorte pequeno na segmentação (C2), progresso da repetição (C8),
notas de procedência separadas do resultado no portão (C12) e os textos da tela para o gerador sem modelo (B3, B4, B5)."""
from __future__ import annotations

import contextlib
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
REPO_ROOT = BACKEND_DIR.parent
for p in (str(SRC_DIR), str(BACKEND_DIR), str(REPO_ROOT / "rag" / "iris-rag" / "pacote")):
    if p not in sys.path:
        sys.path.insert(0, p)

from iris import config
from iris.eval import rag_escolar_benchmark as bench
from iris.eval import sonnet_judge
from iris.eval.rag_escolar_benchmark import _resumir_grupo_itens, avaliar_portao, comparar_com_linha_de_base

PLAYGROUND = SRC_DIR / "iris" / "static" / "playground.html"


@contextlib.contextmanager
def _ambiente_extrativo():
    antigos = {k: os.environ.get(k) for k in ("RAG_LLM", "ANTHROPIC_API_KEY", "IRIS_JUDGE_MODEL")}
    os.environ["RAG_LLM"] = "extractive"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("IRIS_JUDGE_MODEL", None)
    try:
        yield
    finally:
        for chave, valor in antigos.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor


class TestVariedadeDaBusca(unittest.TestCase):
    def test_conta_conjuntos_e_trechos_distintos(self) -> None:
        itens = [
            {"chunk_ids": ["a", "b"]},
            {"chunk_ids": ["a", "b"]},
            {"chunk_ids": ["b", "a"]},  # outra ordem é outro conjunto devolvido
            {"chunk_ids": ["c"]},
        ]
        r = _resumir_grupo_itens(itens)
        self.assertEqual(r["conjuntos_distintos_trechos"], 3)
        self.assertEqual(r["trechos_distintos"], 3)


class TestModeloDoJuiz(unittest.TestCase):
    def test_um_valor_so_e_e_o_que_vale_em_execucao(self) -> None:
        with _ambiente_extrativo(), patch.object(config, "_parse_dotenv_file", lambda _p: {}):
            em_execucao = config.get_settings().judge_model
        self.assertEqual(em_execucao, config.JUIZ_MODELO_PADRAO)
        self.assertEqual(config.IrisSettings().judge_model, config.JUIZ_MODELO_PADRAO)
        texto = (SRC_DIR / "iris" / "config.py").read_text(encoding="utf-8")
        self.assertEqual(len(set(re.findall(r'"(claude-sonnet[^"]+)"', texto))), 1)
        self.assertNotIn("claude-sonnet", (SRC_DIR / "iris" / "eval" / "rag_escolar_benchmark.py").read_text(encoding="utf-8"))
        self.assertEqual(sonnet_judge.JUIZ_MODELO_PADRAO, config.JUIZ_MODELO_PADRAO)


def _rodada(run_id: str, segundos: float, **extra: object) -> dict:
    base = {
        "run_id": run_id,
        "metodo_efetivo": "bm25",
        "estrategia_query": "contexto_pedagogico",
        "nivel": 2,
        "k": 5,
        "gerar_resposta": True,
        "avaliador_efetivo": "lexico_local",
        "filtros_execucao": {},
        "procedencia": {"commit": "abc1234", "dataset_sha256": "0123456789abcdef"},
        "itens": [
            {"id": f"Q{i}", "n_trechos": 5, "segundos_busca": 0.01, "segundos_total": segundos + (i % 4) * 0.001,
             "llm": "x", "fidelidade_efetiva": 0.5 + (i % 3) * 0.1, "relevancia_efetiva": 0.5, "absteve": False}
            for i in range(30)
        ],
    }
    base.update(extra)
    return base


class TestLatenciaComoInformacao(unittest.TestCase):
    def test_mais_lenta_e_mais_rapida_nao_sao_piorou_nem_melhorou(self) -> None:
        base = _rodada("base", 0.1)
        lenta = comparar_com_linha_de_base(_rodada("lenta", 9.0), base)
        rapida = comparar_com_linha_de_base(_rodada("rapida", 0.001), base)
        ver = lambda c, k: next(m["veredito"] for m in c["metricas"] if m["chave"] == k)  # noqa: E731
        self.assertEqual(ver(lenta, "latencia_total_ms"), "mais_lenta")
        self.assertEqual(ver(rapida, "latencia_total_ms"), "mais_rapida")
        p = avaliar_portao(_rodada("lenta", 9.0), lenta)
        self.assertEqual(p["veredito"], "aprovado")
        self.assertTrue(any("mais lenta" in n for n in p["notas"]))


class TestPortaoSeparaProcedencia(unittest.TestCase):
    def test_sem_hash_da_prova_vira_nota(self) -> None:
        base = _rodada("base", 0.1)
        nova = _rodada("nova", 0.1, procedencia={"commit": "abc1234"})
        comp = comparar_com_linha_de_base(nova, base)
        p = avaliar_portao(nova, comp)
        self.assertTrue(any("hash da prova" in n for n in p["notas"]))
        self.assertFalse(any("hash da prova" in m for m in p["motivos"]))

    def test_todo_veredito_traz_o_campo_notas(self) -> None:
        base = _rodada("base", 0.1)
        for comp, rodada in (
            (None, base),
            (comparar_com_linha_de_base(base, base), base),
            (comparar_com_linha_de_base(_rodada("x", 0.1, filtros_execucao={"disciplina": "X"}), base), base),
        ):
            self.assertIn("notas", avaliar_portao(rodada, comp))


class TestProgressoDaRepeticao(unittest.TestCase):
    def test_a_repeticao_avisa_o_progresso_questao_a_questao(self) -> None:
        passos: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp, _ambiente_extrativo():
            runs = Path(tmp) / "runs.jsonl"
            with patch.object(bench, "PROGRESSO_RAG_ESCOLAR_LOG", Path(tmp) / "p.log"):
                bench.executar_benchmark_rag_escolar(
                    metodo="bm25", k=3, limite=3, caminho_runs=runs, caminho_base=Path(tmp) / "b.json",
                    progresso=lambda _m: None,
                )
                bench.repetir_rodada_rag_escolar(caminho_runs=runs, on_step=passos.append)
        concluidas = [p for p in passos if p.get("etapa") == "Concluída questão"]
        self.assertEqual([p["atual"] for p in concluidas], [1, 2, 3])
        self.assertTrue(all(p["total"] == 3 for p in passos))


def _cpf_com_verificadores(base9: str) -> str:
    """Monta um CPF fictício (começa em 000) com dígitos verificadores válidos, só para o teste."""
    d = [int(c) for c in base9]
    for tamanho in (9, 10):
        d.append(sum(d[i] * (tamanho + 1 - i) for i in range(tamanho)) * 10 % 11 % 10)
    return "".join(map(str, d))


class TestRemovedorDeDadoPessoal(unittest.TestCase):
    def test_cpf_sem_pontuacao_sai_inteiro_e_com_o_marcador_certo(self) -> None:
        from iris.security.pii_scrubber import sanitize_pii

        cpf = _cpf_com_verificadores("000123456")
        self.assertEqual(sanitize_pii(f"CPF: {cpf}"), ("CPF: [CPF]", 1))
        self.assertEqual(sanitize_pii("CPF: 00012345678"), ("CPF: [TELEFONE]", 1))  # verificadores inválidos
        self.assertEqual(sanitize_pii("Celular: 00991234567"), ("Celular: [TELEFONE]", 1))

    def test_numero_longo_do_enunciado_nao_perde_pedaco(self) -> None:
        from iris.security.pii_scrubber import sanitize_pii

        for texto in ("O ISBN 9788535902778 do livro", "Código de barras 7891234567895", "Valor 123.45678901"):
            self.assertEqual(sanitize_pii(texto), (texto, 0), texto)

    def test_intervalo_de_anos_e_conteudo_e_telefone_continua_saindo(self) -> None:
        from iris.security.pii_scrubber import sanitize_pii

        for texto in ("Frei Vicente de Salvador (1564-1633)", "Segunda Guerra Mundial (1939-1945)", "No ano de 2020"):
            self.assertEqual(sanitize_pii(texto), (texto, 0), texto)
        self.assertEqual(sanitize_pii("Telefone da escola 3333-4444"), ("Telefone da escola [TELEFONE]", 1))
        self.assertEqual(sanitize_pii("Tel.: (00) 91234-5678"), ("Tel.: [TELEFONE]", 1))

    def test_nenhuma_das_136_questoes_reais_perde_texto(self) -> None:
        from iris.eval.rag_escolar_benchmark import carregar_questoes_curadas
        from iris.security.pii_scrubber import sanitize_pii

        alteradas = [q.id for q in carregar_questoes_curadas() if sanitize_pii(q.texto_completo)[0] != q.texto_completo]
        self.assertEqual(alteradas, [])

    def test_ataque_sem_controle_apagado_e_sem_vazamento_novo(self) -> None:
        from iris.eval.ataque_pii import executar_ataque_pii

        r = executar_ataque_pii(salvar=False)
        self.assertEqual(r["controles"]["apagou_conteudo"], 0)
        self.assertEqual(r["controles"]["total"], 9)
        self.assertEqual(r["por_tipo"]["cpf_sem_pontuacao"]["vazou"], 0)
        self.assertEqual(r["por_tipo"]["telefone"]["vazou"], 0)
        self.assertEqual(r["prometidos_rotulo_pt"]["vazou"], 0)


class TestTesteDeRecusaAmpliado(unittest.TestCase):
    def test_quarenta_perguntas_metade_de_cada_tipo_e_ids_unicos(self) -> None:
        perguntas = bench.carregar_perguntas_fora_da_base()
        self.assertEqual(len(perguntas), 40)
        self.assertEqual(sum(p["tipo"] == "perto" for p in perguntas), 20)
        self.assertEqual(len({p["id"] for p in perguntas}), 40)

    def test_zero_recusas_nao_da_intervalo_de_largura_zero(self) -> None:
        r = bench._resumir_recusa([{"recusou": False}] * 20)
        self.assertEqual(r["taxa_recusa_pct"], 0.0)
        self.assertEqual(r["ic95"][0], 0.0)
        self.assertGreater(r["ic95"][1], 10.0)


class TestTextosDaTela(unittest.TestCase):
    def setUp(self) -> None:
        self.html = PLAYGROUND.read_text(encoding="utf-8")

    def test_dica_da_fidelidade_sem_meta_sem_origem(self) -> None:
        self.assertNotIn("Meta recomendada", self.html)

    def test_aviso_de_rodada_sem_modelo_e_abstencao_explicada(self) -> None:
        self.assertIn("Rodada sem modelo de linguagem.", self.html)
        self.assertIn("function geradorExtrativo(m)", self.html)
        self.assertIn("abstém-se quando os 5 trechos têm aviso de uso", self.html)

    def test_recorte_pequeno_marcado_na_segmentacao(self) -> None:
        self.assertIn("const RECORTE_MINIMO = 20;", self.html)
        self.assertIn("poucas questões", self.html)


if __name__ == "__main__":
    unittest.main()
