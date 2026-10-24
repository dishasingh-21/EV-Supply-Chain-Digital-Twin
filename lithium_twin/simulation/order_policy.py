"""
Base stock replenishment policy with safety stock.
"""
from __future__ import annotations
from dataclasses import dataclass
from scipy.stats import norm

@dataclass
class BaseStockPolicy:
    """Base stock replenishment policy for one node."""
    base_stock_level: float
    safety_stock: float
    demand_mean: float
    lead_time: int
    smoothing_alpha: float = 0.35

    @classmethod
    def from_demand(cls, demand_mean: float, demand_std: float, lead_time: int, service_level: float=0.95) -> "BaseStockPolicy":
        """Compute base stock level from demand statistics.
        Args:
            demand_mean: Mean weekly demand this node sees (kg LCE).
            demand_std: Standard deviation of weekly demand (kg LCE).
            lead_time: Node's lead time in weeks.
            service_level: Target fill rate.
        Returns:
            Calibrated BaseStockPolicy instance.
        """
        z = float(norm.ppf(service_level))
        safety_stock = z * demand_std * (lead_time ** 0.5)
        base_stock = demand_mean * lead_time + safety_stock
        return cls(
            base_stock_level=round(base_stock, 2), safety_stock=round(safety_stock, 2), demand_mean=demand_mean, lead_time=lead_time,
        )

    def order_quantity(self, inventory_position: float) -> float:
        """
        How much to order this week.
        Returns max(0, S-inventory_position). If already above S, then return 0 i.e., no order placed.
        """
        gap = self.base_stock_level - inventory_position
        return max(0.0, self.demand_mean + self.smoothing_alpha * gap)

    def summary(self) -> str:
        return (
            f"BaseStockPolicy: S={self.base_stock_level:,.0f} kg LCE "
            f"(LT={self.lead_time} weeks, SS={self.safety_stock:,.0f} kg LCE)"
        )

    def recalibrate(self, demand_samples: list[float], service_level: float=0.95) -> None:
        """Recompute base_stock_level and safety_stock from observed demand."""
        import statistics
        if len(demand_samples) < 2:
            return
        new_mean = statistics.mean(demand_samples)
        new_std = statistics.stdev(demand_samples)
        z = float(norm.ppf(service_level))
        self.safety_stock = round(z * new_std * (self.lead_time ** 0.5), 2)
        self.base_stock_level = round(new_mean * self.lead_time + self.safety_stock, 2)
        self.demand_mean = new_mean


def build_policies(
        graph, demand_mean: float, demand_cv: float = 0.15, service_level: float = 0.95,
):
    """
    Build a base stock policy for every non-source node in the graph.

    demand_mean per node is its own REQUIRED INPUT -- how much it must
    RECEIVE from its upstream supplier per week to sustain its required
    OUTPUT once its own yield loss is applied (required_output / yield_rate).
    This is the correct unit for order_quantity()/base_stock_level, since
    both represent a RECEIVING target (orders arrive as raw_input), and it
    matches capacity.py's arc-sizing units exactly. Using required OUTPUT
    directly (an earlier version of this fix) chronically understated
    every non-OEM node's order target by its own yield loss.

    lead_time per node uses its INCOMING ARC's lead_time_weeks — the actual
    transit delay _shipment_process enforces between an order and its
    arrival — not node.lead_time_weeks, an independently-set JSON field
    never consumed by the engine's own timing logic. Using the wrong value
    here produces a base_stock_level that doesn't match the real
    replenishment delay, chronically over- or under-sizing safety stock.
    """
    from lithium_twin.simulation.capacity import compute_required_node_outputs

    required_outputs = compute_required_node_outputs(graph, demand_mean)
    policies = {}
    for node in graph.all_nodes():
        if node.node_id == "india-recycling":
            continue
        upstream = graph.upstream_nodes(node.node_id)
        if not upstream:
            continue
        upstream_id = upstream[0]
        arc = graph.arc_data(upstream_id, node.node_id)
        replenishment_lead_time = arc["lead_time_weeks"]

        required_output = required_outputs.get(node.node_id, demand_mean)
        node_demand_mean = required_output / node.yield_rate  # input, not output
        node_demand_std = node_demand_mean * demand_cv
        policies[node.node_id] = BaseStockPolicy.from_demand(
            demand_mean=node_demand_mean,
            demand_std=node_demand_std,
            lead_time=replenishment_lead_time,
            service_level=service_level,
        )
    return policies