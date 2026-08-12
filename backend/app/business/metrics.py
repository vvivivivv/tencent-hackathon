"""
Deterministic detection layer.

No LLM anywhere in this file.  All decisions are threshold comparisons,
ratio arithmetic, and segment set-algebra — so every flag is explainable
and auditable from a plain reading of the numbers.

Pipeline:
    raw journeys
        → get_segment_stats()      per-segment abandonment + conversion counts
        → detect_anomalies()       threshold comparison → list[AnomalyRecord]
        → run_detection()          thin orchestrator: fetch → detect → score
                                   returns DetectionResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Baselines (healthy-day expectations per segment)
# ---------------------------------------------------------------------------

#: Expected abandonment rate (0-1) on a healthy run, keyed by segment.
BASELINE_ABANDONMENT: dict[str, float] = {
    "mobile_first_time":   0.15,
    "mobile_returning":    0.10,
    "desktop_first_time":  0.12,
    "desktop_returning":   0.08,
}

#: Flag when current abandonment rate exceeds baseline by more than this
#: absolute amount (e.g. 0.20 means "+20 percentage points").
ANOMALY_THRESHOLD: float = 0.20

#: Minimum sample size to consider a segment result statistically meaningful.
MIN_SAMPLE_SIZE: int = 2

#: Confidence bounds — how certain we are that the anomaly is real vs. noise.
#: Confidence is linear in (diff / threshold), capped at 1.0, zeroed below
#: threshold — this keeps the maths dead simple and the result defensible.
CONFIDENCE_SLOPE: float = 1.5   # multiplier on normalised excess


# ---------------------------------------------------------------------------
# Data-transfer types
# ---------------------------------------------------------------------------

@dataclass
class SegmentStats:
    """Raw counts + derived rates for one device × customer_type segment."""
    segment: str
    total: int
    abandoned: int
    completed: int

    @property
    def abandonment_rate(self) -> float:
        return self.abandoned / self.total if self.total else 0.0

    @property
    def conversion_rate(self) -> float:
        return self.completed / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "segment":          self.segment,
            "total":            self.total,
            "abandoned":        self.abandoned,
            "completed":        self.completed,
            "abandonment_rate": round(self.abandonment_rate, 3),
            "conversion_rate":  round(self.conversion_rate, 3),
        }


@dataclass
class AnomalyRecord:
    """One flagged segment — everything downstream needs to understand the flag."""
    segment: str
    current_rate: float      # abandonment rate, 0-1
    baseline_rate: float     # healthy-day baseline, 0-1
    diff: float              # current - baseline (always positive when flagged)
    sample_size: int
    confidence: float        # 0-1; how confident we are this is real vs. noise
    severity: str            # "low" | "medium" | "high"

    def to_dict(self) -> dict:
        return {
            "segment":      self.segment,
            "current_rate": self.current_rate,
            "baseline_rate": self.baseline_rate,
            "diff":         self.diff,
            "sample_size":  self.sample_size,
            "confidence":   self.confidence,
            "severity":     self.severity,
        }


@dataclass
class DetectionResult:
    """Top-level output of run_detection(); passed to the Investigator."""
    anomalies: list[AnomalyRecord]
    segment_stats: dict[str, SegmentStats]  # keyed by segment string
    has_anomaly: bool
    primary_anomaly: Optional[AnomalyRecord]  # highest-confidence flagged segment
    summary: str                               # plain-English one-liner for the console

    def to_dict(self) -> dict:
        return {
            "has_anomaly":      self.has_anomaly,
            "primary_anomaly":  self.primary_anomaly.to_dict() if self.primary_anomaly else None,
            "anomalies":        [a.to_dict() for a in self.anomalies],
            "segment_stats":    {k: v.to_dict() for k, v in self.segment_stats.items()},
            "summary":          self.summary,
        }


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _segment_key(device: str, customer_type: str) -> str:
    return f"{device}_{customer_type}"


def _compute_confidence(diff: float, threshold: float, sample_size: int) -> float:
    """
    Returns a 0-1 confidence that this anomaly is real.

    Formula (all deterministic, no randomness):
      - Below threshold   → 0.0  (not flagged at all; should never reach here)
      - At threshold      → base confidence ~0.50
      - Rising linearly   → capped at 1.0
      - Penalty for small samples (< MIN_SAMPLE_SIZE already filtered; 2–3 is
        low-confidence, 5+ is high-confidence at same diff)
    """
    if diff <= threshold:
        return 0.0
    # How far above the threshold are we, in units of the threshold?
    excess_ratio = (diff - threshold) / threshold          # 0 at threshold, 1 at 2×threshold
    raw = 0.50 + CONFIDENCE_SLOPE * excess_ratio
    raw = min(raw, 1.0)
    # Sample-size penalty: scale linearly from 0.60 (n=2) to 1.0 (n≥6)
    sample_factor = min(1.0, 0.60 + 0.08 * (sample_size - 2))
    return round(raw * sample_factor, 3)


def _severity(diff: float) -> str:
    if diff >= 0.40:
        return "high"
    if diff >= 0.30:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_segment_stats(journeys: list[dict]) -> dict[str, SegmentStats]:
    """
    Compute per-segment abandonment / conversion counts from a list of journey
    dicts.

    Each journey dict must have:
        device          str   e.g. "mobile" | "desktop"
        customer_type   str   e.g. "first_time" | "returning"
        result          str   "abandoned" | "completed"

    The caller is responsible for fetching journeys (from Supabase or a test
    fixture).  This function is pure — no I/O, no side effects.
    """
    raw: dict[str, dict] = {}

    for j in journeys:
        key = _segment_key(j["device"], j["customer_type"])
        raw.setdefault(key, {"total": 0, "abandoned": 0, "completed": 0})
        raw[key]["total"] += 1
        if j["result"] == "abandoned":
            raw[key]["abandoned"] += 1
        elif j["result"] == "completed":
            raw[key]["completed"] += 1

    return {
        key: SegmentStats(
            segment=key,
            total=counts["total"],
            abandoned=counts["abandoned"],
            completed=counts["completed"],
        )
        for key, counts in raw.items()
    }


def detect_anomalies(
    stats: dict[str, SegmentStats],
    threshold: float = ANOMALY_THRESHOLD,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> list[AnomalyRecord]:
    """
    Compare each segment's current abandonment rate against baseline.

    Rules (all deterministic):
      1. Segment must have at least `min_sample` journeys — otherwise too
         uncertain to flag (avoids false positives on n=1 runs).
      2. Segment must be in BASELINE_ABANDONMENT — unknown segments are
         ignored so we never flag noise from miscategorised data.
      3. current_rate - baseline > threshold  → flagged.

    Returns a list of AnomalyRecord sorted by confidence desc.
    """
    anomalies: list[AnomalyRecord] = []

    for segment, current in stats.items():
        baseline = BASELINE_ABANDONMENT.get(segment)
        if baseline is None:
            continue                        # unknown segment, skip
        if current.total < min_sample:
            continue                        # too few journeys to be meaningful

        diff = current.abandonment_rate - baseline
        if diff <= threshold:
            continue                        # within normal range

        confidence = _compute_confidence(diff, threshold, current.total)
        anomalies.append(
            AnomalyRecord(
                segment=segment,
                current_rate=round(current.abandonment_rate, 3),
                baseline_rate=baseline,
                diff=round(diff, 3),
                sample_size=current.total,
                confidence=confidence,
                severity=_severity(diff),
            )
        )

    anomalies.sort(key=lambda a: a.confidence, reverse=True)
    return anomalies


def compare_segments(
    stats: dict[str, SegmentStats],
    segment_a: str,
    segment_b: str,
) -> dict:
    """
    Side-by-side comparison of two segments.

    Used by the Investigator agent to run counterfactual tests, e.g.:
        compare_segments(stats, "mobile_first_time", "desktop_first_time")
    to check whether only mobile users are affected (ruling out site-wide causes).

    Returns a plain dict — structured so the LLM tool-call result is readable.
    """
    a = stats.get(segment_a)
    b = stats.get(segment_b)

    def _stat(s: Optional[SegmentStats]) -> dict:
        if s is None:
            return {"present": False}
        return {"present": True, **s.to_dict()}

    diff = None
    if a and b:
        diff = round(a.abandonment_rate - b.abandonment_rate, 3)

    return {
        segment_a: _stat(a),
        segment_b: _stat(b),
        "abandonment_rate_diff": diff,      # positive means A is worse
        "interpretation": _interpret_segment_diff(segment_a, segment_b, diff),
    }


def _interpret_segment_diff(seg_a: str, seg_b: str, diff: Optional[float]) -> str:
    """
    Deterministic natural-language interpretation for the agent console.
    No LLM — just threshold comparisons turned into words.
    """
    if diff is None:
        return "Comparison unavailable — one or both segments have no data."
    if abs(diff) < 0.05:
        return (
            f"{seg_a} and {seg_b} show similar abandonment rates "
            f"(diff={diff:+.1%}). A segment-specific cause is unlikely."
        )
    worse = seg_a if diff > 0 else seg_b
    return (
        f"{worse} has a notably higher abandonment rate "
        f"(diff={diff:+.1%}). Segment-specific cause is plausible."
    )


def run_detection(journeys: list[dict], scenario: Optional[str] = None) -> DetectionResult:
    """
    Thin orchestrator: compute stats → detect anomalies → assemble result.

    `journeys` is the list of journey dicts from the simulator (or fetched from
    Supabase).  Each dict needs at minimum:
        device, customer_type, result, [scenario optional]

    If `scenario` is supplied, only journeys matching that scenario are used.
    """
    if scenario:
        journeys = [j for j in journeys if j.get("scenario") == scenario]

    stats = get_segment_stats(journeys)
    anomalies = detect_anomalies(stats)

    has_anomaly = bool(anomalies)
    primary = anomalies[0] if anomalies else None

    summary = _build_summary(primary, stats)

    return DetectionResult(
        anomalies=anomalies,
        segment_stats=stats,
        has_anomaly=has_anomaly,
        primary_anomaly=primary,
        summary=summary,
    )


def _build_summary(
    primary: Optional[AnomalyRecord],
    stats: dict[str, SegmentStats],
) -> str:
    """
    One-line plain-English summary shown in the agent console.
    Deterministic — built purely from numbers.
    """
    if primary is None:
        return "No anomalies detected. All segments within normal thresholds."

    rel_increase = (
        (primary.current_rate - primary.baseline_rate) / primary.baseline_rate * 100
        if primary.baseline_rate else 0
    )
    return (
        f"Detected unusual increase in {primary.segment.replace('_', ' ')} "
        f"checkout abandonment — "
        f"+{rel_increase:.0f}% vs baseline "
        f"(current {primary.current_rate:.0%}, baseline {primary.baseline_rate:.0%}, "
        f"n={primary.sample_size}, confidence={primary.confidence:.0%})."
    )
