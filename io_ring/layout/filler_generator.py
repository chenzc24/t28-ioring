#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filler Component Generation Module
Loads filler device names from process node configuration
"""

from typing import List, Optional
from .voltage_domain import VoltageDomainHandler
from .process_config import get_process_node_config

class FillerGenerator:
    """Filler Component Generator"""
    
    @staticmethod
    def _get_filler_devices() -> dict:
        """Get filler device names from configuration for T28"""
        config = get_process_node_config()
        return config.get("filler_components", {
            "analog_20": "PFILLER20A_G",
            "digital_20": "PFILLER20_G",
            "separator": "PRCUTA_G"
        })
    
    @staticmethod
    def get_filler_type(component1: dict, component2: dict) -> str:
        """Determine filler type based on voltage domains of two components"""
        domain1 = VoltageDomainHandler.get_voltage_domain(component1)
        domain2 = VoltageDomainHandler.get_voltage_domain(component2)
        
        filler_devices = FillerGenerator._get_filler_devices()
        
        # If both components are digital domain
        if domain1 == "digital" and domain2 == "digital":
            # Check if they are the same digital domain
            if VoltageDomainHandler.is_same_voltage_domain(component1, component2):
                return filler_devices.get("digital_20", "PFILLER20_G")
            else:
                # Isolation needed between different digital domains
                return filler_devices.get("separator", "PRCUTA_G")
        
        # If both components are analog domain
        if domain1 == "analog" and domain2 == "analog":
            # Check if they are the same analog domain
            if VoltageDomainHandler.is_same_voltage_domain(component1, component2):
                return filler_devices.get("analog_20", "PFILLER20A_G")
            else:
                # Isolation needed between different analog domains
                return filler_devices.get("separator", "PRCUTA_G")
        
        # Isolation needed between digital and analog domains
        if (domain1 == "digital" and domain2 == "analog") or (domain1 == "analog" and domain2 == "digital"):
            return filler_devices.get("separator", "PRCUTA_G")
        
        # Default case
        return filler_devices.get("digital_20", "PFILLER20_G")
    
    @staticmethod
    def get_filler_type_for_corner_and_pad(corner_type: str, pad1: dict, pad2: dict = None) -> str:
        """Determine filler type for corner and pad.
        
        Logic:
        - Only consider the voltage domains of the two adjacent pads around the corner
        - Do NOT check the corner's voltage domain
        1. If the two adjacent pads belong to different voltage domains, use separator (PRCUTA_G)
        2. If the two adjacent pads belong to the same voltage domain, use appropriate filler based on that domain
        """
        
        filler_devices = FillerGenerator._get_filler_devices()
        separator = filler_devices.get("separator", "PRCUTA_G")
        
        # If only one pad parameter (backward compatibility), use that pad's domain
        if pad2 is None:
            # Use appropriate filler based on pad's voltage domain
            pad_domain = VoltageDomainHandler.get_voltage_domain(pad1)
            if pad_domain == "digital":
                return filler_devices.get("digital_20", "PFILLER20_G")
            elif pad_domain == "analog":
                return filler_devices.get("analog_20", "PFILLER20A_G")
            else:
                return separator
        
        # Check if two pads belong to different voltage domains
        domain1 = VoltageDomainHandler.get_voltage_domain(pad1)
        domain2 = VoltageDomainHandler.get_voltage_domain(pad2)
        
        # If two pads belong to different voltage domains, use separator
        if domain1 != domain2:
            return separator
        
        # Check if the two pads belong to the same specific voltage domain
        pads_same_domain = VoltageDomainHandler.is_same_voltage_domain(pad1, pad2)
        
        if not pads_same_domain:
            # If pads don't belong to the same specific voltage domain, use separator
            return separator
        
        # If two pads belong to the same voltage domain, choose filler based on voltage domain type
        # Do NOT check corner's voltage domain - only use pad domains
        if domain1 == "digital":
            return filler_devices.get("digital_20", "PFILLER20_G")
        elif domain1 == "analog":
            return filler_devices.get("analog_20", "PFILLER20A_G")
        else:
            # Default case
            return filler_devices.get("digital_20", "PFILLER20_G")
    
    @staticmethod
    def create_corner_component(corner_type: str, name: str = "corner", voltage_domain: dict = None) -> dict:
        """Create corner component configuration, ensuring it contains name and appropriate voltage_domain field"""
        d = {"name": name, "device": corner_type}
        if voltage_domain:
            d["voltage_domain"] = voltage_domain
        elif corner_type == "PCORNERA_G":
            d["voltage_domain"] = {"power": "VDD_ANALOG", "ground": "VSS_ANALOG"}
        elif corner_type == "PCORNER_G":
            d["voltage_domain"] = {"power": "VDD_DIGITAL", "ground": "VSS_DIGITAL"}
        return d 