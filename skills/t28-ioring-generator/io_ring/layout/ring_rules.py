"""T28 application-note checks on the cells that will actually be placed."""

from collections import defaultdict
from math import isclose, isfinite
from .auto_filler import ANALOG_PG, CUTS, base_device, boundary
from .voltage_domain import VoltageDomainHandler
from .enrichment_engine import _check_supply_plan, _check_poc_per_domain


def check_placed_ring(cells, config, generator):
    # Review is best effort, including for edited or partial floorplans.
    try:
        return _review_placement(cells, config, generator)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return {"warnings": [f"Placement review incomplete: {exc}"]}


def _corner_neighbour(cells):
    """Find the first functional cell or power cut on one side of a corner."""
    return next(
        (c for c in cells if c["type"] != "filler" or c["device"] in CUTS),
        None,
    )


def _review_placement(cells, config, generator):
    warnings = []
    width, height = config["chip_width"], config["chip_height"]
    corner = config["corner_size"]
    absolute = generator.convert_relative_to_absolute(width, height, cells, config)
    # Each anchor is at the trailing edge in clockwise traversal.
    edges = {
        "R180": ("top_left", width, lambda x, y: (x, height - y)),
        "R90": ("top_right", height, lambda x, y: (height - y, width - x)),
        "R0": ("bottom_right", width, lambda x, y: (width - x, y)),
        "R270": ("bottom_left", height, lambda x, y: (y, x)),
    }
    corners = {tuple(c["position"]): c for c in absolute if c["type"] == "corner"}
    coords = {
        "top_left": (0, height),
        "top_right": (width, height),
        "bottom_right": (width, 0),
        "bottom_left": (0, 0),
    }
    if (
        set(corners) != set(coords.values())
        or sum(c["type"] == "corner" for c in absolute) != 4
    ):
        warnings.append("Expected one corner at each vertex of a full ring")
    ordered = []
    side_cells = {}
    for orientation, (name, length, project) in edges.items():
        if coords[name] in corners:
            ordered.append(corners[coords[name]])
        edge = []
        for c in absolute:
            if c["type"] != "corner" and c["orientation"] == orientation:
                end, offset = project(*c["position"])
                size, _ = generator._resolve_component_geometry(c, c["type"], config)
                if not isclose(offset, 0, abs_tol=1e-6):
                    warnings.append(f"{c['name']} lies off the {name} edge")
                edge.append((end, size, c))
        placed = []
        previous = corner
        for end, size, c in sorted(edge, key=lambda item: item[0]):
            if not isclose(end - size, previous, abs_tol=1e-6):
                warnings.append(f"Gap or overlap at {c['name']} on {name} edge")
            c["_width"] = size
            placed.append(c)
            previous = end
        side_cells[name] = placed
        ordered.extend(placed)
        if not isclose(previous, length - corner, abs_tol=1e-6):
            warnings.append(f"Incomplete edge at {name}")
    if len(ordered) != len(absolute):
        warnings.append("Unplaced or unsupported cell orientation")

    pads = []
    anchors = [i for i, c in enumerate(ordered) if c["type"] in {"pad", "inner_pad"}]
    if not anchors:
        warnings.append("Ring has no functional cells")
        return {"warnings": warnings}
    sides = list(side_cells)
    for i, side in enumerate(sides):
        c = corners.get(coords[side])
        if c is None:
            continue
        allowed = {
            "PCORNER_G": {"PVSS2DGZ", "PVSS3DGZ"},
            "PCORNERA_G": {"PVSS3A", "PVSS3AC"},
        }.get(c["device"], set())
        neighbours = (
            _corner_neighbour(reversed(side_cells[sides[i - 1]])),
            _corner_neighbour(side_cells[side]),
        )
        if not all(
            p is not None and base_device(p) in allowed and p.get("bonded", True)
            for p in neighbours
        ):
            warnings.append(
                f"{c['name']}: {c['device']} needs adjacent bonded grounds on both sides (6.2, 9.8.2)"
            )

    n = len(ordered)
    for i, c in enumerate(ordered):
        dev = c["device"]
        if dev == "PRCUTA_G":
            neighbours = [ordered[(i + d) % n] for d in (-1, 1)]
            if not any(base_device(p) in ANALOG_PG for p in neighbours):
                warnings.append(
                    f"{c['name']}: PRCUTA_G needs adjacent analog power or ground (9.8.3)"
                )
        elif dev == "PRCUT_G":
            for step in (-1, 1):
                distance = 0
                j = (i + step) % n
                while distance <= 40:
                    p = ordered[j]
                    if base_device(p) in {"PVSS1DGZ", "PVSS3DGZ"} and p.get(
                        "bonded", True
                    ):
                        break
                    if p["type"] == "corner" or p["device"] in CUTS:
                        distance = 41
                        break
                    distance += p["_width"]
                    j = (j + step) % n
                if distance > 40:
                    warnings.append(
                        f"{c['name']}: PRCUT_G lacks a digital ground within two widths (34y.2)"
                    )

    domains = dict(config.get("domains", {}))
    bus_nets = defaultdict(dict)
    for index, i in enumerate(anchors):
        j = anchors[(index + 1) % len(anchors)]
        left, right = ordered[i], ordered[j]
        gap = ordered[i + 1 : j] if j > i else ordered[i + 1 :] + ordered[:j]
        expected = boundary(left, right)
        cuts = [p["device"] for p in gap if p["device"] in CUTS]
        if cuts != ([expected] if expected in CUTS else []):
            warnings.append(
                f"{left['name']} to {right['name']}: expected {expected}, found cuts {cuts}"
            )
        kind = VoltageDomainHandler.get_voltage_domain(left)
        for item in gap:
            if item["device"] in CUTS:
                kind = VoltageDomainHandler.get_voltage_domain(right)
            elif item["device"].startswith("PFILLER"):
                analog = item["device"].endswith("A_G")
                if analog != (kind == "analog"):
                    warnings.append(
                        f"{item['name']}: spacer does not match its {kind} bus"
                    )
        key = left.get("domain") or VoltageDomainHandler.get_voltage_domain_key(left)
        pins = left.get("pin_connection", {})
        if key not in domains:
            if config.get("domains"):
                warnings.append(f"{left['name']}: unknown domain {key}")
            kind = VoltageDomainHandler.get_voltage_domain(left)
            domains[key] = {"kind": kind}
            if kind == "analog":
                for rail, role in (("VDD", "vdd_provider"), ("VSS", "vss_provider")):
                    net = pins.get("TAC" + rail) or pins.get("TA" + rail)
                    domains[key][role] = net["label"] if net else None
            else:
                for rail, role in (
                    ("VDD", "low_vdd"),
                    ("VSS", "low_vss"),
                    ("VDDPST", "high_vdd"),
                    ("VSSPST", "high_vss"),
                ):
                    contact = pins.get(rail) or (
                        pins.get("VSS")
                        if rail == "VSSPST" and base_device(left) == "PVSS3DGZ"
                        else None
                    )
                    if contact:
                        domains[key][role] = contact["label"]
                if pins.get("POC") and pins["POC"] == pins.get("VSS"):
                    domains[key]["poc_grounded"] = True
        if domains[key].get("kind") != VoltageDomainHandler.get_voltage_domain(left):
            warnings.append(f"{left['name']}: pin family disagrees with domain {key}")
        bus_pins = (
            ("TACVDD", "TACVSS", "TAVDD", "TAVSS", "VSS")
            if domains[key]["kind"] == "analog"
            else ("VDD", "VSS", "VDDPST", "VSSPST", "POC")
        )
        for pin in bus_pins:
            if pin in pins:
                net = pins[pin]["label"]
                expected_net = bus_nets[key].setdefault(pin, net)
                if expected_net != net:
                    warnings.append(
                        f"{left['name']}: {key}.{pin} connects both {expected_net} and {net}"
                    )
        pads.append(dict(left, domain=key, device=base_device(left)))
    semantic = {"instances": pads, "domains": domains}
    results = {"warnings": warnings}
    _check_supply_plan(semantic, results)
    _check_poc_per_domain(semantic, results)
    pending = results["G13_supply_plan"]["pending"]
    pending.append(
        "Check bonded package mapping and same-domain bus resistance against tables 8.1/10.1 using extraction."
    )
    if any(d.get("poc_grounded") for d in domains.values()):
        pending.append(
            "Verify a physical POC-to-ground tie in each supply-only digital domain (3.4.1)."
        )
    if any(d.get("kind") == "analog" for d in domains.values()):
        pending.append(
            "Verify AVDD-to-AVSS capacitance >=20 pF, clamp connections, signal swing and secondary ESD protection."
        )
    results["vss_bus"] = _vss_paths(ordered, config, pending)
    results["same_domain_bus"] = _bus_spacing(ordered, config, pending)
    repeated = defaultdict(list)
    for pad in pads:
        if pad["device"] == "PDB3AC":
            repeated[pad["name"]].append(pad.get("position_str", pad["position"]))
    results["repeated_analog_ports"] = {k: v for k, v in repeated.items() if len(v) > 1}
    if results["repeated_analog_ports"]:
        pending.append(
            "Locate the physical join for each repeated analog port and verify it "
            "with extracted LVS at the hierarchy level containing the complete route."
        )
    return results


