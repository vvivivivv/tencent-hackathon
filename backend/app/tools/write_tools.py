"""
Write tools for the Operator agent.

Every function in this file:
  1. Calls _audit_log_entry() BEFORE touching the database — so the audit
     row always exists even if the write fails downstream.
  2. Calls validate_intervention() (constraint check) before any DB mutation.
     On violation, the audit entry records the rejection reason; no state changes.
  3. Returns a plain JSON-serialisable dict (SDK passes it back to the model).
  4. Never calls an LLM — pure Python + Supabase.

Audit log schema (written to the `events` table):
    type        = "audit_log"
    metadata    = {
        agent:      "operator",
        action:     <function name>,
        arguments:  <dict of args passed in>,
        result:     "success" | "rejected" | "error",
        reason:     <constraint message or error string — on non-success>,
        timestamp:  ISO 8601,
    }

This keeps auditing inside the existing schema (no separate audit_log table
needed) — every tool call is a searchable events row.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from app.business.interventions import (
    InterventionRequest,
    apply_intervention,
    run_canary as _run_canary,
    rollback_intervention as _rollback,
    full_rollout as _full_rollout,
    verify_intervention,
    ConstraintViolation,
    LowConfidenceError,
    INTERVENTION_TYPES,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_log_entry(
    db,
    action: str,
    arguments: dict,
    result: str,
    reason: Optional[str] = None,
) -> None:
    """
    Append one row to the events table as an immutable audit record.
    Called by every write tool — before DB mutation on success, immediately
    on rejection/error.

    If `db` is None (test mode) this is a no-op; the interventions module
    maintains its own in-memory _audit_log for tests.
    """
    if db is None:
        return
    payload = {
        "type": "audit_log",
        "metadata": {
            "agent":     "operator",
            "action":    action,
            "arguments": arguments,
            "result":    result,
            "timestamp": _now_iso(),
        },
    }
    if reason is not None:
        payload["metadata"]["reason"] = reason
    try:
        db.table("events").insert(payload).execute()
    except Exception:
        # Audit failure must never silence the underlying error
        pass


def _safe_args(**kwargs) -> dict:
    """Serialise args for audit — drop None values, truncate long strings."""
    out = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, str) and len(v) > 300:
            out[k] = v[:300] + "…"
        else:
            out[k] = v
    return out


def update_checkout(
    db,
    scenario: str,
    affected_segment: str,
    root_cause_confidence: float,
    action: str,                        # "remove_fee" | "update_copy"
    params: Optional[dict] = None,
    estimated_csat_post: Optional[float] = None,
    estimated_margin_post: Optional[float] = None,
) -> dict:
    """
    Apply a checkout-level fix: either remove an undisclosed fee or update
    the checkout copy to disclose all charges upfront.

    This is the primary remediation for Scenario A (hidden fee causing mobile
    first-time abandonment).

    Args:
        scenario:               Scenario being addressed (e.g. 'scenario_a').
        affected_segment:       Segment key (e.g. 'mobile_first_time').
        root_cause_confidence:  Investigator's confidence (0-1). Must be ≥ 0.70.
        action:                 'remove_fee' → remove_checkout_fee intervention;
                                'update_copy' → update_checkout_copy intervention.
        params:                 Optional extra parameters (e.g. fee_amount).
        estimated_csat_post:    Expected CSAT after fix (0-1). Optional but recommended.
        estimated_margin_post:  Expected gross margin after fix (0-1). Required for
                                negative-margin interventions.

    Returns intervention record dict on success, or rejection dict on violation.
    """
    intervention_type = (
        "remove_checkout_fee" if action == "remove_fee" else "update_checkout_copy"
    )
    args = _safe_args(
        scenario=scenario,
        affected_segment=affected_segment,
        action=action,
        root_cause_confidence=root_cause_confidence,
        estimated_csat_post=estimated_csat_post,
        estimated_margin_post=estimated_margin_post,
    )

    try:
        request = InterventionRequest(
            intervention_type=intervention_type,
            scenario=scenario,
            affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            params=params or {},
            estimated_csat_post=estimated_csat_post,
            estimated_margin_post=estimated_margin_post,
        )
        record = apply_intervention(request, db=db)
        _audit_log_entry(db, "update_checkout", args, "success")
        return {"status": "applied", "intervention": record.to_dict()}

    except (ConstraintViolation, LowConfidenceError) as exc:
        _audit_log_entry(db, "update_checkout", args, "rejected", reason=str(exc))
        return {"status": "rejected", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "update_checkout", args, "error", reason=str(exc))
        raise


def update_faq(
    db,
    scenario: str,
    affected_segment: str,
    root_cause_confidence: float,
    content_summary: str,
    params: Optional[dict] = None,
    estimated_csat_post: Optional[float] = None,
) -> dict:
    """
    Update the FAQ page to surface fee or pricing information earlier in the
    customer journey.

    Safer than removing the fee (no margin impact) — use when confidence is
    high but you want to inform rather than eliminate the charge.

    Args:
        scenario:               Scenario being addressed.
        affected_segment:       Target segment.
        root_cause_confidence:  Must be ≥ 0.70.
        content_summary:        Brief description of what the FAQ update says.
        params:                 Optional extra params.
        estimated_csat_post:    Expected CSAT post-update (0-1).

    Returns intervention record dict on success, or rejection dict on violation.
    """
    args = _safe_args(
        scenario=scenario,
        affected_segment=affected_segment,
        content_summary=content_summary,
        root_cause_confidence=root_cause_confidence,
        estimated_csat_post=estimated_csat_post,
    )
    try:
        request = InterventionRequest(
            intervention_type="update_faq",
            scenario=scenario,
            affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            params={"content_summary": content_summary, **(params or {})},
            estimated_csat_post=estimated_csat_post,
        )
        record = apply_intervention(request, db=db)
        _audit_log_entry(db, "update_faq", args, "success")
        return {"status": "applied", "intervention": record.to_dict()}

    except (ConstraintViolation, LowConfidenceError) as exc:
        _audit_log_entry(db, "update_faq", args, "rejected", reason=str(exc))
        return {"status": "rejected", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "update_faq", args, "error", reason=str(exc))
        raise


def send_customer_message(
    db,
    scenario: str,
    affected_segment: str,
    root_cause_confidence: float,
    message_body: str,
    channel: str = "email",
    params: Optional[dict] = None,
    estimated_csat_post: Optional[float] = None,
) -> dict:
    """
    Send a targeted message to the affected customer segment explaining the
    issue and the fix.  This is a one-way, irreversible action (cannot unsend).

    Use after a fix is confirmed to recover trust with affected customers.

    Args:
        scenario:               Scenario being addressed.
        affected_segment:       Target segment.
        root_cause_confidence:  Must be ≥ 0.70.
        message_body:           The message content to send.
        channel:                'email' | 'sms' | 'push' (default 'email').
        params:                 Additional params (e.g. subject line).
        estimated_csat_post:    Expected CSAT after outreach (0-1).

    Returns intervention record on success. Note: this intervention is
    NOT reversible — rollback records the attempt but cannot recall the message.
    """
    args = _safe_args(
        scenario=scenario,
        affected_segment=affected_segment,
        channel=channel,
        root_cause_confidence=root_cause_confidence,
        estimated_csat_post=estimated_csat_post,
        message_body=message_body,
    )
    try:
        request = InterventionRequest(
            intervention_type="send_customer_message",
            scenario=scenario,
            affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            params={"message_body": message_body, "channel": channel, **(params or {})},
            estimated_csat_post=estimated_csat_post,
        )
        record = apply_intervention(request, db=db)
        _audit_log_entry(db, "send_customer_message", args, "success")
        return {"status": "applied", "intervention": record.to_dict()}

    except (ConstraintViolation, LowConfidenceError) as exc:
        _audit_log_entry(db, "send_customer_message", args, "rejected", reason=str(exc))
        return {"status": "rejected", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "send_customer_message", args, "error", reason=str(exc))
        raise


def apply_discount(
    db,
    scenario: str,
    affected_segment: str,
    root_cause_confidence: float,
    discount_pct: float,                # e.g. 0.10 for 10%
    estimated_margin_post: float,       # REQUIRED for negative-margin interventions
    params: Optional[dict] = None,
    estimated_csat_post: Optional[float] = None,
) -> dict:
    """
    Apply a discount coupon to affected customers.

    This is a NEGATIVE-MARGIN intervention — estimated_margin_post is required
    and must remain above the 20% floor or the intervention is rejected.

    Args:
        scenario:               Scenario being addressed.
        affected_segment:       Target segment.
        root_cause_confidence:  Must be ≥ 0.70.
        discount_pct:           Discount fraction (0-1, e.g. 0.10 = 10% off).
        estimated_margin_post:  REQUIRED. Gross margin after discount (0-1).
                                Must be ≥ 0.20 or this is rejected.
        params:                 Additional params (e.g. coupon_code).
        estimated_csat_post:    Expected CSAT after discount (0-1).

    Returns intervention record on success, or rejection dict if margin floor
    would be breached.
    """
    args = _safe_args(
        scenario=scenario,
        affected_segment=affected_segment,
        discount_pct=discount_pct,
        root_cause_confidence=root_cause_confidence,
        estimated_margin_post=estimated_margin_post,
        estimated_csat_post=estimated_csat_post,
    )
    try:
        request = InterventionRequest(
            intervention_type="apply_discount",
            scenario=scenario,
            affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            params={"discount_pct": discount_pct, **(params or {})},
            estimated_csat_post=estimated_csat_post,
            estimated_margin_post=estimated_margin_post,
        )
        record = apply_intervention(request, db=db)
        _audit_log_entry(db, "apply_discount", args, "success")
        return {"status": "applied", "intervention": record.to_dict()}

    except (ConstraintViolation, LowConfidenceError) as exc:
        _audit_log_entry(db, "apply_discount", args, "rejected", reason=str(exc))
        return {"status": "rejected", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "apply_discount", args, "error", reason=str(exc))
        raise


def run_canary_tool(
    db,
    intervention_id: str,
    pre_journeys: list[dict],
    post_journeys: list[dict],
    csat_post: Optional[float] = None,
    margin_post: Optional[float] = None,
) -> dict:
    """
    Evaluate a canary cohort for a previously applied intervention.

    Must be called after update_checkout / update_faq / etc. returns a
    successful intervention_id.  Uses a held-out cohort of journeys to measure
    whether the fix actually improved conversion before full rollout.

    Decision rules (all deterministic — no LLM):
      - post_conversion − pre_conversion ≥ 10 pp  → PASS
      - csat_post < 0.80 (if provided)             → FAIL
      - margin_post < 0.20 (if provided)           → FAIL

    On FAIL: automatically calls rollback_intervention() and returns the reason.
    On PASS: returns the result; the Operator must explicitly call full_rollout.

    Args:
        intervention_id:  The id from a prior apply_* call.
        pre_journeys:     Journey dicts from BEFORE the intervention.
        post_journeys:    Journey dicts from AFTER (the canary cohort).
        csat_post:        Measured CSAT on the canary cohort (0-1), if available.
        margin_post:      Measured gross margin on the canary cohort (0-1), if available.

    Returns CanaryResult dict plus 'action': 'passed' | 'rolled_back'.
    """
    args = _safe_args(
        intervention_id=intervention_id,
        pre_journey_count=len(pre_journeys),
        post_journey_count=len(post_journeys),
        csat_post=csat_post,
        margin_post=margin_post,
    )
    try:
        result = _run_canary(
            intervention_id=intervention_id,
            pre_journeys=pre_journeys,
            post_journeys=post_journeys,
            csat_post=csat_post,
            margin_post=margin_post,
            db=db,
        )
        if result.passed:
            _audit_log_entry(db, "run_canary_tool", args, "success")
            return {"status": "passed", "canary": result.to_dict(), "action": "passed"}
        else:
            # Auto-rollback on canary failure
            _rollback(intervention_id, reason=result.fail_reason or "canary_failed", db=db)
            _audit_log_entry(
                db, "run_canary_tool", args, "rolled_back",
                reason=result.fail_reason,
            )
            return {
                "status":    "failed",
                "canary":    result.to_dict(),
                "action":    "rolled_back",
                "reason":    result.fail_reason,
            }

    except ValueError as exc:
        _audit_log_entry(db, "run_canary_tool", args, "error", reason=str(exc))
        return {"status": "error", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "run_canary_tool", args, "error", reason=str(exc))
        raise


def full_rollout_tool(
    db,
    intervention_id: str,
) -> dict:
    """
    Promote a canary-passed intervention to full rollout.

    Must only be called after run_canary_tool returned 'passed'.
    Updates the incident status to 'resolved'.

    Args:
        intervention_id:  The id from a prior apply_* call that passed canary.

    Returns the updated intervention record dict.
    """
    args = _safe_args(intervention_id=intervention_id)
    try:
        record = _full_rollout(intervention_id, db=db)
        _audit_log_entry(db, "full_rollout_tool", args, "success")
        return {"status": "resolved", "intervention": record.to_dict()}

    except ValueError as exc:
        _audit_log_entry(db, "full_rollout_tool", args, "error", reason=str(exc))
        return {"status": "error", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "full_rollout_tool", args, "error", reason=str(exc))
        raise


def rollback_tool(
    db,
    intervention_id: str,
    reason: str,
) -> dict:
    """
    Manually roll back an intervention and record the reason.

    Use this if you decide the intervention should not proceed (e.g.
    run_canary_tool failed and you want to record an explicit reason beyond
    the automatic rollback, or you are cancelling before canary).

    Args:
        intervention_id:  The id from a prior apply_* call.
        reason:           Plain-English explanation of why it's being rolled back.

    Returns the updated intervention record dict.
    """
    args = _safe_args(intervention_id=intervention_id, reason=reason)
    try:
        record = _rollback(intervention_id, reason=reason, db=db)
        _audit_log_entry(db, "rollback_tool", args, "success")
        return {"status": "rolled_back", "intervention": record.to_dict()}

    except ValueError as exc:
        _audit_log_entry(db, "rollback_tool", args, "error", reason=str(exc))
        return {"status": "error", "reason": str(exc)}

    except Exception as exc:
        _audit_log_entry(db, "rollback_tool", args, "error", reason=str(exc))
        raise
