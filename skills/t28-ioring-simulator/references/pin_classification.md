# Pin Classification Rules - SIM-IO Testbench

The LLM reads `pin_info.json` (pin names, directions, schematic coordinates)
alongside this document and produces `pin_classifications.json`.
The code in `sim_io/flow.py` consumes that JSON to build the testbench schematic.

---

## 0. IO Ring Device -> Domain Mapping

IO ring pins come from two pad families defined in
`io-ring-orchestrator-T28/references/enrichment_rules_T28.md`:

| T28 Pad Devices | Domain | Typical signal names |
|---|---|---|
| `PVDD3AC`, `PVDD1AC` | `analog` | VDDIB, VDDSAR, VAMP, VDD* |
| `PVSS3AC`, `PVSS1AC` | `analog` | VSSIB, VSSSAR, GAMP, GADC*, VSS*, GND_* |
| `PDB3AC` | `analog` | IB*, IBUF*, VCM* |
| `PVDD2POC` | `digital` | typically literally named `PVDD2POC` |
| `PVSS2DGZ` | `digital` | typically literally named `PVSS2DGZ` |
| `PVDD1DGZ` | `digital` | VIOL or similar low-voltage IO supply |
| `PVSS1DGZ` | `digital` | GIOL or similar low-voltage IO ground |
| `PDDW04S*`, `PDDW16SDGZ` | `digital` | RST, D*, SCK, SDI, SDO, SLP, SYNC |

The supply pin naming in a specific design may differ from these examples -
always infer the domain from the actual pad device type in the enrichment rules,
or from name patterns and surrounding context in `pin_info.json`.

---

## 1. Three-Step Classification Process

### Step 1 - Device Class Assignment

Assign one `device_class` to every **outer (left-side)** pin.
Do **not** classify `_CORE` pins - the code handles them automatically.

| `device_class` | How to identify | Domain |
|---|---|---|
| `analog_power` | PVDD*/PVDD1AC/PVDD3AC device; supply names VDD*, VDDIB, VDDSAR, VAMP | `analog` |
| `analog_ground` | PVSS*/PVSS1AC/PVSS3AC device; ground names VSS*, GND_*, GAMP, GADC* | `analog` |
| `analog_current` | PDB3AC device; names starting with `IB*`, `IBUF*` | `analog` |
| `analog_reference` | common-mode/reference pins such as `VCM*`, `VINCM*`, `VREF*` that are not supplies or grounds | `analog` |
| `dig_hv_power` | PVDD2POC device; usually literally named `PVDD2POC` | `digital` |
| `dig_hv_ground` | PVSS2DGZ device; usually literally named `PVSS2DGZ` | `digital` |
| `dig_lv_power` | PVDD1DGZ device; e.g., `VIOL`, `IOVDDL` | `digital` |
| `dig_lv_ground` | PVSS1DGZ device; e.g., `GIOL`, `IOVSS` | `digital` |
| `digital_io_input` | PDDW*/PDDW16SDGZ; direction=input; RST, SCK, SDI, SLP | `digital` |
| `digital_io_output` | PDDW*/PDDW16SDGZ; direction=output; D*, SDO | `digital` |

**Classification priority** (first match wins):
1. `PVDD2POC`, `PVSS2DGZ`, `PVDD1DGZ` by exact name -> `dig_hv_power / dig_hv_ground / dig_lv_power`
2. `GIOL`, `PVSS1DGZ`, `IOVSS` patterns -> `dig_lv_ground`
3. `IB*`, `IBUF*` prefix -> `analog_current` (check before analog_power/analog_ground)
4. `VCM*`, `VINCM*`, `VREF*` reference/common-mode names -> `analog_reference`
5. Analog supply name patterns + context -> `analog_power` or `analog_ground`
6. Digital IO direction/name patterns -> `digital_io_input` or `digital_io_output`
7. Ambiguous digital bidirectional -> default to `digital_io_input` (conservative)

### Step 2 - Inner Pin Resolution (code-handled, LLM awareness only)

After symbol redistribution, each outer (left) pin has a corresponding inner (right) pin:
- If `{pin_name}_CORE` exists in `pin_info.json` -> inner = `{pin_name}_CORE`
- Otherwise -> inner = `{pin_name}` duplicate on the right side

