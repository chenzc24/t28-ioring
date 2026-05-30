# T28 IO Ring Suite

This repository provides two sibling Agent skills for TSMC 28nm IO ring work:

- `t28-ioring-generator`: generates IO ring JSON, schematic/layout SKILL, Virtuoso views, screenshots, DRC/LVS, and optional PEX.
- `t28-ioring-simulator`: builds simulation testbenches, classifies pins, places sources/loads, runs direct Spectre, and syncs Maestro setup.

Register the `skills/` directory as the Agent skills root, or copy/symlink each child skill into the normal Agent skills root:

```text
skills/
  t28-ioring-generator/
    SKILL.md
  t28-ioring-simulator/
    SKILL.md
```

Do not assume nested skills are discovered if only the repository root is installed as one skill. The two explicit sibling skills under `skills/` are the preferred registration targets.

## Repository Layout

```text
t28-ioring/
  README.md
  AGENTS.md
  skills/
    t28-ioring-generator/
      SKILL.md
      .env.example
      requirements.txt
      scripts/
      io_ring/
      references/
      skill_code/
      calibre/
      T28_Testbench/
    t28-ioring-simulator/
      SKILL.md
      .env.example
      requirements.txt
      scripts/
      sim_io/
      references/
      skill_code/
      templates/
```

Generated artifacts are not source of truth. New runs should write under the shared output root described below.

## How It Works

```text
Agent / local Python
  |
  |  generator: JSON -> SKILL -> Virtuoso schematic/layout -> Calibre DRC/LVS
  |  simulator: symbol export -> testbench -> Spectre deck -> measurements/plots
  v
virtuoso-bridge-lite
  |
  +-- TCP socket -> Virtuoso daemon on EDA server
  |
  +-- SSH -> upload SKILL/Calibre/Spectre files, run tools, download reports
```

Filesystem mode controls how Calibre scripts and results are exchanged:

| Mode | When | Behavior |
|---|---|---|
| `remote` | Windows PC, or no shared filesystem | Scripts are uploaded to `/tmp/vb_t28_calibre...` by SSH; reports are downloaded locally. |
| `shared` | Linux on same NFS as EDA server | Local and EDA server see the same paths. |

The generator auto-detects the mode. Set `VB_FS_MODE` in `skills/t28-ioring-generator/.env` to override.

## Output Contract

Both skills use `AMS_OUTPUT_ROOT` when set. The intended shared layout is:

```text
${AMS_OUTPUT_ROOT}/generated/<timestamp>/     generator JSON, SKILL, screenshots
${AMS_OUTPUT_ROOT}/simulation/<timestamp>/    simulator pin info, TB metadata, decks, plots
${AMS_OUTPUT_ROOT}/simulation/.latest_run     simulator latest-run marker
${AMS_OUTPUT_ROOT}/drc/                       DRC reports
${AMS_OUTPUT_ROOT}/lvs/                       LVS reports
${AMS_OUTPUT_ROOT}/pex/                       PEX artifacts
```

If `AMS_OUTPUT_ROOT` is unset, both skills fall back to this repository's `output/` directory.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9+ | Local machine |
| `virtuoso-bridge-lite` | Installed editable into the shared project `.venv` |
| Cadence Virtuoso | On the EDA server |
| TSMC 28nm PDK | On the EDA server; includes `cds.lib`, layer map, LVS/model includes |
| Calibre | On the EDA server; required for DRC/LVS/PEX |
| Spectre/MMSIM | On the EDA server; required for simulation |
| Maestro/ADE | On the EDA server; simulator can sync setup |
| `csh` | On the EDA server; Calibre and Spectre setup wrappers use csh |

## Quick Setup

### 1. Create/activate the shared Python environment

Run from the project root that contains `virtuoso-bridge-lite/` and `t28-ioring/`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .\virtuoso-bridge-lite
pip install -r .\t28-ioring\skills\t28-ioring-generator\requirements.txt
pip install -r .\t28-ioring\skills\t28-ioring-simulator\requirements.txt
```

Linux/Git Bash equivalent:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ./virtuoso-bridge-lite
pip install -r ./t28-ioring/skills/t28-ioring-generator/requirements.txt
pip install -r ./t28-ioring/skills/t28-ioring-simulator/requirements.txt
```

Verify:

```bash
python -c "import virtuoso_bridge; print('virtuoso_bridge ok')"
virtuoso-bridge --version
```

### 2. Configure the bridge connection

Use `virtuoso-bridge init`; do not hand-write the bridge config.

```bash
virtuoso-bridge init <username>@<eda-server>
```

With a jump host:

```bash
virtuoso-bridge init <username>@<eda-server> -J <username>@<jump-host>
```

This writes `~/.virtuoso-bridge/.env` with bridge variables such as `VB_REMOTE_HOST`, `VB_REMOTE_USER`, jump-host settings, and ports. See the `virtuoso-bridge-lite` README for advanced multi-profile or local-mode setup.

### 3. Configure the generator skill

Create the generator `.env` from the example:

```powershell
Copy-Item .\t28-ioring\skills\t28-ioring-generator\.env.example .\t28-ioring\skills\t28-ioring-generator\.env
```

Edit `skills/t28-ioring-generator/.env`:

| Variable | Required | Description |
|---|---:|---|
| `CDS_LIB_PATH_28` | Yes | Remote Linux path to the T28 `cds.lib`. |
| `VB_FS_MODE` | No | `remote` or `shared`; leave blank for auto-detect. |
| `AMS_OUTPUT_ROOT` | No | Shared output root; recommended: `<repo>/output`. |
| `AMS_DRAFT_EDITOR` | No | `on` to open the draft editor by default; otherwise `off`. |
| `AMS_LAYOUT_EDITOR` | No | `on` to open the layout confirmation editor; otherwise `off`. |

### 4. Configure Calibre/PDK paths

Create the local site override:

```powershell
Copy-Item .\t28-ioring\skills\t28-ioring-generator\calibre\site_local.csh.example .\t28-ioring\skills\t28-ioring-generator\calibre\site_local.csh
```

Edit `skills/t28-ioring-generator/calibre/site_local.csh`:

| Variable/path | Required | Description |
|---|---:|---|
| Cadence cshrc source | Site-dependent | Example: `source /home/cshrc/.cshrc.cadence.IC618SP201` |
| Mentor cshrc source | Site-dependent | Example: `source /home/cshrc/.cshrc.mentor` |
| `MGC_HOME` | Yes | Calibre installation root. |
| `PDK_LAYERMAP_28` | Yes | T28 stream layer map. |
| `incFILE_28` | Yes | T28 LVS include/source-added file. |

Do not edit `env_common.csh` for site-specific values. Use `site_local.csh`; it is ignored by git.

### 5. Configure the simulator skill

Create the simulator `.env` from the example:

```powershell
Copy-Item .\t28-ioring\skills\t28-ioring-simulator\.env.example .\t28-ioring\skills\t28-ioring-simulator\.env
```

Edit `skills/t28-ioring-simulator/.env`:

| Variable | Required | Description |
|---|---:|---|
| `SIM_CDS_LIB` | Yes | Remote Linux path to `cds.lib`; if omitted, simulator falls back to `CDS_LIB_PATH_28`. |
| `SIM_IC_ROOT` | Yes | Remote Cadence IC installation root. |
| `SIM_MMSIM_ROOT` | Recommended | Remote Spectre/MMSIM installation root. |
| `SIM_LM_LICENSE_FILE` | Site-dependent | Spectre license path; can be discovered from Virtuoso if blank. |
| `SIM_CDS_LIC_FILE` | Site-dependent | Cadence license path; can be discovered from Virtuoso if blank. |
| `SIM_PDK_IO_SPECTRE_INCLUDE` | Yes | T28 IO pad SPICE include. |
| `SIM_PDK_CORE_SPECTRE_INCLUDE` | Yes | T28 core Spectre model include. |
| `SIM_PDK_CORE_SPECTRE_SECTIONS` | Yes | Model sections, comma-separated. |
| `AMS_OUTPUT_ROOT` | No | Shared output root; recommended: `<repo>/output`. |
| `VB_DISABLE_CONTROL_MASTER` | Recommended on Windows | Set to `1` for Windows/OpenSSH jump-host setups. |

On Windows/OpenSSH jump-host setups, keep `VB_DISABLE_CONTROL_MASTER=1`; stale ControlMaster sockets can otherwise break Spectre file upload with `getsockname failed: Not a socket`.

### 6. Start the bridge and load the Virtuoso daemon

```bash
virtuoso-bridge start
virtuoso-bridge status
```

In Virtuoso CIW, load the daemon SKILL file once per Virtuoso session. The exact path is printed by `virtuoso-bridge start`; it normally looks like:

```skill
load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")
```

Verify bridge connectivity from the generator skill:

```powershell
.\.venv\Scripts\python.exe .\t28-ioring\skills\t28-ioring-generator\scripts\check_virtuoso_connection.py
```

Linux/Git Bash:

```bash
./.venv/bin/python ./t28-ioring/skills/t28-ioring-generator/scripts/check_virtuoso_connection.py
```

