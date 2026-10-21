"""
Supply chain node with 3 canonical state variables (inventory_on_hand, backlog, in_transit).

Yield rate sources:
    - Mining (brine): 0.90 (Source: IEA Critical Minerals 2022; ~8% evaporation/seepage)
    - Chemical processing: 0.90 (Source: Benchmark Mineral Intellingence 2023 cost model)
    - Precursor (CAM): 0.95 (Source: CATL benchmark, cited Bloomberg 2022)
    - Cell Manufacturing: 0.96 (Source: IEA 2023 battery supply chain; range 94-97%)
    - Pack Assembly: 0.99 (Dunn et al. 2021, Joule)
    - OEM: 1.00 (No material transformation)
    - Recycling: 0.72 (Source: Harper et al. 2019, Nature; hydromet Li recovery)
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class NodeType(str, Enum):
    EXTRACTOR = "extractor"
    PROCESSOR = "processor"
    MANUFACTURER = "manufacturer"
    ASSEMBLER = "assembler"
    OEM = "oem"
    RECYCLER = "recycler"

DEFAULT_YIELD: dict[NodeType,float]={
    NodeType.EXTRACTOR: 0.9,
    NodeType.PROCESSOR: 0.9,
    NodeType.MANUFACTURER: 0.95,
    NodeType.ASSEMBLER: 0.97,
    NodeType.OEM: 1.00,
    NodeType.RECYCLER: 0.72,
}

@dataclass
class SupplyChainNode:
    node_id: str
    node_type: NodeType
    location: str
    weekly_capacity: float
    lead_time_weeks: int
    yield_rate: float = 0.0

    # The 3 Sterman state variables (all mutable, all in kg LCE)
    inventory_on_hand: float = 0.0
    backlog: float = 0.0
    in_transit: float = 0.0

    def __post_init__(self) -> None:
        if self.yield_rate == 0.0:
            self.yield_rate = DEFAULT_YIELD[self.node_type]
        if not (0 < self.yield_rate <= 1.0):
            raise ValueError(f"yield_rate must be in (0,1], got {self.yield_rate}")
        if self.weekly_capacity <= 0:
            raise ValueError(f"weekly_capacity must be > 0, got {self.weekly_capacity}")
        if self.lead_time_weeks < 1:
            raise ValueError(f"lead_time_weeks must be >= 1, got {self.lead_time_weeks}")

    def receive_demand(self, qty: float) -> None:
        """Downstream places an order. Increases backlog."""
        self.backlog += qty

    def dispatch_shipment(self, qty:float) -> float:
        """
        Ships up to qty from inventory. Returns what was actually shipped.
        Partial fills happen when inventory < backlog. This is what propagates shortages upstream, the bullwhip mechanism.
        """
        available = min(self.inventory_on_hand, qty)
        self.inventory_on_hand -= available
        self.backlog -= available
        return available

    def receive_shipment(self, qty:float) -> None:
        """In-transit material arrives. Moves from in_transit to inventory."""
        if qty > self.in_transit + 1e-6:
            raise ValueError(f"Cannot receive {qty:.2f} when only {self.in_transit:.2f} is in transit.")
        self.in_transit = max(0.0, self.in_transit - qty)
        self.inventory_on_hand += qty

    def place_order(self, qty:float) -> None:
        """
        Order from upstream supplier. Increases in_transit immediately.
        Pipeline inventory convention (Sterman p.685): tracking what's already ordered prevents the model from re-ordering for goods already en route which is the root cause of bullwhip over-ordering.
        """
        self.in_transit += qty

    def produce(self, input_lce: float) -> float:
        """
        Apply yield rate to convert input to output.
        Mass balance: output = input * yield_rate
        losses: loss = input * (1-yield_rate)
        """
        actual = min(input_lce, self.weekly_capacity/self.yield_rate)
        self.inventory_on_hand -= actual
        output = actual * self.yield_rate
        self.inventory_on_hand += output
        return output

    def total_supply_position(self) -> float:
        """
        inventory_on_hand + in_transit.
        Standard inventory formula = don't reorder if supply position
        already covers demand during the lead time.
        (Silver, Pyke & Thomas 2017, "Inventory and Production Management")
        """
        return self.inventory_on_hand + self.in_transit

    def state_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "inventory_on_hand": round(self.inventory_on_hand,3),
            "backlog": round(self.backlog, 3),
            "in_transit": round(self.in_transit, 3),
            "yield_rate": self.yield_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SupplyChainNode":
        return cls(
            node_id = data["node_id"],
            node_type = NodeType(data["node_type"]),
            location = data["location"],
            weekly_capacity = data["weekly_capacity_lce"],
            lead_time_weeks = data["lead_time_weeks"],
            yield_rate = data.get("yield_rate", 0.0),
            inventory_on_hand = data.get("initial_inventory_lce", 0.0)
        )
