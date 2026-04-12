---
name: io-ring-orchestrator-T28
description: Master coordinator for complete T28 (28nm) IO Ring generation. Handles signal classification, device mapping, pin configuration, JSON generation, and complete workflow through DRC/LVS verification. Use this skill for any T28 IO Ring generation task.
---

# IO Ring Orchestrator - T28

You are the master coordinator for T28 IO Ring generation. You handle the **entire** workflow as a single skill — from parsing requirements through DRC/LVS verification.

## Scripts Path verification

```bash

SCRIPTS_PATH="/absolute_path/to/io-ring-orchestrator-T28/scripts"

# Verify:
ls "$SCRIPTS_PATH/validate_intent.py" || echo "ERROR: SCRIPTS_PATH not found"
```

## Entry Points

- **User provides text requirements only** → Start at Step 0, then continue directly to Step 2 (Draft) and Step 3 (Enrichment)
- **User provides image input (with or without text)** → Start at Step 0, then run Step 1 (Image Input Processing), then continue directly to Step 2 (Draft) and Step 3 (Enrichment)
- **User provides draft intent graph file** → Skip to Step 3 (Enrichment)
- **User provides final intent graph file** → Skip to Step 5 (Validation)
- Determine entry path automatically. Do NOT run any pre-step wizard eligibility/opt-in flow.

## Output Path Contract (Mandatory)

- Use a single workspace output root for the entire run.
- Create `output_dir` exactly once per run and reuse it for all Step 2-9 artifacts.
- Do not regenerate `timestamp` after Step 0.
- Export `AMS_OUTPUT_ROOT` once in Step 0 so script-level outputs remain deterministic.

Required conventions:

- `AMS_OUTPUT_ROOT`: workspace-level output root
- `output_dir`: per-run directory under `${AMS_OUTPUT_ROOT}/generated/${timestamp}`
- DRC/LVS reports: `${AMS_OUTPUT_ROOT}` and its fixed subdirs (`drc`, `lvs`)

## Complete Workflow

### Step 0: Directory Setup & Parse Input

**IMPORTANT**: Before setting up any paths, read and source the `.env` file located in this skill's directory. The `.env` file contains critical configuration including `AMS_OUTPUT_ROOT`, `CDS_LIB_PATH_28`, and bridge connection settings. These values MUST take precedence over defaults.

```bash
# 1. Source .env from skill directory FIRST (values here override defaults)
SKILL_DIR="<skill_directory>"   # e.g. .claude/skills/io-ring-orchestrator-T28
set -a; source "${SKILL_DIR}/.env" 2>/dev/null || true; set +a

# 2. Resolve stable workspace root (prefer AMS_IO_AGENT_PATH, fallback to current directory)
if [ -n "${AMS_IO_AGENT_PATH:-}" ]; then
  WORK_ROOT="${AMS_IO_AGENT_PATH}"
else
  WORK_ROOT="$(pwd)"
fi

# 3. Unified output root: prefer .env AMS_OUTPUT_ROOT, then fallback to ${WORK_ROOT}/output
if [ -z "${AMS_OUTPUT_ROOT:-}" ]; then
  export AMS_OUTPUT_ROOT="${WORK_ROOT}/output"
fi
mkdir -p "${AMS_OUTPUT_ROOT}/generated"

# Create per-run directory once and reuse it across all steps
if [ -n "${output_dir:-}" ] && [ -d "${output_dir}" ]; then
  echo "Reusing existing output_dir: ${output_dir}"
else
  timestamp="${timestamp:-$(date +%Y%m%d_%H%M%S)}"
  output_dir="${AMS_OUTPUT_ROOT}/generated/${timestamp}"
fi

mkdir -p "$output_dir"
echo "AMS_OUTPUT_ROOT=${AMS_OUTPUT_ROOT}"
echo "output_dir=${output_dir}"
```

Parse user input: signal list, ring dimensions (width × height), placement order, inner pad insertions, voltage domain specifications.

### Step 1: Image Input Processing Rules (Before Step 2)

Apply this step only when image input is provided.

Rules:

1. Load image-analysis instruction from `references/image_vision_instruction.md` first.
2. Use the instruction to extract structured requirements from image(s):
  - topology (Single/Double ring)
  - counter-clockwise outer-ring signal order
  - pad count description
  - inner-pad insertion directives (if Double Ring)
