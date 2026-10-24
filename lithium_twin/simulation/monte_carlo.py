"""
monte_carlo.py — Run many randomized trials to get outcome DISTRIBUTIONS,
not single-run point estimates.

WHY: a single run only tells you what happened under ONE random demand
sequence. Risk analysis needs: across plausible futures, how often does
fill rate drop below an acceptable level, and how bad is the tail?

PAIRED DESIGN: each trial runs baseline and disrupted on the SAME demand
seed. The paired difference (disrupted - baseline) isolates the
disruption's effect from ordinary demand randomness, which pure
between-arm comparison can't do.

WINDOW TRACKING: a disruption's damage can appear mid-run and fully
recover by the end (the recalibration process absorbs it), so a metric
measured only at the final week can show "no effect" even when there was
one transiently. track_window lets a trial also record the average of a
chosen weekly_snapshot metric over a specific week range (e.g. the
disruption's active window + recovery weeks).
"""
from __future__ import annotations
import statistics
from dataclasses import dataclass, field

from lithium_twin.simulation.disruption import Disruption
from lithium_twin.scenarios import run_scenario


@dataclass
class TrialResult:
    seed: int
    fill_rate: float
    final_backlog: float
    final_inventory: float
    window_avg: float | None = None
    bullwhip: dict[str, float] = field(default_factory=dict)


@dataclass
class MonteCarloResult:
    baseline_trials: list[TrialResult] = field(default_factory=list)
    disrupted_trials: list[TrialResult] = field(default_factory=list)
    has_disruption: bool = False

    @staticmethod
    def _percentiles(values: list[float]) -> dict[str, float]:
        if len(values) < 2:
            v = values[0] if values else float("nan")
            return {"mean": v, "stdev": 0.0, "p5": v, "p50": v, "p95": v}
        quantiles = statistics.quantiles(values, n=100, method="inclusive")
        return {
            "mean": statistics.mean(values),
            "stdev": statistics.stdev(values),
            "p5": quantiles[4],
            "p50": quantiles[49],
            "p95": quantiles[94],
        }

    def summary(self) -> dict:
        out = {
            "n_trials": len(self.baseline_trials),
            "baseline": {
                "fill_rate": self._percentiles([t.fill_rate for t in self.baseline_trials]),
                "final_backlog": self._percentiles([t.final_backlog for t in self.baseline_trials]),
            },
        }
        if self.has_disruption:
            out["disrupted"] = {
                "fill_rate": self._percentiles([t.fill_rate for t in self.disrupted_trials]),
                "final_backlog": self._percentiles([t.final_backlog for t in self.disrupted_trials]),
            }
            # Paired difference: same-seed disrupted minus baseline.
            # This is the number that actually answers "what does this
            # disruption cost", net of ordinary demand noise.
            paired_fill_diff = [
                d.fill_rate - b.fill_rate
                for b, d in zip(self.baseline_trials, self.disrupted_trials)
            ]
            paired_backlog_diff = [
                d.final_backlog - b.final_backlog
                for b, d in zip(self.baseline_trials, self.disrupted_trials)
            ]
            out["paired_impact"] = {
                "fill_rate_delta": self._percentiles(paired_fill_diff),
                "final_backlog_delta": self._percentiles(paired_backlog_diff),
            }
            if self.baseline_trials[0].window_avg is not None:
                paired_window_diff = [
                    d.window_avg - b.window_avg
                    for b, d in zip(self.baseline_trials, self.disrupted_trials)
                ]
                out["paired_impact"]["window_avg_delta"] = self._percentiles(paired_window_diff)
        return out

    def print_summary(self) -> None:
        s = self.summary()
        print(f"\n  Monte Carlo — {s['n_trials']} trials")
        print("  " + "=" * 60)

        def fmt_pct(block, label):
            p = block[label]
            print(f"    {label:16s} mean={p['mean']:7.1%}  p5={p['p5']:7.1%}  p50={p['p50']:7.1%}  p95={p['p95']:7.1%}")

        def fmt_qty(block, label):
            p = block[label]
            print(f"    {label:16s} mean={p['mean']:>12,.0f}  p5={p['p5']:>12,.0f}  p50={p['p50']:>12,.0f}  p95={p['p95']:>12,.0f}")

        print("\n  Baseline:")
        fmt_pct(s["baseline"], "fill_rate")
        fmt_qty(s["baseline"], "final_backlog")

        if self.has_disruption:
            print("\n  Disrupted:")
            fmt_pct(s["disrupted"], "fill_rate")
            fmt_qty(s["disrupted"], "final_backlog")

            print("\n  Paired impact (disrupted - baseline, same demand seed):")
            p = s["paired_impact"]["fill_rate_delta"]
            print(f"    fill_rate_delta  mean={p['mean']:+7.1%}  p5={p['p5']:+7.1%}  p50={p['p50']:+7.1%}  p95={p['p95']:+7.1%}")
            p = s["paired_impact"]["final_backlog_delta"]
            print(f"    backlog_delta    mean={p['mean']:+12,.0f}  p5={p['p5']:+12,.0f}  p50={p['p50']:+12,.0f}  p95={p['p95']:+12,.0f}")
            if "window_avg_delta" in s["paired_impact"]:
                p = s["paired_impact"]["window_avg_delta"]
                print(f"    window_avg_delta mean={p['mean']:+12,.0f}  p5={p['p5']:+12,.0f}  p50={p['p50']:+12,.0f}  p95={p['p95']:+12,.0f}")


