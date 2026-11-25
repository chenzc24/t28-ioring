---
name: t28-ioring-generator
description: Generate T28 28nm IO rings from text or image requirements. Handles signal classification, device mapping, semantic intent generation, confirmed layout config, Cadence SKILL script generation, Virtuoso schematic/layout execution, screenshots, and DRC/LVS/PEX verification. Use for T28 IO ring generation, layout, schematic, DRC, LVS, or PEX tasks; use t28-ioring-simulator for simulation testbench and Spectre workflows.
---

# T28 IO Ring Generator

Generate T28 IO ring schematic/layout artifacts from requirements and verify the result through Virtuoso and Calibre.

Use this skill for generation. Use `t28-ioring-simulator` for testbench construction, pin stimulus/load placement, Spectre, and Maestro setup.

## Design choices

Use the application note and the bundled checks as recommendations. Preserve user-selected masters, nets, placements and verification settings. Record deviations in the run report and continue the requested stages. A user can start from a semantic plan, an edited intent graph or a confirmed layout.

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

For individual commands create one run directory at the start. Use the absolute paths returned by that run for all later stages.

## Step 0. Locate the tools

Use the repository checkout containing `tools/t28_config_check.py` and the sibling skills. Set `AMS_PYTHON` to the workspace Python executable and `SCRIPTS_PATH` to this skill’s `scripts` directory and use the Python interpreter with the workspace EDA dependencies. Run `python tools/t28_config_check.py` before live EDA. Site settings are in `_local/site.yaml`. The bridge reads its connection from `~/.virtuoso-bridge/.env`.

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

For a new draft, start with the structural fields:

- `ring_config`
- instance `name`
- instance `position`
- instance `type`

When an input already specifies devices or wiring, keep those choices in the semantic plan or resolved graph.

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

The usual semantic plan supplies pad masters, domains and IO directions. Explicit corners and `_H_G` / `_V_G` device suffixes take precedence over automatic choices.

For the normal headless flow, compile the semantic intent in one command (from the repository root).

```sh
python skills/t28-ioring-generator/scripts/prepare_ring.py io_ring_semantic_intent.json
```

Each invocation creates its own run directory and prints the path to `run.json`. Read the manifest for the input digest, generated filenames, design recommendations and pending integration measurements. A failed stage returns nonzero. A prepared run resumes at Step 7 if live OA execution was requested. If an editor or an existing intermediate file is involved, use the individual stages below.

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

## Step 4: Validate Intent JSON

```bash
$AMS_PYTHON "$SCRIPTS_PATH/validate_intent.py" "$output_dir/io_ring_intent_graph.json"
```

Exit handling:

- `0`: proceed.
- Design findings appear in the output and generation continues.
- `2`: file not found.

## Step 5: Build Confirmed Config

Open the editor when requested or enabled in the site settings. Use headless confirmation otherwise.

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

If the GUI bridge is unavailable, use the configured batch Virtuoso workflow when available, or report which live stages could not execute.

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

Record the DRC count and scope. Continue with LVS or other stages requested by the user. If a design change is requested, inspect the rule and coordinates before changing the layout.

## Step 10: Run LVS

Record the library, cell, view and source netlist for this comparison. When checking a project regression, match the planned pad masters and positions to the revision that the integration script uses. If two pads share a signal, locate the metal and vias that join them. When the join runs through the parent or core, verify that path at the routed assembly top using its matching source and deck. Report the cell and assembly verdicts separately. After replacing an existing ring, check the parent’s pad landings and labels against the new pin coordinates.

```bash
$AMS_PYTHON "$SCRIPTS_PATH/run_lvs.py" "$lib" "$cell" layout T28 --intent "$output_dir/io_ring_confirmed.json"
```

Each invocation records raw summaries and result.json in its own directory. The exit code indicates whether execution and report collection completed. Report the DRC count, LVS comparison and ERC counts separately. The default LVS wrapper virtually connects listed supply rails. Supply a local wrapper with --deck to use the project’s own verification settings.

For chip DRC, pass `--chip-deck /eda/path/to/release_matched_full_chip_deck` to `run_drc.py` and select the chip top. Review the effective deck and any foundry-specific exclusions. Refer to the chip integration evidence in `references/enrichment_rules_T28.md` before reporting chip signoff.

## Optional: Run PEX

```bash
$AMS_PYTHON "$SCRIPTS_PATH/run_pex.py" "$lib" "$cell" layout T28
```

Run PEX when requested. Include the latest LVS comparison as context.

## Completion Checklist

- [ ] All user signals preserved, including duplicates.
- [ ] The generated design preserves supplied placement, device and wiring choices.
- [ ] Semantic intent follows `enrichment_rules_T28.md`.
- [ ] Enrichment engine exits `0`.
- [ ] `validate_intent.py` exits `0`.
- [ ] Confirmed config written.
- [ ] Schematic/layout SKILL scripts generated.
- [ ] Virtuoso connection checked.
- [ ] SKILL scripts executed and screenshots captured.
- [ ] DRC/LVS results reported if requested.
- [ ] Final report includes generated JSON, SKILL, screenshots, reports, and output paths.
