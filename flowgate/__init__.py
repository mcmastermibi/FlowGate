"""
FlowGate — Open-source manual FCS gating application
"""

__version__ = "0.1.0"
__author__ = "FlowGate Contributors"

from .fcs_io import read_fcs, write_fcs, apply_transform
from .gates import Gate, GateHierarchy

__all__ = ["read_fcs", "write_fcs", "apply_transform", "Gate", "GateHierarchy"]
