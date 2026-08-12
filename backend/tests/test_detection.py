"""
Unit tests for the deterministic detection layer (business/metrics.py)
and the health-score / snapshot layer (business/state.py).

No LLM, no Supabase, no network — everything is pure in-memory fixtures.
Run with:
    cd backend && pytest tests/test_detection.py -v

Coverage targets (per README §5.5):
  - Anomaly flagged when current abandonment exceeds baseline by > threshold
  - No anomaly when still within threshold
  - Segment below MIN_SAMPLE_SIZE is ignored (avoids false positives on n=1)
  - Unknown segments (not in BASELINE_ABANDONMENT) are silently ignored
  - Confidence increases with diff magnitude and sample size
  - Severity bands (low / medium / high) map to correct diff ranges
  - compare_segments produces correct diff and interpretation
  - Scenario filter in run_detection respects the scenario field
  - Health score drops when anomaly is present
  - Health score recovers when anomaly is resolved
  - Dollar context string is non-empty and contains a dollar sign
  - All-completed cohort: no anomaly, health score near 100
"""

import pytest

from app.business.metrics import (
    ANOMALY_THRESHOLD,
    MIN_SAMPLE_SIZE,
    BASELINE_ABANDONMENT,
    SegmentStats,
    AnomalyRecord,
    get_segment_stats,
    detect_anomalies,
    compare_segments,
    run_detection,
    _compute_confidence,
    _severity,
)
from app.business.state import build_snapshot, compute_health_score


# ---------------------------------------------------------------------------
# Fixtures — plain dicts that mimic what the simulator writes to Supabase
# ---------------------------------------------------------------------------

def _make_journeys(
    mobile_first_time: tuple[int, int],    # (total, abandoned)
    mobile_returning:  tuple[int, int] = (3, 0),
    desktop_first_time: tuple[int, int] = (2, 0),
    desktop_returning:  tuple[int, int] = (2, 0),
    scenario: str = "mobile_checkout_fee",
) -> list[dict]:
    """Helper: build a synthetic journey list from (total, abandoned) tuples."""
    journeys: list[dict] = []

    def _add(device: str, ctype: str, total: int, abandoned: int) -> None:
        for i in range(total):
            journeys.append({
                "device":        device,
                "customer_type": ctype,
                "result":        "abandoned" if i < abandoned else "completed",
                "scenario":      scenario,
            })

    _add("mobile",  "first_time", *mobile_first_time)
    _add("mobile",  "returning",  *mobile_returning)
    _add("desktop", "first_time", *desktop_first_time)
    _add("desktop", "returning",  *desktop_returning)
    return journeys


# Scenario A ground truth: 3 mobile-first-time customers, all abandon
SCENARIO_A_JOURNEYS = _make_journeys(mobile_first_time=(3, 3))

# Healthy run — abandonment within baseline on every segment
HEALTHY_JOURNEYS = _make_journeys(
    mobile_first_time=(4, 0),   # 0% abandonment, baseline 15% — well within threshold
    mobile_returning=(3, 0),
    desktop_first_time=(2, 0),
    desktop_returning=(2, 0),
)

# Marginal run — abandonment exactly at threshold (should NOT be flagged)
# baseline for mobile_first_time = 0.15, threshold = 0.20 → flag point is 0.35
# 1/3 ≈ 0.333, which is below 0.35 — not flagged
MARGINAL_JOURNEYS = _make_journeys(mobile_first_time=(3, 1))  # 0.333 < 0.35


# ---------------------------------------------------------------------------
# get_segment_stats
# ---------------------------------------------------------------------------

