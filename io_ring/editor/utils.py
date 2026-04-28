# -*- coding: utf-8 -*-
"""
Editor Utils - Helper functions to bridge Layout Generator and Layout Editor (GUI)
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from copy import deepcopy


def parse_relative_position(pos: Any):
    """Parse relative position string like top_0/right_1/top_left/left_3_4."""
    if not isinstance(pos, str):
        return None, None, None

    if pos in {"top_left", "top_right", "bottom_left", "bottom_right"}:
        return "corner", None, pos

    parts = pos.split("_")
    if len(parts) == 2 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit():
        return parts[0], int(parts[1]), None

    # Inner pad format: side_index1_index2 (e.g. left_3_4 = between left_3 and left_4)
    if len(parts) == 3 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit() and parts[2].isdigit():
        idx1, idx2 = int(parts[1]), int(parts[2])
        # Use fractional index to sort between the two outer pads
        return parts[0], idx1 + 0.5, None

    return None, None, None

def export_to_editor_json(
    components: List[Dict], 
    ring_config: Dict, 
    visual_colors: Dict,
    output_path: str
) -> str:
    """
    Export layout components to IO Editor compatible JSON format
    
    Args:
        components: List of component dicts (including fillers)
        ring_config: Configuration dict containing chip dimensions etc.
        visual_colors: Dictionary of device colors from Visualizer
        output_path: Path to save the JSON file
    """
    
    chip_width = ring_config.get("chip_width", 0)
    chip_height = ring_config.get("chip_height", 0)
    process_node = ring_config.get("process_node", "T28")

    # Dimensions for logic calculation (T28 default fallback)
    pad_h = ring_config.get("pad_height", 110)
    corner_s = ring_config.get("corner_size", 110)
    pad_w = ring_config.get("pad_width", 20)
    
    # 1. Structure the Graph
    # Preserve ring_config shape instead of trimming to a subset.
    ring_config_preserved = deepcopy(ring_config) if isinstance(ring_config, dict) else {}

    # Keep original ring_config shape intact.
    # Only build a minimal fallback when ring_config is completely missing/empty.
    if not ring_config_preserved:
        ring_config_preserved = {
            "chip_width": chip_width,
            "chip_height": chip_height,
            "placement_order": "counterclockwise",
            "process_node": process_node,
        }

    intent_graph = {
        "ring_config": ring_config_preserved,
        "visual_metadata": {
            "colors": visual_colors,
            "dimensions": {
                "pad_width": pad_w,
                "pad_height": pad_h,
                "corner_size": corner_s,
                "filler_10_width": 10 
            }
        },
        "instances": []
    }
    
    # 2. Buckets for deterministic side ordering without runtime-only fields.
    bottom_side = []
    right_side = []
    top_side = []
    left_side = []
    corners_list = []

    preserved_fields = [
        "view_name", "domain", "pad_width", "pad_height",
        "pin_connection", "direction", "voltage_domain",
        "orientation"
    ]

    # 3. Convert Components
    for idx, comp in enumerate(components):
        rel_pos = comp.get("position_str")
        if not isinstance(rel_pos, str):
            rel_pos = comp.get("position") if isinstance(comp.get("position"), str) else None

        rel_side, rel_index, rel_corner = parse_relative_position(rel_pos)

        if rel_side is None:
            comp_name = comp.get("name", f"component_{idx}")
            raise ValueError(
                f"Component '{comp_name}' is missing valid relative position. "
                f"Expected 'top_N/right_N/bottom_N/left_N' or corner token, got: {rel_pos!r}"
            )

        if rel_side != "corner" and rel_index is None:
            comp_name = comp.get("name", f"component_{idx}")
            raise ValueError(
                f"Component '{comp_name}' has invalid side position {rel_pos!r}; "
                "expected numeric index suffix like 'left_3'."
            )

        instance_type = comp.get("type", "pad")
        persisted_instance = {
            "id": f"inst_{idx}",
            "name": comp.get("name", f"{instance_type}_{idx}"),
            "device": comp.get("device", ""),
            "type": instance_type,
            "position": rel_pos if isinstance(rel_pos, str) else "",
        }

        for field in preserved_fields:
            if field in comp:
                persisted_instance[field] = comp[field]

        # Map to side buckets using parsed relative semantics only.
        if rel_side == "corner":
            corners_list.append(persisted_instance)
        elif rel_side == "bottom":
            bottom_side.append((rel_index, persisted_instance))
        elif rel_side == "right":
            right_side.append((rel_index, persisted_instance))
        elif rel_side == "top":
            top_side.append((rel_index, persisted_instance))
        elif rel_side == "left":
            left_side.append((rel_index, persisted_instance))

    # 4. Assign deterministic ordering by relative index.
    for side_name, side_list in (
        ("bottom", bottom_side),
        ("right", right_side),
        ("top", top_side),
        ("left", left_side),
    ):
        if any(idx is None for idx, _ in side_list):
            raise ValueError(
                f"Side '{side_name}' contains instances without relative index. "
                "Absolute-coordinate fallback has been removed."
            )
        side_list.sort(key=lambda item: item[0])

    # Add to graph in side order; keep corner order as provided.
    ordered_instances = [inst for _, inst in bottom_side]
    ordered_instances.extend(inst for _, inst in right_side)
    ordered_instances.extend(inst for _, inst in top_side)
    ordered_instances.extend(inst for _, inst in left_side)
    ordered_instances.extend(corners_list)

    intent_graph["instances"].extend(ordered_instances)
    
    # 5. Write to File
    out_file = Path(output_path)
    # Ensure directory
    if not out_file.parent.exists():
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(intent_graph, f, indent=2)

    return str(out_file)


def draft_to_editor_json(
    draft_instances: List[Dict],
    ring_config: Dict,
    visual_colors: Dict,
    output_path: str,
) -> str:
    """Export minimal draft instances to IO Editor compatible JSON format.

    Unlike export_to_editor_json(), this function does NOT require fillers,
    corners, pin connections, or even position strings. It tolerates instances
    with only `name` and `side` (and optionally `device` and `type`).

    Args:
        draft_instances: List of draft instance dicts (minimal fields).
        ring_config: Configuration dict (process_node, dimensions, etc.).
        visual_colors: Dictionary of device colors from Visualizer.
        output_path: Path to save the JSON file.

    Returns:
        Path to the written JSON file.
    """
    from copy import deepcopy

    process_node = ring_config.get("process_node", "T28")
    pad_h = ring_config.get("pad_height", 110)
    corner_s = ring_config.get("corner_size", 110)
    pad_w = ring_config.get("pad_width", 20)

    ring_config_preserved = deepcopy(ring_config) if isinstance(ring_config, dict) else {}
    if not ring_config_preserved:
        ring_config_preserved = {
            "placement_order": "counterclockwise",
            "process_node": process_node,
        }
    ring_config_preserved.setdefault("process_node", process_node)
    ring_config_preserved.setdefault("placement_order", "counterclockwise")
    # Strip auto-derived chip dimensions — these are runtime-only, not draft data
    for _key in ("chip_width", "chip_height", "top_count", "right_count", "bottom_count", "left_count",
                 "num_pads_top", "num_pads_right", "num_pads_bottom", "num_pads_left"):
        ring_config_preserved.pop(_key, None)

    intent_graph = {
        "ring_config": ring_config_preserved,
        "visual_metadata": {
            "colors": visual_colors,
            "dimensions": {
                "pad_width": pad_w,
                "pad_height": pad_h,
                "corner_size": corner_s,
                "filler_10_width": 10,
            },
        },
        "instances": [],
    }

    # Track auto-assigned order per side
    side_counters = {"top": 0, "right": 0, "bottom": 0, "left": 0}

    for idx, inst in enumerate(draft_instances):
        # Resolve position
        position = inst.get("position")
        side = inst.get("side")
        order = inst.get("order")

        if isinstance(position, str) and position:
            # Parse position string
            if position in {"top_left", "top_right", "bottom_left", "bottom_right"}:
                resolved_side = "corner"
                resolved_order = 1
            else:
                parts = position.split("_")
                if len(parts) == 2 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit():
                    resolved_side = parts[0]
                    resolved_order = int(parts[1]) + 1
                elif len(parts) == 3 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit() and parts[2].isdigit():
                    # Inner pad format: side_index1_index2 (e.g., left_3_4 = between left_3 and left_4)
                    resolved_side = parts[0]
                    # Place between the two outer pads; fractional order
                    resolved_order = int(parts[1]) + 1.5
                else:
                    resolved_side = side or "top"
                    resolved_order = order or (side_counters.get(resolved_side, 0) + 1)
        elif side and side in side_counters:
            resolved_side = side
            resolved_order = order if order else (side_counters[side] + 1)
        elif side == "corner":
            resolved_side = "corner"
            resolved_order = 1
        else:
            # Fallback: assign to top
            resolved_side = "top"
            resolved_order = side_counters["top"] + 1

        # Update counter — only count outer pads, not inner_pads
        instance_type = inst.get("type", "pad") or "pad"
        if resolved_side in side_counters and instance_type != "inner_pad":
            side_counters[resolved_side] = max(side_counters[resolved_side], resolved_order)

        # Build position string
        if resolved_side == "corner":
            # Try to determine which corner
            location = inst.get("location") or inst.get("meta", {}).get("location")
            if location in {"top_left", "top_right", "bottom_left", "bottom_right"}:
                position_str = location
            else:
                position_str = "top_left"  # placeholder
        elif instance_type == "inner_pad" and isinstance(position, str):
            # Preserve inner_pad position format (e.g., left_3_4 = between left_3 and left_4)
            parts = position.split("_")
            if len(parts) == 3 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit() and parts[2].isdigit():
                position_str = position
            else:
                position_str = f"{resolved_side}_{resolved_order - 1}"
        else:
            position_str = f"{resolved_side}_{resolved_order - 1}"

        device = inst.get("device", "")

        persisted_instance = {
            "id": inst.get("id", f"inst_{idx}"),
            "name": inst.get("name", f"{instance_type}_{idx}"),
            "device": device,
            "type": instance_type,
            "position": position_str,
        }

        # Carry through optional fields
        for field in ("orientation", "domain", "direction", "voltage_domain"):
            if field in inst:
                persisted_instance[field] = inst[field]

        intent_graph["instances"].append(persisted_instance)

    # Write to file
    out_file = Path(output_path)
    if not out_file.parent.exists():
        out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(intent_graph, f, indent=2)

    return str(out_file)
