"""
Unit tests for the deterministic intervention layer (business/interventions.py).

No LLM, no Supabase, no network — everything runs against the in-memory store.

Boundary conditions from README §5.5:
  BC-1  CSAT below floor          → ConstraintViolation('csat_floor')
  BC-2  Canary improvement low    → passed=False + rollback_intervention() works
  BC-3  Margin-destroying action  → ConstraintViolation('margin_floor')
  BC-4  Low root-cause confidence → LowConfidenceError, no write

Additional cases:
  - Happy-path full lifecycle:    apply → canary pass → full_rollout → verify
  - Unknown intervention type     → ConstraintViolation('unknown_intervention')
  - Discount without margin est.  → ConstraintViolation('margin_check_required')
  - full_rollout without canary   → ValueError (wrong status)
  - rollback sets status to 'open' and records reason
  - Audit log has one entry per lifecycle step, in order
  - verify_intervention calculates monthly_revenue_recovered correctly
  - to_dict / to_incident_row are serialisable and contain required keys
"""

import pytest

from app.business.interventions import (
    # config
    MIN_ROOT_CAUSE_CONFIDENCE,
    CANARY_MIN_IMPROVEMENT_PP,
    CSAT_FLOOR,
    MARGIN_FLOOR,
    # types
    InterventionRequest,
    # exceptions
    ConstraintViolation,
    LowConfidenceError,
    # operations
    apply_intervention,
    run_canary,
    rollback_intervention,
    full_rollout,
    verify_intervention,
    validate_intervention,
    # store helpers
    clear_store,
    get_audit_log,
)


@pytest.fixture(autouse=True)
def reset_store():
    """Wipe in-memory state before every test — tests must be independent."""
    clear_store()
    yield
    clear_store()


def _good_request(**overrides) -> InterventionRequest:
    """Return a valid InterventionRequest; caller can override any field."""
    base = dict(
        intervention_type="remove_checkout_fee",
        scenario="mobile_checkout_fee",
        affected_segment="mobile_first_time",
        root_cause_confidence=0.85,
        params={},
        estimated_csat_post=None,
        estimated_margin_post=None,
    )
    base.update(overrides)
    return InterventionRequest(**base)


def _journeys(total: int, completed: int) -> list[dict]:
    """Build a minimal journey list with `completed` completions out of `total`."""
    journeys = []
    for i in range(total):
        journeys.append({
            "result": "completed" if i < completed else "abandoned",
            "device": "mobile",
            "customer_type": "first_time",
            "scenario": "mobile_checkout_fee",
        })
    return journeys


class TestCSATFloor:
    def test_csat_below_floor_raises(self):
        req = _good_request(estimated_csat_post=CSAT_FLOOR - 0.01)
        with pytest.raises(ConstraintViolation) as exc:
            validate_intervention(req)
        assert exc.value.constraint == "csat_floor"

    def test_csat_exactly_at_floor_is_accepted(self):
        req = _good_request(estimated_csat_post=CSAT_FLOOR)
        validate_intervention(req)   # must not raise

    def test_csat_above_floor_is_accepted(self):
        req = _good_request(estimated_csat_post=0.95)
        validate_intervention(req)   # must not raise

    def test_csat_violation_prevents_db_write(self):
        req = _good_request(estimated_csat_post=0.50)
        with pytest.raises(ConstraintViolation):
            apply_intervention(req)
        assert get_audit_log() == []     # nothing written


