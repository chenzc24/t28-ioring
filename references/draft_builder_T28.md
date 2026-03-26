# Draft Builder - T28 (Phase 1)

## Purpose

Build a stable draft intent JSON from user-provided structural inputs only.
This phase MUST avoid device/pin/corner inference and produce a deterministic handoff file for Phase 2.

## Scope and Boundaries

### Allowed in Phase 1

- Parse user signal list and ring dimensions
- Compute `ring_config`
- Assign `position` for outer pads
- Assign `position` for inner pads
- Set `type` as `pad` or `inner_pad`
- Preserve signal order and duplicates

### Forbidden in Phase 1

- No `device` field
- No `pin_connection` field
- No `direction` field
- No corner insertion
- No voltage-domain classification

## Input Contract

Required inputs:

- signal list
- `width` (top/bottom pad count)
- `height` (left/right pad count)
- `placement_order` (`clockwise` or `counterclockwise`; default `counterclockwise` if user does not specify)
- optional inner-pad insertion descriptions

Optional on-demand wizard inputs (when Step 2 requests clarification):

- `geometry.placement_order`
- `geometry.starting_side`
- `geometry.width`
- `geometry.height`

Input precedence for draft build:

1. Explicit user structural input
2. On-demand wizard `geometry` fields
3. Draft default fallback (`placement_order = counterclockwise` only when still unspecified)

## Output Contract (Draft JSON)

```json
{
  "ring_config": {
    "width": 12,
    "height": 12,
    "placement_order": "counterclockwise"
  },
  "instances": [
    {
      "name": "RST",
      "position": "left_0",
      "type": "pad"
    },
    {
      "name": "D15",
      "position": "top_2_3",
      "type": "inner_pad"
    }
  ]
}
```

## Position Rules

### Outer Pad Position Format

- `{side}_{index}`
- examples: `left_3`, `top_0`, `right_11`

### Inner Pad Position Format

- `{side}_{index1}_{index2}`
- example: `left_8_9`
- must satisfy `index1 < index2`
- both indices must refer to distinct adjacent outer-pad positions on the same side
- index pairs are computed from outer pads only; previously inserted inner pads must not change outer indices

When user says inner pad is between signal A and B, resolve by actual pad positions, not name lookup.
The same name may appear multiple times.

## Duplicate Signal Rule

When duplicate signals (same signal name appearing multiple times) are encountered:
- DO NOT delete or remove duplicates
- Preserve all instances of duplicate signals exactly as provided
- Each duplicate occurrence is a valid, separate signal instance
- The draft must contain the exact same number of signal instances as the input signal list

## Inner-Pad Insertion Resolution Rules

### Position-First Resolution

Use position-indexed outer-pad sequence as the only identity source.
Do not resolve a between clause by global-first-name search.

### Repeated Name Disambiguation

For each insertion request `insert inner X between A and B`:

- find all adjacent outer-pad pairs on the same side where names match `(A, B)` in order
- if no pair exists, the request is unresolved and must be reported as hard error
- choose the first unmatched pair in ring traversal order
- once selected, that pair is reserved for this request and cannot be reused by another request

### Same-Endpoint Rule (A equals B)

If request is `between A and A`, match only adjacent outer-pad pair where both endpoints are `A`.
Use the first unmatched adjacent `(A, A)` pair in ring traversal order.

### Duplicate Inner-Name Rule

Inner pad names may repeat across multiple requests.
Each request is resolved independently by endpoint pair identity, not by inner name uniqueness.

### Name Integrity Rule

Inner pad instance name must exactly equal the user-requested inner pad token.
Do not normalize, auto-correct, alias, expand, or rewrite names (for example `VREFN3` must not become `VREFNF3`).

### Endpoint Back-Check Rule (Hard Gate)

After resolving inner pad position `side_i_j`, perform endpoint back-check against outer pads:

- outer `side_i` name must equal requested endpoint A
- outer `side_j` name must equal requested endpoint B
- if either endpoint does not match, treat as hard inconsistency and stop

Do not keep a partially shifted result.
Do not auto-adjust to `side_{i+1}_{j+1}` or any guessed index pair.

## Signal-to-Position Mapping

### Starting-Side Rotation Rule

Base traversal order is defined by `placement_order`:

- clockwise base: `[top, right, bottom, left]`
- counterclockwise base: `[left, bottom, right, top]`

If `starting_side` is provided (from explicit user input or wizard geometry), rotate the base traversal so index 0 starts at `starting_side`, while preserving traversal direction.

Examples:

- clockwise + `starting_side=right` -> `[right, bottom, left, top]`
- counterclockwise + `starting_side=top` -> `[top, left, bottom, right]`

Chunk sizes follow side type after rotation:

- top/bottom chunks use `width`
- left/right chunks use `height`

If `starting_side` is absent, use base traversal order directly.

### Clockwise

Signal list mapping:

- `[top_0..top_{w-1}]`
- `[right_0..right_{h-1}]`
- `[bottom_0..bottom_{w-1}]`
- `[left_0..left_{h-1}]`