The code resolves this automatically. The LLM **does not** need to specify inner pin names.
However, the LLM must know this to correctly determine the `local_pvss` inner pin reference.

### Step 3 - Analog Local Ground Zone Assignment (**LLM JUDGMENT REQUIRED**)

Each `analog_ground` (PVSS) device defines a **local ground zone**.
Every `analog_power`, `analog_current`, and floating reference pin must be assigned
to exactly one zone.

> **Why only name + position, not device type?**
> `pin_info.json` contains only pin names, directions, and coordinates - the pad device
> type (e.g., PVDD3AC vs PVDD1AC) is not available. Do NOT try to infer device class from
> enrichment_rules; use only the information in `pin_info.json`.

**The `y` coordinate IS usable.** TSG uses geometric sorting (`ssgSortPins = geometric`),
so the `y` values in `pin_info.json` preserve the original schematic vertical order.
Pins that are adjacent in the schematic have similar `y` values.

**Grouping rules (apply in this order):**

1. **Name suffix matching (highest confidence)** - strip the type prefix (`VDD/VSS/GND/IB/VCM/VREF`)
   and compare the remaining suffix to the PVSS pin name.
   - `VSSIB` covers: `VDDIB` (suffix `IB`), `IB3` (prefix `IB`), `IB4`
   - `GADC2` covers: `VADC2` (suffix `ADC2`), `VCM_ADC2` (suffix `ADC2`)
   - `GAMP` covers: `VAMP` (suffix `AMP`), `IBVMP` (suffix `VMP`, loose match)

2. **y-coordinate proximity (for ambiguous pins)** - assign to the `analog_ground` pin
   with the closest `y` value. This reflects original schematic adjacency.

3. **Freely assignable reference pins** - pins named `VCM*`, `VREF*`, `VINCM*` have no
   strict name-matched zone constraint. They still MUST choose one analog local ground:
   use name similarity first, then `y` proximity, and if neither is informative choose any
   nearby analog PVSS. This chosen PVSS must be written into `local_pvss`, and the reason
   should say it was selected as a nearby local ground because no stronger naming match
   exists. Example: `VCM1` may use `GAMP` if it is the nearby analog ground zone.

4. **All analog non-ground pins must be assigned** - every `analog_power` and
   `analog_current` pin must appear in `analog_local_grounds[].members`. Analog
   references (`VCM*`, `VINCM*`, `VREF*`) should also appear in the chosen zone's
   `members` list so the local-ground choice is explicit.

Output: declare `analog_local_grounds[]` at the top level of the JSON.
Each `analog_power`, `analog_current`, and `analog_reference` pin must have
`local_pvss` set to the name of its zone's PVSS device.

---

## 2. Topology Rules per Device Class

The following rules define EXACTLY which devices are placed and how they are wired.
"analogLib/gnd" = placed as visual reference; all MINUS terminals use `"gnd!"` directly (Virtuoso global ground net).
"local_pvss_inner" = `{local_pvss}_CORE` if exists, else `{local_pvss}` duplicate.

---

### 2.1 `analog_ground` (PVSS device)

Only the **outer** side gets a `vdc~=0` source. The inner PVSS pin is NOT driven by a
separate device - it is the common MINUS node shared by the inner `idc` (from `analog_power`)
and the inner `vdc` (from `analog_current`) in the same local zone.

```
OUTER side:                         DUT (left pin)
  vdc~=0 PLUS --- [VSSIB net] ------ VSSIB outer
  vdc~=0 MINUS -- "gnd!"

INNER side:                         DUT (right pin = VSSIB_CORE or VSSIB dup.)
  [VSSIB_CORE net] --- idc MINUS  (inner idc of VDDIB, see Section 2.2)
  [VSSIB_CORE net] --- vdc MINUS  (inner vdc of IB3, see Section 2.3)
  <- no separate source placed here
```

**JSON fields required**: `name`, `device_class`, `domain`, `local_pvss` (= self, own name).
No `stimulus` or `inner_stimulus` fields needed.

---

### 2.2 `analog_power` (PVDD device)

