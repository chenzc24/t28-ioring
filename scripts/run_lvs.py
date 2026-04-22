#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run LVS - T28 Skill Script

Runs Layout vs Schematic (LVS) check on Virtuoso cell.
Uses local imports from assets/.

Usage:
    python run_lvs.py <lib> <cell> [view] [tech_node]

Exit Codes:
    0 - Success (LVS passed)
    1 - LVS failed or tool execution error
    2 - Import/setup error
"""

import os
import sys
from datetime import datetime
from pathlib import Path

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


def _resolve_summary_file(subdir: str, filename: str) -> Path:
    """Resolve summary file path (from original runtime_t28.py)."""
    preferred = _resolve_output_root() / subdir / filename
    if preferred.exists():
        return preferred
    return preferred


def _parse_lvs_summary(file_path: str) -> str:
    """Parse LVS summary (from original runtime_t28.py)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        overall_results = ""
        cell_summary = ""
        summary_section = ""
        in_overall = False
        in_cell = False
        in_summary = False

        for i, line in enumerate(lines):
            if "OVERALL COMPARISON RESULTS" in line:
                in_overall = True
                overall_results += line
                continue
            if in_overall:
                overall_results += line
                if "CELL  SUMMARY" in line or "LVS PARAMETERS" in line:
                    in_overall = False

            if "CELL  SUMMARY" in line:
                in_cell = True
                cell_summary += line
                continue
            if in_cell:
                cell_summary += line
                if "LVS PARAMETERS" in line or "SUMMARY" in line:
                    in_cell = False

            if "SUMMARY" in line and (i + 1 < len(lines) and "Total CPU Time" in lines[i + 1]):
                in_summary = True
                summary_section += line
                continue
            if in_summary:
                summary_section += line
                if "Total Elapsed Time" in line:
                    in_summary = False

        result = ["LVS check result summary:", "=" * 50, ""]
        if overall_results:
            result.extend(["Overall comparison results:", overall_results, ""])
        if cell_summary:
            result.extend(["Cell summary:", cell_summary, ""])
        if summary_section:
            result.extend(["Execution summary:", summary_section, ""])

        if not overall_results and not cell_summary and not summary_section:
            return "LVS original summary content (first 100 lines):\n" + "=" * 50 + "\n" + "".join(lines[:100])
        return "\n".join(result)
    except Exception as e:
        return f"Failed to parse LVS summary file: {e}"


def _write_report(title: str, content: str, output_file: str) -> tuple[bool, str]:
    """Write report file (from original runtime_t28.py)."""
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"{title}\n")
            f.write("=" * 50 + "\n\n")
            f.write(content)
        return True, f"Report generated: {output_file}"
    except Exception as e:
        return False, f"Error generating report: {e}"


def main():
    from assets.core.layout.device_classifier import _normalize_process_node
    from assets.utils.bridge_utils import (
        open_cell_view_by_type,
        ui_redraw,
        execute_csh_script,
    )

    # Set output root
    os.environ.setdefault("AMS_OUTPUT_ROOT", str((Path(os.getcwd()) / "output").resolve(strict=False)))
    output_root = _resolve_output_root()

    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python run_lvs.py <lib> <cell> [view] [tech_node]")
        print("\nArguments:")
        print("  lib       - Virtuoso library name")
        print("  cell      - Virtuoso cell name")
        print("  view      - Optional: View name (default: layout)")
        print("  tech_node - Optional: 'T28' (default: T28)")
        print("\nExample:")
        print("  python run_lvs.py MyLib MyCell layout T28")
        sys.exit(2)

    lib = sys.argv[1]
    cell = sys.argv[2]
    view = sys.argv[3] if len(sys.argv) > 3 else "layout"
    tech_node = sys.argv[4] if len(sys.argv) > 4 else "T28"

    try:
        print(f"🔧 Running LVS check...")
        print(f"   Library: {lib}")
        print(f"   Cell: {cell}")
        print(f"   View: {view}")
        print(f"   Tech Node: {tech_node}")
        print(f"   Output Root: {output_root}")

        node = _normalize_process_node(tech_node)
        script_path = skill_dir / "assets" / "external_scripts" / "calibre" / "run_lvs.csh"
        if not script_path.exists():
            print(f"❌ Error: LVS script file not found")
            print(f"   Expected path: {script_path}")
            print(f"   Script location: assets/external_scripts/calibre/run_lvs.csh")
            print(f"   Check:")
            print(f"     1. Verify skill directory structure")
            print(f"     2. Check if Calibre scripts are installed")
            raise FileNotFoundError(f"LVS script file not found: {script_path}")

        script_path.chmod(0o755)
        print(f"   Script: {script_path} (executable)")

        ok = open_cell_view_by_type(lib, cell, view=view, view_type=None, mode="r", timeout=30)
        if not ok:
            print(f"❌ Error: Failed to open cellView")
            print(f"   Target: {lib}/{cell}/{view}")
            print(f"   This may indicate:")
            print(f"     1. Virtuoso is not running (check with check_virtuoso_connection.py)")
            print(f"     2. Library '{lib}' does not exist")
            print(f"     3. Cell '{cell}' does not exist")
            print(f"     4. View '{view}' is not accessible")
            raise RuntimeError(f"Failed to open cellView {lib}/{cell}/{view}")

        print(f"   CellView opened successfully")

        ui_redraw(timeout=5)

        result = execute_csh_script(str(script_path), lib, cell, view, node, timeout=300)
        print(f"   Script execution completed")

        _r = str(result) if result else ""
        _failed = (not result) or any(_r.startswith(p) for p in (
            "Remote csh execution failed", "Remote execution failed", "Remote upload failed"))
        if _failed:
            print(f"❌ Error: LVS script execution failed")
            print(f"   Command: {script_path}")
            print(f"   Arguments: {lib} {cell} {view} {node}")
            print(f"   Result: {result}")
            print(f"   This may indicate:")
            print(f"     1. Calibre is not installed or not in PATH")
            print(f"     2. Calibre LVS rules file is missing")
            print(f"     3. Network/daemon issues with bridge")
            return "❌ LVS check failed"

        print(f"   Script result: Success")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = str(_resolve_summary_file("lvs", f"{cell}.lvs.summary"))
        report_file = str(output_root / f"{cell}_lvs_report_{timestamp}.txt")
        os.makedirs(os.path.dirname(report_file), exist_ok=True)
        print(f"   Summary file: {summary_file}")
        print(f"   Report file: {report_file}")

        parsed = _parse_lvs_summary(summary_file)
        success, msg = _write_report("LVS report", parsed, report_file)
        if not success:
            print(f"⚠️  Warning: Report generation issue - {msg}")

        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report_content = f.read()
            print("\n".join(
                [
                    "✅ LVS check completed!",
                    f"\nReport location: {report_file}",
                    "\nReport content:",
                    "=" * 50,
                    report_content,
                    "=" * 50,
                ]
            ))
        except Exception as e:
            print(f"✅ LVS check completed!")
            print(f"⚠️  Warning: Cannot read report content: {e}")
            print(f"   Report file: {report_file}")

        sys.exit(0)

    except FileNotFoundError as e:
        print(f"❌ Error: File not found - {e}")
        print(f"   Check that specified file exists at correct path")
        print(f"   Verify working directory or use absolute paths")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ Error: Runtime error - {e}")
        print(f"   This may indicate a Virtuoso connection or access issue")
        print(f"   Try running check_virtuoso_connection.py to verify Virtuoso status")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error during LVS: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
