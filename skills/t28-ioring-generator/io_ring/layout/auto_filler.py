"""Fill T28 pad gaps while preserving the side length and electrical boundaries."""

from collections import defaultdict

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
    if domain not in {"analog", "digital"}:
        raise ValueError(f"Unknown domain at {pad['position']}")
    suffix = "A_G" if domain == "analog" else "_G"
    if width < 0 or width % 10:
        raise ValueError(
            f"Cannot fill {width} um at {pad['position']} with T28 spacers"
        )
    return [f"PFILLER20{suffix}"] * (width // 20) + [f"PFILLER10{suffix}"] * (
        (width % 20) // 10
    )


def _gap(left, right, width):
    device = boundary(left, right)
    if device not in CUTS:
        return _spacers(left, width)
    if width < 20:
        raise ValueError(
            f"Cut needs 20 um between {left['position']} and {right['position']}"
        )
    if device == "PRCUTA_G" and base_device(right) in ANALOG_PG:
        return _spacers(left, width - 20) + [device]
    return [device] + _spacers(right, width - 20)


class AutoFillerGeneratorT28:
    def __init__(self, config):
        self.config = config

    def auto_insert_fillers_with_inner_pads(self, layout_components, inner_pads):
        if any(
            DeviceClassifier.is_filler_device(c["device"])
            or DeviceClassifier.is_separator_device(c["device"])
            for c in layout_components
        ):
            return layout_components
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
                raise ValueError(
                    f"Expected one inner pad in an adjacent gap at {pad['position']}"
                )
            inner_by_gap[key] = pad

        fillers = []
        for side, indexed in sides.items():
            indexed.sort(key=lambda item: item[0])
            if len(indexed) < 2:
                raise ValueError(f"{side} needs a bonded ground pad at each corner")
            sequence = []
            for n, ((i, left), (_, right)) in enumerate(zip(indexed, indexed[1:])):
                sequence.append(left)
                inner = inner_by_gap.pop((side, i), None)
                # Move the former 20 um corner spacers into the end gaps.
                # The first and last ground cells now abut their respective corners.
                extra_left = 20 if n == 0 else 0
                extra_right = 20 if n == len(indexed) - 2 else 0
                if inner:
                    before = boundary(left, inner) in CUTS
                    after = boundary(inner, right) in CUTS
                    left_width = 20 if before else 0 if after else 10
                    parts = [
                        *_gap(left, inner, left_width + extra_left),
                        inner,
                        *_gap(inner, right, 20 - left_width + extra_right),
                    ]
                else:
                    parts = _gap(left, right, 40 + extra_left + extra_right)
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
            for index, component in enumerate(sequence):
                component["position"] = f"{side}_{index}"
        if inner_by_gap:
            raise ValueError(
                f"Inner pad gaps without matching outer pads: {list(inner_by_gap)}"
            )
        return layout_components + fillers + inner_pads
