#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Layout Validation Module
"""

from typing import List, Dict

class LayoutValidator:
    """Layout Validator"""
    
    @staticmethod
    def validate_layout_rules(layout_components: List[dict], process_node: str = "T28") -> dict:
        """Validate layout rules
        
        Args:
            layout_components: List of layout components to validate
            process_node: Process node (e.g., "T28", "T180") - reserved for future use
        """
        if not layout_components:
            return {"valid": False, "message": "Component list is empty"}
        
        # Group components by direction
        sides = {
            "R0": [],    # Bottom edge
            "R90": [],   # Right edge
            "R180": [],  # Top edge
            "R270": []   # Left edge
        }
        
        # Classify components
        for component in layout_components:
            if component.get("type") in ["pad", "corner"]:
                orientation = component.get("orientation", "R0")
                sides[orientation].append(component)
        
        # Collect side counts
        left_count = len(sides["R270"])
        right_count = len(sides["R90"])
        top_count = len(sides["R180"])
        bottom_count = len(sides["R0"])

        # For legacy T28, keep opposite-side parity checks.
        # T180 allows asymmetric side counts and should not be blocked here.
        if process_node != "T180":
            if left_count != right_count:
                return {
                    "valid": False,
                    "message": f"Left and right side counts don't match: left {left_count}, right {right_count}"
                }
            if top_count != bottom_count:
                return {
                    "valid": False,
                    "message": f"Top and bottom side counts don't match: top {top_count}, bottom {bottom_count}"
                }
        
        # Validate that each direction has at least one component
        for orientation, components in sides.items():
            if not components:
                return {
                    "valid": False, 
                    "message": f"Direction {orientation} has no components"
                }
        
        # Validate component positions are reasonable
        for component in layout_components:
            if "position" not in component or len(component["position"]) != 2:
                return {
                    "valid": False, 
                    "message": f"Component {component.get('name', 'unknown')} position format error"
                }
            
            if "orientation" not in component:
                return {
                    "valid": False, 
                    "message": f"Component {component.get('name', 'unknown')} missing orientation information"
                }
        
        return {
            "valid": True, 
            "message": "Layout rule validation passed",
            "stats": {
                "left_count": left_count,
                "right_count": right_count,
                "top_count": top_count,
                "bottom_count": bottom_count,
                "total_components": len(layout_components)
            }
        } 