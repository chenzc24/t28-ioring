# Enrichment Rules — T28

> **Scope of this document.** This file covers **semantic decisions** the AI makes during Step 3: how to classify signals, group them into voltage domains, pick devices, and infer direction. The mechanical work that follows — adding `_H_G`/`_V_G` suffix, wiring every pin to the right domain provider, generating corners from adjacent pads, applying the ring-wide VSS rule — is owned by `enrichment_engine.py` (data: `assets/device_info/device_wiring_T28.json`). Once the AI emits a correct **semantic intent JSON** per §4, the engine produces a fully-wired intent graph deterministically.
>
> Rule of thumb: if a decision is "what should this signal be?" — it's in this document. If a decision is "given that, where does each pin go?" — it's the engine.

---

## 1. Universal Ring Structure Principle

- **CRITICAL — Ring Structure Continuity**: An IO ring is a circular structure, so signals at the beginning and end of the list are adjacent. This applies to both analog and digital signals.
  - **General rule**: If signals appear in two segments (one at the beginning of the list and one at the end), they are considered contiguous because the list wraps around.
  - This principle applies to:
    - **Analog signals**: voltage domain continuity
    - **Digital signals**: digital domain continuity

## 2. User Intent Priority

- **Absolute priority**: Strictly follow user-specified signal order, placement order, and all requirements.
- **Signal preservation**: Preserve all signals with identical names; do not deduplicate.
- **Placement sequence**: Process one side at a time, place signals and pads simultaneously.
- **Voltage domain configuration**:
  - **If user explicitly specifies**: MUST strictly follow user's specification exactly. Do not modify or ask for confirmation.
  - **If user does NOT specify**: AI must analyze and create voltage domains automatically — every signal must belong to a voltage domain, and every analog voltage domain must have one VDD provider and one VSS provider.
- **Workflow execution**: Determine workflow entry point automatically based on user input (intent graph file vs requirements), proceed through all steps.

## 3. On-Demand Clarification Trigger

- **Trigger ownership**: The decision of whether to ask the user is owned by draft/enrichment, NOT by wizard.
- **Wizard role**: `wizard_T28.md` only defines question templates and output schema.

Trigger targeted clarification when any ambiguity condition is true:
1. **Device-class ambiguity**: Device class (analog vs digital, IO vs power, provider vs consumer) cannot be uniquely determined from explicit constraints + rule inference.
2. **Direction ambiguity**: Digital IO direction cannot be resolved with sufficient confidence from explicit constraints + direction rules.
3. **Voltage-domain boundary ambiguity**: A signal/block cannot be uniquely assigned to one analog voltage domain range.

Clarification callback protocol:
1. Pause current step at the ambiguity point.
2. Ask only the minimum questions needed for that ambiguity.
3. Merge returned `wizard_constraints` and continue from the paused point.

Constraint precedence (when no immutable-structure conflict exists):
1. Explicit user prompt constraints
2. On-demand `wizard_constraints`
3. Default classification inference (this document)

(Pin family ambiguity is no longer a clarification trigger — the engine resolves all pin connections from the chosen device.)

---

## 4. Output Format: Semantic Intent JSON

The AI's Step 3 output is `io_ring_semantic_intent.json` — a compact (~30 lines) declaration of classification decisions. The engine reads this and produces the full pin-wired intent graph.

### 4.1 Schema