class TestGetSegmentStats:
    def test_counts_are_correct(self):
        journeys = SCENARIO_A_JOURNEYS
        stats = get_segment_stats(journeys)
        mft = stats["mobile_first_time"]
        assert mft.total == 3
        assert mft.abandoned == 3
        assert mft.completed == 0

    def test_abandonment_rate_calculation(self):
        stats = get_segment_stats(SCENARIO_A_JOURNEYS)
        assert stats["mobile_first_time"].abandonment_rate == pytest.approx(1.0)

    def test_conversion_rate_is_complement_of_abandonment(self):
        stats = get_segment_stats(HEALTHY_JOURNEYS)
        mft = stats["mobile_first_time"]
        assert mft.abandonment_rate + mft.conversion_rate == pytest.approx(1.0)

    def test_empty_journey_list_returns_empty_dict(self):
        assert get_segment_stats([]) == {}

    def test_zero_total_segment_rates_are_zero(self):
        # Manually construct a SegmentStats with total=0 (edge-case guard)
        s = SegmentStats(segment="x", total=0, abandoned=0, completed=0)
        assert s.abandonment_rate == 0.0
        assert s.conversion_rate == 0.0


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------

class TestDetectAnomalies:
    def test_flags_mobile_first_time_in_scenario_a(self):
        stats = get_segment_stats(SCENARIO_A_JOURNEYS)
        anomalies = detect_anomalies(stats)
        segments = [a.segment for a in anomalies]
        assert "mobile_first_time" in segments

    def test_no_anomaly_when_healthy(self):
        stats = get_segment_stats(HEALTHY_JOURNEYS)
        anomalies = detect_anomalies(stats)
        assert anomalies == []

    def test_no_anomaly_exactly_at_threshold(self):
        # 1 out of 3 = 0.333; threshold boundary is 0.15 + 0.20 = 0.35 — NOT flagged
        stats = get_segment_stats(MARGINAL_JOURNEYS)
        anomalies = detect_anomalies(stats)
        assert anomalies == []

    def test_flags_when_just_above_threshold(self):
        # 2 out of 4 = 0.50; baseline 0.15, threshold 0.20 → diff 0.35 > 0.20 ✓
        journeys = _make_journeys(mobile_first_time=(4, 2))
        stats = get_segment_stats(journeys)
        anomalies = detect_anomalies(stats)
        assert any(a.segment == "mobile_first_time" for a in anomalies)

    def test_small_sample_below_min_is_not_flagged(self):
        # n=1 — below MIN_SAMPLE_SIZE (2); should be skipped even if 100% abandoned
        journeys = [{"device": "mobile", "customer_type": "first_time",
                     "result": "abandoned", "scenario": "x"}]
        stats = get_segment_stats(journeys)
        anomalies = detect_anomalies(stats, min_sample=MIN_SAMPLE_SIZE)
        assert anomalies == []

    def test_unknown_segment_is_silently_ignored(self):
        journeys = [{"device": "fax", "customer_type": "alien",
                     "result": "abandoned", "scenario": "x"},
                    {"device": "fax", "customer_type": "alien",
                     "result": "abandoned", "scenario": "x"}]
        stats = get_segment_stats(journeys)
        anomalies = detect_anomalies(stats)
        assert anomalies == []   # "fax_alien" not in BASELINE_ABANDONMENT

    def test_anomalies_sorted_by_confidence_desc(self):
        # Both mobile_first_time and mobile_returning spike; first should be higher-conf
        journeys = (
            _make_journeys(mobile_first_time=(6, 6), mobile_returning=(6, 6))
        )
        stats = get_segment_stats(journeys)
        anomalies = detect_anomalies(stats)
        assert len(anomalies) >= 2
        confs = [a.confidence for a in anomalies]
        assert confs == sorted(confs, reverse=True)

    def test_anomaly_record_fields_present(self):
        stats = get_segment_stats(SCENARIO_A_JOURNEYS)
        anomalies = detect_anomalies(stats)
        a = anomalies[0]
        assert 0.0 < a.confidence <= 1.0
        assert a.severity in ("low", "medium", "high")
        assert a.diff > 0
        assert a.sample_size == 3
        assert a.baseline_rate == BASELINE_ABANDONMENT["mobile_first_time"]


# ---------------------------------------------------------------------------
# Confidence and severity helpers
# ---------------------------------------------------------------------------

