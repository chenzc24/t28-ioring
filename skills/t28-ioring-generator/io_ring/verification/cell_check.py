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


def evaluate(kind, directory, cell):
    summary = (directory / f"{cell}.{kind}.summary").read_text(errors="replace")
    if kind == "drc":
        if not re.search(
            rf"^Layout Primary Cell:\s*{re.escape(cell)}\s*$", summary, re.M
        ):
            raise ValueError("DRC primary cell differs from requested cell")
        if _total(summary, "TOTAL DRC RuleChecks Executed") == 0:
            raise ValueError("No DRC checks executed")
        count = _total(summary, "TOTAL DRC Results Generated")
        return {"drc_results": count}, count == 0
    overall = re.search(r"OVERALL COMPARISON RESULTS(.*?)CELL\s+SUMMARY", summary, re.S)
    if not overall or not re.search(r"\b(?:CORRECT|INCORRECT)\b", overall[1]):
        raise ValueError("Missing overall LVS comparison verdict")
    correct = (
        bool(re.search(r"\bCORRECT\b", overall[1])) and "INCORRECT" not in overall[1]
    )
    erc = (directory / "calibre_erc.sum").read_text(errors="replace")
    if not re.search(rf"^Layout Primary Cell:\s*{re.escape(cell)}\s*$", erc, re.M):
        raise ValueError("ERC primary cell differs from requested cell")
    if _total(erc, "TOTAL ERC RuleChecks Executed") == 0:
        raise ValueError("No ERC checks executed")
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
    }, correct and count == 0


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
    if not power or not ground or power & ground:
        raise ValueError("Expected distinct nonempty power and ground net lists")
    return _quoted(power), _quoted(ground)


def run(kind):
    parser = argparse.ArgumentParser()
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
    text = deck.read_text(encoding="utf-8")
    report = {
        "library": args.lib,
        "cell": args.cell,
        "view": args.view,
        "scope": "cell",
        "deck": str(deck),
        "passed": False,
    }
    try:
        if kind == "lvs":
            power, ground = supply_names(args.intent)
            for keyword, names in (
                ("LVS POWER NAME", '"VDD?" ' + power),
                ("LVS GROUND NAME", '"VSS?" "GND?" ' + ground),
                ("VIRTUAL CONNECT NAME", power + " " + ground),
            ):
                text, n = re.subn(
                    rf"^{keyword} .*$", keyword + " " + names, text, flags=re.M
                )
                if n != 1:
                    raise ValueError(f"Expected one {keyword} in {deck}")
            report["erc_required"] = True
            report["supply_source"] = str(args.intent or "configured T28 rail names")
        elif args.chip_deck:
            if not re.fullmatch(r"/[\w./+-]+", args.chip_deck):
                raise ValueError("Expected an absolute EDA-host deck path")
            text = re.sub(r'(?m)^DRC UNSELECT CHECK\s*(?:"[^"]+"\s*)+', "", text)
            text, n = re.subn(
                r'(?m)^INCLUDE ".*"$', f'INCLUDE "{args.chip_deck}"', text
            )
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
        details, report["passed"] = evaluate(kind, root / kind, args.cell)
        report.update(details)
    except Exception as exc:
        report["error"] = str(exc)
    path = root / "result.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"{kind.upper()} {report['scope']} {'PASS' if report['passed'] else 'FAIL'}  {path}"
    )
    if "error" in report:
        print(report["error"])
    return 0 if report["passed"] else 1