```json
{
  "schema_version": "1.0",
  "tech_node": "T28",
  "ring_config": {
    "width": 4,
    "height": 4,
    "placement_order": "counterclockwise"
  },
  "instances": [
    {"name": "VCM",   "position": "left_0",  "type": "pad", "device": "PDB3AC",     "domain": "ana_1"},
    {"name": "VDDIB", "position": "left_1",  "type": "pad", "device": "PVDD3AC",    "domain": "ana_1"},
    {"name": "VSSIB", "position": "left_2",  "type": "pad", "device": "PVSS3AC",    "domain": "ana_1"},
    {"name": "RST",   "position": "left_3",  "type": "pad", "device": "PDDW16SDGZ", "domain": "dig_1", "direction": "input"},
    {"name": "D15",   "position": "top_2_3", "type": "inner_pad", "device": "PDDW16SDGZ", "domain": "dig_1", "direction": "output"}
  ],
  "domains": {
    "ana_1": {"kind": "analog",  "vdd_provider": "VDDIB", "vss_provider": "VSSIB"},
    "dig_1": {"kind": "digital", "low_vdd": "VIOL", "low_vss": "GIOL", "high_vdd": "VIOH", "high_vss": "GIOH"}
  },
  "global": {
    "vss_ground": "GIOL",
    "ring_esd": null
  },
  "overrides": {}
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `schema_version` | Yes | string | `"1.0"` |
| `tech_node` | Yes | string | `"T28"` |
| `ring_config.width` / `height` | Yes | int | > 0 |
| `ring_config.placement_order` | Yes | string | `"clockwise"` or `"counterclockwise"` |
| `instances[].name` | Yes | string | Signal name (preserve `<>` bus notation) |
| `instances[].position` | Yes | string | `{side}_{idx}` for outer pads; `{side}_{idx1}_{idx2}` (idx1<idx2) for inner pads |
| `instances[].type` | Yes | string | `"pad"` or `"inner_pad"` only |
| `instances[].device` | Yes | string | Base device name (e.g. `"PDB3AC"`) — **do NOT include `_H_G` or `_V_G` suffix** |
| `instances[].domain` | Yes | string | Domain ID; must exist in `domains{}` |
| `instances[].direction` | Required for `PDDW16SDGZ`/`PRUW08SDGZ` | string | `"input"` or `"output"` |
| `domains[].kind` | Yes | string | `"analog"` or `"digital"` |
| `domains[].vdd_provider` / `vss_provider` | Analog domains | string | Signal name appearing in instances |
| `domains[].low_vdd` / `low_vss` / `high_vdd` / `high_vss` | Digital domains | string | The 4 unique digital provider signal names |
| `global.vss_ground` | Yes | string | Universal VSS label (default `"GIOL"`) |
| `global.ring_esd` | No | string or null | If set, ring-wide ESD signal name (overrides every pad's VSS) |
| `overrides` | No | object | Per-position pin label overrides — see §6.2 |

### 4.2 Hard Rules (engine will reject)

- `device` must NOT include `_H_G` or `_V_G` — the engine adds the suffix from position.
- `direction` is required for `PDDW16SDGZ` and `PRUW08SDGZ`; absent on all other devices.
- Every `instance.domain` must be a key of top-level `domains{}`.
- Inner pad position requires `idx1 < idx2`, and both indices must be valid for that side.
- Do NOT include corner instances (`type: "corner"`). The engine generates the four corners.

### 4.3 Position-Indexed Identity

The same signal name may appear at multiple positions with different roles. The engine processes by position index, never by name. Example: `VSSIB` at `left_2` (provider, `device: "PVSS3AC"`) and `VSSIB` at `left_8` (consumer, `device: "PVSS1AC"`) — both valid; each resolves its own pins from its own device entry.

### 4.4 Constraint Precedence (when filling in semantic intent)

1. Explicit user prompt constraints
2. Draft Editor `device` hints (from Step 2b, if used)
3. `wizard_constraints` (from on-demand wizard, if invoked)
4. Default classification inference (rules in §5 below)

---

## 5. Classification Rules (G1: Signal Classification & Device Selection)

This section provides the rules the AI uses to decide each instance's `device`, `domain`, and `direction` fields in the semantic intent. After classification, the engine handles all pin wiring, suffix application, and corner generation.

### 5.1 Step 1: Signal list and classification (analog vs digital)

- **CRITICAL — User Voltage Domain Assignment is the PRIMARY Classification Criterion**:
  - **FIRST check user's voltage domain assignments** — if a signal appears in ANY user-specified analog voltage domain, it is an ANALOG signal and MUST use analog device types, regardless of its name.
  - **Signal name is SECONDARY** — do NOT classify signals as digital based on name patterns alone.
  - **Digital domain provider count MUST be exactly 4 unique signal names** — if you identify more than 4 different signal names as digital power/ground providers, you have misclassified some signals.
- **CRITICAL — Domain Continuity in Signal Recognition**: When identifying and classifying signals:
  - **Digital signals** must form a contiguous block in the signal list (cannot be split by analog signals).
  - **Analog signals** must form contiguous blocks (voltage domain continuity).
  - **Ring structure continuity applies** (see §1).
- **CRITICAL — Signal Name Context Classification**: If a signal with a digital domain name appears within an analog signal block (surrounded by analog signals) OR is assigned to an analog voltage domain by user, treat it as an analog pad.
- **CRITICAL — Continuity Check Triggers Re-classification**: If digital signals are found to be non-contiguous, re-examine signal recognition — signals appearing in analog voltage domains should be classified as analog signals.

**Digital domain power/ground providers MUST be exactly 4 unique signal names:**
- 1 low-voltage VDD provider signal name (device: `PVDD1DGZ`)
- 1 low-voltage VSS provider signal name (device: `PVSS1DGZ`)
- 1 high-voltage VDD provider signal name (device: `PVDD2POC`)
- 1 high-voltage VSS provider signal name (device: `PVSS2DGZ`)
- **Note**: Each signal name can have multiple instances (pads), but only 4 unique signal names can be digital domain providers.

**If you count more than 4 digital power/ground providers, STOP and re-check:**
- Those extra signals likely belong to analog voltage domains and should use analog device types.

---

### 5.2 Step 2.1: Digital Domain Continuity and Signal Name Context Classification

**CRITICAL — Digital Domain Continuity:**
- **All digital signals must form a contiguous block** in the signal list/placement order.
- Digital signals (digital IO and digital power/ground) must be identified and grouped together as a continuous block, cannot be split by analog signals.
- **Ring structure continuity applies** (see §1).
- This ensures proper power supply and signal routing for the digital domain.
- **CRITICAL — Continuity Check Triggers Re-classification**: If digital signals are found to be non-contiguous after initial classification, you MUST re-examine signal recognition and classification. This indicates that some signals with digital domain names may have been misclassified and should be treated as analog signals instead.

**CRITICAL — Signal Name Context Classification:**
- If a signal with a digital domain name appears within an analog signal block (surrounded by analog signals on both sides in the signal list), **treat it as an analog pad**, not a digital pad.
  - **Digital domain name signals include**: GIOL, VIOL, VIOH, GIOH, DVDD, DVSS, and other digital power/ground signal names.
  - **Reason**: These signals are likely serving as power/ground connections for analog devices (e.g., analog devices' VSS pins connect to digital domain ground signal names like GIOL, DVSS).
  - **Device class**: Use analog power/ground devices (e.g., `PVSS1AC`, `PVDD1AC`) instead of digital devices (e.g., `PVSS1DGZ`, `PVDD1DGZ`).
  - **Classification rule**: Check the surrounding signals — if both adjacent signals in the list are analog, classify the signal as analog.
  - **Examples**:
    - If DVDD or DVSS appears between analog signals, treat them as analog power/ground (PVDD1AC/PVSS1AC).
    - If GIOL appears between analog signals, treat it as analog ground (PVSS1AC).

---

### 5.3 Step 2.2: Digital Domain Power/Ground assignment

The four digital provider devices are mapped to user signals as follows:

| Provider role | Device | What the AI emits in semantic intent |
|---|---|---|
| Low-voltage digital power | `PVDD1DGZ` | One pad whose `device` is `PVDD1DGZ`; the signal name becomes `domains.<dig_id>.low_vdd` |
| Low-voltage digital ground | `PVSS1DGZ` | One pad whose `device` is `PVSS1DGZ`; signal name becomes `low_vss` |
| High-voltage digital power | `PVDD2POC` | One pad whose `device` is `PVDD2POC`; signal name becomes `high_vdd` |
| High-voltage digital ground | `PVSS2DGZ` | One pad whose `device` is `PVSS2DGZ`; signal name becomes `high_vss` |

**CRITICAL — User-Specified Digital Domain Provider Names**: If user explicitly specifies digital domain provider signal names in requirements (e.g., "Digital signals use digital domain voltage domain (VSS/IOVSS/IOVDDL/IOVDDH)"), MUST use those signal names — write them into the corresponding `domains.<dig_id>` fields and into the `name` of each provider instance. Do NOT use default names (VIOL/GIOL/VIOH/GIOH) when user specifies different names.

**CRITICAL — Exactly One Provider Pair Per Voltage Level**: The digital domain MUST have exactly ONE pair of standard power/ground providers (`PVDD1DGZ`/`PVSS1DGZ`) and exactly ONE pair of high-voltage power/ground providers (`PVDD2POC`/`PVSS2DGZ`).
- **Exactly ONE low-voltage provider pair**: One PVDD1DGZ + one PVSS1DGZ
- **Exactly ONE high-voltage provider pair**: One PVDD2POC + one PVSS2DGZ
- **Total**: digital domain has exactly 2 provider pairs (one low + one high)
- **CRITICAL — Exactly 4 Unique Signal Names**: The digital domain MUST have exactly 4 different signal names identified as digital voltage domain providers (one for each role). Multiple instances of the same signal name are allowed (e.g., multiple GIOL signals all using `PVSS1DGZ`), but only 4 unique signal names can be digital domain providers.

**CRITICAL — Provider Signal Selection Rules**:
- **Selection rule for multiple signals with identical digital domain names**: If multiple signals with the same digital domain provider name appear in the digital signal block, ALL of them within the digital block MUST use the same digital device type (e.g., all "GIOL" pads in the digital block use `PVSS1DGZ`).
- **CRITICAL — Same name in digital block = Same device type**: Within the digital signal block, if multiple signals share the same name and that name is a digital domain provider, they MUST all use the same digital device. Do NOT mix device types (e.g., do NOT use PVSS1AC for one GIOL and PVSS1DGZ for another GIOL if both are in the digital block).
- **Other occurrences handling**: Signals with digital domain provider names that appear OUTSIDE the digital signal block:
  - **If between analog signals**: apply Signal Name Context Classification (§5.2) — treat as analog (PVSS1AC/PVDD1AC).
  - **If within the digital signal block**: same digital device as other instances of the same name.

**CRITICAL — Voltage Domain Assignment Takes Precedence Over Signal Name**: If a signal is assigned to an analog voltage domain by the user, it MUST use analog devices, regardless of its name. Signal names that might suggest digital domain (DVDD, DVSS, etc.) should be classified based on their voltage domain assignment, NOT based on name pattern.

**CRITICAL — Error Detection and Re-classification**: If you find more than one pair of low-voltage providers, more than one pair of high-voltage providers, or the total count of digital power/ground provider signals is not exactly 4, this indicates:
1. **Signal recognition error**: Some signals were incorrectly classified as digital domain providers when they should be:
   - **Analog signals** (if they belong to analog voltage domains): use analog devices, NOT digital.
   - **Digital IO signals** (if they are actual IO signals): use `PDDW16SDGZ`, NOT digital power/ground devices.
2. **Re-classification needed**: Re-examine the signal list and voltage domain assignments. Only 4 signals should be digital domain power/ground providers.

---

### 5.4 Step 2.3: Digital IO Signals — Device and Direction

- **Examples**: SDI, RST, SCK, SLP, SDO, D0–D13, DCLK, SYNC
- **Device selection** (in semantic intent's `device` field):
  - **Default**: `PDDW16SDGZ`
  - **User-specified alternative**: `PRUW08SDGZ` — use ONLY when user explicitly names PRUW08SDGZ. (Engine handles the input-direction REN/OEN difference between PRUW08 and PDDW16 mechanically.)
- **Required field**: `direction` (`"input"` or `"output"`) on every digital IO instance, including inner-ring digital IO pads.

**Direction Judgment Rules:**
- **Common input signals**: SDI (Serial Data In), RST (Reset), SCK (Serial Clock), SLP (Sleep), SYNC (Synchronization), DCLK (Data Clock), control signals.
- **Common output signals**: SDO (Serial Data Out), D0–D13 (Data outputs), status signals.
- **General rule**:
  - Signals with "IN" suffix or "I" prefix typically indicate input.
  - Signals with "OUT" suffix or "O" prefix typically indicate output.
  - Data signals (D0, D1, etc.) are typically outputs unless explicitly specified as inputs.
  - Control signals (RST, SLP, etc.) are typically inputs.
  - Clock signals (SCK, DCLK) are typically inputs.
- **If user explicitly specifies direction**: use it.
- **If ambiguous**: infer from signal name patterns and context; default to `"input"` for control/clock signals, `"output"` for data signals; if still uncertain, invoke wizard (§3).

---

### 5.5 Step 3.1: Voltage Domain Judgment And Signal Assignment

**Universal Voltage Domain Principles (apply to both Priority 1 and Priority 2):**

- **CRITICAL — Use Position Index for Signal Identification**: When processing signals, ALWAYS use position index as the unique identifier, NOT signal name.
  - Same signal name may appear at different positions with different voltage domains.
  - Same signal name may have different roles (provider vs consumer) at different positions.
- **CRITICAL — Every Signal Must Belong to a Voltage Domain** (analog IO, analog power/ground, and analog ESD).
- **CRITICAL — Voltage Domain Continuity**:
  - **Single block**: Voltage domain signals should ideally form a contiguous block.
  - **Multiple blocks allowed**: If a voltage domain has multiple non-contiguous blocks, this is acceptable ONLY IF each block has its own complete provider pair (one VDD provider + one VSS provider within that block).
  - **Ring structure continuity applies** (see §1).
- **CRITICAL — Provider Pair Per Block**: Each contiguous block of a voltage domain MUST have its own provider pair (one VDD provider and one VSS provider within that block).
  - **Provider device choice**: `PVDD3AC`/`PVSS3AC` (default) or `PVDD3A`/`PVSS3A` (only if user explicitly specifies).
  - **Selection rule for multiple signals with identical names** within the same domain:
    - **Default — Same name in same domain uses same device**: If multiple signals in the same domain share the same name, ALL instances MUST use the same device. When that name is the domain's chosen provider name, ALL of those instances use the provider device (`PVDD3A`/`PVSS3A` or `PVDD3AC`/`PVSS3AC`); do NOT convert some instances to consumer devices, and do NOT restrict the domain to only one pair of provider devices. Example: in the same analog domain with two `VDDH` signals and the user requesting `PVDD3A`, BOTH must be assigned `PVDD3A` — do NOT convert one to `PVDD1A`.
    - **Different voltage domains, identical signal names**: Each domain identifies its provider independently within its own specific range.
    - **User override**: If user explicitly requires multiple identical-name signals to all be providers, follow user spec.
  - **Each voltage domain** must have its own provider pair — cannot share providers across domains.

- **Consumer device class** (analog power/ground signals NOT selected as providers):
  - **Default (empirical) pairing**: `PVDD3AC`/`PVSS3AC` providers → `PVDD1AC`/`PVSS1AC` consumers; `PVDD3A`/`PVSS3A` providers → `PVDD1A`/`PVSS1A` consumers.
  - **User override allowed**: The 1AC↔3AC / 1A↔3A pairing is an empirical default, NOT a hard constraint. If the user explicitly requests a different combination within a domain (e.g., `PVDD3A` provider with `PVDD1AC` consumer, or any other mix), follow the user's spec exactly.

- **CRITICAL — Provider vs Consumer Distinction**:
  - **Provider**: ONLY signals selected as the voltage domain's VDD or VSS provider → use `PVDD3AC`/`PVSS3AC` (or `3A` variants).
  - **Consumer**: ALL other power/ground signals in that domain (even if their name contains VDD/VSS) → use the matching consumer family.
  - **Key point**: If domain providers are AVSS1/VREFP1, then ONLY AVSS1 and VREFP1 are providers. Any other power/ground signal (like AVDDH1) in this domain MUST use the matching consumer device, NOT provider device.

**Priority 1: User Explicit Specification (MUST strictly follow)**

- If user explicitly specifies a voltage domain, MUST follow the spec exactly.
- **Provider selection**:
  - If user explicitly names provider signals → use those signals as providers.
  - If user requires multiple identical-name signals to all be providers → all become providers (PVDD3AC/PVSS3AC or PVDD3A/PVSS3A).
  - If user does NOT specify which signals are providers (only domain membership) → first occurrence within that voltage domain's range in placement order is provider; others are consumers.
  - **CRITICAL — Provider Signals Must Use Power/Ground Device Class**: When a signal is explicitly specified as a voltage domain VDD or VSS provider, it MUST use the corresponding power/ground device (`PVDD3AC`/`PVSS3AC` or `PVDD3A`/`PVSS3A`), NOT an IO device (`PDB3AC`), even if the signal name suggests it might be an IO signal (e.g., VREFP1, VREFN1). Provider role takes precedence over name-based classification.
  - **CRITICAL — Handling Identical Signal Names Across Different Voltage Domains**: When the same signal name (e.g., "AVSS1") appears in multiple voltage domains, identify the provider within each domain's specific range, not the global first occurrence.
  - **CRITICAL — Device Assignment by Position**: Assign device class based on signal position (index), NOT name alone. Each instance at a specific position has its own device assignment, even if multiple instances share the same name. Example: if VSSIB appears at index 27 (provider, `PVSS3AC`) and index 30 (consumer, `PVSS1AC`) in the same voltage domain, assign `PVSS3AC` to index 27 and `PVSS1AC` to index 30.

- **Device choice for providers**:
  - **If user explicitly specifies `PVDD3A`/`PVSS3A`**: Use `PVDD3A`/`PVSS3A` for this domain's provider pair.
  - **Otherwise**: Use `PVDD3AC`/`PVSS3AC`.

**Priority 2: Automatic Analysis (when user does NOT specify)**

- **Default behavior**: All analog signals belong to ONE voltage domain.
- **Ensure continuity**: All analog signals must form a contiguous block in placement order. Ring structure continuity applies.
- **Voltage domain analysis process**:
  1. **Select ONE VDD signal as VDD provider**:
     - Identify all analog power signals (VDD, AVDD, VDDIB, VDDSAR, etc.).
     - Select first occurrence in placement order as VDD provider.
     - **Device choice**: `PVDD3AC` (default), or `PVDD3A` if user explicitly specifies in general requirements.
  2. **Select ONE VSS signal as VSS provider**:
     - Identify the corresponding ground signal of the selected VDD provider (e.g., VSSIB if VDDIB chosen).
     - If no corresponding ground exists, first occurrence of any analog ground signal in placement order.
     - **Device choice**: `PVSS3AC` (default), or `PVSS3A` if user explicitly specifies.
  3. **Assign all other analog signals to the same voltage domain**:
     - **Analog IO signals**: device `PDB3AC`, all reference the selected provider pair via their `domain` field.
     - **Analog power/ground signals (consumers)**: device `PVDD1AC`/`PVSS1AC` (or `PVDD1A`/`PVSS1A` if domain providers are 3A variants).

**Example:**
- Signal list: `VREFN VREFM VREFH VSSSAR VDDSAR VDDCLK VSSCLK VCM VDD_DAT GND_DAT`
- User prompt: "from VSSSAR to GND_DAT use VDD_DAT and GND_DAT as voltage domain"
- Resulting analog domain (providers: `GND_DAT`, `VDD_DAT`): `VSSSAR VDDSAR VDDCLK VSSCLK VCM GND_DAT VDD_DAT`

---

### 5.6 Step 3.2: Analog Power/Ground Device Class Selection (semantic only)

After deciding which signal is the provider for each domain, choose the device class per instance:

- **Provider** (selected as voltage domain VDD or VSS provider):
  - **If user explicitly specifies `PVDD3A`/`PVSS3A`**: Use `PVDD3A`/`PVSS3A`.
  - **Otherwise**: Use `PVDD3AC`/`PVSS3AC`.
  - **CRITICAL**: Each voltage domain MUST have exactly one VDD provider name and one VSS provider name (one provider name pair). Multiple instances sharing the chosen provider name all use the same provider device — do NOT downgrade some to consumer devices (see §5.5 same-name rule).
  - **Multiple provider instances with identical names allowed**: All instances in the same domain sharing the chosen provider name become provider-device instances. Example: two `VDDH` in one analog domain with user-requested `PVDD3A` → both use `PVDD3A`, NOT one `PVDD3A` + one `PVDD1A`.

- **Consumer** (other analog power/ground signals in the same domain):
  - **Default (empirical) pairing**: under a `PVDD3AC`/`PVSS3AC` provider pair → `PVDD1AC`/`PVSS1AC`; under a `PVDD3A`/`PVSS3A` provider pair → `PVDD1A`/`PVSS1A`.
  - **User override allowed**: 1AC↔3AC / 1A↔3A matching is an empirical default, not a hard rule. If the user explicitly requests a mixed combination within a domain (e.g., `PVDD3A` provider with `PVDD1AC` consumer, or any other mix), follow the user's spec.

(Pin connections — including the `_CORE` suffix on provider AVDD/AVSS pins, and which pin connects to which domain provider — are handled by the engine. Just pick the right `device` and the engine wires it correctly.)

---

### 5.7 Step 3.3: Analog IO Device Class (semantic only)

- **Examples**: VCM, CLKP, CLKN, IB12, VREFM, VREFDES, VINCM, VINP, VINN, VREF_CORE
- **Device** (in semantic intent's `device` field): `PDB3AC`
- **Domain**: assign to the analog voltage domain containing this signal (per §5.5).

(Engine wires AIO=self, TACVSS=domain VSS provider, TACVDD=domain VDD provider, VSS=global vss_ground. AI does not need to specify pins.)

---

### 5.8 Step 4: Ring ESD Handling (Optional, User-Triggered)

**Trigger**: User explicitly declares a whole-Ring ESD signal (e.g., "use VSS as the whole Ring ESD", "ring-wide ESD = <name>"). If user does NOT declare a Ring ESD, skip this section and leave `global.ring_esd: null`.

**Device class by domain** (the ESD signal name may appear multiple times; classify each instance by the domain of its position):
- **In the digital signal block**: device `PVSS1DGZ` (treat the ESD signal as the digital low-voltage VSS provider).
- **In any analog voltage domain**: device `PVSS2A` (analog Ring ESD pad).
- **Same signal name across domains is expected**: e.g., a signal literally named `VSS` may appear both inside the digital block and inside one or more analog voltage domains. Device class is chosen per-instance by domain, NOT by signal name.

**Set `global.ring_esd` to the ESD signal name in semantic intent.** The engine will:
1. Wire PVSS2A's VSS pin to its own name (the ESD name) — already encoded in the wiring table.
2. Override every other pad's VSS pin in the entire ring to point to the ESD signal name.

(Both behaviors are mechanical and handled by the engine. The AI's only job is correct device classification per domain plus setting `global.ring_esd`.)

---

## 6. Engine Interaction

### 6.1 Invocation

The engine consumes `io_ring_semantic_intent.json` (AI output) and produces `io_ring_intent_graph.json` (full pin-wired output). Gate check results (G1-G10) and ESD override info are printed to console.

```bash
$AMS_PYTHON $SCRIPTS_PATH/enrich_intent.py \
  {output_dir}/io_ring_semantic_intent.json \
  {output_dir}/io_ring_intent_graph.json \
  T28