```
OUTER (left):                DUT                    INNER (right):
                          +--------+
 vdc PLUS --- [VDDIB] --- VDDIB   VDDIB_CORE --- idc PLUS
 vdc MINUS -- "gnd!"    +--------+               idc MINUS -- [VSSIB_CORE or VSSIB]
 vdc = ~0.9 V (non-round)                          idc = few mA (non-round)
```

- **Outer device**: `vdc`
  - PLUS -> outer pin name (e.g., `VDDIB`)
  - MINUS -> `"gnd!"` (analogLib/gnd, global reference)
  - Voltage: **~0.9 V, non-round** (e.g., `0.87`, `0.91`, `0.93`)

- **Inner device**: `idc`
  - PLUS -> inner pin (`VDDIB_CORE` or `VDDIB` duplicate)
  - MINUS -> local PVSS inner pin (`VSSIB_CORE` or `VSSIB` duplicate)
  - Current: **few mA, non-round** (e.g., `2.3m`, `4.7m`, `1.8m`)

**LLM must provide**: `stimulus_params.vdc`, `inner_params.idc`, `local_pvss`

---

### 2.3 `analog_current` (IB* / PDB3AC device)

Outer current source is INVERTED vs normal: PLUS=gnd, MINUS=pin (current flows INTO pin).

```
OUTER (left):                DUT                    INNER (right):
                          +--------+
 idc PLUS --- "gnd!"     IB3     IB3_CORE --- vdc PLUS
 idc MINUS -- [IB3] ---- +--------+            vdc MINUS -- [VSSIB_CORE or VSSIB]
 idc = positive, few uA (non-round)             vdc = ~few hundred mV (non-round)
```

- **Outer device**: `idc`
  - PLUS -> `"gnd!"` (analogLib/gnd)
  - MINUS -> outer pin name (e.g., `IB3`)
  - Current: **positive, few uA, non-round** (e.g., `11.3u`, `8.7u`)
  - > Positive value because PLUS is at gnd, MINUS at pin -> conventional current flows gnd->pin -> into DUT OK

- **Inner device**: `vdc`
  - PLUS -> inner pin (`IB3_CORE` or `IB3` duplicate)
  - MINUS -> local PVSS inner pin (`VSSIB_CORE` or `VSSIB` duplicate)
  - Voltage: **few hundred mV, non-round** (e.g., `0.34`, `0.27`, `0.41`)

**LLM must provide**: `stimulus_params.idc` (positive), `inner_params.vdc`, `local_pvss`

> **CRITICAL**: `analog_current` outer idc is INVERTED (PLUS=gnd, MINUS=pin).
> This is different from all other device classes where PLUS=pin, MINUS=gnd.

---

### 2.3A `analog_reference` (`VCM*`, `VINCM*`, `VREF*`)

Common-mode/reference pins are analog inputs, not supplies and not grounds. They may not
have a reliable suffix match to a local PVSS name, so choose a nearby analog local ground
zone and record it explicitly in `local_pvss`.

```
OUTER side:                         DUT (left pin)
  vdc PLUS ---- [VCM1 net] -------- VCM1 outer
  vdc MINUS --- "gnd!"
  vdc = few hundred mV, non-round (e.g., 0.43, 0.37, 0.52)

INNER side:                         DUT (right pin = VCM1_CORE or VCM1 dup.)
  idc PLUS ---- [VCM1_CORE/VCM1 inner net]
  idc MINUS --- local PVSS inner pin (`GAMP_CORE` or `GAMP` duplicate)
  idc = small non-round current, usually uA range (e.g., 3.1u)
```

- **Outer device**: `vdc`, PLUS->pin, MINUS->`"gnd!"`
- **Inner device**: `idc`, PLUS->inner reference pin, MINUS->local PVSS inner pin
- **Local ground selection**: if no naming match exists, choose any nearby analog PVSS
  using schematic/pin `y` proximity. This is intentional; do not leave `local_pvss`
  empty and do not connect the inner source to global ground.

**LLM must provide**: `stimulus_params.vdc`, `inner_params.idc`, `local_pvss`

---

### 2.4 `dig_hv_power` (PVDD2POC)

