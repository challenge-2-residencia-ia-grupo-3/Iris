"""Testes unitários da História 4.2.1 (Issue #39 — Schema e Catálogo de Características).

Verifica:
1. Carregamento e validação do catálogo oficial `rag/catalogs/tdah_caracteristicas_funcionais.json`.
2. Integridade referencial: todos os `doc_id` citados no catálogo existem em `rag/iris-rag/fontes.json`
   e todas as `barreira_rag_associada` existem no banco vetorial do RAG.
3. Rejeição estrita de catálogos sem referências bibliográficas ou com campos extras (`extra='forbid'`).
4. Extensibilidade dinâmica para novos perfis (ex.: TEA, Dislexia) sem alterar código-fonte.
5. Integração ponta a ponta entre `id_caracteristica` (#39) e a busca filtrada no RAG (`buscar_por_caracteristica_atomica`).
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris.config import CATALOGS_DIR
from iris.rag import (
    buscar_por_caracteristica_atomica,
    carregar_catalogo_fontes,
    listar_barreiras_rag,
)
from iris.schemas.catalog import (
    BARREIRAS_RAG_VALIDAS,
    CatalogValidationError,
    CharacteristicCatalog,
    get_characteristic_by_id,
    load_all_catalogs,
    load_catalog_file,
)


class TestCharacteristicCatalogSchema(unittest.TestCase):
    """Valida todos os critérios de aceite BDD da Issue #39."""

    def test_official_tdah_catalog_loads_and_matches_rag_sources(self) -> None:
        """O catálogo oficial de TDAH deve carregar sem erros e referenciar documentos reais do RAG."""
        tdah_path = CATALOGS_DIR / "tdah_caracteristicas_funcionais.json"
        self.assertTrue(tdah_path.exists(), "Catálogo oficial de TDAH deve existir em rag/catalogs/")

        catalog = load_catalog_file(tdah_path)
        self.assertEqual(catalog.id_catalogo, "tdah_funcoes_executivas_v1")
        self.assertGreaterEqual(len(catalog.caracteristicas), 7)

        # Verifica que todas as 6 barreiras do RAG estão cobertas pelo catálogo
        barreiras_cobertas = {c.barreira_rag_associada for c in catalog.caracteristicas}
        self.assertEqual(barreiras_cobertas, set(BARREIRAS_RAG_VALIDAS))

        barreiras_indexadas = set(listar_barreiras_rag())
        self.assertTrue(barreiras_cobertas.issubset(barreiras_indexadas))

        # Verifica que todos os doc_id citados existem em rag/iris-rag/fontes.json
        fontes = carregar_catalogo_fontes()
        ids_fontes_oficiais = {d["id"] for d in fontes["documentos"]}
        for c in catalog.caracteristicas:
            self.assertGreaterEqual(len(c.referencias_bibliograficas), 1)
            for ref in c.referencias_bibliograficas:
                self.assertIn(
                    ref.doc_id,
                    ids_fontes_oficiais,
                    f"doc_id {ref.doc_id!r} citado em {c.id_caracteristica!r} deve existir em fontes.json",
                )

    def test_rejects_missing_bibliographic_references(self) -> None:
        """Catálogos sem referência bibliográfica válida devem ser rejeitados na validação."""
        tdah_path = CATALOGS_DIR / "tdah_caracteristicas_funcionais.json"
        raw = json.loads(tdah_path.read_text(encoding="utf-8"))
        invalido = copy.deepcopy(raw)
        invalido["caracteristicas"][0]["referencias_bibliograficas"] = []

        with self.assertRaises(CatalogValidationError):
            CharacteristicCatalog.from_dict(invalido)

    def test_rejects_extra_or_clinical_fields(self) -> None:
        """Campos não declarados (como `cid_medico` ou `laudo_exigido`) devem ser rejeitados (`extra='forbid'`)."""
        tdah_path = CATALOGS_DIR / "tdah_caracteristicas_funcionais.json"
        raw = json.loads(tdah_path.read_text(encoding="utf-8"))
        invalido = copy.deepcopy(raw)
        invalido["caracteristicas"][0]["cid_medico"] = "F90.0"

        with self.assertRaises(CatalogValidationError):
            CharacteristicCatalog.from_dict(invalido)

    def test_extensibility_for_new_catalogs_without_code_changes(self) -> None:
        """Novos catálogos (ex.: Dislexia, TEA) adicionados ao diretório devem ser carregados dinamicamente."""
        tdah_path = CATALOGS_DIR / "tdah_caracteristicas_funcionais.json"
        base_data = json.loads(tdah_path.read_text(encoding="utf-8"))

        dislexia_data = copy.deepcopy(base_data)
        dislexia_data["id_catalogo"] = "dislexia_decodificacao_v1"
        dislexia_data["perfil_referencia"] = "Dislexia"
        dislexia_data["titulo"] = "Catálogo de Características Funcionais — Dislexia"
        dislexia_data["caracteristicas"] = [dislexia_data["caracteristicas"][0]]
        dislexia_data["caracteristicas"][0]["id_caracteristica"] = "fluencia_decodificacao_simbolos_graficos"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "tdah.json").write_text(json.dumps(base_data, ensure_ascii=False), encoding="utf-8")
            (tmp_path / "dislexia.json").write_text(json.dumps(dislexia_data, ensure_ascii=False), encoding="utf-8")

            loaded = load_all_catalogs(tmp_path)
            self.assertEqual(set(loaded.keys()), {"tdah_funcoes_executivas_v1", "dislexia_decodificacao_v1"})
            item = get_characteristic_by_id("fluencia_decodificacao_simbolos_graficos", directory=tmp_path)
            self.assertEqual(item.barreira_rag_associada, "memoria_trabalho")

    def test_integration_catalog_characteristic_to_rag_search(self) -> None:
        """A busca por `id_caracteristica` deve retornar a diretriz de nível e os trechos filtrados do RAG."""
        pacote = buscar_por_caracteristica_atomica(
            id_caracteristica="sobrecarga_memoria_trabalho_comandos_multiplos",
            nivel=2,
            pergunta_adicional="questão de ciências com três comandos seguidos",
            metodo="bm25",
            k=3,
        )
        self.assertEqual(pacote["barreira_rag_associada"], "memoria_trabalho")
        self.assertEqual(pacote["nivel_selecionado"], 2)
        self.assertIn("acoes_permitidas", pacote["diretriz_andaime"])
        self.assertEqual(len(pacote["trechos_rag"]), 3)


if __name__ == "__main__":
    unittest.main()
