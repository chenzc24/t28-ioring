#!/usr/bin/env python3
"""
manage_registry.py - Defect registry CRUD for skill-maintenance.

Commands: list, add, update, report

Reads/writes data/skill_defects_registry.json relative to this script's
parent directory (i.e. <skill_path>/data/).

Usage:
    python3 manage_registry.py list [--skill SKILL] [--status STATUS]
    python3 manage_registry.py add --skill SKILL --severity SEV --title TITLE --description DESC
    python3 manage_registry.py update --id DEF-NNN [--status STATUS] [--fix_description FIX]
    python3 manage_registry.py report

Tier 1: stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
REGISTRY_PATH = DATA_DIR / "skill_defects_registry.json"


def load_registry() -> dict:
    """Load the defect registry from disk."""
    if not REGISTRY_PATH.exists():
        return {"defects": [], "config": {}, "metadata": {"last_updated": None, "next_id": 1}}
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)


def save_registry(registry: dict):
    """Save the defect registry to disk."""
    registry["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"Registry saved to {REGISTRY_PATH}")


def next_defect_id(registry: dict) -> str:
    """Generate the next defect ID (DEF-001, DEF-002, ...)."""
    next_num = registry.get("metadata", {}).get("next_id", 1)
    # Also scan existing IDs to avoid collision
    for d in registry.get("defects", []):
        try:
            existing_num = int(d["id"].split("-")[1])
            if existing_num >= next_num:
                next_num = existing_num + 1
        except (ValueError, IndexError):
            pass
    return f"DEF-{next_num:03d}"


def cmd_list(args: dict):
    """List defects, optionally filtered."""
    registry = load_registry()
    defects = registry.get("defects", [])

    skill_filter = args.get("skill")
    status_filter = args.get("status")

    if skill_filter:
        defects = [d for d in defects if d.get("skill") == skill_filter]
    if status_filter:
        defects = [d for d in defects if d.get("status") == status_filter]

    if not defects:
        print("No defects found matching the filter.")
        return

    print(f"{'ID':<10} {'Severity':<10} {'Status':<12} {'Skill':<35} {'Title'}")
    print("-" * 100)
    for d in defects:
        print(f"{d['id']:<10} {d.get('severity','?'):<10} {d.get('status','open'):<12} "
              f"{d.get('skill','?'):<35} {d.get('title','')}")

    print(f"\nTotal: {len(defects)} defect(s)")


def cmd_add(args: dict):
    """Add a new defect."""
    required = ["skill", "severity", "title", "description"]
    for field in required:
        if not args.get(field):
            print(f"Error: --{field} is required for 'add' command.")
            sys.exit(2)

    registry = load_registry()
    defect_id = next_defect_id(registry)

    defect = {
        "id": defect_id,
        "skill": args["skill"],
        "severity": args["severity"],
        "title": args["title"],
        "description": args["description"],
        "status": "open",
        "created": datetime.now(timezone.utc).isoformat(),
        "fix_description": None,
    }

    registry["defects"].append(defect)
    # Update next_id
    num = int(defect_id.split("-")[1])
    registry.setdefault("metadata", {})["next_id"] = num + 1

    save_registry(registry)
    print(f"Added defect {defect_id}: {args['title']}")


def cmd_update(args: dict):
    """Update an existing defect."""
    defect_id = args.get("id")
    if not defect_id:
        print("Error: --id is required for 'update' command.")
        sys.exit(2)

    registry = load_registry()
    found = None
    for d in registry["defects"]:
        if d["id"] == defect_id:
            found = d
            break

    if not found:
        print(f"Error: Defect {defect_id} not found.")
        sys.exit(1)

    updated_fields = []
    if args.get("status"):
        found["status"] = args["status"]
        updated_fields.append("status")
    if args.get("fix_description"):
        found["fix_description"] = args["fix_description"]
        updated_fields.append("fix_description")
    if args.get("severity"):
        found["severity"] = args["severity"]
        updated_fields.append("severity")
    if args.get("title"):
        found["title"] = args["title"]
        updated_fields.append("title")

    if not updated_fields:
        print("No fields to update. Use --status, --fix_description, --severity, or --title.")
        sys.exit(2)

    save_registry(registry)
    print(f"Updated {defect_id}: {', '.join(updated_fields)}")


def cmd_report(args: dict):
    """Generate a summary report of all defects."""
    registry = load_registry()
    defects = registry.get("defects", [])

    if not defects:
        print("No defects in registry.")
        return

    # Count by status
    by_status = {}
    by_severity = {}
    by_skill = {}
    for d in defects:
        s = d.get("status", "open")
        by_status[s] = by_status.get(s, 0) + 1
        sev = d.get("severity", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        skill = d.get("skill", "unknown")
        by_skill[skill] = by_skill.get(skill, 0) + 1

    print("=" * 60)
    print("SKILL DEFECT REPORT")
    print("=" * 60)
    print(f"\nTotal defects: {len(defects)}")
    print(f"\nBy status:")
    for k, v in sorted(by_status.items()):
        print(f"  {k}: {v}")
    print(f"\nBy severity:")
    for k, v in sorted(by_severity.items()):
        print(f"  {k}: {v}")
    print(f"\nBy skill:")
    for k, v in sorted(by_skill.items()):
        print(f"  {k}: {v}")
    print()

    # Detail each open defect
    open_defects = [d for d in defects if d.get("status") == "open"]
    if open_defects:
        print(f"Open defects ({len(open_defects)}):")
        print("-" * 60)
        for d in open_defects:
            print(f"  [{d['id']}] [{d.get('severity','')}] {d.get('skill','')}")
            print(f"    {d.get('title','')}")
            print(f"    {d.get('description','')[:100]}")
            print()


def parse_args(argv: list[str]) -> tuple[str, dict]:
    """Simple argument parser. Returns (command, args_dict)."""
    if not argv:
        return "help", {}

    command = argv[0]
    args = {}
    i = 1
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            key = argv[i][2:]
            args[key] = argv[i + 1]
            i += 2
        else:
            i += 1

    return command, args


def main():
    command, args = parse_args(sys.argv[1:])

    commands = {
        "list": cmd_list,
        "add": cmd_add,
        "update": cmd_update,
        "report": cmd_report,
    }

    if command == "help" or command not in commands:
        print("Usage: python3 manage_registry.py <command> [options]")
        print("\nCommands:")
        print("  list    [--skill SKILL] [--status STATUS]")
        print("  add     --skill SKILL --severity SEV --title TITLE --description DESC")
        print("  update  --id DEF-NNN [--status STATUS] [--fix_description FIX]")
        print("  report")
        sys.exit(0 if command == "help" else 2)

    commands[command](args)


if __name__ == "__main__":
    main()
