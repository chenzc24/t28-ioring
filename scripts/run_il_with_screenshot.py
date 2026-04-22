#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run IL with Screenshot - T28 Skill Script

Executes SKILL (.il) file in Virtuoso and captures screenshot.
Uses local imports from assets/.

Usage:
    python run_il_with_screenshot.py <il_file> <lib> <cell> [screenshot_path] [view]

Exit Codes:
    0 - Success
    1 - Tool execution error
    2 - Import/setup error
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from time import sleep

# Add assets to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))


def _resolve_output_root() -> Path:
    """Resolve unified output root for generated reports/artifacts.

    Priority:
    1) AMS_OUTPUT_ROOT env var (explicit override)
    2) AMS_IO_AGENT_PATH/output (workspace root hint)
    3) Current working directory output
    4) Legacy skill-relative output
    """
    env_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve(strict=False)

    agent_root = os.environ.get("AMS_IO_AGENT_PATH", "").strip()
    if agent_root:
        return (Path(agent_root).expanduser().resolve(strict=False) / "output")

    cwd_output = Path(os.getcwd()) / "output"
    return cwd_output.resolve(strict=False)


def run_il_file(il_file_path: str, lib: str, cell: str, view: str = "layout", save: bool = False) -> str:
    """Run IL file in Virtuoso.

    Uses load_skill_file() which uploads the .il to the remote EDA server via SSH
    before calling load() in Virtuoso.  This is required when running from Windows
    because Virtuoso (on Linux) cannot access local Windows paths directly.
    """
    from assets.utils.bridge_utils import (
        open_cell_view_by_type,
        ge_open_window,
        ui_redraw,
        rb_exec,
        load_skill_file,
        save_current_cellview,
    )

    ok = open_cell_view_by_type(lib, cell, view=view, view_type=None, mode="w", timeout=30)
    if not ok:
        return f"❌ Error: Failed to open cellView {lib}/{cell}/{view}"

    window_ok = ge_open_window(lib, cell, view=view, view_type=None, mode="a", timeout=30)
    if not window_ok:
        return f"❌ Error: Failed to open window for {lib}/{cell}/{view}"

    ui_redraw(timeout=10)
    sleep(0.5)
    rb_exec("cv = geGetEditCellView()", timeout=10)

    skill_path = Path(il_file_path)
    if not skill_path.exists():
        candidate = _resolve_output_root() / skill_path.name
        if candidate.exists():
            skill_path = candidate
        else:
            return f"❌ Error: File {il_file_path} does not exist"

    if skill_path.suffix.lower() not in [".il", ".skill"]:
        return f"❌ Error: File {skill_path} is not a valid il/skill file"

    # Upload to remote server then load — works for both local and remote Virtuoso.
    ok = load_skill_file(str(skill_path.resolve()), timeout=300)
    if ok:
        if save:
            if save_current_cellview(timeout=30):
                return f"✅ il file {skill_path.name} executed and saved successfully"
            return f"✅ il file {skill_path.name} executed successfully but save failed"
        return f"✅ il file {skill_path.name} executed successfully"

    return f"❌ il file {skill_path.name} execution failed"


def main():
    from assets.utils.bridge_utils import (
        ui_redraw,
        ui_zoom_absolute_scale,
        load_script_and_take_screenshot,
    )

    # Parse arguments
    if len(sys.argv) < 4:
        print("Usage: python run_il_with_screenshot.py <il_file> <lib> <cell> [screenshot_path] [view]")
        print("\nArguments:")
        print("  il_file         - Path to SKILL (.il) file to execute")
        print("  lib             - Virtuoso library name")
        print("  cell            - Virtuoso cell name")
        print("  screenshot_path - Optional: Path for output screenshot (PNG)")
        print("  view            - Optional: 'schematic' or 'layout' (default: layout)")
        print("\nExample:")
        print("  python run_il_with_screenshot.py schematic.il MyLib MyCell output.png schematic")
        sys.exit(2)

    il_file_path = sys.argv[1]
    lib = sys.argv[2]
    cell = sys.argv[3]
    screenshot_path = sys.argv[4] if len(sys.argv) > 4 else None
    view = sys.argv[5] if len(sys.argv) > 5 else "layout"

    # Check input file exists
    if not Path(il_file_path).exists():
        print(f"❌ Error: SKILL file not found")
        print(f"   File: {Path(il_file_path).resolve()}")
        print(f"   Working directory: {os.getcwd()}")
        print(f"   Please check:")
        print(f"     1. File exists at specified path")
        print(f"     2. Use absolute path if relative path fails")
        sys.exit(2)

    print("")
    print("=== Configuration ===")
    print(f"IL file: {Path(il_file_path).resolve()}")
    print(f"Library: {lib}")
    print(f"Cell: {cell}")
    print(f"View: {view}")
    print(f"Screenshot: {screenshot_path if screenshot_path else 'default (screenshots/virtuoso_<timestamp>.png)'}")

    # Resolve screenshot path early for display
    if screenshot_path:
        save_path_obj = Path(screenshot_path).expanduser().resolve(strict=False)
        save_path_obj.parent.mkdir(parents=True, exist_ok=True)
        save_path = str(save_path_obj)
    else:
        save_dir = _resolve_output_root() / "screenshots"
        save_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = str((save_dir / f"virtuoso_{Path(il_file_path).stem}_{stamp}.png").resolve())

    print(f"Resolved screenshot path: {save_path}")
    print("")

    result_dict = {
        "status": "pending",
        "message": "",
        "screenshot_path": None,
        "observations": [],
    }

    try:
        print(f"🔧 Executing SKILL file in Virtuoso...")
        print(f"   File: {il_file_path}")
        print(f"   Library: {lib}")
        print(f"   Cell: {cell}")
        print(f"   View: {view}")
        if screenshot_path:
            print(f"   Screenshot: {screenshot_path}")

        # Run IL file
        run_result = run_il_file(il_file_path=il_file_path, lib=lib, cell=cell, view=view, save=True)
        if not run_result.startswith("✅"):
            result_dict["message"] = run_result
            print(json.dumps(result_dict, ensure_ascii=False, indent=2))
            sys.exit(1)

        # Take screenshot
        ui_redraw(timeout=10)
        ui_zoom_absolute_scale(0.9, timeout=10)
        sleep(2.0)

        if screenshot_path:
            save_path_obj = Path(screenshot_path).expanduser().resolve(strict=False)
            save_path_obj.parent.mkdir(parents=True, exist_ok=True)
            save_path = str(save_path_obj)
        else:
            save_dir = _resolve_output_root() / "screenshots"
            save_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str((save_dir / f"virtuoso_{Path(il_file_path).stem}_{stamp}.png").resolve())

        screenshot_script = str((skill_dir / "assets" / "skill_code" / "screenshot.il").resolve(strict=False))
        if load_script_and_take_screenshot(screenshot_script, save_path, timeout=20):
            result_dict["status"] = "success"
            result_dict["message"] = run_result
            result_dict["screenshot_path"] = save_path
            result_dict["observations"].append(f"Screenshot saved: {save_path}")
        else:
            result_dict["message"] = "❌ Screenshot failed"

        print(json.dumps(result_dict, ensure_ascii=False, indent=2))
        sys.exit(0)

    except Exception as e:
        result_dict["message"] = f"❌ Error occurred while running il file: {type(e).__name__}: {e}"
        print(json.dumps(result_dict, ensure_ascii=False, indent=2))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
