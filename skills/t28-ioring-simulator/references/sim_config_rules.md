# IO Ring Simulation Configuration Rules

Rules for generating a simulation deck configuration for IO Ring testbenches.
The LLM reads this file plus `pin_classifications.json` and produces `sim_config.json`.

**Key principle: the LLM decides WHAT to measure; the code decides HOW to express it
in Maestro OCEAN syntax.** Never write OCEAN expressions, eval_type, or save_signals
directly - specify measurement *intent* and let the code template generate correct syntax.

---

## Core Rules (Non-Negotiable)

1. **No design variables.** Never emit `design_vars` or `parameters`. All voltage/current
   values come directly from `pin_classifications.json` stimulus params - they are already
   fixed numbers.

2. **No AC analysis.** IO Ring cells do not need frequency response. Only DC and transient.

3. **Always run both DC and transient.** DC first (sets operating point), transient second.
   This applies to both analog and digital IO cells - no exceptions.

4. **Power is always calculated from transient.** The code auto-generates the correct
   OCEAN expression when you specify `measures: ["power"]` for a pin. Never write
   `integ(pwr(...))` or `pwr()` yourself.

5. **Do not specify model includes.** Leave `model_includes: []`. testbench_build injects them
   automatically from `_local/site.yaml`.

6. **Do not specify save_signals.** The code auto-determines the correct save level
   (`"all"` when current/power measurements are needed, `"allpub"` otherwise).

---

## Analysis Order and Settings

### 1. DC Operating Point

- **No sweep parameter.** Just an operating point - all sources are at their DC values.
- Runs first to establish initial conditions for transient.
- Applied to both analog and digital cells.

### 2. Transient

- `stop`: should be long enough to see at least 10 full cycles of the slowest `vpulse`
  stimulus. Compute from stimulus params: `tstop = 10 x max(per)` across all `vpulse`
  sources. Minimum: `100n`. Maximum: `10u`. Round to a clean value (e.g. `500n`, `1u`).
- `errpreset=moderate` for digital-dominant cells; `errpreset=conservative` for
  analog-dominant. A cell is "analog-dominant" if more than half its non-ground pins
  are `analog_*`, `reference`, or `bias_current` type.
- `maxstep`: set to `tstop / 1000` (Spectre default is often too coarse for IO switching).

---

## Pin Measurements (Core Output)

Instead of writing OCEAN expressions, specify **measurement intent** per pin.
The code translates intent into correct Maestro outputs automatically.

### What to specify

For each non-ground pin, list what you want to measure:

| Measure | What it produces | When to use |
|---------|-----------------|-------------|
| `"voltage"` | Voltage net waveform (`add_output` type=net) | All non-ground pins |
| `"current"` | Average current through SRC_ device | Power supply pins (VDD, VIOH, VIOL) |
| `"power"` | Average power (VxI) through SRC_ device | Power supply pins (VDD, VIOH, VIOL) |
| `"custom"` | User-supplied expression (use `custom_expr` field) | Special measurements (gain, BW, etc.) |

### Spec constraints

Use the `spec` dict to add pass/fail boundaries:

| Spec key | Meaning | Example |
|----------|---------|---------|
| `"i_max"` | Current must be < this value (amps) | `"0.1"` (100 mA) |
| `"p_max"` | Power must be < this value (watts) | `"0.5"` |
| `"vmax_above"` | Peak voltage must be > this (supports `*VDD`) | `"0.9*VDD"` |
| `"vmin_below"` | Minimum voltage must be < this (supports `*VDD`) | `"0.1*VDD"` |

### Important notes

- **Only request `"current"` or `"power"` for pins that have an SRC_ device placed.**
  These are outer-side (left) power pins. Inner/CORE-side pins do not have SRC_ devices
  - requesting current/power for them will cause OCEAN evaluation errors.
- **Pins with `measures: []` are explicitly skipped.** Use this for ground, no_connect,
  reference, and bias_current pins.
