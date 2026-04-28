---
name: io-ring-orchestrator-T28
description: Master coordinator for complete T28 (28nm) IO Ring generation. Handles signal classification, device mapping, pin configuration, JSON generation, and complete workflow through DRC/LVS verification. Use this skill for any T28 IO Ring generation task.
---

# IO Ring Orchestrator - T28

Master coordinator for T28 IO Ring generation — entire workflow from requirements through DRC/LVS.

## Scripts Path Verification

Auto-detect `SCRIPTS_PATH` from this file's location. Do NOT hard-code:

```bash
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_PATH="${SKILL_ROOT}/scripts"
ls "$SCRIPTS_PATH/validate_intent.py" || echo "ERROR: SCRIPTS_PATH not found"
```

## Entry Points

- **Text requirements only** → Step 0 → Step 2 (Draft) → [Step 2b if enabled] → Step 3 (Semantic Intent + Engine)
- **Image input (with or without text)** → Step 0 → Step 1 (Image) → Step 2 → [Step 2b if enabled] → Step 3
- **Draft intent graph file provided** → Skip to Step 3
- **Final intent graph file provided** → Skip to Step 4
- **User explicitly requests Draft Editor** (e.g. "I want to use the editor", "open draft editor", "visual editor") → Always open Step 2b regardless of `AMS_DRAFT_EDITOR`

Determine entry path automatically. Do NOT run pre-step wizard eligibility/opt-in flow.

## Draft Editor vs Confirmation Editor

| | Draft Editor (Step 2b) | Confirmation Editor (Step 5) |
|---|---|---|
| **Input** | Minimal: name, position, type (optional device) | Full enriched intent graph |
| **Pin connections** | Hidden / not generated | Visible and editable |
| **Fillers** | Not shown (added in Step 5) | Visible and editable |
| **Corners** | Placeholder "+ Corner" slots | All 4 must be filled |
| **Validation** | Ring closure check | Full layout validation |
| **Output** | Draft JSON → Step 3 | Confirmed JSON → Step 6 |
| **Confirm button** | "Confirm Draft" | "Confirm & Continue" |
| **Banner** | "Draft mode — fillers and pins added automatically later" | None |

## Output Path Contract (Mandatory)

- Single workspace output root per run; create `output_dir` once and reuse for Steps 2-8.
- Do NOT regenerate `timestamp` after Step 0. Export `AMS_OUTPUT_ROOT` once in Step 0.
- `AMS_OUTPUT_ROOT`: workspace-level output root
- `output_dir`: `${AMS_OUTPUT_ROOT}/generated/${timestamp}`
- DRC/LVS reports: `${AMS_OUTPUT_ROOT}/drc` and `${AMS_OUTPUT_ROOT}/lvs`

## Complete Workflow

### Step 0: Directory Setup & Parse Input

