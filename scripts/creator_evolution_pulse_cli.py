#!/usr/bin/env python3
"""CLI wrapper for headless Creator Evolution Pulse."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creator_evolution_pulse_service import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
