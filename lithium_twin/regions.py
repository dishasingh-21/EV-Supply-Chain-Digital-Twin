"""
regions.py -- Loads regional demand weights for india-oem from the Route
Optimizer's warehouse data (server/data/warehouses.xlsx, mirrored here as
lithium_twin/data/regions.json), used to split OEM's single national
demand stream into per-region demand (Phase 3b).

WHY capacityUnits AS THE DEMAND-WEIGHTING PROXY:
A warehouse's throughput capacity was presumably sized against that
region's EV distribution volume, making it a reasonable, already-collected
proxy for "how much of national EV demand does this region represent" --
a better fit for battery-material demand than RecommendedStation.demandScore,
which measures need for a NEW charging station (an infrastructure gap),
not existing EV population or consumption.

Only active=True warehouses are included in regions.json, matching the
Route Optimizer's own convention that an inactive warehouse isn't usable.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json

REGIONS_JSON = Path(__file__).parent / "data" / "regions.json"


@dataclass
class Region:
    region_id: str
    name: str
    town: str
    lat: float
    lon: float
    capacity_units: float


def load_regions(path: str | Path = REGIONS_JSON) -> list[Region]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Region(**r) for r in data["regions"]]


def region_demand_weights(regions: list[Region] | None = None) -> dict[str, float]:
    """Each region's share of total demand, proportional to capacity_units.
    Returns {region_id: weight}, weights summing to 1.0."""
    if regions is None:
        regions = load_regions()
    total = sum(r.capacity_units for r in regions)
    if total <= 0:
        raise ValueError("Total capacity_units across regions must be > 0.")
    return {r.region_id: r.capacity_units / total for r in regions}
