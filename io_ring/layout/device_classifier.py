#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Device Type Classification Module for T28 (28nm)
Loads device lists from process node configuration files
"""

import json
from pathlib import Path
from typing import Dict

# Get config directory path
_CONFIG_DIR = Path(__file__).parent / "config"


def _normalize_process_node(process_node: str) -> str:
    """Normalize process node aliases to canonical values used by scripts."""
    value = str(process_node or "").strip().upper()
    alias_map = {
        "28": "T28",
        "28NM": "T28",
        "T28": "T28",
        "180": "T180",
        "180NM": "T180",
        "T180": "T180",
    }
    if value in alias_map:
        return alias_map[value]
    raise ValueError(f"Unsupported process node: {process_node}")


def _load_device_config() -> Dict:
    """Load device configuration from JSON file in config directory"""
    config_file = _CONFIG_DIR / "lydevices_28.json"

    if not config_file.exists():
        raise FileNotFoundError(
            f"Device configuration file not found: {config_file}. "
            f"Please ensure config file exists for T28 process node."
        )

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse device configuration file {config_file}: {e}"
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to load device configuration file {config_file}: {e}"
        )


class DeviceClassifier:
    """Device Type Classifier - Loads device lists from configuration files"""

    # Cache for device lists
    _device_lists_cache = {}

    def __init__(self):
        """Initialize classifier for T28 process node"""
        # Load device lists
        self._data = self._get_device_lists()

    @staticmethod
    def _load_device_config() -> Dict:
        """Class wrapper for module loader used by cached list initialization."""
        return _load_device_config()

    @classmethod
    def _get_device_lists(cls) -> dict:
        """Get device lists for T28 process node (with caching)

        Returns:
            Dictionary containing device lists

        Raises:
            ValueError: If config file is missing
        """
        if not cls._device_lists_cache:
            # Load from config file
            config = cls._load_device_config()

            # Extract device lists from config
            device_lists = {
                "digital_devices": config.get("digital_devices", []),
                "analog_devices": config.get("analog_devices", []),
                "digital_io": config.get("digital_io", []),
                "corner_devices": config.get("corner_devices", []),
                "filler_devices": config.get("filler_devices", []),
                "cut_devices": config.get("cut_devices", [])
            }

            cls._device_lists_cache = device_lists

        return cls._device_lists_cache

    @staticmethod
    def is_digital_device(device_type: str) -> bool:
        """Check if it's a digital device"""
        device_lists = DeviceClassifier._get_device_lists()
        return device_type in device_lists.get("digital_devices", [])

    @staticmethod
    def is_analog_device(device_type: str) -> bool:
        """Check if it's an analog device"""
        device_lists = DeviceClassifier._get_device_lists()
        return device_type in device_lists.get("analog_devices", [])

    @staticmethod
    def is_digital_io_device(device_type: str) -> bool:
        """Check if it's a digital IO device"""
        device_lists = DeviceClassifier._get_device_lists()
        return device_type in device_lists.get("digital_io", [])

    @staticmethod
    def is_corner_device(device_type: str) -> bool:
        """Check if it's a corner component"""
        device_lists = DeviceClassifier._get_device_lists()
        return device_type in device_lists.get("corner_devices", [])

    @staticmethod
    def is_filler_device(device_type: str) -> bool:
        """Check if it's a filler component"""
        device_lists = DeviceClassifier._get_device_lists()
        return device_type in device_lists.get("filler_devices", [])

    @staticmethod
    def is_separator_device(device_type: str) -> bool:
        """Check if it's a separator component"""
        device_lists = DeviceClassifier._get_device_lists()
        return device_type in device_lists.get("cut_devices", [])

    # Instance methods (matching merge_source interface)
    def is_filler(self, device_type: str) -> bool:
        """Check if it's a filler component (instance method, matching merge_source)"""
        return device_type in set(self._data.get('filler_devices', []))

    def is_corner(self, device_type: str) -> bool:
        """Check if it's a corner component (instance method, matching merge_source)"""
        return device_type in set(self._data.get('corner_devices', []))

    def is_digital_device_instance(self, device_type: str) -> bool:
        """Check if it's a digital device (instance method)"""
        return device_type in set(self._data.get('digital_devices', []))

    def is_analog_device_instance(self, device_type: str) -> bool:
        """Check if it's an analog device (instance method)"""
        return device_type in set(self._data.get('analog_devices', []))

    def is_digital_io_instance(self, device_type: str) -> bool:
        """Check if it's a digital IO device (instance method)"""
        return device_type in set(self._data.get('digital_io', []))