3. Treat extracted structure as Step 2 input. If user text and image conflict, prefer explicit user text constraints and keep unresolved conflicts explicit in the report.
4. Keep extraction/output conventions unchanged:
  - right side is read bottom-to-top
  - top side is read right-to-left
  - ignore `PFILLER*` devices

### Step 2: Build Draft JSON (Structural Only)

Build a draft JSON with only structural fields. No device/pin/corner inference in this step.

Primary reference:

- `references/draft_builder_T28.md`

Process:

1. Parse user structural inputs (signal list, width, height, placement_order, inner-pad insertions).
  - If `placement_order`/dimensions/starting-side mapping cannot be uniquely resolved, invoke targeted questions from `references/wizard_T28.md`, then continue.
2. Compute `ring_config`.
3. Generate `instances` for `pad`/`inner_pad` with only:
  - `name`
  - `position`
  - `type`
4. Save draft to `{output_dir}/io_ring_intent_graph_draft.json`.

Strict boundary:

- Do NOT add `device`, `pin_connection`, `direction`, or any `corner` instance in Step 2.

### Step 3: Enrich Draft JSON to Final Intent Graph

Read the Step 2 draft and enrich in a single pass.

Mandatory inputs for Step 3:

- Step 2 draft JSON (primary source for structural fields)
- Original user prompt (source for explicit intent not encoded structurally, such as voltage-domain assignment, provider naming, digital pin-domain naming, and direction overrides)
- `wizard_constraints` object only if ambiguity was encountered and targeted questions were invoked during Step 2/3

Input precedence:

- Keep structural fields from Step 2 draft immutable (`ring_config`, `name`, `position`, `type`) unless a hard inconsistency is reported.
- Apply constraints in this order when they do not conflict with immutable draft structure:
  1. Explicit user prompt constraints
  2. `wizard_constraints`
  3. Enrichment default inference

Primary reference:

- `references/enrichment_rules_T28.md`

Process:

1. Read `ring_config` and all draft instances (`name`, `position`, `type`) and user prompt constraints.
  - If ambiguity is detected during enrichment, invoke targeted questions, merge returned constraints, then continue enrichment.
2. Add per-instance `device` (and `direction` for digital IO).
3. Add per-instance `pin_connection`.
4. Insert 4 corners with correct type/order.
5. Run pre-save rule gates (must pass before saving), as defined in `references/enrichment_rules_T28.md`:
  - Continuity gate
  - Provider-count gate
  - Position-identity gate
  - Pin-family gate
  - VSS-consistency gate
6. Save final JSON to `{output_dir}/io_ring_intent_graph.json`.

Handoff rule:

- Treat draft structural fields as immutable unless a hard inconsistency must be reported.

### Step 4: Reference-Guided Gate Check (Mandatory)

Before Step 5 validation, explicitly verify Step 3 output against references:

- `references/enrichment_rules_T28.md` -> Priority, Domain Continuity, Position-Based Identity, Digital Provider Count
- `references/enrichment_rules_T28.md` -> Analog Pins, Digital Pins, Universal VSS Rule, Direction Rules
- `references/enrichment_rules_T28.md` -> Corner Rules

Also verify that Step 3 output preserves explicit constraints from the original user prompt (especially voltage-domain ranges, provider names, digital domain names, and direction overrides).

If `wizard_constraints` exists, also verify every override in `wizard_constraints` is reflected in the Step 3 output.

If any gate fails, repair JSON first and repeat Step 4. Do not proceed to Step 5.


### Step 5: Validate JSON

```bash
python3 $SCRIPTS_PATH/validate_intent.py {output_dir}/io_ring_intent_graph.json
```

- Exit 0 → proceed
- Exit 1 → enter repair loop:
  1. Read validator error messages carefully.
  2. Go back to references and query the matching rules (`references/draft_builder_T28.md` or `references/enrichment_rules_T28.md`).
  3. Apply targeted JSON fixes only for reported issues.
  4. Run validator again.
  5. Repeat until Exit 0 or a blocking inconsistency is found (then stop and report clearly).
- Exit 2 → file not found

Validation repair constraints:

- Do NOT regenerate the whole JSON unless structure is fundamentally broken.
- Preserve Step 2 immutable fields (`ring_config`, `name`, `position`, `type`) during repair.
- Every fix must be traceable to an explicit validator error and a reference rule.
- If continuity/provider-count gates fail during repair, fix classification first, then device/pin labels.

### Step 6: Build Confirmed Config

```bash
python3 $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  T28 \
  --skip-editor
```

### Step 7: Generate SKILL Scripts

```bash
python3 $SCRIPTS_PATH/generate_schematic.py \
  {output_dir}/io_ring_confirmed.json \
  {output_dir}/io_ring_schematic.il \
  T28

python3 $SCRIPTS_PATH/generate_layout.py \
  {output_dir}/io_ring_confirmed.json \
  {output_dir}/io_ring_layout.il \
  T28
```

### Step 8: Check Virtuoso Connection

```bash
python3 $SCRIPTS_PATH/check_virtuoso_connection.py
```

- Exit 0 → proceed
- Exit 1 → **STOP**. Report all generated files so far and instruct user to start Virtuoso. Do NOT proceed.

### Step 9: Execute SKILL Scripts in Virtuoso

```bash
python3 $SCRIPTS_PATH/run_il_with_screenshot.py \
  {output_dir}/io_ring_schematic.il \
  {lib} {cell} \
  {output_dir}/schematic_screenshot.png \
  schematic

python3 $SCRIPTS_PATH/run_il_with_screenshot.py \
  {output_dir}/io_ring_layout.il \
  {lib} {cell} \
  {output_dir}/layout_screenshot.png \
  layout
```

### Step 10: Run DRC

```bash
python3 $SCRIPTS_PATH/run_drc.py {lib} {cell} layout T28
```

- Exit 0 -> proceed to Step 11
- Exit 1 -> enter DRC repair loop:
  1. Read DRC report and extract failing rule/check locations.
  2. Map each error to reference rules (continuity/classification, device mapping, pin configuration, corner typing/order).
  3. Fix the source intent JSON first (`io_ring_intent_graph.json`), then re-run Step 6-10 to regenerate and recheck.
  4. Repeat until DRC passes, but allow at most 2 repair attempts; if still failing, stop and report the unresolved DRC blockers.

### Step 11: Run LVS

```bash
python3 $SCRIPTS_PATH/run_lvs.py {lib} {cell} layout T28
```

- Exit 0 -> proceed to Step 12
- Exit 1 -> enter LVS repair loop:
  1. Read LVS report and identify mismatch class (net mismatch, missing device, pin mismatch, shorts/opens).
  2. Query matching reference rules and locate the root cause in intent JSON (check continuity/provider-count gates before pin-level edits).
  3. Fix intent JSON by returning to Step 3 checks/fixes first, then re-run Step 3-12 (enrich, gate-check, validate, build, generate, execute, DRC, LVS, final report).
  4. Repeat until LVS passes, but allow at most 2 repair attempts; if still failing, stop and report the unresolved LVS blockers.

### Step 12: Final Report

Provide structured summary:
- Generated files (JSON, SKILL scripts, screenshots, reports) with paths
- Validation results (pass/fail)
- DRC/LVS results (if applicable)
- Ring statistics (total pads, analog/digital counts, voltage domains)
- Image analysis results (if layout analysis was performed)

## Task Completion Checklist

### Core Requirements
- [ ] All signals preserved (including duplicates), order strictly followed
- [ ] Step 2 draft JSON generated with only ring_config + name/position/type
- [ ] Step 3 enrichment completed (device/pin_connection/direction/corners)
- [ ] Step 3 reads draft JSON fields (name/position/type + ring_config), not name only

### Workflow
- [ ] Step 0: Timestamp directory created
- [ ] Wizard question callback: Only invoked during Step 2/3 when ambiguity is detected
- [ ] Wizard question callback: If invoked — run targeted questions per `references/wizard_T28.md` and assemble `wizard_constraints`
- [ ] Step 2: Draft intent graph generated and saved
- [ ] Step 3: Final intent graph generated from draft and saved
- [ ] Step 4: Reference-guided gate check passed
- [ ] Step 5: Validation passed (exit 0)
- [ ] Step 6: Confirmed config built
- [ ] Step 7: SKILL scripts generated
- [ ] Step 8: Virtuoso connection verified before execution
- [ ] Step 9: Scripts executed, screenshots saved
- [ ] Step 10: DRC completed
- [ ] Step 11: LVS completed
- [ ] Step 12: Final report delivered

