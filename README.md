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
├── .env                            ← SSH + T28 config (you fill this in)
├── virtuoso-bridge-lite/           ← bridge source
└── .claude/skills/
    └── io-ring-orchestrator-T28/
        └── assets/external_scripts/calibre/
            └── site_local.csh      ← Calibre/PDK paths on the EDA server (you fill this in)
```

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

**2. Configure `.env`** (project root — bridge + T28 vars in one file):
```bash
cp .env.example .env   # then edit with your values
```

| Variable | Required | What to set |
|---|---|---|
| `VB_REMOTE_HOST` | Yes | EDA server hostname or IP |
| `VB_REMOTE_USER` | Yes | Your SSH username on the EDA server |
| `CDS_LIB_PATH_28` | Yes | Remote Linux path to your T28 `cds.lib` |
| `VB_JUMP_HOST` | If needed | Bastion/jump host hostname |
| `VB_FS_MODE` | Optional | `remote` (Windows) or `shared` (NFS Linux). Auto-detected if blank. |
| `AMS_OUTPUT_ROOT` | Optional | Output directory. Defaults to `<project-root>/output`. |

**3. Configure `site_local.csh`** (Calibre/PDK paths on the EDA server):
```bash
cd .claude/skills/io-ring-orchestrator-T28/assets/external_scripts/calibre
cp site_local.csh.example site_local.csh   # then edit with your site paths
```

Set `MGC_HOME`, `PDK_LAYERMAP_28`, `incFILE_28`, and source your site's Cadence/Mentor
cshrc files. Do **not** edit `env_common.csh` — `site_local.csh` overrides it.

**4. Start bridge and verify:**
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

## Usage

**Via Claude Code (natural language):**
```
Generate T28 IO ring with signals: VCM, CLKP, VDDIB, VSSIB, DA0, RST.
Clockwise placement, 2 pads per side.
Library: LLM_Layout_Design, Cell: IO_RING_test.
```
Or explicitly: `Use io-ring-orchestrator-T28 to generate an IO ring with...`

**Writing effective prompts** — the skill classifies signals by name pattern and
voltage domain. For non-standard names, always specify explicitly:

```
Signal classification:
- Analog IO: VIN, VCM
- Analog power: VDDIB (provider), VSSIB (provider)
- Digital IO: D1, D2, D3, D4 (outputs)
- Digital power: VIOL (low VDD), GIOL (low VSS), VIOH (high VDD), GIOH (high VSS)
Voltage domain: VDDIB/VSSIB → VIN, VCM
Library: LLM_Layout_Design, Cell: IO_RING_4x4
```

**Test cases:** `T28_Testbench/` contains 30 ready-made prompts. Run any:
```bash
cat T28_Testbench/IO_28nm_3x3_single_ring_mixed.txt   # paste into Claude Code
```

---

## Configuration Reference

### `.env` variables

| Variable | Description | Required |
|---|---|---|
| `VB_REMOTE_HOST` | EDA server hostname/IP | Yes |
| `VB_REMOTE_USER` | SSH username | Yes |
| `VB_REMOTE_PORT` | SSH port (default: 22) | No |
| `VB_JUMP_HOST` / `VB_JUMP_USER` | Bastion host | If needed |
| `VB_FS_MODE` | `shared` or `remote` (auto-detect if blank) | No |
| `CDS_LIB_PATH_28` | Remote path to T28 `cds.lib` | Yes |
| `AMS_OUTPUT_ROOT` | Output root (default: `./output`) | No |

Bridge vars can also live in `~/.virtuoso-bridge/.env` (user-level, shared across
projects). The skill searches both — project root `.env` takes priority.

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

### Step 2 — Write `.env` ❓ → 🤖

```bash
cp .env.example .env
```

**Ask user — required (must have before continuing):**

| Variable | File | Question to ask user |
|---|---|---|
| `VB_REMOTE_HOST` | `.env` | "Hostname or IP of your EDA server?" |
| `VB_REMOTE_USER` | `.env` | "SSH username on that server?" |
| `CDS_LIB_PATH_28` | `.env` | "Remote Linux path to your T28 `cds.lib`? (e.g. `/home/youruser/TSMC28/cds.lib`)" |

**Ask user — optional (use defaults if not provided):**

| Variable | File | Default | Question to ask user |
|---|---|---|---|
| `VB_REMOTE_PORT` | `.env` | `22` | "Non-standard SSH port?" |
| `VB_JUMP_HOST` | `.env` | — | "Jump/bastion hostname? (blank = direct SSH)" |
| `VB_JUMP_USER` | `.env` | = `VB_REMOTE_USER` | "Jump host username?" |
| `VB_FS_MODE` | `.env` | auto-detect | "`shared` (NFS) or `remote` (Windows/no NFS)? Blank = auto." |
| `AMS_OUTPUT_ROOT` | `.env` | `<project-root>/output` | "Custom output directory?" |

Write the collected values directly into `.env`. Example of a complete filled-in file:

```bash
VB_REMOTE_HOST=eda-server.mysite.com
VB_REMOTE_USER=jdoe
VB_JUMP_HOST=bastion.mysite.com
CDS_LIB_PATH_28=/home/jdoe/TSMC28/llm_IO/cds.lib
VB_FS_MODE=remote
AMS_OUTPUT_ROOT=C:/Users/jdoe/Desktop/bridge-Agent/output
```

---

### Step 3 — Write `site_local.csh` ❓ → 🤖

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

### Step 4 — Start bridge and verify 🤖

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
├── .env                                           ← written in Step 2
├── .env.example                                   ← template (tracked in git)
├── virtuoso-bridge-lite/                          ← bridge source (editable install)
└── .claude/skills/io-ring-orchestrator-T28/
    └── assets/external_scripts/calibre/
        └── site_local.csh                         ← written in Step 3
```

`AMS_PYTHON` in `SKILL.md` Step 0 finds `.venv` at project root automatically —
no manual activation needed when Claude Code runs scripts.
