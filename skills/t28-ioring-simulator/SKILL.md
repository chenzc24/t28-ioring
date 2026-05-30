---
name: t28-ioring-simulator
description: Build and run simulation testbenches for T28 IO ring or mixed-signal Cadence Virtuoso cells. Use when the user asks to create a testbench, export/redistribute a symbol, classify IO pins, place sources or loads, generate sim_config.json, run Spectre, sync Maestro setup, inspect simulation measurements, or continue a prior simulator run.
---

# T28 IO Ring Simulator

Build a simulation testbench around an existing Virtuoso DUT cell and optionally run direct Spectre simulation with Maestro setup sync.

This skill is the simulation sibling of `t28-ioring-generator`. Use the generator to create the IO ring schematic/layout; use this simulator on the generated or any existing schematic cell.

## Output Contract

Use one shared output root:

```bash
AMS_OUTPUT_ROOT="${AMS_OUTPUT_ROOT:-<repo-root>/output}"
```

Simulator artifacts must go under:

```text
${AMS_OUTPUT_ROOT}/simulation/<YYYYMMDD_HHMMSS>/
${AMS_OUTPUT_ROOT}/simulation/.latest_run
```

Do not create new runs under the old `SIM-IO/output/` path.

## Entry Points

| Situation | Start here |
|---|---|
| Fresh run with `lib` and `cell` | Step 0 then Step 1 |
| `pin_info.json` exists but classifications are missing | Step 2 |
| `pin_classifications.json` and `sim_config.json` exist | Step 3 |
| Testbench exists and user only wants simulation | Step 4 |

## Step 0: Environment Setup

Auto-detect paths from this skill root. Do not hard-code an absolute install path.

```bash
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_PATH="${SKILL_ROOT}/scripts"
export PYTHONPATH="${SKILL_ROOT}:${PYTHONPATH:-}"

# REPO_ROOT owns _local/site.yaml and tools/t28_config_export.py.
REPO_ROOT="$(cd "${SKILL_ROOT}" && while [ ! -f tools/t28_config_export.py ] && [ "$(pwd)" != "/" ]; do cd ..; done; pwd)"

# VENV_ROOT may be the parent workspace that contains both t28-ioring/ and virtuoso-bridge-lite/.
VENV_ROOT="$(cd "${SKILL_ROOT}" && while [ ! -d .venv ] && [ "$(pwd)" != "/" ]; do cd ..; done; pwd)"
if   [ -f "${VENV_ROOT}/.venv/Scripts/python.exe" ]; then export AMS_PYTHON="${VENV_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${VENV_ROOT}/.venv/bin/python" ];         then export AMS_PYTHON="${VENV_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1;                then export AMS_PYTHON="python3"
elif command -v python  >/dev/null 2>&1;                then export AMS_PYTHON="python"
else echo "ERROR: No Python found."; return 1; fi

if [ -f "${REPO_ROOT}/tools/t28_config_export.py" ]; then
  eval "$("$AMS_PYTHON" "${REPO_ROOT}/tools/t28_config_export.py" --shell sh)"
fi

# Windows/OpenSSH jump-host setups can fail on stale ControlMaster sockets during Spectre uploads.
export VB_DISABLE_CONTROL_MASTER="${VB_DISABLE_CONTROL_MASTER:-1}"
```

All subsequent commands use `$AMS_PYTHON`.

Required simulator configuration:

- `_local/site.yaml` at the repository root.
- `~/.virtuoso-bridge/.env`, created by `virtuoso-bridge init`, for bridge connection values.

Optional:

- `VB_DISABLE_CONTROL_MASTER` (recommended `1` on Windows/OpenSSH jump-host setups)

## Step 1: Symbol Export

Run when the user provides a Virtuoso library and cell with an existing schematic view.

```bash
$AMS_PYTHON "$SCRIPTS_PATH/symbol_export.py" <lib> <cell> [--vdd <vdd_value>]
```

What it does:

1. Exports or regenerates `{lib}/{cell}/symbol` from the schematic.
2. Redistributes pins to a left/right testbench-friendly symbol layout.
3. Extracts pin names, directions, positions, and sides.
4. Writes `pin_info.json` and `dut_context.json`.
5. Writes `${AMS_OUTPUT_ROOT}/simulation/.latest_run`.

Outputs:

```text
output/simulation/<timestamp>/pin_info.json
output/simulation/<timestamp>/dut_context.json
output/simulation/<timestamp>/build/
```

Exit code `0` means proceed to Step 2. Exit code `1` means read stderr and fix environment, bridge, lib/cell, or schematic availability before continuing.

## Step 2: Pin Intent Authoring

This is the deliberate LLM step between symbol export and testbench build.