class TestCanaryFail:
    def test_insufficient_improvement_fails(self):
        req = _good_request()
        record = apply_intervention(req)

        # improvement = 0.0 — below 10 pp minimum
        pre  = _journeys(total=5, completed=1)
        post = _journeys(total=5, completed=1)
        result = run_canary(record.id, pre, post)

        assert result.passed is False
        assert result.fail_reason is not None
        assert "improvement" in result.fail_reason.lower()

    def test_canary_fail_allows_rollback(self):
        req = _good_request()
        record = apply_intervention(req)

        pre  = _journeys(5, 0)
        post = _journeys(5, 0)
        run_canary(record.id, pre, post)

        rolled = rollback_intervention(record.id, reason="canary failed: no improvement")
        assert rolled.status == "open"
        assert rolled.rollback_reason == "canary failed: no improvement"

    def test_canary_exactly_at_minimum_passes(self):
        req = _good_request()
        record = apply_intervention(req)

        # 0/10 → 1/10 = exactly 10 pp improvement
        pre  = _journeys(10, 0)
        post = _journeys(10, 1)
        result = run_canary(record.id, pre, post)
        assert result.passed is True

    def test_canary_csat_fail_reason_included(self):
        req = _good_request()
        record = apply_intervention(req)

        pre  = _journeys(5, 0)
        post = _journeys(5, 5)   # conversion passes
        result = run_canary(record.id, pre, post, csat_post=0.50)

        assert result.passed is False
        assert "csat" in result.fail_reason.lower()

    def test_canary_margin_fail_reason_included(self):
        req = _good_request()
        record = apply_intervention(req)

        pre  = _journeys(5, 0)
        post = _journeys(5, 5)   # conversion passes
        result = run_canary(record.id, pre, post, margin_post=0.05)

        assert result.passed is False
        assert "margin" in result.fail_reason.lower()


class TestMarginFloor:
    def test_discount_below_margin_floor_raises(self):
        req = _good_request(
            intervention_type="apply_discount",
            estimated_margin_post=MARGIN_FLOOR - 0.01,
        )
        with pytest.raises(ConstraintViolation) as exc:
            validate_intervention(req)
        assert exc.value.constraint == "margin_floor"

    def test_discount_without_margin_estimate_raises(self):
        req = _good_request(
            intervention_type="apply_discount",
            estimated_margin_post=None,   # forgot to supply
        )
        with pytest.raises(ConstraintViolation) as exc:
            validate_intervention(req)
        assert exc.value.constraint == "margin_check_required"

    def test_discount_above_floor_accepted(self):
        req = _good_request(
            intervention_type="apply_discount",
            estimated_margin_post=MARGIN_FLOOR + 0.05,
        )
        validate_intervention(req)   # must not raise

    def test_margin_violation_prevents_db_write(self):
        req = _good_request(
            intervention_type="apply_discount",
            estimated_margin_post=0.05,
        )
        with pytest.raises(ConstraintViolation):
            apply_intervention(req)
        assert get_audit_log() == []


class TestLowConfidence:
    def test_below_threshold_raises_low_confidence_error(self):
        req = _good_request(root_cause_confidence=MIN_ROOT_CAUSE_CONFIDENCE - 0.01)
        with pytest.raises(LowConfidenceError) as exc:
            validate_intervention(req)
        assert exc.value.confidence == pytest.approx(MIN_ROOT_CAUSE_CONFIDENCE - 0.01)

    def test_exactly_at_threshold_is_accepted(self):
        req = _good_request(root_cause_confidence=MIN_ROOT_CAUSE_CONFIDENCE)
        validate_intervention(req)   # must not raise

    def test_low_confidence_prevents_any_write(self):
        req = _good_request(root_cause_confidence=0.50)
        with pytest.raises(LowConfidenceError):
            apply_intervention(req)
        assert get_audit_log() == []
        assert len(get_audit_log()) == 0

    def test_error_message_mentions_escalation(self):
        req = _good_request(root_cause_confidence=0.40)
        with pytest.raises(LowConfidenceError) as exc:
            validate_intervention(req)
        assert "escalat" in str(exc.value).lower()


