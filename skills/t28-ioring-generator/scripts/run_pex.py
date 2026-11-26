#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run PEX - T28 Skill Script

Runs Parasitic Extraction (PEX) on Virtuoso cell.
Uses local imports from io_ring/.

Usage:
    python run_pex.py [lib] [cell] [view] [runDir]

Exit Codes:
    0 - Success (PEX completed)
    1 - PEX failed or tool execution error
    2 - Import/setup error
"""

import os
import sys
from datetime import datetime
from pathlib import Path
import shutil
import time

# Add io_ring to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

from io_ring.config import resolve_output_root


def main():
    from io_ring.layout.device_classifier import _normalize_process_node
    from io_ring.verification.pex import parse_pex_capacitance
    from io_ring.bridge import (
        check_bridge_installed,
        open_cell_view_by_type,
        ui_redraw,
        execute_csh_script,
        get_current_design,
    )

    # Early check — fail fast if bridge is not installed
    ok, info = check_bridge_installed()
    if not ok:
        print(f"[ERROR] {info}")
        sys.exit(2)

    # Set output root. resolve_output_root() applies _local/site.yaml first,
    # then falls back to legacy env/cwd behavior.
    output_root = resolve_output_root()
    os.environ.setdefault("AMS_OUTPUT_ROOT", str(output_root))

    # Parse arguments
    # Optional: lib, cell, view, runDir
    # If lib/cell not provided, use current design
    lib = None
    cell = None
    view = "layout"
    run_dir = None

    if len(sys.argv) > 1:
        lib = sys.argv[1]
    if len(sys.argv) > 2:
        cell = sys.argv[2]
    if len(sys.argv) > 3:
        view = sys.argv[3]
    if len(sys.argv) > 4:
        run_dir = sys.argv[4] if sys.argv[4] not in ("T28", "28") else None
    if len(sys.argv) > 5:
        run_dir = sys.argv[5]

    tech_node = "T28"  # Only T28 is supported (T180 removed)

    try:
        print(f"[>>] Running PEX extraction...")
        print(f"   Tech Node: {tech_node}")
        print(f"   Output Root: {output_root}")

        node = _normalize_process_node(tech_node)
        script_path = skill_dir / "calibre" / "run_pex.csh"

        if not script_path.exists():
            print(f"[ERROR] Error: PEX script file not found")
            print(f"   Expected path: {script_path}")
            print(f"   Script location: calibre/run_pex.csh")
            raise FileNotFoundError(f"PEX script file not found: {script_path}")

        script_path.chmod(0o755)
        print(f"   Script: {script_path} (executable)")

        # If lib/cell provided, open the specified cell first
        if lib and cell:
            ok = open_cell_view_by_type(lib, cell, view=view, view_type=None, mode="r", timeout=30)
            if not ok:
                print(f"[ERROR] Error: Failed to open cellView")
                print(f"   Target: {lib}/{cell}/{view}")
                raise RuntimeError(f"Failed to open cellView {lib}/{cell}/{view}")
            print(f"   CellView opened: {lib}/{cell}/{view}")
            ui_redraw(timeout=5)
        else:
            # Fall back to current design if not explicitly provided
            print(f"   No lib/cell provided, using current design...")
            lib, cell, current_view = get_current_design()
            if lib is None or cell is None:
                print(f"[ERROR] Error: Cannot get current design information")
                print(f"   Please ensure a design is open in Virtuoso, or specify lib and cell")
                raise RuntimeError("Cannot get current design information")
            print(f"   Current design: {lib}/{cell}/{current_view}")

        # Generate timestamped PEX directory to avoid conflicts in parallel runs
        # Use timestamp + process ID + microseconds for maximum uniqueness
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        microseconds = int(time.time() * 1000000) % 1000000
        process_id = os.getpid()

        run_root = output_root / "pex" / f"{timestamp_str}_{process_id}_{microseconds}"
        run_root.mkdir(parents=True, exist_ok=False)
        os.environ["AMS_OUTPUT_ROOT"] = str(run_root)
        pex_dir = run_root / "pex"
        result = execute_csh_script(str(script_path), lib, cell, view, node, timeout=900)
        if "Calibre flow completed successfully." not in str(result).splitlines():
            raise RuntimeError(f"PEX failed. Evidence under {run_root}: {str(result)[-1000:]}")
        netlist_file = pex_dir / f"{cell}.pex.netlist"
        if not netlist_file.is_file() or netlist_file.stat().st_size == 0:
            raise RuntimeError(f"Missing extracted netlist: {netlist_file}")
        if run_dir:
            target = Path(run_dir)
            shutil.copytree(pex_dir, target, dirs_exist_ok=True)
            pex_dir = target
            netlist_file = target / netlist_file.name
        log_file = pex_dir / f"PIPO.LOG.{cell}"

        # Generate report
        report_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_root / f"{cell}_pex_report_{report_timestamp}.txt"
        os.makedirs(report_file.parent, exist_ok=True)

        print(f"   Netlist file: {netlist_file if netlist_file.exists() else 'Not generated'}")
        print(f"   Log file: {log_file if log_file.exists() else 'Not generated'}")
        print(f"   Report file: {report_file}")

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("PEX Extraction Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Design Library: {lib}\nDesign Cell: {cell}\n\n")
            f.write(f"PEX netlist path: {netlist_file if netlist_file.exists() else 'Not generated'}\n")
            f.write(f"PEX log file: {log_file if log_file.exists() else 'Not generated'}\n\n")
            f.write("[OK] PEX extraction process executed successfully!\n\n")
            # Log summary
            if log_file.exists():
                f.write("Log summary:\n")
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as lf:
                        lines = lf.readlines()
                        for line in lines[-2:]:
                            f.write(line)
                except Exception as e:
                    f.write(f"Log reading failed: {e}\n")
            else:
                f.write("PEX log file not found.\n")
            # Add capacitance parsing
            f.write("\n" + parse_pex_capacitance(netlist_file) + "\n")
            f.write("\n" + "=" * 50 + "\n")

        print(f"[OK] Extracted netlist: {netlist_file}")
        print(f"Report: {report_file}")

    except FileNotFoundError as e:
        print(f"[ERROR] Error: File not found - {e}")
        print(f"   Check that the PEX script exists at the correct path")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except RuntimeError as e:
        print(f"[ERROR] Error: Runtime error - {e}")
        print(f"   This may indicate a Virtuoso connection or access issue")
        print(f"   Try running check_virtuoso_connection.py to verify Virtuoso status")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error during PEX: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
