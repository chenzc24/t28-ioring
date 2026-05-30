#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Device Template Parser - Specialized for parsing SKILL output and generating device templates
"""

import json
from pathlib import Path

class DeviceTemplate:
    def __init__(self):
        self.center_x = 0
        self.center_y = 0
        self.pins = []
        self.device_lib = ""
        self.device_cell = ""
        self.device_view = ""
    
    def load_from_skill_output(self, skill_output):
        lines = skill_output.strip().split('\n')
        for line in lines:
            if line.startswith('DEVICE_INFO:'):
                parts = line.replace('DEVICE_INFO: ', '').split(',')
                if len(parts) == 3:
                    self.device_lib = parts[0]
                    self.device_cell = parts[1]
                    self.device_view = parts[2]
            elif line.startswith('DEVICE_CENTER:'):
                parts = line.replace('DEVICE_CENTER: ', '').split(',')
                self.center_x = float(parts[0])
                self.center_y = float(parts[1])
            elif line.startswith('PIN_TEMPLATE:'):
                parts = line.replace('PIN_TEMPLATE: ', '').split(',')
                if len(parts) == 4:
                    self.pins.append({
                        'name': parts[0],
                        'x': float(parts[1]),
                        'y': float(parts[2]),
                        'original_side': parts[3]
                    })
    
    def to_dict(self):
        """Convert to dictionary format for JSON serialization"""
        return {
            'center_x': self.center_x,
            'center_y': self.center_y,
            'pins': self.pins,
            'device_lib': self.device_lib,
            'device_cell': self.device_cell,
            'device_view': self.device_view
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create DeviceTemplate object from dictionary"""
        template = cls()
        template.center_x = data['center_x']
        template.center_y = data['center_y']
        template.pins = data['pins']
        template.device_lib = data['device_lib']
        template.device_cell = data['device_cell']
        template.device_view = data['device_view']
        return template

