"""Ponte de execução para manter compatibilidade com `tests/api/test_materials.py`."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
SRC_DIR = BACKEND_DIR / "src"

for p in (str(SRC_DIR), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from tests.test_materials import (  # noqa: E402, F401
    TestContentValidationAndService,
    TestMaterialParsersAndValidation,
    TestPiiScrubber,
)

if __name__ == "__main__":
    unittest.main()