```bash
# Workspace root (prefer AMS_IO_AGENT_PATH, fallback to current dir)
if [ -n "${AMS_IO_AGENT_PATH:-}" ]; then WORK_ROOT="${AMS_IO_AGENT_PATH}"; else WORK_ROOT="$(pwd)"; fi

export AMS_OUTPUT_ROOT="${WORK_ROOT}/output"
mkdir -p "${AMS_OUTPUT_ROOT}/generated"

# Per-run dir: reuse if set, else create
if [ -n "${output_dir:-}" ] && [ -d "${output_dir}" ]; then
  echo "Reusing existing output_dir: ${output_dir}"
else
  timestamp="${timestamp:-$(date +%Y%m%d_%H%M%S)}"
  output_dir="${AMS_OUTPUT_ROOT}/generated/${timestamp}"
fi
mkdir -p "$output_dir"
echo "AMS_OUTPUT_ROOT=${AMS_OUTPUT_ROOT}"; echo "output_dir=${output_dir}"

# Resolve Python — project-root .venv preferred (shared with bridge), then skill .venv, then system.
PROJECT_ROOT="$(cd "${WORK_ROOT}" && while [ ! -d .venv ] && [ "$(pwd)" != "/" ]; do cd ..; done; pwd)"
if   [ -f "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]; then export AMS_PYTHON="${PROJECT_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${PROJECT_ROOT}/.venv/bin/python" ];         then export AMS_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${SKILL_ROOT}/.venv/Scripts/python.exe" ];   then export AMS_PYTHON="${SKILL_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${SKILL_ROOT}/.venv/bin/python" ];           then export AMS_PYTHON="${SKILL_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null;                    then export AMS_PYTHON="python3"
elif command -v python  &>/dev/null;                    then export AMS_PYTHON="python"
else echo "ERROR: No Python 3.9+ found. Create .venv at project root."; return 1; fi
echo "AMS_PYTHON=${AMS_PYTHON}"

# Load .env into shell environment (skill .env, then project .env; later does NOT override earlier)
if [ -f "${SKILL_ROOT}/.env" ]; then set -a; . "${SKILL_ROOT}/.env"; set +a; fi
if [ -f "${PROJECT_ROOT}/.env" ]; then set -a; . "${PROJECT_ROOT}/.env"; set +a; fi

# Editor modes (default off if not set by .env)
[ "${AMS_DRAFT_EDITOR:-}"  = "on" ] || export AMS_DRAFT_EDITOR="off"
[ "${AMS_LAYOUT_EDITOR:-}" = "on" ] || export AMS_LAYOUT_EDITOR="off"
echo "AMS_DRAFT_EDITOR=${AMS_DRAFT_EDITOR}  AMS_LAYOUT_EDITOR=${AMS_LAYOUT_EDITOR}"
```

**IMPORTANT:** All subsequent steps MUST use `$AMS_PYTHON` instead of `python3`.

Parse user input: signal list, ring dimensions (width x height), placement order, inner pad insertions, voltage domain specs.

**Draft Editor override:** If user explicitly requests the visual/draft editor ("I want to use the editor", etc.), set `AMS_DRAFT_EDITOR=on` for this run regardless of `.env`.

### Step 1: Image Input Processing (only if image provided)

1. Load instruction from `references/image_vision_instruction.md` first.
2. Extract structured requirements from image(s):
   - topology (Single/Double ring)
   - counter-clockwise outer-ring signal order
   - pad count description
   - inner-pad insertion directives (if Double Ring)
3. Treat extracted structure as Step 2 input. If user text and image conflict, prefer explicit user text; keep unresolved conflicts in the report.
4. Conventions (unchanged): right side read bottom-to-top; top side read right-to-left; ignore `PFILLER*` devices.

### Step 2: Build Draft JSON (Structural Only)

Reference: `references/draft_builder_T28.md`

1. Parse structural inputs (signal list, width, height, placement_order, inner-pad insertions). If `placement_order`/dimensions/starting-side cannot be uniquely resolved, invoke targeted questions from `references/wizard_T28.md`, then continue.
2. Compute `ring_config`.
3. Generate `instances` for `pad`/`inner_pad` with ONLY: `name`, `position`, `type`.
4. Save to `{output_dir}/io_ring_intent_graph_draft.json`.

**Strict boundary:** Do NOT add `device`, `pin_connection`, `direction`, or any `corner` instance in Step 2.

### Step 2b: Draft Editor (Optional)

**Open when:** `AMS_DRAFT_EDITOR=on` OR user explicitly requested the editor.
**Skip when:** neither condition is true → go straight to Step 3.

Draft Editor lets users drag pads between sides, add/remove pads and corners, optionally set `device` (e.g. PVDD3AC) and `type` (pad/inner_pad), and see live ring validation (closure, corners, side parity).

```bash
$AMS_PYTHON $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph_draft.json \
  {output_dir}/io_ring_draft_confirmed.json \
  --mode draft
```

Launches browser editor in draft mode → waits for "Confirm Draft" click → writes `io_ring_draft_confirmed.json` containing `"editor_mode": "draft"`, instances with `name`/`position`/`type` and optional `device`/`orientation`/`domain`/`direction`/`voltage_domain`. No fillers, no pin connections, no corners unless user added them.

**Merge back before Step 3:** update `io_ring_intent_graph_draft.json` with structural changes (reordering, add/remove, type changes); carry through any user-set `device` fields as **hints** for Step 3; include any corners the user added.

### Step 3: Generate Semantic Intent + Run Enrichment Engine

