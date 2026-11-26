"""Fill T28 pad gaps while preserving the side length and electrical boundaries."""

from collections import defaultdict

from .enrichment_engine import adjacent_pads
from .filler_generator import FillerGenerator
from .voltage_domain import VoltageDomainHandler
from .device_classifier import DeviceClassifier


ANALOG_PG = {"PVDD3A", "PVDD3AC", "PVSS3A", "PVSS3AC"}
CUTS = {"PRCUT_G", "PRCUTA_G"}


def base_device(pad):
    return pad["device"].removesuffix("_V_G").removesuffix("_H_G")


def boundary(left, right):
    return FillerGenerator.get_filler_type(left, right)


def _spacers(pad, width):
    domain = VoltageDomainHandler.get_voltage_domain(pad)
    suffix = "A_G" if domain == "analog" else "_G"
    width = max(0, int(width))
    return [f"PFILLER20{suffix}"] * (width // 20) + [f"PFILLER10{suffix}"] * (
        (width % 20) // 10
    )


def _gap(left, right, width):
    device = boundary(left, right)
    if device not in CUTS:
        return _spacers(left, width)
    if width < 20:
        return _spacers(left, width)
    if device == "PRCUTA_G" and base_device(right) in ANALOG_PG:
        return _spacers(left, width - 20) + [device]
    return [device] + _spacers(right, width - 20)


def _corner_cuts(components, config):
    """Choose the end spacer that isolates two pad domains across each corner."""
    cuts = {}
    pads = {p["position"]: p for p in components if p.get("type") == "pad"}
    order = config.get("placement_order", "counterclockwise")
    width, height = config.get("width", 0), config.get("height", 0)
    for corner in (c for c in components if c.get("type") == "corner"):
        if corner["position"] not in {
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
        }:
            continue
        pos_a, pos_b = adjacent_pads(corner["position"], order, width, height)
        a, b = pads.get(pos_a), pads.get(pos_b)
        if not a or not b:
            continue
        cut = boundary(a, b)
        if cut not in CUTS:
            continue
        # The spacer on the other leg continues the corner master's buses.
        target = (
            pos_b
            if VoltageDomainHandler.get_voltage_domain(a)
            == VoltageDomainHandler.get_voltage_domain(corner)
            else pos_a
        )
        side, index = target.split("_")
        end = "start" if int(index) == 0 else "end"
        cuts[(side, end)] = cut
    return cuts


class AutoFillerGeneratorT28:
    def __init__(self, config):
        self.config = config

    def auto_insert_fillers_with_inner_pads(self, layout_components, inner_pads):
        if any(
            DeviceClassifier.is_filler_device(c["device"])
            or DeviceClassifier.is_separator_device(c["device"])
            for c in layout_components
        ):
            return layout_components + inner_pads
        if any(
            isinstance(pad.get("position"), (list, tuple))
            for pad in layout_components + inner_pads
        ):
            # Explicit physical placement takes precedence over generation from relative slots.
            return layout_components + inner_pads
        sides = defaultdict(list)
        for pad in layout_components:
            if pad.get("type") == "pad":
                side, index = pad["position"].split("_")
                sides[side].append((int(index), pad))
        inner_by_gap = {}
        for pad in inner_pads:
            side, i, j = pad["position"].split("_")
            key = (side, int(i))
            if int(j) != int(i) + 1 or key in inner_by_gap:
                return layout_components + inner_pads
            inner_by_gap[key] = pad

        cuts = _corner_cuts(layout_components, self.config)
        fillers = []
        for side, indexed in sides.items():
            indexed.sort(key=lambda item: item[0])
            # A 20 um end spacer preserves the published pad pitch and landing coordinates.
            sequence = []

            def add_spacer(device, name):
                filler = {"name": name, "type": "filler", "device": device}
                fillers.append(filler)
                sequence.append(filler)

            def add_end_spacers(pad, end):
                masters = _spacers(pad, 20)
                if (side, end) in cuts:
                    masters[0] = cuts[side, end]
                for k, device in enumerate(masters):
                    add_spacer(device, f"{side}_{end}_{k}")

            add_end_spacers(indexed[0][1], "start")
            for (i, left), (_, right) in zip(indexed, indexed[1:]):
                sequence.append(left)
                inner = inner_by_gap.pop((side, i), None)
                if inner:
                    # Original staggered pitch reserves equal spaces on both sides of the inner pad.
                    family = VoltageDomainHandler.get_voltage_domain(left)
                    same_family = family == VoltageDomainHandler.get_voltage_domain(right)
                    same_bus = VoltageDomainHandler.is_same_voltage_domain(
                        left, right, placement_pitch=True
                    )
                    flank_width = 10 if same_family and (same_bus or family == "unknown") else 20
                    parts = [
                        *_gap(left, inner, flank_width),
                        inner,
                        *_gap(inner, right, flank_width),
                    ]
                else:
                    parts = _gap(left, right, 40)
                for k, item in enumerate(parts):
                    if isinstance(item, str):
                        item = {
                            "name": f"{side}_{i}_mid_{k + 1}",
                            "type": "filler",
                            "device": item,
                        }
                        fillers.append(item)
                    sequence.append(item)
            sequence.append(indexed[-1][1])
            add_end_spacers(indexed[-1][1], "end")
            for index, component in enumerate(sequence):
                component["position"] = f"{side}_{index}"
        return layout_components + fillers + inner_pads
