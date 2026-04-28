#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate Intent Graph - T28 Skill Script

Thin CLI wrapper around assets.core.intent_graph.json_validator.

Usage:
    python validate_intent.py <config_file_path>

Exit Codes:
    0 - Validation passed
    1 - Validation failed
    2 - File or JSON error
"""

import sys
from pathlib import Path

# Add io_ring to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

from io_ring.validation.json_validator import main

if __name__ == "__main__":
    main()
