"""
SimPy discrete event simulation engine.
"""

from  __future__ import annotations
import simpy
from lithium_twin.models.graph import SupplyChainGraph
from lithium_twin.models.events import EventLog, EventType, SupplyChainEvent
from lithium_twin.simulation.order_policy import BaseStockPolicy
from lithium_twin.simulation.demand import DemandGenerator

_RECYCLING_LEAD_TIME: int = 12
_RECYCLING_TRANSPORT_LOSS: float = 0.01
_RECALIBRATION_INTERVAL: int =4
_RECALIBRATION_WINDOW: int=12
_MIN_SAMPLES_FOR_RECALIBRATION: int=8

class SupplyChainEngine:
    """SimPy-based weekly simulation engine for the lithium supply chain."""
    def __init__(self, graph: SupplyChainGraph, log: EventLog, policies: dict[str, BaseStockPolicy], demand_gen: DemandGenerator, service_level: float=0.95):
        self.env = simpy.Environment()
        self.graph = graph
        self.log = log
        self.policies = policies
        self.demand_gen = demand_gen
        self.service_level = service_level
        self.weekly_snapshots: list[dict] = []

    def run(self, weeks: int) -> None:
        """Run simulation for `weeks` time steps and collect metrics."""
        self.env.process(self._market_demand_process())
        for node_id in self.graph.topological_sort():
            self.env.process(self._node_process(node_id))
        for node_id in self.policies:
            self.env.process(self._recalibration_process(node_id))
        self.env.process(self._recycling_injection_process())
        self.env.process(self._snapshot_process(weeks))
        self.env.run(until=weeks+0.5)

    # MARKET DEMAND PROCESS
    def _market_demand_process(self):
        """Generates stochastic weekly demand at india-oem from the market."""
        oem = self.graph.get_node("india-oem")
        while True:
            yield self.env.timeout(1)
            try:
                week = int(self.env.now)
                demand = self.demand_gen.sample()
                oem.receive_demand(demand)
                self.log.append(SupplyChainEvent(
                    event_type=EventType.DEMAND_RECEIVED,
                    source_node="india-oem",
                    week=week,
                    quantity_lce=demand,
                    payload={"source": "market"},
                ))
            except Exception as e:
                print(f"PROCESS CRASH: {type(e).__name__}: {e}")
                return

    # NODE REPLENISHMENT PROCESS
    def _node_process(self, node_id: str):
        """
        Weekly replenishment cycle for a single supply chain node.
        Each week:
            1. Dispatch to fill backlog (if inventory available)
            2. Check inventory position against base stock level S
            3. If below S: order from upstream supplier
        """
        node = self.graph.get_node(node_id)
        policy = self.policies.get(node_id)
        upstream_ids = self.graph.upstream_nodes(node_id)

        while True:
            yield self.env.timeout(1)
            week = int(self.env.now)

            # Step 1: Retry fulfilling any outstanding backlog from current inventory
            if node.backlog > 0 and node.inventory_on_hand > 0:
                downstream_ids = self.graph.downstream_nodes(node_id)
                if downstream_ids and node_id!="india-oem":
                    receiver_id = downstream_ids[0]
                    arc=self.graph.arc_data(node_id, receiver_id)
                    retry_qty = min(node.backlog, arc["capacity_lce"])
                    self.env.process(self._shipment_process(
                        supplier_id=node_id,
                        receiver_id=receiver_id,
                        order_qty=retry_qty,
                        arc=arc,
                    ))
                else:
                    dispatched = node.dispatch_shipment(node.backlog)
                    if dispatched>0:
                        self.log.append(SupplyChainEvent(
                            event_type=EventType.SHIPMENT_DISPATCHED,
                            source_node=node_id,
                            week=week,
                            quantity_lce=dispatched,
                        ))

            # Step-2: Reorder from upstream if below base level stock
            if policy is None or not upstream_ids:
                continue # Source nodes don't order
            inv_position = node.total_supply_position()
            order_qty = policy.order_quantity(inv_position)
            if order_qty <= 0:
                continue

            # Phase-1: single upstream supplier per node
            supplier_id = upstream_ids[0]
            arc = self.graph.arc_data(supplier_id, node_id)
            order_qty = min(order_qty, arc["capacity_lce"])

            # Notify upstream of demand
            supplier_node = self.graph.get_node(supplier_id)
            supplier_node.receive_demand(order_qty)
            self.log.append(SupplyChainEvent(
                event_type = EventType.DEMAND_RECEIVED,
                source_node = supplier_id,
                week=week,
                quantity_lce=order_qty,
                payload={"ordered_by": node_id},
            ))
            self.log.append(SupplyChainEvent(
                event_type=EventType.ORDER_PLACED,
                source_node=node_id,
                week=week,
                quantity_lce=order_qty,
                payload={"supplier": supplier_id},
            ))

            # Spawn shipment process (handles dispatch + transit + arrival)
            self.env.process(self._shipment_process(
                supplier_id=supplier_id,
                receiver_id=node_id,
                order_qty=order_qty,
                arc=arc,
            ))

    # SHIPMENT PROCESS
    def _shipment_process(self, supplier_id: str, receiver_id: str, order_qty: float, arc: dict,):
        """
        Models one shipment from supplier to receiver.
        Synchronous: supplier dispatches immediately.
        Async: yield timeout(lead_time) handles the transit delay.
        Receiver's in_transit is updated with ACTUAL dispatched amount.
        """
        supplier = self.graph.get_node(supplier_id)
        receiver = self.graph.get_node(receiver_id)
        lead_time = arc["lead_time_weeks"]
        transport_loss = arc.get("transport_loss", 0.0)

        # Supplier dispatches what it actually has (maybe less than order_qty)
        actual_dispatched = supplier.dispatch_shipment(order_qty)
        if actual_dispatched <= 0:
            return

        week_dispatched = int(self.env.now)
        receiver.place_order(actual_dispatched)
        self.log.append(SupplyChainEvent(
            event_type=EventType.SHIPMENT_DISPATCHED,
            source_node=supplier_id,
            week=week_dispatched,
            quantity_lce=actual_dispatched,
            payload={"dest": receiver_id},
        ))

        # Wait for transit
        yield self.env.timeout(lead_time)

        # Taking into account transport loss (moisture, spoilage, inspection rejection)
        arrived_qty = actual_dispatched * (1.0 - transport_loss)

        receiver.receive_shipment(arrived_qty)
        week_arrived = int(self.env.now)
        self.log.append(SupplyChainEvent(
            event_type=EventType.SHIPMENT_RECEIVED,
            source_node=receiver_id,
            week=week_arrived,
            quantity_lce=arrived_qty,
            payload={"from": supplier_id},
        ))

    # RECYCLING INJECTION PROCESS
    def _recycling_injection_process(self):
        """Recovers LCE from india-recycling and injects it at china-processing."""
        recycler = self.graph.get_node("india-recycling")
        china_proc = self.graph.get_node("china-processing")
        while True:
            yield self.env.timeout(1)
            week = int(self.env.now)

            # Recycle what's available (up to weekly capacity)
            available = min(recycler.inventory_on_hand, recycler.weekly_capacity)
            if available <= 0:
                continue
            recovered = recycler.produce(available)
            if recovered <= 0:
                continue

            # Schedule arrival at china-processing after transit
            self.env.process(
                self._recycling_arrival(recovered, week, china_proc)
            )

    def _recycling_arrival(self, qty: float, week_dispatched: int, china_proc):
        """Deliver recovered LCE to china-processing after transit."""
        yield self.env.timeout(_RECYCLING_LEAD_TIME)
        arrived = qty * (1.0 - _RECYCLING_TRANSPORT_LOSS)
        china_proc.inventory_on_hand += arrived     # direct shipment, not a shipment
        week_arrived = int(self.env.now)
        self.log.append(SupplyChainEvent(
            event_type=EventType.EXTERNAL_SUPPLY,
            source_node="china-processing",
            week=week_arrived,
            quantity_lce=arrived,
            payload={
                "from": "india-recycling",
                "dispatched_week": week_dispatched,
            },
        ))

    # METRICS SNAPSHOT PROCESS
    def _snapshot_process(self, total_weeks: int):
        """Records system-wide state at end of each week for analysis."""
        for _ in range(total_weeks):
            yield self.env.timeout(1)
            week = int(self.env.now)
            oem = self.graph.get_node("india-oem")
            pack = self.graph.get_node("india-pack-assembly")
            china = self.graph.get_node("china-processing")
            self.weekly_snapshots.append({
                "week": week,
                "total_inventory": self.graph.total_inventory(),
                "total_in_transit": self.graph.total_in_transit(),
                "total_backlog": self.graph.total_backlog(),
                "oem_inventory": oem.inventory_on_hand,
                "oem_backlog": oem.backlog,
                "pack_inventory": pack.inventory_on_hand,
                "pack_backlog": pack.backlog,
                "china_proc_inventory": china.inventory_on_hand,
            })

    # ANALYSIS HELPERS
    def bullwhip_coefficient(self, node_id: str) -> float:
        """Ratio of order variance at node to demand variance at OEM.
        Bullwhip coefficient = Var(orders at node_id) / Var(demand at OEM)
        > 1.0: orders at this node are more variable than OEM demand (bullwhip)
        = 1.0: no amplification
        < 1.0: dampening (shouldn't occur under normal policy)

        Source: Chen et al. (2000), "Quantifying the Bullwhip Effect", Management Science 46(3).
        """
        import statistics
        oem_demands = [
            e.quantity_lce for e in self.log.query(
                node_id="india-oem", event_type=EventType.DEMAND_RECEIVED
            )
        ]
        node_orders = [
            e.quantity_lce for e in self.log.query(
                node_id=node_id, event_type=EventType.ORDER_PLACED
            )
        ]
        if len(oem_demands) < 2 or len(node_orders) < 2:
            return float("nan")
        var_demand = statistics.variance(oem_demands)
        var_orders = statistics.variance(node_orders)
        if var_demand == 0:
            return float("inf")
        return var_orders/var_demand

    def fill_rate(self, node_id: str = "india-oem") -> float:
        """Fraction of demand that was dispatched on time."""
        total_demand = self.log.total_flow(
            EventType.DEMAND_RECEIVED, node_id=node_id
        )
        total_dispatched = self.log.total_flow(
            EventType.SHIPMENT_DISPATCHED, node_id=node_id
        )
        if total_demand == 0:
            return 0.0
        return total_dispatched / total_demand

    def _recalibration_process(self, node_id: str):
        """
        Periodically recalibrates a node's safety stock from its own
        recently observed incoming order history, instead of leaving it
        fixed for the whole run.
        """
        policy = self.policies.get(node_id)
        if policy is None:
            return
        while True:
            yield self.env.timeout(_RECALIBRATION_INTERVAL)
            week = int(self.env.now)
            window_start = max(1, week-_RECALIBRATION_WINDOW+1)
            observed = [
                e.quantity_lce for e in self.log.query(
                    node_id = node_id, event_type = EventType.DEMAND_RECEIVED, week_start = window_start, week_end = week,
                )
            ]
            if len(observed) < _MIN_SAMPLES_FOR_RECALIBRATION:
                continue
            policy.recalibrate(observed, service_level=self.service_level)



