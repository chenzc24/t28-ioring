#!/usr/bin/env python3
"""
audit_skill.py - Main audit runner for claude-code-skills.

Orchestrates all checks for a given skill (or all skills):
  1. SKILL.md frontmatter validation
  2. Script import validation (delegates to audit_imports.py logic)
  3. Cross-skill reference validation
  4. Environment/venv checks
  5. Sync check (delegates to audit_sync.py logic)

Usage:
    python3 audit_skill.py <skill-name>
    python3 audit_skill.py all

Outputs structured JSON report + human-readable summary.

Tier 1: stdlib only.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

# Add script dir to path so we can import sibling modules
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from audit_imports import audit_skill_imports
from audit_sync import check_skill_sync


# --- Path constants ---
HOME = Path.home()
CACHE_ROOT = HOME / ".claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills"
REPO_ROOT = HOME / "AMS-IO-Agent_processes_combined/claude-code-skills"
AMS_ROOT = HOME / "AMS-IO-Agent_processes_combined/AMS-IO-Agent"
AMS_VENV = AMS_ROOT / "venv/bin/python3"


def check_frontmatter(skill_name: str) -> list[dict]:
    """Validate SKILL.md frontmatter exists and has required fields."""
    issues = []
    skill_md = CACHE_ROOT / skill_name / "SKILL.md"

    if not skill_md.is_file():
        issues.append({
            "check": "frontmatter",
            "severity": "high",
            "message": f"SKILL.md not found at {skill_md}",
        })
        return issues

    content = skill_md.read_text(encoding="utf-8", errors="replace")

    if not content.startswith("---"):
        issues.append({
            "check": "frontmatter",
            "severity": "high",
            "message": "SKILL.md missing YAML frontmatter (must start with ---)",
        })
        return issues

    parts = content.split("---", 2)
    if len(parts) < 3:
        issues.append({
            "check": "frontmatter",
            "severity": "high",
            "message": "SKILL.md has malformed frontmatter (missing closing ---)",
        })
        return issues

    frontmatter = parts[1]

    if "name:" not in frontmatter:
        issues.append({
            "check": "frontmatter",
            "severity": "high",
            "message": "Frontmatter missing 'name' field",
        })

    if "description:" not in frontmatter:
        issues.append({
            "check": "frontmatter",
            "severity": "high",
            "message": "Frontmatter missing 'description' field",
        })

    # Check that the name matches the directory name
    name_match = re.search(r"name:\s*(.+)", frontmatter)
    if name_match:
        declared_name = name_match.group(1).strip()
        if declared_name != skill_name:
            issues.append({
                "check": "frontmatter",
                "severity": "medium",
                "message": f"Declared name '{declared_name}' does not match directory name '{skill_name}'",
            })

    return issues


def check_cross_references(skill_name: str) -> list[dict]:
    """Parse SKILL.md for cross-skill invocation patterns and verify they exist."""
    issues = []
    skill_md = CACHE_ROOT / skill_name / "SKILL.md"

    if not skill_md.is_file():
        return issues

    content = skill_md.read_text(encoding="utf-8", errors="replace")

    # Look for patterns like: **Invoke:** `skill-name`
    invoke_pattern = re.compile(r"\*\*Invoke:\*\*\s*`([^`]+)`")
    referenced_skills = invoke_pattern.findall(content)

    for ref_skill in referenced_skills:
        ref_path = CACHE_ROOT / ref_skill
        if not ref_path.is_dir():
            issues.append({
                "check": "cross_reference",
                "severity": "high",
                "message": f"SKILL.md invokes '{ref_skill}' but it does not exist in cache",
                "referenced_skill": ref_skill,
            })

    return issues


def check_environment(skill_name: str) -> list[dict]:
    """Check environment setup: venv references, run_with_ams.sh, etc."""
    issues = []
    skill_dir = CACHE_ROOT / skill_name
    scripts_dir = skill_dir / "scripts"

    if not scripts_dir.is_dir():
        return issues

    has_run_with_ams = (scripts_dir / "run_with_ams.sh").is_file()
    has_tier2_scripts = False

    # Check each Python script for AMS-IO-Agent imports (Tier 2 dependency)
    for py_file in scripts_dir.glob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
                has_tier2_scripts = True
                break

    if has_tier2_scripts and not has_run_with_ams:
        issues.append({
            "check": "environment",
            "severity": "medium",
            "message": "Skill has Tier 2 scripts (import from src.*) but no run_with_ams.sh wrapper",
        })

    # Check if SKILL.md mentions venv for Tier 2 workflows
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file() and has_tier2_scripts:
        content = skill_md.read_text(encoding="utf-8", errors="replace")
        if "venv" not in content.lower() and "virtual" not in content.lower():
            issues.append({
                "check": "environment",
                "severity": "medium",
                "message": "Skill has Tier 2 scripts but SKILL.md does not mention venv/virtual environment",
            })

    # Check if run_with_ams.sh actually references the venv
    if has_run_with_ams:
        rwa_content = (scripts_dir / "run_with_ams.sh").read_text(errors="replace")
        if "venv" not in rwa_content:
            issues.append({
                "check": "environment",
                "severity": "low",
                "message": "run_with_ams.sh exists but does not reference venv",
            })

    return issues


def audit_skill(skill_name: str) -> dict:
    """Run all audit checks on a single skill."""
    all_issues = []

    # 1. Frontmatter
    all_issues.extend(check_frontmatter(skill_name))

    # 2. Import validation
    import_report = audit_skill_imports(skill_name)
    for imp_issue in import_report.get("issues", []):
        all_issues.append({
            "check": "import",
            "severity": "high",
            "message": imp_issue.get("detail", str(imp_issue)),
            "name": imp_issue.get("name"),
            "module": imp_issue.get("module"),
            "script": imp_issue.get("script"),
            "line": imp_issue.get("line"),
        })

    # 3. Cross-skill references
    all_issues.extend(check_cross_references(skill_name))

    # 4. Environment
    all_issues.extend(check_environment(skill_name))

    # 5. Sync
    sync_result = check_skill_sync(skill_name)
    if sync_result["status"] == "DRIFTED":
        all_issues.append({
            "check": "sync",
            "severity": "medium",
            "message": f"Cache and repo copies are out of sync",
            "different_files": sync_result.get("different_files", []),
            "only_in_cache": sync_result.get("only_in_cache", []),
            "only_in_repo": sync_result.get("only_in_repo", []),
        })
    elif sync_result["status"] in ("ORPHANED_CACHE", "ORPHANED_REPO"):
        all_issues.append({
            "check": "sync",
            "severity": "low",
            "message": f"Skill is {sync_result['status'].lower().replace('_', ' ')}",
        })

    # Categorize
    high = [i for i in all_issues if i.get("severity") == "high"]
    medium = [i for i in all_issues if i.get("severity") == "medium"]
    low = [i for i in all_issues if i.get("severity") == "low"]

    return {
        "skill": skill_name,
        "total_issues": len(all_issues),
        "high": len(high),
        "medium": len(medium),
        "low": len(low),
        "issues": all_issues,
        "sync_status": sync_result["status"],
    }


def get_all_skill_names() -> list[str]:
    """List all skill directories in the cache."""
    if not CACHE_ROOT.is_dir():
        return []
    return sorted(d.name for d in CACHE_ROOT.iterdir() if d.is_dir())


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 audit_skill.py <skill-name|all>")
        sys.exit(2)

    target = sys.argv[1]

    if target == "all":
        skills = get_all_skill_names()
    else:
        skills = [target]

    all_reports = []
    total_issues = 0

    for skill in skills:
        report = audit_skill(skill)
        all_reports.append(report)
        total_issues += report["total_issues"]

    # JSON output
    output = {
        "audit_type": "full_skill_audit",
        "skills_checked": len(skills),
        "total_issues": total_issues,
        "reports": all_reports,
    }
    print(json.dumps(output, indent=2, default=str))

    # Human-readable summary
    print("\n" + "=" * 70)
    print("SKILL AUDIT SUMMARY")
    print("=" * 70)

    for report in all_reports:
        skill = report["skill"]
        n = report["total_issues"]
        status = "PASS" if n == 0 else "FAIL"
        sync = report["sync_status"]
        print(f"\n  {status}  {skill}  ({n} issues, sync: {sync})")

        if n > 0:
            for issue in report["issues"]:
                sev = issue.get("severity", "?").upper()
                check = issue.get("check", "?")
                msg = issue.get("message", "")
                print(f"         [{sev}] ({check}) {msg}")

    print(f"\n{'=' * 70}")
    print(f"Total: {len(skills)} skills audited, {total_issues} issues found")

    # Count by severity across all
    all_high = sum(r["high"] for r in all_reports)
    all_med = sum(r["medium"] for r in all_reports)
    all_low = sum(r["low"] for r in all_reports)
    print(f"  HIGH: {all_high}  MEDIUM: {all_med}  LOW: {all_low}")

    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()
