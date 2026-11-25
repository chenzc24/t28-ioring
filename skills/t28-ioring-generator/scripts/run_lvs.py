#!/usr/bin/env python3
"""Run T28 LVS and record the deck scope and verdict."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from io_ring.verification.cell_check import run

if __name__ == "__main__":
    sys.exit(run("lvs"))