```
OUTER (left):                 DUT
 vdc PLUS --- [PVDD2POC] --- PVDD2POC outer
 vdc MINUS -- "gnd!"
 vdc = 1.8 V (fixed)

 idc placed between PVDD2POC net and PVSS2DGZ net (see Section 3 Digital Supply Pairs)
```

- **Outer device**: `vdc`, PLUS->pin, MINUS->`"gnd!"`, voltage = **1.8 V** (fixed, not adjustable)
- **Inner device**: none (the _CORE/duplicate pin gets a `noConn` label in code)

**LLM must provide**: `local_dig_gnd = "PVSS2DGZ"` (the paired HV ground pin name)

---

### 2.5 `dig_hv_ground` (PVSS2DGZ)

```
OUTER (left):
 vdc PLUS --- [PVSS2DGZ] --- PVSS2DGZ outer
 vdc MINUS -- "gnd!"
 vdc = ~10-20 mV, non-round (e.g., 0.017)
```

- **Outer device**: `vdc`, PLUS->pin, MINUS->`"gnd!"`, voltage: **~0 V, non-round**
- **Inner device**: none

---

### 2.6 `dig_lv_power` (PVDD1DGZ - e.g., VIOL)

```
OUTER (left):
 vdc PLUS --- [VIOL] --- VIOL outer
 vdc MINUS -- "gnd!"
 vdc = ~0.9 V, non-round (e.g., 0.87, 0.92)

 idc placed between VIOL net and GIOL net (see Section 3 Digital Supply Pairs)
```

- **Outer device**: `vdc`, PLUS->pin, MINUS->`"gnd!"`, voltage: **~0.9 V, non-round**
- **Inner device**: none

**LLM must provide**: `local_dig_gnd = "<dig_lv_ground pin name>"` (e.g., `"GIOL"`)

---

### 2.7 `dig_lv_ground` (PVSS1DGZ - e.g., GIOL)

```
OUTER (left):
 vdc PLUS --- [GIOL] --- GIOL outer
 vdc MINUS -- "gnd!"
 vdc = ~10-20 mV, non-round (e.g., 0.013)
```

- **Outer device**: `vdc`, PLUS->pin, MINUS->`"gnd!"`, voltage: **~10-20 mV, non-round**
- **Inner device**: none
- This pin name becomes the `digital_low_gnd` value in the top-level JSON.

---

### 2.8 `digital_io_input` (e.g., RST, SCK, SDI, SLP)

Each input IO gets its **own** outer vpulse and its **own** inner cap.

```
OUTER (left):                    DUT                   INNER (right):
 vpulse PLUS --- [RST] ---------- RST    RST_CORE --- cap PLUS
 vpulse MINUS -- "gnd!"                               cap MINUS -- [GIOL]
 v1=0, v2=1.7, per=10n                                 c = 10pF (fixed)
```

- **Outer device**: `vpulse`
  - PLUS -> pin name
  - MINUS -> `"gnd!"`
  - Params: `v1=0, v2=1.7, per=10n, tr=0.1n, tf=0.1n, pw=5n`
  - **v2 = 1.7 V** (fixed), **per = 10 ns** (fixed)

- **Inner device**: `cap`
  - PLUS -> inner pin (`RST_CORE` or `RST` duplicate)
  - MINUS -> `digital_low_gnd` (e.g., `GIOL`)
  - **c = 10pF** (fixed)

**LLM must provide**: `stimulus_params` (v2=1.7, per=10n are fixed; other params can be
as shown above)

---

### 2.9 `digital_io_output` (e.g., D*, SDO)

All output IOs share **one** inner vpulse (placed once by code, connected to all output _CORE
nets). Each output IO gets its **own** outer cap.

```
OUTER (left):                    DUT                   INNER (right):
 cap PLUS --- [D0] -------------- D0    D0_CORE ---+
 cap MINUS -- "gnd!"                               |
 c = 10pF                         D1    D1_CORE ---+-- [shared vpulse PLUS]
                                  ...               |   vpulse MINUS -- [GIOL]
                                  Dn    Dn_CORE ---+
```

- **Outer device**: `cap`
  - PLUS -> pin name
  - MINUS -> `"gnd!"`
  - **c = 10pF** (fixed)

