"""Testes de API e serviços da História 1.1.1 (Issue #4)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Importa as classes de teste para garantir execução direta por caminho específico
from tests.test_materials import (
    TestContentValidationAndService,
    TestMaterialParsersAndValidation,
    TestPiiScrubber,
)

if __name__ == "__main__":
    unittest.main()

