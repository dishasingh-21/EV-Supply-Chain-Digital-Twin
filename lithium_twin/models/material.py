"""
This script contains code for conversion of units of each node to one canonical unit "LCE".
CONVERSION BASIS - IUPAC 2021 Standard Atomic Weights:
Li = 6.941, C = 12.011, O = 15.999, H = 1.008
Li₂CO₃ = 2(6.941) + 12.011 + 3(15.999) = 73.891 g/mol
LiOH = 6.941 + 15.999 + 1.008 = 23.948 g/mol
LiOH·H₂O = 23.948 + 18.015 = 41.963 g/mol
"""

from __future__ import annotations
from enum import Enum

class MaterialForm(str, Enum):
    BRINE = "brine"
    SPODUMENE = "spodumene"
    CARBONATE = "carbonate"
    HYDROXIDE = "hydroxide"
    HYDROXIDE_MH = "LiOH_monohydrate"
    CAM = "cathode_active_material"
    CELL = "battery_cell"
    PACK = "battery_pack"
    RECOVERED_LCE = "recovered_LCE"

# Taking Li2CO3 as the reference. 1 kg Li2CO3 = 1 kg LCE
LI_METAL_TO_LCE: float = 73.891/(2*6.941)
TO_LCE_FACTOR: dict[MaterialForm, float] = {
    MaterialForm.CARBONATE: 1.0,
    MaterialForm.HYDROXIDE: 73.891/(2*23.948),
    MaterialForm.HYDROXIDE_MH: 73.891/(2*41.963),
    MaterialForm.RECOVERED_LCE: 1.0,
}

def to_lce(quantity: float, form: MaterialForm) -> float:
    """Convert kg of a material form -> kg LCE."""
    if form not in TO_LCE_FACTOR:
        raise ValueError(
            f"'{form}' needs node-level grade/yield parameters, not a fixed factor."
            f"Use node.yield_rate instead."
        )
    return quantity * TO_LCE_FACTOR[form]

LI_KG_PER_KWH: dict[str, float] = {
    "NMC-811": 0.070,
    "NMC-622": 0.075,
    "LFP": 0.060,
    "NCA": 0.068,
}

LCE_PER_KWH: dict[str, float] = {
    chem: li*LI_METAL_TO_LCE
    for chem, li in LI_KG_PER_KWH.items()
}

def lce_from_kwh(kwh: float, chemistry: str = "LFP") -> float:
    """kg LCE required for a given kWh of battery capacity."""
    if chemistry not in LCE_PER_KWH:
        raise KeyError(f"Unknown chemistry '{chemistry}'. Options: {list(LCE_PER_KWH)}")
    return kwh * LCE_PER_KWH[chemistry]