## .il Script Debugging

When a generated `.il` script fails during Step 9 execution, read `references/skill_language_reference.md` for SKILL language syntax, Virtuoso API, and common runtime errors before attempting fixes. Typical issues: nil cellview, wrong layer-purpose pairs, unbound variables, mismatched parentheses in prefix notation.

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Scripts not found | Use Option B (absolute path); verify with `ls $SCRIPTS_PATH/validate_intent.py` |
| Virtuoso not connected | Start Virtuoso; do NOT retry SKILL execution |
| .il execution error | Read `references/skill_language_reference.md` for SKILL syntax and common runtime errors; fix the generated `.il` file, then re-run Step 9 |
| Domain continuity fails | Re-classify signals using ring-wrap continuity first, then re-check digital provider count = 4 unique names |
| Validation failure | Enter Step 5 repair loop: parse error -> query matching rule in references -> apply targeted JSON fix -> re-validate; common issues: missing pins, wrong suffixes, duplicate indices |
| DRC failure | Enter Step 10 repair loop: parse DRC report -> query matching reference rules -> fix intent JSON -> regenerate and rerun DRC |
| LVS failure | Enter Step 11 repair loop: parse LVS mismatch -> return to Step 3 to check/fix intent JSON -> rerun Step 3-12 |

Repair loop cap (applies to Step 10/11):

- Maximum 2 repair attempts per loop. If still failing after attempt 2, stop the loop and report unresolved blockers.

## Directory Structure

```
io-ring-orchestrator-T28/
├── SKILL.md                          # This file
├── requirements.txt                   # Python requirements (minimal)
│
├── scripts/                          # CLI entry point scripts (each self-contained)
│   ├── validate_intent.py
│   ├── build_confirmed_config.py
│   ├── generate_schematic.py
│   ├── generate_layout.py
│   ├── check_virtuoso_connection.py
│   ├── run_il_with_screenshot.py
│   ├── run_drc.py
│   ├── run_lvs.py
│   ├── run_pex.py
│   └── README.md
│
├── references/                       # Documentation & templates
│   ├── draft_builder_T28.md
│   ├── enrichment_rules_T28.md
│   ├── T28_Technology.md
│   ├── skill_language_reference.md    # SKILL language syntax & Virtuoso API reference
│   ├── intent_graph_minimal.json
│   ├── intent_graph_template.json
│   └── image_vision_instruction.md
│
└── assets/                          # All bundled code (self-contained)
    ├── core/                         # Core logic
    │   ├── layout/                    # Layout generation modules
    │   │   ├── layout_generator.py      # T28 layout generator
    │   │   ├── confirmed_config_builder.py
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
    │   │   └── editor_utils.py
    │   ├── schematic/
    │   │   ├── schematic_generator_T28.py
    │   │   └── devices/
    │   │       └── IO_device_info_T28_parser.py
    │   └── intent_graph/
    │       └── json_validator.py
    │
    ├── utils/                        # Utility modules
    │   ├── bridge_utils.py           # Virtuoso bridge
    │   ├── logging_utils.py
    │   ├── visualization.py
    │   └── banner.py
    │
    ├── skill_code/                   # Virtuoso SKILL files (.il)
    │   ├── screenshot.il
    │   ├── get_cellview_info.il
    │   ├── helper_based_device_T28.il
    │   ├── create_io_ring_lib_full.il
    │   └── create_schematic_cv.il
    │
    ├── device_info/                  # Device templates
    │   ├── IO_device_info_T28.json
    │   └── IO_device_info_T28_parser.py
    │
    └── external_scripts/             # External executables
        ├── calibre/
        │   ├── T28/
        │   ├── run_drc.csh
        │   ├── run_lvs.csh
        │   └── run_pex.csh
        └── ramic_bridge/
            ├── ramic_bridge.py
            ├── ramic_bridge.il
            └── ramic_bridge_daemon_27.py
```