def _vss_paths(ring, config, pending):
    """Estimate the shortest eligible bus route from each core-voltage analog IO.

    A calibrated resistance per unit length is optional. Traverse both directions
    to the first eligible electrode. Use the two corner legs for a planning estimate.
    """
    coefficient = config.get("vss_ohm_per_um")
    if coefficient is not None and (
        type(coefficient) not in (int, float)
        or not isfinite(coefficient)
        or coefficient <= 0
    ):
        pending.append(
            "VSS resistance estimate omitted: vss_ohm_per_um must be positive and finite"
        )
        coefficient = None
    paths = []
    for i, pad in enumerate(ring):
        if base_device(pad) != "PDB3AC":
            continue
        candidates = []
        for step in (-1, 1):
            last_domain = pad
            crossings = 0
            distance = pad["_width"] / 2
            for offset in range(1, len(ring)):
                c = ring[(i + step * offset) % len(ring)]
                width = c.get("_width", 2 * config["corner_size"])
                if c["type"] in {"pad", "inner_pad"}:
                    if not VoltageDomainHandler.is_same_voltage_domain(last_domain, c):
                        crossings += 1
                    if crossings > 1:
                        break
                    last_domain = c
                    allowed = {"PVSS2AC"} if crossings == 0 else {"PVSS1DGZ"}
                    if c.get("bonded", True) and base_device(c) in allowed:
                        candidates.append((distance + width / 2, c))
                        break
                distance += width
        if not candidates:
            pending.append(
                f"{pad['name']}: no bonded global VSS supply in own/adjacent domain (10.4, 23y.3)"
            )
            continue
        length, ground = min(candidates, key=lambda pair: pair[0])
        row = {
            "position": pad.get("position_str", pad["position"]),
            "signal": pad["name"],
            "ground_position": ground.get("position_str", ground["position"]),
            "estimated_length_um": length,
        }
        if coefficient is not None:
            row["estimated_ohm"] = length * coefficient
            if row["estimated_ohm"] >= 1:
                pending.append(
                    f"{pad['name']} at {row['position']}: VSS estimate >=1 ohm. Review supply placement against extraction."
                )
        paths.append(row)
    if paths:
        pending.append(
            "Confirm each PDB3AC path to its nearest eligible bonded VSS supply is below 1 ohm (23y.3)."
        )
    return paths


