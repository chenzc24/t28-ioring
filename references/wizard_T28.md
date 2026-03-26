# IO Ring Wizard - T28 Reference

This file defines the question and answer contract for the on-demand wizard used by the T28 flow.

The wizard is NOT a standalone step. It is invoked only when Step 2 (draft build) or Step 3 (enrichment) decides that ambiguity must be resolved.

Rule ownership note:
- This file does not define classification, device mapping, pin mapping, or direction inference rules.
- Those rules are owned by `enrichment_rules_T28.md`.
- This file defines only what to ask and what to write back.

---

## Scope

Wizard responsibilities:
1. Ask focused clarification questions for ambiguity cases raised by Step 2/3.
2. Return structured constraints in a stable schema.
3. Provide W5 final confirmation before generation proceeds.

Wizard non-responsibilities:
1. Do not decide when wizard should be called.
2. Do not run full auto-classification logic.
3. Do not redefine device/pin/direction rules already in enrichment.

---

## Invocation Contract

Caller (Step 2/3) must provide:
- `reason`: short ambiguity reason
- `context`: minimal affected signals/positions/domains
- `current_proposal`: what the flow currently infers

Wizard returns:
- `wizard_constraints` with only the fields required by the specific ambiguity
- `confirmation` status from W5

---

## Question Modules

Use one or more modules depending on ambiguity type.

### Module G - Geometry Clarification (Step 2 only)

Use when draft builder cannot uniquely resolve geometry.

Questions:
1. Placement order
2. Starting side (signal list index 0 side)
3. Dimensions (`width` and `height`)

Example prompts:
- "Ring traversal direction?"
- "Which side is first in your signal list?"
- "Confirm side counts: top=X right=Y bottom=X left=Y"

Output fields:
- `geometry.placement_order`
- `geometry.starting_side`
- `geometry.width`
- `geometry.height`

### Module S - Signal Type Override

Use when Step 3 cannot uniquely decide signal type for specific signals.

Question pattern (one signal per question):
- "{signal_name} at {position} should be treated as?"

Allowed answer classes:
- `analog_io`
- `analog_power_provider`
- `analog_ground_provider`
- `analog_power_consumer`
- `analog_ground_consumer`
- `digital_io`
- `digital_power_low`
- `digital_ground_low`
- `digital_power_high`
- `digital_ground_high`

Output field:
- `manual_overrides.signal_types[{position_key}]`

### Module D - Voltage Domain Boundary Override

Use when domain boundary assignment is ambiguous.

Question patterns:
- "Signal {name}@{position} belongs to which analog domain?"
- "Confirm domain range for {domain_id}: from {start} to {end}?"

Output field:
- `manual_overrides.voltage_domains[]`

Each entry format:
- `domain_id`
- `vdd_provider`
- `vss_provider`
- `range_from`
- `range_to`

### Module P - Digital Provider Mapping Override

Use when digital provider names are not explicit or conflicts remain.

Question pattern:
- "Confirm digital provider mapping (low_vdd/low_vss/high_vdd/high_vss)."

Output field:
- `digital_providers.low_vdd`
- `digital_providers.low_vss`
- `digital_providers.high_vdd`
- `digital_providers.high_vss`

### Module R - Direction Override

Use when direction cannot be inferred with high confidence.

Question pattern:
- "Direction for {signal_name} at {position}: input or output?"

Output field:
- `manual_overrides.directions[{position_key}]`

### Module W5 - Final Confirmation (Required)

W5 is kept as a mandatory final confirmation entry.

Before asking, print a concise plan summary:
- geometry
- resolved overrides
- inferred digital provider mapping
- affected signals list

Confirmation question:
- "Plan ready. Proceed to generate?"

Recommended options:
- Generate now
- Fix one item
- Cancel

Output field:
- `confirmation.action`

---

## Constraint Output Schema

Only include fields that were actually asked.

```json
{
  "geometry": {
    "placement_order": "clockwise|counterclockwise",
    "starting_side": "top|right|bottom|left",
    "width": 12,
    "height": 12
  },
  "wizard_constraints": {
    "manual_overrides": {
      "signal_types": {
        "left_3": "analog_ground_consumer"
      },
      "voltage_domains": [
        {
          "domain_id": "ana_domain_1",
          "vdd_provider": "AVDD",
          "vss_provider": "AVSS",
          "range_from": "left_2",
          "range_to": "bottom_4"
        }
      ],
      "directions": {
        "top_5": "input"
      }
    },
    "digital_providers": {
      "low_vdd": "IOVDDL",
      "low_vss": "GIOL",
      "high_vdd": "IOVDDH",
      "high_vss": "GIOH"
    }
  },
  "confirmation": {
    "action": "generate|fix|cancel"
  }
}
```

Notes:
- Keys for overrides must be position-based.
- Never use name-only keys when writing overrides.

---

## AskUserQuestion Usage Rules

1. Print current state in plain text before each question batch.
2. Ask only about ambiguous items provided by Step 2/3.
3. Keep one question to one decision.
4. Use "Other" for free-text overrides when needed.
5. Do not ask for decisions unrelated to current ambiguity scope.

---

## Minimal Checklist

- Asked only the ambiguity items provided by caller
- Returned only required override fields
- Preserved position-based identity for duplicated signal names
- Completed W5 final confirmation
