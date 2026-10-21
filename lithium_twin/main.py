"""
main.py — Phase 0 demo: load chain, manually step 4 weeks, print state.

Run: python -m lithium_twin.main
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lithium_twin.models.graph import SupplyChainGraph
from lithium_twin.models.events import EventLog, EventType, SupplyChainEvent
from lithium_twin.models.material import lce_from_kwh

CHAIN_JSON = Path(__file__).parent / "data" / "chain.json"
WEEKS = 4
WEEKLY_DEMAND = lce_from_kwh(200_000 * 30, "LFP") / 52.0  # ~36,850 kg/wk


def print_state(graph, week):
    print(f"\n  {'Node':30s} {'Inv':>10s}  {'Backlog':>8s}  {'InTransit':>10s}")
    print(f"  {'-'*30} {'-'*10}  {'-'*8}  {'-'*10}")
    for nid in graph.topological_sort():
        n = graph.get_node(nid)
        print(f"  {nid:30s} {n.inventory_on_hand:>10,.0f}  "
              f"{n.backlog:>8,.0f}  {n.in_transit:>10,.0f}")


def run():
    print("=" * 60)
    print("  Lithium Supply Chain Digital Twin — Phase 0")
    print("=" * 60)

    graph = SupplyChainGraph.from_json(CHAIN_JSON)
    log = EventLog()

    print(f"\nChain: 8 nodes | India LFP | ~200k EVs/yr")
    print(f"Weekly OEM demand: {WEEKLY_DEMAND:,.0f} kg LCE")
    print(f"\nInitial state:")
    print_state(graph, 0)
    print(f"\n  Total system inventory: {graph.total_inventory():,.0f} kg LCE")

    for week in range(1, WEEKS + 1):
        print(f"\n{'─'*60}\n  WEEK {week}\n{'─'*60}")

        oem = graph.get_node("india-oem")
        pack = graph.get_node("india-pack-assembly")
        pack_arc = graph.arc_data("india-pack-assembly", "india-oem")

        # OEM receives market demand → backlog
        oem.receive_demand(WEEKLY_DEMAND)
        log.append(SupplyChainEvent(EventType.DEMAND_RECEIVED, "india-oem", week, WEEKLY_DEMAND))

        # OEM ships from inventory
        shipped = oem.dispatch_shipment(WEEKLY_DEMAND)
        if shipped > 0:
            log.append(SupplyChainEvent(EventType.SHIPMENT_DISPATCHED, "india-oem",
                                        week, shipped,
                                        {"fill_rate": shipped / WEEKLY_DEMAND}))
        print(f"  OEM fill rate: {shipped/WEEKLY_DEMAND:.1%}")

        # OEM places replenishment order (naive: same as demand — no safety stock yet)
        oem.place_order(WEEKLY_DEMAND)
        pack.receive_demand(WEEKLY_DEMAND)
        log.append(SupplyChainEvent(EventType.ORDER_PLACED, "india-oem", week, WEEKLY_DEMAND))
        log.append(SupplyChainEvent(EventType.DEMAND_RECEIVED, "india-pack-assembly",
                                    week, WEEKLY_DEMAND))

        # Pack assembly ships what it can
        pack_shipped = pack.dispatch_shipment(min(WEEKLY_DEMAND, pack_arc["capacity_lce"]))
        if pack_shipped > 0:
            log.append(SupplyChainEvent(EventType.SHIPMENT_DISPATCHED,
                                        "india-pack-assembly", week, pack_shipped))
            print(f"  Pack shipped: {pack_shipped:,.0f} kg LCE "
                  f"(arrives OEM in {pack_arc['lead_time_weeks']} weeks)")

        print_state(graph, week)
        print(f"\n  Inventory: {graph.total_inventory():,.0f} | "
              f"In transit: {graph.total_in_transit():,.0f} | "
              f"Events: {len(log)}")

    print(f"\n{'='*60}\n  SUMMARY — {WEEKS} weeks")
    print(f"{'='*60}")
    total_d = log.total_flow(EventType.DEMAND_RECEIVED, "india-oem")
    total_s = log.total_flow(EventType.SHIPMENT_DISPATCHED, "india-oem")
    print(f"  Total demand:    {total_d:>10,.0f} kg LCE")
    print(f"  Total shipped:   {total_s:>10,.0f} kg LCE")
    print(f"  OEM fill rate:   {total_s/total_d:>9.1%}")
    print(f"\n  ✓ Phase 0 validated")
    print(f"  Next: Phase 1 — SimPy engine + EOQ order policy\n")


if __name__ == "__main__":
    run()