class DeviceTemplateManager:
    def __init__(self):
        self.templates = {}
        # Define default pin configuration rules for device types
        self.device_pin_rules = {
            'PDB3AC_H_G': {
                'AIO': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name to generate label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Fixed name
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Fixed name
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Fixed name
                }
            },
            'PDB3AC_V_G': {
                'AIO': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name to generate label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Fixed name
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Fixed name
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Fixed name
                }
            },
            'PVSS1AC_H_G': {
                'AVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Fixed name
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Fixed name
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Fixed name
                }
            },
            'PVSS1AC_V_G': {
                'AVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Fixed name
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Fixed name
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Fixed name
                }
            },
            'PVDD1AC_H_G': {
                'AVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Fixed name
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Fixed name
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Fixed name
                }
            },
            'PVDD1AC_V_G': {
                'AVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Fixed name
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Fixed name
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Fixed name
                }
            },
            'PVDD3A_H_G': {
                'TAVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TAVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Voltage domain VSS
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVDD3A_V_G': {
                'TAVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TAVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Voltage domain VSS
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVSS3A_H_G': {
                'TAVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TAVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Voltage domain VDD
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVSS3A_V_G': {
                'TAVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TAVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Voltage domain VDD
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVDD3AC_H_G': {
                'TACVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Voltage domain VSS
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVDD3AC_V_G': {
                'TACVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TACVSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VSSIB'  # Voltage domain VSS
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVSS3AC_H_G': {
                'TACVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Voltage domain VDD
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVSS3AC_V_G': {
                'TACVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'AVSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Use pad name_CORE as label
                },
                'TACVDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VDDIB'  # Voltage domain VDD
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Grounded together
                }
            },
            'PVSS1DGZ_H_G': {
                'VSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVSS1DGZ_V_G': {
                'VSS': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVDD1DGZ_H_G': {
                'VDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVDD1DGZ_V_G': {
                'VDD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVDD2POC_H_G': {
                'VDDPST': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVDD2POC_V_G': {
                'VDDPST': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVSS2DGZ_H_G': {
                'VSSPST': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PVSS2DGZ_V_G': {
                'VSSPST': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                }
            },
            'PDDW16SDGZ_H_G': {
                'PAD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                },
                'REN': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Default input IO configuration
                },
                'OEN': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Default input IO configuration
                },
                'C': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Default input IO configuration
                },
                'I': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Default input IO configuration
                }
            },
            'PDDW16SDGZ_V_G': {
                'PAD': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}'  # Use pad name as label
                },
                'VSSPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOH'  # Digital high voltage ground
                },
                'VDDPST': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOH'  # Digital high voltage power
                },
                'VDD': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Digital low voltage power
                },
                'VSS': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Digital low voltage ground
                },
                'POC': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'POC'  # POC
                },
                'REN': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Default input IO configuration
                },
                'OEN': {
                    'create_pin': False,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'VIOL'  # Default input IO configuration
                },
                'C': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': '{pad_name}_CORE'  # Default input IO configuration
                },
                'I': {
                    'create_pin': True,
                    'create_wire': True,
                    'create_label': True,
                    'label_pattern': 'GIOL'  # Default input IO configuration
                }
            },
            'PRUW08SDGZ_H_G': {
                'PAD': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'VSSPST': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOH'},
                'VDDPST': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VIOH'},
                'VDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VIOL'},
                'VSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'POC': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'POC'},
                'REN': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'OEN': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VIOL'},
                'C': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}_CORE'},
                'I': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'}
            },
            'PRUW08SDGZ_V_G': {
                'PAD': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'VSSPST': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOH'},
                'VDDPST': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VIOH'},
                'VDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VIOL'},
                'VSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'POC': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'POC'},
                'REN': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'OEN': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VIOL'},
                'C': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}_CORE'},
                'I': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'}
            },
            'PVDD1A_H_G': {
                'AVDD': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'TAVSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VSSIB'},
                'VSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'TAVDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VDDIB'}
            },
            'PVDD1A_V_G': {
                'AVDD': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'TAVSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VSSIB'},
                'VSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'TAVDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VDDIB'}
            },
            'PVSS1A_H_G': {
                'AVSS': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'TAVSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VSSIB'},
                'VSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'TAVDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VDDIB'}
            },
            'PVSS1A_V_G': {
                'AVSS': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'TAVSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VSSIB'},
                'VSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'GIOL'},
                'TAVDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VDDIB'}
            },
            'PVSS2A_H_G': {
                'VSS': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'TAVSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VSSIB'},
                'TAVDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VDDIB'}
            },
            'PVSS2A_V_G': {
                'VSS': {'create_pin': True, 'create_wire': True, 'create_label': True, 'label_pattern': '{pad_name}'},
                'TAVSS': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VSSIB'},
                'TAVDD': {'create_pin': False, 'create_wire': True, 'create_label': True, 'label_pattern': 'VDDIB'}
            }
        }

    def add_template(self, template_name, template):
        self.templates[template_name] = template
    
    def get_template(self, template_name):
        return self.templates.get(template_name)
    
    def get_pin_config(self, device_type, pin_name, pad_name, io_type='input', pin_label=None, vdd_label=None, vss_label=None, vddpst_label=None, vsspst_label=None):
        """Get default configuration based on device type and pin name, auxiliary pins prioritize main power/ground labels."""
        if device_type in self.device_pin_rules:
            if pin_name in self.device_pin_rules[device_type]:
                rule = self.device_pin_rules[device_type][pin_name].copy()
                
                # Prioritize the passed pin_label
                if pin_label is not None:
                    rule['label'] = pin_label
                else:
                    # Handle special IO configuration for digital IO devices; auxiliary pins dynamically follow main power/ground labels
                    is_pruw08 = device_type in ['PRUW08SDGZ_H_G', 'PRUW08SDGZ_V_G']
                    is_pddw16 = device_type in ['PDDW16SDGZ_H_G', 'PDDW16SDGZ_V_G']
                    if (is_pddw16 or is_pruw08) and io_type in ['input', 'output']:
                        if pin_name == 'REN':
                            if io_type == 'input':
                                if is_pruw08:
                                    rule['label'] = vdd_label if vdd_label is not None else 'VIOL'  # PRUW08 input: REN to VDD
                                else:
                                    rule['label'] = vss_label if vss_label is not None else 'GIOL'  # PDDW16 input: REN to VSS
                            else:  # output — both PDDW16 and PRUW08: REN to VDD
                                rule['label'] = vdd_label if vdd_label is not None else 'VIOL'
                        elif pin_name == 'OEN':
                            if io_type == 'input':
                                rule['label'] = vdd_label if vdd_label is not None else 'VIOL'  # Input OEN to VDD (both devices)
                            else:  # output — both PDDW16 and PRUW08: OEN to VSS
                                rule['label'] = vss_label if vss_label is not None else 'GIOL'
                        elif pin_name == 'C':
                            if io_type == 'input':
                                rule['label'] = f'{pad_name}_CORE'  # Input IO: C connected to name_CORE
                                rule['create_pin'] = True  # Pin created when connected to _CORE
                            else:  # output
                                rule['label'] = 'noConn'  # Output IO: C connected to noConn
                                rule['create_pin'] = False  # No pin created when connected to noConn
                        elif pin_name == 'I':
                            if io_type == 'input':
                                rule['label'] = vss_label if vss_label is not None else 'GIOL'  # Input I set to low level
                                rule['create_pin'] = False  # No pin created when connected to fixed name
                            else:  # output
                                rule['label'] = f'{pad_name}_CORE'  # Output IO: I connected to name_CORE
                                rule['create_pin'] = True  # Pin created when connected to _CORE
                        elif pin_name == 'VDD':
                            # VDD pin prioritizes vdd_label, otherwise uses default
                            rule['label'] = vdd_label if vdd_label is not None else 'VIOL'
                        elif pin_name == 'VSS':
                            # VSS pin prioritizes vss_label, otherwise uses default
                            rule['label'] = vss_label if vss_label is not None else 'GIOL'
                        elif pin_name == 'VDDPST':
                            # VDDPST pin prioritizes vddpst_label, otherwise uses default
                            rule['label'] = vddpst_label if vddpst_label is not None else 'VIOH'
                        elif pin_name == 'VSSPST':
                            # VSSPST pin prioritizes vsspst_label, otherwise uses default
                            rule['label'] = vsspst_label if vsspst_label is not None else 'GIOH'
                        else:
                            # Other pins use label_pattern
                            if 'label_pattern' in rule:
                                rule['label'] = rule['label_pattern'].format(pad_name=pad_name)
                    else:
                        # Handle label_pattern for other device types
                        if 'label_pattern' in rule:
                            rule['label'] = rule['label_pattern'].format(pad_name=pad_name)
                return rule
        # Default configuration (compatible with other device types)
        return {
            'create_pin': True,
            'create_wire': True,
            'create_label': True,
            'label': pin_label if pin_label is not None else pin_name
        }
    
    def load_templates_from_skill_output(self, skill_output):
        """Load templates from SKILL output"""
        blocks = skill_output.split('TEMPLATE_END')
        for block in blocks:
            if 'DEVICE_INFO:' in block:
                template = DeviceTemplate()
                template.load_from_skill_output(block + 'TEMPLATE_END')
                if template.device_cell:
                    self.add_template(template.device_cell, template)
    
    def save_templates_to_json(self, file_path):
        """Save templates to JSON file"""
        templates_dict = {}
        for name, template in self.templates.items():
            templates_dict[name] = template.to_dict()
        
        # Also save pin rules
        data = {
            'templates': templates_dict,
            'pin_rules': self.device_pin_rules
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_templates_from_json(self, file_path):
        """Load templates from JSON file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Load templates
        templates_dict = data.get('templates', {})
        for name, template_data in templates_dict.items():
            template = DeviceTemplate.from_dict(template_data)
            self.add_template(name, template)
        
        # Load pin rules
        if 'pin_rules' in data:
            self.device_pin_rules = data['pin_rules']

def parse_and_save_templates():
    """Parse SKILL output and save as JSON file"""
    # Load SKILL output data from external file
    skill_output_file = "skill_output_data.txt"
    
    try:
        with open(skill_output_file, 'r', encoding='utf-8') as f:
            complete_skill_output = f.read()
    except FileNotFoundError:
        print(f"[ERROR] Error: SKILL output file '{skill_output_file}' not found")
        print("Please ensure the file exists in the current directory")
        return None
    except Exception as e:
        print(f"[ERROR] Error reading SKILL output file: {e}")
        return None

    # Create template manager and parse
    template_manager = DeviceTemplateManager()
    template_manager.load_templates_from_skill_output(complete_skill_output)
    
    # Save to JSON file
    output_file = "device_templates.json"
    template_manager.save_templates_to_json(output_file)
    
    print(f"[OK] Successfully parsed and saved {len(template_manager.templates)} device templates to {output_file}")
    print("Available device types:")
    for device_type in sorted(template_manager.templates.keys()):
        print(f"  - {device_type}")
    
    print("\n📋 Configured pin rules:")
    for device_type, rules in template_manager.device_pin_rules.items():
        print(f"  {device_type}:")
        for pin_name, rule in rules.items():
            print(f"    {pin_name}: {rule}")
    
    return template_manager

if __name__ == "__main__":
    parse_and_save_templates() 