class TestConfidenceAndSeverity:
    def test_confidence_is_zero_at_or_below_threshold(self):
        assert _compute_confidence(0.20, threshold=0.20, sample_size=5) == 0.0
        assert _compute_confidence(0.10, threshold=0.20, sample_size=5) == 0.0

    def test_confidence_increases_with_larger_diff(self):
        c_small = _compute_confidence(0.25, threshold=0.20, sample_size=5)
        c_large = _compute_confidence(0.45, threshold=0.20, sample_size=5)
        assert c_large > c_small

    def test_confidence_increases_with_larger_sample(self):
        c_small = _compute_confidence(0.30, threshold=0.20, sample_size=2)
        c_large = _compute_confidence(0.30, threshold=0.20, sample_size=8)
        assert c_large > c_small

    def test_confidence_capped_at_one(self):
        c = _compute_confidence(999.0, threshold=0.20, sample_size=100)
        assert c <= 1.0

    def test_severity_bands(self):
        # low:    diff < 0.30
        assert _severity(0.29) == "low"
        assert _severity(0.21) == "low"
        # medium: 0.30 <= diff < 0.40
        assert _severity(0.30) == "medium"
        assert _severity(0.39) == "medium"
        # high:   diff >= 0.40
        assert _severity(0.40) == "high"
        assert _severity(0.99) == "high"


# ---------------------------------------------------------------------------
# compare_segments
# ---------------------------------------------------------------------------

class TestCompareSegments:
    def test_diff_is_correct(self):
        stats = get_segment_stats(SCENARIO_A_JOURNEYS)
        result = compare_segments(stats, "mobile_first_time", "desktop_first_time")
        # mobile_first_time: 100% abandon; desktop_first_time: 0% abandon
        assert result["abandonment_rate_diff"] == pytest.approx(1.0)

    def test_missing_segment_returns_not_present(self):
        stats = get_segment_stats(SCENARIO_A_JOURNEYS)
        result = compare_segments(stats, "mobile_first_time", "nonexistent_segment")
        assert result["nonexistent_segment"]["present"] is False

    def test_interpretation_is_non_empty_string(self):
        stats = get_segment_stats(SCENARIO_A_JOURNEYS)
        result = compare_segments(stats, "mobile_first_time", "desktop_returning")
        assert isinstance(result["interpretation"], str)
        assert len(result["interpretation"]) > 0

    def test_similar_segments_give_benign_interpretation(self):
        # Both mobile and desktop returning are healthy — diff should be small
        stats = get_segment_stats(HEALTHY_JOURNEYS)
        result = compare_segments(stats, "mobile_returning", "desktop_returning")
        # diff < 0.05 → "similar" interpretation
        assert "similar" in result["interpretation"].lower()


# ---------------------------------------------------------------------------
# run_detection — end-to-end
# ---------------------------------------------------------------------------

class TestRunDetection:
    def test_scenario_a_has_anomaly(self):
        result = run_detection(SCENARIO_A_JOURNEYS)
        assert result.has_anomaly is True

    def test_healthy_run_has_no_anomaly(self):
        result = run_detection(HEALTHY_JOURNEYS)
        assert result.has_anomaly is False

    def test_primary_anomaly_is_highest_confidence(self):
        result = run_detection(SCENARIO_A_JOURNEYS)
        assert result.primary_anomaly is not None
        assert result.primary_anomaly.segment == "mobile_first_time"

    def test_summary_is_non_empty_string(self):
        result = run_detection(SCENARIO_A_JOURNEYS)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_summary_mentions_mobile_first_time_on_scenario_a(self):
        result = run_detection(SCENARIO_A_JOURNEYS)
        assert "mobile" in result.summary.lower()

    def test_healthy_summary_says_no_anomalies(self):
        result = run_detection(HEALTHY_JOURNEYS)
        assert "no anomalies" in result.summary.lower()

    def test_scenario_filter_excludes_other_scenarios(self):
        mixed = (
            _make_journeys(mobile_first_time=(3, 3), scenario="mobile_checkout_fee") +
            _make_journeys(mobile_first_time=(3, 0), scenario="other_scenario")
        )
        result = run_detection(mixed, scenario="other_scenario")
        # Only the healthy half passes the filter — no anomaly expected
        assert result.has_anomaly is False

    def test_to_dict_is_serialisable(self):
        result = run_detection(SCENARIO_A_JOURNEYS)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "has_anomaly" in d
        assert "anomalies" in d
        assert "segment_stats" in d