- **Driven common-mode references are measured as voltage.** For `VCM*`, `VINCM*`,
  or `VREF*` pins classified as `analog_reference` with an outer `vdc`, request
  `{"measures": ["voltage"]}` unless the user explicitly wants to skip them.
- **Voltage is always added automatically** when any measurement is requested - you do
  not need to list `"voltage"` separately if you already have `"current"` or `"power"`,
  but it is clearer to include it explicitly.
- **Pins not listed in `pin_measurements`** still get voltage net outputs as a debug
  baseline (unless they are ground/no_connect type).
- **`*VDD` in spec values** is auto-replaced with the actual VDD value by the code.

---

## sim_config.json Schema (Produced by LLM)

```json
{
  "analyses": [
    {
      "name": "dc",
      "enabled": true
    },
    {
      "name": "tran",
      "enabled": true,
      "stop": "<computed tstop, e.g. 200n>",
      "maxstep": "<tstop/1000, e.g. 200p>",
      "errpreset": "moderate"
    }
  ],
  "model_includes": [],
  "save_default": "allpub",
  "pin_measurements": {
    "VDD": {
      "measures": ["voltage", "current", "power"],
      "spec": { "i_max": "0.1" }
    },
    "VIOH": {
      "measures": ["voltage", "current", "power"],
      "spec": { "i_max": "0.1" }
    },
    "VIOL": {
      "measures": ["voltage", "current", "power"],
      "spec": { "i_max": "0.1" }
    },
    "D0": {
      "measures": ["voltage"],
      "spec": { "vmax_above": "0.9*VDD", "vmin_below": "0.1*VDD" }
    },
    "SCK": {
      "measures": ["voltage"],
      "spec": { "vmax_above": "0.9*VDD", "vmin_below": "0.1*VDD" }
    },
    "VADC2": {
      "measures": ["voltage"]
    },
    "OUT": {
      "measures": ["voltage", "custom"],
      "custom_expr": "bandwidth(VF(\"/OUT\"), 3, \"low\")",
      "custom_name": "BW_OUT"
    },
    "GND": {
      "measures": []
    }
  }
}
```

Rules for field values:
- `model_includes`: always leave empty `[]` - injected by testbench_build.
- `save_default`: always `"allpub"` - the code auto-upgrades to `"all"` when current/power
  measurements are detected. Do NOT set `"all"` yourself.
- `pin_measurements`: list every DUT pin. Use `measures: []` for pins to skip.
- `custom_expr` / `custom_name`: only when `"custom"` is in measures. The expression
  uses standard OCEAN syntax (the code handles quote escaping).

---

## Determining `tstop`

1. Collect all `per` values from `vpulse` stimulus params across all pins.
2. `tstop = 10 x max(per)`. If no vpulse sources exist (pure analog cell), use `500n`.
3. Clamp to `[100n, 10u]`.
4. Round to a readable value: prefer multiples of 100n or 500n.

Example: if `per` values are `7n`, `10n`, `14n` -> `tstop = 10 x 14n = 140n` -> round to `200n`.

---

## Simulator Options

Only override when the user explicitly asks. Defaults are:
```
reltol=1e-4  vabstol=1e-6  iabstol=1e-12  gmin=1e-12  temp=27.0  tnom=27.0
```

---

## What NOT to Include

| Item | Reason |
|------|--------|
| `design_vars` / `parameters` block | No design variables in IO Ring TB |
| `ac` analysis | Not applicable to IO Ring |
| DC sweep (`param=VDD start=0 stop=3`) | No sweep - fixed operating point only |
| `outputs` array with OCEAN expressions | Use `pin_measurements` instead - code generates expressions |
| `save_signals` array | Code auto-determines from pin_measurements |
| `eval_type` / `from_analysis` fields | Handled by code, not LLM |
| `info_statements` | Standard set injected by code |
| `save_default: "all"` | Code auto-upgrades; always specify `"allpub"` |
