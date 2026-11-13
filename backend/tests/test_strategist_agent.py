"""Testes do Agente Estrategista RAG (História 2.1.1 / Issue #16).

Os testes com resposta do modelo usam um cliente falso; a busca é a real por palavra (BM25), sem
banco e sem LLM, ou uma busca montada à mão quando o caso exige trechos controlados.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Garante que `backend/src` esteja no sys.path mesmo quando rodado via `python3 -m unittest`
BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pydantic import ValidationError

from iris.agents.strategist_agent import StrategistAgent
from iris.core.llm_client import LLMResponse
from iris.rag import garantir_chunks_locais, obter_trechos_base
from iris.schemas.adaptation import AdaptationRequest
from iris.schemas.curriculum import CurriculumInvariants
from iris.schemas.strategy import StrategyRequest

UM = "carac_um"
DOIS = "carac_dois"


class ClienteFalso:
    """Cliente de LLM que devolve um texto fixo ou levanta erro, e guarda os prompts recebidos."""

    def __init__(self, texto: str = "", erro: Exception | None = None, provider_name: str = "ollama") -> None:
        self.texto = texto
        self.erro = erro
        self.provider_name = provider_name
        self.prompts: list[str] = []

    def generate(self, prompt, temperature=0.0, max_tokens=700, system_prompt=None, json_mode=False):
        self.prompts.append(prompt)
        if self.erro:
            raise self.erro
        return LLMResponse(text=self.texto, provider="ollama", model="falso", prompt_tokens=100, completion_tokens=50)


def _trecho(cid: str) -> dict:
    return {"chunk_id": cid, "doc": f"doc_{cid}", "titulo": f"Título {cid}", "pagina": "3",
            "url": f"https://exemplo.org/{cid}", "nao_usar_para": [], "nota_uso": "", "trecho": f"Texto integral de {cid}."}


def _busca(id_carac: str, barreira: str, chunk_ids: list[str]) -> dict:
    return {
        "id_caracteristica": id_carac,
        "nome_caracteristica": f"Nome de {id_carac}",
        "barreira_rag_associada": barreira,
        "nivel_selecionado": 2,
        "diretriz_andaime": {"objetivo_andaime": "Objetivo.", "acoes_permitidas": ["Ação A", "Ação B"],
                             "restricoes_escopo": ["Restrição R"]},
        "metodo_solicitado": "bm25",
        "metodo_efetivo": "bm25",
        "fallback_aplicado": False,
        "trechos_rag": [_trecho(c) for c in chunk_ids],
    }


def _agente_com_buscas(cliente: ClienteFalso, buscas: dict[str, dict], barreiras: dict[str, set[str]]):
    """Agente cuja busca devolve as buscas dadas e cujo mapa de barreiras é o informado."""
    agente = StrategistAgent(llm_client=cliente)
    agente._barreiras_por_trecho = barreiras
    alvo = patch(
        "iris.agents.strategist_agent.buscar_por_caracteristica_atomica",
        side_effect=lambda id_caracteristica, **_: json.loads(json.dumps(buscas[id_caracteristica])),
    )
    return agente, alvo


BUSCAS = {UM: _busca(UM, "memoria_trabalho", ["a", "b"]), DOIS: _busca(DOIS, "sobrecarga_visual", ["c"])}
BARREIRAS = {"a": {"memoria_trabalho"}, "b": {"memoria_trabalho"}, "c": {"sobrecarga_visual"}}


class TestFiltroEstrito(unittest.TestCase):
    def test_uma_caracteristica_so_traz_trechos_da_sua_barreira(self) -> None:
        garantir_chunks_locais()
        barreiras = {c["chunk_id"]: set(c.get("barreiras") or []) for c in obter_trechos_base()}
        agente = StrategistAgent(llm_client=ClienteFalso(provider_name="extractive"))
        r = agente.strategize(StrategyRequest(caracteristicas=["atencao_sustentada_textos_longos"], metodo="bm25"))
        self.assertEqual(r.trechos_fora_do_filtro, [])
        self.assertEqual(len(r.fontes), 5)
        for f in r.fontes:
            self.assertEqual(f.caracteristicas, ["atencao_sustentada_textos_longos"])
            self.assertIn("leitura_texto_longo", barreiras[f.chunk_id])

    def test_trecho_sem_a_barreira_e_descartado_antes_do_prompt(self) -> None:
        cliente = ClienteFalso(json.dumps({"intervencoes": [{"id_caracteristica": UM, "texto": "Dividir o enunciado em etapas curtas [T1]"}]}))
        barreiras = {**BARREIRAS, "b": {"atencao_sustentada"}}
        agente, alvo = _agente_com_buscas(cliente, BUSCAS, barreiras)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM]))
        self.assertEqual(r.trechos_fora_do_filtro, ["b"])
        self.assertEqual([f.chunk_id for f in r.fontes], ["a"])
        self.assertNotIn("Texto integral de b.", cliente.prompts[0])


class TestConferenciaDaDiretiva(unittest.TestCase):
    def test_so_aprova_intervencao_com_citacao_valida_da_propria_caracteristica(self) -> None:
        propostas = [
            {"id_caracteristica": UM, "texto": "Dividir o enunciado em etapas numeradas [T1][T2]"},
            {"id_caracteristica": DOIS, "texto": "Reduzir elementos visuais concorrentes na página [T3]"},
            {"id_caracteristica": "carac_tres", "texto": "Oferecer tempo adicional para a prova [T1]"},
            {"id_caracteristica": UM, "texto": "Usar lista de verificação ao lado da questão [T9]"},
            {"id_caracteristica": UM, "texto": "Destacar os elementos da figura em cores [T3]"},
            {"id_caracteristica": DOIS, "texto": "Separar o texto de apoio em blocos curtos"},
        ]
        agente, alvo = _agente_com_buscas(ClienteFalso(json.dumps({"intervencoes": propostas})), BUSCAS, BARREIRAS)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM, DOIS]))
        self.assertFalse(r.telemetry.used_fallback)
        self.assertEqual([(i.id_caracteristica, i.citacoes) for i in r.intervencoes], [(UM, ["T1", "T2"]), (DOIS, ["T3"])])
        self.assertEqual(
            [d["motivo"] for d in r.intervencoes_descartadas],
            ["caracteristica_nao_ativada", "citacao_inexistente", "citacao_de_outra_caracteristica", "sem_citacao"],
        )
        self.assertEqual(r.telemetry.n_intervencoes_propostas, 6)
        self.assertEqual(r.telemetry.n_intervencoes_aprovadas, 2)
        self.assertEqual(
            r.diretiva,
            f"Para {UM}: Dividir o enunciado em etapas numeradas [T1][T2]\n"
            f"Para {DOIS}: Reduzir elementos visuais concorrentes na página [T3]",
        )

    def test_fontes_nao_levam_o_texto_do_trecho(self) -> None:
        agente, alvo = _agente_com_buscas(ClienteFalso(provider_name="extractive"), BUSCAS, BARREIRAS)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM]))
        self.assertNotIn("Texto integral", r.model_dump_json())
        self.assertEqual(r.fontes[0].referencia, "Título a, p. 3. Disponível em: https://exemplo.org/a")

    def test_invariantes_e_enunciado_entram_no_prompt(self) -> None:
        cliente = ClienteFalso(json.dumps({"intervencoes": [{"id_caracteristica": UM, "texto": "Dividir o enunciado em etapas curtas [T1]"}]}))
        agente, alvo = _agente_com_buscas(cliente, BUSCAS, BARREIRAS)
        inv = CurriculumInvariants(conceitos_obrigatorios=["fração equivalente"], verbo_comando_bncc="calcular",
                                   operacao_cognitiva="aplicação")
        with alvo:
            agente.strategize(StrategyRequest(caracteristicas=[UM], invariantes=inv, enunciado="Calcule 2/4 + 1/4."))
        self.assertIn("- fração equivalente", cliente.prompts[0])
        self.assertIn("Calcule 2/4 + 1/4.", cliente.prompts[0])
        self.assertIn("[T1] Título a", cliente.prompts[0])


class TestLimitesDaDiretiva(unittest.TestCase):
    """Regras acrescentadas depois da primeira medição com modelo real (cópia literal e excesso de itens)."""

    def test_texto_longo_copia_e_quarta_intervencao_sao_descartados(self) -> None:
        buscas = {UM: _busca(UM, "memoria_trabalho", ["a"])}
        buscas[UM]["trechos_rag"][0]["trecho"] = (
            "Oferecer indicações explícitas para cada etapa em qualquer processo sequencial e apresentar métodos variados."
        )
        longo = " ".join(["palavra"] * 41) + " [T1]"
        copia = "Oferecer indicações explícitas para cada etapa em qualquer processo sequencial e apresentar [T1]"
        validas = [f"Numerar as etapas da questão número {n} [T1]" for n in range(1, 5)]
        propostas = [{"id_caracteristica": UM, "texto": t} for t in [longo, copia, *validas]]
        agente, alvo = _agente_com_buscas(ClienteFalso(json.dumps({"intervencoes": propostas})), buscas, BARREIRAS)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM]))
        self.assertEqual(len(r.intervencoes), 3)
        self.assertEqual(
            [d["motivo"] for d in r.intervencoes_descartadas],
            ["texto_longo", "copia_do_trecho", "excede_limite_por_caracteristica"],
        )

    def test_resposta_cortada_aproveita_as_intervencoes_completas(self) -> None:
        completo = json.dumps({"intervencoes": [
            {"id_caracteristica": UM, "texto": "Dividir o enunciado em etapas numeradas [T1]"},
            {"id_caracteristica": UM, "texto": "Usar lista de verificação ao lado da questão [T2]"},
        ]}, ensure_ascii=False)
        cortado = completo[:-2] + ', {"id_caracteristica": "carac_um", "texto": "Oferecer indica'
        agente, alvo = _agente_com_buscas(ClienteFalso(cortado), BUSCAS, BARREIRAS)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM]))
        self.assertFalse(r.telemetry.used_fallback)
        self.assertTrue(r.telemetry.json_recuperado)
        self.assertFalse(r.telemetry.json_valido_direto)
        self.assertEqual([i.citacoes for i in r.intervencoes], [["T1"], ["T2"]])

    def test_limite_de_tokens_cresce_com_as_caracteristicas(self) -> None:
        vistos: list[int] = []
        cliente = ClienteFalso(json.dumps({"intervencoes": []}))
        original = cliente.generate
        cliente.generate = lambda prompt, max_tokens=0, **kw: (vistos.append(max_tokens), original(prompt, **kw))[1]
        agente, alvo = _agente_com_buscas(cliente, BUSCAS, BARREIRAS)
        with alvo:
            agente.strategize(StrategyRequest(caracteristicas=[UM]))
            agente.strategize(StrategyRequest(caracteristicas=[UM, DOIS]))
        self.assertEqual(vistos, [350, 700])


class TestDiretivaDeReserva(unittest.TestCase):
    def _reserva(self, cliente: ClienteFalso, motivo: str) -> None:
        agente, alvo = _agente_com_buscas(cliente, BUSCAS, BARREIRAS)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM, DOIS], nivel=3))
        self.assertTrue(r.telemetry.used_fallback)
        self.assertEqual(r.telemetry.motivo_fallback, motivo)
        self.assertEqual([i.origem for i in r.intervencoes], ["catalogo", "catalogo"])
        self.assertEqual([i.citacoes for i in r.intervencoes], [["T1", "T2"], ["T3"]])
        self.assertIn(f"Para {UM}: Ações do catálogo para o nível 3: Ação A; Ação B. Evidências recuperadas: [T1][T2]", r.diretiva)

    def test_provedor_sem_modelo(self) -> None:
        self._reserva(ClienteFalso(provider_name="extractive"), "provedor_sem_modelo")

    def test_falha_do_modelo(self) -> None:
        self._reserva(ClienteFalso(erro=TimeoutError("sem resposta")), "falha_llm:TimeoutError")

    def test_json_invalido(self) -> None:
        self._reserva(ClienteFalso("Aqui estão as intervenções sugeridas."), "falha_llm:JSONDecodeError")

    def test_nenhuma_intervencao_aprovada(self) -> None:
        texto = json.dumps({"intervencoes": [{"id_caracteristica": UM, "texto": "Sem citação nenhuma aqui"}]})
        self._reserva(ClienteFalso(texto), "nenhuma_intervencao_aprovada")

    def test_sem_evidencia_nao_ha_diretiva(self) -> None:
        buscas = {UM: _busca(UM, "memoria_trabalho", []), DOIS: _busca(DOIS, "sobrecarga_visual", ["c"])}
        cliente = ClienteFalso(json.dumps({"intervencoes": [{"id_caracteristica": DOIS, "texto": "Reduzir elementos visuais da página [T1]"}]}))
        agente, alvo = _agente_com_buscas(cliente, buscas, BARREIRAS)
        with alvo:
            parcial = agente.strategize(StrategyRequest(caracteristicas=[UM, DOIS]))
            nada = agente.strategize(StrategyRequest(caracteristicas=[UM]))
        self.assertEqual(parcial.caracteristicas_sem_evidencia, [UM])
        self.assertEqual([i.id_caracteristica for i in parcial.intervencoes], [DOIS])
        self.assertEqual(nada.diretiva, "")
        self.assertEqual(nada.telemetry.motivo_fallback, "sem_evidencia")
        self.assertEqual(len(cliente.prompts), 1)


class TestContrato(unittest.TestCase):
    def test_caracteristica_repetida_ou_lista_vazia_sao_recusadas(self) -> None:
        with self.assertRaises(ValidationError):
            StrategyRequest(caracteristicas=[UM, UM])
        with self.assertRaises(ValidationError):
            StrategyRequest(caracteristicas=[])

    def test_diretiva_entra_no_adaptador(self) -> None:
        agente, alvo = _agente_com_buscas(ClienteFalso(provider_name="extractive"), BUSCAS, BARREIRAS)
        with alvo:
            r = agente.strategize(StrategyRequest(caracteristicas=[UM]))
        inv = CurriculumInvariants(conceitos_obrigatorios=["fração"], verbo_comando_bncc="calcular", operacao_cognitiva="aplicação")
        req = AdaptationRequest(enunciado="Calcule a soma das frações 2/4 e 1/4.", id_caracteristica=UM,
                                invariantes=inv, diretiva_psicopedagogica=r.diretiva)
        self.assertTrue(req.diretiva_psicopedagogica.startswith(f"Para {UM}:"))


if __name__ == "__main__":
    unittest.main()