## Agent Setup Checklist

An Agent setting up this repository should do the following, in order:

1. Verify a shared `.venv` exists at the project root.
2. Install `virtuoso-bridge-lite` editable into `.venv`.
3. Install both skill requirements.
4. Run `virtuoso-bridge init ...` if `~/.virtuoso-bridge/.env` is missing.
5. Ask for and write generator values:
   - `CDS_LIB_PATH_28`
   - optional `VB_FS_MODE`
   - optional `AMS_OUTPUT_ROOT`
6. Ask for and write Calibre values:
   - Cadence cshrc path
   - Mentor cshrc path
   - `MGC_HOME`
   - `PDK_LAYERMAP_28`
   - `incFILE_28`
7. Ask for and write simulator values:
   - `SIM_CDS_LIB`
   - `SIM_IC_ROOT`
   - `SIM_MMSIM_ROOT`
   - `SIM_PDK_IO_SPECTRE_INCLUDE`
   - `SIM_PDK_CORE_SPECTRE_INCLUDE`
   - `SIM_PDK_CORE_SPECTRE_SECTIONS`
   - license vars if not discoverable from Virtuoso
8. Set `VB_DISABLE_CONTROL_MASTER=1` on Windows/OpenSSH jump-host setups.
9. Start bridge, ask the user to load the daemon in Virtuoso CIW, then run `check_virtuoso_connection.py`.

Do not create a mandatory common `.env`. Generator and simulator settings are deliberately skill-local because their required site variables differ.

## Generator Workflow

Use `t28-ioring-generator` for IO ring creation:

```text
Generate a T28 IO ring with 4 pads per side, single ring, counterclockwise placement.
Signals: VIN VSSIB VDDIB VCM D1 D2 D3 D4 VIOL GIOL VIOH GIOH.
Library: LLM_Layout_Design. Cell: IO_RING_4x4_mixed.
```

Pipeline:

1. Parse structural requirements.
2. Build draft intent JSON.
3. Optionally open the draft editor.
4. Generate semantic intent and enriched pin-wired graph.
5. Validate JSON.
6. Build confirmed config.
7. Generate schematic/layout SKILL.
8. Execute SKILL in Virtuoso and capture screenshots.
9. Run DRC/LVS and optional PEX.

Primary output:

```text
output/generated/<timestamp>/
```

Full procedural details are in `skills/t28-ioring-generator/SKILL.md`.

## Simulator Workflow

Use `t28-ioring-simulator` after the DUT schematic exists:

```text
Build a simulation testbench for IO_RING_4x4_mixed in LLM_Layout_Design.
VDD is 0.9 V. Run simulation after building.
```

Pipeline:

1. Export and redistribute the DUT symbol.
2. Write `pin_info.json` and `dut_context.json`.
3. Agent reads `references/pin_classification.md` and writes `pin_classifications.json`.
4. Agent reads `references/sim_config_rules.md` and writes `sim_config.json`.
5. Build `{cell}_tb/schematic`.
6. Place sources, loads, PVSS references, digital supply currents, and inner devices.
7. Export Spectre netlist, build `deck.scs`, run Spectre, parse measurements, generate plots.
8. Sync the resolved setup into Maestro without using Maestro as the primary verification source.

Primary output:

```text
output/simulation/<timestamp>/
```

Important simulator artifacts:

```text
pin_info.json
pin_classifications.json
sim_config.json
dut_context.json
result.json
spectre/netlist.scs
spectre/deck.scs
spectre/spectre.out
measurements.json
sim_run_result.json
plots/
```

Full procedural details are in `skills/t28-ioring-simulator/SKILL.md`.

## End-to-End Flow

1. Use `t28-ioring-generator` to create the IO ring schematic/layout in Virtuoso.
2. Confirm DRC/LVS are clean enough for the requested task.
3. Use `t28-ioring-simulator` on the generated `{lib}/{cell}`.
4. Inspect `sim_run_result.json`, `measurements.json`, `spectre/spectre.out`, and `plots/`.

Generation and simulation are separate skills because they have different trigger conditions, configuration, artifacts, and failure modes.

## T28 Device Reference

| Signal type | Device |
|---|---|
| Analog IO/reference | `PDB3AC` |
| Analog power provider | `PVDD3AC` / `PVSS3AC` |
| Analog power provider, alternate | `PVDD3A` / `PVSS3A` |
| Analog power consumer | `PVDD1AC` / `PVSS1AC` |
| Analog power consumer, alternate | `PVDD1A` / `PVSS1A` |
| Ring ESD, analog | `PVSS2A` |
| Digital IO, default | `PDDW16SDGZ` |
| Digital IO, alternate | `PRUW08SDGZ` |
| Digital power, low VDD | `PVDD1DGZ` |
| Digital ground, low VSS | `PVSS1DGZ` |
| Digital power, high VDD | `PVDD2POC` |
| Digital ground, high VSS | `PVSS2DGZ` |
| Digital corner | `PCORNER_G` |
| Analog/mixed corner | `PCORNERA_G` |