# ---------------------------------------------------------------------------
# Health score and BusinessSnapshot
# ---------------------------------------------------------------------------

class TestHealthScore:
    def test_healthy_cohort_scores_high(self):
        detection = run_detection(HEALTHY_JOURNEYS)
        score = compute_health_score(detection.segment_stats, detection)
        assert score >= 70, f"Expected healthy score ≥ 70, got {score}"

    def test_all_abandoned_scores_low(self):
        # All mobile-first-time abandon (and it's the majority of the cohort)
        journeys = _make_journeys(
            mobile_first_time=(4, 4),
            mobile_returning=(3, 3),
            desktop_first_time=(2, 2),
            desktop_returning=(2, 2),
        )
        detection = run_detection(journeys)
        score = compute_health_score(detection.segment_stats, detection)
        assert score < 50, f"Expected distressed score < 50, got {score}"

    def test_scenario_a_scores_lower_than_healthy(self):
        healthy_score = compute_health_score(
            run_detection(HEALTHY_JOURNEYS).segment_stats,
            run_detection(HEALTHY_JOURNEYS),
        )
        anomaly_score = compute_health_score(
            run_detection(SCENARIO_A_JOURNEYS).segment_stats,
            run_detection(SCENARIO_A_JOURNEYS),
        )
        assert anomaly_score < healthy_score

    def test_health_score_in_0_100_range(self):
        for journeys in [HEALTHY_JOURNEYS, SCENARIO_A_JOURNEYS, MARGINAL_JOURNEYS]:
            detection = run_detection(journeys)
            score = compute_health_score(detection.segment_stats, detection)
            assert 0 <= score <= 100


class TestBuildSnapshot:
    def test_snapshot_fields_populated(self):
        snap = build_snapshot(SCENARIO_A_JOURNEYS, scenario="mobile_checkout_fee")
        assert snap.total_journeys == len(SCENARIO_A_JOURNEYS)
        assert snap.completed + snap.abandoned == snap.total_journeys
        assert isinstance(snap.health_score, int)
        assert isinstance(snap.dollar_context, str)

    def test_dollar_context_contains_dollar_sign(self):
        snap = build_snapshot(SCENARIO_A_JOURNEYS)
        assert "$" in snap.dollar_context

    def test_health_delta_is_none_on_first_run(self):
        snap = build_snapshot(SCENARIO_A_JOURNEYS, previous_health=None)
        assert snap.health_delta is None

    def test_health_delta_reflects_improvement(self):
        snap = build_snapshot(HEALTHY_JOURNEYS, previous_health=57)
        assert snap.health_delta == snap.health_score - 57

    def test_to_dict_is_serialisable(self):
        snap = build_snapshot(SCENARIO_A_JOURNEYS)
        d = snap.to_dict()
        assert isinstance(d, dict)
        assert "health_score" in d
        assert "detection" in d

    def test_scenario_filter_applied_in_snapshot(self):
        mixed = (
            _make_journeys(mobile_first_time=(3, 3), scenario="mobile_checkout_fee") +
            _make_journeys(mobile_first_time=(3, 0), scenario="other")
        )
        snap_a     = build_snapshot(mixed, scenario="mobile_checkout_fee")
        snap_other = build_snapshot(mixed, scenario="other")
        assert snap_a.detection.has_anomaly is True
        assert snap_other.detection.has_anomaly is False
