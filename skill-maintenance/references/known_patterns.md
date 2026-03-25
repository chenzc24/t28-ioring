# Known Defect Patterns

Reference catalog of common defect patterns found in claude-code-skills, with diagnosis and fix guidance.

---

## Pattern 1: Stale API Reference

**Category:** Import / API mismatch
**Severity:** High
**Detection:** `audit_imports.py` flags `NAME_NOT_FOUND`

### Symptoms
- Script imports a function/class from an AMS-IO-Agent module, but the name does not exist
- `ImportError: cannot import name 'X' from 'src.tools.Y'`

### Root Cause
The skill was authored against a planned or outdated API. The function was renamed, moved to a different module, or never implemented.

### Example
```python
# In scripts/check_virtuoso_connection.py:
from src.tools.io_ring_generator_tool import check_virtuoso_connection
# ERROR: check_virtuoso_connection does not exist in that module
```

### How to Fix
1. Identify the actual function in AMS-IO-Agent that provides the needed capability
2. Update the import statement in the wrapper script
3. Update the SKILL.md documentation to reference the correct function
4. Dual-write the fix to both cache and repo

### Search Strategy
```bash
# Find all functions defined in the target module:
python3 audit_imports.py <skill-name>
# The output lists available names in the module

# Or manually search AMS-IO-Agent source:
grep -rn "def <function_name>" ~/AMS-IO-Agent_processes_combined/AMS-IO-Agent/src/
```

---

## Pattern 2: Environment Assumption

**Category:** Environment / dependency
**Severity:** Medium
**Detection:** `audit_skill.py` environment check

### Symptoms
- `ModuleNotFoundError: No module named 'smolagents'` (or other package)
- Script works with AMS-IO-Agent venv but fails with system Python
- No documentation about which Python interpreter to use

### Root Cause
Skill scripts assume system Python has all required packages, but AMS-IO-Agent dependencies are only in the project's virtual environment.

### Example
```bash
python3 scripts/build_confirmed_config.py ...
# ModuleNotFoundError: No module named 'smolagents'

# Works with:
~/AMS-IO-Agent_processes_combined/AMS-IO-Agent/venv/bin/python3 scripts/build_confirmed_config.py ...
```

### How to Fix

**Option A:** Add venv documentation to SKILL.md
```markdown
### Python Environment
Tier 2 scripts require the AMS-IO-Agent virtual environment:
\`\`\`bash
AMS-IO-Agent/venv/bin/python3 scripts/<script>.py
\`\`\`
```

**Option B:** Add/update `run_with_ams.sh` wrapper
```bash
#!/bin/bash
VENV="$HOME/AMS-IO-Agent_processes_combined/AMS-IO-Agent/venv/bin/python3"
if [ -f "$VENV" ]; then
    exec "$VENV" "$@"
else
    echo "Error: AMS-IO-Agent venv not found at $VENV"
    exit 2
fi
```

**Option C:** Add shebang to scripts
```python
#!/home/chenzc_intern25/AMS-IO-Agent_processes_combined/AMS-IO-Agent/venv/bin/python3
```

---

## Pattern 3: Workflow Gap

**Category:** SKILL.md documentation / workflow design
**Severity:** High
**Detection:** Manual review, or `audit_skill.py` cross-reference check

### Symptoms
- A step in the SKILL.md workflow fails in certain execution modes (CLI vs GUI)
- The SKILL.md describes a mandatory step that only works in one context
- Workarounds needed to proceed past a documented step

### Root Cause
The skill was designed for one execution mode (typically GUI/interactive) and the workflow doesn't account for alternative modes (CLI/automated).

### Example
```markdown
# In SKILL.md Step 8:
build_io_ring_confirmed_config(...)   # <-- GUI-only step

# In CLI mode, this is unnecessary. Generators can use:
generate_io_ring_schematic(config_path=intent_graph, consume_confirmed_only=False)
```

### How to Fix
1. Identify which execution modes are supported
2. Add conditional logic or documentation for each mode:
   ```markdown
   ### Step 8: Build Confirmed Config

   **GUI mode:** Call `build_io_ring_confirmed_config(...)`
   **CLI mode:** Skip this step. Pass `consume_confirmed_only=False` to generators.
   ```
3. Update wrapper scripts to accept a `--mode cli|gui` flag if applicable

---

## Pattern 4: Missing Cross-Reference

**Category:** Skill dependency
**Severity:** High
**Detection:** `audit_skill.py` cross-reference check

### Symptoms
- SKILL.md references `**Invoke:** \`some-skill\`` but that skill doesn't exist in the cache
- Orchestrator skill fails because a sub-skill isn't available

### Root Cause
- The referenced skill was renamed or removed
- The skill was never deployed to the cache
- Typo in the skill name

### How to Fix
1. Check if the skill exists under a different name: `ls ~/.claude/plugins/cache/anthropic-agent-skills/claude-api/b0cbd3df1533/skills/`
2. If renamed, update the reference in SKILL.md
3. If missing, deploy the skill to both cache and repo
4. If the feature is handled differently now, update the workflow

---

## Pattern 5: Sync Drift

**Category:** Deployment
**Severity:** Medium
**Detection:** `audit_sync.py`

### Symptoms
- A fix applied to the cache isn't reflected in the user repo (or vice versa)
- Different behavior depending on which copy is loaded
- `audit_sync.py` reports `DRIFTED` status

### Root Cause
- Manual edit to one location without updating the other
- Partial deployment (copied to cache but forgot repo)
- Different fix applied independently to each location

### How to Fix
1. Run `audit_sync.py --skill <name>` to see exactly which files differ
2. Determine which copy has the correct version
3. Use `patch_skill.py` for targeted dual-write, or manually copy the correct version to both locations
4. Re-run sync check to confirm resolution