def _pair_limit(kind, masters):
    """Planning limits for the supported bus classes (AN Tables 8.1 and 10.1)."""
    if kind == "analog":
        groups = {"PDB3AC": "io"}
        for suffix in ("A", "AC"):
            for role in ("PVDD3", "PVSS3", "PVSS2", "PVDD1", "PVSS1"):
                groups[role + suffix] = role
        a, b = (groups.get(master) for master in masters)
        if a and b and a != b:
            return 3 if "PVSS2" in (a, b) else 1
    else:
        groups = {
            "PDDW16SDGZ": "io",
            "PRUW08SDGZ": "io",
            "PVDD1DGZ": "vdd",
            "PVDD2DGZ": "vddpst",
            "PVDD2POC": "vddpst",
            "PVSS1DGZ": "vss",
            "PVSS2DGZ": "vsspst",
        }
        a, b = (groups.get(master) for master in masters)
        if a and b and a != b:
            three = {
                frozenset(pair)
                for pair in (
                    ("io", "vdd"),
                    ("io", "vss"),
                    ("vdd", "vddpst"),
                    ("vdd", "vsspst"),
                    ("vss", "vsspst"),
                )
            }
            return 3 if frozenset((a, b)) in three else 1
    return None


def _bus_spacing(ring, config, pending):
    """Report the longest same-domain path by master pair for extraction review.

    For each pair of bonded positions use the shorter uncut perimeter route.
    Lengths are centre-to-centre estimates and include both legs of each corner.
    """
    widths = [cell.get("_width", 2 * config["corner_size"]) for cell in ring]
    pads = {"pad", "inner_pad"}
    paths = {}
    for i, left in enumerate(ring):
        if left["type"] not in pads or not left.get("bonded", True):
            continue
        distance = widths[i] / 2
        for offset in range(1, len(ring)):
            j = (i + offset) % len(ring)
            right = ring[j]
            if right["device"] in CUTS:
                break
            if right["type"] in pads and right.get("bonded", True):
                pair = tuple(sorted((i, j)))
                length = distance + widths[j] / 2
                paths[pair] = min(paths.get(pair, length), length)
            distance += widths[j]

    worst = {}
    for (i, j), length in paths.items():
        left, right = ring[i], ring[j]
        domain = left.get("domain") or VoltageDomainHandler.get_voltage_domain_key(left)
        masters = tuple(sorted((base_device(left), base_device(right))))
        if masters[0] == masters[1]:
            continue
        key = domain, masters
        if key not in worst or length > worst[key]["estimated_length_um"]:
            worst[key] = {
                "domain": domain,
                "masters": masters,
                "estimated_length_um": length,
                "positions": [
                    p.get("position_str", p["position"]) for p in (left, right)
                ],
                "reference": "8.1"
                if VoltageDomainHandler.get_voltage_domain(left) == "digital"
                else "10.1",
            }
    coefficients = config.get("bus_ohm_per_um", {})
    if not isinstance(coefficients, dict) or any(
        type(value) not in (float, int) or not isfinite(value) or value <= 0
        for value in coefficients.values()
    ):
        pending.append(
            "bus_ohm_per_um must map domains to positive, finite resistances per micron"
        )
        coefficients = {}
    for row in worst.values():
        kind = "analog" if row["reference"] == "10.1" else "digital"
        limit = _pair_limit(kind, row["masters"])
        row["planning_limit_ohm"] = limit
        if row["domain"] in coefficients:
            row["estimated_ohm"] = (
                row["estimated_length_um"] * coefficients[row["domain"]]
            )
            if limit is not None and row["estimated_ohm"] > limit:
                pending.append(
                    f"{row['domain']} {row['positions']}: estimate exceeds {limit} ohm. "
                    f"Check topology, applicability and extracted resistance (Table {row['reference']})."
                )
    return list(worst.values())
