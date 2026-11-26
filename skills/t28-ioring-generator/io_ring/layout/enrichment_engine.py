#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enrichment Engine - T28 IO Ring

Converts AI-produced semantic intent into a full intent graph by mechanically
applying suffix rules, pin wiring, corner generation, and gate checks.

The AI owns semantic decisions (signal class, device choice, domain assignment,
direction, ring ESD). The engine owns mechanical execution (_H_G/_V_G suffix,
pin label resolution, _CORE suffix, corner type from adjacent pads, gate checks,
ring ESD VSS override).

Inputs:
  - semantic_intent.json   (AI output, ~30 lines)
  - device_wiring_T28.json (data file, ~250 lines)

Outputs:
  - intent_graph.json      (full pin-wired output, ~200 lines, golden-compatible)
  - console gate summary   (G1-G8 pass/fail + ESD override printed to stdout)

Exit codes (used by scripts/enrich_intent.py CLI):
  0 - success
  1 - semantic intent input error (with hint to fix)
  2 - wiring table error / engine bug
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, OrderedDict
from math import isfinite
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Exceptions — distinguish input errors from engine bugs from gate failures
# ============================================================================


class EngineError(Exception):
    """Base. Subclasses indicate which exit code to use."""

    exit_code = 2

    def __init__(self, summary: str, *, position: str = "", device: str = "",
                 detail: str = "", hint: str = "", section: str = ""):
        self.summary = summary
        self.position = position
        self.device = device
        self.detail = detail
        self.hint = hint
        self.section = section
        super().__init__(self.format_message())

    def format_message(self) -> str:
        prefix = f"[ENGINE-{self.kind}]"
        lines = [f"{prefix} {self.summary}"]
        if self.position or self.device:
            ctx = []
            if self.position:
                ctx.append(f"position={self.position}")
            if self.device:
                ctx.append(f"device={self.device}")
            lines.append(f"  At: {', '.join(ctx)}")
        if self.detail:
            lines.append(f"  Detail: {self.detail}")
        if self.hint:
            lines.append(f"  Hint: {self.hint}")
        if self.section:
            lines.append(f"  See: references/enrichment_rules_T28.md {self.section}")
        return "\n".join(lines)

    @property
    def kind(self) -> str:
        return "ERROR"


class InputError(EngineError):
    """Semantic intent malformed. AI should fix and re-run."""

    exit_code = 1

    @property
    def kind(self) -> str:
        return "INPUT"


class WiringError(EngineError):
    """Wiring table malformed. Engine bug or PDK data error. Stop."""

    exit_code = 2

    @property
    def kind(self) -> str:
        return "WIRING"


# ============================================================================
# Wiring table loader + validator
# ============================================================================


VALID_LABEL_FROM = {
    "self", "self_core",
    "domain.vdd_provider", "domain.vss_provider",
    "domain.low_vdd", "domain.low_vss", "domain.high_vdd", "domain.high_vss",
    "global.vss_ground",
    "const.POC", "const.noConn",
    "io.ren", "io.oen", "io.c", "io.i",
}


