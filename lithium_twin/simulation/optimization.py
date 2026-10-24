"""
optimization.py — Centralized network-flow optimization benchmark.

WHY: the SimPy engine simulates DECENTRALIZED decision-making — each node
reacts only to its own inventory position via a local base-stock policy,
the way independent real-world firms in a chain actually behave. This
module instead solves for the best possible outcome if a single planner
had full visibility of the whole chain (and, in this version, perfect
foresight of future demand) and could allocate flow optimally, subject to
the SAME physical constraints: arc capacity, node processing capacity,
yield-rate loss, and transit lead time.

The gap between this optimum and the simulated decentralized fill rate is
the real finding — it bounds the combined cost of (a) decentralized,
local-information-only reordering and (b) not knowing future demand in
advance. This connects to Clark & Scarf (1960)'s result that centralized
multi-echelon control dominates decentralized local-reorder-point control.

OBJECTIVE DESIGN: unmet demand at OEM is tracked as a running backlog
stock (not a one-off "lost sale"), exactly matching engine.fill_rate()'s
semantics (total dispatched / total demand, where dispatch can happen
late). Minimizing the FINAL backlog is equivalent to maximizing total
served demand, so the resulting fill rate is directly comparable to a
simulated run using the same seed.

MODEL: one time-indexed linear program over the whole horizon (continuous
flow, not integer — fine for bulk kg LCE quantities), solved with PuLP's
bundled CBC solver.
"""
from __future__ import annotations
import pulp

from lithium_twin.models.graph import SupplyChainGraph
from lithium_twin.simulation.demand import DemandGenerator


def solve_centralized_optimum(
    graph: SupplyChainGraph,
    weeks: int,
    demand_mean: float,
    demand_cv: float,
    seed: int,
) -> dict:
    """Solves for the best achievable india-oem fill rate over `weeks`,
    given centralized control and perfect demand foresight, using the
    SAME realized demand sequence a decentralized sim run with this seed
    would see (so the two are directly comparable)."""
    nodes = {n.node_id: n for n in graph.all_nodes()}
    node_ids = list(nodes.keys())
    arcs = [(u, v) for u in node_ids for v in graph.downstream_nodes(u)]
    T = list(range(1, weeks + 1))

    demand_gen = DemandGenerator(mean=demand_mean, cv=demand_cv, seed=seed)
    demand = {t: demand_gen.sample() for t in T}

    prob = pulp.LpProblem("centralized_supply_chain", pulp.LpMinimize)

    flow = {(u, v, t): pulp.LpVariable(f"flow_{u}_{v}_{t}", lowBound=0)
            for (u, v) in arcs for t in T}
    production = {(n, t): pulp.LpVariable(f"prod_{n}_{t}", lowBound=0)
                  for n in node_ids for t in T}
    raw_inv = {(n, t): pulp.LpVariable(f"raw_{n}_{t}", lowBound=0)
               for n in node_ids for t in [0] + T}
    fin_inv = {(n, t): pulp.LpVariable(f"fin_{n}_{t}", lowBound=0)
               for n in node_ids for t in [0] + T}
    backlog = {t: pulp.LpVariable(f"backlog_{t}", lowBound=0) for t in [0] + T}
    served = {t: pulp.LpVariable(f"served_{t}", lowBound=0) for t in T}

    # Initial state matches the simulation's starting conditions exactly:
    # finished inventory = chain.json's initial_inventory_lce, raw input
    # pool starts empty, OEM backlog starts at zero.
    for n in node_ids:
        prob += fin_inv[(n, 0)] == nodes[n].inventory_on_hand
        prob += raw_inv[(n, 0)] == 0
    prob += backlog[0] == 0

    # Node processing capacity: production[n,t] is OUTPUT (post-yield),
    # capped by weekly_capacity — same cap node.produce() enforces.
    for n in node_ids:
        node = nodes[n]
        for t in T:
            prob += production[(n, t)] <= node.weekly_capacity

    # Arc capacity
    for (u, v) in arcs:
        arc = graph.arc_data(u, v)
        for t in T:
            prob += flow[(u, v, t)] <= arc["capacity_lce"]

    # Raw-input balance per node: this week's pool = last week's leftover
    # + arrivals (shipped lead_time weeks ago, minus transport loss) -
    # raw material consumed by this week's production. Production is
    # capped by yield_rate here too (raw_consumed = output/yield_rate),
    # same mass-balance relationship as node.produce().
    for n in node_ids:
        node = nodes[n]
        inbound = graph.upstream_nodes(n)
        for t in T:
            arrivals = []
            for u in inbound:
                arc = graph.arc_data(u, n)
                lead = arc["lead_time_weeks"]
                loss = arc.get("transport_loss", 0.0)
                dispatch_week = t - lead
                if dispatch_week in T:
                    arrivals.append(flow[(u, n, dispatch_week)] * (1.0 - loss))
            raw_consumed = production[(n, t)] * (1.0 / node.yield_rate)
            prob += raw_inv[(n, t)] == raw_inv[(n, t - 1)] + pulp.lpSum(arrivals) - raw_consumed

    # Finished-inventory balance: this week's stock = last week's
    # leftover + this week's production - outbound shipments (- demand
    # served this week, for OEM specifically).
    for n in node_ids:
        outbound = graph.downstream_nodes(n)
        for t in T:
            dispatched_out = pulp.lpSum(flow[(n, v, t)] for v in outbound)
            if n == "india-oem":
                prob += fin_inv[(n, t)] == fin_inv[(n, t - 1)] + production[(n, t)] - dispatched_out - served[t]
            else:
                prob += fin_inv[(n, t)] == fin_inv[(n, t - 1)] + production[(n, t)] - dispatched_out

    # OEM backlog: grows with new demand, shrinks with whatever gets
    # served — served[t] is implicitly capped at backlog[t-1]+demand[t]
    # by backlog[t]'s own lowBound=0, exactly mirroring dispatch_shipment().
    for t in T:
        prob += backlog[t] == backlog[t - 1] + demand[t] - served[t]

    prob += backlog[weeks]  # minimize final backlog == maximize total served

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    total_demand = sum(demand[t] for t in T)
    total_served = sum(pulp.value(served[t]) for t in T)
    fill_rate = total_served / total_demand if total_demand else 0.0

    return {
        "status": pulp.LpStatus[prob.status],
        "total_demand": total_demand,
        "total_served": total_served,
        "final_backlog": pulp.value(backlog[weeks]),
        "fill_rate": fill_rate,
    }


if __name__ == "__main__":
    from lithium_twin.main import CHAIN_JSON, DEMAND_MEAN, DEMAND_CV
    from lithium_twin.simulation.capacity import set_generous_capacities

    graph = SupplyChainGraph.from_json(CHAIN_JSON)
    set_generous_capacities(graph, DEMAND_MEAN)
    result = solve_centralized_optimum(
        graph, weeks=104, demand_mean=DEMAND_MEAN, demand_cv=DEMAND_CV, seed=42
    )

    print("=" * 65)
    print("  Centralized optimization benchmark (seed=42, 104 weeks)")
    print("=" * 65)
    print(f"  Status:          {result['status']}")
    print(f"  Total demand:    {result['total_demand']:,.0f} kg LCE")
    print(f"  Total served:    {result['total_served']:,.0f} kg LCE")
    print(f"  Fill rate:       {result['fill_rate']:.1%}")
    print(f"  Final backlog:   {result['final_backlog']:,.0f} kg LCE")
    print()
    print("  Compare against main.py's decentralized simulation (same seed=42)")
    print("  — the gap is the cost of decentralized, backward-looking decisions.")