---
name: t28-ioring-generator
description: Generate T28 28nm IO rings from text or image requirements. Handles signal classification, device mapping, semantic intent generation, confirmed layout config, Cadence SKILL script generation, Virtuoso schematic/layout execution, screenshots, and DRC/LVS/PEX verification. Use for T28 IO ring generation, layout, schematic, DRC, LVS, or PEX tasks; use t28-ioring-simulator for simulation testbench and Spectre workflows.
---

# T28 IO Ring Generator

Generate T28 IO ring schematic/layout artifacts from requirements and verify the result through Virtuoso and Calibre.

Use this skill for generation. Use `t28-ioring-simulator` for testbench construction, pin stimulus/load placement, Spectre, and Maestro setup.

## Output Contract

Use one shared output root:

```bash
AMS_OUTPUT_ROOT="${AMS_OUTPUT_ROOT:-<repo-root>/output}"
```

Generation artifacts go under:

```text
${AMS_OUTPUT_ROOT}/generated/<YYYYMMDD_HHMMSS>/
```

Verification artifacts go under:

```text
${AMS_OUTPUT_ROOT}/drc/
${AMS_OUTPUT_ROOT}/lvs/
${AMS_OUTPUT_ROOT}/pex/
```

Create `output_dir` once at Step 0 and reuse it for the full run. Do not regenerate the timestamp mid-flow.

## Step 0: Environment Setup

Auto-detect paths from this skill root. Do not hard-code install paths.

```bash
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_PATH="${SKILL_ROOT}/scripts"
export PYTHONPATH="${SKILL_ROOT}:${PYTHONPATH:-}"

if [ -n "${AMS_IO_AGENT_PATH:-}" ]; then WORK_ROOT="${AMS_IO_AGENT_PATH}"; else WORK_ROOT="$(pwd)"; fi

if [ -z "${AMS_OUTPUT_ROOT:-}" ]; then
  export AMS_OUTPUT_ROOT="${WORK_ROOT}/output"
fi
mkdir -p "${AMS_OUTPUT_ROOT}/generated"

if [ -n "${output_dir:-}" ] && [ -d "${output_dir}" ]; then
  echo "Reusing existing output_dir: ${output_dir}"
else
  timestamp="${timestamp:-$(date +%Y%m%d_%H%M%S)}"
  output_dir="${AMS_OUTPUT_ROOT}/generated/${timestamp}"
fi
mkdir -p "$output_dir"

PROJECT_ROOT="$(cd "${SKILL_ROOT}" && while [ ! -d .venv ] && [ "$(pwd)" != "/" ]; do cd ..; done; pwd)"
if   [ -f "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]; then export AMS_PYTHON="${PROJECT_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${PROJECT_ROOT}/.venv/bin/python" ];         then export AMS_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${SKILL_ROOT}/.venv/Scripts/python.exe" ];   then export AMS_PYTHON="${SKILL_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${SKILL_ROOT}/.venv/bin/python" ];           then export AMS_PYTHON="${SKILL_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1;                then export AMS_PYTHON="python3"
elif command -v python  >/dev/null 2>&1;                then export AMS_PYTHON="python"
else echo "ERROR: No Python 3.9+ found."; return 1; fi

[ -f "${SKILL_ROOT}/.env.local" ] && { set -a; . "${SKILL_ROOT}/.env.local"; set +a; }
[ -f "${SKILL_ROOT}/.env" ] && { set -a; . "${SKILL_ROOT}/.env"; set +a; }

[ "${AMS_DRAFT_EDITOR:-}" = "on" ] || export AMS_DRAFT_EDITOR="off"
[ "${AMS_LAYOUT_EDITOR:-}" = "on" ] || export AMS_LAYOUT_EDITOR="off"
```

All subsequent commands use `$AMS_PYTHON`.

Required generator configuration:

- `CDS_LIB_PATH_28`
- `VB_FS_MODE` if auto-detection is insufficient
- Calibre site config in `calibre/site_local.csh` for DRC/LVS/PEX

Optional:

- `AMS_OUTPUT_ROOT`
- `AMS_DRAFT_EDITOR`
- `AMS_LAYOUT_EDITOR`

## Entry Points

| User input | Start |
|---|---|
| Text requirements only | Step 1 |
| Image input | Read `references/image_vision_instruction.md`, then Step 1 |
| Draft intent graph provided | Step 3 |
| Final intent graph provided | Step 4 |
| Confirmed config provided | Step 6 |

If the user explicitly requests a visual or draft editor, set `AMS_DRAFT_EDITOR=on` for this run.

## Step 1: Build Draft Intent JSON

Read structural requirements:

- signal list
- ring dimensions or pads per side
- single ring or double ring
- placement order
- inner-pad insertion directives
- library and cell names

Use `references/draft_builder_T28.md`.

Write:

```text
{output_dir}/io_ring_intent_graph_draft.json
```

The draft JSON must contain only structural data:

- `ring_config`
- instance `name`
- instance `position`
- instance `type`

Do not add `device`, `pin_connection`, `direction`, or generated corners in the draft.

## Step 2: Optional Draft Editor

Open only if `AMS_DRAFT_EDITOR=on` or the user explicitly asks for the editor.