Find the run directory from the path printed by Step 1, or read:

```text
${AMS_OUTPUT_ROOT}/simulation/.latest_run
```

Then write two files into that run directory.

### File 1: `pin_classifications.json`

1. Read `references/pin_classification.md`.
2. Read `<run_dir>/pin_info.json`.
3. Classify every pin, including `_CORE` pins and duplicated supply pins.
4. Write `<run_dir>/pin_classifications.json`.

Validate against:

```text
scripts/pin_classify_schema.json
```

Key rules:

- Use `device_class` to drive source/load topology.
- Assign analog local ground zones.
- Assign digital supply pairs.
- Use non-round stimulus values, for example `1.72`, `2.7m`, `137n`.

### File 2: `sim_config.json`

1. Read `references/sim_config_rules.md`.
2. Collect every `vpulse` period from `pin_classifications.json`.
3. Set `tstop = 10 * max(per)`, clamped to `[100n, 10u]`.
4. Declare per-pin measurement intent in `pin_measurements`.
5. Write `<run_dir>/sim_config.json`.

Validate against:

```text
scripts/sim_config_schema.json
```

Do not write raw OCEAN expressions in `outputs`; use `pin_measurements`.

## Step 3: Build Testbench

```bash
$AMS_PYTHON "$SCRIPTS_PATH/tb_builder.py" [--run-dir <run_dir>]
```

If `--run-dir` is omitted, the script reads `${AMS_OUTPUT_ROOT}/simulation/.latest_run`.

What it does:

1. Creates `{lib}/{cell}_tb/schematic`.
2. Places the DUT instance.
3. Labels DUT terminals using label-based wiring.
4. Places sources, loads, PVSS references, digital supply currents, and inner devices from `pin_classifications.json`.
5. Writes `result.json`.

Output:

```text
<run_dir>/result.json
```

If `pin_classifications.json` is missing, the script can fall back to heuristic classification, but for real T28 IO ring work you should write the classification file first.

## Step 4: Direct Spectre Simulation with Maestro Sync

```bash
$AMS_PYTHON "$SCRIPTS_PATH/spectre_runner.py" [--run-dir <run_dir>] [--intent "<description>"]
```

What it does:

1. Exports a fresh Spectre netlist from `{cell}_tb`.
2. Builds `deck.scs` from `sim_config.json` plus model includes from `_local/site.yaml`.
3. Runs Spectre directly.
4. Parses PSF results locally.
5. Writes measurements and SVG plots.
6. Syncs the resolved setup into Maestro without running Maestro simulation.

Primary outputs:

```text
<run_dir>/spectre/netlist.scs
<run_dir>/spectre/deck.scs
<run_dir>/spectre/spectre.out
<run_dir>/measurements.json
<run_dir>/sim_run_result.json
<run_dir>/plots/
```

Do not use Maestro results as the verification source for this route. Use `sim_run_result.json`, `measurements.json`, and `plots/`.

## Optional: Maestro Runner

Use only for legacy/debug workflows:

```bash
$AMS_PYTHON "$SCRIPTS_PATH/maestro_runner.py" [--run-dir <run_dir>] [--run-sim]
```

Prefer `spectre_runner.py` for normal simulator validation.

## Troubleshooting

| Problem | Action |
|---|---|
| Virtuoso connection fails | Check `virtuoso-bridge status`, local port, and daemon `.il` loaded in CIW |
| `lib/cell` not found | Verify `SIM_CDS_LIB` or `CDS_LIB_PATH_28` points to the right remote `cds.lib` |
| No schematic view | Open/create `{lib}/{cell}/schematic` before Step 1 |
| Wrong source/load placement | Re-read `pin_classification.md` and fix `pin_classifications.json` |
| Spectre model missing | Check `spectre.io_model_include` and `spectre.core_model_include` in `_local/site.yaml` |
| Spectre license error | Set `spectre.lm_license_file` and `spectre.cds_lic_file` in `_local/site.yaml` |
| `si` netlist export hangs | Dismiss Virtuoso confirmation dialogs or check `templates/si_spectre.env` |

## Completion Checklist

- [ ] Step 0: `$AMS_PYTHON` resolved and `_local/site.yaml` loaded.
- [ ] Step 1: `pin_info.json`, `dut_context.json`, and `output/simulation/.latest_run` written.
- [ ] Step 2: `pin_classifications.json` written after reading `pin_classification.md`.
- [ ] Step 2: `sim_config.json` written after reading `sim_config_rules.md`.
- [ ] Step 3: `{cell}_tb/schematic` built and `result.json` written.
- [ ] Step 4: `sim_run_result.json`, `measurements.json`, and plots written if simulation was requested.
