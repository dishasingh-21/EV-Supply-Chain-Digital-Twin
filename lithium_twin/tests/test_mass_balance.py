"""
test_mass_balance.py — Mass balance and unit system tests for Phase 0.

Mass balance equation per node per week:
  output = input × yield_rate
  ending_inventory = starting_inventory - input × (1 - yield_rate)

If this breaks: LCE is being created or destroyed. Bug in the model.

Run: python -m pytest lithium_twin/tests/ -v
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from lithium_twin.models.material import (
    MaterialForm, TO_LCE_FACTOR, LI_METAL_TO_LCE,
    LCE_PER_KWH, to_lce, lce_from_kwh,
)
from lithium_twin.models.node import SupplyChainNode, NodeType
from lithium_twin.models.events import SupplyChainEvent, EventType, EventLog
from lithium_twin.models.graph import SupplyChainGraph


class TestLCEConversions:

    def test_carbonate_is_reference(self):
        assert TO_LCE_FACTOR[MaterialForm.CARBONATE] == 1.0

    def test_li_metal_to_lce(self):
        assert abs(LI_METAL_TO_LCE - 73.891 / (2 * 6.941)) < 1e-6

    def test_lioh_conversion(self):
        expected = 73.891 / (2 * 23.948)
        assert abs(TO_LCE_FACTOR[MaterialForm.HYDROXIDE] - expected) < 1e-6

    def test_lioh_monohydrate_conversion(self):
        expected = 73.891 / (2 * 41.963)
        assert abs(TO_LCE_FACTOR[MaterialForm.HYDROXIDE_MH] - expected) < 1e-6

    def test_lioh_greater_than_monohydrate(self):
        # Anhydrous has more Li per kg than monohydrate (water adds mass, no Li)
        assert TO_LCE_FACTOR[MaterialForm.HYDROXIDE] > TO_LCE_FACTOR[MaterialForm.HYDROXIDE_MH]

    def test_lfp_lce_per_kwh(self):
        # 0.060 kg Li/kWh × 5.3229 LCE/Li ≈ 0.3194
        assert abs(LCE_PER_KWH["LFP"] - 0.060 * LI_METAL_TO_LCE) < 1e-4

    def test_lce_from_30kwh_lfp(self):
        result = lce_from_kwh(30.0, "LFP")
        assert 9.5 < result < 9.7  # should be ~9.58 kg LCE

    def test_to_lce_raises_for_brine(self):
        with pytest.raises(ValueError, match="yield_rate"):
            to_lce(1.0, MaterialForm.BRINE)

    def test_unknown_chemistry_raises(self):
        with pytest.raises(KeyError):
            lce_from_kwh(10.0, "NMF-999")

    def test_weekly_india_demand(self):
        # 200k EVs × 30 kWh × LFP LCE/kWh ÷ 52 weeks ≈ 37,000 kg/wk
        weekly = lce_from_kwh(200_000 * 30, "LFP") / 52.0
        assert 35_000 < weekly < 40_000


class TestNodeStateVariables:

    def _node(self, inv=10000.0):
        return SupplyChainNode(
            node_id="test", node_type=NodeType.PROCESSOR, location="Test",
            weekly_capacity=50000.0, lead_time_weeks=4, yield_rate=0.90,
            inventory_on_hand=inv,
        )

    def test_demand_increases_backlog(self):
        n = self._node()
        n.receive_demand("customer-a", 5000.0)
        assert n.backlog["customer-a"] == 5000.0
        assert n.total_backlog() == 5000.0

    def test_dispatch_fills_from_inventory(self):
        n = self._node(10000.0)
        n.receive_demand("customer-a", 8000.0)
        d = n.dispatch_shipment("customer-a", 8000.0)
        assert d == 8000.0
        assert n.inventory_on_hand == 2000.0
        assert n.total_backlog() == 0.0

    def test_partial_fill_when_inventory_short(self):
        n = self._node(3000.0)
        n.receive_demand("customer-a", 8000.0)
        d = n.dispatch_shipment("customer-a", 8000.0)
        assert d == 3000.0
        assert n.backlog["customer-a"] == 5000.0  # shortage propagates upstream

    def test_multiple_customers_tracked_separately(self):
        """The actual point of Phase 3a: a node with two downstream
        customers tracks each one's shortfall independently, not merged
        into one undifferentiated number."""
        n = self._node(5000.0)
        n.receive_demand("region-a", 3000.0)
        n.receive_demand("region-b", 4000.0)
        assert n.total_backlog() == 7000.0
        dispatched_a = n.dispatch_shipment("region-a", 3000.0)
        assert dispatched_a == 3000.0
        assert n.backlog["region-a"] == 0.0
        assert n.backlog["region-b"] == 4000.0  # untouched by region-a's fulfillment

    def test_order_increases_in_transit(self):
        n = self._node()
        n.place_order(12000.0)
        assert n.in_transit == 12000.0

    def test_receive_shipment_moves_to_raw_input(self):
        """Arriving shipments land in raw_input (unprocessed), not
        inventory_on_hand directly — they still need produce() to apply
        yield loss and respect weekly_capacity before becoming dispatchable."""
        n = self._node(5000.0)
        n.place_order(8000.0)
        n.receive_shipment(8000.0)
        assert n.in_transit == pytest.approx(0.0, abs=1e-6)
        assert n.raw_input == pytest.approx(8000.0, abs=1e-3)
        assert n.inventory_on_hand == pytest.approx(5000.0, abs=1e-3)  # unchanged

    def test_receive_more_than_in_transit_raises(self):
        n = self._node()
        n.place_order(5000.0)
        with pytest.raises(ValueError):
            n.receive_shipment(9999.0)

    def test_produce_applies_yield(self):
        n = self._node(10000.0)
        n.raw_input = 1000.0
        output = n.produce()
        assert output == pytest.approx(900.0, abs=1e-3)
        # raw_input and inventory_on_hand are now separate pools:
        # raw_input is consumed, inventory_on_hand only gains the output
        assert n.raw_input == pytest.approx(0.0, abs=1e-3)
        assert n.inventory_on_hand == pytest.approx(10900.0, abs=1e-3)

    def test_supply_position(self):
        n = self._node(5000.0)
        n.place_order(3000.0)
        assert n.total_supply_position() == pytest.approx(8000.0, abs=1e-3)


class TestEventSystem:

    def test_flow_event_zero_qty_raises(self):
        with pytest.raises(ValueError, match="quantity_lce > 0"):
            SupplyChainEvent(EventType.DEMAND_RECEIVED, "india-oem", week=1, quantity_lce=0.0)

    def test_negative_qty_raises(self):
        with pytest.raises(ValueError, match="negative"):
            SupplyChainEvent(EventType.SHIPMENT_DISPATCHED, "node", week=1, quantity_lce=-1.0)

    def test_week_zero_raises(self):
        with pytest.raises(ValueError, match="week must be"):
            SupplyChainEvent(EventType.PRODUCTION_COMPLETED, "node", week=0, quantity_lce=100.0)

    def test_append_and_query(self):
        log = EventLog()
        log.append(SupplyChainEvent(EventType.DEMAND_RECEIVED, "india-oem", 1, 37000.0))
        log.append(SupplyChainEvent(EventType.ORDER_PLACED, "india-pack-assembly", 1, 37374.0))
        assert len(log) == 2
        assert len(log.query(node_id="india-oem")) == 1

    def test_duplicate_event_rejected(self):
        log = EventLog()
        e = SupplyChainEvent(EventType.SHIPMENT_DISPATCHED, "chile-mining", 2, 45000.0)
        log.append(e)
        with pytest.raises(ValueError, match="Duplicate"):
            log.append(e)

    def test_total_flow_sum(self):
        log = EventLog()
        for w in range(1, 5):
            log.append(SupplyChainEvent(EventType.DEMAND_RECEIVED, "india-oem", w, 37000.0))
        assert log.total_flow(EventType.DEMAND_RECEIVED, node_id="india-oem") == pytest.approx(148000.0)


class TestGraphTopology:

    @pytest.fixture
    def graph(self):
        return SupplyChainGraph.from_json(
            Path(__file__).parent.parent / "data" / "chain.json"
        )

    def test_eight_nodes(self, graph):
        assert len(list(graph.all_nodes())) == 8

    def test_is_dag(self, graph):
        order = graph.topological_sort()
        assert len(order) == 8

    def test_atacama_has_no_upstream(self, graph):
        assert graph.upstream_nodes("atacama-deposits") == []

    def test_oem_receives_from_pack(self, graph):
        assert "india-pack-assembly" in graph.upstream_nodes("india-oem")

    def test_chile_to_china_arc(self, graph):
        arc = graph.arc_data("chile-mining", "china-processing")
        assert arc["lead_time_weeks"] == 10
        assert arc["transport_loss"] == pytest.approx(0.005)

    def test_nonzero_initial_inventory(self, graph):
        assert graph.total_inventory() > 1_000_000


class TestSingleWeekMassBalance:
    """The core correctness test. If these fail, nothing else matters."""

    def test_processor_mass_balance(self):
        """Mass balance now spans two pools: raw_input (consumed) and
        inventory_on_hand (gains yield-adjusted output). The yield loss is
        the gap between raw consumed and output produced — not a drawdown
        of inventory_on_hand, since produce() never subtracts from it."""
        n = SupplyChainNode("p", NodeType.PROCESSOR, "T", 50000.0, 4, 0.90, 10000.0)
        n.raw_input = 1000.0
        output = n.produce()
        assert output == pytest.approx(900.0, abs=1e-3)
        raw_consumed = 1000.0 - n.raw_input
        loss = raw_consumed - output
        assert loss == pytest.approx(100.0, abs=1e-3)  # 1000 × (1-0.90) = 100
        assert n.inventory_on_hand == pytest.approx(10900.0, abs=1e-3)

    def test_oem_zero_loss(self):
        n = SupplyChainNode("o", NodeType.OEM, "T", 40000.0, 2, 1.00, 5000.0)
        n.raw_input = 5000.0
        output = n.produce()
        assert output == pytest.approx(5000.0)
        assert n.inventory_on_hand == pytest.approx(10000.0)  # 5000 start + 5000 output

    def test_recycler_mass_balance(self):
        n = SupplyChainNode("r", NodeType.RECYCLER, "T", 5000.0, 8, 0.72, 1000.0)
        n.raw_input = 1000.0
        output = n.produce()
        assert output == pytest.approx(720.0, abs=1e-3)
        # 280 kg LCE genuinely lost (slag, leach residue)
        assert n.inventory_on_hand == pytest.approx(1720.0, abs=1e-3)

    def test_chain_yield_product(self):
        # ∏ yield_i across 6 processing nodes: 0.90 × 0.90 × 0.95 × 0.96 × 0.99 × 1.00
        chain_yield = math.prod([0.90, 0.90, 0.95, 0.96, 0.99, 1.00])
        assert 0.70 < chain_yield < 0.75  # expect ~0.731
        # Means: to deliver 37,000 kg/wk to OEM, mines need ~50,600 kg/wk