#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Layout - T28 Skill Script

Generates layout SKILL (.il) code from confirmed config JSON.
Uses local imports from io_ring/.

Usage:
    python generate_layout.py <config.json> <output.il>

Exit Codes:
    0 - Success
    1 - Tool execution error
    2 - Import/setup error
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add io_ring to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

from io_ring.config import resolve_output_root, resolve_confirmed_config_path


def main():
    from io_ring.layout.visualizer import visualize_layout
    from io_ring.layout.generator import generate_layout_from_json
    from io_ring.validation.json_validator import convert_config_to_list

    assets_dir = skill_dir / "io_ring"

    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python generate_layout.py <config.json> <output.il>")
        print("\nArguments:")
        print("  config.json  - Path to confirmed config file")
        print("  output.il    - Path for output layout SKILL file")
        print("\nExample:")
        print("  python generate_layout.py io_ring_confirmed.json layout.il")
        sys.exit(2)

    config_path = sys.argv[1]
    output_path = sys.argv[2]

    # Check input file exists
    if not Path(config_path).exists():
        print(f"[ERROR] Error: Input file not found: {config_path}")
        sys.exit(2)

    try:
        print(f"[>>] Generating layout SKILL code...")
        print(f"   Input:  {config_path}")
        print(f"   Output: {output_path}")

        config_path_obj = Path(config_path)

        # Resolve confirmed config path (auto-build if needed)
        config_path = resolve_confirmed_config_path(config_path_obj, consume_confirmed_only=True)

        # Ensure output path is .il with timestamp to avoid duplicate files
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        if output_path_obj.suffix.lower() != ".il":
            output_path_obj = output_path_obj.with_suffix(".il")
        # Add timestamp to filename if not already present
        stem = output_path_obj.stem
        if not re.search(r'_\d{8}_\d{6}', stem):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path_obj = output_path_obj.with_name(f"{stem}_{ts}{output_path_obj.suffix}")

        # Load and convert config
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        config_list = convert_config_to_list(config)

        # Generate layout
        generate_layout_from_json(str(config_path), str(output_path_obj))

        # Generate visualization (matches original logic)
        vis_path = output_path_obj.parent / f"{output_path_obj.stem}_visualization.png"
        try:
            visualize_layout(str(output_path_obj), str(vis_path))
            vis_generated = True
        except Exception:
            vis_generated = False

        if vis_generated and Path(vis_path).exists():
            print(f"\n[OK] Successfully generated layout file: {output_path_obj}")
            print(f"[STATS] Layout visualization generated: {vis_path}")
            print("[TIP] Tip: Review visualization image to verify layout arrangement.")
        else:
            print(f"\n[OK] Successfully generated layout file: {output_path_obj}")

        sys.exit(0)

    except Exception as e:
        print(f"[ERROR] Error during layout generation: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
