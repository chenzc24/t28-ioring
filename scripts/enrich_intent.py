#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrich Intent - T28 Skill Script

Runs the enrichment engine on a semantic intent JSON to produce a full
intent graph JSON (mechanically wired pins, suffix, corners, gate checks).
Gate check results and ESD override info are printed to console instead of
a separate trace JSON file.

Usage:
    python enrich_intent.py <semantic_intent.json> <intent_graph.json> [tech_node]

Exit Codes:
    0 - Success
    1 - Semantic intent input error (read engine stderr for fix hint)
    2 - Wiring table or engine bug
    3 - Gate failure (read engine stderr; re-classify in semantic intent)
"""

import sys
from pathlib import Path

skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))


def main():
    from io_ring.layout.enrichment_engine import (
        enrich,
        EngineError,
        InputError,
        WiringError,
        GateError,
    )

    if len(sys.argv) < 3:
        print("Usage: python enrich_intent.py <semantic_intent.json> <intent_graph.json> [tech_node]")
        print("")
        print("Arguments:")
        print("  semantic_intent.json  - AI-produced semantic intent (input)")
        print("  intent_graph.json     - Full pin-wired intent graph (output)")
        print("  tech_node             - Optional: T28 (default)")
        print("")
        print("Exit codes:")
        print("  0 - Success")
        print("  1 - Semantic intent input error")
        print("  2 - Wiring table / engine bug")
        print("  3 - Gate failure")
        sys.exit(2)

    semantic_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    tech_node = sys.argv[3] if len(sys.argv) > 3 else "T28"

    if tech_node != "T28":
        print(f"[ERROR] Only T28 supported in this engine version (got: {tech_node})")
        sys.exit(2)

    wiring_path = skill_dir / "io_ring" / "schematic" / "devices" / "device_wiring_T28.json"

    print(f"[>>] Enriching semantic intent...")
    print(f"   Input:    {semantic_path}")
    print(f"   Output:   {output_path}")
    print(f"   Wiring:   {wiring_path}")

    try:
        result = enrich(semantic_path, wiring_path, output_path)
    except InputError as e:
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except WiringError as e:
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except GateError as e:
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print("", file=sys.stderr)
        print(f"[ENGINE-BUG] Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    n_pads = sum(1 for i in result["intent_graph"]["instances"] if i["type"] in ("pad", "inner_pad"))
    n_corners = sum(1 for i in result["intent_graph"]["instances"] if i["type"] == "corner")
    duration = result["duration_ms"]

    print(f"")
    print(f"[OK] Enrichment complete in {duration}ms")
    print(f"   Pads: {n_pads}, Corners: {n_corners}")

    # Print gate results
    gates = result["gates"]
    print(f"   Gates:")
    for gate_id, gate_result in gates.items():
        status = "PASS" if gate_result.get("pass") else "FAIL"
        label = gate_id
        extra = ""
        if "skipped" in gate_result:
            extra = f" (skipped: {gate_result['skipped']})"
        elif "label" in gate_result:
            extra = f" (VSS={gate_result['label']})"
        elif "providers" in gate_result:
            extra = f" (providers: {', '.join(gate_result['providers'])})"
        elif "counts" in gate_result:
            extra = f" ({gate_result['counts']})"
        elif "esd_signal" in gate_result:
            extra = f" (ESD={gate_result['esd_signal']})"
        print(f"     {label}: {status}{extra}")

    # Print G8 domain continuity warnings
    g8_warnings = gates.get("G8_domain_continuity", {}).get("warnings", [])
    if g8_warnings:
        print(f"   [WARN] Domain continuity:")
        for w in g8_warnings:
            print(f"     - {w}")

    # Print ESD override info
    if result["esd_override_applied"]:
        print(f"   Ring ESD override applied to {result['esd_pads_overridden']} pads")

    print(f"   Wrote: {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