def _window_average(engine, metric: str, week_start: int, week_end: int) -> float | None:
    values = [
        snap[metric] for snap in engine.weekly_snapshots
        if week_start <= snap["week"] <= week_end
    ]
    return statistics.mean(values) if values else None


def _to_trial_result(engine, seed: int, bullwhip_nodes: tuple[str, ...], track_window, track_metric: str) -> TrialResult:
    window_avg = None
    if track_window is not None:
        window_avg = _window_average(engine, track_metric, track_window[0], track_window[1])
    return TrialResult(
        seed=seed,
        fill_rate=engine.fill_rate("india-oem"),
        final_backlog=engine.graph.total_backlog(),
        final_inventory=engine.graph.total_inventory(),
        window_avg=window_avg,
        bullwhip={nid: engine.bullwhip_coefficient(nid) for nid in bullwhip_nodes},
    )


def run_monte_carlo(
    weeks: int,
    n_trials: int,
    disruptions: list[Disruption] | None = None,
    base_seed: int = 1000,
    bullwhip_nodes: tuple[str, ...] = ("india-oem",),
    track_window: tuple[int, int] | None = None,
    track_metric: str = "total_backlog",
) -> MonteCarloResult:
    """Runs n_trials paired baseline/disrupted simulations.

    Each trial i uses seed = base_seed + i, same seed for both arms of
    the pair, so the paired difference isolates the disruption's effect.
    """
    result = MonteCarloResult(has_disruption=disruptions is not None)
    for i in range(n_trials):
        seed = base_seed + i
        baseline_engine = run_scenario(weeks, disruptions=None, seed=seed)
        result.baseline_trials.append(
            _to_trial_result(baseline_engine, seed, bullwhip_nodes, track_window, track_metric)
        )
        if disruptions is not None:
            disrupted_engine = run_scenario(weeks, disruptions=disruptions, seed=seed)
            result.disrupted_trials.append(
                _to_trial_result(disrupted_engine, seed, bullwhip_nodes, track_window, track_metric)
            )
    return result

if __name__ == "__main__":
    # Re-run the chile-mining drought, but now targeting the ARC (the
    # parameter that actually governs headroom in this chain, per the
    # set_generous_capacities analysis), across 100 trials, tracking the
    # disruption's active window plus 10 recovery weeks.
    chile_drought = Disruption(
        target_type="arc",
        target_id=("atacama-deposits", "chile-mining"),
        parameter="capacity_lce",
        reduction_pct=0.40,
        start_week=70,
        duration_weeks=15,
    )
    mc = run_monte_carlo(
        weeks=104,
        n_trials=100,
        disruptions=[chile_drought],
        track_window=(70, 90),
    )
    mc.print_summary()