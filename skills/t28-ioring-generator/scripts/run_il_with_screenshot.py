#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run IL with Screenshot - T28 Skill Script

Executes SKILL (.il) file in Virtuoso and captures screenshot.
Uses local imports from io_ring/.

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

# Add io_ring to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

from io_ring.config import resolve_output_root


def _verify_cellview(lib: str, cell: str, view: str) -> bool:
    """Verify that the current edit cellView matches the requested lib/cell/view.

    Returns True if cv points to the correct cellView, False otherwise.
    This prevents loading .il scripts into the wrong cell and polluting existing work.
    """
    from io_ring.bridge import rb_exec

    actual_lib = rb_exec('cv~>libName', timeout=10).strip().strip('"')
    actual_cell = rb_exec('cv~>cellName', timeout=10).strip().strip('"')
    actual_view = rb_exec('cv~>viewName', timeout=10).strip().strip('"')
    if actual_lib == lib and actual_cell == cell and actual_view == view:
        return True
    print(f"   [ERROR] CellView mismatch! Expected {lib}/{cell}/{view}, got {actual_lib}/{actual_cell}/{actual_view}")
    return False


def run_il_file(il_file_path: str, lib: str, cell: str, view: str = "layout", save: bool = False) -> str:
    """Run IL file in Virtuoso.

    Uses load_skill_file() which uploads the .il to the remote EDA server via SSH
    before calling load() in Virtuoso.  This is required when running from Windows
    because Virtuoso (on Linux) cannot access local Windows paths directly.

    Includes cellView verification before every load attempt to prevent writing
    into the wrong cell and polluting existing work.
    """
    from io_ring.bridge import (
        open_cell_view_by_type,
        ge_open_window,
        ui_redraw,
        rb_exec,
        load_skill_file,
        save_current_cellview,
    )

    # Ensure library exists before opening cellview
    lib_check = rb_exec(f'if(!ddGetObj("{lib}") dbCreateLib("{lib}" "tphn28hpcpgv18"))', timeout=15)

    skill_path = Path(il_file_path)
    if not skill_path.exists():
        candidate = resolve_output_root() / skill_path.name
        if candidate.exists():
            skill_path = candidate
        else:
            return f"[ERROR] Error: File {il_file_path} does not exist"

    if skill_path.suffix.lower() not in [".il", ".skill"]:
        return f"[ERROR] Error: File {skill_path} is not a valid il/skill file"

    # Upload to remote server then load — works for both local and remote Virtuoso.
    # The bridge daemon can return ok=False for large scripts due to TCP response
    # timing. We verify cellView identity before every load to prevent polluting
    # other cells.
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        # Open and verify the correct cellView before each attempt
        ok = open_cell_view_by_type(lib, cell, view=view, view_type=None, mode="w", timeout=30)
        if not ok:
            return f"[ERROR] Error: Failed to open cellView {lib}/{cell}/{view}"

        window_ok = ge_open_window(lib, cell, view=view, view_type=None, mode="a", timeout=30)
        if not window_ok:
            return f"[ERROR] Error: Failed to open window for {lib}/{cell}/{view}"

        ui_redraw(timeout=10)
        sleep(0.5)
        rb_exec("cv = geGetEditCellView()", timeout=10)

        # CRITICAL: Verify cv points to the requested cell, not some other cell
        if not _verify_cellview(lib, cell, view):
            return (f"[ERROR] Error: CellView mismatch — refusing to load {skill_path.name} "
                    f"into wrong cell. Expected {lib}/{cell}/{view}. "
                    f"Close other cells in Virtuoso and retry.")

        ok = load_skill_file(str(skill_path.resolve()), timeout=300)
        if ok:
            if save:
                if save_current_cellview(timeout=30):
                    return f"[OK] il file {skill_path.name} executed and saved successfully"
                return f"[OK] il file {skill_path.name} executed successfully but save failed"
            return f"[OK] il file {skill_path.name} executed successfully"

        # load_il returned False — but Virtuoso may still be executing or may have
        # finished while the TCP response was lost.  Wait and verify.
        print(f"   [WARN] Attempt {attempt}/{max_attempts} load_il returned False, waiting 5s then verifying...")
        sleep(5)

        # Re-verify cellView is still correct before checking instances
        if not _verify_cellview(lib, cell, view):
            return (f"[ERROR] Error: CellView shifted after failed load — {lib}/{cell}/{view} lost focus. "
                    f"Aborting to prevent polluting other cells.")

        # Check if instances were actually created despite the False return
        inst_count = rb_exec(
            'sprintf(nil "%d" length(cv~>instances))', timeout=10
        ).strip()
        if inst_count and inst_count.isdigit() and int(inst_count) > 0:
            print(f"   ✓ Found {inst_count} instances — script actually succeeded (daemon response was lost)")
            if save:
                save_current_cellview(timeout=30)
            return f"[OK] il file {skill_path.name} executed and saved successfully (verified after response loss)"

        # Genuinely failed — retry
        if attempt < max_attempts:
            print(f"   No instances found, retrying...")

    return f"[ERROR] il file {skill_path.name} execution failed after {max_attempts} attempts"


def main():
    from io_ring.bridge import (
        check_bridge_installed,
        ui_redraw,
        ui_zoom_absolute_scale,
        load_script_and_take_screenshot,
    )

    # Early check — fail fast if bridge is not installed
    ok, info = check_bridge_installed()
    if not ok:
        print(f"[ERROR] {info}")
        sys.exit(2)

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
        print(f"[ERROR] Error: SKILL file not found")
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
        save_dir = resolve_output_root() / "screenshots"
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
        print(f"[>>] Executing SKILL file in Virtuoso...")
        print(f"   File: {il_file_path}")
        print(f"   Library: {lib}")
        print(f"   Cell: {cell}")
        print(f"   View: {view}")
        if screenshot_path:
            print(f"   Screenshot: {screenshot_path}")

        # Run IL file
        run_result = run_il_file(il_file_path=il_file_path, lib=lib, cell=cell, view=view, save=True)
        if not run_result.startswith("[OK]"):
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
            save_dir = resolve_output_root() / "screenshots"
            save_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str((save_dir / f"virtuoso_{Path(il_file_path).stem}_{stamp}.png").resolve())

        screenshot_script = str((skill_dir / "skill_code" / "screenshot.il").resolve(strict=False))
        if load_script_and_take_screenshot(screenshot_script, save_path, timeout=20):
            result_dict["status"] = "success"
            result_dict["message"] = run_result
            result_dict["screenshot_path"] = save_path
            result_dict["observations"].append(f"Screenshot saved: {save_path}")
        else:
            result_dict["message"] = "[ERROR] Screenshot failed"

        print(json.dumps(result_dict, ensure_ascii=False, indent=2))
        sys.exit(0)

    except Exception as e:
        result_dict["message"] = f"[ERROR] Error occurred while running il file: {type(e).__name__}: {e}"
        print(json.dumps(result_dict, ensure_ascii=False, indent=2))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
