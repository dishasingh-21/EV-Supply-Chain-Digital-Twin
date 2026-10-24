"""
regional_demo.py -- Phase 3b demo: split india-oem's demand across
Rajasthan's warehouse regions (server/data/warehouses.xlsx) instead of one
undifferentiated national market, and report per-region fill rates.

HOW TO RUN:
  python -m lithium_twin.regional_demo
"""
from __future__ import annotations
from lithium_twin.models.graph import SupplyChainGraph
from lithium_twin.models.events import EventLog
from lithium_twin.simulation.demand import DemandGenerator
from lithium_twin.simulation.order_policy import build_policies
from lithium_twin.simulation.capacity import set_generous_capacities
from lithium_twin.simulation.engine import SupplyChainEngine
from lithium_twin.regions import load_regions, region_demand_weights
from lithium_twin.main import CHAIN_JSON, DEMAND_MEAN, DEMAND_CV, SERVICE_LEVEL


def run_regional_demo(weeks: int = 104, seed: int = 42) -> SupplyChainEngine:
    regions = load_regions()
    weights = region_demand_weights(regions)

    graph = SupplyChainGraph.from_json(CHAIN_JSON)
    set_generous_capacities(graph, DEMAND_MEAN)
    log = EventLog()
    demand_gen = DemandGenerator(mean=DEMAND_MEAN, cv=DEMAND_CV, seed=seed)
    policies = build_policies(graph, DEMAND_MEAN, DEMAND_CV, SERVICE_LEVEL)
    engine = SupplyChainEngine(
        graph, log, policies, demand_gen,
        service_level=SERVICE_LEVEL, region_weights=weights,
    )
    engine.run(weeks)
    return engine


if __name__ == "__main__":
    engine = run_regional_demo()
    weights = region_demand_weights(load_regions())

    print("=" * 65)
    print("  Regional demand disaggregation -- india-oem by warehouse region")
    print("=" * 65)
    print(f"\n  Overall OEM fill rate: {engine.fill_rate('india-oem'):>8.1%}\n")
    print(f"  {'Region':15s}{'Demand share':>14s}{'Fill rate':>12s}")
    for region_id, weight in sorted(weights.items(), key=lambda kv: -kv[1]):
        fr = engine.fill_rate_by_region(region_id)
        print(f"  {region_id:15s}{weight:>13.1%}{fr:>12.1%}")
