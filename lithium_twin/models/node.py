"""
Supply chain node with 4 state variables:
    - inventory_on_hand: finished/dispatchable stock (post-yield)
    - backlog: dict[customer_id, float] -- unmet demand PER CUSTOMER, not
      pooled, so a node with more than one downstream customer (e.g.
      india-oem split into regions, Phase 3b) can tell which customer is
      underserved. Use total_backlog() for the pooled total.
    - in_transit: ordered from upstream, not yet arrived
    - raw_input: arrived from upstream, not yet run through produce()
      (separated from inventory_on_hand so yield loss and weekly_capacity
      are applied for real, not assumed away)

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
from dataclasses import dataclass, field
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

    # State variables (all mutable, all in kg LCE)
    inventory_on_hand: float = 0.0
    backlog: dict[str, float] = field(default_factory=dict)  # per-customer, not pooled
    in_transit: float = 0.0
    raw_input: float = 0.0

    def __post_init__(self) -> None:
        if self.yield_rate == 0.0:
            self.yield_rate = DEFAULT_YIELD[self.node_type]
        if not (0 < self.yield_rate <= 1.0):
            raise ValueError(f"yield_rate must be in (0,1], got {self.yield_rate}")
        if self.weekly_capacity <= 0:
            raise ValueError(f"weekly_capacity must be > 0, got {self.weekly_capacity}")
        if self.lead_time_weeks < 1:
            raise ValueError(f"lead_time_weeks must be >= 1, got {self.lead_time_weeks}")

    def receive_demand(self, customer_id: str, qty: float) -> None:
        """A specific downstream customer places demand. Tracked per
        customer_id (not a single pooled number) so a node serving more
        than one downstream customer -- an OEM split into regions
        (Phase 3b), or any node with more than one downstream node -- can
        tell which customer is underserved, instead of collapsing every
        shortfall into one undifferentiated figure. customer_id is either
        a real downstream node's node_id (ordinary node-to-node arcs) or a
        logical key like "market" for a node that serves demand directly
        with no arc."""
        self.backlog[customer_id] = self.backlog.get(customer_id, 0.0) + qty

    def dispatch_shipment(self, customer_id: str, qty: float) -> float:
        """
        Ships up to qty to ONE specific customer from inventory. Returns
        what was actually shipped. Partial fills happen when inventory <
        qty -- this is what propagates shortages upstream, the bullwhip
        mechanism. The caller decides how much each customer gets this
        week (e.g. engine.py's proportional rationing across several
        backlogged customers when inventory can't cover everyone) --
        this method just executes one customer's allocation.
        """
        available = min(self.inventory_on_hand, qty)
        self.inventory_on_hand -= available
        self.backlog[customer_id] = max(0.0, self.backlog.get(customer_id, 0.0) - available)
        return available

    def total_backlog(self) -> float:
        """Total unmet demand across all customers combined."""
        return sum(self.backlog.values())

    def receive_shipment(self, qty:float) -> None:
        """In-transit material arrives. Moves from in_transit to inventory."""
        if qty > self.in_transit + 1e-6:
            raise ValueError(f"Cannot receive {qty:.2f} when only {self.in_transit:.2f} is in transit.")
        self.in_transit = max(0.0, self.in_transit - qty)
        self.raw_input += qty

    def place_order(self, qty:float) -> None:
        """
        Order from upstream supplier. Increases in_transit immediately.
        Pipeline inventory convention (Sterman p.685): tracking what's already ordered prevents the model from re-ordering for goods already en route which is the root cause of bullwhip over-ordering.
        """
        self.in_transit += qty

    def produce(self) -> float:
        """
        Apply yield rate to convert input to output.
        Mass balance: output = input * yield_rate
        losses: loss = input * (1-yield_rate)
        """
        actual = min(self.raw_input, self.weekly_capacity / self.yield_rate)
        self.raw_input -= actual
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
            "backlog": round(self.total_backlog(), 3),
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
