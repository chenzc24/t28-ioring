#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Layout Generator Factory - Creates process node-specific generators
"""

from .generator import LayoutGeneratorT28, generate_layout_from_json as generate_T28


def create_layout_generator(process_node: str = "T28"):
    """Factory function to create process node-specific layout generator

    Args:
        process_node: Process node ("T28" or "T180", default: "T28")

    Returns:
        Process node-specific layout generator instance
    """
    # Currently only T28 is supported in this skill
    return LayoutGeneratorT28()


def generate_layout_from_json(json_file: str, output_file: str = "generated_layout.il", process_node: str = "T28"):
    """Generate layout from JSON file using process node-specific generator

    Args:
        json_file: Path to intent graph JSON file
        output_file: Path to output SKILL file
        process_node: Process node to use ("T28" or "T180", default: "T28")
    """
    # Currently only T28 is supported in this skill
    return generate_T28(json_file, output_file)


def validate_layout_config(json_file: str, process_node: str = "T28") -> dict:
    """Validate intent graph file
    
    Args:
        json_file: Path to intent graph JSON file
        process_node: Process node to use ("T28" or "T180", default: "T28")
    
    Returns:
        Validation result dictionary with 'valid' and 'message' keys
    """
    import json
    
    print(f"[>>] Validating intent graph file: {json_file}")
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        return {"valid": False, "message": f"Intent graph file not found: {json_file}"}
    except json.JSONDecodeError as e:
        return {"valid": False, "message": f"JSON format error - {e}"}
    
    # Determine process node
    ring_config = config_data.get("ring_config", {})
    if "process_node" in ring_config:
        process_node = ring_config["process_node"]
    
    # Use factory to get correct generator
    generator = create_layout_generator(process_node)
    
    # Check if it's the new relative position format
    if "ring_config" in config_data and "instances" in config_data:
        print("[--] Detected relative position format, converting for validation...")
        
        # Convert relative positions to absolute positions
        instances = config_data["instances"]
        ring_config = config_data["ring_config"]
        layout_components = generator.convert_relative_to_absolute(instances, ring_config)
        
        print(f"[OK] Conversion completed: {len(instances)} relative positions -> {len(layout_components)} absolute positions")
        
    else:
        # Old format handling
        if "layout_components" not in config_data:
            return {"valid": False, "message": "Missing 'layout_components' or 'instances' field"}
        
        layout_components = config_data["layout_components"]
    
    # Validate layout rules
    validation_result = generator.layout_validator.validate_layout_rules(layout_components, process_node)
    
    return validation_result

