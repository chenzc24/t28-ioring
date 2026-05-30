#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Schematic - T28 Skill Script

Generates schematic SKILL (.il) code from confirmed config JSON.
Uses local imports from io_ring/.

Usage:
    python generate_schematic.py <config.json> <output.il>

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
    from io_ring.validation.json_validator import convert_config_to_list
    from io_ring.layout.process_config import get_template_file_paths
    from io_ring.schematic.generator import SchematicGenerator
    from io_ring.schematic.device_parser import DeviceTemplateManager

    assets_dir = skill_dir / "io_ring"

    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python generate_schematic.py <config.json> <output.il>")
        print("\nArguments:")
        print("  config.json  - Path to confirmed config file")
        print("  output.il    - Path for output schematic SKILL file")
        print("\nExample:")
        print("  python generate_schematic.py io_ring_confirmed.json schematic.il")
        sys.exit(2)

    config_path = sys.argv[1]
    output_path = sys.argv[2]

    # Check input file exists
    if not Path(config_path).exists():
        print(f"[ERROR] Error: Input file not found: {config_path}")
        sys.exit(2)

    try:
        print(f"[>>] Generating schematic SKILL code...")
        print(f"   Input:  {config_path}")
        print(f"   Output: {output_path}")

        config_path_obj = Path(config_path)

        # Resolve confirmed config path (auto-build if needed)
        config_path = resolve_confirmed_config_path(config_path_obj, consume_confirmed_only=True)

        # Get template file paths
        template_file_names = get_template_file_paths()
        # Add backward-compatible fallback names
        template_file_names = list(dict.fromkeys(template_file_names + ["IO_device_info_T28.json", "device_templates.json"]))

        # Template search paths
        possible_paths = []
        for name in template_file_names:
            possible_paths.append(skill_dir / "io_ring" / "schematic" / "devices" / name)
            possible_paths.append(skill_dir / name)
        template_file = next((p for p in possible_paths if p.exists()), None)
        if template_file is None:
            expected = ", ".join(template_file_names)
            raise FileNotFoundError(f"Device template file not found. Expected: {expected}")

        # Load and convert config
        with open(str(config_path), "r", encoding="utf-8") as f:
            config = json.load(f)

        config_list = convert_config_to_list(config)
        if output_path is None:
            output_dir = resolve_output_root()
            output_dir.mkdir(exist_ok=True)
            output_path_obj = output_dir / f"{config_path_obj.stem}_generated.il"
        else:
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            if output_path_obj.suffix.lower() != ".il":
                output_path_obj = output_path_obj.with_suffix(".il")
            # Add timestamp to filename if not already present
            stem = output_path_obj.stem
            if not re.search(r'_\d{8}_\d{6}', stem):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path_obj = output_path_obj.with_name(f"{stem}_{ts}{output_path_obj.suffix}")

        # Generate schematic
        template_manager = DeviceTemplateManager()
        template_manager.load_templates_from_json(str(template_file))
        generator = SchematicGenerator(template_manager)
        generator.generate_schematic(config_list, str(output_path_obj))

        # Statistics (matches original)
        device_instances = [item for item in config_list if isinstance(item, dict) and "device" in item]
        device_count = len(device_instances)
        device_types = sorted({item["device"] for item in device_instances if item.get("device")})

        lines = [f"[OK] Successfully generated schematic file: {output_path_obj}", "[STATS] Statistics:", f"  - Device instance count: {device_count}"]
        if device_types:
            lines.append(f"  - Device types used: {', '.join(device_types)}")
        print("\n".join(lines))
        sys.exit(0)

    except Exception as e:
        print(f"[ERROR] Error during schematic generation: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
