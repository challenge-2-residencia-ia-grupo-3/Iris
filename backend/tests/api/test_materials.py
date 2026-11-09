"""Testes de API e serviços da História 1.1.1 (Issue #4)."""
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

# Importa as classes de teste para garantir execução direta por caminho específico
from tests.test_materials import (
    TestContentValidationAndService,
    TestMaterialParsersAndValidation,
    TestPiiScrubber,
)

if __name__ == "__main__":
    unittest.main()

