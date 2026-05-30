#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Filler Component Generation Module for T28
"""

from typing import List
from .device_classifier import DeviceClassifier
from .voltage_domain import VoltageDomainHandler
from .filler_generator import FillerGenerator
from .position_calculator import PositionCalculator
from .inner_pad_handler import InnerPadHandler
from .process_config import get_process_node_config


class AutoFillerGeneratorT28:
    """Auto Filler Component Generator for T28 process node"""
    
    def __init__(self, config: dict):
        self.config = config
        self.position_calculator = PositionCalculator(config)
        self.inner_pad_handler = InnerPadHandler(config)
    
    def auto_insert_fillers_with_inner_pads(self, layout_components: List[dict], inner_pads: List[dict]) -> List[dict]:
        """Auto-insert filler components for 28nm, supporting inner pad space reservation, compatible with clockwise and counterclockwise placement"""
        process_node = self.config.get("process_node", "T28")
        
        # Check if filler components are already included
        existing_fillers = [comp for comp in layout_components if comp.get("type") == "filler" or DeviceClassifier.is_filler_device(comp.get("device", ""))]
        existing_separators = [comp for comp in layout_components if comp.get("type") == "separator" or DeviceClassifier.is_separator_device(comp.get("device", ""))]
        
        if existing_fillers or existing_separators:
            print(f"[--] Detected filler components in intent graph: {len(existing_fillers)} fillers, {len(existing_separators)} separators")
            print("[--] Skipping auto-filler generation, using components defined in intent graph")
            return layout_components
        
        # Get placement order
        placement_order = self.config.get("placement_order", "counterclockwise")
               
        fillers = []

        def create_filler(name: str, device: str) -> dict:
            return {
                "type": "filler",
                "name": name,
                "device": device,
                "position": "",
            }
        
        def parse_relative_position(value):
            if not isinstance(value, str):
                return None, None
            if value in ("top_left", "top_right", "bottom_left", "bottom_right"):
                return "corner", None
            parts = value.split("_")
            if len(parts) == 2 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit():
                return parts[0], int(parts[1])
            return None, None

        def infer_orientation_from_position(component: dict):
            side, _ = parse_relative_position(component.get("position"))
            if side == "top":
                return "R180"
            if side == "right":
                return "R90"
            if side == "bottom":
                return "R0"
            if side == "left":
                return "R270"
            return ""
            
        def get_adjacent_pads_for_corner(oriented_pads, corner_orientation, placement_order: str = "clockwise") -> str:
            """Get corner domain based on the two pads around the corner.

            If the two adjacent pads share the same domain, return that domain;
            otherwise, default to "analog". If either pad is missing, also
            default to "analog".
            """
            pad1 = None
            pad2 = None
            is_clockwise = str(placement_order).lower() == "clockwise"

            if is_clockwise:
                # Start-corner mapping for clockwise indices:
                # top->TL, right->TR, bottom->BR, left->BL
                if corner_orientation == "R180":  # Top edge
                    left_pads = oriented_pads.get("R270", [])
                    top_pads = oriented_pads.get("R180", [])
                    pad1 = left_pads[-1] if left_pads else None
                    pad2 = top_pads[0] if top_pads else None
                elif corner_orientation == "R90":  # Right edge
                    top_pads = oriented_pads.get("R180", [])
                    right_pads = oriented_pads.get("R90", [])
                    pad1 = top_pads[-1] if top_pads else None
                    pad2 = right_pads[0] if right_pads else None
                elif corner_orientation == "R0":  # Bottom edge
                    right_pads = oriented_pads.get("R90", [])
                    bottom_pads = oriented_pads.get("R0", [])
                    pad1 = right_pads[-1] if right_pads else None
                    pad2 = bottom_pads[0] if bottom_pads else None
                elif corner_orientation == "R270":  # Left edge
                    bottom_pads = oriented_pads.get("R0", [])
                    left_pads = oriented_pads.get("R270", [])
                    pad1 = bottom_pads[-1] if bottom_pads else None
                    pad2 = left_pads[0] if left_pads else None
            else:
                # Start-corner mapping for counterclockwise indices:
                # top->TR, right->BR, bottom->BL, left->TL
                if corner_orientation == "R180":  # Top edge
                    top_pads = oriented_pads.get("R180", [])
                    right_pads = oriented_pads.get("R90", [])
                    pad1 = top_pads[0] if top_pads else None
                    pad2 = right_pads[-1] if right_pads else None
                elif corner_orientation == "R90":  # Right edge
                    right_pads = oriented_pads.get("R90", [])
                    bottom_pads = oriented_pads.get("R0", [])
                    pad1 = right_pads[0] if right_pads else None
                    pad2 = bottom_pads[-1] if bottom_pads else None
                elif corner_orientation == "R0":  # Bottom edge
                    bottom_pads = oriented_pads.get("R0", [])
                    left_pads = oriented_pads.get("R270", [])
                    pad1 = bottom_pads[0] if bottom_pads else None
                    pad2 = left_pads[-1] if left_pads else None
                elif corner_orientation == "R270":  # Left edge
                    left_pads = oriented_pads.get("R270", [])
                    top_pads = oriented_pads.get("R180", [])
                    pad1 = left_pads[0] if left_pads else None
                    pad2 = top_pads[-1] if top_pads else None
            if pad1 and pad2:
                return (pad1, pad2)
            else:
                return (None, None)

        def get_adjacent_pads_for_end_corner(oriented_pads, corner_orientation, placement_order: str = "clockwise"):
            """Get the two pads adjacent to the end corner of the current side sequence."""
            pad1 = None
            pad2 = None
            is_clockwise = str(placement_order).lower() == "clockwise"

            if is_clockwise:
                if corner_orientation == "R180":  # Top side end -> top-right corner
                    top_pads = oriented_pads.get("R180", [])
                    right_pads = oriented_pads.get("R90", [])
                    pad1 = top_pads[-1] if top_pads else None
                    pad2 = right_pads[0] if right_pads else None
                elif corner_orientation == "R90":  # Right side end -> bottom-right corner
                    right_pads = oriented_pads.get("R90", [])
                    bottom_pads = oriented_pads.get("R0", [])
                    pad1 = right_pads[-1] if right_pads else None
                    pad2 = bottom_pads[0] if bottom_pads else None
                elif corner_orientation == "R0":  # Bottom side end -> bottom-left corner
                    bottom_pads = oriented_pads.get("R0", [])
                    left_pads = oriented_pads.get("R270", [])
                    pad1 = bottom_pads[-1] if bottom_pads else None
                    pad2 = left_pads[0] if left_pads else None
                elif corner_orientation == "R270":  # Left side end -> top-left corner
                    left_pads = oriented_pads.get("R270", [])
                    top_pads = oriented_pads.get("R180", [])
                    pad1 = left_pads[-1] if left_pads else None
                    pad2 = top_pads[0] if top_pads else None
            else:
                if corner_orientation == "R180":  # Top side end -> top-left corner
                    top_pads = oriented_pads.get("R180", [])
                    left_pads = oriented_pads.get("R270", [])
                    pad1 = top_pads[-1] if top_pads else None
                    pad2 = left_pads[0] if left_pads else None
                elif corner_orientation == "R90":  # Right side end -> top-right corner
                    right_pads = oriented_pads.get("R90", [])
                    top_pads = oriented_pads.get("R180", [])
                    pad1 = right_pads[-1] if right_pads else None
                    pad2 = top_pads[0] if top_pads else None
                elif corner_orientation == "R0":  # Bottom side end -> bottom-right corner
                    bottom_pads = oriented_pads.get("R0", [])
                    right_pads = oriented_pads.get("R90", [])
                    pad1 = bottom_pads[-1] if bottom_pads else None
                    pad2 = right_pads[0] if right_pads else None
                elif corner_orientation == "R270":  # Left side end -> bottom-left corner
                    left_pads = oriented_pads.get("R270", [])
                    bottom_pads = oriented_pads.get("R0", [])
                    pad1 = left_pads[-1] if left_pads else None
                    pad2 = bottom_pads[0] if bottom_pads else None

            if pad1 and pad2:
                return (pad1, pad2)
            return (None, None)
        # Separate pads and corners
        pads = [comp for comp in layout_components if comp.get("type") == "pad"]
        corners = [comp for comp in layout_components if comp.get("type") == "corner"]
        
        # Group pads by orientation
        oriented_pads = {"R0": [], "R90": [], "R180": [], "R270": []}
        for pad in pads:
            orientation = pad.get("orientation", "")
            if orientation not in oriented_pads:
                orientation = infer_orientation_from_position(pad)
            if orientation in oriented_pads:
                oriented_pads[orientation].append(pad)
        
        for orientation, pad_list in oriented_pads.items():
            if not pad_list:
                continue

            oriented_pads[orientation] = sorted(
                pad_list,
                key=lambda p: (
                    parse_relative_position(p.get("position"))[1]
                ),
            )

        # Process each orientation's pads
        for orientation, pad_list in oriented_pads.items():
            if not pad_list:
                continue
            
            # 1. Filler between corner and first pad (28nm only)
            # if orientation == "R180":  # Top edge
            #     # Between top-left corner and first pad
            #     first_pad = pad_list[0]
            #     x = first_pad["position"][0] - pad_width
                # y = chip_height  # 28nm: filler on top edge, not chip_height - pad_height
            # start_Filler/PCUTTER
            side = {
                    "R180": "top",
                    "R90": "right",
                    "R0": "bottom",
                    "R270": "left",
                }.get(orientation)

            side_components = []
            pad1, pad2 = get_adjacent_pads_for_corner(oriented_pads, orientation, placement_order)
            filler_type = FillerGenerator.get_filler_type_for_corner_and_pad("PCORNERA_G", pad1, pad2)
            start_filler = create_filler(f"filler_{side}_corner_1", filler_type)
            fillers.append(start_filler)
            side_components.append(start_filler)
            
            # 2. Filler between pads
            for i in range(len(pad_list) - 1):
                curr_pad = pad_list[i]
                side_components.append(curr_pad)
                next_pad = pad_list[i + 1]
                               
                # 28nm: Use original logic with 2 fillers
                curr_index = parse_relative_position(curr_pad.get("position"))[1]
                next_index = parse_relative_position(next_pad.get("position"))[1]

                matched_inner_pads = []
                if side is not None and curr_index is not None and next_index is not None:
                    matched_inner_pads = self.inner_pad_handler.get_inner_pads_for_gap(
                        side,
                        curr_index,
                        next_index,
                        inner_pads,
                        pads,
                    )
                
                if matched_inner_pads:
                    # Reserve space for inner pad, use 10 unit filler
                    filler_type = FillerGenerator.get_filler_type(curr_pad, next_pad)
                    
                    # If in the same voltage domain, use 10 unit filler
                    if VoltageDomainHandler.get_voltage_domain(curr_pad) == VoltageDomainHandler.get_voltage_domain(next_pad):
                        if "PFILLER" in filler_type:
                            # Replace 20 unit filler with 10 unit
                            filler_type = filler_type.replace("PFILLER20", "PFILLER10")
                    
                    mid_filler_inner1 = create_filler(f"{side}_{i}_mid_1", filler_type)
                    fillers.append(mid_filler_inner1)
                    side_components.append(mid_filler_inner1)
                    side_components.append(matched_inner_pads[0])
                    mid_filler_inner2 = create_filler(f"{side}_{i}_mid_2", filler_type)
                    fillers.append(mid_filler_inner2)
                    side_components.append(mid_filler_inner2)

                else:
                    # Normal spacing, use 20 unit filler
                    filler_type = FillerGenerator.get_filler_type(curr_pad, next_pad)
                    
                    # Insert two 20 unit fillers
                    mid_filler_1 = create_filler(f"{side}_{i}_mid_1", filler_type)
                    fillers.append(mid_filler_1)
                    side_components.append(mid_filler_1)

                    mid_filler_2 = create_filler(f"{side}_{i}_mid_2", filler_type)
                    fillers.append(mid_filler_2)
                    side_components.append(mid_filler_2)

            if pad_list:
                side_components.append(pad_list[-1])
            # 3. Filler between last pad and corner
            end_pad1, end_pad2 = get_adjacent_pads_for_end_corner(oriented_pads, orientation, placement_order)
            end_filler_type = FillerGenerator.get_filler_type_for_corner_and_pad("PCORNERA_G", end_pad1, end_pad2)
            end_filler = create_filler(f"filler_{side}_corner_2", end_filler_type)
            fillers.append(end_filler)
            side_components.append(end_filler)   
            for i, component in enumerate(side_components):
                # Update position to be sequential: side_0, side_1, side_2...
                new_pos = f"{side}_{i}"
                component["position"] = new_pos 
        
        return layout_components + fillers + inner_pads

