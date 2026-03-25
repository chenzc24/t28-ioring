---
name: skill-maintenance
description: Audit, diagnose, track, and patch claude-code-skills. Detects stale imports, missing functions, workflow gaps, and environment issues. Dual-writes patches to both active cache and user repo.
---

# Skill Maintenance

You are a skill maintenance agent. You audit, diagnose, track, and patch defects across all claude-code-skills in this project.

## Path Constants

### Active Cache (what Claude Code loads at runtime)
```
CACHE_ROOT = ~/.claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills/
```

### User Repository (source of truth, user-browsable)
```
REPO_ROOT  = ~/AMS-IO-Agent_processes_combined/claude-code-skills/
REPO_T28   = ~/AMS-IO-Agent_processes_combined/claude-code-skills/T28/
REPO_T180  = ~/AMS-IO-Agent_processes_combined/claude-code-skills/T180/
```

### AMS-IO-Agent Source (for import validation)
```
AMS_ROOT   = ~/AMS-IO-Agent_processes_combined/AMS-IO-Agent/
AMS_SRC    = ~/AMS-IO-Agent_processes_combined/AMS-IO-Agent/src/
AMS_VENV   = ~/AMS-IO-Agent_processes_combined/AMS-IO-Agent/venv/bin/python3
```

### This Skill's Bundled Scripts
```
SKILL_SCRIPTS = <skill_path>/scripts/
SKILL_DATA    = <skill_path>/data/
```

## Modes

This skill operates in 5 modes. Use the mode that matches the user's intent.

---

## Mode 1: Audit

**Trigger:** User asks to audit, check, or validate a skill (or all skills).

**What it does:**
1. Validates SKILL.md frontmatter (name, description present)
2. Checks script imports against AMS-IO-Agent source (AST-based, no execution)
3. Verifies cross-skill references (`**Invoke:** \`skill-name\``) resolve to real skills
4. Checks environment setup (venv references, `run_with_ams.sh` presence)
5. Checks sync between cache and repo copies

**How to run:**
```bash
python3 <skill_path>/scripts/audit_skill.py <skill-name>
python3 <skill_path>/scripts/audit_skill.py all
```

**Example:**
```
User: "Audit io-ring-orchestrator-T28"

1. Run: python3 <skill_path>/scripts/audit_skill.py io-ring-orchestrator-T28
2. Review the JSON report and human-readable summary
3. Present findings organized by severity (HIGH, MEDIUM, LOW)
4. Suggest fixes for each issue found
```

**Output:** JSON report + human-readable summary listing all issues found.

---

## Mode 2: Diagnose

**Trigger:** User reports a specific skill failure or error.

**What it does:**
1. Reads the error context from the user
2. Runs targeted audit checks on the affected skill
3. Cross-references against known defect patterns (see `references/known_patterns.md`)
4. Checks the defect registry for known issues
5. Proposes a root cause and fix

**How to run:**
```bash
# Check imports specifically
python3 <skill_path>/scripts/audit_imports.py <skill-name>

# Check known defects
python3 <skill_path>/scripts/manage_registry.py list --skill <skill-name>
```

**Example:**
```
User: "check_virtuoso_connection fails with ImportError"

1. Run audit_imports.py on the affected skill
2. It will show that check_virtuoso_connection is not defined in io_ring_generator_tool
3. Check known_patterns.md for "Stale API Reference" pattern
4. Check registry: manage_registry.py list --skill io-ring-orchestrator-T28
5. Propose fix: use rb_exec from il_runner_tool instead
```

---

## Mode 3: Track

**Trigger:** User wants to log, list, or update a skill defect.

**What it does:**
- CRUD operations on the defect registry (`data/skill_defects_registry.json`)
- Each defect has: id, skill, severity, title, description, status, fix_description

**How to run:**
```bash
# List all defects
python3 <skill_path>/scripts/manage_registry.py list

# List defects for one skill
python3 <skill_path>/scripts/manage_registry.py list --skill io-ring-orchestrator-T28

# Add a new defect
python3 <skill_path>/scripts/manage_registry.py add \
  --skill "skill-name" \
  --severity "high" \
  --title "Brief title" \
  --description "Full description of the defect"

# Update status
python3 <skill_path>/scripts/manage_registry.py update --id DEF-001 --status fixed

# Generate report
python3 <skill_path>/scripts/manage_registry.py report
```

