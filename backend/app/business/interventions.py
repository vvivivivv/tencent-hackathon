"""
Deterministic intervention layer.

No LLM anywhere in this file.

Responsibilities:
  - Define the catalogue of available intervention types
  - Enforce business constraints before any write (CSAT floor, margin floor,
    root-cause confidence threshold)
  - Evaluate canary cohort results and decide pass / fail
  - Execute, record, and roll back interventions via Supabase
  - Maintain an immutable audit trail via the events table

Supabase schema mapping
-----------------------
  incidents   — one row per active investigation / intervention lifecycle
                status: 'open' → 'investigating' → 'canary_testing' → 'resolved'
                actions  (jsonb) — list of intervention dicts applied so far
                canary_result (jsonb) — last CanaryResult.to_dict()
                before_metrics / after_metrics (jsonb) — VerificationResult snapshots
                confidence (numeric) — root-cause confidence from Investigator

  events      — append-only audit log; every state transition writes one row
                type  = intervention_applied | canary_evaluated |
                        intervention_rolled_back | full_rollout_applied |
                        intervention_verified
                metadata (jsonb) — full detail dict

Pipeline (called by the Operator agent):
    Investigator result
        → validate_intervention()     constraint checks → raises on violation
        → apply_intervention()        write incidents row + audit event
        → run_canary()                evaluate cohort → update incidents + audit event
        → (pass)  full_rollout()      status → 'resolved' + audit event
        → (fail)  rollback_intervention()  status → 'open' + audit event + reason

All writes go through:
    LLM decision → structured call here → validate → constraint check
    → DB mutation (incidents) → audit entry (events)
No LLM-to-database direct writes, ever.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# Minimum root-cause confidence for the Operator to act autonomously.
# Below this the agent escalates to human review instead of writing.
MIN_ROOT_CAUSE_CONFIDENCE: float = 0.70

# Canary: minimum absolute improvement in conversion rate to pass.
CANARY_MIN_IMPROVEMENT_PP: float = 0.10      # 10 percentage points

# Business constraint floors
CSAT_FLOOR:   float = 0.80                   # 0–1 scale
MARGIN_FLOOR: float = 0.20                   # gross margin fraction

# Maximum fraction of affected journeys used in a canary cohort
CANARY_MAX_FRACTION: float = 0.40


INTERVENTION_TYPES: dict[str, dict] = {
    "remove_checkout_fee": {
        "description":   "Remove or waive an undisclosed fee at checkout",
        "reversible":    True,
        "margin_impact": "neutral",   # fee was suppressing conversion; removal recovers revenue
    },
    "update_faq": {
        "description":   "Update FAQ page to surface fee / pricing information earlier",
        "reversible":    True,
        "margin_impact": "neutral",
    },
    "update_checkout_copy": {
        "description":   "Rewrite checkout copy to disclose all charges upfront",
        "reversible":    True,
        "margin_impact": "neutral",
    },
    "send_customer_message": {
        "description":   "Send targeted message to affected segment explaining the fix",
        "reversible":    False,       # can't unsend; follow-up message is a separate intervention
        "margin_impact": "neutral",
    },
    "change_pricing": {
        "description":   "Change product / plan pricing",
        "reversible":    True,
        "margin_impact": "variable",  # depends on direction; checked at validation time
    },
    "apply_discount": {
        "description":   "Apply a discount coupon to affected customers",
        "reversible":    True,
        "margin_impact": "negative",  # always costs margin
    },
}


@dataclass
class InterventionRequest:
    """
    Submitted by the Operator agent.  Built from the LLM's structured decision;
    the deterministic layer validates it before any write.
    """
    intervention_type:      str            # key in INTERVENTION_TYPES
    scenario:               str            # scenario being addressed
    affected_segment:       str            # e.g. "mobile_first_time"
    root_cause_confidence:  float          # 0–1; from Investigator
    params:                 dict = field(default_factory=dict)
    # Optional business estimates for constraint checks
    estimated_csat_post:    Optional[float] = None   # 0–1
    estimated_margin_post:  Optional[float] = None   # 0–1 gross margin


@dataclass
class InterventionRecord:
    """
    Mirrors a row in the incidents table plus the action that was applied.

    Fields map to incidents columns:
        id                 → incidents.id
        status             → incidents.status
        affected_segment   → incidents.affected_segment
        root_cause         → incidents.root_cause (intervention_type)
        confidence         → incidents.confidence
        actions            → incidents.actions  (jsonb list)
        canary_result      → incidents.canary_result (jsonb)
        before_metrics     → incidents.before_metrics (jsonb)
        after_metrics      → incidents.after_metrics  (jsonb)
    """
    id:                     str
    intervention_type:      str
    scenario:               str
    affected_segment:       str
    root_cause_confidence:  float
    params:                 dict
    status:                 str    # open | investigating | canary_testing | resolved
    applied_at:             str    # ISO timestamp
    rolled_back_at:         Optional[str] = None
    rollback_reason:        Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id":                    self.id,
            "intervention_type":     self.intervention_type,
            "scenario":              self.scenario,
            "affected_segment":      self.affected_segment,
            "root_cause_confidence": self.root_cause_confidence,
            "params":                self.params,
            "status":                self.status,
            "applied_at":            self.applied_at,
            "rolled_back_at":        self.rolled_back_at,
            "rollback_reason":       self.rollback_reason,
        }

    # Convenience: shape that matches the incidents table schema
    def to_incident_row(self) -> dict:
        return {
            "id":               self.id,
            "title":            f"Intervention: {self.intervention_type} on {self.scenario}",
            "severity":         "high" if self.root_cause_confidence >= 0.85 else "medium",
            "affected_segment": self.affected_segment,
            "root_cause":       self.intervention_type,
            "confidence":       self.root_cause_confidence,
            "status":           self.status,
            "actions":          [self.to_dict()],
        }


@dataclass
class CanaryResult:
    """Result of evaluating a canary cohort against pre/post journeys."""
    intervention_id:    str
    passed:             bool
    pre_conversion_rate:  float
    post_conversion_rate: float
    improvement_pp:     float          # absolute PP improvement (can be negative)
    csat_post:          Optional[float]
    margin_post:        Optional[float]
    fail_reason:        Optional[str]  # None if passed

    def to_dict(self) -> dict:
        return {
            "intervention_id":  self.intervention_id,
            "passed":           self.passed,
            "pre_conversion":   round(self.pre_conversion_rate, 3),
            "post_conversion":  round(self.post_conversion_rate, 3),
            "improvement_pp":   round(self.improvement_pp, 3),
            "csat_post":        self.csat_post,
            "margin_post":      self.margin_post,
            "fail_reason":      self.fail_reason,
        }


@dataclass
class VerificationResult:
    """Before/after comparison after full rollout — shown in the impact report."""
    intervention_id:           str
    pre_conversion_rate:       float
    post_conversion_rate:      float
    improvement_pp:            float
    pre_health_score:          int
    post_health_score:         int
    health_delta:              int
    monthly_revenue_recovered: float
    resolved:                  bool

    def to_dict(self) -> dict:
        return {
            "intervention_id":           self.intervention_id,
            "pre_conversion":            round(self.pre_conversion_rate, 3),
            "post_conversion":           round(self.post_conversion_rate, 3),
            "improvement_pp":            round(self.improvement_pp, 3),
            "pre_health_score":          self.pre_health_score,
            "post_health_score":         self.post_health_score,
            "health_delta":              self.health_delta,
            "monthly_revenue_recovered": round(self.monthly_revenue_recovered, 2),
            "resolved":                  self.resolved,
        }


class ConstraintViolation(Exception):
    """
    Raised when a proposed intervention violates a business constraint.
    The Operator catches this, logs the reason, and selects an alternative.
    """
    def __init__(self, constraint: str, reason: str) -> None:
        self.constraint = constraint
        self.reason = reason
        super().__init__(f"[{constraint}] {reason}")


class LowConfidenceError(Exception):
    """
    Raised when root-cause confidence < MIN_ROOT_CAUSE_CONFIDENCE.
    The Operator must escalate to human review; no writes occur.
    """
    def __init__(self, confidence: float) -> None:
        self.confidence = confidence
        super().__init__(
            f"Root-cause confidence {confidence:.0%} is below the "
            f"{MIN_ROOT_CAUSE_CONFIDENCE:.0%} minimum. Escalating to human review."
        )


def validate_intervention(request: InterventionRequest) -> None:
    """
    Enforce all business constraints before any DB write.

    Checks (in order):
      1. Root-cause confidence ≥ MIN_ROOT_CAUSE_CONFIDENCE
      2. intervention_type is in the catalogue
      3. Negative-margin interventions require an explicit margin estimate
      4. estimated_margin_post ≥ MARGIN_FLOOR  (if supplied or required)
      5. estimated_csat_post   ≥ CSAT_FLOOR    (if supplied)

    Raises LowConfidenceError or ConstraintViolation on failure.
    Returns None on approval — no side effects.
    """
    # 1. Confidence gate
    if request.root_cause_confidence < MIN_ROOT_CAUSE_CONFIDENCE:
        raise LowConfidenceError(request.root_cause_confidence)

    # 2. Known type
    if request.intervention_type not in INTERVENTION_TYPES:
        raise ConstraintViolation(
            "unknown_intervention",
            f"'{request.intervention_type}' is not in the catalogue. "
            f"Valid: {', '.join(INTERVENTION_TYPES)}",
        )

    spec = INTERVENTION_TYPES[request.intervention_type]

    # 3+4. Margin
    if spec["margin_impact"] == "negative":
        if request.estimated_margin_post is None:
            raise ConstraintViolation(
                "margin_check_required",
                f"'{request.intervention_type}' has negative margin impact. "
                f"Supply estimated_margin_post before proceeding.",
            )
        if request.estimated_margin_post < MARGIN_FLOOR:
            raise ConstraintViolation(
                "margin_floor",
                f"Estimated post-intervention margin {request.estimated_margin_post:.1%} "
                f"is below floor {MARGIN_FLOOR:.1%}. Intervention rejected.",
            )

    # 5. CSAT
    if request.estimated_csat_post is not None:
        if request.estimated_csat_post < CSAT_FLOOR:
            raise ConstraintViolation(
                "csat_floor",
                f"Estimated post-intervention CSAT {request.estimated_csat_post:.1%} "
                f"would fall below floor {CSAT_FLOOR:.1%}. Intervention rejected.",
            )


_store: dict[str, InterventionRecord] = {}
_audit_log: list[dict] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(event_type: str, intervention_id: str, detail: dict) -> None:
    """
    Append an immutable audit entry.

    In a live run (db is not None) this writes to the events table:
        type        = event_type
        journey_id  = None  (incident-level event, not tied to one journey)
        metadata    = {intervention_id, ...detail}
    """
    _audit_log.append({
        "event_type":      event_type,
        "intervention_id": intervention_id,
        "timestamp":       _now_iso(),
        **detail,
    })


def get_audit_log() -> list[dict]:
    """Return a copy of the in-memory audit log (read-only; for tests)."""
    return list(_audit_log)


def clear_store() -> None:
    """Reset in-memory state between tests. Do not call in production."""
    _store.clear()
    _audit_log.clear()


def _db_insert_incident(db, record: InterventionRecord) -> None:
    db.table("incidents").insert(record.to_incident_row()).execute()


def _db_update_incident(db, incident_id: str, patch: dict) -> None:
    db.table("incidents").update(patch).eq("id", incident_id).execute()


def _db_insert_event(db, event_type: str, intervention_id: str, detail: dict) -> None:
    db.table("events").insert({
        "type":      event_type,
        "metadata":  {"intervention_id": intervention_id, **detail},
    }).execute()


def apply_intervention(
    request: InterventionRequest,
    db=None,
) -> InterventionRecord:
    """
    Validate then record a new intervention.

    On success:
      - Writes an incidents row (status = 'investigating')
      - Writes an events row (type = 'intervention_applied')
      - Stores the record in _store for subsequent lifecycle calls

    Raises ConstraintViolation or LowConfidenceError if validation fails;
    no DB writes occur on failure.
    """
    validate_intervention(request)   # raises on violation — must come first

    record = InterventionRecord(
        id=str(uuid.uuid4()),
        intervention_type=request.intervention_type,
        scenario=request.scenario,
        affected_segment=request.affected_segment,
        root_cause_confidence=request.root_cause_confidence,
        params=request.params,
        status="investigating",
        applied_at=_now_iso(),
    )

    _store[record.id] = record

    detail = {
        "type":       record.intervention_type,
        "scenario":   record.scenario,
        "segment":    record.affected_segment,
        "confidence": record.root_cause_confidence,
        "params":     record.params,
    }
    _audit("intervention_applied", record.id, detail)

    if db is not None:
        _db_insert_incident(db, record)
        _db_insert_event(db, "intervention_applied", record.id, detail)

    return record


def run_canary(
    intervention_id: str,
    pre_journeys: list[dict],
    post_journeys: list[dict],
    csat_post: Optional[float] = None,
    margin_post: Optional[float] = None,
    db=None,
) -> CanaryResult:
    """
    Evaluate a canary cohort and decide pass / fail.

    Decision rules (all deterministic):
      1. post_conversion − pre_conversion ≥ CANARY_MIN_IMPROVEMENT_PP  → pass
      2. csat_post  < CSAT_FLOOR   (if provided)                       → fail
      3. margin_post < MARGIN_FLOOR (if provided)                      → fail

    On completion:
      - Updates incidents.status to 'canary_testing'
      - Updates incidents.canary_result
      - Writes an events row (type = 'canary_evaluated')
    """
    record = _store.get(intervention_id)
    if record is None:
        raise ValueError(f"No intervention with id={intervention_id}")

    def _conv(journeys: list[dict]) -> float:
        if not journeys:
            return 0.0
        return sum(1 for j in journeys if j["result"] == "completed") / len(journeys)

    pre_conv  = _conv(pre_journeys)
    post_conv = _conv(post_journeys)
    improvement_pp = post_conv - pre_conv

    fail_reason: Optional[str] = None

    if improvement_pp < CANARY_MIN_IMPROVEMENT_PP:
        fail_reason = (
            f"Improvement {improvement_pp:+.1%} below minimum "
            f"{CANARY_MIN_IMPROVEMENT_PP:.1%}."
        )

    if csat_post is not None and csat_post < CSAT_FLOOR:
        msg = f"CSAT {csat_post:.1%} fell below floor {CSAT_FLOOR:.1%}."
        fail_reason = f"{fail_reason} {msg}" if fail_reason else msg

    if margin_post is not None and margin_post < MARGIN_FLOOR:
        msg = f"Margin {margin_post:.1%} fell below floor {MARGIN_FLOOR:.1%}."
        fail_reason = f"{fail_reason} {msg}" if fail_reason else msg

    passed = fail_reason is None
    result = CanaryResult(
        intervention_id=intervention_id,
        passed=passed,
        pre_conversion_rate=pre_conv,
        post_conversion_rate=post_conv,
        improvement_pp=improvement_pp,
        csat_post=csat_post,
        margin_post=margin_post,
        fail_reason=fail_reason,
    )

    record.status = "canary_testing"
    detail = result.to_dict()
    _audit("canary_evaluated", intervention_id, detail)

    if db is not None:
        _db_update_incident(db, intervention_id, {
            "status":        "canary_testing",
            "canary_result": detail,
        })
        _db_insert_event(db, "canary_evaluated", intervention_id, detail)

    return result


def rollback_intervention(
    intervention_id: str,
    reason: str,
    db=None,
) -> InterventionRecord:
    """
    Mark an intervention as rolled back; write an immutable audit entry.

    Called by the Operator when:
      - run_canary() returns passed=False
      - A downstream constraint violation occurs during staged rollout

    Must be called before selecting an alternative intervention — this is
    what makes the agent's risk management visible in the console.

    Updates incidents.status back to 'open' so the investigation can restart.
    """
    record = _store.get(intervention_id)
    if record is None:
        raise ValueError(f"No intervention with id={intervention_id}")

    record.status = "open"
    record.rolled_back_at = _now_iso()
    record.rollback_reason = reason

    detail = {"reason": reason, "was_type": record.intervention_type}
    _audit("intervention_rolled_back", intervention_id, detail)

    if db is not None:
        _db_update_incident(db, intervention_id, {
            "status":          "open",
            "actions":         [record.to_dict()],
        })
        _db_insert_event(db, "intervention_rolled_back", intervention_id, detail)

    return record


def full_rollout(
    intervention_id: str,
    db=None,
) -> InterventionRecord:
    """
    Promote a canary-passed intervention to resolved (full rollout).

    Precondition: the record must be in 'canary_testing' status, meaning
    run_canary() was called and returned passed=True.

    Updates incidents.status to 'resolved'.
    """
    record = _store.get(intervention_id)
    if record is None:
        raise ValueError(f"No intervention with id={intervention_id}")
    if record.status != "canary_testing":
        raise ValueError(
            f"Intervention {intervention_id} has status '{record.status}'; "
            f"full_rollout() requires 'canary_testing'. Run run_canary() first."
        )

    record.status = "resolved"
    detail = {"type": record.intervention_type, "segment": record.affected_segment}
    _audit("full_rollout_applied", intervention_id, detail)

    if db is not None:
        _db_update_incident(db, intervention_id, {
            "status":       "resolved",
            "resolved_at":  _now_iso(),
        })
        _db_insert_event(db, "full_rollout_applied", intervention_id, detail)

    return record


def verify_intervention(
    intervention_id: str,
    pre_journeys: list[dict],
    post_journeys: list[dict],
    pre_health_score: int,
    post_health_score: int,
    revenue_per_conversion: float = 120.0,
    monthly_customers: int = 500,
    db=None,
) -> VerificationResult:
    """
    Final before/after comparison after full rollout.

    Produces the numbers shown in the Business Health Meter and impact report.
    Writes before_metrics + after_metrics to the incidents row.
    """
    record = _store.get(intervention_id)
    if record is None:
        raise ValueError(f"No intervention with id={intervention_id}")

    def _conv(journeys: list[dict]) -> float:
        if not journeys:
            return 0.0
        return sum(1 for j in journeys if j["result"] == "completed") / len(journeys)

    pre_conv  = _conv(pre_journeys)
    post_conv = _conv(post_journeys)
    improvement_pp = post_conv - pre_conv
    monthly_revenue_recovered = improvement_pp * monthly_customers * revenue_per_conversion
    resolved = improvement_pp >= CANARY_MIN_IMPROVEMENT_PP

    result = VerificationResult(
        intervention_id=intervention_id,
        pre_conversion_rate=pre_conv,
        post_conversion_rate=post_conv,
        improvement_pp=improvement_pp,
        pre_health_score=pre_health_score,
        post_health_score=post_health_score,
        health_delta=post_health_score - pre_health_score,
        monthly_revenue_recovered=monthly_revenue_recovered,
        resolved=resolved,
    )

    detail = result.to_dict()
    _audit("intervention_verified", intervention_id, detail)

    if db is not None:
        _db_update_incident(db, intervention_id, {
            "before_metrics": {"conversion_rate": pre_conv,  "health_score": pre_health_score},
            "after_metrics":  {"conversion_rate": post_conv, "health_score": post_health_score,
                               "monthly_revenue_recovered": monthly_revenue_recovered},
        })
        _db_insert_event(db, "intervention_verified", intervention_id, detail)

    return result
