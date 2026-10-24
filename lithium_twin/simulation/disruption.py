"""
disruption.py — A general mechanism for temporarily degrading one parameter
of one node or arc, then restoring it.

WHY GENERIC OVER NODE vs ARC?
A real-world shock can hit either a node's own throughput (a mine's capacity
drops in a drought) or a shipping lane's throughput (a port closure, a
shipping-route disruption). Rather than writing separate machinery for
each, one Disruption spec + one SimPy process handles both by checking
whether the target is a SupplyChainNode (attribute access) or an arc dict
(key access).
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Disruption:
    """Spec for one temporary degradation of a node or arc parameter."""
    target_type: str          # "node" or "arc"
    target_id: str | tuple[str, str]  # node_id, or (from_id, to_id) for an arc
    parameter: str            # e.g. "weekly_capacity", "yield_rate", "capacity_lce"
    reduction_pct: float      # 0.0-1.0 fraction reduced (0.4 = 40% cut)
    start_week: int
    duration_weeks: int

    def __post_init__(self) -> None:
        if self.target_type not in ("node", "arc"):
            raise ValueError(f"target_type must be 'node' or 'arc', got {self.target_type!r}")
        if not (0.0 < self.reduction_pct <= 1.0):
            raise ValueError(f"reduction_pct must be in (0, 1], got {self.reduction_pct}")
        if self.start_week < 1:
            raise ValueError(f"start_week must be >= 1, got {self.start_week}")
        if self.duration_weeks < 1:
            raise ValueError(f"duration_weeks must be >= 1, got {self.duration_weeks}")

    def label(self) -> str:
        if self.target_type == "node":
            return str(self.target_id)
        from_id, to_id = self.target_id
        return f"{from_id}->{to_id}"