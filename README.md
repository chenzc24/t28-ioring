# io-ring-orchestrator-T28

> **AI Agent:** Skip to [Agent Setup Guide](#-agent-setup-guide) below for
> executable installation steps with concrete commands and ask/write tables.

A Claude Code skill for automated IO Ring generation on TSMC 28nm (T28) process
nodes — from natural-language requirements to verified layout, including JSON
construction, Cadence SKILL generation, Virtuoso execution, and DRC/LVS/PEX.

---

<!--=======================================================================-->
<!-- PART 1 — HUMAN GUIDE                                                   -->
<!-- Quick orientation, prerequisites, config reference, usage              -->
<!--=======================================================================-->

## Overview

`io-ring-orchestrator-T28` depends on **virtuoso-bridge-lite** for all Virtuoso
communication (TCP + SSH). The project layout after setup:

```
<project-root>/
├── .venv/                          ← one shared Python env (bridge + all skills)
├── virtuoso-bridge-lite/           ← bridge source
└── .claude/skills/
    └── io-ring-orchestrator-T28/
        ├── .env                    ← T28 skill config (CDS_LIB_PATH_28, VB_FS_MODE)
        └── assets/external_scripts/calibre/
            └── site_local.csh      ← Calibre/PDK paths on the EDA server (you fill this in)
```

### How the system works

```
Claude Code (your machine)
       │
       │  1. Generates JSON + SKILL scripts locally
       │
       ▼
virtuoso-bridge-lite
       │
       ├─ TCP socket ──────────────► Virtuoso daemon (EDA server)
       │                              loads .il, returns results
       │
       └─ SSH tunnel ──────────────► EDA server
              │
              ├─ uploads .il file → Virtuoso load()
              ├─ uploads calibre/ scripts → runs csh
              └─ downloads reports / screenshots
```

**Filesystem mode** controls how Calibre scripts and output files are exchanged:

| Mode | When | Behavior |
|---|---|---|
| `remote` | Windows PC, or no NFS | Scripts uploaded to `/tmp/vb_t28_calibre/` via SSH; results downloaded back |
| `shared` | Linux on same NFS as EDA server | Both machines see the same paths; Calibre reads/writes directly |

Auto-detected: Windows path (`C:\...`) → `remote`; NFS probe → `shared`. Set `VB_FS_MODE` in `.env` to override.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9+ | Local machine |
| Git | For cloning repos |
| Cadence Virtuoso | On the EDA server — required for SKILL execution and screenshots |
| Calibre (Mentor/Siemens) | On the EDA server — required for DRC, LVS, PEX |
| TSMC 28nm PDK | On the EDA server — layer map, LVS include files, `cds.lib` |
| `csh` | On the EDA server — Calibre wrapper scripts are written in csh |

---

## Quick Setup (Human)

**1. Clone and install:**
```bash
# At your project root:
git clone https://github.com/chenzc24/virtuoso-bridge-lite.git
git clone https://github.com/chenzc24/io-ring-orchestrator-T28.git .claude/skills/io-ring-orchestrator-T28

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e virtuoso-bridge-lite
pip install -r .claude/skills/io-ring-orchestrator-T28/requirements.txt
```

**2. Configure bridge connection:**

The bridge `.env` is created by `virtuoso-bridge init`. See
[`virtuoso-bridge-lite/README.md`](https://github.com/chenzc24/virtuoso-bridge-lite#quick-start)
for full details (jump hosts, multi-profile, local mode).

```bash
virtuoso-bridge init <username>@<eda-server>    # creates ~/.virtuoso-bridge/.env
# With jump host:
# virtuoso-bridge init <username>@<eda-server> -J <username>@<jump-host>
```

**3. Configure T28 skill `.env`:**

Edit `.claude/skills/io-ring-orchestrator-T28/.env` — the fields marked `# ← CHANGE`:

| Variable | Required | What to set |
|---|---|---|
| `CDS_LIB_PATH_28` | Yes | Remote Linux path to your T28 `cds.lib` |
| `VB_FS_MODE` | Optional | `remote` (Windows) or `shared` (NFS Linux). Auto-detected if blank. |

**4. Configure `site_local.csh`** (Calibre/PDK paths on the EDA server):
```bash
cd .claude/skills/io-ring-orchestrator-T28/assets/external_scripts/calibre
cp site_local.csh.example site_local.csh   # then edit with your site paths
```

Set `MGC_HOME`, `PDK_LAYERMAP_28`, `incFILE_28`, and source your site's Cadence/Mentor
cshrc files. Do **not** edit `env_common.csh` — `site_local.csh` overrides it.

**5. Start bridge and verify:**
```bash
virtuoso-bridge start
virtuoso-bridge status                  # tunnel ✓  daemon ✓
```
In Virtuoso CIW, load the daemon SKILL file once per session (path printed by `start`):
```skill
load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")
```
```bash
cd .claude/skills/io-ring-orchestrator-T28
python scripts/check_virtuoso_connection.py   # expect: ✅ Virtuoso Connection: OK
```

**Auto-activate `.venv`:** Set VS Code to use `.venv` as the interpreter, or add
`echo 'source .venv/bin/activate' > .envrc && direnv allow` (Linux/Mac).
Claude Code finds `.venv` automatically — no manual activation needed for skill runs.

---

## Workflow

The skill runs a 12-step pipeline automatically:

```
1.  Parse input → create timestamped output directory
2.  Build draft intent graph JSON (structure only)
3.  Enrich draft → final intent graph (devices, pins, corners)
4.  Reference-guided gate check (continuity, provider count, pin families)
5.  Validate JSON (validate_intent.py)
6.  Build confirmed config — optionally open Layout Editor (see below)
7.  Generate schematic SKILL (.il)
8.  Generate layout SKILL (.il)
9.  Check Virtuoso connection
10. Execute SKILL in Virtuoso + capture screenshots
11. Run Calibre DRC
12. Run Calibre LVS   [optional: PEX after LVS]
```

Output files land in `${AMS_OUTPUT_ROOT}/generated/<YYYYMMDD_HHMMSS>/`:
`io_ring_intent_graph.json`, `io_ring_confirmed.json`, `io_ring_schematic.il`,
`io_ring_layout.il`, `schematic_screenshot.png`, `layout_screenshot.png`,
`drc_report.txt`, `lvs_report.txt`.

---

## Layout Editor (Step 6)

Before generating SKILL scripts the skill asks:
> *"Open Layout Editor or Skip?"* (no response within ~15 s → skip automatically)

**If opened:** a browser launches on `localhost` showing the IO ring as an
interactive SVG. Every pad, corner, and filler is draggable and editable.
Click **"Confirm & Continue"** when done — edits are merged back into the
confirmed config and the pipeline resumes.

**Component colors:**

| Category | Color | Examples |
|---|---|---|
| Analog IO / Power | Blue | `PDB3AC`, `PVDD3AC`, `PVSS1AC` |
| Digital IO / Power | Green | `PDDW16SDGZ`, `PVDD1DGZ`, `PVSS1DGZ` |
| Corners | Red | `PCORNERA_G`, `PCORNER_G` |
| Fillers | Gray | `PFILLER10`, `PFILLER20` |
| Inner pads | Dashed border | Double-ring inner row |

**Key operations:** drag to move · click Inspector to edit properties · Ctrl+Z undo ·
toolbar Add/Delete · Import/Export JSON · Confirm & Continue to proceed.

---

## T28 Device Reference

| Signal type | Device | Notes |
|---|---|---|
| Analog IO | `PDB3AC` | Bidirectional analog pad |
| Analog power provider | `PVDD3AC` / `PVSS3AC` | Default (TACVDD/TACVSS pins) |
| Analog power provider (alt) | `PVDD3A` / `PVSS3A` | User-specified (TAVDD/TAVSS pins) |
| Analog power consumer | `PVDD1AC` / `PVSS1AC` | Under 3AC provider |
| Analog power consumer (alt) | `PVDD1A` / `PVSS1A` | Under 3A provider |
| Ring ESD (analog) | `PVSS2A` | User-triggered; 3 pins: VSS + TAVSS + TAVDD |
| Digital IO (default) | `PDDW16SDGZ` | 16-bit |
| Digital IO (alt) | `PRUW08SDGZ` | 8-bit; user-specified |
| Digital power (low VDD) | `PVDD1DGZ` | Standard digital power |
| Digital ground (low VSS) | `PVSS1DGZ` | Standard digital ground |
| Digital power (high VDD) | `PVDD2POC` | High-voltage digital power |
| Digital ground (high VSS) | `PVSS2DGZ` | High-voltage digital ground |
| Digital corner | `PCORNER_G` | Both adjacent pads digital |
| Analog/mixed corner | `PCORNERA_G` | At least one adjacent pad analog |

---

## Usage

**Via Claude Code (natural language):**
```
Generate T28 IO ring with signals: VCM, CLKP, VDDIB, VSSIB, DA0, RST.
Clockwise placement, 2 pads per side.
Library: LLM_Layout_Design, Cell: IO_RING_test.
```
Or explicitly: `Use io-ring-orchestrator-T28 to generate an IO ring with...`

### Writing Effective Prompts

The skill classifies signals by **name pattern** and **voltage domain assignment**.
For non-standard names, always specify explicitly — it overrides all inference.

**Required in every prompt:**
- Signal list (in placement order)
- Pads per side (e.g. `4 pads per side` or `top=4, bottom=4, left=2, right=2`)
- Ring type: `single ring` or `double ring`
- Placement order: `clockwise` or `counterclockwise`
- Library and cell name

**Signal classification (how the skill decides device type):**

| Signal type | Auto-detected when | Device |
|---|---|---|
| Analog IO | Name matches analog patterns (VCM, CLKP, VREF…) or in analog domain | `PDB3AC` |
| Analog power provider | First VDD/VSS in a domain range | `PVDD3AC` / `PVSS3AC` |
| Analog power consumer | Other VDD/VSS in same domain | `PVDD1AC` / `PVSS1AC` |
| Digital IO | Non-power signal not in any analog domain | `PDDW16SDGZ` |
| Digital power | Exactly 4 unique names forming digital domain | `PVDD1DGZ` / `PVSS1DGZ` / `PVDD2POC` / `PVSS2DGZ` |
| Corner | Inferred from adjacent pad types | `PCORNER_G` / `PCORNERA_G` |

**Full recommended prompt:**
```
Task: Generate IO ring schematic and layout for Cadence Virtuoso.
4 pads per side. Single ring. Counterclockwise placement.

Signals: VIN VSSIB VDDIB VCM D1 D2 D3 D4 VIOL GIOL VIOH GIOH

Signal classification:
- Analog IO: VIN, VCM
- Analog power: VDDIB (VDD provider), VSSIB (VSS provider)
- Digital IO: D1, D2, D3, D4 (outputs)
- Digital power: VIOL (low VDD), GIOL (low VSS), VIOH (high VDD), GIOH (high VSS)

Voltage domain: VDDIB/VSSIB → VIN, VCM

Technology: 28nm  |  Library: LLM_Layout_Design  |  Cell: IO_RING_4x4_mixed
```

### Built-in Test Cases

`T28_Testbench/` has **30 ready-made prompts** covering all die sizes and signal mixes.

```bash
cat T28_Testbench/IO_28nm_3x3_single_ring_mixed.txt   # then paste into Claude Code
```

| Case group | Die sizes | Ring | Signal mix |
|---|---|---|---|
| `*_3x3_*` to `*_7x7_*` | 3×3 → 7×7 | Single | Analog / Digital / Mixed |
| `*_8x8_double_*` | 8×8 | Double | Analog / Digital / Mixed / Multi-voltage |
| `*_10x6_*` | 10×6 | Single | Mixed (2 variants) |
| `*_10x10_double_*` | 10×10 | Double | Multi-voltage |
| `*_12x12_*` | 12×12 | Single + Double | Mixed / Multi-voltage (4 variants) |
| `*_12x18_*` / `*_18x12_*` | 12×18, 18×12 | Double / Single | Mixed / Multi-voltage |
| `*_18x18_*` | 18×18 | Single + Double | Multi-voltage |

Compare output against `T28_Testbench/golden_output/<case>/` to verify correctness.

---

## Configuration Reference

### Bridge `.env` variables

Bridge connection is configured via `virtuoso-bridge init`. See
[`virtuoso-bridge-lite/README.md`](https://github.com/chenzc24/virtuoso-bridge-lite#quick-start)
for the full reference (`VB_REMOTE_HOST`, `VB_REMOTE_USER`, jump hosts, multi-profile, etc.).

### T28 skill `.env` variables

| Variable | Description | Required |
|---|---|---|
| `CDS_LIB_PATH_28` | Remote path to T28 `cds.lib` | Yes |
| `VB_FS_MODE` | `shared` or `remote` (auto-detect if blank) | No |
| `AMS_OUTPUT_ROOT` | Output root (default: `./output`) | No |

These live in `.claude/skills/io-ring-orchestrator-T28/.env`.

### `site_local.csh` variables

| Variable | Description |
|---|---|
| `MGC_HOME` | Calibre installation root on EDA server |
| `PDK_LAYERMAP_28` | T28 PDK layer map file |
| `incFILE_28` | T28 LVS include file (`source.added`) |

`env_common.csh` defaults are applied only if the variable is **not** set by
`site_local.csh` or the shell — all `setenv` calls are guarded by `if ( ! $?VAR )`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Virtuoso connection fails | `virtuoso-bridge status` → `restart`; confirm daemon `.il` loaded in CIW |
| DRC/LVS path errors | Check `CDS_LIB_PATH_28` in `.env`; check `MGC_HOME` / `PDK_LAYERMAP_28` / `incFILE_28` in `site_local.csh` |
| Wrong output location | Set `AMS_OUTPUT_ROOT` in `.env` |
| Skill not triggering | Say `Use io-ring-orchestrator-T28 to...`; verify `SKILL.md` exists in `.claude/skills/` |
| `import virtuoso_bridge` fails | Run `pip install -e virtuoso-bridge-lite` inside the project `.venv` |

---

## Related Documentation

| Document | Description |
|---|---|
| `SKILL.md` | Full workflow contract — Steps 0–12, repair loops, troubleshooting |
| `references/enrichment_rules_T28.md` | Signal classification, device selection, pin connection rules |
| `references/T28_Technology.md` | Device specifications and process details |
| `virtuoso-bridge-lite/README.md` | Bridge CLI, SSH tunnel, daemon, multi-profile setup |

---

<!--=======================================================================-->
<!-- PART 2 — AI AGENT SETUP GUIDE                                          -->
<!-- Executable steps. No placeholders. 🤖 = run directly, ❓ = ask user.  -->
<!--=======================================================================-->

## 🤖 Agent Setup Guide

> **Human readers:** This section is written for AI agents performing automated
> setup. You can read it as a detailed reference, but the [Human Guide](#quick-setup-human)
> above covers everything you need more concisely.

Steps marked **🤖** can be executed with the exact commands shown.
Steps marked **❓ → 🤖** require collecting values from the user first, then
writing them into the specified file. Every repo URL and command is concrete.

---

### Step 0 — Clone repositories 🤖

```bash
# Run from the project root directory:
git clone https://github.com/chenzc24/virtuoso-bridge-lite.git
git clone https://github.com/chenzc24/io-ring-orchestrator-T28.git .claude/skills/io-ring-orchestrator-T28
```

The skill lands in `.claude/skills/io-ring-orchestrator-T28/` — Claude Code
discovers skills in `.claude/skills/` automatically. Bridge repo stays at project root.

---

### Step 1 — Create project `.venv` and install packages 🤖

```bash
python -m venv .venv

# Activate (choose by OS):
source .venv/bin/activate          # Linux / Mac / Git Bash
# .venv\Scripts\Activate.ps1       # Windows PowerShell
# .venv\Scripts\activate.bat       # Windows CMD

pip install -e virtuoso-bridge-lite
pip install -r .claude/skills/io-ring-orchestrator-T28/requirements.txt

# Verify:
python -c "import virtuoso_bridge; print('ok:', virtuoso_bridge.__version__)"
virtuoso-bridge --version          # expect: 0.6.x
```

One `.venv` serves all skills. To add a second skill later: `pip install -r .claude/skills/<other-skill>/requirements.txt`.

---

### Step 2 — Initialize bridge config ❓ → 🤖

**Ask user — required:**

| Question to ask user |
|---|
| "Hostname or IP of your EDA server?" |
| "SSH username on that server?" |

Then run `virtuoso-bridge init` to create the bridge `.env` with correct format and defaults:

```bash
virtuoso-bridge init <username>@<eda-server>
# With jump host:
# virtuoso-bridge init <username>@<eda-server> -J <username>@<jump-host>
```

This writes `~/.virtuoso-bridge/.env` (or project-root `.env`) with all bridge variables
(`VB_REMOTE_HOST`, `VB_REMOTE_USER`, ports, jump host, etc.) in the correct format.
**Do not** write the bridge `.env` manually — always use `virtuoso-bridge init`.

For advanced options (multi-profile, local mode, custom ports), see
[`virtuoso-bridge-lite/README.md`](https://github.com/chenzc24/virtuoso-bridge-lite#quick-start).

---

### Step 3 — Configure T28 skill `.env` ❓ → 🤖

**Ask user — required:**

| Variable | Question to ask user |
|---|---|
| `CDS_LIB_PATH_28` | "Remote Linux path to your T28 `cds.lib`? (e.g. `/home/youruser/TSMC28/cds.lib`)" |

Write the value into `.claude/skills/io-ring-orchestrator-T28/.env`. The file ships
pre-filled with defaults — only update the fields marked `# ← CHANGE`:

```bash
# Edit the skill .env:
CDS_LIB_PATH_28=/home/<username>/TSMC28/llm_IO/cds.lib
```

---

### Step 4 — Write `site_local.csh` ❓ → 🤖

```bash
cp .claude/skills/io-ring-orchestrator-T28/assets/external_scripts/calibre/site_local.csh.example \
   .claude/skills/io-ring-orchestrator-T28/assets/external_scripts/calibre/site_local.csh
```

**Ask user — required:**

| What | Question to ask user |
|---|---|
| Cadence cshrc path | "Path to site's Cadence setup script on EDA server? (e.g. `/home/cshrc/.cshrc.cadence.IC618SP201`)" |
| Mentor cshrc path | "Path to site's Mentor setup script? (e.g. `/home/cshrc/.cshrc.mentor`)" |
| `MGC_HOME` | "Calibre install root on EDA server? (e.g. `/home/mentor/calibre/calibre2022/aoj_cal_2022.1_36.16`)" |
| `PDK_LAYERMAP_28` | "T28 PDK layer map path on EDA server? (e.g. `/home/process/tsmc28n/.../tsmcN28.layermap`)" |
| `incFILE_28` | "T28 LVS `source.added` path on EDA server?" |

Write values directly into `site_local.csh`. Example of a complete filled-in file:

```csh
source /home/cshrc/.cshrc.cadence.IC618SP201
source /home/cshrc/.cshrc.mentor
setenv MGC_HOME /home/mentor/calibre/calibre2022/aoj_cal_2022.1_36.16
setenv PDK_LAYERMAP_28 /home/process/tsmc28n/iPDK_CRN28HPC+ULL/tsmcN28/tsmcN28.layermap
setenv incFILE_28 /home/process/tsmc28n/iPDK_CRN28HPC+ULL/Calibre/lvs/source.added
```

---

### Step 5 — Start bridge and verify 🤖

```bash
virtuoso-bridge start         # opens SSH tunnel + deploys daemon on EDA server
virtuoso-bridge status        # expect: tunnel ✓  daemon ✓
```

Instruct user to load the daemon SKILL file in Virtuoso CIW once per Virtuoso session.
`virtuoso-bridge start` prints the exact path to load:
```skill
load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")
```

Verify end-to-end:
```bash
cd .claude/skills/io-ring-orchestrator-T28
python scripts/check_virtuoso_connection.py
# Success: ✅ Virtuoso Connection: OK
# Failure: follow printed instructions; run `virtuoso-bridge restart` if tunnel is down
```

---

### Setup complete ✅

```
<project-root>/
├── .venv/                                         ← shared env (bridge + all skills)
├── virtuoso-bridge-lite/                          ← bridge source (editable install)
└── .claude/skills/io-ring-orchestrator-T28/
    ├── .env                                       ← T28 skill config (CDS_LIB_PATH_28, VB_FS_MODE)
    └── assets/external_scripts/calibre/
        └── site_local.csh                         ← written in Step 4
```

Bridge config lives in `~/.virtuoso-bridge/.env` (created by `virtuoso-bridge init` in Step 2).
`AMS_PYTHON` in `SKILL.md` Step 0 finds `.venv` at project root automatically —
no manual activation needed when Claude Code runs scripts.
