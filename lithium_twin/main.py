"""
main.py — Phase 1 demo: SimPy engine, base-stock policy, 52-week run.

HOW TO RUN:
  python -m lithium_twin.main

WHAT TO LOOK FOR IN THE OUTPUT:
  1. OEM fill rate: should be near the service level target (95%)
  2. Bullwhip coefficients: should be > 1 and increasing upstream
     — this confirms the model is producing realistic dynamics
  3. Total inventory drawdown: system starts with buffer stock
     that the policies gradually consume and stabilize
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lithium_twin.models.graph import SupplyChainGraph
from lithium_twin.models.events import EventLog
from lithium_twin.models.material import lce_from_kwh
from lithium_twin.simulation.demand import DemandGenerator
from lithium_twin.simulation.order_policy import build_policies
from lithium_twin.simulation.engine import SupplyChainEngine

CHAIN_JSON = Path(__file__).parent / "data" / "chain.json"
WEEKS = 52
DEMAND_MEAN = lce_from_kwh(200_000 * 30, "LFP") / 52.0   # ~36,862 kg/wk
DEMAND_CV = 0.15
SERVICE_LEVEL = 0.95


def run() -> None:
    print("=" * 65)
    print("  Lithium Supply Chain Digital Twin — Phase 1")
    print("  SimPy engine | Base-stock policy | 52-week run")
    print("=" * 65)

    # ── Load chain ────────────────────────────────────────────────────
    graph = SupplyChainGraph.from_json(CHAIN_JSON)
    log = EventLog()

    # ── Demand generator ──────────────────────────────────────────────
    demand_gen = DemandGenerator(mean=DEMAND_MEAN, cv=DEMAND_CV, seed=42)
    print(f"\nDemand: Normal(μ={DEMAND_MEAN:,.0f}, σ={demand_gen.std:,.0f}) kg LCE/wk")

    # ── Build policies ────────────────────────────────────────────────
    policies = build_policies(graph, DEMAND_MEAN, DEMAND_CV, SERVICE_LEVEL)
    print(f"\nOrder policies (service level {SERVICE_LEVEL:.0%}):")
    for node_id, policy in policies.items():
        print(f"  {node_id:30s}  {policy.summary()}")

    # ── Run simulation ────────────────────────────────────────────────
    engine = SupplyChainEngine(graph, log, policies, demand_gen)
    print(f"\nRunning {WEEKS}-week simulation...")
    engine.run(WEEKS)
    print(f"Done. {len(log)} events logged.")

    # ── Results ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  RESULTS — {WEEKS} weeks")
    print(f"{'='*65}")

    print(f"\n  OEM fill rate:        {engine.fill_rate('india-oem'):>8.1%}")
    print(f"  Pack fill rate:       {engine.fill_rate('india-pack-assembly'):>8.1%}")

    print(f"\n  Bullwhip coefficients (order variance / OEM demand variance):")
    for node_id in graph.topological_sort():
        bw = engine.bullwhip_coefficient(node_id)
        if bw != bw:  # nan = no orders placed (source node)
            continue
        bar = "█" * min(40, int(bw * 5))
        print(f"  {node_id:30s}  {bw:6.2f}  {bar}")

    if engine.weekly_snapshots:
        last = engine.weekly_snapshots[-1]
        print(f"\n  Final state (week {WEEKS}):")
        print(f"  Total system inventory:  {last['total_inventory']:>12,.0f} kg LCE")
        print(f"  Total in transit:        {last['total_in_transit']:>12,.0f} kg LCE")
        print(f"  Total system backlog:    {last['total_backlog']:>12,.0f} kg LCE")
        print(f"  OEM inventory:           {last['oem_inventory']:>12,.0f} kg LCE")
        print(f"  OEM backlog:             {last['oem_backlog']:>12,.0f} kg LCE")

    print(f"\n  ✓ Phase 1 complete")
    print(f"  Next: Phase 2 — disruption scenarios + network flow optimisation\n")


if __name__ == "__main__":
    run()