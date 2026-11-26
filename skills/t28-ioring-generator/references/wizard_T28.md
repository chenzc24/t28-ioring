# IO Ring Wizard - T28 Reference

Use these optional prompts for an unresolved geometry, domain, rail or direction decision that would change the requested placement or connectivity. Apply [the classification guidance](enrichment_rules_T28.md#classify-signals-and-assign-domains) to the information already available and continue the parts of the draft that can be resolved.

---

## Use the answers

State the affected signals, positions or domains, the current proposal, and the specific choice to resolve. Include only answered fields in your working notes. Copy geometry answers into the draft and the device, direction and rail answers into the semantic plan. Keep undecided items in the handoff and proceed with the requested generation when the plan is ready.

---

## Question Modules

Use one or more modules depending on ambiguity type.

### Clarify geometry

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
- `analog_power_consumer` for a dedicated macro supply
- `analog_ground_consumer` for a dedicated macro ground
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
  }
}
```

Notes:
- Keys for overrides must be position-based.
- Never use name-only keys when writing overrides.

---

## Focused questions

1. Print current state in plain text before each question batch.
2. Keep one question to the unresolved decision.
3. Accept the user's terms and explicit overrides.

---

## Minimal Checklist

- Applied the supplied answers to the plan.
- Preserved position-based identity for duplicated signal names.