- **Inner device**: shared `vpulse` (one instance, PLUS connected to ALL output _CORE nets)
  - Params declared in top-level `shared_output_vpulse`
  - **v2 = 1.62 V** (fixed), **per = 7 ns** (fixed)
  - MINUS -> `digital_low_gnd` (e.g., `GIOL`)

No per-pin inner fields needed. Just declare `device_class: "digital_io_output"`.

---

## 3. Digital Supply Current Sources

Between each digital supply pair, a current source provides bulk operating current.
Declared in top-level `digital_supply_pairs[]`.

```
[PVDD2POC net] -- idc PLUS
[PVSS2DGZ net] -- idc MINUS
idc = few mA, non-round

[VIOL net] -- idc PLUS
[GIOL net] -- idc MINUS
idc = few mA, non-round
```

The code places one `idc` instance per pair. LLM provides the `idc` value.

---

## 4. Value Selection Rules

When a rule says "non-round", pick a value that is NOT a clean integer, .5, .25, etc.

| Quantity | Typical range | Bad (round) | Good (non-round) |
|---|---|---|---|
| Analog supply vdc | 0.85-0.95 V | `0.9` | `0.87`, `0.91`, `0.93` |
| Analog inner idc (PVDD->PVSS) | 1-5 mA | `2m`, `3m` | `2.3m`, `4.7m`, `1.8m` |
| Analog IB outer idc | 5-15 uA | `10u` | `11.3u`, `8.7u`, `6.4u` |
| Analog IB inner vdc | 250-450 mV | `0.3`, `0.4` | `0.34`, `0.27`, `0.41` |
| Analog ground (PVSS) vdc | 10-20 mV | `0` | `0.017`, `0.013` |
| Digital LV supply vdc | 0.85-0.95 V | `0.9` | `0.87`, `0.92` |
| Digital HV supply vdc | 1.8 V (fixed) | - | `1.8` <- exact OK |
| PVSS2DGZ / dig HV gnd vdc | 10-20 mV | `0` | `0.017`, `0.023` |
| PVSS1DGZ / dig LV gnd vdc | 10-20 mV | `0` | `0.013`, `0.019` |
| Digital supply pair idc | 3-8 mA | `5m` | `5.3m`, `3.7m` |
| Digital input IO v2 | 1.7 V (fixed) | - | `1.7` <- exact OK |
| Digital output IO v2 | 1.62 V (fixed) | - | `1.62` <- exact OK |

Reason: non-round values stress the circuit more realistically and avoid accidental
cancellations in simulation.

---

## 5. Output JSON Schema

The LLM outputs `pin_classifications.json` with the following structure.
**Only classify outer (left-side) pins** - pins whose name does NOT end in `_CORE`
and whose `side` is `"left"` in `pin_info.json`.

```json
{
  "lib": "<library name>",
  "cell": "<cell name>",
  "vdd_value": 0.9,
  "vio_high": 1.8,
  "llm_model": "<model name>",
  "timestamp": "<ISO timestamp>",

  "digital_low_gnd": "GIOL",

  "analog_local_grounds": [
    {
      "pvss_name": "VSSIB",
      "members": ["VDDIB", "IB3", "IB4"]
    },
    {
      "pvss_name": "GADC2",
      "members": ["VADC2", "VCM1"]
    }
  ],

  "digital_supply_pairs": [
    {
      "power": "PVDD2POC",
      "ground": "PVSS2DGZ",
      "idc": "5.3m"
    },
    {
      "power": "VIOL",
      "ground": "GIOL",
      "idc": "3.7m"
    }
  ],

  "shared_output_vpulse": {
    "v1": "0",
    "v2": "1.62",
    "per": "7n",
    "tr": "0.1n",
    "tf": "0.1n",
    "pw": "3.5n"
  },

  "pins": [
    ...
  ]
}
```

### 5.1 Per-pin entry schema

Every left-side pin gets one entry. Fields marked **LLM** must be filled by the LLM.
Field names here match the `PinClassification` dataclass in `sim_io/pin_types.py`.