Example (w=3, h=3):

- signal list: `VCM IBAMP IBREF AVDD AVSS VIN VIP VAMP IBAMP IBREF VDDIB VSSIB`
- top (3): `VCM, IBAMP, IBREF` -> `top_0, top_1, top_2`
- right (3): `AVDD, AVSS, VIN` -> `right_0, right_1, right_2`
- bottom (3): `VIP, VAMP, IBAMP` -> `bottom_0, bottom_1, bottom_2`
- left (3): `IBREF, VDDIB, VSSIB` -> `left_0, left_1, left_2`

### Counterclockwise

Signal list mapping:

- `[left_0..left_{h-1}]`
- `[bottom_0..bottom_{w-1}]`
- `[right_0..right_{h-1}]`
- `[top_0..top_{w-1}]`

Example (w=3, h=3):

- signal list: `VCM IBAMP IBREF AVDD AVSS VIN VIP VAMP IBAMP IBREF VDDIB VSSIB`
- left (3): `VCM, IBAMP, IBREF` -> `left_0, left_1, left_2`
- bottom (3): `AVDD, AVSS, VIN` -> `bottom_0, bottom_1, bottom_2`
- right (3): `VIP, VAMP, IBAMP` -> `right_0, right_1, right_2`
- top (3): `IBREF, VDDIB, VSSIB` -> `top_0, top_1, top_2`

## Position-Indexed Identity Rule

Use position index as the unique identity during this phase.
Do not use global name lookup for repeated names.

## Draft Validation Checklist

- `ring_config.width` and `ring_config.height` exist and are valid
- `placement_order` is valid (`clockwise` or `counterclockwise`)
- if `starting_side` exists, it is one of `top/right/bottom/left` and mapping uses rotated traversal
- every instance has `name`, `position`, `type`
- `type` is only `pad` or `inner_pad`
- no `corner` instances exist in draft
- no `device`/`pin_connection`/`direction` fields exist
- inner-pad indices are valid and adjacent
- position uniqueness is maintained for physical placement
- every inner-pad insertion request is materialized exactly once
- no insertion request is silently dropped
- no two insertion requests reuse the same outer-pad gap
- each generated inner-pad `name` exactly matches the requested token

## Request-to-Result Consistency Rules

- Build an ordered insertion-request list from user input text.
- Build an ordered generated-inner-pad list from draft JSON.
- Validate cardinality equality between these two lists.
- Validate per-request mapping record: `requested_name`, `endpoint_pair`, `resolved_position`.
- For each mapping record, back-check `resolved_position` to outer endpoints and verify exact `(A, B)` match.
- If any request cannot be resolved uniquely, stop and return hard inconsistency instead of partial draft.

## Handoff Invariants to Phase 2

Phase 2 MUST treat the following fields as immutable unless reporting hard input inconsistency:

- `ring_config.width`
- `ring_config.height`
- `ring_config.placement_order`
- `instances[].name`
- `instances[].position`
- `instances[].type`

## Operational Checklists (Phase 1 Gate)

### Preflight Checklist

- confirm `width` and `height` are positive integers
- confirm `placement_order` is `clockwise` or `counterclockwise`
- if provided, confirm `starting_side` is `top/right/bottom/left`
- parse outer signal list first and verify outer count equals `2 * width + 2 * height`
- parse inner-pad insertion requests into ordered tuples: `(inner_name, endpoint_a, endpoint_b)`
- reject malformed insertion statements instead of guessing

### Build-Time Checklist

- build outer-pad position map strictly from configured placement order
- verify outer-side counts before inserting inner pads:
  - left count = `height`
  - right count = `height`
  - top count = `width`
  - bottom count = `width`
- resolve each insertion request using adjacent outer-pad pairs only
- reserve matched outer-pad gap immediately to prevent gap reuse
- enforce `index1 < index2` for generated inner-pad positions
- enforce same-side adjacency for every inner-pad position
- preserve exact requested inner-pad name token without rewriting
- back-check every resolved `side_i_j` against requested endpoint names `(A, B)`

### Post-Build Checklist

- draft has only allowed fields for Phase 1 (`name`, `position`, `type` plus `ring_config`)
- no `device`, `pin_connection`, `direction`, or `corner` in draft
- all positions are unique physical locations (no duplicate `position` among instances)
- every insertion request appears exactly once in generated `inner_pad` instances
- generated inner-pad count equals insertion request count
- no unresolved request remains; if unresolved, return hard inconsistency
- outer-side counts still satisfy: left/right = `height`, top/bottom = `width`
- every generated inner-pad position still maps to its requested endpoint pair after full build

### Failure Reporting Checklist

- include failing request tuple and reason (`not found`, `ambiguous`, `reused gap`, `invalid adjacency`)
- include endpoint back-check mismatch details when applicable:
  - `requested_pair=(A,B)`, `resolved_position=side_i_j`, `actual_pair=(A2,B2)`
- include nearest candidate positions for debugging when available
- stop output on hard inconsistency (do not emit partial-success draft)
