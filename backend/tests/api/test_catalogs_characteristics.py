"""Testes unitários e de API da História 1.2.1 (Issue #8 — Seleção Cirúrgica de Características Funcionais).

Verifica todos os Critérios de Aceitação BDD:
1. Endpoint `GET /api/v1/catalogs/characteristics` retorna o catálogo oficial de barreiras atômicas sem exigir laudo médico.
2. Seleção de 1 ou mais características atômicas registra exclusivamente as marcadas como escopo permitido (`selected_ids`)
   e mantém todas as demais bloqueadas para intervenção (`blocked_ids`).
3. Impede o avanço caso nenhuma característica funcional seja selecionada (`EMPTY_CHARACTERISTIC_SELECTION`).
4. Rejeita campos extras ou clínicos como `cid_medico` ou `laudo_clinico` (`CLINICAL_OR_EXTRA_FIELD_FORBIDDEN`).
5. Rejeita identificadores de características inexistentes (`UNKNOWN_CHARACTERISTIC_ID`).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris.api.routes.catalogs import (
    get_characteristics_catalog_service,
    select_surgical_characteristics_service,
)
from iris.schemas.catalog import CharacteristicSelectionError


class TestSurgicalCharacteristicsSelection(unittest.TestCase):
    """Bateria de testes para os serviços e contratos da História 1.2.1 (Issue #8)."""

    def test_get_characteristics_catalog_returns_official_atomic_items(self) -> None:
        """O serviço de catálogo deve retornar as 10 características atômicas sem exigir laudo médico."""
        data = get_characteristics_catalog_service()
        self.assertEqual(data["id_catalogo"], "tdah_funcoes_executivas_v1")
        self.assertFalse(data["exige_laudo_medico"])
        self.assertEqual(data["total_caracteristicas"], 10)
        self.assertEqual(len(data["caracteristicas"]), 10)
        self.assertIn("memoria_trabalho", data["barreiras_disponiveis"])
        self.assertIn("acao_e_expressao", data["principios_dua_disponiveis"])

    def test_surgical_selection_single_characteristic_isolates_scope(self) -> None:
        """Selecionar apenas 1 característica deve ativar somente ela e bloquear as outras 9."""
        target_id = "sobrecarga_memoria_trabalho_comandos_multiplos"
        result = select_surgical_characteristics_service({"selected_ids": [target_id]})
        dumped = result.model_dump()

        self.assertEqual(dumped["status"], "success")
        self.assertEqual(dumped["total_catalog_characteristics"], 10)
        self.assertEqual(dumped["selected_count"], 1)
        self.assertEqual(dumped["blocked_count"], 9)
        self.assertEqual(dumped["selected_ids"], [target_id])
        self.assertNotIn(target_id, dumped["blocked_ids"])
        self.assertEqual(len(dumped["active_characteristics"]), 1)
        self.assertEqual(dumped["active_characteristics"][0]["id_caracteristica"], target_id)

    def test_surgical_selection_multiple_characteristics_deduplicates_and_blocks_rest(self) -> None:
        """Selecionar múltiplas características deve preservar a ordem, desduplicar e bloquear as restantes."""
        ids = [
            "atencao_sustentada_textos_longos",
            "impulsividade_leitura_superficial_negacoes",
            "atencao_sustentada_textos_longos",  # duplicata intencional
        ]
        result = select_surgical_characteristics_service({"selected_ids": ids})
        dumped = result.model_dump()

        self.assertEqual(dumped["selected_count"], 2)
        self.assertEqual(dumped["blocked_count"], 8)
        self.assertEqual(
            dumped["selected_ids"],
            [
                "atencao_sustentada_textos_longos",
                "impulsividade_leitura_superficial_negacoes",
            ],
        )
        for active_id in dumped["selected_ids"]:
            self.assertNotIn(active_id, dumped["blocked_ids"])

    def test_empty_selection_blocks_advancement(self) -> None:
        """Nenhuma característica selecionada deve lançar EMPTY_CHARACTERISTIC_SELECTION."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            select_surgical_characteristics_service({"selected_ids": []})
        self.assertEqual(ctx.exception.code, "EMPTY_CHARACTERISTIC_SELECTION")
        self.assertEqual(ctx.exception.field, "selected_ids")

    def test_unknown_characteristic_id_rejected(self) -> None:
        """ID de característica inexistente no catálogo deve lançar UNKNOWN_CHARACTERISTIC_ID."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            select_surgical_characteristics_service(
                {"selected_ids": ["caracteristica_inexistente_pacote_fechado"]}
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_CHARACTERISTIC_ID")

    def test_rejects_clinical_or_extra_fields_in_selection_payload(self) -> None:
        """Campos extras como 'cid_medico' ou 'laudo_medico' devem ser estritamente bloqueados."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            select_surgical_characteristics_service(
                {
                    "selected_ids": ["sobrecarga_memoria_trabalho_comandos_multiplos"],
                    "cid_medico": "F90.0",
                }
            )
        self.assertEqual(ctx.exception.code, "CLINICAL_OR_EXTRA_FIELD_FORBIDDEN")
        self.assertEqual(ctx.exception.field, "cid_medico")

    def test_unknown_catalog_id_rejected(self) -> None:
        """Catálogo inexistente deve lançar CATALOG_NOT_FOUND."""
        with self.assertRaises(CharacteristicSelectionError) as ctx:
            get_characteristics_catalog_service(id_catalogo="catalogo_inexistente_v99")
        self.assertEqual(ctx.exception.code, "CATALOG_NOT_FOUND")

    def test_frontend_step2_component_and_session_persistence_contract(self) -> None:
        """Verifica a existência do componente da Etapa 2, bloqueio acessível e persistência em sessão do cliente."""
        step1_component = REPO_ROOT / "frontend" / "src" / "components" / "Step1MaterialIntake.tsx"
        step2_component = REPO_ROOT / "frontend" / "src" / "components" / "Step2FunctionalProfile.tsx"
        catalogs_api = REPO_ROOT / "frontend" / "src" / "services" / "catalogsApi.ts"
        etapa2_page = REPO_ROOT / "frontend" / "src" / "app" / "etapa-2" / "page.tsx"

        self.assertTrue(step1_component.exists(), "Step1MaterialIntake.tsx deve existir no frontend")
        self.assertTrue(step2_component.exists(), "Step2FunctionalProfile.tsx deve existir no frontend")
        self.assertTrue(catalogs_api.exists(), "catalogsApi.ts deve existir no frontend")
        self.assertTrue(etapa2_page.exists(), "etapa-2/page.tsx deve existir no frontend")

        step1_code = step1_component.read_text(encoding="utf-8")
        comp_code = step2_component.read_text(encoding="utf-8")
        api_code = catalogs_api.read_text(encoding="utf-8")

        # Verifica filtros atômicos desacoplados de rótulo clínico, acessibilidade e bloqueio de avanço
        self.assertIn('role="checkbox"', comp_code)
        self.assertIn("aria-checked={isSelected}", comp_code)
        self.assertIn('role="alert"', comp_code)
        self.assertIn("EMPTY_CHARACTERISTIC_SELECTION", comp_code)
        self.assertIn("disabled={selectedCount === 0 || isSubmitting}", comp_code)

        # Verifica consumo do endpoint oficial e persistência do vetor na sessão do cliente
        self.assertIn("/api/v1/catalogs/characteristics", api_code)
        self.assertIn("SURGICAL_VECTOR_STORAGE_KEY", api_code)
        self.assertIn("window.sessionStorage.setItem", api_code)

        # Verifica persistência e restauração do material da Etapa 1 ao clicar em 'Revisar Material'
        self.assertIn("saveStep1StateToSession", step1_code)
        self.assertIn("loadStep1StateFromSession", step1_code)
        self.assertIn("clearStep1StateFromSession", step1_code)
        self.assertIn("loadStep1StateFromSession", comp_code)



if __name__ == "__main__":
    unittest.main()