def load_wiring_table(path: Path) -> Dict[str, Any]:
    """Load and validate device_wiring_T28.json."""
    if not path.exists():
        raise WiringError(
            f"Wiring table not found: {path}",
            hint="Ensure io_ring/schematic/devices/device_wiring_T28.json exists.",
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise WiringError(f"Wiring table is not valid JSON: {e}")

    if "devices" not in data:
        raise WiringError("Wiring table missing 'devices' section")

    for device, spec in data["devices"].items():
        if not isinstance(spec, dict):
            raise WiringError(f"Device {device}: spec must be a dict")
        if "family" not in spec:
            raise WiringError(f"Device {device}: missing 'family'")
        if "pins" not in spec or not spec["pins"]:
            raise WiringError(f"Device {device}: missing or empty 'pins'")
        for pin_name, pin_spec in spec["pins"].items():
            lf = pin_spec.get("label_from")
            if lf not in VALID_LABEL_FROM:
                raise WiringError(
                    f"Device {device}, pin {pin_name}: unknown label_from='{lf}'",
                    hint=f"Valid values: {sorted(VALID_LABEL_FROM)}",
                )
        # digital_io devices must have io_direction_rules
        if spec["family"] == "digital_io":
            if "io_direction_rules" not in spec:
                raise WiringError(f"Device {device}: digital_io requires io_direction_rules")
            for direction in ("input", "output"):
                if direction not in spec["io_direction_rules"]:
                    raise WiringError(
                        f"Device {device}: io_direction_rules missing '{direction}'"
                    )

    return data


# ============================================================================
# Position parsing + suffix
# ============================================================================


_POS_PAD = re.compile(r"^(left|right|top|bottom)_(\d+)$")
_POS_INNER = re.compile(r"^(left|right|top|bottom)_(\d+)_(\d+)$")
_POS_CORNER = re.compile(r"^(top_left|top_right|bottom_left|bottom_right)$")


def parse_position(pos: str) -> Tuple[str, str, Tuple[int, ...]]:
    """Return (kind, side, indices). kind in {pad, inner_pad, corner}."""
    m = _POS_CORNER.match(pos)
    if m:
        return ("corner", pos, ())
    m = _POS_PAD.match(pos)
    if m:
        return ("pad", m.group(1), (int(m.group(2)),))
    m = _POS_INNER.match(pos)
    if m:
        return ("inner_pad", m.group(1), (int(m.group(2)), int(m.group(3))))
    raise InputError(
        f"Position '{pos}' does not match any known format",
        position=pos,
        hint="Use side_idx (e.g. left_3), side_idx1_idx2 (e.g. top_2_3), or corner names.",
        section="§4.1 (Schema)",
    )


def suffix_for_side(side: str) -> str:
    if side in ("left", "right"):
        return "_H_G"
    if side in ("top", "bottom"):
        return "_V_G"
    raise InputError(f"Unknown side '{side}' for suffix computation")


# ============================================================================
# Label resolution
# ============================================================================


class ResolutionContext:
    """Per-instance resolution context for label_from references."""

    def __init__(self, instance: Dict[str, Any], domains: Dict[str, Any],
                 globals_: Dict[str, Any], device_spec: Dict[str, Any]):
        self.instance = instance
        self.domains = domains
        self.globals = globals_
        self.device_spec = device_spec
        self.name = instance["name"]
        self.position = instance["position"]
        self.domain_id = instance.get("domain")
        self.domain = domains.get(self.domain_id) if self.domain_id else None
        self.direction = instance.get("direction")

    def resolve(self, label_from: str) -> str:
        if label_from == "self":
            return self.name
        if label_from == "self_core":
            return _self_core(self.name)
        if label_from == "global.vss_ground":
            esd = self.globals.get("ring_esd")
            if esd:
                return esd
            return self.globals.get("vss_ground", "GIOL")
        if label_from == "const.POC":
            if self.domain and self.domain.get("poc_grounded") is True:
                return self.resolve("global.vss_ground")
            return f"POC_{self.domain_id}" if self.domain_id else "POC"
        if label_from == "const.noConn":
            return "noConn"
        if label_from.startswith("domain."):
            return self._resolve_domain(label_from)
        if label_from.startswith("io."):
            return self._resolve_io(label_from)
        raise WiringError(f"Cannot resolve label_from '{label_from}'")

    def _resolve_domain(self, ref: str) -> str:
        key = ref.split(".", 1)[1]
        if not self.domain_id:
            raise InputError(
                f"Pin uses '{ref}' but instance has no 'domain' field",
                position=self.position,
                device=self.instance.get("device", ""),
                hint="Add a 'domain' field to this instance in semantic_intent.",
                section="§4.1 (Schema)",
            )
        if self.domain is None:
            raise InputError(
                f"Instance references domain '{self.domain_id}' which is not defined",
                position=self.position,
                device=self.instance.get("device", ""),
                detail=f"available domains: {sorted(self.domains.keys())}",
                hint=f"Add '{self.domain_id}' to top-level 'domains' in semantic_intent, "
                     f"or change this instance's domain to one that exists.",
                section="§4.1 (Schema)",
            )
        if key not in self.domain:
            # Hazard: device class mismatched with domain kind?
            domain_kind = self.domain.get("kind", "unknown")
            ref_kind = "digital" if key in ("low_vdd", "low_vss", "high_vdd", "high_vss") else "analog"
            extra_hint = ""
            if domain_kind != ref_kind:
                extra_hint = (f" (Device expects a {ref_kind} domain but '{self.domain_id}' "
                              f"is kind={domain_kind} — likely device/domain mismatch.)")
            raise InputError(
                f"Domain '{self.domain_id}' has no '{key}'{extra_hint}",
                position=self.position,
                device=self.instance.get("device", ""),
                detail=f"domain definition: {self.domain}",
                hint=f"Either add '{key}' to domains.{self.domain_id}, or change this "
                     f"instance to use a {ref_kind}-kind domain.",
                section="§4.1 (Schema)",
            )
        return self.domain[key]

    def _resolve_io(self, ref: str) -> str:
        if "io_direction_rules" not in self.device_spec:
            raise WiringError(
                f"Pin uses {ref} but device has no io_direction_rules",
                position=self.position,
            )
        if not self.direction:
            raise InputError(
                "Digital IO instance missing 'direction' field",
                position=self.position,
                device=self.instance.get("device", ""),
                hint="Set 'direction' to 'input' or 'output' on this instance.",
                section="§5.4 (Step 2.3 Direction inference)",
            )
        rules = self.device_spec["io_direction_rules"].get(self.direction)
        if not rules:
            raise InputError(
                f"Direction '{self.direction}' not in io_direction_rules",
                position=self.position,
                hint="Direction must be 'input' or 'output'.",
            )
        pin_name = ref.split(".", 1)[1].upper()
        if pin_name not in rules:
            raise WiringError(
                f"io_direction_rules missing pin '{pin_name}'",
                position=self.position,
            )
        return self.resolve(rules[pin_name]["label_from"])


def _self_core(name: str) -> str:
    """Append _CORE preserving angle-bracket bus suffixes (e.g. VDD<0> → VDD_CORE<0>)."""
    m = re.match(r"^(.+?)(<[^>]+>)$", name)
    if m:
        return f"{m.group(1)}_CORE{m.group(2)}"
    return f"{name}_CORE"


# ============================================================================
# Instance expansion
# ============================================================================


def expand_instance(instance: Dict[str, Any], wiring: Dict[str, Any],
                    domains: Dict[str, Any], globals_: Dict[str, Any],
                    overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a semantic instance to a fully-wired output instance."""

    position = instance["position"]
    inst_type = instance.get("type", "pad")
    device_base = instance.get("device", "")

    # Validate device name
    if not device_base:
        raise InputError(
            "Instance missing 'device' field",
            position=position,
            hint="Add a base device name (e.g. 'PDB3AC') to the instance.",
            section="§4.1 (Schema)",
        )
    supplied_device = device_base
    device_base = _strip_suffix(device_base)
    if inst_type in ("corner", "filler", "separator"):
        return dict(instance)
    kind, side, _ = parse_position(position)
    if kind == "corner":
        return dict(instance, type="corner")

    suffix = suffix_for_side(side)
    full_device = device_base + suffix if supplied_device == device_base and device_base in wiring["devices"] else supplied_device
    device_spec = wiring["devices"].get(device_base, {"pins": {}})
    unresolved = []
    # Resolve pin connections
    ctx = ResolutionContext(instance, domains, globals_, device_spec)
    pin_overrides = {pin: value["label"] for pin, value in instance.get("pin_connection", {}).items() if "label" in value}
    pin_overrides.update(overrides.get(position, {}).get("pin_overrides", {}))

    pin_connection: "OrderedDict[str, Dict[str, str]]" = OrderedDict()

    # Collect all pin specs to process: main pins + emittable io_direction_rules pins
    all_pin_specs: "OrderedDict[str, Dict]" = OrderedDict(device_spec["pins"])
    direction_val = instance.get("direction")
    if "io_direction_rules" in device_spec and direction_val:
        for pin_name, pin_spec in device_spec["io_direction_rules"].get(direction_val, {}).items():
            if isinstance(pin_spec, dict) and pin_spec.get("emit", False) and pin_name not in all_pin_specs:
                all_pin_specs[pin_name] = pin_spec

    for pin_name, pin_spec in all_pin_specs.items():
        if not pin_spec.get("emit", True) and pin_name not in pin_overrides:
            continue
        # Override?
        if pin_name in pin_overrides:
            override_val = pin_overrides[pin_name]
            if override_val.startswith("label_from:"):
                label = ctx.resolve(override_val.split(":", 1)[1])
            else:
                label = override_val
        else:
            try:
                label = ctx.resolve(pin_spec["label_from"])
            except InputError as exc:
                unresolved.append(f"{position}.{pin_name}: {exc.summary}")
                continue
        pin_connection[pin_name] = {"label": label}

    for pin_name, value in pin_overrides.items():
        if pin_name not in pin_connection:
            pin_connection[pin_name] = {"label": ctx.resolve(value[11:]) if value.startswith("label_from:") else value}

    out = OrderedDict(instance)
    out["type"] = inst_type
    out["device"] = full_device
    for pin, config in instance.get("pin_connection", {}).items():
        pin_connection[pin] = {**config, **pin_connection.get(pin, {})}
    out["pin_connection"] = pin_connection
    if unresolved:
        out["wiring_notes"] = unresolved

    return out


# ============================================================================
# Corner generation
# ============================================================================


CORNER_NAMES = {
    "top_left": "CORNER_TOPLEFT",
    "top_right": "CORNER_TOPRIGHT",
    "bottom_left": "CORNER_BOTTOMLEFT",
    "bottom_right": "CORNER_BOTTOMRIGHT",
}

# Adjacent outer-pad positions for each corner, given placement_order and ring dims.
# Counterclockwise traversal: left → bottom → right → top
# Clockwise traversal:        top  → right  → bottom → left


def adjacent_pads(corner: str, placement_order: str, w: int, h: int) -> Tuple[str, str]:
    if placement_order == "counterclockwise":
        return {
            "top_left":     (f"top_{w-1}",    f"left_0"),
            "top_right":    (f"top_0",        f"right_{h-1}"),
            "bottom_left":  (f"left_{h-1}",   f"bottom_0"),
            "bottom_right": (f"bottom_{w-1}", f"right_0"),
        }[corner]
    if placement_order == "clockwise":
        return {
            "top_left":     (f"left_{h-1}",   f"top_0"),
            "top_right":    (f"top_{w-1}",    f"right_0"),
            "bottom_left":  (f"bottom_{w-1}", f"left_0"),
            "bottom_right": (f"right_{h-1}",  f"bottom_0"),
        }[corner]
    raise InputError(
        f"Unknown placement_order '{placement_order}'",
        hint="Must be 'clockwise' or 'counterclockwise'.",
    )


def corner_insertion_order(placement_order: str) -> List[str]:
    """Order in which corners appear in the output instances list.

    Note: golden outputs vary — different cases use different orderings.
    We pick a deterministic order that matches the most common golden pattern.
    """
    if placement_order == "counterclockwise":
        return ["bottom_left", "top_left", "top_right", "bottom_right"]
    return ["top_right", "bottom_right", "bottom_left", "top_left"]


def generate_corners(expanded_pads: List[Dict[str, Any]], wiring: Dict[str, Any],
                     ring_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build 4 corner instances based on adjacent pad device families."""
    digital_families = set(wiring["family_classification"]["digital_families"])
    placement = ring_config["placement_order"]
    w = ring_config["width"]
    h = ring_config["height"]

    # Index pads by position for quick lookup
    by_pos: Dict[str, Dict[str, Any]] = {}
    for inst in expanded_pads:
        if inst["type"] == "pad":  # outer pads only
            by_pos[inst["position"]] = inst

    corners = []
    for corner_pos in corner_insertion_order(placement):
        adj_a, adj_b = adjacent_pads(corner_pos, placement, w, h)
        pad_a = by_pos.get(adj_a)
        pad_b = by_pos.get(adj_b)
        family_a = _device_family(pad_a["device"], wiring) if pad_a else None
        family_b = _device_family(pad_b["device"], wiring) if pad_b else None
        both_digital = family_a in digital_families and family_b in digital_families
        device = "PCORNER_G" if both_digital else "PCORNERA_G"

        corner = OrderedDict()
        corner["name"] = CORNER_NAMES[corner_pos]
        corner["device"] = device
        corner["position"] = corner_pos
        corner["type"] = "corner"
        corners.append(corner)

    return corners


def _device_family(full_device: str, wiring: Dict[str, Any]) -> str:
    """Lookup family from full device name (with suffix)."""
    base = full_device
    for suf in ("_H_G", "_V_G"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    spec = wiring["devices"].get(base)
    if not spec:
        return ""
    return spec["family"]


# ============================================================================
# Ring ESD override
# ============================================================================


def apply_ring_esd_override(instances: List[Dict[str, Any]], esd_signal: str) -> int:
    """Override every pad's VSS pin to esd_signal. Returns count of overrides applied."""
    count = 0
    for inst in instances:
        if inst.get("type") not in ("pad", "inner_pad"):
            continue
        pins = inst.get("pin_connection", {})
        if "VSS" in pins:
            pins["VSS"] = {"label": esd_signal}
            count += 1
    return count


# ============================================================================
# Gate checks
# ============================================================================


def _finding(results, rule, message, *, position=None, device=None, detail=None, hint=None, section=None):
    text = " ".join(str(part) for part in (position, device, message, detail, hint, section) if part)
    results.setdefault(rule, {}).setdefault("warnings", []).append(text)


def _finish(results, rule, **metadata):
    entry = results.setdefault(rule, {})
    entry.update(metadata)
    entry["pass"] = not bool(entry.get("warnings"))


def run_gates(intent_graph: Dict[str, Any], semantic: Dict[str, Any],
              wiring: Dict[str, Any]) -> Dict[str, Any]:
    """Collect application-note recommendations alongside the generated design."""

    instances = intent_graph["instances"]
    ring = intent_graph["ring_config"]
    w, h = ring["width"], ring["height"]
    digital_families = set(wiring["family_classification"]["digital_families"])

    results: Dict[str, Any] = {}

    positions = [p["position"] for p in instances]
    if len(set(positions)) != len(positions):
        _finding(results, "G1_side_counts", "G1: two physical cells have the same position")
    # G1: Side counts
    side_counts = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    for inst in instances:
        if inst["type"] != "pad":
            continue
        for side in side_counts:
            if inst["position"].startswith(side + "_"):
                side_counts[side] += 1
                break
    expected = {"left": h, "right": h, "top": w, "bottom": w}
    if side_counts != expected:
        _finding(results, "G1_side_counts",
            "G1: Outer pad side counts mismatch",
            detail=f"expected={expected}, actual={side_counts}",
            hint="Check semantic intent has correct number of outer pads per side.",
            section="§5 (Classification rules)",
        )
    _finish(results, "G1_side_counts", counts=side_counts)

    # G2: 4 corners
    corners = [i for i in instances if i["type"] == "corner"]
    if len(corners) != 4:
        _finding(results, "G2_corners", f"G2: Corner count is {len(corners)}, expected 4")
    _finish(results, "G2_corners")

    # G3: Digital provider count — each digital domain must have exactly 4 unique provider names.
    # Multi-quadrant rings with independent digital rails per quadrant have multiple digital domains;
    # the check is therefore per-domain, not global.
    digital_domains = {
        d_id: d for d_id, d in semantic.get("domains", {}).items()
        if d.get("kind") == "digital"
    }
    if digital_domains:
        g3_domain_results = {}
        for d_id, d in digital_domains.items():
            roles = ("low_vdd", "low_vss", "high_vdd", "high_vss")
            if not all(isinstance(d.get(k), str) and d[k].strip() for k in roles):
                _finding(results, "G3_digital_provider_count", f"G3: Domain '{d_id}' needs a rail name for each of {roles}")
            if {d.get("low_vdd"), d.get("high_vdd")} & {d.get("low_vss"), d.get("high_vss")}:
                _finding(results, "G3_digital_provider_count", f"G3: Domain '{d_id}' uses the same net for power and ground")
            g3_domain_results[d_id] = {k: d.get(k) for k in roles}
        _finish(results, "G3_digital_provider_count", per_domain=g3_domain_results)
    else:
        _finish(results, "G3_digital_provider_count", skipped="no digital domain")

    # G4: VSS consistency across all pads
    vss_labels = set()
    for inst in instances:
        if inst.get("type") not in ("pad", "inner_pad"):
            continue
        vss_pin = inst.get("pin_connection", {}).get("VSS")
        if vss_pin and vss_pin.get("label"):
            vss_labels.add(vss_pin["label"])
    if len(vss_labels) > 1:
        _finding(results, "G4_vss_consistency",
            f"G4: VSS pin labels not consistent across ring",
            detail=f"distinct VSS labels = {sorted(vss_labels)}",
            hint="All pads must share the same VSS label (digital low VSS, "
                 "or ring_esd signal if active).",
            section="§5 (Universal VSS rule)",
        )
    _finish(results, "G4_vss_consistency", label=next(iter(vss_labels), None))

    # G5: Required pins on digital pads (VDD/VSS/VDDPST/VSSPST)
    for inst in instances:
        if inst.get("type") not in ("pad", "inner_pad"):
            continue
        family = _device_family(inst["device"], wiring)
        if family in digital_families:
            pins = inst.get("pin_connection", {})
            required_pins = ("VDD", "VSS", "VDDPST") if _strip_suffix(inst["device"]) == "PVSS3DGZ" else ("VDD", "VSS", "VDDPST", "VSSPST")
            for required in required_pins:
                if required not in pins:
                    _finding(results, "G5_digital_required_pins",
                        f"G5: Digital pad missing required pin {required}",
                        position=inst["position"],
                        device=inst["device"],
                    )
    _finish(results, "G5_digital_required_pins")

    # G6: Direction field present iff digital_io
    digital_io_list = set(wiring.get("digital_io_devices", {}).get("list", []))
    for inst in instances:
        if inst.get("type") not in ("pad", "inner_pad"):
            continue
        base = _strip_suffix(inst["device"])
        has_direction = "direction" in inst
        is_digital_io = base in digital_io_list
        if is_digital_io and not has_direction:
            _finding(results, "G6_direction_field",
                "G6: digital_io device missing direction",
                position=inst["position"],
                device=inst["device"],
            )
    _finish(results, "G6_direction_field")

    # G7: Ring ESD validation
    esd = semantic.get("global", {}).get("ring_esd")
    if esd:
        # Verify VSS labels all equal ESD
        for inst in instances:
            if inst.get("type") not in ("pad", "inner_pad"):
                continue
            vss = inst.get("pin_connection", {}).get("VSS", {}).get("label")
            if vss != esd:
                _finding(results, "G7_ring_esd",
                    f"G7: Ring ESD active but pad VSS != '{esd}' (got '{vss}')",
                    position=inst["position"],
                )
        _finish(results, "G7_ring_esd", esd_signal=esd)
    else:
        _finish(results, "G7_ring_esd", skipped="no ring_esd set")

    # G8: Domain continuity (warning, not hard fail)
    warnings = _check_domain_continuity(instances, semantic, w, h)
    _finish(results, "G8_domain_continuity", warnings=warnings)

    # G9: Provider signal names exist as instances with correct provider device
    _check_provider_instances(semantic, wiring, results)

    # G13: count bonded supply cells in each domain.
    _check_supply_plan(semantic, results)

    # G11: One and only one PVDD2POC per digital domain (extra VDDPST supplies use PVDD2DGZ)
    _check_poc_per_domain(semantic, results)

    # G12: The VSS ESD-bus supply cell matches its analog domain's voltage family
    _check_esd_cell_family(semantic, results)

    return results


def _check_provider_instances(semantic: Dict[str, Any], wiring: Dict[str, Any],
                             results: Dict[str, Any]) -> None:
    """G9: Verify provider names in domains exist as instances with correct provider device."""
    devices = wiring["devices"]
    instances = semantic.get("instances", [])
    domains = semantic.get("domains", {})

    # Build name → [(device, domain)] lookup (same name can appear at multiple positions)
    name_to_instances: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    for inst in instances:
        name = inst["name"]
        name_to_instances.setdefault(name, []).append(
            (inst.get("device", ""), inst.get("domain"))
        )

    for domain_id, domain_spec in domains.items():
        kind = domain_spec.get("kind", "")

        if kind == "analog":
            for provider_key, family in (("vdd_provider", "analog_power_provider"),
                                         ("vss_provider", "analog_ground_provider")):
                provider_name = domain_spec.get(provider_key)
                if not provider_name:
                    continue
                matches = name_to_instances.get(provider_name, [])
                if not matches:
                    _finding(results, "G9_provider_instances",
                        f"G9: Analog domain '{domain_id}' {provider_key}='{provider_name}' "
                        f"not found in any instance name",
                        hint=f"Add an instance with name='{provider_name}' and a provider device "
                             f"(PVDD3AC/PVSS3AC or PVDD3A/PVSS3A) assigned to domain '{domain_id}'.",
                        section="§5.5 (Step 3.1 Voltage Domain)",
                    )
                # Check that at least one instance with this name in this domain is a provider device
                has_provider = False
                for dev, dom in matches:
                    if dom != domain_id:
                        continue
                    dev_spec = devices.get(dev)
                    if dev_spec and dev_spec.get("family") == family:
                        has_provider = True
                        break
                if not has_provider:
                    found_devices = [dev for dev, dom in matches if dom == domain_id]
                    _finding(results, "G9_provider_instances",
                        f"G9: Analog domain '{domain_id}' {provider_key}='{provider_name}' "
                        f"exists as instance(s) but none use a provider device",
                        detail=f"found device(s): {found_devices}; expected a provider "
                               f"(PVDD3AC/PVSS3AC or PVDD3A/PVSS3A)",
                        hint=f"Change the device for '{provider_name}' in domain '{domain_id}' "
                             f"to a provider device, or pick a different provider name.",
                        section="§5.6 (Step 3.2 Provider/consumer device selection)",
                    )

        elif kind == "digital":
            provider_role_device = {
                "low_vdd": "PVDD1DGZ",
                "low_vss": ("PVSS1DGZ", "PVSS3DGZ"),
                "high_vdd": ("PVDD2DGZ", "PVDD2POC"),
                "high_vss": ("PVSS2DGZ", "PVSS3DGZ"),
            }
            for provider_key, expected_device in provider_role_device.items():
                provider_name = domain_spec.get(provider_key)
                if not provider_name:
                    continue
                matches = name_to_instances.get(provider_name, [])
                if not matches:
                    _finding(results, "G9_provider_instances",
                        f"G9: Digital domain '{domain_id}' {provider_key}='{provider_name}' "
                        f"not found in any instance name",
                        hint=f"Add an instance with name='{provider_name}' and device='{expected_device}'.",
                        section="§5.3 (Step 2.2 Digital provider assignment)",
                    )
                has_correct_device = any(dom == domain_id and dev in (expected_device if isinstance(expected_device, tuple) else (expected_device,)) for dev, dom in matches)
                if not has_correct_device:
                    found_devices = list(set(dev for dev, _ in matches))
                    _finding(results, "G9_provider_instances",
                        f"G9: Digital domain '{domain_id}' {provider_key}='{provider_name}' "
                        f"exists but no instance uses expected device '{expected_device}'",
                        detail=f"found device(s): {found_devices}",
                        hint=f"Change the device for '{provider_name}' to '{expected_device}', "
                             f"or pick a provider name that already uses it.",
                        section="§5.3 (Step 2.2 Digital provider assignment)",
                    )

    _finish(results, "G9_provider_instances")


def _check_supply_plan(semantic, results):
    """Check planned bonded cells per electrical domain (AN 8.6 and 10.6)."""
    errors = []
    pending = []
    for domain_id, spec in semantic["domains"].items():
        pads = [p for p in semantic["instances"] if p.get("domain") == domain_id]
        if any(type(p.get("bonded", True)) is not bool for p in pads):
            errors.append(f"{domain_id}: bonded should be a JSON boolean")
        bonded = [p for p in pads if p.get("bonded", True)]
        count = Counter(p["device"] for p in bonded)
        devices = {p["device"] for p in pads}
        for key in ("core_voltage", "io_voltage"):
            voltage = spec.get(key)
            if voltage is None:
                pending.append(f"{domain_id}: supply {key} in volts before integration")
            elif type(voltage) not in (float, int) or not isfinite(voltage) or voltage <= 0:
                errors.append(f"{domain_id}: invalid {key}")
        if spec.get("kind") == "digital":
            minima = [(("PVDD1DGZ",), 3), (("PVDD2DGZ", "PVDD2POC"), 2),
                      (("PVSS1DGZ", "PVSS3DGZ"), 1), (("PVSS2DGZ", "PVSS3DGZ"), 1)]
            if "PVSS3DGZ" in devices and spec.get("low_vss") != spec.get("high_vss"):
                errors.append(f"{domain_id}: PVSS3DGZ internally connects both grounds")
            roles = {"PVDD1DGZ": "low_vdd", "PVDD2POC": "high_vdd", "PVDD2DGZ": "high_vdd",
                     "PVSS1DGZ": "low_vss", "PVSS3DGZ": "low_vss", "PVSS2DGZ": "high_vss"}
            for p in pads:
                role = roles.get(p["device"])
                if role and role in spec and p["name"] != spec[role]:
                    errors.append(f"{p['position']}: {p['device']} must supply {spec[role]}")
            drivers = [p for p in pads if p.get("device") in {"PDDW16SDGZ","PRUW08SDGZ"}]
            factors = [p.get("drive_factor") for p in drivers]
            for key in ("package_inductance_nh", "load_pf"):
                value = spec.get(key)
                if value is not None and (type(value) not in (int, float) or not isfinite(value) or value <= 0):
                    errors.append(f"{domain_id}: invalid {key}")
            if drivers and not all(spec.get(k) for k in ("sso_source", "package_inductance_nh", "load_pf")):
                pending.append(f"{domain_id}: verify drive factors against the library table at the package inductance and load")
            if any(v is None for v in factors):
                pending.append(f"{domain_id}: SSO needs package inductance, load and drive factors for every bidirectional IO (7.3)")
            elif any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in factors):
                errors.append(f"{domain_id}: invalid SSO drive_factor")
            elif drivers:
                from math import ceil
                total = round(sum(factors), 10)
                minima += [(("PVSS2DGZ", "PVSS3DGZ"), ceil(total)),
                           (("PVDD2DGZ", "PVDD2POC"), ceil(round(total / 1.1, 10)))]
        elif spec.get("kind") == "analog":
            core = "PVDD3AC" in devices
            if core and "PVDD3A" in devices:
                errors.append(f"{domain_id}: PVDD3A and PVDD3AC share a domain (9.3)")
            suffix = "AC" if core else "A"
            minima = [(("PVDD3" + suffix,), 3 if core else 2), (("PVSS3" + suffix,), 1)]
            if any(d in devices for d in ("PDB3AC", "PVSS3AC")) and not core:
                errors.append(f"{domain_id}: core-voltage cells need a core-voltage bus provider")
            if "PVSS3A" in devices and core:
                errors.append(f"{domain_id}: IO-voltage ground on a core-voltage bus")
            if not core and {"PVDD1AC", "PVSS1AC"} & devices or core and {"PVDD1A", "PVSS1A"} & devices:
                errors.append(f"{domain_id}: dedicated macro cells require the matching analog bus family")
            if core:
                pending.append(f"{domain_id}: verify core clamp, orientation and connection (10.7, 16)")
            for polarity, role in (("PVDD3", "vdd_provider"), ("PVSS3", "vss_provider")):
                if any(p["device"].startswith(polarity) and p["name"] != spec.get(role) for p in pads):
                    errors.append(f"{domain_id}: a {polarity} pad would short distinct named bus supplies")
            for dedicated, minimum in (("AC", 3), ("A", 2)):
                groups = Counter()
                for p in pads:
                    if p["device"] not in {"PVDD1" + dedicated, "PVSS1" + dedicated}:
                        continue
                    if not p.get("macro") or not p.get("package_pin"):
                        errors.append(f"{p['position']}: dedicated supply requires macro and package_pin (9.5–9.6)")
                    if p["device"].startswith("PVDD") and p.get("bonded", True):
                        groups[(p["name"], p.get("package_pin"))] += 1
                    paired = "PVSS1" if p["device"].startswith("PVDD") else "PVDD1"
                    if not any(q["device"] == paired + dedicated and q.get("macro") == p.get("macro") for q in bonded):
                        errors.append(f"{p['position']}: missing dedicated {paired + dedicated} for {p.get('macro')}")
                for group, n in groups.items():
                    if n < minimum:
                        errors.append(f"{domain_id}: {group} has {n} bonded PVDD1{dedicated}, needs {minimum}")
        else:
            errors.append(f"{domain_id}: no supply recommendation for this domain kind")
            continue
        for masters, minimum in minima:
            n = sum(count[m] for m in masters)
            if n < minimum:
                errors.append(f"{domain_id}: {'/'.join(masters)} bonded {n}, requires {minimum}")
    if errors:
        results["G13_supply_plan"] = {"warnings": errors}
    _finish(results, "G13_supply_plan", pending=pending)


def _check_poc_per_domain(semantic: Dict[str, Any], results: Dict[str, Any]) -> None:
    """G11: A digital domain holds exactly one PVDD2POC; further VDDPST supplies are PVDD2DGZ."""
    counts = {}
    for d_id, d in semantic.get("domains", {}).items():
        if d.get("kind") != "digital":
            continue
        pocs = [i["position"] for i in semantic.get("instances", [])
                if i.get("domain") == d_id and i.get("device") == "PVDD2POC"]
        has_io = any(i.get("domain") == d_id and i.get("direction") in ("input", "output")
                     for i in semantic["instances"])
        grounded = d.get("poc_grounded") is True
        if grounded == has_io or len(pocs) != int(has_io):
            _finding(results, "G11_poc_per_domain", f"G11: {d_id} has {len(pocs)} PVDD2POC, functional IO={has_io}. "
                            "Use one POC source with functional IO. For a supply-only domain "
                            "set poc_grounded=true and plan the physical ground connection.")
        counts[d_id] = len(pocs)
    _finish(results, "G11_poc_per_domain", per_domain=counts)


def _check_esd_cell_family(semantic: Dict[str, Any], results: Dict[str, Any]) -> None:
    """G12: PVSS2AC belongs to core-voltage (AC) analog domains, PVSS2A to I/O-voltage (A) domains."""
    ac_family = {"PVDD3AC", "PVSS3AC", "PVDD1AC", "PVSS1AC", "PDB3AC"}
    a_family = {"PVDD3A", "PVSS3A", "PVDD1A", "PVSS1A"}
    for d_id, d in semantic.get("domains", {}).items():
        if d.get("kind") != "analog":
            continue
        members = [i for i in semantic.get("instances", []) if i.get("domain") == d_id]
        devices = {i.get("device", "") for i in members}
        for esd, wrong, right in (("PVSS2A", ac_family, "PVSS2AC"), ("PVSS2AC", a_family, "PVSS2A")):
            if esd in devices and devices & wrong:
                _finding(results, "G12_esd_cell_family",
                    f"G12: Analog domain '{d_id}' uses {esd} with {sorted(devices & wrong)}",
                    detail=f"{esd} at {[i['position'] for i in members if i.get('device') == esd]}",
                    hint=f"Use {right} for the VSS ESD-bus supply in this domain; PVSS2AC serves core-voltage "
                         f"(AC) domains and PVSS2A I/O-voltage (A) domains, and the two must not share a domain.",
                    section="§5.8 (Ring ESD handling)",
                )
    _finish(results, "G12_esd_cell_family")


def _strip_suffix(device: str) -> str:
    for suf in ("_H_G", "_V_G"):
        if device.endswith(suf):
            return device[: -len(suf)]
    return device


def _check_domain_continuity(instances: List[Dict[str, Any]], semantic: Dict[str, Any],
                              w: int, h: int) -> List[str]:
    """Return warning strings for non-contiguous domains. Allows ring-wrap continuity."""
    sem_instances = semantic.get("instances", [])
    if not sem_instances:
        return []

    # Compute traversal order for outer pads
    placement = semantic["ring_config"]["placement_order"]
    if placement == "counterclockwise":
        sides = [("left", h), ("bottom", w), ("right", h), ("top", w)]
    else:
        sides = [("top", w), ("right", h), ("bottom", w), ("left", h)]

    # Build position → domain map (outer pads only for continuity check)
    pos_to_domain = {}
    for s in sem_instances:
        if s.get("type") == "pad":
            pos_to_domain[s["position"]] = s.get("domain")

    # Walk traversal, build domain sequence
    seq = []
    for side, count in sides:
        for i in range(count):
            d = pos_to_domain.get(f"{side}_{i}")
            if d:
                seq.append(d)

    if not seq:
        return []

    # For each domain, count blocks (allowing ring wrap)
    warnings = []
    for d_id in set(seq):
        # Run-length encode
        blocks = 0
        in_block = False
        for x in seq:
            if x == d_id:
                if not in_block:
                    blocks += 1
                    in_block = True
            else:
                in_block = False
        # Ring wrap: if first and last are both this domain, merge blocks count by 1
        if blocks > 1 and seq[0] == d_id and seq[-1] == d_id:
            blocks -= 1
        if blocks > 1:
            warnings.append(
                f"Domain '{d_id}' has {blocks} non-contiguous blocks; "
                f"verify each block has its own provider pair."
            )
    return warnings


# ============================================================================
# Top-level enrich() function
# ============================================================================


def enrich(semantic_path: Path, wiring_path: Path,
           output_path: Path) -> Dict[str, Any]:
    """Read semantic intent, run engine, write intent graph. Return summary dict."""

    started = time.time()

    # Load wiring
    wiring = load_wiring_table(wiring_path)

    # Load semantic intent
    if not semantic_path.exists():
        raise InputError(f"Semantic intent file not found: {semantic_path}")
    try:
        with open(semantic_path, "r", encoding="utf-8") as f:
            semantic = json.load(f)
    except json.JSONDecodeError as e:
        raise InputError(f"Semantic intent is not valid JSON: {e}")

    # Top-level checks
    for required in ("ring_config", "instances"):
        if required not in semantic:
            raise InputError(
                f"Semantic intent missing top-level '{required}'",
                hint="See references/enrichment_rules_T28.md §4 for the required schema.",
                section="§4.1 (Schema)",
            )
    domains = semantic.setdefault("domains", {})
    globals_ = semantic.get("global", {})
    overrides = semantic.get("overrides", {})
    ring_config = semantic["ring_config"]

    # Phase 2: Expand instances
    expanded: List[Dict[str, Any]] = []
    for inst in semantic["instances"]:
        out_inst = expand_instance(inst, wiring, domains, globals_, overrides)
        expanded.append(out_inst)

    # Phase 3: Generate corners
    corners = []
    if ring_config.get("auto_corners", True):
        provided = {p["position"] for p in expanded if p.get("type") == "corner"}
        corners = [c for c in generate_corners(expanded, wiring, ring_config) if c["position"] not in provided]

    # Phase 4: Ring ESD override (if active)
    esd_signal = globals_.get("ring_esd")
    esd_count = 0
    if esd_signal:
        explicit_vss = {p["position"] for p in semantic["instances"] if "VSS" in p.get("pin_connection", {})}
        explicit_vss.update(pos for pos, spec in overrides.items() if "VSS" in spec.get("pin_overrides", {}))
        esd_count = apply_ring_esd_override([p for p in expanded if p["position"] not in explicit_vss], esd_signal)

    # Assemble final intent graph
    intent_graph = OrderedDict()
    intent_graph["ring_config"] = OrderedDict([
        ("width", ring_config["width"]),
        ("height", ring_config["height"]),
        ("placement_order", ring_config["placement_order"]),
    ])
    intent_graph["ring_config"].update(ring_config)
    intent_graph["ring_config"]["domains"] = domains
    intent_graph["instances"] = expanded + corners

    # Phase 5: Gate checks
    gate_results = run_gates(intent_graph, semantic, wiring)
    notes = [note for inst in expanded for note in inst.get("wiring_notes", [])]
    if notes:
        _finish(gate_results, "wiring_defaults", warnings=notes)

    intent_graph["recommendations"] = gate_results

    # Write intent graph
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(intent_graph, f, indent=2, ensure_ascii=False)

    duration_ms = int((time.time() - started) * 1000)

    return {
        "intent_graph": intent_graph,
        "duration_ms": duration_ms,
        "esd_override_applied": esd_count > 0,
        "esd_pads_overridden": esd_count,
        "gates": gate_results,
    }
