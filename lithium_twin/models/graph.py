"""
Supply Chain network as a NetworkX directed acyclic graph.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterator
import networkx as nx
from lithium_twin.models.node import SupplyChainNode, NodeType

class SupplyChainGraph:
    """
    DAG of supply chain nodes connected by material flow arcs/edges.
    Edge attributes on each arc:
        - capacity_lce: max weekly flow (kg LCE)
        - lead_time_weeks: transit time
        - transport_loss: fraction lost in transit (0.0 to 1.0)
    """
    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, SupplyChainNode] = {}

    def add_node(self, node: SupplyChainNode) -> None:
        self._nodes[node.node_id] = node
        self._g.add_node(node.node_id, node_type=node.node_type.value)

    def add_arc(self, source_id: str, dest_id: str, capacity_lce: float, lead_time_weeks: int, transport_loss: float=0.0) -> None:
        for nid in (source_id, dest_id):
            if nid not in self._nodes:
                raise KeyError(f"Node'{nid}' not found. Add it before adding arcs.")
        self._g.add_edge(source_id, dest_id, capacity_lce=capacity_lce, lead_time_weeks=lead_time_weeks, transport_loss=transport_loss)

    def topological_sort(self) -> list[str]:
        """
        Nodes in upstream-first order for weekly simulation steps.
        Eg: We'll process the mine before the processor as it needs to know what the mine shipped this week before making its own decisions. Raises ValueError if graph has a cycle.
        """
        try:
            return list(nx.topological_sort(self._g))
        except nx.NetworkXUnfeasible as e:
            raise ValueError(
                "Graph has a cycle. Recycling feedback must be an event injection, not a graph arc, to preserve DAG topology."
            ) from e

    def upstream_nodes(self, node_id: str) -> list[str]:
        return list(self._g.predecessors(node_id))

    def downstream_nodes(self, node_id: str) -> list[str]:
        return list(self._g.successors(node_id))

    def arc_data(self, source_id: str, dest_id: str) -> dict:
        if not self._g.has_edge(source_id, dest_id):
            raise KeyError(f"No arc from '{source_id} to '{dest_id}'.")
        return self._g[source_id][dest_id]

    def get_node(self, node_id:str) -> SupplyChainNode:
        if node_id not in self._nodes:
            raise KeyError(f"Node '{node_id}' not found.")
        return self._nodes[node_id]

    def all_nodes(self) -> Iterator[SupplyChainNode]:
        yield from self._nodes.values()

    def total_inventory(self) -> float:
        return sum(n.inventory_on_hand for n in self._nodes.values())

    def total_in_transit(self) -> float:
        return sum(n.in_transit for n in self._nodes.values())

    def total_backlog(self) -> float:
        return sum(n.total_backlog() for n in self._nodes.values())

    @classmethod
    def from_json(cls, path: str | Path) -> "SupplyChainGraph":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        graph = cls()
        for node_dict in data["nodes"]:
            graph.add_node(SupplyChainNode.from_dict(node_dict))
        for arc in data["arcs"]:
            if "source" not in arc:
                continue
            graph.add_arc(
                source_id=arc["source"],
                dest_id=arc["dest"],
                capacity_lce=arc["capacity_lce"],
                lead_time_weeks=arc["lead_time_weeks"],
                transport_loss = arc.get("transport_loss", 0.0),
            )
        return graph

    def summary(self) -> str:
        lines = [f"SupplyChainGraph: {len(self._nodes)} nodes, {self._g.number_of_edges()} arcs"]
        for nid in self.topological_sort():
            n = self._nodes[nid]
            dn = self.downstream_nodes(nid)
            lines.append(
                f" [{n.node_type.value:14s}] {nid:25s} "
                f"cap={n.weekly_capacity:8,.0f} kg/week  "
                f"inv={n.inventory_on_hand:8,.0f}"
                + (f" -> {dn}" if dn else " (sink)")
            )
        return "\n".join(lines)