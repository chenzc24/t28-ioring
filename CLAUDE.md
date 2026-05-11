# Claude Code Instructions

This file intentionally mirrors `AGENTS.md` so Claude Code receives the same
engineering guardrails as other coding agents. Keep both files in sync.

This repository is a T28 IO ring generation skill. Treat core generation logic as
high-risk: small edits can create invalid layouts, DRC/LVS failures, or process
rule regressions.

## Operating Principles

- Follow `SKILL.md` for workflow order, exit-code handling, and repair-loop
  limits.
- Read the relevant input JSON, generated artifacts, logs, and references before
  editing files.
- Preserve user intent: signal names, duplicates, side order, voltage domains,
  and explicitly provided device hints.
- Prefer the smallest repair at the earliest safe layer of the workflow.
- Do not silently change device mapping, pin schema, corner/filler behavior,
  domain-continuity rules, or DRC/LVS rule interpretation.

## Failure Triage

When a workflow step fails, classify the problem before editing:

1. User input or semantic intent issue
2. Environment, bridge, Virtuoso, Calibre, or PDK configuration issue
3. Generated JSON or generated `.il` issue
4. Core engine, generator, or shared rule bug

Do not modify core code until input/config/generated-output causes have been
ruled out with evidence.

## Preferred Repair Order

1. Fix semantic intent JSON or draft intent data.
2. Fix local configuration, environment paths, or bridge setup.
3. Regenerate confirmed config.
4. Regenerate schematic/layout `.il`.
5. Only then consider engine, generator, or shared rule changes.

For DRC/LVS failures, follow the Step 9/10 repair loops in `SKILL.md`. Prefer
semantic intent or configuration fixes before pin-level or generator edits.

## Core Code Guardrails

Core code includes:

- `scripts/enrich_intent.py`
- `scripts/generate_layout.py`
- `scripts/generate_schematic.py`
- `scripts/build_confirmed_config.py`
- `scripts/run_drc.py`, `scripts/run_lvs.py`, and `scripts/run_pex.py`
- `skill_code/*.il`
- reference files that affect device mapping, pin generation, corners, fillers,
  domain continuity, or validation gates

Before editing core code, collect and report:

- failing command
- failing step number
- input JSON path
- stderr/log excerpt
- suspected root cause
- why semantic-intent, generated-output, or configuration repair is insufficient
- proposed minimal code change

Stop and ask for confirmation before changing core algorithms, device maps, pin
connection schemas, corner/filler insertion, continuity gates, or DRC/LVS rule
interpretation.

## Generated Files

- Generated files under `output/` are run artifacts, not source of truth.
- It is acceptable to inspect and regenerate them.
- Do not patch generated files as the only fix unless the user explicitly asks
  for a one-off artifact repair.

## Validation

After any change, rerun the smallest relevant workflow step and report exact
pass/fail status. For code changes, include the command that was run and the
artifact path that proves the fix.