| Field | Type | LLM? | Description |
|---|---|---|---|
| `name` | string | LLM | Pin name from `pin_info.json` (left side only) |
| `device_class` | string | **LLM** | One of the classes in Section 1 (new field, extends `pin_type`) |
| `pin_type` | string | LLM | Legacy field; set to same value as `device_class` for compat |
| `domain` | string | LLM | `"analog"` or `"digital"` |
| `local_pvss` | string | **LLM** | *(analog only)* PVSS pin name that is this pin's local ground zone anchor |
| `local_dig_gnd` | string | **LLM** | *(dig_hv_power, dig_lv_power only)* paired ground pin name |
| `stimulus` | string | LLM | Outer stimulus cell: `"vdc"`, `"idc"`, `"vpulse"`, or null |
| `stimulus_params` | object | **LLM** | Outer stimulus params (non-round values) |
| `load` | string | LLM | Outer load cell: `"cap"` for `digital_io_output`, else null |
| `load_params` | object | LLM | Outer load params (e.g., `{"c": "10p"}`) |
| `inner_stimulus` | string | LLM | Inner device: `"idc"`, `"vdc"`, `"cap"`, or null |
| `inner_params` | object | **LLM** | Inner device params (non-round values) |
| `confidence` | float | LLM | 0.0-1.0 |
| `reason` | string | LLM | Brief classification rationale |

**Omit** `stimulus`/`inner_stimulus` for device classes with no stimulus
(see Section 2.1 for `analog_ground`, Section 2.4-2.7 for digital supply, Section 2.9 for outputs).

### 5.2 Top-level field reference

| Field | LLM? | Description |
|---|---|---|
| `digital_low_gnd` | **LLM** | Name of the `dig_lv_ground` pin (e.g., `"GIOL"`) |
| `analog_local_grounds[].pvss_name` | **LLM** | PVSS device pin name defining the zone |
| `analog_local_grounds[].members` | **LLM** | All `analog_power`, `analog_current`, and `analog_reference` pins in this zone |
| `digital_supply_pairs[].power` | **LLM** | Name of the digital supply power pin |
| `digital_supply_pairs[].ground` | **LLM** | Name of the paired digital ground pin |
| `digital_supply_pairs[].idc` | **LLM** | Current value (non-round string, e.g., `"5.3m"`) |
| `shared_output_vpulse` | **LLM** | Params for the single digital output vpulse (v2, per fixed) |

---

## 6. Complete Example

Given `pin_info.json` with these left-side pins:
`VDDIB, VSSIB, IB3, VIOL, GIOL, PVDD2POC, PVSS2DGZ, RST, D0, D1`

And assuming: `VSSIB_CORE` and `GIOL` and `D0_CORE, D1_CORE, RST_CORE` exist in the pin list.

