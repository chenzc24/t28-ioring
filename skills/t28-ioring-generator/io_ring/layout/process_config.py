#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process Node Configuration - T28 (28nm) specific
Loads configuration from JSON files for better maintainability
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

# Get config directory path
_CONFIG_DIR = Path(__file__).parent / "config"


def _load_device_config() -> Optional[Dict[str, Any]]:
    """Load device configuration from JSON file"""
    config_file = _CONFIG_DIR / "lydevices_28.json"

    if not config_file.exists():
        return None

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


# Base configuration (fallback if JSON files not found)
PROCESS_CONFIG = {
    "library_name": "tphn28hpcpgv18",
    "pad_width": 20,
    "pad_height": 110,
    "corner_size": 110,
    "pad_spacing": 60,
    "device_offset_rules": {
        "PDB3AC": 1.5 * 0.125,  # Analog signal
        "PDDW16SDGZ": -5.5 * 0.125,  # Digital IO
        "PRUW08SDGZ": -5.5 * 0.125,  # Digital IO alternative (same offset as PDDW16SDGZ)
        "PVDD1DGZ": -8 * 0.125,  # Digital power/ground
        "PVSS1DGZ": -8 * 0.125,
        "PVDD2POC": -8 * 0.125,
        "PVSS2DGZ": -8 * 0.125,
        "default": 1.5 * 0.125
    },
    "template_files": [
        "device_templates.json",
        "IO_device_info_T28.json"
    ],
    "filler_components": {
        "analog_10": "PFILLER10A_G",
        "analog_20": "PFILLER20A_G",
        "digital_10": "PFILLER10_G",
        "digital_20": "PFILLER20_G",
        "separator": "PRCUTA_G"
    }
}


def get_process_node_config() -> Dict[str, Any]:
    """
    Get configuration for T28 process node
    Loads from JSON file if available, falls back to hardcoded config

    Returns:
        Configuration dictionary for T28 process node
    """
    # Start with base config
    config = PROCESS_CONFIG.copy()

    # Try to load from JSON file and merge
    device_config = _load_device_config()
    if device_config:
        # Merge layout_params if present
        if "layout_params" in device_config:
            layout_params = device_config["layout_params"]
            config.update({
                "pad_width": layout_params.get("pad_width", config["pad_width"]),
                "pad_height": layout_params.get("pad_height", config["pad_height"]),
                "corner_size": layout_params.get("corner_size", config["corner_size"]),
                "pad_spacing": layout_params.get("pad_spacing", config["pad_spacing"]),
                "pad_offset": layout_params.get("pad_offset", 20),
            })
            # Store full layout_params for access
            config["layout_params"] = layout_params

        # Merge skill_params if present
        if "skill_params" in device_config:
            config["skill_params"] = device_config["skill_params"]

        # Merge device_masters if present
        if "device_masters" in device_config:
            config["device_masters"] = device_config["device_masters"]
            if "default_library" in device_config["device_masters"]:
                config["library_name"] = device_config["device_masters"]["default_library"]

        # Update filler_components from JSON
        if "analog_filler" in device_config and "digital_filler" in device_config:
            analog_fillers = device_config["analog_filler"]
            digital_fillers = device_config["digital_filler"]
            cut_devices = device_config.get("cut_devices", [])

            config["filler_components"] = {
                "analog_10": analog_fillers[0] if len(analog_fillers) > 0 else config["filler_components"]["analog_10"],
                "analog_20": analog_fillers[1] if len(analog_fillers) > 1 else analog_fillers[0] if len(analog_fillers) > 0 else config["filler_components"]["analog_20"],
                "digital_10": digital_fillers[0] if len(digital_fillers) > 0 else config["filler_components"]["digital_10"],
                "digital_20": digital_fillers[1] if len(digital_fillers) > 1 else digital_fillers[0] if len(digital_fillers) > 0 else config["filler_components"]["digital_20"],
                "separator": cut_devices[0] if len(cut_devices) > 0 else config["filler_components"]["separator"]
            }

        # Store device lists for use by device_classifier
        config["device_lists"] = {
            "digital_devices": device_config.get("digital_devices", []),
            "analog_devices": device_config.get("analog_devices", []),
            "digital_io": device_config.get("digital_io", []),
            "analog_io": device_config.get("analog_io", []),
            "corner_devices": device_config.get("corner_devices", []),
            "filler_devices": device_config.get("filler_devices", []),
            "cut_devices": device_config.get("cut_devices", []),
            "digital_pins": device_config.get("digital_pins", []),
            "analog_pins": device_config.get("analog_pins", []),
        }

    return config


def get_device_offset(device_type: str) -> float:
    """
    Get device offset based on device type for T28 process

    Args:
        device_type: Device type string (e.g., "PDB3AC_V_G", "PVDD1DGZ_H_G")

    Returns:
        Offset value in microns
    """
    config = get_process_node_config()
    rules = config["device_offset_rules"]

    # Check for exact match first
    if device_type in rules:
        return rules[device_type]

    # Check for prefix match (device_type may have suffix like _V_G, _H_G)
    for prefix, offset in rules.items():
        if prefix != "default" and device_type.startswith(prefix):
            return offset

    # Return default
    return rules.get("default", 1.5 * 0.125)


def get_template_file_paths() -> list:
    """
    Get possible template file paths for T28 process node

    Returns:
        List of possible template file names
    """
    config = get_process_node_config()
    return config.get("template_files", [])
