#!/usr/bin/env python3
"""
audit_imports.py - AST-based import validation for claude-code-skills scripts.

Parses Python scripts for import statements and verifies that the imported
names actually exist in the target AMS-IO-Agent modules. Uses AST parsing
only (no execution, no external deps).

Usage:
    python3 audit_imports.py <skill-name>
    python3 audit_imports.py all

Tier 1: stdlib only.
"""
from __future__ import annotations

import ast
import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Set


# --- Path constants ---
HOME = Path.home()
CACHE_ROOT = HOME / ".claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills"
AMS_ROOT = HOME / "AMS-IO-Agent_processes_combined/AMS-IO-Agent"
AMS_SRC = AMS_ROOT / "src"


def resolve_module_path(module_name: str) -> Optional[Path]:
    """Resolve a dotted module name (e.g. 'src.tools.io_ring_generator_tool')
    to a .py file path relative to AMS_ROOT."""
    parts = module_name.split(".")
    # Try as a module file first
    candidate = AMS_ROOT / "/".join(parts)
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return py_file
    # Try as a package __init__.py
    init_file = candidate / "__init__.py"
    if init_file.is_file():
        return init_file
    return None


def get_defined_names(module_path: Path) -> Set[str]:
    """Parse a Python file's AST and extract all top-level defined names
    (functions, classes, assignments)."""
    try:
        source = module_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(module_path))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            names.add(elt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def extract_imports(script_path: Path) -> List[Dict]:
    """Parse a Python script and extract all import-from statements
    that reference AMS-IO-Agent modules (src.*)."""
    try:
        source = script_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(script_path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [{"error": f"Could not parse {script_path}: {e}"}]

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("src."):
                for alias in node.names:
                    imports.append({
                        "module": node.module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                        "script": str(script_path),
                    })
    return imports


def check_import(imp: dict) -> dict:
    """Verify a single import: does the name exist in the target module?"""
    result = dict(imp)
    module_path = resolve_module_path(imp["module"])

    if module_path is None:
        result["status"] = "MODULE_NOT_FOUND"
        result["detail"] = f"Module {imp['module']} does not resolve to a file under {AMS_ROOT}"
        return result

    result["module_path"] = str(module_path)
    defined = get_defined_names(module_path)

    if imp["name"] == "*":
        result["status"] = "WILDCARD"
        result["detail"] = "Star import - cannot validate individual names"
    elif imp["name"] in defined:
        result["status"] = "OK"
        result["detail"] = f"{imp['name']} found in {module_path.name}"
    else:
        result["status"] = "NAME_NOT_FOUND"
        result["detail"] = (
            f"{imp['name']} is NOT defined in {module_path.name}. "
            f"Available names: {sorted(defined)[:20]}"
        )
    return result


def audit_skill_imports(skill_name: str) -> dict:
    """Audit all Python scripts in a skill for import issues."""
    skill_path = CACHE_ROOT / skill_name / "scripts"
    if not skill_path.is_dir():
        return {
            "skill": skill_name,
            "error": f"Scripts directory not found: {skill_path}",
            "issues": [],
        }

    all_results = []
    issues = []

    for py_file in sorted(skill_path.glob("*.py")):
        imports = extract_imports(py_file)
        for imp in imports:
            if "error" in imp:
                issues.append(imp)
                continue
            result = check_import(imp)
            all_results.append(result)
            if result["status"] not in ("OK", "WILDCARD"):
                issues.append(result)

    return {
        "skill": skill_name,
        "scripts_checked": len(list(skill_path.glob("*.py"))),
        "imports_checked": len(all_results),
        "issues_found": len(issues),
        "issues": issues,
        "all_results": all_results,
    }


def get_all_skill_names() -> List[str]:
    """List all skill directories in the cache."""
    if not CACHE_ROOT.is_dir():
        return []
    return sorted(d.name for d in CACHE_ROOT.iterdir() if d.is_dir())


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 audit_imports.py <skill-name|all>")
        sys.exit(2)

    target = sys.argv[1]

    if target == "all":
        skills = get_all_skill_names()
    else:
        skills = [target]

    all_reports = []
    total_issues = 0

    for skill in skills:
        report = audit_skill_imports(skill)
        all_reports.append(report)
        total_issues += report.get("issues_found", 0)

    # JSON output
    output = {
        "audit_type": "import_validation",
        "skills_checked": len(skills),
        "total_issues": total_issues,
        "reports": all_reports,
    }
    print(json.dumps(output, indent=2, default=str))

    # Human-readable summary
    print("\n" + "=" * 70)
    print("IMPORT AUDIT SUMMARY")
    print("=" * 70)
    for report in all_reports:
        skill = report["skill"]
        if "error" in report:
            print(f"  SKIP  {skill}: {report['error']}")
            continue
        n_issues = report["issues_found"]
        n_imports = report["imports_checked"]
        status = "PASS" if n_issues == 0 else "FAIL"
        print(f"  {status}  {skill}: {n_imports} imports checked, {n_issues} issues")
        for issue in report["issues"]:
            severity = "HIGH" if issue.get("status") == "NAME_NOT_FOUND" else "MEDIUM"
            name = issue.get("name", "?")
            detail = issue.get("detail", "")
            print(f"         [{severity}] {name}: {detail}")

    print(f"\nTotal: {len(skills)} skills, {total_issues} issues")
    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()
