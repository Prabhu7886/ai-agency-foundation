"""Launch Aegis with the project-local desktop dependency bundle."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ROOT / ".test-deps"

sys.path.insert(0, str(ROOT))
if DEPENDENCIES.is_dir():
    sys.path.insert(0, str(DEPENDENCIES))

runpy.run_path(str(ROOT / "run_aegis.py"), run_name="__main__")
