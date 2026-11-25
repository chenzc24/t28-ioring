# T28 semantic intent

Work from the signal list, package bond map, supply specification and placement order. Give every position its own identity. Preserve duplicate signal names and explicit assignments through both rows of a staggered ring. An unresolved voltage or domain assignment belongs in the planning report. Ask the designer when existing inputs cannot resolve a decision that changes connectivity.

## Input fields

Partial example showing field shapes. A complete ring also needs the bonded counts and neighbours below.

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
| `domains[].low_vdd` / `low_vss` / `high_vdd` / `high_vss` | Digital domains | string | The four rail roles. Use a common ground with PVSS3DGZ. |
| `global.vss_ground` | Yes | string | Universal VSS label (default `"GIOL"`) |
| `global.ring_esd` | No | string or null | If set, ring-wide ESD signal name (overrides every pad's VSS) |
| `overrides` | No | object | Per-position pin label overrides — see §6.2 |


Record nominal `core_voltage` and `io_voltage` in volts for each domain. On each pad `bonded` defaults to true for historical fully bonded plans. Mark dummy cells false and reconcile the planned count with the package drawing. The generator uses a voltage specification for planning; actual library voltage ranges come from the applicable release.

## Select the cells

- Digital domains can occur at different operating voltages. Use the four supply roles for each domain. Count at least three bonded PVDD1DGZ and two PVDD2DGZ/PVDD2POC combined. Provide at least one bonded ground for each rail. PVSS3DGZ supplies both grounds when they are the same net.
- Each domain with functional digital IO uses one PVDD2POC. Assign the remaining high supplies PVDD2DGZ. For a supply-only domain set `poc_grounded: true` and provide a physical ground connection at integration. The POC source exposes one cell-level monitor terminal to match the layout rail text. It has no bond pad. Leave it unloaded in the testbench unless the measurement plan specifies a probe.
- Choose PDDW16SDGZ or PRUW08SDGZ from the requested input behaviour, drive, slew and SSO budget. Set `direction` on every functional digital pad. Supply the tabulated `drive_factor` on each bidirectional pad, including a pad configured as an input. Record `sso_source`, `package_inductance_nh` and `load_pf` on the domain. A missing table value leaves SSO pending.
- Ordinary analog rail pads share the electrical domain’s supply names. Use PVDD3AC/PVSS3AC for core voltage and PVDD3A/PVSS3A for IO voltage. Minimum bonded counts are 3/1 and 2/1 respectively. Never connect differently named supplies by assigning them to the same abutted bus. Resolve ambiguous DVDD, DVSS or GIOL from the schematic or explicit domain map.
- Dedicated analog macro supplies use matched PVDD1AC/PVSS1AC or PVDD1A/PVSS1A. Record the macro and actual package pin on each dedicated pad. Each dedicated positive supply needs three bonded cells on one package pin for AC, two for A. Verify the corresponding ground, clamp and core-side capacitance. The numerical minimum in §10.6 applies to the positive supply.
- For each PDB3AC identify a bonded global VSS source in the same analog domain or in an adjacent digital domain. Add PVSS2AC when required to meet resistance. Select PVSS2A for the IO-voltage equivalent. The optional global `ring_esd` field names the VSS net. Its presence does not determine whether cells are necessary.

## Plan the perimeter

Place bonded grounds immediately on both sides of every corner. Use PVSS3A/AC at analog corners and PVSS2DGZ/3DGZ at digital corners. Locate domain boundaries on a side. PRCUTA_G requires an adjacent analog 3A/3AC power or ground cell. PRCUT_G separates digital domains and needs a bonded PVSS1DGZ/3DGZ within two cell widths on each side. Budget the 20 µm separator when placing inner pads. The layout check uses the final ordered cells and their physical widths. If a fixed side order cannot meet a rule, report the failing positions before proposing a new order.

Use the same_domain_bus rows to identify the longest uncut path for each bonded master pair in a domain. Match the pair and circuit topology to Tables 8.1 and 10.1 and check the extracted resistance. Planning distances include both corner legs. Set ring_config.bus_ohm_per_um to a mapping from domain ID to a calibrated conservative resistance per micron to flag estimates above the tabulated limits for supported master pairs. A null limit requires a release-specific review. Check the Table 10.1 circuit-between-pads exception during extraction. An optional `ring_config.vss_ohm_per_um` yields a uniform-resistance planning estimate for PDB3AC. Supply the coefficient from this library and stack. The `rule_review.vss_bus` rows identify the positions to measure after extraction. The global bus requirement in checklist 23y.3 is below 1 Ω.

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


## Chip integration evidence

Use the local *TSMC N28 General I/O Library Application Note* v1.4 and the installed IO and CUP library release notes. Cite the release and section in the design report.

| Item | Evidence to attach |
|---|---|
| Bonding and empty slots (§6.1, 8.3, 10.3) | Package pin map and verified analog/digital CUP master. Consider unbonded dummy supply cells where gaps exceed a cell width, with their standby leakage. |
| ESD (§8.4–8.7, 10.4–10.7, 16) | Extracted rail resistances, ≥20 pF core-side analog decoupling, core-voltage PCLAMPC and connections. Use the variant and orientation that leave gate poly vertical. |
| Power sequencing (§3, 9.3) | Measured supply ramp above 10 µs and domain sequencing. Check VDDPST before VDD preference and PVDD2ANA ordering where applicable. |
| Analog input (§9.2, 23y) | Core device connection, secondary protection and swing from −0.3 V through nominal TACVDD + 0.3 V. |
| Partial perimeter (§6.4, 8.11, 9.8.4, 10.11) | Current generator handles four-sided closed rings. L/U-shaped structures require endcaps, guard-band closure and verified IP interfaces. |
| Full-chip verification | Release-matched full-chip deck, unselected checks, LVS virtual connections, individual ERC markers and foundry basis for each disposition. Cell deck exclusions are laboratory settings. |
