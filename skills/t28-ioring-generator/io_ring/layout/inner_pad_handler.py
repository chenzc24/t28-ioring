#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inner Pad Processing Module
"""

from typing import List, Tuple
from .device_classifier import DeviceClassifier
from .position_calculator import PositionCalculator

class InnerPadHandler:
    """Inner Pad Handler"""
    
    def __init__(self, config: dict):
        self.config = config
        self.position_calculator = PositionCalculator(config)
    
    def sanitize_skill_instance_name(self, name: str) -> str:
        """
        Sanitize instance names for SKILL compatibility.
        Replace < > with _ (underscore) for instance names.
        
        Args:
            name: Original instance name
            
        Returns:
            Sanitized instance name safe for SKILL
        """
        # Replace < > with _ (underscore) for SKILL instance name compatibility
        sanitized = name.replace('<', '_').replace('>', '_')
        # Collapse multiple consecutive underscores into a single underscore
        while '__' in sanitized:
            sanitized = sanitized.replace('__', '_')
        return sanitized
    
    def calculate_inner_pad_position(self, position_str: str, outer_pads: List[dict], ring_config: dict) -> tuple:
        """Calculate inner pad position and orientation, supporting clockwise/counterclockwise"""
        parts = position_str.split('_')
        if len(parts) != 3:
            raise ValueError(f"Invalid inner pad position format: {position_str}")
        side = parts[0]  # top, bottom, left, right
        pad1_index = int(parts[1])
        pad2_index = int(parts[2])
        placement_order = ring_config.get("placement_order", "counterclockwise")

        # Calculate pad count per side
        width = ring_config.get("width", 3)
        height = ring_config.get("height", 3)
        side_pad_count = {
            "top": width,
            "bottom": width,
            "left": height,
            "right": height
        }
        N = side_pad_count.get(side, 0)
        if placement_order == "clockwise":
            real_pad1_index = pad1_index
            real_pad2_index = pad2_index
        else:
            real_pad1_index = (N - 1) - pad1_index
            real_pad2_index = (N - 1) - pad2_index

        # Sort outer pads by placement order
        sorted_outer_pads = self.position_calculator.sort_components_by_position(outer_pads, placement_order)
        
        # Determine pad starting index based on placement order
        if placement_order == "clockwise":
            # Clockwise: Top-left -> Top edge -> Top-right -> Right edge -> Bottom-right -> Bottom edge -> Bottom-left -> Left edge
            side_start_indices = {
                "top": 0,
                "right": len([p for p in sorted_outer_pads if p["orientation"] == "R180"]),
                "bottom": len([p for p in sorted_outer_pads if p["orientation"] == "R180"]) + len([p for p in sorted_outer_pads if p["orientation"] == "R90"]),
                "left": len([p for p in sorted_outer_pads if p["orientation"] == "R180"]) + len([p for p in sorted_outer_pads if p["orientation"] == "R90"]) + len([p for p in sorted_outer_pads if p["orientation"] == "R0"])
            }
        else:
            # Counterclockwise: Top-left -> Left edge -> Bottom-left -> Bottom edge -> Bottom-right -> Right edge -> Top-right -> Top edge
            side_start_indices = {
                "left": 0,
                "bottom": len([p for p in sorted_outer_pads if p["orientation"] == "R270"]),
                "right": len([p for p in sorted_outer_pads if p["orientation"] == "R270"]) + len([p for p in sorted_outer_pads if p["orientation"] == "R0"]),
                "top": len([p for p in sorted_outer_pads if p["orientation"] == "R270"]) + len([p for p in sorted_outer_pads if p["orientation"] == "R0"]) + len([p for p in sorted_outer_pads if p["orientation"] == "R90"])
            }
        
        if side not in side_start_indices:
            raise ValueError(f"Invalid side: {side}")
        start_index = side_start_indices[side]
        pad1_global_index = start_index + real_pad1_index
        pad2_global_index = start_index + real_pad2_index

        # Get positions of two outer pads
        pad1 = sorted_outer_pads[pad1_global_index]
        pad2 = sorted_outer_pads[pad2_global_index]

        # Calculate middle position
        x1, y1 = pad1["position"]
        x2, y2 = pad2["position"]
        orientation = pad1["orientation"]

        # Calculate middle position based on orientation
        if orientation == "R180":  # Top edge
            x = (x1 + x2) // 2
            y = y1
        elif orientation == "R0":  # Bottom edge
            x = (x1 + x2) // 2
            y = y1
        elif orientation == "R90":  # Right edge
            x = x1
            y = (y1 + y2) // 2
        elif orientation == "R270":  # Left edge
            x = x1
            y = (y1 + y2) // 2
        else:
            raise ValueError(f"Invalid orientation: {orientation}")

        return ([x, y], orientation)
    
    def generate_inner_pad_skill_commands(self, inner_pads: List[dict], outer_pads: List[dict], ring_config: dict) -> List[str]:
        """Generate SKILL commands for inner pads"""
        skill_commands = []
        
        for i, inner_pad in enumerate(inner_pads):
            name = inner_pad["name"]
            device = inner_pad["device"]
            
            # If position is already absolute coordinates, use directly
            if isinstance(inner_pad["position"], list):
                position = inner_pad["position"]
                orientation = inner_pad["orientation"]
            else:
                # Otherwise, recalculate position
                position_str = inner_pad["position"]
                position, orientation = self.calculate_inner_pad_position(position_str, outer_pads, ring_config)
            
            x, y = position
            position_str = inner_pad["position_str"]
            # Generate SKILL commands for inner pads
            device_masters = ring_config.get("device_masters", {})
            library_name = ring_config.get("library_name", device_masters.get("default_library", "tphn28hpcpgv18"))
            pad_library = device_masters.get("pad_library", "PAD")
            pad60nu_master = device_masters.get("pad60nu_master", "PAD60NU")
            view_name = ring_config.get("view_name", "layout")
            # Sanitize instance names for SKILL compatibility (replace < > with _)
            sanitized_name = self.sanitize_skill_instance_name(f"inner_pad_{name}_{position_str}")
            sanitized_pad_name = self.sanitize_skill_instance_name(f"inner_pad60nu_{name}_{position_str}")
            skill_commands.append(f'dbCreateParamInstByMasterName(cv "{library_name}" "{device}" "{view_name}" "{sanitized_name}" list({x} {y}) "{orientation}")')
            skill_commands.append(f'dbCreateParamInstByMasterName(cv "{pad_library}" "{pad60nu_master}" "layout" "{sanitized_pad_name}" list({x} {y}) "{orientation}")')
        
        return skill_commands
    
    def get_all_digital_pads_with_inner(self, outer_pads: List[dict], inner_pads: List[dict], ring_config: dict) -> List[dict]:
        """Get all digital IO pad information (including outer and inner rings)"""
        digital_pads = []

        # Outer ring digital IO pads
        for pad in outer_pads:
            if DeviceClassifier.is_digital_io_device(pad["device"]):
                digital_pads.append({
                    "position": pad["position"],
                    "orientation": pad["orientation"],
                    "name": pad["name"],
                    "device": pad["device"],
                    "direction": pad.get("direction", "unknown"),
                    "is_inner": False
                })

        # Inner ring digital IO pads
        for inner_pad in inner_pads:
            if DeviceClassifier.is_digital_io_device(inner_pad["device"]):
                # If position is already absolute coordinates, use directly
                if isinstance(inner_pad["position"], list):
                    position = inner_pad["position"]
                    orientation = inner_pad["orientation"]
                else:
                    # Otherwise, recalculate position
                    position, orientation = self.calculate_inner_pad_position(inner_pad["position"], outer_pads, ring_config)

                digital_pads.append({
                    "position": position,
                    "orientation": orientation,
                    "name": inner_pad["name"],
                    "device": inner_pad["device"],
                    "direction": inner_pad.get("direction", "unknown"),
                    "is_inner": True
                })

        return digital_pads
    
    def get_all_digital_pads_with_inner_any(self, outer_pads: List[dict], inner_pads: List[dict], ring_config: dict) -> List[dict]:
        """Get all digital pad information (including outer and inner rings, all digital pads, not limited to IO)"""
        digital_pads = []

        # Outer ring digital pads
        for pad in outer_pads:
            if DeviceClassifier.is_digital_device(pad["device"]):
                digital_pads.append({
                    "position": pad["position"],
                    "orientation": pad["orientation"],
                    "name": pad["name"],
                    "device": pad["device"],
                    "direction": pad.get("direction", "unknown"),
                    "domain": pad.get("domain", ""),
                    "is_inner": False
                })

        # Inner ring digital pads
        for inner_pad in inner_pads:
            if DeviceClassifier.is_digital_device(inner_pad["device"]):
                if isinstance(inner_pad["position"], list):
                    position = inner_pad["position"]
                    orientation = inner_pad["orientation"]
                else:
                    position, orientation = self.calculate_inner_pad_position(inner_pad["position"], outer_pads, ring_config)
                digital_pads.append({
                    "position": position,
                    "orientation": orientation,
                    "name": inner_pad["name"],
                    "device": inner_pad["device"],
                    "direction": inner_pad.get("direction", "unknown"),
                    "domain": inner_pad.get("domain", ""),
                    "is_inner": True
                })

        return digital_pads
    
    def get_inner_pad_gap_indices(self, inner_pads: List[dict], outer_pads: List[dict]) -> List[tuple]:
        """Get (side, i, j, inner_pad) tuples for inner-pad gaps based on relative positions."""
        _ = outer_pads
        gap_pairs = []

        for inner_pad in inner_pads:
            position_str = inner_pad.get("position_str", "")
            if not position_str and isinstance(inner_pad.get("position"), str):
                position_str = inner_pad.get("position")

            if not position_str or not isinstance(position_str, str):
                continue

            parts = position_str.split("_")
            if len(parts) != 3:
                continue

            side = parts[0]
            if side not in {"top", "right", "bottom", "left"}:
                continue

            if not parts[1].isdigit() or not parts[2].isdigit():
                continue

            pad1_index = int(parts[1])
            pad2_index = int(parts[2])
            gap_pairs.append((side, pad1_index, pad2_index, inner_pad))

        return gap_pairs

    def get_inner_pads_for_gap(self, side: str, index1: int, index2: int, inner_pads: List[dict], outer_pads: List[dict]) -> List[dict]:
        """Return inner pad records whose gap matches side/index pair (order-insensitive)."""
        matches = []
        for gap_side, pad1, pad2, inner_pad in self.get_inner_pad_gap_indices(inner_pads, outer_pads):
            if gap_side != side:
                continue
            if (pad1 == index1 and pad2 == index2) or (pad1 == index2 and pad2 == index1):
                matches.append(inner_pad)
        return matches

    def is_inner_pad_gap_by_side_indices(self, side: str, index1: int, index2: int, inner_pads: List[dict], outer_pads: List[dict]) -> bool:
        """Check whether there is an inner-pad gap between two side-local pad indices."""
        return bool(self.get_inner_pads_for_gap(side, index1, index2, inner_pads, outer_pads))

    def is_inner_pad_gap_by_index(self, index1: int, index2: int, inner_pads: List[dict], outer_pads: List[dict]) -> bool:
        """Backward-compatible wrapper using side-agnostic matching."""
        for _, pad1, pad2, _ in self.get_inner_pad_gap_indices(inner_pads, outer_pads):
            if (pad1 == index1 and pad2 == index2) or (pad1 == index2 and pad2 == index1):
                return True
        return False