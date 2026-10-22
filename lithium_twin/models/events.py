"""
Event taxonomy for supply chain digital twin.
"""
from  __future__ import annotations
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class EventType(str, Enum):
    DEMAND_RECEIVED = "DEMAND_RECEIVED"
    ORDER_PLACED = "ORDER_PLACED"
    SHIPMENT_DISPATCHED = "SHIPMENT_DISPATCHED"
    SHIPMENT_RECEIVED = "SHIPMENT_RECEIVED"
    PRODUCTION_COMPLETED = "PRODUCTION_COMPLETED"
    DISRUPTION_STARTED = "DISRUPTION_STARTED"
    DISRUPTION_ENDED = "DISRUPTION_ENDED"
    INVENTORY_CHECKED = "INVENTORY_CHECKED"
    EXTERNAL_SUPPLY = "EXTERNAL_SUPPLY"

@dataclass
class SupplyChainEvent:
    """
    Immutable record of one state transition.
    Once created and appended to the log, never modified.
    """
    event_type: EventType
    source_node: str
    week: int
    quantity_lce: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.week<1:
            raise ValueError(f"week must be >=1")
        if self.quantity_lce<0:
            raise ValueError(f"quantity_lce cannot be negative, got {self.quantity_lce}")
        flow_events = {
            EventType. DEMAND_RECEIVED, EventType.ORDER_PLACED, EventType.SHIPMENT_DISPATCHED, EventType.SHIPMENT_RECEIVED, EventType.PRODUCTION_COMPLETED,
        }
        if self.event_type in flow_events and self.quantity_lce==0.0:
            raise ValueError(
                f"Flow event {self.event_type} must have quantity_lce > 0. "
                f"Use INVENTORY_CHECKED for zero-quantity snapshots."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_node": self.source_node,
            "week": self.week,
            "quantity_lce": self.quantity_lce,
            "payload": self.payload,
        }

class EventLog:
    def __init__(self) -> None:
        self._log: list[SupplyChainEvent] = []

    def append(self, event: SupplyChainEvent) -> None:
        ids = {e.event_id for e in self._log}
        if event.event_id in ids:
            raise ValueError(f"Duplicate event_id '{event.event_id}'.")
        self._log.append(event)

    def query(self, node_id: str | None=None, event_type: EventType | None=None, week_start: int | None=None, week_end: int | None=None) -> list[SupplyChainEvent]:
        results = self._log
        if node_id:
            results = [e for e in results if e.source_node == node_id]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if week_start is not None:
            results = [e for e in results if e.week >= week_start]
        if week_end is not None:
            results = [e for e in results if e.week <= week_end]
        return results

    def total_flow(self, event_type: EventType | None=None, node_id: str | None=None, week_start: int | None=None, week_end: int | None=None) -> float:
        """Sum quantity_lce for a filtered event set. Used in mass balance tests."""
        return sum(e.quantity_lce for e in self.query(event_type=event_type, node_id=node_id, week_start=week_start, week_end=week_end))

    def __len__(self) -> int:
        return len(self._log)


