"""Run Calibre in an isolated directory and evaluate its actual result summaries."""

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from io_ring.config import resolve_output_root


def _total(summary, key):
    values = re.findall(rf"^{key}:\s*(\d+)(?:\s*\((\d+)\))?\s*$", summary, re.M)
    if len(values) != 1:
        raise ValueError(f"Expected one {key} in Calibre summary")
    flat, hierarchical = values[0]
    if int(flat) == 0 and int(hierarchical or 0) > 0:
        raise ValueError(f"Inconsistent Calibre counts for {key}")
    return int(flat)


def evaluate(kind, directory, cell, *, erc_enabled=True):
    summary = (directory / f"{cell}.{kind}.summary").read_text(errors="replace")
    if kind == "drc":
        if not re.search(
            rf"^Layout Primary Cell:\s*{re.escape(cell)}\s*$", summary, re.M
        ):
            raise ValueError("DRC primary cell differs from requested cell")
        executed = _total(summary, "TOTAL DRC RuleChecks Executed")
        count = _total(summary, "TOTAL DRC Results Generated")
        return {
            "drc_checks_executed": executed,
            "drc_results": count,
        }, executed > 0 and count == 0
    overall = re.search(r"OVERALL COMPARISON RESULTS(.*?)CELL\s+SUMMARY", summary, re.S)
    if not overall or not re.search(r"\b(?:CORRECT|INCORRECT)\b", overall[1]):
        raise ValueError("Missing overall LVS comparison verdict")
    correct = (
        bool(re.search(r"\bCORRECT\b", overall[1])) and "INCORRECT" not in overall[1]
    )
    if not erc_enabled and not (directory / "calibre_erc.sum").exists():
        return {"lvs_correct": correct, "erc_results": None, "erc_rules": {}}, correct
    erc = (directory / "calibre_erc.sum").read_text(errors="replace")
    if not re.search(rf"^Layout Primary Cell:\s*{re.escape(cell)}\s*$", erc, re.M):
        raise ValueError("ERC primary cell differs from requested cell")
    executed = _total(erc, "TOTAL ERC RuleChecks Executed")
    count = _total(erc, "TOTAL ERC RuleCheck Results Generated")
    violations = {
        rule: int(n)
        for rule, n in re.findall(
            r"^RULECHECK (\S+)\s+\.+\s+TOTAL Result Count = (\d+)", erc, re.M
        )
        if int(n)
    }
    return {
        "lvs_correct": correct,
        "erc_results": count,
        "erc_rules": violations,
        "erc_checks_executed": executed,
    }, correct and executed > 0 and count == 0


def _quoted(values):
    for name in values:
        if not re.fullmatch(r"[A-Za-z0-9_!<>.\[\]-]+", name):
            raise ValueError(f"Unsupported literal Calibre supply net {name!r}")
    return " ".join(f'"{name}"' for name in sorted(values))


def supply_names(intent):
    power, ground = set(), set()
    if intent:
        for pad in json.loads(intent.read_text(encoding="utf-8"))["instances"]:
            for pin, value in pad.get("pin_connection", {}).items():
                if pin in {"VDD", "VDDPST", "TACVDD", "TAVDD", "AVDD"}:
                    power.add(value["label"])
                elif pin in {"VSS", "VSSPST", "TACVSS", "TAVSS", "AVSS"}:
                    ground.add(value["label"])
    else:
        config = Path(__file__).parents[1] / "layout/config/lydevices_28.json"
        names = json.loads(config.read_text())
        power, ground = set(names["power_names"]), set(names["ground_names"])
    return _quoted(power), _quoted(ground)


