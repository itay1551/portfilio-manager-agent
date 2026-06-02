"""Shared pytest configuration: source paths for unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for rel in (
    "orchestrator/src",
    "tools/guidelines/src",
    "tools/value_at_risk/src",
):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)