---

## Mode 4: Patch

**Trigger:** User wants to fix a skill defect.

**What it does:**
1. Applies a text patch to a file within a skill
2. Writes to BOTH the active cache and the user repo (dual-write)
3. Verifies both writes succeeded and files match
4. Logs the patch to `data/patch_log.json`

**CRITICAL:** All patches MUST be written to both locations. Never patch only one copy.

**How to run:**
```bash
python3 <skill_path>/scripts/patch_skill.py \
  --skill "io-ring-orchestrator-T28" \
  --file "scripts/check_virtuoso_connection.py" \
  --old "from src.tools.io_ring_generator_tool import check_virtuoso_connection" \
  --new "from src.tools.il_runner_tool import rb_exec"
```

**Manual patch workflow (when the script can't handle complex changes):**
1. Identify both file paths:
   - Cache: `~/.claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills/{skill}/`
   - Repo: Figure out the repo subdir:
     - Skills ending with `-T28` -> `claude-code-skills/T28/{skill}/`
     - Skills ending with `-T180` -> `claude-code-skills/T180/{skill}/`
     - Other skills -> `claude-code-skills/{skill}/`
2. Edit the file in the cache location
3. Copy the identical edit to the repo location
4. Verify both files are identical
5. Log the change

**After patching:** Update the defect registry status to "fixed".

---

## Mode 5: Sync

**Trigger:** User asks to check if cache and repo copies are in sync.

**What it does:**
1. For each skill in the cache, finds the corresponding repo location
2. Recursively compares all files (content-level diff)
3. Reports: identical, drifted (with diff summary), or orphaned (exists in one location only)

**How to run:**
```bash
python3 <skill_path>/scripts/audit_sync.py
python3 <skill_path>/scripts/audit_sync.py --skill io-ring-orchestrator-T28
```

**Output:** Table showing sync status of each skill.

**To fix drift:** Either:
- Copy cache -> repo (if cache has the desired version)
- Copy repo -> cache (if repo has the desired version)
- Use Mode 4 (Patch) to apply a targeted fix to both

---

## Bundled Scripts Reference

| Script | Purpose | Tier |
|--------|---------|------|
| `audit_skill.py` | Full audit of one or all skills | 1 (stdlib) |
| `audit_sync.py` | Dual-location sync check | 1 (stdlib) |
| `audit_imports.py` | AST-based import validation | 1 (stdlib) |
| `manage_registry.py` | Defect registry CRUD | 1 (stdlib) |
| `patch_skill.py` | Dual-write patcher | 1 (stdlib) |

All scripts are **Tier 1**: they use only Python stdlib and have zero external dependencies.

## Data Files

| File | Purpose |
|------|---------|
| `data/skill_defects_registry.json` | Known defect database |
| `data/patch_log.json` | History of applied patches (auto-created) |

## References

| File | Purpose |
|------|---------|
| `references/known_patterns.md` | Catalog of common defect patterns and fixes |

## Defect Pattern Categories

When auditing or diagnosing, classify issues into these categories:

1. **Stale API Reference** - Script imports a function that doesn't exist in the target module
2. **Environment Assumption** - Script assumes a specific Python env, venv, or system dependency
3. **Workflow Gap** - SKILL.md documents a step that doesn't work in all execution modes (CLI vs GUI)
4. **Missing Cross-Reference** - SKILL.md references another skill that doesn't exist in the cache
5. **Sync Drift** - Cache and repo copies of a skill have diverged

## Example Full Workflow

```
User: "Audit all skills and fix any issues found"

1. Run: python3 scripts/audit_skill.py all
2. Review report - say it finds 5 issues across 3 skills
3. For each issue:
   a. Check if it's already in the registry (manage_registry.py list)
   b. If new, add it (manage_registry.py add ...)
   c. Determine fix
   d. Apply fix with dual-write (patch_skill.py or manual)
   e. Update registry status (manage_registry.py update --id DEF-XXX --status fixed)
4. Run audit again to confirm all issues resolved
5. Run sync check to confirm both locations match
```
