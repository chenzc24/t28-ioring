"""Compile semantic intent into checked schematic/layout scripts in one run directory."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent))
from io_ring.config import resolve_output_root
from io_ring.layout.enrichment_engine import EngineError, enrich


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intent", type=Path)
    parser.add_argument("--output-root", type=Path, help="parent of generated/<run>")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run = (
        (args.output_root or resolve_output_root()).resolve()
        / "generated"
        / f"{stamp}_{uuid4().hex[:8]}"
    )
    run.mkdir(parents=True)
    manifest = {
        "status": "failed",
        "stage": "input",
        "run_dir": str(run),
        "artifacts": {},
    }

    def record(key, path):
        manifest["artifacts"][key] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    code = 1
    try:
        semantic = run / "io_ring_semantic_intent.json"
        semantic.write_bytes(args.intent.read_bytes())
        record("semantic", semantic)
        graph = run / "io_ring_intent_graph.json"
        confirmed = run / "io_ring_confirmed.json"
        manifest["stage"] = "enrich"
        result = enrich(
            semantic,
            SCRIPTS.parent / "io_ring/schematic/devices/device_wiring_T28.json",
            graph,
        )
        manifest["gates"] = result["gates"]
        record("intent", graph)
        steps = [
            ("validate_intent", [graph], None),
            ("build_confirmed_config", [graph, confirmed, "--skip-editor"], confirmed),
        ]
        for view in ("schematic", "layout"):
            target = run / f"io_ring_{view}_{stamp}.il"
            steps.append((f"generate_{view}", [confirmed, target, "T28"], target))
        for stage, arguments, target in steps:
            manifest["stage"] = stage
            subprocess.run(
                [sys.executable, str(SCRIPTS / (stage + ".py")), *map(str, arguments)],
                env=dict(os.environ, PYTHONUTF8="1"),
                check=True,
            )
            if target:
                record(stage, target)
        manifest["rule_review"] = json.loads(confirmed.read_text(encoding="utf-8"))[
            "rule_review"
        ]
        manifest.update(
            status="prepared", stage="complete", physical_verification="pending"
        )
        code = 0
    except (EngineError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        manifest["error"] = str(exc)
        code = getattr(exc, "returncode", getattr(exc, "exit_code", 1))
    finally:
        path = run / "run.json"
        path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"{manifest['status']}  {path}", flush=True)
        if "error" in manifest:
            print(manifest["error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
