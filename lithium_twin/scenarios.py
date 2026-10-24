"""
scenarios.py — Run and compare disruption scenarios against a baseline.

HOW TO RUN:
  python -m lithium_twin.scenarios
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lithium_twin.models.graph import SupplyChainGraph
from lithium_twin.models.events import EventLog
from lithium_twin.simulation.demand import DemandGenerator
from lithium_twin.simulation.order_policy import build_policies
from lithium_twin.simulation.capacity import set_generous_capacities
from lithium_twin.simulation.engine import SupplyChainEngine
from lithium_twin.simulation.disruption import Disruption

# Reuse main.py's calibrated constants instead of redefining them
from lithium_twin.main import CHAIN_JSON, DEMAND_MEAN, DEMAND_CV, SERVICE_LEVEL


def run_scenario(weeks: int, disruptions: list[Disruption] | None = None, seed: int = 42) -> SupplyChainEngine:
    """Runs one full scenario from a fresh graph, with a given demand seed.
    Same seed across two calls = same demand sequence, so any difference
    in outcome is attributable only to the disruptions passed in."""
    graph = SupplyChainGraph.from_json(CHAIN_JSON)
    set_generous_capacities(graph, DEMAND_MEAN)
    log = EventLog()
    demand_gen = DemandGenerator(mean=DEMAND_MEAN, cv=DEMAND_CV, seed=seed)
    policies = build_policies(graph, DEMAND_MEAN, DEMAND_CV, SERVICE_LEVEL)
    engine = SupplyChainEngine(graph, log, policies, demand_gen, service_level=SERVICE_LEVEL)
    engine.run(weeks, disruptions=disruptions)
    return engine


def compare_chile_drought(weeks: int = 104) -> None:
    baseline = run_scenario(weeks, disruptions=None, seed=42)

    chile_drought = Disruption(
        target_type="arc",
        target_id=("atacama-deposits", "chile-mining"),
        parameter="capacity_lce",
        reduction_pct=0.40,
        start_week=70,
        duration_weeks=15,
    )
    disrupted = run_scenario(weeks, disruptions=[chile_drought], seed=42)

    print("=" * 65)
    print("  Scenario comparison — Chile mining drought (40% capacity cut, weeks 70-85)")
    print("=" * 65)
    print(f"\n  Baseline OEM fill rate:    {baseline.fill_rate('india-oem'):>8.1%}")
    print(f"  Disrupted OEM fill rate:   {disrupted.fill_rate('india-oem'):>8.1%}")
    print(f"\n  Baseline final backlog:    {baseline.graph.total_backlog():>12,.0f} kg LCE")
    print(f"  Disrupted final backlog:   {disrupted.graph.total_backlog():>12,.0f} kg LCE")


if __name__ == "__main__":
    compare_chile_drought()