#!/usr/bin/env python3
"""
audit_sync.py - Dual-location sync check for claude-code-skills.

Compares files between the active cache and the user repository to detect
skills that have drifted, are orphaned, or are missing from one location.

Usage:
    python3 audit_sync.py
    python3 audit_sync.py --skill io-ring-orchestrator-T28

Tier 1: stdlib only.
"""
from __future__ import annotations

import filecmp
import json
import os
import sys
from pathlib import Path
from typing import Optional, List


# --- Path constants ---
HOME = Path.home()
CACHE_ROOT = HOME / ".claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills"
REPO_ROOT = HOME / "AMS-IO-Agent_processes_combined/claude-code-skills"
REPO_T28 = REPO_ROOT / "T28"
REPO_T180 = REPO_ROOT / "T180"


def skill_to_repo_path(skill_name: str) -> Optional[Path]:
    """Map a skill name to its user-repo location.

    Rules:
      - Names ending with '-T28'  -> REPO_T28/{skill_name}/
      - Names ending with '-T180' -> REPO_T180/{skill_name}/
      - Otherwise                 -> REPO_ROOT/{skill_name}/
    """
    if skill_name.endswith("-T28"):
        candidate = REPO_T28 / skill_name
        if candidate.is_dir():
            return candidate
    elif skill_name.endswith("-T180"):
        candidate = REPO_T180 / skill_name
        if candidate.is_dir():
            return candidate

    # Fallback: check root, then T28, then T180
    for base in [REPO_ROOT, REPO_T28, REPO_T180]:
        candidate = base / skill_name
        if candidate.is_dir():
            return candidate
    return None


def compare_dirs(dir_a: Path, dir_b: Path) -> dict:
    """Recursively compare two directories. Returns a dict with:
      - identical: list of files that match
      - different: list of files that differ (with summary)
      - only_in_a: files only in dir_a
      - only_in_b: files only in dir_b
    """
    identical = []
    different = []
    only_in_a = []
    only_in_b = []

    # Collect all relative paths from both dirs
    files_a = set()
    files_b = set()

    for root, _dirs, files in os.walk(dir_a):
        for f in files:
            rel = Path(root).relative_to(dir_a) / f
            files_a.add(str(rel))

    for root, _dirs, files in os.walk(dir_b):
        for f in files:
            rel = Path(root).relative_to(dir_b) / f
            files_b.add(str(rel))

    common = files_a & files_b
    only_in_a_set = files_a - files_b
    only_in_b_set = files_b - files_a

    only_in_a = sorted(only_in_a_set)
    only_in_b = sorted(only_in_b_set)

    for rel in sorted(common):
        path_a = dir_a / rel
        path_b = dir_b / rel
        if filecmp.cmp(path_a, path_b, shallow=False):
            identical.append(rel)
        else:
            # Get a brief diff summary (first differing line)
            try:
                lines_a = path_a.read_text(errors="replace").splitlines()
                lines_b = path_b.read_text(errors="replace").splitlines()
                diff_lines = 0
                for la, lb in zip(lines_a, lines_b):
                    if la != lb:
                        diff_lines += 1
                diff_lines += abs(len(lines_a) - len(lines_b))
                different.append({
                    "file": rel,
                    "lines_differ": diff_lines,
                    "lines_a": len(lines_a),
                    "lines_b": len(lines_b),
                })
            except Exception:
                different.append({"file": rel, "error": "binary or unreadable"})

    return {
        "identical": identical,
        "different": different,
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
    }


def check_skill_sync(skill_name: str) -> dict:
    """Check sync status for a single skill."""
    cache_path = CACHE_ROOT / skill_name
    repo_path = skill_to_repo_path(skill_name)

    if not cache_path.is_dir() and repo_path is None:
        return {"skill": skill_name, "status": "NOT_FOUND", "detail": "Not found in cache or repo"}

    if not cache_path.is_dir():
        return {
            "skill": skill_name,
            "status": "ORPHANED_REPO",
            "detail": f"Only in repo: {repo_path}",
            "repo_path": str(repo_path),
        }

    if repo_path is None:
        return {
            "skill": skill_name,
            "status": "ORPHANED_CACHE",
            "detail": f"Only in cache: {cache_path}",
            "cache_path": str(cache_path),
        }

    comparison = compare_dirs(cache_path, repo_path)

    n_diff = len(comparison["different"])
    n_only_a = len(comparison["only_in_a"])
    n_only_b = len(comparison["only_in_b"])

    if n_diff == 0 and n_only_a == 0 and n_only_b == 0:
        status = "IN_SYNC"
    else:
        status = "DRIFTED"

    return {
        "skill": skill_name,
        "status": status,
        "cache_path": str(cache_path),
        "repo_path": str(repo_path),
        "identical_files": len(comparison["identical"]),
        "different_files": comparison["different"],
        "only_in_cache": comparison["only_in_a"],
        "only_in_repo": comparison["only_in_b"],
    }


def get_all_skill_names() -> List[str]:
    """Collect all unique skill names from cache and repo."""
    names = set()
    if CACHE_ROOT.is_dir():
        for d in CACHE_ROOT.iterdir():
            if d.is_dir():
                names.add(d.name)
    for subdir in [REPO_ROOT, REPO_T28, REPO_T180]:
        if subdir.is_dir():
            for d in subdir.iterdir():
                if d.is_dir() and (d / "SKILL.md").exists():
                    names.add(d.name)
    return sorted(names)


def main():
    # Parse args
    skill_filter = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--skill" and i + 1 < len(args):
            skill_filter = args[i + 1]
            i += 2
        else:
            skill_filter = args[i]
            i += 1

    if skill_filter:
        skills = [skill_filter]
    else:
        skills = get_all_skill_names()

    results = []
    for skill in skills:
        results.append(check_skill_sync(skill))

    # JSON output
    output = {
        "audit_type": "sync_check",
        "skills_checked": len(skills),
        "results": results,
    }
    print(json.dumps(output, indent=2, default=str))

    # Human-readable summary
    print("\n" + "=" * 70)
    print("SYNC AUDIT SUMMARY")
    print("=" * 70)
    counts = {"IN_SYNC": 0, "DRIFTED": 0, "ORPHANED_CACHE": 0, "ORPHANED_REPO": 0, "NOT_FOUND": 0}
    for r in results:
        status = r["status"]
        counts[status] = counts.get(status, 0) + 1
        icon = {"IN_SYNC": "OK", "DRIFTED": "DRIFT", "ORPHANED_CACHE": "CACHE_ONLY",
                "ORPHANED_REPO": "REPO_ONLY", "NOT_FOUND": "MISSING"}.get(status, status)
        print(f"  {icon:12s} {r['skill']}")
        if status == "DRIFTED":
            for df in r.get("different_files", []):
                print(f"               diff: {df['file']} ({df.get('lines_differ', '?')} lines differ)")
            for f in r.get("only_in_cache", []):
                print(f"               cache-only: {f}")
            for f in r.get("only_in_repo", []):
                print(f"               repo-only: {f}")

    print(f"\nTotals: {counts['IN_SYNC']} in-sync, {counts['DRIFTED']} drifted, "
          f"{counts['ORPHANED_CACHE']} cache-only, {counts['ORPHANED_REPO']} repo-only")
    sys.exit(1 if counts["DRIFTED"] > 0 else 0)


if __name__ == "__main__":
    main()
