#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SKILL Script Generation Module for T28
"""

from typing import List, Dict, Any
from .device_classifier import DeviceClassifier
from .voltage_domain import VoltageDomainHandler
from .inner_pad_handler import InnerPadHandler
from .position_calculator import PositionCalculator
from .process_config import get_process_node_config

class SkillGeneratorT28:
    """SKILL Script Generator for T28 process node"""
    
    def __init__(self, config: dict):
        self.config = config
        self.inner_pad_handler = InnerPadHandler(config)
        self.position_calculator = PositionCalculator(config)
    
    def _format_core_label(self, signal_name: str) -> str:
        """Format signal name with _CORE suffix, handling <> notation correctly.
        
        For signals with <>, format as: PREFIX_CORE<INDEX>
        For regular signals, format as: SIGNAL_CORE
        
        Examples:
            SEL<0> -> SEL_CORE<0>
            VDD<1> -> VDD_CORE<1>
            VCM -> VCM_CORE
        """
        import re
        # Check if signal has <> notation
        match = re.match(r'^(.+?)(<.+>)$', signal_name)
        if match:
            prefix = match.group(1)
            index_part = match.group(2)
            return f"{prefix}_CORE{index_part}"
        else:
            return f"{signal_name}_CORE"
    
    def _get_skill_params(self, ring_config: dict) -> Dict[str, Any]:
        """Get skill parameters from config, with fallback to defaults"""
        process_config = get_process_node_config()
        skill_params = process_config.get("skill_params", {})
        
        # Default values if not in config
        defaults = {
            "layers": {
                "config_layer": "M3",
                "secondary_layer": "M3",
                "pin_layer": "AP",
                "core_label_layer": "M4"
            },
            "wire_widths": {
                "config_width": 0.2,
                "secondary_width": 0.2
            },
            "wire_offsets": {
                "vdd_wire_offset": 0.5,
                "gnd_wire_offset": -0.76
            },
            "via": {
                "via_def_name": "M3_M2",
                "via_params": {"cutRows": 2, "cutColumns": 4}
            },
            "pin_label_offsets": {
                "R0": {"x": 10, "y": -11},
                "R90": {"x": 11, "y": 10},
                "R180": {"x": -10, "y": 11},
                "R270": {"x": -11, "y": -10}
            }
        }
        
        # Merge with config values
        result = defaults.copy()
        if skill_params:
            if "layers" in skill_params:
                result["layers"].update(skill_params["layers"])
            if "wire_widths" in skill_params:
                result["wire_widths"].update(skill_params["wire_widths"])
            if "wire_offsets" in skill_params:
                result["wire_offsets"].update(skill_params["wire_offsets"])
            if "via" in skill_params:
                result["via"].update(skill_params["via"])
            if "pin_label_offsets" in skill_params:
                result["pin_label_offsets"].update(skill_params["pin_label_offsets"])
            if "via_offsets" in skill_params:
                result["via_offsets"] = skill_params["via_offsets"]
            if "secondary_offsets" in skill_params:
                result["secondary_offsets"] = skill_params["secondary_offsets"]
        
        return result
    
    def generate_digital_io_features_with_inner(self, outer_pads: List[dict], inner_pads: List[dict], ring_config: dict) -> List[str]:
        """Generate digital IO features (configuration lines + secondary lines + pin labels), supporting inner pads. Configuration lines cover all digital pads, secondary lines and pins only for digital IO."""
        skill_commands = []
        # Get process_node to determine layer names

        
        # Get skill parameters from config
        skill_params = self._get_skill_params(ring_config)
        config_layer = skill_params["layers"]["config_layer"]
        secondary_layer = skill_params["layers"]["secondary_layer"]
        config_width = skill_params["wire_widths"]["config_width"]
        secondary_width = skill_params["wire_widths"]["secondary_width"]
        
        # Get all digital pads (not distinguishing IO)
        all_digital_pads = self.inner_pad_handler.get_all_digital_pads_with_inner_any(outer_pads, inner_pads, ring_config)
        # Get all digital IO pads
        digital_io_pads = self.inner_pad_handler.get_all_digital_pads_with_inner(outer_pads, inner_pads, ring_config)
        if not all_digital_pads:
            return skill_commands

        # Configuration offsets for digital IO wires (from config)
        vdd_wire_offset = skill_params["wire_offsets"]["vdd_wire_offset"]
        gnd_wire_offset = skill_params["wire_offsets"]["gnd_wire_offset"]

        # Walk real pad neighbours clockwise. Each side interval ends at a domain cut,
        # even when the same domain reaches that side again after wrapping the ring.
        order = {"R180": (0, 0, 1), "R90": (1, 1, -1), "R0": (2, 0, -1), "R270": (3, 1, 1)}
        def clockwise_key(p):
            side, axis, sign = order[p["orientation"]]
            return side, sign * p["position"][axis]

        perimeter = sorted(outer_pads + inner_pads, key=clockwise_key)
        def rail_ends(p, offset):
            x, y = p["position"]
            w = p.get("pad_width", ring_config["pad_width"])
            h = ring_config["pad_height"] + offset
            return {"R180": ((x-w, y-h), (x, y-h)), "R90": ((x-h, y+w), (x-h, y)),
                    "R0": ((x+w, y+h), (x, y+h)), "R270": ((x+h, y-w), (x+h, y))}[p["orientation"]]

        def path(points):
            distinct = [point for j, point in enumerate(points) if j == 0 or points[j-1] != point]
            if len(distinct) >= 2:
                coords = " ".join(f"list({x} {y})" for x,y in distinct)
                skill_commands.append(f'dbCreatePath(cv list("{config_layer}" "drawing") list({coords}) {config_width})')

        for i, pad in enumerate(perimeter):
            if not DeviceClassifier.is_digital_device(pad["device"]):
                continue
            next_pad = perimeter[(i+1) % len(perimeter)]
            connected = (DeviceClassifier.is_digital_device(next_pad["device"])
                         and VoltageDomainHandler.is_same_voltage_domain(pad, next_pad))
            for offset in (vdd_wire_offset, gnd_wire_offset):
                start, end = rail_ends(pad, offset)
                points = [start, end]
                if connected:
                    target, _ = rail_ends(next_pad, offset)
                    if pad["orientation"] != next_pad["orientation"]:
                        if pad["orientation"] in {"R0", "R180"}:
                            points.append((target[0], end[1]))
                        else:
                            points.append((end[0], target[1]))
                    points.append(target)
                for first, last in zip(points, points[1:]):
                    path([first, last])

        # Secondary lines and pin labels only for digital IO pads
        offsets = skill_params.get("secondary_offsets", {"I": 1.725, "OEN": 5.9, "REN": 10.2, "C": 14.33})
        
        # Place vias and connect to configuration lines for digital power pads
        # Handle both outer and inner ring digital power pads (same treatment)
        # Only low-voltage digital power/ground pads need this treatment (PVDD1DGZ, PVSS1DGZ)
        for pad in all_digital_pads:
            device = pad["device"]
            # Only process low-voltage digital power/ground device types
            if device in ["PVDD1DGZ_V_G", "PVDD1DGZ_H_G", "PVSS1DGZ_V_G", "PVSS1DGZ_H_G", "PVSS3DGZ_V_G", "PVSS3DGZ_H_G"]:
                x, y = pad["position"]
                orient = pad["orientation"]
                
                # Get via offsets from config
                via_offsets = skill_params.get("via_offsets", {})
                via_y_offset = via_offsets.get("via_y_offset", 110.12)
                
                # Determine offset based on pad type
                if device.startswith("PVDD"):
                    offset = via_offsets.get("vdd_offset", 2.345)
                    is_vdd = True
                elif device.startswith("PVSS"):
                    offset = via_offsets.get("vss_offset", 2.39)
                    is_vdd = False
                else:
                    continue
                
                # Get wire offsets from config
                wire_offsets = skill_params["wire_offsets"]
                
                # Calculate via position (based on orientation)
                if orient == "R0":  # Bottom edge
                    via_x = x + offset
                    via_y = y + via_y_offset
                    # Configuration line y-coordinate (use wire offsets from config)
                    config_y = y + ring_config["pad_height"] + (wire_offsets["vdd_wire_offset"] if is_vdd else wire_offsets["gnd_wire_offset"])
                    config_x = via_x
                    # Draw line connecting via and configuration line
                    via_orientation = "R0"
                    skill_commands.append(f'dbCreatePath(cv list("{config_layer}" "drawing") list(list({via_x} {via_y}) list({config_x} {config_y})) {config_width})')
                elif orient == "R90":  # Right edge
                    via_x = x - via_y_offset
                    via_y = y + offset
                    wire_offsets = skill_params["wire_offsets"]
                    config_x = x - ring_config["pad_height"] + (-wire_offsets["vdd_wire_offset"] if is_vdd else abs(wire_offsets["gnd_wire_offset"]))
                    config_y = via_y
                    via_orientation = "R90"
                    skill_commands.append(f'dbCreatePath(cv list("{config_layer}" "drawing") list(list({via_x} {via_y}) list({config_x} {config_y})) {config_width})')
                elif orient == "R180":  # Top edge
                    via_x = x - offset
                    via_y = y - via_y_offset
                    wire_offsets = skill_params["wire_offsets"]
                    config_y = y - ring_config["pad_height"] + (-wire_offsets["vdd_wire_offset"] if is_vdd else abs(wire_offsets["gnd_wire_offset"]))
                    config_x = via_x
                    via_orientation = "R180"
                    skill_commands.append(f'dbCreatePath(cv list("{config_layer}" "drawing") list(list({via_x} {via_y}) list({config_x} {config_y})) {config_width})')
                elif orient == "R270":  # Left edge
                    via_x = x + via_y_offset
                    via_y = y - offset
                    wire_offsets = skill_params["wire_offsets"]
                    config_x = x + ring_config["pad_height"] + (wire_offsets["vdd_wire_offset"] if is_vdd else wire_offsets["gnd_wire_offset"])
                    config_y = via_y
                    via_orientation = "R270"
                    skill_commands.append(f'dbCreatePath(cv list("{config_layer}" "drawing") list(list({via_x} {via_y}) list({config_x} {config_y})) {config_width})')
                else:
                    continue
                
                # Place via (use process-specific via definition from config)
                skill_commands.append("tech = techGetTechFile(cv)")
                via_config = skill_params["via"]
                via_def_name = via_config["via_def_name"]
                via_params_dict = via_config["via_params"]
                viaParams = f'list(list("cutRows" {via_params_dict["cutRows"]}) list("cutColumns" {via_params_dict["cutColumns"]}))'
                skill_commands.append(f'viaParams = {viaParams}')
                skill_commands.append(f'viaDefId = techFindViaDefByName(tech "{via_def_name}")')
                skill_commands.append(f'newVia = dbCreateVia(cv viaDefId list({via_x} {via_y}) "{via_orientation}" viaParams)')
        
        # Secondary lines and pin labels only for digital IO pads (exclude digital power/ground pads)
        for pad in digital_io_pads:
            device = pad.get("device", "")
            # Skip low-voltage digital power/ground pads - they should not have secondary lines or pin labels
            # Digital power/ground pads are handled separately above with vias and configuration lines
            if device in ["PVDD1DGZ_V_G", "PVDD1DGZ_H_G", "PVSS1DGZ_V_G", "PVSS1DGZ_H_G", "PVSS3DGZ_V_G", "PVSS3DGZ_H_G"]:
                continue

            x, y = pad["position"]
            orient = pad["orientation"]
            is_input = pad["direction"] == "input"
            # PRUW08 input: both OEN and REN connect to VDD (high); PRUW08 output: same as PDDW16
            is_pruw08 = "PRUW08" in device

            if orient == "R0":  # Bottom edge pad
                base_y = y + ring_config["pad_height"] - 0.125
                high_y = y + ring_config["pad_height"] + 0.5
                low_y = y + ring_config["pad_height"] - 0.76

                # Create secondary line (use secondary_layer for 180nm, config_layer for 28nm)
                secondary_wire_width = 0.26
                if is_input:
                    # Both PDDW16 and PRUW08 input: OEN→high; PRUW08 input: REN→high (VDD), PDDW16 input: REN→low (VSS)
                    if is_pruw08:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x + offsets["REN"]} {base_y}) list({x + offsets["REN"]} {high_y})) {secondary_wire_width})')
                    else:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x + offsets["REN"]} {base_y}) list({x + offsets["REN"]} {low_y})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x + offsets["I"]} {base_y}) list({x + offsets["I"]} {low_y})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x + offsets["OEN"]} {base_y}) list({x + offsets["OEN"]} {high_y})) {secondary_wire_width})')
                    pin_pos = f"list({x + offsets['C']} {base_y})"
                else:
                    # Both PDDW16 and PRUW08 output: REN→high, OEN→low
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x + offsets["REN"]} {base_y}) list({x + offsets["REN"]} {high_y})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x + offsets["OEN"]} {base_y}) list({x + offsets["OEN"]} {low_y})) {secondary_wire_width})')
                    pin_pos = f"list({x + offsets['I']} {base_y})"

                # Create pin label
                core_label = self._format_core_label(pad["name"])
                skill_commands.append(f'dbCreateLabel(cv list("M4" "pin") {pin_pos} "{core_label}" "centerLeft" "R90" "roman" 2)')

            elif orient == "R90":  # Right edge pad
                base_x = x - ring_config["pad_height"] + 0.125
                high_x = x - ring_config["pad_height"] - 0.5
                low_x = x - ring_config["pad_height"] + 0.76

                # Create secondary line
                secondary_wire_width = 0.26
                if is_input:
                    # Both PDDW16 and PRUW08 input: OEN→high; PRUW08 input: REN→high, PDDW16 input: REN→low
                    if is_pruw08:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({high_x} {y + offsets["REN"]}) list({base_x} {y + offsets["REN"]})) {secondary_wire_width})')
                    else:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({low_x} {y + offsets["REN"]}) list({base_x} {y + offsets["REN"]})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({low_x} {y + offsets["I"]}) list({base_x} {y + offsets["I"]})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({high_x} {y + offsets["OEN"]}) list({base_x} {y + offsets["OEN"]})) {secondary_wire_width})')
                    pin_pos = f"list({base_x} {y + offsets['C']})"
                else:
                    # Both PDDW16 and PRUW08 output: REN→high, OEN→low
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({high_x} {y + offsets["REN"]}) list({base_x} {y + offsets["REN"]})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({low_x} {y + offsets["OEN"]}) list({base_x} {y + offsets["OEN"]})) {secondary_wire_width})')
                    pin_pos = f"list({base_x} {y + offsets['I']})"

                # Create pin label
                core_label = self._format_core_label(pad["name"])
                skill_commands.append(f'dbCreateLabel(cv list("M4" "pin") {pin_pos} "{core_label}" "centerRight" "R0" "roman" 2)')

            elif orient == "R180":  # Top edge pad
                base_y = y - ring_config["pad_height"] + 0.125
                high_y = y - ring_config["pad_height"] - 0.5
                low_y = y - ring_config["pad_height"] + 0.76

                # Create secondary line
                secondary_wire_width = 0.26
                if is_input:
                    # Both PDDW16 and PRUW08 input: OEN→high; PRUW08 input: REN→high, PDDW16 input: REN→low
                    if is_pruw08:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x - offsets["REN"]} {base_y}) list({x - offsets["REN"]} {high_y})) {secondary_wire_width})')
                    else:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x - offsets["REN"]} {base_y}) list({x - offsets["REN"]} {low_y})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x - offsets["I"]} {base_y}) list({x - offsets["I"]} {low_y})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x - offsets["OEN"]} {base_y}) list({x - offsets["OEN"]} {high_y})) {secondary_wire_width})')
                    pin_pos = f"list({x - offsets['C']} {base_y})"
                else:
                    # Both PDDW16 and PRUW08 output: REN→high, OEN→low
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x - offsets["REN"]} {base_y}) list({x - offsets["REN"]} {high_y})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({x - offsets["OEN"]} {base_y}) list({x - offsets["OEN"]} {low_y})) {secondary_wire_width})')
                    pin_pos = f"list({x - offsets['I']} {base_y})"

                # Create pin label
                core_label = self._format_core_label(pad["name"])
                skill_commands.append(f'dbCreateLabel(cv list("M4" "pin") {pin_pos} "{core_label}" "centerRight" "R90" "roman" 2)')

            elif orient == "R270":  # Left edge pad
                base_x = x + ring_config["pad_height"] - 0.125
                high_x = x + ring_config["pad_height"] + 0.5
                low_x = x + ring_config["pad_height"] - 0.76

                # Create secondary line
                secondary_wire_width = 0.26
                if is_input:
                    # Both PDDW16 and PRUW08 input: OEN→high; PRUW08 input: REN→high, PDDW16 input: REN→low
                    if is_pruw08:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({base_x} {y - offsets["REN"]}) list({high_x} {y - offsets["REN"]})) {secondary_wire_width})')
                    else:
                        skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({base_x} {y - offsets["REN"]}) list({low_x} {y - offsets["REN"]})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({base_x} {y - offsets["I"]}) list({low_x} {y - offsets["I"]})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({base_x} {y - offsets["OEN"]}) list({high_x} {y - offsets["OEN"]})) {secondary_wire_width})')
                    pin_pos = f"list({base_x} {y - offsets['C']})"
                else:
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({base_x} {y - offsets["REN"]}) list({high_x} {y - offsets["REN"]})) {secondary_wire_width})')
                    skill_commands.append(f'dbCreatePath(cv list("{secondary_layer}" "drawing") list(list({base_x} {y - offsets["OEN"]}) list({low_x} {y - offsets["OEN"]})) {secondary_wire_width})')
                    pin_pos = f"list({base_x} {y - offsets['I']})"

                # Create pin label
                core_label = self._format_core_label(pad["name"])
                skill_commands.append(f'dbCreateLabel(cv list("M4" "pin") {pin_pos} "{core_label}" "centerLeft" "R0" "roman" 2)')

        return skill_commands
    
    def generate_pin_labels_with_inner(self, outer_pads: List[dict], inner_pads: List[dict], ring_config: dict) -> List[str]:
        """Generate main pin labels, supporting inner pads"""
        skill_commands = []
        
        # Main pin labels for outer pads
        skill_params = self._get_skill_params( ring_config)
        pin_layer = skill_params["layers"]["pin_layer"]
        pin_offsets = skill_params["pin_label_offsets"]
        
        for pad in outer_pads:
            x, y = pad["position"]
            orient = pad["orientation"]
            name = pad["name"]
            device = pad.get("device", "")
            
            # Calculate pin label position from config
            offset = pin_offsets.get(orient, {"x": 0, "y": 0})
            pin_pos = f'list({x + offset["x"]} {y + offset["y"]})'
            
            # Justification and orientation mapping
            if orient == "R0":  # bottom edge pad
                justification, pin_orient = "centerRight", "R90"
            elif orient == "R90":  # right edge pad
                justification, pin_orient = "centerLeft", "R0"
            elif orient == "R180":  # top edge pad
                justification, pin_orient = "centerLeft", "R90"
            elif orient == "R270":  # left edge pad
                justification, pin_orient = "centerRight", "R0"
            else:
                justification, pin_orient = "centerLeft", "R0"
            
            if pad.get("bonded", True):
                skill_commands.append(f'dbCreateLabel(cv list("{pin_layer}" "pin") {pin_pos} "{name}" "{justification}" "{pin_orient}" "roman" 10)')
            
            # Create core label for voltage domain components
            if VoltageDomainHandler.is_voltage_domain_provider(pad):
                # Calculate core label position (within the pad)
                if orient == "R0":
                    core_pos = f'list({x + 10} {y + ring_config["pad_height"] - 0.1})'
                    core_just, core_orient = "centerLeft", "R90"
                elif orient == "R90":
                    core_pos = f'list({x - ring_config["pad_height"] + 0.1} {y + 10})'
                    core_just, core_orient = "centerRight", "R0"
                elif orient == "R180":
                    core_pos = f'list({x - 10} {y - ring_config["pad_height"] + 0.1})'
                    core_just, core_orient = "centerRight", "R90"
                elif orient == "R270":
                    core_pos = f'list({x + ring_config["pad_height"] - 0.1} {y - 10})'
                    core_just, core_orient = "centerLeft", "R0"
                
                core_label = self._format_core_label(name)
                skill_commands.append(f'dbCreateLabel(cv list("M2" "pin") {core_pos} "{core_label}" "{core_just}" "{core_orient}" "roman" 2)')
        
        # Main pin labels for inner pads (move 152 units inward, opposite direction)
        for inner_pad in inner_pads:
            # If position is already absolute coordinates, use directly
            if isinstance(inner_pad["position"], list):
                position = inner_pad["position"]
                orient = inner_pad["orientation"]
            else:
                # Otherwise, recalculate position
                position, orient = self.inner_pad_handler.calculate_inner_pad_position(inner_pad["position"], outer_pads, ring_config)
            
            x, y = position
            name = inner_pad["name"]
            device = inner_pad.get("device", "")
            
            # Calculate pin label position for inner pads (move inward) and direction (opposite to outer)
            if orient == "R0":  # Bottom edge inner pad
                pin_pos = f'list({x + 10} {y + 152})'  # Move inward (up)
                justification, pin_orient = "centerLeft", "R90"  # Opposite direction
            elif orient == "R90":  # Right edge inner pad
                pin_pos = f'list({x - 152} {y + 10})'  # Move inward (left)
                justification, pin_orient = "centerRight", "R0"  # Opposite direction
            elif orient == "R180":  # Top edge inner pad
                pin_pos = f'list({x - 10} {y - 152})'  # Move inward (down)
                justification, pin_orient = "centerRight", "R90"  # Opposite direction
            elif orient == "R270":  # Left edge inner pad
                pin_pos = f'list({x + 152} {y - 10})'  # Move inward (right)
                justification, pin_orient = "centerLeft", "R0"  # Opposite direction
            
            if pad.get("bonded", True):
                skill_commands.append(f'dbCreateLabel(cv list("AP" "pin") {pin_pos} "{name}" "{justification}" "{pin_orient}" "roman" 10)')
            
            # Create core label for inner pad voltage domain components
            if VoltageDomainHandler.is_voltage_domain_provider(inner_pad):
                # Calculate core label position for inner pads (within the pad, opposite to outer)
                if orient == "R0":  # Bottom edge inner pad
                    core_pos = f'list({x + 10} {y + ring_config["pad_height"] - 0.1})'
                    core_just, core_orient = "centerLeft", "R90"
                elif orient == "R90":  # Right edge inner pad
                    core_pos = f'list({x - ring_config["pad_height"] + 0.1} {y + 10})'
                    core_just, core_orient = "centerRight", "R0"
                elif orient == "R180":  # Top edge inner pad
                    core_pos = f'list({x - 10} {y - ring_config["pad_height"] + 0.1})'
                    core_just, core_orient = "centerRight", "R90"
                elif orient == "R270":  # Left edge inner pad
                    core_pos = f'list({x + ring_config["pad_height"] - 0.1} {y - 10})'
                    core_just, core_orient = "centerLeft", "R0"
                
                core_label = self._format_core_label(name)
                skill_commands.append(f'dbCreateLabel(cv list("M2" "pin") {core_pos} "{core_label}" "{core_just}" "{core_orient}" "roman" 2)')
        
        return skill_commands