```

Exit codes:
- `0` — success
- `1` — semantic intent input error (engine stderr includes hint + section pointer)
- `2` — wiring table or engine bug (stop and report)
- `3` — gate failure (engine stderr identifies the gate and suggests re-classification)

### 6.2 Override Syntax

For unusual cases where the AI needs to bypass the engine's standard wiring (e.g., novel PDK device, special-net requirement), use the `overrides` field in semantic intent:

```json
"overrides": {
  "left_3": {
    "pin_overrides": {
      "VSS": "SPECIAL_VSS_BUS"
    }
  },
  "top_5": {
    "pin_overrides": {
      "VDDPST": "label_from:domain.high_vdd"
    }
  }
}
```

| Form | Behavior |
|------|----------|
| Plain string (e.g. `"SPECIAL_VSS_BUS"`) | Used as literal label, no resolution |
| `"label_from:<ref>"` prefix | Resolved through the standard `label_from` machinery (e.g. `domain.vss_provider`, `global.vss_ground`, `self_core`) |

Use overrides sparingly — they are an escape hatch, not a default tool. If you find yourself overriding the same pin on the same device class repeatedly, the wiring table likely needs updating.

### 6.3 Common Engine Errors

| Error class | Typical cause | Fix |
|-------------|---------------|-----|
| `[ENGINE-INPUT]` device suffix included | AI wrote `"device": "PDB3AC_H_G"` | Remove suffix; engine adds it from position |
| `[ENGINE-INPUT]` domain reference not found | Instance references a domain ID not in `domains{}` | Add the domain to `domains{}` or fix the ID |
| `[ENGINE-INPUT]` digital IO missing direction | `device` is `PDDW16SDGZ` or `PRUW08SDGZ` but no `direction` field | Add `"direction": "input"` or `"output"` |
| `[ENGINE-GATE] G3` provider count != 4 | More than 4 unique digital provider names | Re-classify suspect signals as analog (§5.1, §5.3) |
| `[ENGINE-GATE] G4` VSS inconsistency | Pads have different VSS labels | Should not happen with correct semantic intent — may be an engine bug |
| `[ENGINE-GATE] G8` domain continuity warning | An analog domain has multiple non-contiguous blocks | Verify each block has its own provider pair, or re-classify |
| `[ENGINE-GATE] G9` provider not found or wrong device | Domain provider name missing from instances, or uses non-provider device | Add instance with provider name + correct device (§5.5, §5.6) |
| `[ENGINE-GATE] G10` family pairing warning | AC provider with A consumer (or vice versa) in same domain | Non-blocking warning. Default pairing is 1AC↔3AC, 1A↔3A. If the mix is user-specified, ignore the warning; otherwise change consumer to match provider family (§5.6). |

Each engine error message includes the position, device, hint, and a `See: enrichment_rules_T28.md §X.Y` pointer back to the relevant rule.

---

## 7. AI Self-Check (Run Before Writing semantic_intent.json)

Before emitting `io_ring_semantic_intent.json`, verify every check below. If any fails, fix the classification and re-verify. This catches errors that would cause engine failures (exit 1/3) before you waste a round-trip.

### 7.1 Domain-Instance Consistency

| # | Check | What to verify | Engine gate |
|---|-------|----------------|-------------|
| SC1 | **Provider name exists** | Every `domains.<id>.vdd_provider` / `vss_provider` name appears as an instance `name` in `instances[]` | G9 |
| SC2 | **Provider device is correct** | The instance named as provider in each analog domain uses a provider device (`PVDD3AC`/`PVSS3AC` or `PVDD3A`/`PVSS3A`), NOT a consumer or IO device | G9 |
| SC3 | **Digital provider device matches role** | Instance named as `low_vdd` uses `PVDD1DGZ`; `low_vss` → `PVSS1DGZ`; `high_vdd` → `PVDD2POC`; `high_vss` → `PVSS2DGZ` | G9 |
| SC4 | **Analog domain has both providers** | Each analog domain has both `vdd_provider` and `vss_provider` defined | (engine crash) |

### 7.2 Device-Domain Consistency

| # | Check | What to verify | Engine gate |
|---|-------|----------------|-------------|
| SC5 | **Analog devices in analog domains** | `PDB3AC`, `PVDD*AC`, `PVSS*AC`, `PVDD*A`, `PVSS*A`, `PVSS2A` must have `domain` pointing to an analog domain (`kind: "analog"`) | (engine crash) |
| SC6 | **Digital devices in digital domains** | `PDDW16SDGZ`, `PRUW08SDGZ`, `PVDD1DGZ`, `PVSS1DGZ`, `PVDD2POC`, `PVSS2DGZ` must have `domain` pointing to a digital domain (`kind: "digital"`) | (engine crash) |

### 7.3 Family Consistency

| # | Check | What to verify | Engine gate |
|---|-------|----------------|-------------|
| SC7 | **AC/A pairing default** | By empirical default: `PVDD3AC`/`PVSS3AC` providers → `PVDD1AC`/`PVSS1AC` consumers; `PVDD3A`/`PVSS3A` providers → `PVDD1A`/`PVSS1A` consumers. **User override allowed** — if the user explicitly requests a mixed combination (e.g., `PVDD3A` provider with `PVDD1AC` consumer), follow user spec. | G10 |

### 7.4 Completeness

| # | Check | What to verify | Engine gate |
|---|-------|----------------|-------------|
| SC8 | **Digital provider count = 4** | Count unique signal names across `low_vdd`, `low_vss`, `high_vdd`, `high_vss` in all digital domains. Must be exactly 4. | G3 |
| SC9 | **Digital IO has direction** | Every instance with `device: PDDW16SDGZ` or `PRUW08SDGZ` has `"direction": "input"` or `"output"`. No other device has `direction`. | G6 |
| SC10 | **No suffix on device names** | No `device` field contains `_H_G` or `_V_G`. | G1 input |
| SC11 | **No corners in instances** | No instance has `type: "corner"`. | G2 input |

### 7.5 How to Run the Self-Check

After drafting the semantic intent JSON in memory, walk through SC1–SC11 before writing the file. The checks are fast (just lookups against your own data). If you catch an error here, you save an engine round-trip and produce correct output faster.

**The engine will still run G1–G10 as a safety net** — the self-check is not a replacement for engine gates, it's a pre-filter that catches the most common mistakes before they reach the engine.

---

## Task Completion Checklist

### Classification (semantic decisions)
- [ ] Every signal belongs to a voltage domain (analog) or digital domain
- [ ] Digital provider count = exactly 4 unique signal names (or no digital domain at all)
- [ ] Digital signals form a contiguous block (with ring wrap)
- [ ] Each analog voltage domain block has its own provider pair
- [ ] Provider/consumer device family matches within domain by empirical default (1AC↔3AC, 1A↔3A) — G10. User override allowed: if user explicitly requests a mixed combination (e.g., 3A provider + 1AC consumer), follow user spec.
- [ ] Provider signals use power/ground devices (PVDD3AC/PVSS3AC or 3A variants), NOT IO devices, even if name suggests IO — G9
- [ ] Digital IO instances have `direction` field set; non-digital-IO instances do not
- [ ] User-specified device hints from Draft Editor and explicit prompt constraints are respected
- [ ] Ring ESD: if user-declared, `global.ring_esd` is set; ESD instances use `PVSS2A` in analog domains and `PVSS1DGZ` in digital blocks

### AI Self-Check (§7 — run before writing semantic_intent.json)
- [ ] SC1–SC4: Domain-instance consistency (provider names exist, correct devices)
- [ ] SC5–SC6: Device-domain kind consistency (analog↔analog, digital↔digital)
- [ ] SC7: No AC/A mixing within any domain
- [ ] SC8–SC11: Completeness checks

### Semantic Intent Output (engine input contract)
- [ ] No corner instances in `instances` (engine generates)
- [ ] No `_H_G`/`_V_G` suffix on `device` names (engine adds)
- [ ] No `pin_connection` field (engine generates)
- [ ] Every `instance.domain` exists as a key in `domains{}`
- [ ] Inner pad positions: `idx1 < idx2`
- [ ] `global.vss_ground` set (default `"GIOL"` if no special override)

### Final Confirmation
- [ ] Engine exits 0 (success, all G1–G10 pass)
- [ ] Engine console output shows no domain-continuity warnings, or warnings are intentional
- [ ] Step 4 `validate_intent.py` exits 0
