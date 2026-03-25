#!/usr/bin/env python3
"""
patch_skill.py - Dual-write patcher for claude-code-skills.

Applies a text patch (string replacement) to a file within a skill,
writing to BOTH the active cache and the user repo. Verifies both
writes succeeded and logs changes.

Usage:
    python3 patch_skill.py --skill SKILL --file REL_PATH --old OLD_TEXT --new NEW_TEXT
    python3 patch_skill.py --skill SKILL --file REL_PATH --old-file OLD.txt --new-file NEW.txt

Tier 1: stdlib only.
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# --- Path constants ---
HOME = Path.home()
CACHE_ROOT = HOME / ".claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills"
REPO_ROOT = HOME / "AMS-IO-Agent_processes_combined/claude-code-skills"
REPO_T28 = REPO_ROOT / "T28"
REPO_T180 = REPO_ROOT / "T180"
SCRIPT_DIR = Path(__file__).resolve().parent
PATCH_LOG = SCRIPT_DIR.parent / "data" / "patch_log.json"


def skill_to_repo_path(skill_name: str) -> Optional[Path]:
    """Map a skill name to its user-repo location."""
    if skill_name.endswith("-T28"):
        candidate = REPO_T28 / skill_name
        if candidate.is_dir():
            return candidate
    elif skill_name.endswith("-T180"):
        candidate = REPO_T180 / skill_name
        if candidate.is_dir():
            return candidate

    for base in [REPO_ROOT, REPO_T28, REPO_T180]:
        candidate = base / skill_name
        if candidate.is_dir():
            return candidate
    return None


def load_patch_log() -> list:
    if PATCH_LOG.exists():
        with open(PATCH_LOG, "r") as f:
            return json.load(f)
    return []


def save_patch_log(log: list):
    PATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PATCH_LOG, "w") as f:
        json.dump(log, f, indent=2)


def apply_patch(skill_name: str, rel_path: str, old_text: str, new_text: str) -> dict:
    """Apply a text replacement patch to both cache and repo copies of a skill file."""
    cache_dir = CACHE_ROOT / skill_name
    repo_dir = skill_to_repo_path(skill_name)

    result = {
        "skill": skill_name,
        "file": rel_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_path": None,
        "repo_path": None,
        "cache_written": False,
        "repo_written": False,
        "verified": False,
        "error": None,
    }

    # Resolve paths
    cache_file = cache_dir / rel_path if cache_dir.is_dir() else None
    repo_file = repo_dir / rel_path if repo_dir else None

    if cache_file:
        result["cache_path"] = str(cache_file)
    if repo_file:
        result["repo_path"] = str(repo_file)

    # Read from whichever location exists (prefer cache as it's the live version)
    source_file = None
    if cache_file and cache_file.is_file():
        source_file = cache_file
    elif repo_file and repo_file.is_file():
        source_file = repo_file

    if source_file is None:
        result["error"] = f"File {rel_path} not found in either location for skill {skill_name}"
        return result

    content = source_file.read_text(encoding="utf-8")

    # Apply patch
    if old_text not in content:
        result["error"] = f"Old text not found in {source_file}. Patch cannot be applied."
        return result

    patched = content.replace(old_text, new_text, 1)

    # Write to cache
    if cache_file:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(patched, encoding="utf-8")
            result["cache_written"] = True
        except OSError as e:
            result["error"] = f"Failed to write cache: {e}"
            return result

    # Write to repo
    if repo_file:
        try:
            repo_file.parent.mkdir(parents=True, exist_ok=True)
            repo_file.write_text(patched, encoding="utf-8")
            result["repo_written"] = True
        except OSError as e:
            result["error"] = f"Cache written but repo write failed: {e}"
            return result

    # Verify both are identical
    if cache_file and repo_file and cache_file.is_file() and repo_file.is_file():
        result["verified"] = filecmp.cmp(cache_file, repo_file, shallow=False)
        if not result["verified"]:
            result["error"] = "Written files differ - verification failed!"
    elif result["cache_written"] or result["repo_written"]:
        # Only one location exists - that's OK, just note it
        result["verified"] = True
        if not cache_file or not cache_file.parent.is_dir():
            result["error"] = f"Warning: cache dir missing for {skill_name}, only repo patched"
        elif not repo_file:
            result["error"] = f"Warning: repo dir missing for {skill_name}, only cache patched"

    return result


def parse_args(argv: list[str]) -> dict:
    """Parse command-line arguments."""
    args = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            key = argv[i][2:].replace("-", "_")
            args[key] = argv[i + 1]
            i += 2
        else:
            i += 1
    return args


def main():
    args = parse_args(sys.argv[1:])

    skill = args.get("skill")
    rel_path = args.get("file")
    old_text = args.get("old")
    new_text = args.get("new")

    # Support reading old/new from files
    if not old_text and args.get("old_file"):
        old_text = Path(args["old_file"]).read_text()
    if not new_text and args.get("new_file"):
        new_text = Path(args["new_file"]).read_text()

    if not all([skill, rel_path, old_text, new_text]):
        print("Usage: python3 patch_skill.py --skill SKILL --file REL_PATH --old OLD_TEXT --new NEW_TEXT")
        print("  or:  python3 patch_skill.py --skill SKILL --file REL_PATH --old-file F1 --new-file F2")
        sys.exit(2)

    print(f"Patching {skill}/{rel_path}")
    print(f"  Replace: {old_text[:80]}{'...' if len(old_text) > 80 else ''}")
    print(f"  With:    {new_text[:80]}{'...' if len(new_text) > 80 else ''}")

    result = apply_patch(skill, rel_path, old_text, new_text)

    # Log the patch
    log = load_patch_log()
    log.append(result)
    save_patch_log(log)

    # Report
    print()
    if result.get("error"):
        print(f"ERROR: {result['error']}")

    print(f"Cache written: {result['cache_written']}" +
          (f" ({result['cache_path']})" if result['cache_path'] else ""))
    print(f"Repo written:  {result['repo_written']}" +
          (f" ({result['repo_path']})" if result['repo_path'] else ""))
    print(f"Verified:      {result['verified']}")

    if result["cache_written"] and result["repo_written"] and result["verified"]:
        print("\nPatch applied successfully to both locations.")
        sys.exit(0)
    else:
        print("\nPatch had issues - see above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
