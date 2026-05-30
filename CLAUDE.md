# Claude Code Instructions

This file intentionally mirrors `AGENTS.md` so Claude Code receives the same
engineering guardrails as other coding agents. Keep both files in sync.

This repository is a T28 IO ring suite. It contains two preferred sibling skills under `skills/`:

- `t28-ioring-generator`
- `t28-ioring-simulator`

Treat both workflows as high-risk EDA automation. Small changes can create invalid layouts, bad schematic connectivity, DRC/LVS failures, or misleading simulation results.

## Registration

Prefer registering `skills/` as the Agent skills root, or copying/symlinking the two child skill folders into the normal skills root.

Do not register the repository root as a single skill. Use these explicit skill roots:

```text
skills/t28-ioring-generator/
skills/t28-ioring-simulator/
```

Root-level historical copies of generator code may be removed after migration. Agents must not rely on root-level `SKILL.md`, `scripts/`, `io_ring/`, `calibre/`, `references/`, `skill_code/`, or `T28_Testbench/`.

## Output Rules

Use the shared output root:

```text
${AMS_OUTPUT_ROOT}/generated/<timestamp>/
${AMS_OUTPUT_ROOT}/simulation/<timestamp>/
${AMS_OUTPUT_ROOT}/simulation/.latest_run
${AMS_OUTPUT_ROOT}/drc/
${AMS_OUTPUT_ROOT}/lvs/
${AMS_OUTPUT_ROOT}/pex/
```

Generated files under `output/` are artifacts, not source of truth. It is acceptable to inspect and regenerate them. Do not patch generated files as the only fix unless the user explicitly asks for a one-off repair.

## Configuration

Keep generator and simulator `.env` files separate.

Generator-specific variables belong in `skills/t28-ioring-generator/.env`:

```text
CDS_LIB_PATH_28
VB_FS_MODE
AMS_DRAFT_EDITOR
AMS_LAYOUT_EDITOR
AMS_OUTPUT_ROOT
```

Simulator-specific variables belong in `skills/t28-ioring-simulator/.env`:

```text
SIM_CDS_LIB
SIM_IC_ROOT
SIM_MMSIM_ROOT
SIM_LM_LICENSE_FILE
SIM_CDS_LIC_FILE
SIM_PDK_IO_SPECTRE_INCLUDE
SIM_PDK_CORE_SPECTRE_INCLUDE
SIM_PDK_CORE_SPECTRE_SECTIONS
AMS_OUTPUT_ROOT
VB_DISABLE_CONTROL_MASTER
```

The simulator may fall back from `SIM_CDS_LIB` to `CDS_LIB_PATH_28`. Do not introduce a mandatory common `.env` unless several more variables become genuinely shared.
Use `VB_DISABLE_CONTROL_MASTER=1` on Windows/OpenSSH jump-host setups to avoid stale mux socket failures during direct Spectre uploads.

## Generator Guardrails

Follow `skills/t28-ioring-generator/SKILL.md` for workflow order, exit-code handling, and DRC/LVS repair-loop limits.

Preserve user intent:

- signal names
- duplicates
- side order
- voltage domains
- explicitly provided device hints

Do not silently change:

- device mapping
- pin schema
- corner or filler behavior
- domain-continuity rules
- DRC/LVS rule interpretation

Before editing generator core code, collect:

- failing command
- failing step number
- input JSON path
- stderr/log excerpt
- suspected root cause
- why semantic-intent, generated-output, or configuration repair is insufficient
- proposed minimal code change

Core generator code includes:

```text
skills/t28-ioring-generator/scripts/enrich_intent.py
skills/t28-ioring-generator/scripts/generate_layout.py
skills/t28-ioring-generator/scripts/generate_schematic.py
skills/t28-ioring-generator/scripts/build_confirmed_config.py
skills/t28-ioring-generator/scripts/run_drc.py
skills/t28-ioring-generator/scripts/run_lvs.py
skills/t28-ioring-generator/scripts/run_pex.py
skills/t28-ioring-generator/io_ring/
skills/t28-ioring-generator/skill_code/
skills/t28-ioring-generator/references/
```

Prefer the earliest safe repair:

1. semantic intent JSON or draft data
2. local configuration and environment paths
3. confirmed config regeneration
4. schematic/layout SKILL regeneration
5. core engine or generator code

## Simulator Guardrails

Follow `skills/t28-ioring-simulator/SKILL.md` for symbol export, pin intent authoring, testbench build, and Spectre run order.

Do not skip the LLM authoring step for real validation:

1. Read `references/pin_classification.md`.
2. Read `<run_dir>/pin_info.json`.
3. Write `<run_dir>/pin_classifications.json`.
4. Read `references/sim_config_rules.md`.
5. Write `<run_dir>/sim_config.json`.

Treat these as high-risk simulator logic:

```text
skills/t28-ioring-simulator/sim_io/pin_types.py
skills/t28-ioring-simulator/sim_io/flow.py
skills/t28-ioring-simulator/sim_io/sim/
skills/t28-ioring-simulator/sim_io/maestro/
skills/t28-ioring-simulator/skill_code/
skills/t28-ioring-simulator/references/pin_classification.md
skills/t28-ioring-simulator/references/sim_config_rules.md
```

Before editing simulator core code, rule out:

1. stale or missing `pin_classifications.json`
2. stale or missing `sim_config.json`
3. wrong `SIM_CDS_LIB` or `CDS_LIB_PATH_28`
4. missing model include paths
5. Virtuoso bridge or Spectre license/environment issues

Simulation verification source is the direct Spectre route:

```text
sim_run_result.json
measurements.json
plots/
spectre/spectre.out
```

Do not treat Maestro GUI state as the primary verification source for direct Spectre runs.

## Validation

After any code change, run the smallest relevant check and report the exact command and result.

Recommended non-Virtuoso checks:

```bash
python skills/t28-ioring-simulator/scripts/symbol_export.py --help
python skills/t28-ioring-simulator/scripts/tb_builder.py --help
python skills/t28-ioring-simulator/scripts/spectre_runner.py --help
python -c "import sim_io; import sim_io.flow; import sim_io.site_config"
```

Run bridge, Virtuoso, Calibre, or Spectre steps only when the environment is available and the user expects live EDA operations.
