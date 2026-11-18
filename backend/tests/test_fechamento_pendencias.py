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


class TestRemovedorNoAtaqueSintetico(unittest.TestCase):
    """Os casos de número do removedor estão em test_removedor_dado_pessoal.py; aqui fica só o que depende do ataque."""

    def test_ataque_sem_controle_apagado_e_sem_vazamento_novo(self) -> None:
        from iris.eval.ataque_pii import executar_ataque_pii

        r = executar_ataque_pii(salvar=False, formatos=())
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


class TestAtaqueEmArquivo(unittest.TestCase):
    def test_docx_e_pdf_passam_pelo_extrator_e_dao_o_mesmo_vazamento_do_texto(self) -> None:
        from iris.eval.ataque_pii import executar_ataque_pii

        r = executar_ataque_pii(salvar=False, formatos=("docx", "pdf"))
        texto = r["por_formato"]["texto"]
        for formato in ("docx", "pdf"):
            f = r["por_formato"][formato]
            self.assertEqual(f["total"], texto["total"], formato)
            self.assertEqual(f["por_tipo"], texto["por_tipo"], formato)
            self.assertEqual(f["prometidos_rotulo_pt"]["vazou"], 0, formato)

    def test_o_arquivo_traz_o_dado_de_verdade(self) -> None:
        from iris.eval.ataque_pii import _texto_extraido

        texto = "Atividade\nAluno: Fulano Ficticio\nQuestão 1: explique."
        for formato in ("docx", "pdf"):
            self.assertIn("Fulano Ficticio", _texto_extraido(formato, texto), formato)


class TestIndiceDoBancoDessincronizado(unittest.TestCase):
    """B13: banco pgvector montado com outra base de trechos. A busca densa explica e quem chama recua para bm25."""

    def test_erro_claro_e_recuo_com_motivo_legivel(self) -> None:
        from iris.rag import bridge

        _, consultar, _ = bridge.carregar_modulos_rag()

        class ModeloFalso:
            def vetor_pergunta(self, _pergunta: str) -> list[float]:
                return [0.0]

        class BancoFalso:
            def buscar_denso(self, _con, _v, _apelido, n, _filtro):
                return [("TRECHO-QUE-NAO-EXISTE#0001", 0.9)][:n]

        with (
            _ambiente_extrativo(),
            patch.object(consultar, "_modelo", lambda _apelido: ModeloFalso()),
            patch.object(consultar, "_pg", lambda: (BancoFalso(), None)),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                consultar._ranking_denso("pergunta", "qwen3", 5, None)
            res = bridge.buscar_evidencias_com_meta("Como dividir um texto longo?", metodo="qwen3", k=3)
        self.assertIn("índice do banco", str(ctx.exception))
        self.assertTrue(res["fallback_aplicado"])
        self.assertEqual(res["metodo_efetivo"], "bm25")
        self.assertIn("reconstrua o índice", res["fallback_motivo"])


class TestTextosDaTela(unittest.TestCase):
    def setUp(self) -> None:
        self.html = PLAYGROUND.read_text(encoding="utf-8")

    def test_dica_da_fidelidade_com_a_meta_do_painel_original(self) -> None:
        # a meta é do painel do grupo e fica; a dúvida sobre a origem do número vai como proposta, não como troca
        self.assertIn("Meta recomendada ≥ 0,80.", self.html)

    def test_aviso_de_rodada_sem_modelo_e_abstencao_explicada(self) -> None:
        self.assertIn("Rodada sem modelo de linguagem.", self.html)
        self.assertIn("function geradorExtrativo(m)", self.html)
        self.assertIn("O gerador sem modelo descarta todo trecho com aviso de uso", self.html)

    def test_recorte_pequeno_marcado_na_segmentacao(self) -> None:
        self.assertIn("const RECORTE_MINIMO = 20;", self.html)
        self.assertIn("poucas questões", self.html)


class TestJulgamentoDoPainelOriginalPreservado(unittest.TestCase):
    """As cores, a meta e as leituras que o painel do grupo já tinha continuam como eram; o que é das Verificações
    de qualidade aparece ao lado, como acréscimo. Cada trecho abaixo é a linha do painel original."""

    ORIGINAIS = (
        "cls: classePct(retorno, 95, 70),",
        "cls: classePct(aderencia, 90, 60),",
        "cls: Number(r.latencia_total_ms || 0) <= 15000 ? 'score-ok' : (Number(r.latencia_total_ms || 0) <= 60000 ? 'score-warn' : 'score-danger'),",
        "Meta recomendada ≥ 0,80.",
        "cls: (abstencao || 0) <= 10 ? 'score-ok' : ((abstencao || 0) <= 40 ? 'score-warn' : 'score-danger'),",
        '<td class="num ${fidCls}">${fidStr}',
        "<div class=\"verdict-num ${classePct(Number(r.taxa_retorno_pct || 0), 95, 70) === 'score-ok' ? 'ok' : 'warn'}\">",
        '<div class="verdict-sub">${escapeHtml(r.aderencia_barreira_pct)}% aderência à barreira</div>',
        "leitura: (abstencao || 0) <= 10 ? 'Dentro do esperado (próximo de 0%)' : 'Alta recusa: revise o prompt ou cobertura dos trechos',",
    )
    ACRESCIMOS = (
        '<span class="tag">por construção</span>',
        "motivoPorConstrucao('taxa_retorno_pct')",
        "RNF-07 (",
        "poucas questões",
        "O gerador sem modelo descarta todo trecho com aviso de uso",
        "ic: textoIc95(r, 'taxa_abstencao_pct'",
    )

    def setUp(self) -> None:
        self.html = PLAYGROUND.read_text(encoding="utf-8")

    def test_regras_do_painel_original_continuam_iguais(self) -> None:
        for trecho in self.ORIGINAIS:
            self.assertIn(trecho, self.html, trecho)

    def test_acrescimos_continuam_ao_lado(self) -> None:
        for trecho in self.ACRESCIMOS:
            self.assertIn(trecho, self.html, trecho)


if __name__ == "__main__":
    unittest.main()