Reference: `references/enrichment_rules_T28.md` (classification rules, output format §4, override syntax §6 — all in one file).

**Mandatory inputs:**
- Step 2 draft JSON (structural source — immutable)
- Step 2b draft editor output (if opened — device hints carried through)
- Original user prompt (voltage-domain assignment, provider naming, direction overrides, ring ESD declaration)
- `wizard_constraints` (only if wizard ran)

**Input precedence:**
1. Explicit user prompt constraints
2. Draft Editor `device` hints
3. `wizard_constraints`
4. Default classification inference (per `enrichment_rules_T28.md` §5)

**Process:**
1. Per `enrichment_rules_T28.md` §5, decide for each instance: signal class, device (base name, no suffix), domain assignment, direction (digital IO only). Per §4, decide domain providers and global vss_ground / ring_esd.
2. Write `{output_dir}/io_ring_semantic_intent.json` per `enrichment_rules_T28.md` §4 schema. Do NOT include corners (engine generates) and do NOT add `_H_G`/`_V_G` to device names.
3. Run engine:

```bash
$AMS_PYTHON $SCRIPTS_PATH/enrich_intent.py \
  {output_dir}/io_ring_semantic_intent.json \
  {output_dir}/io_ring_intent_graph.json \
  T28
```

- Exit 0 → engine wrote `io_ring_intent_graph.json`; gate results printed to console. Proceed to Step 4.
- Exit 1 → semantic intent input error. Read engine stderr (it includes hint + section pointer), fix semantic intent, re-run.
- Exit 2 → wiring/engine bug. Stop and report.
- Exit 3 → gate failure (semantic mistake — usually misclassification). Read engine stderr for which gate failed and the suggested re-classification, fix semantic intent, re-run.

**Handoff rule:** Treat draft structural fields (`ring_config`, `name`, `position`, `type`) as immutable.

### Step 4: Validate JSON

```bash
$AMS_PYTHON $SCRIPTS_PATH/validate_intent.py {output_dir}/io_ring_intent_graph.json
```

- Exit 0 → proceed to Step 5.
- Exit 1 → engine produced invalid output. Should not happen — report as engine bug.
- Exit 2 → file not found.

(Old "Step 4 gate check" deleted — engine handles gates as part of Step 3. validate_intent.py remains as a final mechanical safety net.)

### Step 5: Build Confirmed Config (Confirmation Editor)

Check `AMS_LAYOUT_EDITOR`:
- `on` → Ask user via `AskUserQuestion`: *"The layout is ready for confirmation. Would you like to open the visual Layout Editor to review and adjust pad placement, fillers, and pin connections before proceeding?"*
  - **Open Layout Editor** — browser editor in confirmation mode (fillers, pins, corners); click "Confirm & Continue" when done.
  - **Skip Editor** — build confirmed config directly (recommended for batch runs).
- `off` → skip automatically, no question.

**Open editor:**
```bash
$AMS_PYTHON $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json
```
This inserts fillers, generates intermediate JSON, opens browser editor, waits for confirm, merges changes back.

**Skip editor:**
```bash
$AMS_PYTHON $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  --skip-editor
```

### Step 6: Generate SKILL Scripts

```bash
$AMS_PYTHON $SCRIPTS_PATH/generate_schematic.py {output_dir}/io_ring_confirmed.json {output_dir}/io_ring_schematic.il T28
$AMS_PYTHON $SCRIPTS_PATH/generate_layout.py    {output_dir}/io_ring_confirmed.json {output_dir}/io_ring_layout.il    T28
```

The scripts automatically add a timestamp to the output filename (e.g. `io_ring_schematic_20260428_181744.il`).
Use the **actual output path printed by each script** in subsequent steps.

### Step 7: Check Virtuoso Connection

```bash
$AMS_PYTHON $SCRIPTS_PATH/check_virtuoso_connection.py
```
- Exit 0 → proceed
- Exit 1 → **STOP**. Report generated files so far; instruct user to start Virtuoso. Do NOT proceed.

### Step 8: Execute SKILL Scripts in Virtuoso

Use the timestamped `.il` filenames printed by Step 6:

```bash
$AMS_PYTHON $SCRIPTS_PATH/run_il_with_screenshot.py {output_dir}/io_ring_schematic_<timestamp>.il {lib} {cell} {output_dir}/schematic_screenshot.png schematic
$AMS_PYTHON $SCRIPTS_PATH/run_il_with_screenshot.py {output_dir}/io_ring_layout_<timestamp>.il    {lib} {cell} {output_dir}/layout_screenshot.png    layout
```

### Step 9: Run DRC

```bash
$AMS_PYTHON $SCRIPTS_PATH/run_drc.py {lib} {cell} layout T28
```
- Exit 0 → Step 10
- Exit 1 → DRC repair loop: read report → map errors to reference rules (continuity/classification, device mapping, pin config, corner typing/order) → fix semantic intent → re-run Steps 5-9. Max 2 attempts; if still failing, stop and report blockers.

### Step 10: Run LVS

```bash
$AMS_PYTHON $SCRIPTS_PATH/run_lvs.py {lib} {cell} layout T28
```
- Exit 0 → Step 11
- Exit 1 → LVS repair loop: identify mismatch class (net/missing device/pin/shorts/opens) → query reference rules → fix semantic intent (check continuity/provider-count gates before pin-level edits) → re-run Steps 3-10. Max 2 attempts; if still failing, stop and report blockers.

### Step 11: Final Report

Structured summary:
- Generated files (JSON, SKILL scripts, screenshots, reports) with paths
- Validation results (pass/fail)
- DRC/LVS results (if applicable)
- Ring statistics (total pads, analog/digital counts, voltage domains)
- Image analysis results (if layout analysis was performed)
- Draft Editor usage (if Step 2b was invoked)

## Task Completion Checklist

**Core Requirements**
- [ ] All signals preserved (including duplicates), order strictly followed
- [ ] Step 2 draft JSON: only `ring_config` + name/position/type
- [ ] Step 2b: Draft Editor opened if `AMS_DRAFT_EDITOR=on` or user requested; skipped otherwise
- [ ] Step 2b: Draft editor output merged back into draft JSON before Step 3
- [ ] Step 3 semantic intent: per-instance device (no suffix), domain, direction (digital IO only); engine generates pin_connection and corners
- [ ] Step 3 reads draft fields (name/position/type + ring_config), not name only
- [ ] Step 3 respects user-specified device hints from Draft Editor

**Workflow**
- [ ] Step 0: Timestamp dir created; `AMS_DRAFT_EDITOR` resolved from .env/user request
- [ ] Wizard callback: invoked ONLY during Step 2/3 when ambiguity detected; runs targeted questions per `references/wizard_T28.md` → `wizard_constraints`
- [ ] Step 2: Draft intent graph generated/saved
- [ ] Step 2b: Draft Editor opened/skipped per setting
- [ ] Step 3: Semantic intent saved; engine produced full intent_graph; all gates passed (check console output)
- [ ] Step 4: Validation Exit 0
- [ ] Step 5: Confirmed config built (AMS_LAYOUT_EDITOR=on → ask user; off → skip)
- [ ] Step 6: SKILL scripts generated
- [ ] Step 7: Virtuoso connection verified
- [ ] Step 8: Scripts executed, screenshots saved
- [ ] Step 9: DRC completed
- [ ] Step 10: LVS completed
- [ ] Step 11: Final report delivered

## .il Script Debugging

When a generated `.il` fails in Step 8, read `references/skill_language_reference.md` for SKILL syntax, Virtuoso API, and common runtime errors before fixing. Typical issues: nil cellview, wrong layer-purpose pairs, unbound variables, mismatched parentheses in prefix notation.

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Scripts not found | Use Option B (absolute path); verify with `ls $SCRIPTS_PATH/validate_intent.py` |
| Virtuoso not connected | Start Virtuoso; do NOT retry SKILL execution |
| .il execution error | Read `references/skill_language_reference.md` for SKILL syntax/runtime errors; fix `.il` file, re-run Step 8 |
| Domain continuity fails | Re-classify signals using ring-wrap continuity first, then re-check digital provider count = 4 unique names |
| Engine error (Step 3 exit 1/3) | Read engine stderr — it includes hint and `enrichment_rules_T28.md` section pointer. Fix semantic intent and re-run engine |
| Validation failure | Should not happen if engine succeeded. If it does, report as engine bug |
| DRC failure | Enter Step 9 repair loop: parse DRC report → query reference rules → fix semantic intent → regenerate and rerun DRC |
| LVS failure | Enter Step 10 repair loop: parse LVS mismatch → return to Step 3 to check/fix semantic intent → rerun Steps 3-10 |
| Draft Editor not opening | Check `AMS_DRAFT_EDITOR` in `.env` or verify user requested it; ensure port is not blocked |
| Draft Editor shows pin connections | Should not happen in draft mode — verify `window.__EDITOR_MODE__` is set to `draft` in server response |

