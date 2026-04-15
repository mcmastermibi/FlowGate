"""
gates.py — Gate data model for FlowGate
Supports Polygon, Rectangle, and Quadrant gates
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import json
import uuid
from matplotlib.path import Path


@dataclass
class Gate:
    """Base class for a single gate."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Gate"
    x_channel: str = ""
    y_channel: str = ""
    parent_id: Optional[str] = None   # None = root (applied to all events)
    gate_type: str = "polygon"        # "polygon" | "rectangle" | "threshold"
    color: str = "#00C8FF"
    # Polygon vertices in DISPLAY (transformed) space
    vertices: List[Tuple[float, float]] = field(default_factory=list)
    # Rectangle bounds in display space
    rect_bounds: Optional[Tuple[float, float, float, float]] = None  # x0,y0,x1,y1
    # Threshold (1D gate)
    threshold_value: Optional[float] = None
    threshold_channel: Optional[str] = None
    threshold_direction: str = "above"   # "above" | "below"
    # Per-axis transform settings (recorded at gate creation time)
    x_transform: str = "asinh"
    y_transform: str = "asinh"
    x_cofactor: float = 150.0
    y_cofactor: float = 150.0

    def apply(self, display_data: np.ndarray, x_idx: int, y_idx: int) -> np.ndarray:
        """
        Apply gate to display_data (n_events x n_channels, already transformed).
        Returns boolean mask of passing events.
        """
        if self.gate_type == "polygon" and len(self.vertices) >= 3:
            pts = display_data[:, [x_idx, y_idx]]
            path = Path(self.vertices)
            return path.contains_points(pts)

        elif self.gate_type == "rectangle" and self.rect_bounds is not None:
            x0, y0, x1, y1 = self.rect_bounds
            xmin, xmax = min(x0, x1), max(x0, x1)
            ymin, ymax = min(y0, y1), max(y0, y1)
            xvals = display_data[:, x_idx]
            yvals = display_data[:, y_idx]
            return (xvals >= xmin) & (xvals <= xmax) & (yvals >= ymin) & (yvals <= ymax)

        elif self.gate_type == "threshold":
            ch_idx = x_idx if self.threshold_channel == self.x_channel else y_idx
            vals = display_data[:, ch_idx]
            if self.threshold_direction == "above":
                return vals >= self.threshold_value
            else:
                return vals <= self.threshold_value

        return np.ones(len(display_data), dtype=bool)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "x_channel": self.x_channel,
            "y_channel": self.y_channel,
            "parent_id": self.parent_id,
            "gate_type": self.gate_type,
            "color": self.color,
            "vertices": self.vertices,
            "rect_bounds": self.rect_bounds,
            "threshold_value": self.threshold_value,
            "threshold_channel": self.threshold_channel,
            "threshold_direction": self.threshold_direction,
            "x_transform": self.x_transform,
            "y_transform": self.y_transform,
            "x_cofactor": self.x_cofactor,
            "y_cofactor": self.y_cofactor,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Gate":
        g = cls()
        for k, v in d.items():
            if hasattr(g, k):
                setattr(g, k, v)
        if g.vertices:
            g.vertices = [tuple(v) for v in g.vertices]
        return g


class GateHierarchy:
    """
    Manages a tree of gates and computes event membership.
    Each gate's population = parent population ∩ this gate.
    """

    def __init__(self):
        self.gates: List[Gate] = []

    def add_gate(self, gate: Gate):
        self.gates.append(gate)

    def remove_gate(self, gate_id: str):
        # Also remove children
        children = [g for g in self.gates if g.parent_id == gate_id]
        for child in children:
            self.remove_gate(child.id)
        self.gates = [g for g in self.gates if g.id != gate_id]

    def get_gate(self, gate_id: str) -> Optional[Gate]:
        for g in self.gates:
            if g.id == gate_id:
                return g
        return None

    def get_children(self, parent_id: Optional[str]) -> List[Gate]:
        return [g for g in self.gates if g.parent_id == parent_id]

    def compute_mask(
        self,
        gate_id: str,
        display_data: np.ndarray,
        channel_names: List[str],
    ) -> np.ndarray:
        """Recursively compute the boolean event mask for a gate."""
        gate = self.get_gate(gate_id)
        if gate is None:
            return np.ones(len(display_data), dtype=bool)

        # Get parent mask
        if gate.parent_id is None:
            parent_mask = np.ones(len(display_data), dtype=bool)
        else:
            parent_mask = self.compute_mask(gate.parent_id, display_data, channel_names)

        # Map channel names to indices
        try:
            x_idx = channel_names.index(gate.x_channel)
            y_idx = channel_names.index(gate.y_channel) if gate.y_channel else x_idx
        except ValueError:
            return parent_mask

        own_mask = gate.apply(display_data, x_idx, y_idx)
        return parent_mask & own_mask

    def get_gate_stats(
        self,
        gate_id: str,
        display_data: np.ndarray,
        channel_names: List[str],
    ) -> dict:
        """Return count and % of parent for a gate."""
        gate = self.get_gate(gate_id)
        total = len(display_data)

        own_mask = self.compute_mask(gate_id, display_data, channel_names)
        count = own_mask.sum()

        if gate.parent_id is None:
            parent_count = total
        else:
            parent_mask = self.compute_mask(gate.parent_id, display_data, channel_names)
            parent_count = parent_mask.sum()

        pct_parent = (count / parent_count * 100) if parent_count > 0 else 0
        pct_total = (count / total * 100) if total > 0 else 0

        return {
            "count": int(count),
            "parent_count": int(parent_count),
            "total": total,
            "pct_parent": pct_parent,
            "pct_total": pct_total,
        }

    def get_event_indices(
        self,
        gate_id: str,
        display_data: np.ndarray,
        channel_names: List[str],
    ) -> np.ndarray:
        """Return indices of events passing a gate (for export)."""
        mask = self.compute_mask(gate_id, display_data, channel_names)
        return np.where(mask)[0]

    def save(self, filepath: str):
        data = [g.to_dict() for g in self.gates]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: str):
        with open(filepath, "r") as f:
            data = json.load(f)
        self.gates = [Gate.from_dict(d) for d in data]