## Prompt Guidance

Every generator prompt should specify:

- Signal list in placement order.
- Pads per side, for example `4 pads per side` or `top=4, bottom=4, left=2, right=2`.
- Ring type: `single ring` or `double ring`.
- Placement order: `clockwise` or `counterclockwise`.
- Library and cell name.
- Voltage domain provider names and digital supply roles when not obvious.
- Digital IO direction for each PDDW/PRUW signal.

For non-standard names, specify classification explicitly. Explicit user constraints override name-pattern inference.

Recommended prompt shape:

```text
Task: Generate IO ring schematic and layout for Cadence Virtuoso.
4 pads per side. Single ring. Counterclockwise placement.

Signals: VIN VSSIB VDDIB VCM D1 D2 D3 D4 VIOL GIOL VIOH GIOH

Signal classification:
- Analog IO: VIN, VCM
- Analog power: VDDIB is VDD provider, VSSIB is VSS provider
- Digital IO: D1, D2, D3, D4 are outputs
- Digital power: VIOL low_vdd, GIOL low_vss, VIOH high_vdd, GIOH high_vss

Voltage domain: VDDIB/VSSIB -> VIN, VCM

Technology: 28nm
Library: LLM_Layout_Design
Cell: IO_RING_4x4_mixed
```

## Built-In Test Cases

Generator benchmark prompts and golden outputs are under:

```text
skills/t28-ioring-generator/T28_Testbench/
```

Example:

```bash
cat skills/t28-ioring-generator/T28_Testbench/IO_28nm_3x3_single_ring_mixed.txt
```

Use `skills/t28-ioring-generator/T28_Testbench/golden_output/<case>/` as a reference for expected generated artifacts.

## Troubleshooting

| Problem | Check/Fix |
|---|---|
| Skill does not trigger | Register `skills/` as skills root, or register/copy each child skill directly. |
| `import virtuoso_bridge` fails | Run `pip install -e <project-root>/virtuoso-bridge-lite` inside the shared `.venv`. |
| Virtuoso connection fails | Run `virtuoso-bridge status`; restart bridge; confirm daemon `.il` is loaded in CIW. |
| DRC/LVS path errors | Check `CDS_LIB_PATH_28`, `VB_FS_MODE`, and generator `calibre/site_local.csh`. |
| Calibre cannot find rules/includes | Check `MGC_HOME`, `PDK_LAYERMAP_28`, `incFILE_28`, and sourced Cadence/Mentor cshrc paths. |
| Wrong output location | Set `AMS_OUTPUT_ROOT` in the relevant skill `.env`. |
| Simulator cannot find cell/libs | Check `SIM_CDS_LIB` or fallback `CDS_LIB_PATH_28`. |
| Spectre model missing | Check `SIM_PDK_IO_SPECTRE_INCLUDE`, `SIM_PDK_CORE_SPECTRE_INCLUDE`, and sections. |
| Spectre license error | Set `SIM_LM_LICENSE_FILE` and `SIM_CDS_LIC_FILE`, or verify Virtuoso environment discovery. |
| Spectre upload fails with `getsockname failed` | Set `VB_DISABLE_CONTROL_MASTER=1`. |
| `/tmp/sim_io_spectre_setup.csh` missing | Current simulator verifies and retries the upload; rerun with `VB_DISABLE_CONTROL_MASTER=1` if SSH is unstable. |

## Related Documentation

| Document | Description |
|---|---|
| `skills/t28-ioring-generator/SKILL.md` | Generator workflow contract and repair loops. |
| `skills/t28-ioring-generator/references/enrichment_rules_T28.md` | Signal classification, device selection, and pin connection rules. |
| `skills/t28-ioring-generator/references/T28_Technology.md` | Device specifications and process details. |
| `skills/t28-ioring-simulator/SKILL.md` | Simulator workflow contract. |
| `skills/t28-ioring-simulator/references/pin_classification.md` | Testbench pin classification rules. |
| `skills/t28-ioring-simulator/references/sim_config_rules.md` | Spectre measurement/config rules. |
| `virtuoso-bridge-lite/README.md` | Bridge CLI, SSH tunnel, daemon, and multi-profile setup. |
