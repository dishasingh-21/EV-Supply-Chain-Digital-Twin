"""
Stochastic Demand Generation
Stochastic demand is required to observe and measure the bullwhip in simulation.
Weekly OEM demand is the aggregate of many independent dealer orders across India (Tata, Ola, MG dealer networks). By the central limit theorem, the sum of many independent random variables converges to Normal regardless of individual dealer order distributions.
Using coefficient of variation, CV=0.15 (represents ±15% week-to-week variability). SOURCE: SIAM monthly EV segment data FY2022-24 shows ~15% month-to-month CV. We use same value weekly as a conservative estimate.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

@dataclass
class DemandGenerator:
    """Generates stochastic weekly demand from a Normal distribution."""
    mean: float
    cv: float = 0.15
    seed: int = 42
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.std = self.mean * self.cv
        self._rng = np.random.default_rng(self.seed)

    def sample(self) -> float:
        """One week's demand."""
        return float(max(0.0, self._rng.normal(self.mean, self.std)))

    def samples(self, n:int) -> list[float]:
        """n weeks of demand."""
        return [self.sample() for _ in range(n)]

    def reset(self) -> None:
        """Reset RNG to initial seed. Lets you re-run from week-1 identically."""
        self._rng = np.random.default_rng(self.seed)