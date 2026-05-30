#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Confirmed Config - T28 Skill Script

Builds confirmed IO ring configuration from intent graph JSON.
Uses local imports from io_ring/.

Usage:
    python build_confirmed_config.py <intent_graph.json> <output_confirmed.json> [--skip-editor]

Exit Codes:
    0 - Success
    1 - Tool execution error
    2 - Import/setup error
"""

import os
import sys
from pathlib import Path

# Add io_ring to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))


def _format_exception(error: Exception) -> str:
    """Format exception with causes (from original runtime_t28.py)."""
    message = f"{type(error).__name__}: {error}"
    causes = []
    current = error.__cause__ or error.__context__
    while current and len(causes) < 3:
        causes.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    if causes:
        message += " | caused by: " + " -> ".join(causes)
    return message


def main():
    from io_ring.layout.confirmed_config import build_confirmed_config_from_io_config

    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python build_confirmed_config.py <intent_graph.json> <output_confirmed.json> [--skip-editor] [--mode draft|confirmation]")
        print("\nArguments:")
        print("  intent_graph.json    - Path to input intent graph JSON file")
        print("  output_confirmed.json - Path for output confirmed config JSON")
        print("  --skip-editor        - Optional: Skip GUI confirmation in CLI mode")
        print("  --mode draft         - Optional: Open in Draft Editor mode (no fillers/pins)")
        print("  --mode confirmation  - Optional: Open in Confirmation Editor mode (default)")
        print("\nExamples:")
        print("  python build_confirmed_config.py io_ring.json io_ring_confirmed.json")
        print("  python build_confirmed_config.py draft.json draft_confirmed.json --mode draft")
        print("  python build_confirmed_config.py io_ring.json io_ring_confirmed.json --skip-editor")
        sys.exit(2)

    intent_graph_path = sys.argv[1]
    confirmed_output_path = sys.argv[2]
    extra_args = sys.argv[3:]
    skip_editor_confirmation = False
    editor_mode = 'confirmation'
    for arg in extra_args:
        if arg == "--skip-editor":
            skip_editor_confirmation = True
        elif arg == "--mode" or arg.startswith("--mode="):
            if arg.startswith("--mode="):
                editor_mode = arg.split("=", 1)[1]
            else:
                # next arg is the mode value
                idx = extra_args.index(arg)
                if idx + 1 < len(extra_args):
                    editor_mode = extra_args[idx + 1]

    # Check input file exists
    if not Path(intent_graph_path).exists():
        print(f"[ERROR] Error: Input file not found")
        print(f"   File: {Path(intent_graph_path).resolve()}")
        print(f"   Please check:")
        print(f"     1. File exists at specified path")
        print(f"     2. Working directory is correct: {os.getcwd()}")
        print(f"     3. Use absolute path if having issues")
        sys.exit(2)

    # Validate output path parent directory exists
    output_parent = Path(confirmed_output_path).parent
    if not output_parent.exists():
        print(f"[WARN]  Warning: Output directory does not exist: {output_parent}")
        print(f"   Will create directory automatically")
        output_parent.mkdir(parents=True, exist_ok=True)

    try:
        print("")
        print("=== Configuration ===")
        print(f"Working directory: {os.getcwd()}")
        print(f"Intent graph: {Path(intent_graph_path).resolve()}")
        print(f"Output: {Path(confirmed_output_path).resolve()}")
        print(f"Process node: T28")
        print(f"Skip editor: {skip_editor_confirmation}")
        print("")

        print("[>>] Building confirmed config...")
        print(f"   Input: {intent_graph_path}")
        print(f"   Output: {confirmed_output_path}")
        print(f"   Process: T28")
        print(f"   Mode: {editor_mode}")

        # Draft mode: use the draft editor session
        if editor_mode == 'draft':
            from io_ring.layout.confirmed_config import build_draft_editor_session
            confirmed_path = build_draft_editor_session(
                draft_json_path=intent_graph_path,
                confirmed_output_path=confirmed_output_path,
                skip_editor_confirmation=skip_editor_confirmation,
            )
        else:
            # Call the core function directly (confirmation mode)
            confirmed_path = build_confirmed_config_from_io_config(
                source_json_path=intent_graph_path,
                confirmed_output_path=confirmed_output_path,
                skip_editor_confirmation=skip_editor_confirmation,
            )

        # Verify output was created
        if Path(confirmed_path).exists():
            print("")
            print("=== Success ===")
            print(f"[OK] Confirmed IO config generated successfully: {Path(confirmed_path).resolve()}")
            file_size = Path(confirmed_path).stat().st_size
            print(f"   File size: {file_size} bytes")
            print("[TIP] This file is ready for downstream layout/schematic generation.")
            sys.exit(0)
        else:
            print("")
            print("[WARN]  Warning: Output file may not have been created")
            print(f"   Expected: {Path(confirmed_path).resolve()}")
            print(f"   Check the output above for any error messages")
            sys.exit(0)

    except FileNotFoundError as e:
        print("")
        print(f"[ERROR] Error: File not found - {e}")
        print(f"   Message: {str(e)}")
        print(f"   This may indicate:")
        print(f"     1. Input file does not exist")
        print(f"     2. Incorrect file path specified")
        print(f"   3. File permissions issue")
        print(f"   Troubleshooting:")
        print(f"     - Verify file path is correct")
        print(f"     - Check if file exists: ls -la '{intent_graph_path}'")
        print(f"     - Use absolute path if relative path fails")
        sys.exit(1)

    except RuntimeError as e:
        print("")
        print(f"[ERROR] Error: Runtime error - {e}")
        print(f"   Message: {str(e)}")
        print(f"   This may indicate:")
        print(f"     1. Configuration validation failure")
        print(f"     2. Missing required dependencies")
        print(f"     3. Device template file not found")
        print(f"     4. JSON parsing error in intent graph")
        print(f"   Troubleshooting:")
        print(f"     - Check intent graph format is correct")
        print(f"     - Verify device info files exist in io_ring/schematic/devices/")
        print(f"     - Check if dependencies are installed")
        sys.exit(1)

    except Exception as e:
        print("")
        print(f"[ERROR] Error during config build - {type(e).__name__}: {e}")
        print(f"   Message: {str(e)}")
        print(f"   Debug information:")
        print(f"     Working directory: {os.getcwd()}")
        print(f"     Python version: {sys.version}")
        print(f"     Intent graph: {Path(intent_graph_path).resolve()}")
        print(f"     Output: {Path(confirmed_output_path).resolve()}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