class TestFullLifecycle:
    def test_apply_returns_investigating_status(self):
        record = apply_intervention(_good_request())
        assert record.status == "investigating"
        assert record.intervention_type == "remove_checkout_fee"

    def test_apply_writes_audit_entry(self):
        apply_intervention(_good_request())
        log = get_audit_log()
        assert len(log) == 1
        assert log[0]["event_type"] == "intervention_applied"

    def test_canary_pass_sets_canary_testing_status(self):
        record = apply_intervention(_good_request())
        pre  = _journeys(10, 2)
        post = _journeys(10, 8)
        result = run_canary(record.id, pre, post)
        assert result.passed is True
        assert record.status == "canary_testing"

    def test_full_rollout_sets_resolved_status(self):
        record = apply_intervention(_good_request())
        pre  = _journeys(10, 2)
        post = _journeys(10, 9)
        run_canary(record.id, pre, post)
        full_rollout(record.id)
        assert record.status == "resolved"

    def test_full_rollout_without_canary_raises(self):
        record = apply_intervention(_good_request())
        with pytest.raises(ValueError, match="canary_testing"):
            full_rollout(record.id)

    def test_verify_calculates_revenue_recovered(self):
        record = apply_intervention(_good_request())
        pre  = _journeys(10, 2)
        post = _journeys(10, 8)
        run_canary(record.id, pre, post)
        full_rollout(record.id)

        vr = verify_intervention(
            record.id,
            pre_journeys=_journeys(20, 4),
            post_journeys=_journeys(20, 16),
            pre_health_score=55,
            post_health_score=82,
            revenue_per_conversion=100.0,
            monthly_customers=400,
        )
        # 16/20=0.80 − 4/20=0.20 = 0.60 improvement; 0.60×400×100 = $24,000
        assert vr.improvement_pp == pytest.approx(0.60)
        assert vr.monthly_revenue_recovered == pytest.approx(24_000.0)
        assert vr.health_delta == 27
        assert vr.resolved is True

    def test_audit_log_has_all_lifecycle_entries(self):
        record = apply_intervention(_good_request())
        pre  = _journeys(10, 2)
        post = _journeys(10, 9)
        run_canary(record.id, pre, post)
        full_rollout(record.id)
        verify_intervention(
            record.id,
            pre_journeys=pre,
            post_journeys=post,
            pre_health_score=55,
            post_health_score=80,
        )
        event_types = [e["event_type"] for e in get_audit_log()]
        assert event_types == [
            "intervention_applied",
            "canary_evaluated",
            "full_rollout_applied",
            "intervention_verified",
        ]


class TestRollback:
    def test_rollback_sets_open_status(self):
        record = apply_intervention(_good_request())
        pre  = _journeys(5, 0)
        post = _journeys(5, 0)
        run_canary(record.id, pre, post)
        rolled = rollback_intervention(record.id, reason="no improvement observed")
        assert rolled.status == "open"

    def test_rollback_records_reason(self):
        record = apply_intervention(_good_request())
        run_canary(record.id, _journeys(3, 0), _journeys(3, 0))
        rollback_intervention(record.id, reason="csat degraded unexpectedly")
        assert record.rollback_reason == "csat degraded unexpectedly"

    def test_rollback_writes_audit_entry(self):
        record = apply_intervention(_good_request())
        run_canary(record.id, _journeys(3, 0), _journeys(3, 0))
        rollback_intervention(record.id, reason="test")
        types = [e["event_type"] for e in get_audit_log()]
        assert "intervention_rolled_back" in types

    def test_rollback_unknown_id_raises(self):
        with pytest.raises(ValueError, match="No intervention"):
            rollback_intervention("nonexistent-id", reason="test")


class TestEdgeCases:
    def test_unknown_intervention_type_raises(self):
        req = _good_request(intervention_type="launch_missiles")
        with pytest.raises(ConstraintViolation) as exc:
            validate_intervention(req)
        assert exc.value.constraint == "unknown_intervention"

    def test_empty_pre_journeys_gives_zero_conversion(self):
        record = apply_intervention(_good_request())
        result = run_canary(record.id, [], _journeys(5, 5))
        # post=1.0, pre=0.0 → improvement=1.0 → passes
        assert result.pre_conversion_rate == 0.0
        assert result.passed is True

    def test_to_dict_contains_required_keys(self):
        record = apply_intervention(_good_request())
        d = record.to_dict()
        for key in ("id", "intervention_type", "scenario", "affected_segment",
                    "root_cause_confidence", "status", "applied_at"):
            assert key in d, f"Missing key: {key}"

    def test_to_incident_row_maps_to_schema_columns(self):
        record = apply_intervention(_good_request())
        row = record.to_incident_row()
        for col in ("id", "title", "severity", "affected_segment",
                    "root_cause", "confidence", "status", "actions"):
            assert col in row, f"Missing incidents column: {col}"

    def test_canary_result_to_dict_serialisable(self):
        record = apply_intervention(_good_request())
        result = run_canary(record.id, _journeys(5, 0), _journeys(5, 5))
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "passed" in d and "improvement_pp" in d

    def test_run_canary_unknown_id_raises(self):
        with pytest.raises(ValueError, match="No intervention"):
            run_canary("bad-id", [], [])

    def test_multiple_interventions_are_independent(self):
        r1 = apply_intervention(_good_request())
        r2 = apply_intervention(_good_request())
        assert r1.id != r2.id
        assert len(get_audit_log()) == 2