**Repair loop cap (Steps 9/10):** Max 2 attempts. If still failing, stop and report unresolved blockers.

## Directory Structure

```
io-ring-orchestrator-T28/
├── SKILL.md                          # This file
├── .env                              # Skill configuration (edit per deployment)
├── requirements.txt                   # Python requirements (minimal)
│
├── scripts/                          # CLI entry points (each self-contained)
│   ├── enrich_intent.py                  # Step 3 enrichment engine CLI
│   ├── validate_intent.py
│   ├── build_confirmed_config.py       # Supports --mode draft|confirmation
│   ├── generate_schematic.py
│   ├── generate_layout.py
│   ├── check_virtuoso_connection.py
│   ├── run_il_with_screenshot.py
│   ├── run_drc.py
│   ├── run_lvs.py
│   ├── run_pex.py
│   └── README.md
│
├── references/                       # Docs & templates
│   ├── draft_builder_T28.md
│   ├── enrichment_rules_T28.md
│   ├── T28_Technology.md
│   ├── skill_language_reference.md    # SKILL syntax & Virtuoso API
│   ├── intent_graph_minimal.json
│   ├── intent_graph_template.json
│   └── image_vision_instruction.md
│
└── assets/                           # Bundled code (self-contained)
    ├── core/
    │   ├── layout/                     # Layout generation modules
    │   │   ├── enrichment_engine.py      # Step 3 engine (semantic intent → full intent graph)
    │   │   ├── layout_generator.py       # T28 layout generator
    │   │   ├── confirmed_config_builder.py # build_confirmed_config + build_draft_editor_session
    │   │   ├── skill_generator.py
    │   │   ├── auto_filler.py
    │   │   ├── layout_visualizer.py
    │   │   ├── inner_pad_handler.py
    │   │   ├── device_classifier.py
    │   │   ├── position_calculator.py
    │   │   ├── process_node_config.py
    │   │   ├── layout_generator_factory.py
    │   │   ├── filler_generator.py
    │   │   ├── layout_validator.py
    │   │   ├── voltage_domain.py
    │   │   ├── editor_confirm_merge.py
    │   │   └── editor_utils.py           # export_to_editor_json + draft_to_editor_json
    │   ├── schematic/
    │   │   ├── schematic_generator_T28.py
    │   │   └── devices/IO_device_info_T28_parser.py
    │   └── intent_graph/json_validator.py
    │
    ├── layout_editor/                # Browser-based editor
    │   ├── layout_editor.html          # Single-file React editor (draft + confirmation modes)
    │   ├── layout_editor_launcher.py   # HTTP server + browser launcher (--mode draft|confirmation)
    │   └── vendor/                     # React/ReactDOM (served locally)
    │
    ├── utils/                        # bridge_utils.py (Virtuoso bridge), logging_utils.py, visualization.py, banner.py
    │
    ├── skill_code/                   # Virtuoso .il files
    │   ├── screenshot.il
    │   ├── get_cellview_info.il
    │   ├── helper_based_device_T28.il
    │   ├── create_io_ring_lib_full.il
    │   └── create_schematic_cv.il
    │
    ├── device_info/                  # IO_device_info_T28.json + IO_device_info_T28_parser.py + device_wiring_T28.json (engine wiring table)
    │
    └── external_scripts/calibre/     # run_drc.csh, run_lvs.csh, run_pex.csh, T28/
# Virtuoso TCP bridge + SSH transfer: virtuoso-bridge-lite (installed separately; see README.md Prerequisites).
```
