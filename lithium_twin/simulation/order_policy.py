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
    """
    demand_std = demand_mean * demand_cv
    policies = {}
    for node in graph.all_nodes():
        if node.node_id == "india-recycling":
            continue
        upstream = graph.upstream_nodes(node.node_id)
        if not upstream:
            continue
        policies[node.node_id] = BaseStockPolicy.from_demand(
            demand_mean=demand_mean,
            demand_std = demand_std,
            lead_time=node.lead_time_weeks,
            service_level=service_level,
        )
    return policies
