from __future__ import annotations
TARGET_UTILIZATION: float = 0.60

def compute_required_node_outputs(graph, demand_mean: float) -> dict[str, float]:
    """For each node, the average quantity IT must ship to its downstream
    customer to sustain OEM's mean demand — i.e. the yield-chain-corrected
    target each node's own order policy should replenish toward, not raw
    OEM-level demand. Exposed separately from compute_required_arc_flows()
    because order_policy.build_policies() needs this per-node figure
    directly, not the arc-indexed version."""
    downstream_requirement: dict[str, float] = {"india-oem": demand_mean}
    for node_id in reversed(graph.topological_sort()):
        required_output = downstream_requirement.get(node_id)
        if required_output is None:
            continue
        upstream_ids = graph.upstream_nodes(node_id)
        if not upstream_ids:
            continue
        node = graph.get_node(node_id)
        upstream_id = upstream_ids[0]
        downstream_requirement[upstream_id] = required_output / node.yield_rate
    return downstream_requirement

def compute_required_arc_flows(graph, demand_mean: float) -> dict[tuple[str,str], float]:
    """
    Average steady state flow each arc must carry to meet mean OEM demand.
    Walks the chain backward from india-oem, dividing by each node's own yield_rate to find how much INPUT that node needs to produce the required OUTPUT for its downstream customer.
    """
    required_flows: dict[tuple[str, str], float]={}
    downstream_requirement: dict[str, float]={"india-oem": demand_mean}
    for node_id in reversed(graph.topological_sort()):
        required_input = downstream_requirement.get(node_id)
        if required_input is None:
            continue
        upstream_ids = graph.upstream_nodes(node_id)
        if not upstream_ids:
            continue
        node = graph.get_node(node_id)
        upstream_id = upstream_ids[0]
        arc_flow = required_input/node.yield_rate
        required_flows[(upstream_id, node_id)] = arc_flow
        downstream_requirement[upstream_id] = arc_flow

    return required_flows

def set_generous_capacities(graph, demand_mean: float, target_utilization: float=TARGET_UTILIZATION) -> None:
    """Overwrites each arc's capacity_lce with a generously-margined value."""
    required_flows = compute_required_arc_flows(graph, demand_mean)
    for (from_id, to_id), flow in required_flows.items():
        arc = graph.arc_data(from_id, to_id)
        generous_capacity = round(flow/target_utilization, 1)
        arc["phase0_capacity_lce"] = arc.get("capacity_lce")
        arc["base_capacity_lce"] = generous_capacity
        arc["capacity_lce"] = generous_capacity