def prepare_deck(kind, deck, report, *, intent=None, chip_deck=None, custom_deck=None):
    """Stage and identify the wrapper actually supplied to the Calibre scripts."""
    text = deck.read_text(encoding="utf-8")
    if custom_deck:
        text = custom_deck.read_text(encoding="utf-8")
        report["source_wrapper"] = str(custom_deck)
    elif kind == "lvs":
        power, ground = supply_names(intent)
        for keyword, names in (
            ("LVS POWER NAME", '"VDD?" ' + power),
            ("LVS GROUND NAME", '"VSS?" "GND?" ' + ground),
            ("VIRTUAL CONNECT NAME", power + " " + ground),
        ):
            text, n = re.subn(
                rf"^{keyword} .*$",
                (keyword + " " + names if names.strip() else ""),
                text,
                flags=re.M,
            )
            if n != 1:
                raise ValueError(f"Expected one {keyword} in {deck}")
        report["erc_required"] = True
        report["supply_source"] = str(intent or "configured T28 rail names")
    elif chip_deck:
        if not re.fullmatch(r"/[\w./+-]+", chip_deck):
            raise ValueError("Expected an absolute EDA-host deck path")
        text = re.sub(r'(?m)^DRC UNSELECT CHECK\s*(?:"[^"]+"\s*)+', "", text)
        text, n = re.subn(r'(?m)^INCLUDE ".*"$', f'INCLUDE "{chip_deck}"', text)
        if n != 1:
            raise ValueError("Expected one DRC deck include")
        text = text.replace('VIRTUAL CONNECT NAME "?"', "")
        report["scope"] = "chip"
    deck.write_text(text, encoding="utf-8")
    report["deck_sha256"] = hashlib.sha256(deck.read_bytes()).hexdigest()
    report["directives"] = re.findall(
        r"^(?:INCLUDE |source |VIRTUAL CONNECT |LVS (?:POWER|GROUND) NAME |LVS EXECUTE ERC ).*$",
        text,
        re.M,
    )
    unselect = re.search(r'^DRC UNSELECT CHECK\s*((?:"[^"]+"\s*)+)', text, re.M)
    report["wrapper_unselected_checks"] = (
        re.findall(r'"([^"]+)"', unselect[1]) if unselect else []
    )
    if kind == "lvs":
        report["erc_required"] = bool(re.search(r"(?im)^LVS EXECUTE ERC YES\b", text))


def run(kind):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck",
        type=Path,
        help="Use your complete local wrapper with the normal stream/netlist placeholders",
    )
    parser.add_argument("--threads", type=int, help="CPU count for Calibre -turbo on a shared host")
    parser.add_argument("lib")
    parser.add_argument("cell")
    parser.add_argument("view", nargs="?", default="layout")
    parser.add_argument("node", nargs="?", choices=["T28", "28"], default="T28")
    if kind == "lvs":
        parser.add_argument(
            "--intent",
            type=Path,
            help="resolved intent or confirmed JSON for literal supply names",
        )
    else:
        parser.add_argument(
            "--chip-deck", help="absolute EDA-host path to full-chip DRC include"
        )
    args = parser.parse_args()
    if args.threads is not None:
        if args.threads < 1:
            parser.error("--threads expects a positive count")
        os.environ["AMS_CALIBRE_THREADS"] = str(args.threads)
    if not all(
        re.fullmatch(r"[\w.-]+", name) and name not in {".", ".."}
        for name in (args.lib, args.cell, args.view)
    ):
        parser.error("Invalid library, cell or view name")
    source = Path(__file__).resolve().parents[2] / "calibre"
    root = resolve_output_root() / kind / f"{args.cell}_{uuid4().hex[:12]}"
    staged = root / "calibre"
    shutil.copytree(source, staged)
    os.environ["AMS_OUTPUT_ROOT"] = str(root)
    deck = (
        staged
        / "T28"
        / ("_calibre_T28.lvs_" if kind == "lvs" else "_drc_rule_T28_cell_")
    )
    report = {
        "library": args.lib,
        "cell": args.cell,
        "view": args.view,
        "scope": "cell",
        "calibre_threads": os.environ.get("AMS_CALIBRE_THREADS"),
        "deck": str(deck),
        "passed": False,
    }
    try:
        prepare_deck(
            kind,
            deck,
            report,
            intent=getattr(args, "intent", None),
            chip_deck=getattr(args, "chip_deck", None),
            custom_deck=args.deck,
        )
        from io_ring.bridge import execute_csh_script

        script = staged / f"run_{kind}.csh"
        result = execute_csh_script(
            str(script), args.lib, args.cell, args.view, args.node, timeout=600
        )
        marker = f"Calibre {kind.upper()} flow ({args.node}) completed successfully."
        if marker not in str(result).splitlines():
            raise RuntimeError(
                f"Calibre execution or output transfer failed: {str(result)[-1200:]}"
            )
        details, report["passed"] = evaluate(
            kind, root / kind, args.cell, erc_enabled=report.get("erc_required", True)
        )
        report.update(details)
    except Exception as exc:
        report["error"] = str(exc)
    report["completed"] = "error" not in report
    path = root / "result.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if "error" in report:
        print(f"{kind.upper()} execution failed: {report['error']}  {path}")
    elif kind == "drc":
        print(f"DRC {report['scope']}: {report['drc_results']} results  {path}")
    else:
        verdict = "CORRECT" if report["lvs_correct"] else "INCORRECT"
        erc = report["erc_results"] if report["erc_results"] is not None else "not run"
        print(f"LVS {report['scope']}: {verdict}, ERC: {erc}  {path}")
    return 0 if report["completed"] else 1