```json
{
  "lib": "myLib",
  "cell": "myCell",
  "vdd_value": 0.9,
  "vio_high": 1.8,
  "llm_model": "claude-sonnet-4-6",
  "timestamp": "2026-05-04T10:00:00Z",

  "digital_low_gnd": "GIOL",

  "analog_local_grounds": [
    {
      "pvss_name": "VSSIB",
      "members": ["VDDIB", "IB3"]
    }
  ],

  "digital_supply_pairs": [
    {"power": "PVDD2POC", "ground": "PVSS2DGZ", "idc": "5.3m"},
    {"power": "VIOL",     "ground": "GIOL",      "idc": "3.7m"}
  ],

  "shared_output_vpulse": {
    "v1": "0", "v2": "1.62", "per": "7n",
    "tr": "0.1n", "tf": "0.1n", "pw": "3.5n"
  },

  "pins": [
    {
      "name": "VDDIB",
      "device_class": "analog_power",
      "pin_type": "analog_power",
      "domain": "analog",
      "local_pvss": "VSSIB",
      "stimulus": "vdc",
      "stimulus_params": {"vdc": "0.87"},
      "inner_stimulus": "idc",
      "inner_params": {"idc": "2.3m"},
      "confidence": 0.95,
      "reason": "VDD prefix + IB suffix -> analog power supply, zone VSSIB by name match"
    },
    {
      "name": "VSSIB",
      "device_class": "analog_ground",
      "pin_type": "ground",
      "domain": "analog",
      "local_pvss": "VSSIB",
      "confidence": 0.98,
      "reason": "VSS prefix + IB suffix -> analog ground device, defines IB local zone"
    },
    {
      "name": "IB3",
      "device_class": "analog_current",
      "pin_type": "bias_current",
      "domain": "analog",
      "local_pvss": "VSSIB",
      "stimulus": "idc",
      "stimulus_params": {"idc": "11.3u"},
      "inner_stimulus": "vdc",
      "inner_params": {"vdc": "0.34"},
      "confidence": 0.95,
      "reason": "IB prefix -> PDB3AC current bias, zone VSSIB by suffix and position"
    },
    {
      "name": "PVDD2POC",
      "device_class": "dig_hv_power",
      "pin_type": "power",
      "domain": "digital",
      "local_dig_gnd": "PVSS2DGZ",
      "stimulus": "vdc",
      "stimulus_params": {"vdc": "1.8"},
      "confidence": 0.99,
      "reason": "Exact name PVDD2POC = digital high-voltage supply, 1.8V fixed"
    },
    {
      "name": "PVSS2DGZ",
      "device_class": "dig_hv_ground",
      "pin_type": "ground",
      "domain": "digital",
      "stimulus": "vdc",
      "stimulus_params": {"vdc": "0.017"},
      "confidence": 0.99,
      "reason": "Exact name PVSS2DGZ = digital high-voltage ground, ~0V"
    },
    {
      "name": "VIOL",
      "device_class": "dig_lv_power",
      "pin_type": "power",
      "domain": "digital",
      "local_dig_gnd": "GIOL",
      "stimulus": "vdc",
      "stimulus_params": {"vdc": "0.87"},
      "confidence": 0.97,
      "reason": "VIOL = PVDD1DGZ low-voltage IO supply ~0.9V, paired with GIOL"
    },
    {
      "name": "GIOL",
      "device_class": "dig_lv_ground",
      "pin_type": "ground",
      "domain": "digital",
      "stimulus": "vdc",
      "stimulus_params": {"vdc": "0.013"},
      "confidence": 0.99,
      "reason": "GIOL = PVSS1DGZ digital LV ground ~0V, reference for digital IO inner caps"
    },
    {
      "name": "RST",
      "device_class": "digital_io_input",
      "pin_type": "digital_input",
      "domain": "digital",
      "stimulus": "vpulse",
      "stimulus_params": {
        "v1": "0", "v2": "1.7", "per": "10n",
        "tr": "0.1n", "tf": "0.1n", "pw": "5n"
      },
      "confidence": 0.95,
      "reason": "RST = reset signal, direction=input, outer vpulse v2=1.7V per=10ns"
    },
    {
      "name": "D0",
      "device_class": "digital_io_output",
      "pin_type": "digital_output",
      "domain": "digital",
      "load": "cap",
      "load_params": {"c": "10p"},
      "confidence": 0.90,
      "reason": "D prefix, direction=output -> digital IO output; outer cap, shares inner vpulse"
    },
    {
      "name": "D1",
      "device_class": "digital_io_output",
      "pin_type": "digital_output",
      "domain": "digital",
      "load": "cap",
      "load_params": {"c": "10p"},
      "confidence": 0.90,
      "reason": "D prefix, direction=output -> digital IO output; outer cap, shares inner vpulse"
    }
  ]
}
```

---

## 7. LLM Self-Check Before Writing Output

- [ ] Every `analog_power` and `analog_current` pin has `local_pvss` set
- [ ] Every `analog_reference` pin (`VCM*`, `VINCM*`, `VREF*`) has `local_pvss` set, even if the local ground was chosen only by proximity
- [ ] Every `analog_ground` pin has `local_pvss` = its own name
- [ ] `analog_local_grounds[].members` covers ALL `analog_power`, `analog_current`, and `analog_reference` pins
- [ ] PVDD3AC/PVSS3AC provider pairs have their own isolated zone (not shared with consumers)
- [ ] `digital_low_gnd` is set to the `dig_lv_ground` pin name
- [ ] `digital_supply_pairs` covers both HV pair and LV pair
- [ ] All `stimulus_params` use non-round values (no clean integers/halves, except fixed specs)
- [ ] All `inner_params` use non-round values
- [ ] `analog_current` outer idc is **positive** (PLUS=gnd, MINUS=pin -> current into pin)
- [ ] `dig_hv_power` vdc = 1.8 V (fixed)
- [ ] `dig_hv_ground` vdc is ~10-20 mV non-round (e.g., 0.017)
- [ ] `dig_lv_ground` vdc is ~10-20 mV non-round (e.g., 0.013)
- [ ] All digital IO pins classified as input or output (no bidirectional)
- [ ] `shared_output_vpulse` declared with v2=1.62, per=7n (fixed)
- [ ] Only left-side pins (no `_CORE` suffix, side="left") appear in `pins[]`
- [ ] Confidence < 0.7 -> flag reason for review

