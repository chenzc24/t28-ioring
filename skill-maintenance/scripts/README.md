# Skill Maintenance Scripts

All scripts are **Tier 1** (Python stdlib only, no external dependencies).

## Scripts

### audit_skill.py
Main audit runner. Orchestrates all checks for a given skill or all skills.

```bash
python3 audit_skill.py <skill-name>   # Audit one skill
python3 audit_skill.py all            # Audit all skills in cache
```

Checks performed:
1. SKILL.md frontmatter validation
2. Script import validation (AST-based)
3. Cross-skill reference validation
4. Environment/venv checks
5. Cache-repo sync check

Output: JSON report + human-readable summary.

### audit_imports.py
AST-based import validation. Parses each Python script in a skill for
`from src.* import X` statements and verifies that `X` actually exists
in the target AMS-IO-Agent module (via AST, not execution).

```bash
python3 audit_imports.py <skill-name>
python3 audit_imports.py all
```

### audit_sync.py
Compares files between the active cache and user repository to detect drift.

```bash
python3 audit_sync.py                              # Check all skills
python3 audit_sync.py --skill io-ring-orchestrator-T28  # Check one skill
```

### manage_registry.py
CRUD operations on the defect registry (`data/skill_defects_registry.json`).

```bash
python3 manage_registry.py list [--skill SKILL] [--status STATUS]
python3 manage_registry.py add --skill SKILL --severity high --title "..." --description "..."
python3 manage_registry.py update --id DEF-001 --status fixed
python3 manage_registry.py report
```

### patch_skill.py
Applies text patches to skill files, dual-writing to both cache and repo.

```bash
python3 patch_skill.py --skill SKILL --file scripts/foo.py --old "old text" --new "new text"
```
