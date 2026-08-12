"""
Business state snapshot.

Deterministic only — no LLM calls.

Responsibilities:
  - Aggregate raw journey data into a BusinessSnapshot
  - Compute the 0-100 Business Health Score shown in the UI
  - Produce a plain-English dollar-value context string
    ("Health 57 → equivalent to $X/month in lost conversion revenue")

The health score formula is intentionally simple so it can be explained in one
sentence during the demo Q&A.  Weights were chosen to reflect what a small
e-commerce operator would actually care about, not to over-engineer a KPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.business.metrics import (
    DetectionResult,
    SegmentStats,
    run_detection,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Rough average monthly revenue per converted customer (used for dollar context)
# In a real product this comes from the business profile; here it's a sensible
# default the user can override.
DEFAULT_REVENUE_PER_CONVERSION: float = 120.0   # $ per converted customer
DEFAULT_MONTHLY_CUSTOMERS: int = 500             # baseline visits / month

# Health score component weights — must sum to 1.0
WEIGHT_CONVERSION  = 0.50    # conversion rate across all segments
WEIGHT_RELIABILITY = 0.30    # absence of anomalies; penalised per flagged segment
WEIGHT_EXPERIENCE  = 0.20    # mobile first-time conversion (proxy for CX quality)

# Benchmark conversion rates used to normalise the 0-100 scale
BENCHMARK_CONVERSION_LOW  = 0.50   # score of 0
BENCHMARK_CONVERSION_HIGH = 0.95   # score of 100


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BusinessSnapshot:
    """Everything the Investigator / UI needs from one simulation run."""

    # Raw counts
    total_journeys: int
    completed: int
    abandoned: int

    # Derived rates
    overall_conversion_rate: float      # completed / total
    overall_abandonment_rate: float     # abandoned / total

    # Per-segment breakdown (mirrors what metrics.py computes)
    segment_stats: dict[str, SegmentStats]

    # Detection output
    detection: DetectionResult

    # Health
    health_score: int           # 0-100
    health_delta: Optional[int] # change vs. previous snapshot (None on first run)
    dollar_context: str         # "Health 57 — equivalent to recovering $X/month"

    def to_dict(self) -> dict:
        return {
            "total_journeys":           self.total_journeys,
            "completed":                self.completed,
            "abandoned":                self.abandoned,
            "overall_conversion_rate":  round(self.overall_conversion_rate, 3),
            "overall_abandonment_rate": round(self.overall_abandonment_rate, 3),
            "segment_stats":            {k: v.to_dict() for k, v in self.segment_stats.items()},
            "detection":                self.detection.to_dict(),
            "health_score":             self.health_score,
            "health_delta":             self.health_delta,
            "dollar_context":           self.dollar_context,
        }


# ---------------------------------------------------------------------------
# Health score computation (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _normalise(value: float, low: float, high: float) -> float:
    """Linearly map `value` from [low, high] to [0, 1], clamped."""
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def compute_health_score(
    segment_stats: dict[str, SegmentStats],
    detection: DetectionResult,
) -> int:
    """
    Compute a 0-100 business health score from three components:

    1. CONVERSION (50%)
       Normalises overall conversion rate between benchmark low and high.

    2. RELIABILITY (30%)
       Starts at 1.0; each flagged anomaly subtracts a penalty proportional
       to its confidence and severity — so a high-confidence critical anomaly
       tanks reliability more than a tentative minor one.

    3. EXPERIENCE (20%)
       Mobile-first-time conversion rate, normalised.  This segment is the
       canary for CX problems (undisclosed fees, friction) since it represents
       the most vulnerable customers — first visit, small screen.

    Score = weighted sum, mapped to 0-100 and rounded to the nearest integer.
    """
    # ── 1. Conversion ────────────────────────────────────────────────────────
    total     = sum(s.total     for s in segment_stats.values())
    completed = sum(s.completed for s in segment_stats.values())
    overall_conv = completed / total if total else 0.0
    conv_component = _normalise(overall_conv, BENCHMARK_CONVERSION_LOW, BENCHMARK_CONVERSION_HIGH)

    # ── 2. Reliability ────────────────────────────────────────────────────────
    severity_penalty = {"low": 0.15, "medium": 0.25, "high": 0.40}
    reliability = 1.0
    for anomaly in detection.anomalies:
        penalty = severity_penalty.get(anomaly.severity, 0.15) * anomaly.confidence
        reliability -= penalty
    reliability_component = max(0.0, reliability)

    # ── 3. Experience (mobile first-time) ────────────────────────────────────
    mft = segment_stats.get("mobile_first_time")
    if mft and mft.total >= 1:
        mft_conv = mft.conversion_rate
    else:
        # No mobile-first-time data — default to overall; don't penalise absence
        mft_conv = overall_conv
    experience_component = _normalise(mft_conv, BENCHMARK_CONVERSION_LOW, BENCHMARK_CONVERSION_HIGH)

    # ── Weighted sum ──────────────────────────────────────────────────────────
    raw = (
        WEIGHT_CONVERSION  * conv_component +
        WEIGHT_RELIABILITY * reliability_component +
        WEIGHT_EXPERIENCE  * experience_component
    )
    return round(raw * 100)


def _dollar_context(
    health_score: int,
    health_delta: Optional[int],
    overall_conversion_rate: float,
    revenue_per_conversion: float = DEFAULT_REVENUE_PER_CONVERSION,
    monthly_customers: int = DEFAULT_MONTHLY_CUSTOMERS,
) -> str:
    """
    Translate the health score into a dollar figure for non-technical founders.

    The conversion-revenue calculation is intentionally transparent:
        recovered = monthly_customers × delta_conversion_rate × revenue_per_conversion
    where delta_conversion_rate is the gap between current and benchmark-high
    conversion (i.e. how much revenue the anomaly is costing).
    """
    # Gap between current conversion and a healthy benchmark
    benchmark_conv = BENCHMARK_CONVERSION_HIGH
    shortfall_conv = max(0.0, benchmark_conv - overall_conversion_rate)
    lost_monthly = monthly_customers * shortfall_conv * revenue_per_conversion

    if health_delta is not None and health_delta > 0:
        # Post-fix context — show recovery
        return (
            f"Health {health_score} — "
            f"equivalent to recovering ${lost_monthly:,.0f}/month "
            f"in lost conversion revenue (+{health_delta} pts)"
        )
    else:
        return (
            f"Health {health_score} — "
            f"estimated ${lost_monthly:,.0f}/month at risk from conversion shortfall"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_snapshot(
    journeys: list[dict],
    scenario: Optional[str] = None,
    previous_health: Optional[int] = None,
    revenue_per_conversion: float = DEFAULT_REVENUE_PER_CONVERSION,
    monthly_customers: int = DEFAULT_MONTHLY_CUSTOMERS,
) -> BusinessSnapshot:
    """
    Build a full BusinessSnapshot from a list of journey dicts.

    Args:
        journeys:             Raw journey list from the simulator.
        scenario:             Optional filter — only include journeys for this scenario.
        previous_health:      Health score from the prior run (used for delta display).
        revenue_per_conversion: Avg revenue per completed conversion ($).
        monthly_customers:    Estimated monthly customer volume (for dollar context).

    Returns:
        BusinessSnapshot with everything the UI / Investigator needs.
    """
    if scenario:
        journeys = [j for j in journeys if j.get("scenario") == scenario]

    total     = len(journeys)
    completed = sum(1 for j in journeys if j["result"] == "completed")
    abandoned = sum(1 for j in journeys if j["result"] == "abandoned")

    detection = run_detection(journeys, scenario=None)  # already filtered above

    health = compute_health_score(detection.segment_stats, detection)
    delta  = (health - previous_health) if previous_health is not None else None

    overall_conv = completed / total if total else 0.0

    dollar_ctx = _dollar_context(
        health_score=health,
        health_delta=delta,
        overall_conversion_rate=overall_conv,
        revenue_per_conversion=revenue_per_conversion,
        monthly_customers=monthly_customers,
    )

    return BusinessSnapshot(
        total_journeys=total,
        completed=completed,
        abandoned=abandoned,
        overall_conversion_rate=overall_conv,
        overall_abandonment_rate=abandoned / total if total else 0.0,
        segment_stats=detection.segment_stats,
        detection=detection,
        health_score=health,
        health_delta=delta,
        dollar_context=dollar_ctx,
    )