---

## 8. Code Interface (Developer Reference)

JSON field names match `PinClassification` fields directly. New fields need to be added
to the dataclass and loader in `sim_io/pin_types.py`:

### 8.1 Per-pin field mapping

| JSON field | PinClassification field | Status | Notes |
|---|---|---|---|
| `name` | `name` | existing | |
| `device_class` | `device_class` | **ADD** | Primary dispatch key; replaces `pin_type` logic |
| `pin_type` | `pin_type` | existing | Keep for fallback; set same value as `device_class` |
| `domain` | `domain` | existing | |
| `local_pvss` | `local_pvss` | **ADD** | Replaces `ground_net`; stores PVSS pin name directly |
| `local_dig_gnd` | `local_dig_gnd` | **ADD** | For dig_hv_power / dig_lv_power |
| `stimulus` | `stimulus` | existing | Outer device cell |
| `stimulus_params` | `stimulus_params` | existing | |
| `load` | `load` | existing | `"cap"` for digital_io_output |
| `load_params` | `load_params` | existing | |
| `inner_stimulus` | `inner_stimulus` | existing | |
| `inner_params` | `inner_params` | existing | |
| `confidence` | `confidence` | existing | |
| `reason` | `reason` | existing | |

### 8.2 Top-level fields to add to `ClassificationResult`

| Field | Type | Purpose |
|---|---|---|
| `digital_low_gnd` | `str` | Name of `dig_lv_ground` pin; inner cap MINUS for digital IO input |
| `analog_local_grounds` | `list[dict]` | Zone map `{pvss_name, members[]}`; inner MINUS resolution for analog |
| `digital_supply_pairs` | `list[dict]` | `{power, ground, idc}`; code places idc between the outer nets |
| `shared_output_vpulse` | `dict` | Vpulse params for the single shared digital-output inner driver |

### 8.3 Wiring rules implemented by code (not in JSON)

**Outer MINUS** - always `"gnd!"` for every outer device (Virtuoso global ground net):
- `analog_power` outer vdc MINUS -> `"gnd!"`
- `analog_current` outer idc: PLUS=`"gnd!"`, MINUS=`pin.name` <- **inverted** vs normal
- `dig_hv_power / dig_hv_ground / dig_lv_power / dig_lv_ground` outer vdc MINUS -> `"gnd!"`
- `digital_io_input` outer vpulse MINUS -> `"gnd!"`
- `digital_io_output` outer cap MINUS -> `"gnd!"`

**Inner MINUS** - derived from `device_class` + context:
- `analog_power` inner `idc` MINUS -> `_find_core_pin_name(cls.local_pvss, right_pins)`
  (= `VSSIB_CORE` if exists, else `VSSIB` duplicate; this is a bare wire net with no source)
- `analog_current` inner `vdc` MINUS -> same resolution as above
- `digital_io_input` inner `cap` MINUS -> `result.digital_low_gnd`
- `digital_io_output` shared vpulse MINUS -> `result.digital_low_gnd`

**Special placements** triggered by `device_class`:
- `analog_ground`: code places **one** PVSS `vdc~=0` instance on the outer side only; the inner PVSS pin is left as a bare wire net - it becomes the shared MINUS node for the inner idc (Section 2.2) and inner vdc (Section 2.3) of the same local zone
- `digital_io_output`: code places **one** shared vpulse connected to ALL output _CORE nets
- `dig_hv_power` / `dig_lv_power`: code places idc between power and ground outer nets
  (using `digital_supply_pairs` for current values)
