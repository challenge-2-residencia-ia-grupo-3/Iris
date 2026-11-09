"""Testes unitários e de integração da História 4.2.4 (Issue #44).

Valida a estrutura base de `src/iris/`, a configuração stateless e a ponte de
integração com o módulo RAG independentemente do diretório de trabalho (`cwd`).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Garante que `src` esteja no sys.path mesmo quando rodado via `python3 -m unittest`
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import iris
from iris.config import RAG_BASE_DIR, RAG_PACOTE_DIR, get_settings
from iris.main import get_health_status
from iris.rag import (
    buscar_evidencias,
    carregar_catalogo_fontes,
    garantir_chunks_locais,
    listar_barreiras_rag,
    obter_trechos_base,
)


class TestFoundationAndRagBridge(unittest.TestCase):
    """Verifica os critérios de aceite da Issue #44."""

    def test_package_structure_imports(self) -> None:
        """Todos os subpacotes modulares de `src/iris/` devem ser importáveis."""
        import iris.agents
        import iris.api
        import iris.api.routes
        import iris.core
        import iris.parsers
        import iris.rag
        import iris.schemas
        import iris.security

        self.assertEqual(iris.__version__, "0.1.0")
        self.assertTrue(hasattr(iris.rag, "buscar_evidencias"))

    def test_stateless_health_and_settings(self) -> None:
        """A configuração deve assegurar `zero_student_database=True` e caminhos existentes."""
        settings = get_settings()
        self.assertTrue(settings.zero_student_database)
        self.assertTrue(RAG_BASE_DIR.exists())
        self.assertTrue(RAG_PACOTE_DIR.exists())
        self.assertTrue((REPO_ROOT / ".env.example").exists())

        health = get_health_status()
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["zero_student_database"])

    def test_rag_bridge_independent_of_cwd(self) -> None:
        """A busca do RAG via `iris.rag` deve funcionar fora da pasta `rag/iris-rag/pacote`."""
        old_cwd = Path.cwd()
        try:
            # Muda o cwd para a raiz para provar independência de caminhos relativos
            os.chdir(REPO_ROOT)
            chunks_path = garantir_chunks_locais()
            self.assertTrue(chunks_path.exists())

            chunks = obter_trechos_base()
            self.assertGreater(len(chunks), 1000)

            catalogo = carregar_catalogo_fontes()
            self.assertIn("documentos", catalogo)
            self.assertGreaterEqual(len(catalogo["documentos"]), 38)

            barreiras = listar_barreiras_rag()
            self.assertIn("memoria_trabalho", barreiras)
            self.assertIn("atencao_sustentada", barreiras)

            resultados = buscar_evidencias(
                pergunta="aluno esquece enunciado longo com várias etapas",
                metodo="bm25",
                k=3,
                filtro_barreira="memoria_trabalho",
            )
            self.assertEqual(len(resultados), 3)
            self.assertIn("chunk_id", resultados[0])
            self.assertIn("titulo", resultados[0])
            self.assertIn("url", resultados[0])
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()