```bash
$AMS_PYTHON "$SCRIPTS_PATH/build_confirmed_config.py" \
  "$output_dir/io_ring_intent_graph_draft.json" \
  "$output_dir/io_ring_draft_confirmed.json" \
  --mode draft
```

The draft editor may add device hints and structural edits. Merge those edits back into the draft before semantic enrichment.

## Step 3: Generate Semantic Intent and Enrich

Read:

- `references/enrichment_rules_T28.md`
- draft JSON
- original user prompt
- draft editor output if Step 2 ran

Write semantic intent:

```text
{output_dir}/io_ring_semantic_intent.json
```

Semantic intent must include per-instance device/domain/direction decisions but must not include generated corners or `_H_G` / `_V_G` device suffixes.

Run the enrichment engine:

```bash
$AMS_PYTHON "$SCRIPTS_PATH/enrich_intent.py" \
  "$output_dir/io_ring_semantic_intent.json" \
  "$output_dir/io_ring_intent_graph.json" \
  T28
```

Exit handling:

- `0`: proceed.
- `1`: semantic input error; read stderr, fix semantic intent, rerun.
- `2`: engine/wiring bug; stop and report.
- `3`: gate failure; fix semantic classification and rerun.

## Step 4: Validate Intent JSON

```bash
$AMS_PYTHON "$SCRIPTS_PATH/validate_intent.py" "$output_dir/io_ring_intent_graph.json"
```

Exit handling:

- `0`: proceed.
- `1`: invalid output; report as engine or schema bug unless input was manually edited.
- `2`: file not found.

## Step 5: Build Confirmed Config

If `AMS_LAYOUT_EDITOR=on`, ask whether to open the confirmation editor. If it is off, skip automatically.

Open editor:

```bash
$AMS_PYTHON "$SCRIPTS_PATH/build_confirmed_config.py" \
  "$output_dir/io_ring_intent_graph.json" \
  "$output_dir/io_ring_confirmed.json"
```

Skip editor:

```bash
$AMS_PYTHON "$SCRIPTS_PATH/build_confirmed_config.py" \
  "$output_dir/io_ring_intent_graph.json" \
  "$output_dir/io_ring_confirmed.json" \
  --skip-editor
```

## Step 6: Generate Cadence SKILL Scripts

```bash
$AMS_PYTHON "$SCRIPTS_PATH/generate_schematic.py" "$output_dir/io_ring_confirmed.json" "$output_dir/io_ring_schematic.il" T28
$AMS_PYTHON "$SCRIPTS_PATH/generate_layout.py"    "$output_dir/io_ring_confirmed.json" "$output_dir/io_ring_layout.il"    T28
```

The scripts add timestamps to output filenames. Use the actual printed paths in later steps.

## Step 7: Check Virtuoso Connection

```bash
$AMS_PYTHON "$SCRIPTS_PATH/check_virtuoso_connection.py"
```

If this fails, stop. Report generated files so far and instruct the user to start or repair Virtuoso bridge connectivity.

## Step 8: Execute SKILL in Virtuoso

Use the timestamped `.il` paths printed in Step 6:

```bash
$AMS_PYTHON "$SCRIPTS_PATH/run_il_with_screenshot.py" "$schematic_il" "$lib" "$cell" "$output_dir/schematic_screenshot.png" schematic
$AMS_PYTHON "$SCRIPTS_PATH/run_il_with_screenshot.py" "$layout_il"    "$lib" "$cell" "$output_dir/layout_screenshot.png"    layout
```

If a generated `.il` fails, read `references/skill_language_reference.md` before fixing SKILL syntax or Virtuoso API usage.

## Step 9: Run DRC

```bash
$AMS_PYTHON "$SCRIPTS_PATH/run_drc.py" "$lib" "$cell" layout T28
```

On failure, follow the repair loop:

1. Read the DRC report.
2. Map errors to continuity, classification, device mapping, pin config, corner typing, or order.
3. Prefer semantic intent/config fixes before generator code edits.
4. Regenerate and rerun.

Maximum two repair attempts.

## Step 10: Run LVS

```bash
$AMS_PYTHON "$SCRIPTS_PATH/run_lvs.py" "$lib" "$cell" layout T28
```

On failure, identify mismatch class:

- net mismatch
- missing device
- pin mismatch
- shorts
- opens

Prefer semantic intent or confirmed config repair before pin-level generator changes. Maximum two repair attempts.

## Optional: Run PEX

```bash
$AMS_PYTHON "$SCRIPTS_PATH/run_pex.py" "$lib" "$cell" layout T28
```

Run PEX only after LVS is clean or when the user explicitly asks.

## Completion Checklist

- [ ] All user signals preserved, including duplicates.
- [ ] Draft JSON contains only structural fields.
- [ ] Semantic intent follows `enrichment_rules_T28.md`.
- [ ] Enrichment engine exits `0`.
- [ ] `validate_intent.py` exits `0`.
- [ ] Confirmed config written.
- [ ] Schematic/layout SKILL scripts generated.
- [ ] Virtuoso connection checked.
- [ ] SKILL scripts executed and screenshots captured.
- [ ] DRC/LVS results reported if requested.
- [ ] Final report includes generated JSON, SKILL, screenshots, reports, and output paths.
