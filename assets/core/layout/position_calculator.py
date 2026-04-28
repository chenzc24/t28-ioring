#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Position Calculation Module
"""

from typing import List, Tuple

class PositionCalculator:
    """Position Calculator"""
    
    def __init__(self, config: dict):
        self.config = config
        self.current_ring_config = dict(config) if isinstance(config, dict) else {}
    
    def calculate_chip_size(self, layout_components: List[dict]) -> Tuple[int, int]:
        """Calculate chip size based on layout components"""
        # Check if ring_config information exists
        if hasattr(self, 'current_ring_config') and self.current_ring_config:
            # Prefer explicit chip_width/chip_height from editor (e.g. after filler addition)
            explicit_w = self.current_ring_config.get("chip_width")
            explicit_h = self.current_ring_config.get("chip_height")
            if explicit_w is not None and explicit_h is not None:
                return explicit_w, explicit_h
            # Fallback: compute from width/height/pad_spacing/corner_size
            width = self.current_ring_config.get("width", 3)
            height = self.current_ring_config.get("height", 3)
            pad_spacing = self.current_ring_config.get("pad_spacing", 60)
            corner_size = self.current_ring_config.get("corner_size", 110)
            chip_width = width * pad_spacing + 2 * corner_size
            chip_height = height * pad_spacing + 2 * corner_size
            return chip_width, chip_height
        
        # If no ring_config, use original logic
        # max_x, max_y = 0, 0
        # for component in layout_components:
        #     if component.get("type") == "pad":
        #         x, y = component.get("position", [0, 0])
        #         max_x = max(max_x, x)
        #         max_y = max(max_y, y)
        
        # # If no pad components, use default size
        # if max_x == 0 and max_y == 0:
        #     return 460, 460  # Default size
        
        # # Add margins
        # width = max_x + self.config["corner_size"]
        # height = max_y + self.config["corner_size"]
    
    def calculate_position_from_relative(self, relative_position: str, ring_config: dict, instance: dict = None) -> tuple:
        """Calculate actual coordinates and orientation based on relative position, supporting clockwise/counterclockwise"""
        # Use fixed technology parameters from default configuration (matching merge_source)
        if instance:
            pad_width = instance.get("pad_width", 20)
            pad_height = instance.get("pad_height", 110)
            corner_size = instance.get("corner_size", 110)
        else:
            pad_width = self.config.get("pad_width", 20)
            pad_height = self.config.get("pad_height", 110)
            corner_size = self.config.get("corner_size", 110)
        
        # Get chip dimensions and counts from ring_config (matching merge_source)
        chip_width = ring_config.get("chip_width", 2250)
        chip_height = ring_config.get("chip_height", 2160)
        pad_spacing = ring_config.get("pad_spacing", 90)
        placement_order = ring_config.get("placement_order", "counterclockwise")
        top_count = ring_config.get("top_count", 12)
        bottom_count = ring_config.get("bottom_count", 12)
        left_count = ring_config.get("left_count", 12)
        right_count = ring_config.get("right_count", 12)
        
        # Get process_node to determine offset from config
        process_node = ring_config.get("process_node", self.config.get("process_node", "T28"))
        layout_params = ring_config.get("layout_params", {})
        offset = layout_params.get("pad_offset", 20 if process_node == "T28" else 10)

        # Parse relative positions
        if relative_position == "top_left":
            return ([0, chip_height], "R270")
        elif relative_position == "top_right":
            return ([chip_width, chip_height], "R180")
        elif relative_position == "bottom_left":
            return ([0, 0], "R0")
        elif relative_position == "bottom_right":
            return ([chip_width, 0], "R90")

        # Parse edge positions (28nm: no offset, 180nm: +10 offset)
        if relative_position.startswith("top_"):
            index = int(relative_position.split("_")[1])
            if placement_order == "clockwise":
                real_index = index
            else:
                real_index = (top_count - 1) - index
            x = corner_size + real_index * pad_spacing + pad_width + offset
            y = chip_height
            return ([x, y], "R180")
        elif relative_position.startswith("bottom_"):
            index = int(relative_position.split("_")[1])
            if placement_order == "clockwise":
                real_index = index
            else:
                real_index = (bottom_count - 1) - index
            x = chip_width - corner_size - real_index * pad_spacing - pad_width - offset
            y = 0
            return ([x, y], "R0")
        elif relative_position.startswith("left_"):
            index = int(relative_position.split("_")[1])
            if placement_order == "clockwise":
                real_index = index
            else:
                real_index = (left_count - 1) - index
            x = 0
            y = corner_size + real_index * pad_spacing + pad_width + offset
            return ([x, y], "R270")
        elif relative_position.startswith("right_"):
            index = int(relative_position.split("_")[1])
            if placement_order == "clockwise":
                real_index = index
            else:
                real_index = (right_count - 1) - index
            x = chip_width
            y = chip_height - corner_size - real_index * pad_spacing - pad_width - offset
            return ([x, y], "R90")

        # Default return to origin
        return ([0, 0], "R0")
    
    def calculate_filler_position(self, pos1: list, pos2: list, orientation: str, filler_index: int = 0) -> list:
        """Calculate filler position"""
        x1, y1 = pos1
        x2, y2 = pos2
        
        if orientation == "R0":  # Bottom edge
            # Distribute evenly in x direction
            total_distance = abs(x2 - x1)
            if total_distance == 0:
                return [x1, y1]
            filler_x = x1 + (total_distance * (filler_index + 1)) / 3
            return [filler_x, y1]
        elif orientation == "R90":  # Right edge
            # Distribute evenly in y direction
            total_distance = abs(y2 - y1)
            if total_distance == 0:
                return [x1, y1]
            filler_y = y1 + (total_distance * (filler_index + 1)) / 3
            return [x1, filler_y]
        elif orientation == "R180":  # Top edge
            # Distribute evenly in x direction
            total_distance = abs(x2 - x1)
            if total_distance == 0:
                return [x1, y1]
            filler_x = x1 + (total_distance * (filler_index + 1)) / 3
            return [filler_x, y1]
        elif orientation == "R270":  # Left edge
            # Distribute evenly in y direction
            total_distance = abs(y2 - y1)
            if total_distance == 0:
                return [x1, y1]
            filler_y = y1 + (total_distance * (filler_index + 1)) / 3
            return [x1, filler_y]
        
        return [x1, y1]  # Default return to first position
    
    def calculate_filler_position_from_relative(self, relative_position: str, ring_config: dict, instance: dict = None) -> tuple:
        """Calculate actual coordinates and orientation of filler based on relative position"""
        # Use fixed technology parameters from default configuration (matching merge_source)
        if instance:
            pad_width = instance.get("pad_width", 20)
            pad_height = instance.get("pad_height", 110)
        else:
            pad_width = self.config.get("pad_width", 20)
            pad_height = self.config.get("pad_height", 110)
        corner_size = ring_config.get("corner_size", 110)
        pad_spacing = ring_config.get("pad_spacing", 90)
        placement_order = ring_config.get("placement_order", "counterclockwise")
        
        # Get chip dimensions and counts from ring_config (matching merge_source)
        chip_width = ring_config.get("chip_width", 2250)
        chip_height = ring_config.get("chip_height", 2160)
        top_count = ring_config.get("top_count", 12)
        bottom_count = ring_config.get("bottom_count", 12)
        left_count = ring_config.get("left_count", 12)
        right_count = ring_config.get("right_count", 12)

        # Parse filler position format
        parts = relative_position.split('_')
        
        if len(parts) >= 3 and parts[1] == "corner":
            # Corner filler format: side_corner_index
            side = parts[0]  # left, right, top, bottom
            corner_index = int(parts[2])
            
            if side == "left":
                if corner_index == 0:  # Top-left corner
                    return ([0, chip_height - corner_size], "R270")
                elif corner_index == 3:  # Bottom-left corner
                    return ([0, corner_size], "R270")
            elif side == "right":
                if corner_index == 0:  # Top-right corner
                    return ([chip_width, chip_height - corner_size], "R90")
                elif corner_index == 3:  # Bottom-right corner
                    return ([chip_width, corner_size], "R90")
            elif side == "top":
                if corner_index == 0:  # Top-left corner
                    return ([corner_size, chip_height], "R180")
                elif corner_index == 3:  # Top-right corner
                    return ([chip_width - corner_size, chip_height], "R180")
            elif side == "bottom":
                if corner_index == 0:  # Bottom-left corner
                    return ([corner_size, 0], "R0")
                elif corner_index == 3:  # Bottom-right corner
                    return ([chip_width - corner_size - 10, 0], "R0")
        
        elif len(parts) >= 3 and parts[1].isdigit():
            # Pad filler format: side_pad_index_filler_index
            side = parts[0]  # left, right, top, bottom
            pad_index = int(parts[1])
            filler_index = int(parts[2])
            
            # Calculate pad position (matching merge_source)
            if side == "left":
                if placement_order == "clockwise":
                    real_index = pad_index
                else:
                    real_index = (left_count - 1) - pad_index
                pad_x = 0
                pad_y = corner_size + real_index * pad_spacing + 2 * pad_width
                
                # Filler position between pads
                if filler_index == 1:
                    return ([pad_x, pad_y - pad_width], "R270")
                elif filler_index == 2:
                    return ([pad_x, pad_y - 2 * pad_width], "R270")
                    
            elif side == "right":
                if placement_order == "clockwise":
                    real_index = pad_index
                else:
                    real_index = (right_count - 1) - pad_index
                pad_x = chip_width
                pad_y = chip_height - corner_size - real_index * pad_spacing - 2 * pad_width
                
                # Filler position between pads
                if filler_index == 1:
                    return ([pad_x, pad_y + pad_width], "R90")
                elif filler_index == 2:
                    return ([pad_x, pad_y + 2 * pad_width], "R90")
                    
            elif side == "top":
                if placement_order == "clockwise":
                    real_index = pad_index
                else:
                    real_index = (top_count - 1) - pad_index
                pad_x = corner_size + real_index * pad_spacing + 2 * pad_width
                pad_y = chip_height
                
                # Filler position between pads
                if filler_index == 1:
                    return ([pad_x + pad_width, pad_y], "R180")
                elif filler_index == 2:
                    return ([pad_x + 2 * pad_width, pad_y], "R180")
                    
            elif side == "bottom":
                if placement_order == "clockwise":
                    real_index = pad_index
                else:
                    real_index = (bottom_count - 1) - pad_index
                pad_x = chip_width - corner_size - real_index * pad_spacing - 2 * pad_width
                pad_y = 0
                
                # Filler position between pads
                if filler_index == 1:
                    return ([pad_x - pad_width, pad_y], "R0")
                elif filler_index == 2:
                    return ([pad_x - 2 * pad_width, pad_y], "R0")

        # Default return to origin
        return ([0, 0], "R0")
    
    def sort_components_by_position(self, layout_components: List[dict], placement_order: str = None) -> List[dict]:
        """Sort components by position, supporting clockwise and counterclockwise placement orders"""
        if placement_order is None:
            placement_order = self.config.get("placement_order", "counterclockwise")
        
        def get_sort_key(component):
            pos = component.get("position", [0, 0])
            orientation = component.get("orientation", "R0")
            
            if placement_order == "clockwise":
                # Clockwise: Top-left -> Top edge -> Top-right -> Right edge -> Bottom-right -> Bottom edge -> Bottom-left -> Left edge
                if orientation == "R180":  # Top edge, from left to right
                    return (0, pos[0])
                elif orientation == "R90":  # Right edge, from top to bottom
                    return (1, -pos[1])
                elif orientation == "R0":  # Bottom edge, from right to left
                    return (2, -pos[0])
                elif orientation == "R270":  # Left edge, from bottom to top
                    return (3, pos[1])
                else:
                    return (4, pos[0], pos[1])
            else:
                # Counterclockwise: Top-left -> Left edge -> Bottom-left -> Bottom edge -> Bottom-right -> Right edge -> Top-right -> Top edge
                if orientation == "R270":  # Left edge, from bottom to top
                    return (0, pos[1])
                elif orientation == "R0":  # Bottom edge, from right to left
                    return (1, -pos[0])
                elif orientation == "R90":  # Right edge, from top to bottom
                    return (2, -pos[1])
                elif orientation == "R180":  # Top edge, from left to right
                    return (3, pos[0])
                else:
                    return (4, pos[0], pos[1])
        
        return sorted(layout_components, key=get_sort_key) 