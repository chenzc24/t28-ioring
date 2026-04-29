#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T28 Layout Generator - Complete independent implementation for T28 process node
No inheritance, completely standalone
"""

import os
import json
import re
from typing import Dict, Tuple, List, Optional

from .device_classifier import DeviceClassifier
from .voltage_domain import VoltageDomainHandler
from .position_calculator import PositionCalculator
from .filler_generator import FillerGenerator
from .validator import LayoutValidator
from .inner_pad_handler import InnerPadHandler
from .skill_generator import SkillGeneratorT28
from .auto_filler import AutoFillerGeneratorT28
from .process_config import get_process_node_config
from .visualizer import visualize_layout


class LayoutGeneratorT28:
    """T28 Layout Generator - Standalone implementation"""
    
    def __init__(self):
        # Get T28 configuration
        node_config = get_process_node_config()

        # Default configuration for T28
        self.config = {
            "library_name": node_config["library_name"],
            "view_name": "layout",
            "pad_width": node_config["pad_width"],
            "pad_height": node_config["pad_height"],
            "corner_size": node_config["corner_size"],
            "pad_spacing": node_config["pad_spacing"],
            "placement_order": "counterclockwise",
            "filler_components": node_config["filler_components"],
            "process_node": "T28"
        }
        
        # Store device_masters from config
        if "device_masters" in node_config:
            self.config["device_masters"] = node_config["device_masters"]
        
        # Initialize modules
        self.position_calculator = PositionCalculator(self.config)
        self.voltage_domain_handler = VoltageDomainHandler()
        self.filler_generator = FillerGenerator()
        self.layout_validator = LayoutValidator()
        self.inner_pad_handler = InnerPadHandler(self.config)
        self.skill_generator = SkillGeneratorT28(self.config)
        self.auto_filler_generator = AutoFillerGeneratorT28(self.config)
    
    def sanitize_skill_instance_name(self, name: str) -> str:
        """Sanitize instance names for SKILL compatibility"""
        sanitized = name.replace('<', '_').replace('>', '_')
        while '__' in sanitized:
            sanitized = sanitized.replace('__', '_')
        return sanitized
    
    def set_config(self, config: dict):
        """Set configuration parameters"""
        self.config.update(config)
        self.position_calculator.config = self.config
        self.position_calculator.current_ring_config = self.config
        self.inner_pad_handler.config = self.config
        self.skill_generator.config = self.config
        self.auto_filler_generator.config = self.config
    
    def calculate_chip_size(self, layout_components: List[dict]) -> Tuple[int, int]:
        """Calculate chip size based on layout components"""
        return self.position_calculator.calculate_chip_size(layout_components)

    def _extract_relative_position(self, instance: dict) -> str:
        """Extract relative position string from instance fields."""
        raw_position = instance.get("position", "")
        if isinstance(raw_position, str):
            return raw_position
        return ""

    def _parse_side_index(self, relative_position: str) -> Tuple[Optional[str], Optional[int]]:
        """Parse side-index format: top_0/right_2/bottom_5/left_1."""
        if not isinstance(relative_position, str):
            return None, None
        parts = relative_position.split("_")
        if len(parts) == 2 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit():
            return parts[0], int(parts[1])
        return None, None

    def _get_component_type(self, instance: dict) -> str:
        """Resolve component type using explicit type first, then device."""
        comp_type = instance.get("type")
        if isinstance(comp_type, str) and comp_type:
            return comp_type

        device = str(instance.get("device", ""))
        if DeviceClassifier.is_corner_device(device):
            return "corner"
        if DeviceClassifier.is_filler_device(device) or DeviceClassifier.is_separator_device(device):
            return "filler"
        return "pad"

    def _resolve_component_geometry(self, instance: dict, component_type: str, ring_config: dict) -> Tuple[float, float]:
        """Resolve geometry by component type for T28."""
        default_pad_width = float(ring_config.get("pad_width", self.config.get("pad_width", 20)))
        default_pad_height = float(ring_config.get("pad_height", self.config.get("pad_height", 110)))
        width = default_pad_width
        height = default_pad_height
        instance_pad_width = instance.get("pad_width")
        instance_pad_height = instance.get("pad_height")
        if isinstance(instance_pad_width, (int, float)) and instance_pad_width > 0:
            width = float(instance_pad_width)
        if isinstance(instance_pad_height, (int, float)) and instance_pad_height > 0:
            height = float(instance_pad_height)

        if component_type == "filler":
            device = str(instance.get("device", "")).upper()
            filler_width_match = re.search(r"PFILLER(\d+)", device)
            if filler_width_match:
                width = float(int(filler_width_match.group(1)))
        return float(width), float(height)

    def _build_t28_side_sequences(self, instances: List[dict], ring_config: dict) -> Dict[str, dict]:
        """Build per-side cumulative width map for side-indexed components."""
        placement_order = ring_config.get("placement_order", "counterclockwise")
        side_index_widths: Dict[str, Dict[int, float]] = {
            "top": {},
            "right": {},
            "bottom": {},
            "left": {},
        }

        for instance in instances:
            side, index = self._parse_side_index(self._extract_relative_position(instance))
            if side is None or index is None:
                continue
            if index not in side_index_widths[side]:
                comp_type = self._get_component_type(instance)
                width, _ = self._resolve_component_geometry(instance, comp_type, ring_config)
                side_index_widths[side][index] = width

        sequence_map: Dict[str, dict] = {}
        for side, idx_map in side_index_widths.items():
            if not idx_map:
                sequence_map[side] = {"max_index": -1, "prefix_sum": {}}
                continue

            max_index = max(idx_map.keys())
            ranked = []
            for logical_index, width in idx_map.items():
                real_index = logical_index if placement_order == "clockwise" else (max_index - logical_index)
                ranked.append((real_index, logical_index, width))
            ranked.sort(key=lambda item: item[0])

            cumulative = 0.0
            prefix_sum: Dict[int, float] = {}
            for _, logical_index, width in ranked:
                cumulative += width
                prefix_sum[logical_index] = cumulative

            sequence_map[side] = {"max_index": max_index, "prefix_sum": prefix_sum}

        return sequence_map

    def _calculate_t28_cumulative_position(
        self,
        chip_width: float,
        chip_height: float,
        relative_position: str,
        ring_config: dict,
        side_sequences: Dict[str, dict],
    ) -> Optional[Tuple[List[float], str]]:
        """Calculate T28 side component position by cumulative sequence width."""
        if not isinstance(chip_width, (int, float)):
            chip_width = 460
        if not isinstance(chip_height, (int, float)):
            chip_height = 460
        corner_size = ring_config.get("corner_size", self.config.get("corner_size", 110))

        if relative_position == "top_left":
            return [0, chip_height], "R270"
        if relative_position == "top_right":
            return [chip_width, chip_height], "R180"
        if relative_position == "bottom_left":
            return [0, 0], "R0"
        if relative_position == "bottom_right":
            return [chip_width, 0], "R90"

        side, logical_index = self._parse_side_index(relative_position)
        if side is None or logical_index is None:
            return None

        side_info = side_sequences.get(side, {})
        prefix_sum = side_info.get("prefix_sum", {})
        if logical_index not in prefix_sum:
            return None

        cumulative_distance = prefix_sum[logical_index]
        if side == "top":
            return [corner_size + cumulative_distance, chip_height], "R180"
        if side == "bottom":
            return [chip_width - corner_size - cumulative_distance, 0], "R0"
        if side == "left":
            return [0, corner_size + cumulative_distance], "R270"
        if side == "right":
            return [chip_width, chip_height - corner_size - cumulative_distance], "R90"
        return None
    
    def convert_relative_to_absolute(self, chip_width: float, chip_height: float, instances: List[dict], ring_config: dict) -> List[dict]:
        """Convert relative positions to absolute positions for 28nm format.

        Supports mixed inputs:
        - relative position strings (converted)
        - absolute [x, y] positions (kept, orientation preserved if present)
        """
        converted_components = []
        inner_pads = []
        side_sequences = self._build_t28_side_sequences(instances, ring_config)
        for instance in instances:
            raw_position = instance.get("position", "")
            name = instance.get("name", "")
            relative_pos = self._extract_relative_position(instance)
            device = instance.get("device", "")
            if not device:
                raise ValueError(f"[ERROR] Error: Instance '{name}' must have 'device' field")
            
            component_type = self._get_component_type(instance)
            direction = instance.get("direction", "")
            voltage_domain = instance.get("voltage_domain", {})
            pin_connection = instance.get("pin_connection", {})
            
            has_relative_semantics = isinstance(relative_pos, str) and bool(relative_pos)
            if isinstance(raw_position, (list, tuple)) and len(raw_position) == 2 and not has_relative_semantics:
                position = [raw_position[0], raw_position[1]]
                orientation = instance.get("orientation", "R0")
            else:
                cumulative_result = self._calculate_t28_cumulative_position(chip_width, chip_height, relative_pos, ring_config, side_sequences)
                if cumulative_result is not None:
                    position, orientation = cumulative_result
                else:
                    if component_type == "filler":
                        position, orientation = self.position_calculator.calculate_filler_position_from_relative(relative_pos, ring_config, instance)
                    else:
                        position, orientation = self.position_calculator.calculate_position_from_relative(relative_pos, ring_config, instance)
            
            component = {
                "type": component_type,
                "name": name,
                "device": device,
                "position": position,
                "orientation": orientation,
            }

            if relative_pos:
                component["position_str"] = relative_pos

            if direction:
                component["direction"] = direction

            if voltage_domain:
                component["voltage_domain"] = voltage_domain
            if pin_connection:
                component["pin_connection"] = pin_connection

            domain = instance.get("domain", "")
            if domain:
                component["domain"] = domain

            converted_components.append(component)
        
        # Check corners
        has_corners = any(comp.get("type") == "corner" for comp in converted_components)
        if not has_corners:
            raise ValueError("[ERROR] Error: Corner components are missing in the intent graph!")
        
        # Handle inner pads
        for inner_pad in inner_pads:
            name = inner_pad.get("name", "")
            device = inner_pad.get("device", "")
            if not device:
                raise ValueError(f"[ERROR] Error: Inner pad '{name}' must have 'device' field")
            
            position_str = inner_pad.get("position_str") or inner_pad.get("position", "")
            direction = inner_pad.get("direction", "")
            voltage_domain = inner_pad.get("voltage_domain", {})
            pin_connection = inner_pad.get("pin_connection", {})
            
            outer_pads_for_inner = [comp for comp in converted_components if comp.get("type") == "pad"]
            position, orientation = self.inner_pad_handler.calculate_inner_pad_position(position_str, outer_pads_for_inner, ring_config)
            
            component = {
                "type": "inner_pad",
                "name": name,
                "device": device,
                "position": position,
                "orientation": orientation,
                "position_str": position_str
            }
            
            if direction:
                component["direction"] = direction
            if voltage_domain:
                component["voltage_domain"] = voltage_domain
            if pin_connection:
                component["pin_connection"] = pin_connection
            
            converted_components.append(component)
        
        return converted_components


def generate_layout_from_json(json_file: str, output_file: str = "generated_layout.il"):
    """Generate 28nm layout from JSON file"""
    print(f"[>>] Reading intent graph file: {json_file}")
    print(f"[--] Using process node: 28nm")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    instances = config.get("instances", [])
    ring_config = config.get("ring_config", {})
    if not isinstance(ring_config, dict):
        ring_config = {}

    # Ensure process_node is always present for downstream io-editor branching
    ring_config["process_node"] = "T28"
    
    generator = LayoutGeneratorT28()
    
    # Normalize ring_config format (legacy compatibility)
    if "width" in ring_config and "chip_width" not in ring_config:
        width = ring_config.get("width", 3)
        height = ring_config.get("height", 3)
        corner_size = ring_config.get("corner_size", generator.config["corner_size"])
        pad_spacing = ring_config.get("pad_spacing", generator.config["pad_spacing"])

        ring_config["chip_width"] = width * pad_spacing + corner_size * 2
        ring_config["chip_height"] = height * pad_spacing + corner_size * 2

        if "top_count" not in ring_config:
            ring_config["top_count"] = width
        if "bottom_count" not in ring_config:
            ring_config["bottom_count"] = width
        if "left_count" not in ring_config:
            ring_config["left_count"] = height
        if "right_count" not in ring_config:
            ring_config["right_count"] = height
    
    # Merge top-level config
    if "library_name" in config and "library_name" not in ring_config:
        ring_config["library_name"] = config["library_name"]
    if "cell_name" in config and "cell_name" not in ring_config:
        ring_config["cell_name"] = config["cell_name"]
    
    generator.set_config(ring_config)
    # Ensure chip_width and chip_height are in config for auto_filler (after calculation)
    if "chip_width" in ring_config:
        generator.config["chip_width"] = ring_config["chip_width"]
        generator.auto_filler_generator.config["chip_width"] = ring_config["chip_width"]
    if "chip_height" in ring_config:
        generator.config["chip_height"] = ring_config["chip_height"]
        generator.auto_filler_generator.config["chip_height"] = ring_config["chip_height"]
    if "pad_width" not in ring_config:
        ring_config["pad_width"] = generator.config["pad_width"]
    if "pad_height" not in ring_config:
        ring_config["pad_height"] = generator.config["pad_height"]
    if "corner_size" not in ring_config:
        ring_config["corner_size"] = generator.config["corner_size"]
    if "pad_spacing" not in ring_config:
        ring_config["pad_spacing"] = generator.config["pad_spacing"]
    if "library_name" not in ring_config:
        ring_config["library_name"] = generator.config["library_name"]
    if "view_name" not in ring_config:
        ring_config["view_name"] = generator.config["view_name"]
    if "device_masters" not in ring_config:
        ring_config["device_masters"] = generator.config.get("device_masters", {})
    
    print("[OK] Configuration parameters set")
    
    # Convert relative positions
    # if any("position" in instance and "_" in str(instance["position"]) for instance in instances):
    #     instances = generator.convert_relative_to_absolute(instances, ring_config)
    
    # Separate components
    outer_pads = []
    inner_pads = []
    corners = []
    for instance in instances:
        if instance.get("type") == "inner_pad":
            inner_pads.append(instance)
        elif instance.get("type") == "pad":
            outer_pads.append(instance)
        elif instance.get("type") == "corner":
            corners.append(instance)

    chip_width, chip_height = generator.calculate_chip_size(outer_pads)

    # Persist recomputed chip dimensions for all downstream consumers.
    ring_config["chip_width"] = chip_width
    ring_config["chip_height"] = chip_height
    generator.config["chip_width"] = chip_width
    generator.config["chip_height"] = chip_height
    generator.auto_filler_generator.config["chip_width"] = chip_width
    generator.auto_filler_generator.config["chip_height"] = chip_height
    generator.position_calculator.current_ring_config = generator.config

    print(f"[--] Outer ring pads: {len(outer_pads)}")
    print(f"[--] Inner ring pads: {len(inner_pads)}")
    print(f"[--] Corners: {len(corners)}")
    
    # Validate
    # validation_components = outer_pads + corners
    # process_node = ring_config.get("process_node"
    # validation_result = generator.layout_validator.validate_layout_rules(validation_components, process_node)
    # if not validation_result["valid"]:
    #     print(f"[ERROR] Layout rule validation failed: {validation_result['message']}")
    #     return None
    
    # Check fillers
    all_instances = instances
    existing_fillers = [comp for comp in all_instances if comp.get("type") == "filler" or 
                        DeviceClassifier.is_filler_device(comp.get("device", ""))]
    existing_separators = [comp for comp in all_instances if comp.get("type") == "separator" or 
                          DeviceClassifier.is_separator_device(comp.get("device", ""))]
    
    # Update chip dimensions in auto_filler config before generating fillers (T28 uses locally computed values)
    generator.auto_filler_generator.config["chip_width"] = chip_width
    generator.auto_filler_generator.config["chip_height"] = chip_height
    
    validation_components = outer_pads + corners
    if existing_fillers or existing_separators:
        print(f"[--] Detected filler components in JSON: {len(existing_fillers)} fillers, {len(existing_separators)} separators")
        all_components_with_fillers = []
        for comp in all_instances:
            if not isinstance(comp, dict):
                continue
            comp_type = comp.get("type")
            device = str(comp.get("device", ""))
            if comp_type in {"pad", "corner", "inner_pad", "filler", "separator"}:
                all_components_with_fillers.append(comp)
            elif DeviceClassifier.is_filler_device(device) or DeviceClassifier.is_separator_device(device):
                all_components_with_fillers.append(comp)
    else:
        all_components_with_fillers = generator.auto_filler_generator.auto_insert_fillers_with_inner_pads(validation_components, inner_pads)

    final_components_input = list(all_components_with_fillers)
    
    final_components = generator.convert_relative_to_absolute(chip_width, chip_height, final_components_input, ring_config)
    outer_pads = [comp for comp in final_components if comp.get("type") == "pad"]
    corners = [comp for comp in final_components if comp.get("type") == "corner"]
    inner_pads = [comp for comp in final_components if comp.get("type") == "inner_pad"]
    all_components_with_fillers = final_components
    filler_components = [
        comp for comp in all_components_with_fillers
        if comp.get("type") == "filler" or DeviceClassifier.is_filler_device(comp.get("device", ""))
    ]
    
    # Generate SKILL script
    print("[>>] Starting Layout Skill script generation...")
    skill_commands = []
    
    skill_commands.append("cv = geGetWindowCellView()")
    skill_commands.append("; Generated Layout Script with Dual Ring Support")
    skill_commands.append("")
    
    # Sort components
    placement_order = ring_config.get("placement_order", "counterclockwise")
    all_components = outer_pads + corners
    sorted_components = generator.position_calculator.sort_components_by_position(all_components, placement_order)
    
    # 1. Generate all components
    skill_commands.append("; ==================== All Components (Sorted by Placement Order) ====================")
    for component in sorted_components:
        x, y = component["position"]
        orientation = component["orientation"]
        device = component["device"]
        name = component["name"]
        component_type = component["type"]
        position_str = component.get('position_str', 'abs')
        
        sanitized_name = generator.sanitize_skill_instance_name(f"{name}_{position_str}")
        skill_commands.append(f'dbCreateParamInstByMasterName(cv "{ring_config.get("library_name", "tphn28hpcpgv18")}" "{device}" "{ring_config.get("view_name", "layout")}" "{sanitized_name}" list({x} {y}) "{orientation}")')
        
        # Add PAD60GU for pad components (28nm specific)
        if component_type == "pad":
            device_masters = ring_config.get("device_masters", {})
            pad_library = device_masters.get("pad_library", "PAD")
            pad_master = device_masters.get("pad60_master", "PAD60GU")
            sanitized_pad_name = generator.sanitize_skill_instance_name(f"pad60gu_{name}_{position_str}")
            skill_commands.append(f'dbCreateParamInstByMasterName(cv "{pad_library}" "{pad_master}" "layout" "{sanitized_pad_name}" list({x} {y}) "{orientation}")')
    
    skill_commands.append("")
    
    # 2. Inner Ring Pads
    if inner_pads:
        skill_commands.append("; ==================== Inner Ring Pads ====================")
        inner_pad_commands = generator.inner_pad_handler.generate_inner_pad_skill_commands(inner_pads, outer_pads, ring_config)
        skill_commands.extend(inner_pad_commands)
        skill_commands.append("")
    
    # 3. Filler components
    skill_commands.append("; ==================== Filler Components ====================")

    for filler_index, filler in enumerate(filler_components):
        x, y = filler["position"]
        orientation = filler["orientation"]
        device = filler["device"]
        name = str(filler.get("name", "")).strip()
        position_str = filler.get("position_str")
        if not isinstance(position_str, str) or not position_str:
            raw_pos = filler.get("position")
            position_str = raw_pos if isinstance(raw_pos, str) and raw_pos else f"idx_{filler_index}"
        skill_inst_name = f"{name}_{position_str}" if name else f"filler_{position_str}"
        sanitized_name = generator.sanitize_skill_instance_name(skill_inst_name)
        skill_commands.append(f'dbCreateParamInstByMasterName(cv "{ring_config.get("library_name", "tphn28hpcpgv18")}" "{device}" "{ring_config.get("view_name", "layout")}" "{sanitized_name}" list({x} {y}) "{orientation}")')
    
    skill_commands.append("")
    
    # 4. Digital IO features
    skill_commands.append("; ==================== Digital IO Features (with Inner Pad Support) ====================")
    digital_io_commands = generator.skill_generator.generate_digital_io_features_with_inner(outer_pads, inner_pads, ring_config)
    skill_commands.extend(digital_io_commands)
    skill_commands.append("")
    
    # 5. Pin labels
    skill_commands.append("; ==================== Pin Labels (with Inner Pad Support) ====================")
    if hasattr(generator.skill_generator, "generate_pin_labels_with_inner"):
        pin_label_commands = generator.skill_generator.generate_pin_labels_with_inner(outer_pads, inner_pads, ring_config)
    else:
        pin_label_commands = []
    skill_commands.extend(pin_label_commands)
    skill_commands.append("")
    skill_commands.append("dbSave(cv)")
    skill_commands.append("t")
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(skill_commands))
    
    # Generate visualization (28nm uses layout_visualizer)
    try:
        output_dir = os.path.dirname(output_file) or "output"
        vis_name = os.path.splitext(os.path.basename(output_file))[0] + "_visualization.png"
        visualization_path = os.path.join(output_dir, vis_name)
        os.makedirs(output_dir, exist_ok=True)
        visualize_layout(output_file, visualization_path)
        print(f"[OK] Visualization generated: {visualization_path}")
    except Exception as e:
        print(f"[WARN] Visualization generation failed: {e}")
    
    # Keep chip size consistent with the value calculated before downstream processing
    total_components = len(all_components_with_fillers) + len(inner_pads) * 2
    
    print(f"[--] Chip size: {chip_width} x {chip_height}")
    print(f"[--] Total components: {total_components}")
    if inner_pads:
        print(f"[--] Inner ring pads: {len(inner_pads)}")
    print(f"[OK] Layout Skill script generated: {output_file}")
    
    return output_file

