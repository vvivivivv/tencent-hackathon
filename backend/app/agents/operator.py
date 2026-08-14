"""
Operator agent.

Responsibilities:
  - Receive an InvestigatorReport and decide which intervention to apply
  - Use write tools (update_checkout, update_faq, etc.) to act on the business
  - Enforce business constraints: budget, CSAT floor, margin floor
  - Always test on a canary cohort before full rollout
  - Return a structured OperatorReport: actions taken, canary result, outcome

Architecture:
  - Same google-genai automatic function calling pattern as Investigator
  - Tool list EXTENDS analytics tools with write tools from tools/write_tools.py
  - System prompt embeds all constraint rules so they are visible in the
    model's reasoning chain (the audit log records what the model decided)
  - db is injected at call time; all writes go through write_tools.py which
    calls _audit_log_entry() before every DB mutation
  - The model CANNOT skip canary — run_canary_tool is the gating step before
    full_rollout_tool is allowed to be called

Safety invariants (enforced in the system prompt AND in the tools themselves):
  1. Confidence < 0.70  → escalate, do not write
  2. CSAT estimate < 0.80 → reject intervention
  3. Margin estimate < 0.20 for negative-margin interventions → reject
  4. Always call run_canary_tool before full_rollout_tool
  5. Every write call is logged to the events table (audit_log entries)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types

from app.agents.investigator import InvestigatorReport
from app.agents.prompts import OPERATOR_SYSTEM_PROMPT
from app.tools.analytics import (
    run_detection_tool,
    get_segment_stats_tool,
    compare_segments_tool,
    get_journey_detail,
    get_recent_changes,
)
from app.tools.write_tools import (
    update_checkout,
    update_faq,
    send_customer_message,
    apply_discount,
    run_canary_tool,
    full_rollout_tool,
    rollback_tool,
)


_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


MODEL = "gemini-flash-latest"


@dataclass
class OperatorReport:
    """Structured output from one operator run."""
    outcome:           str            # resolved | rolled_back | escalated | no_action
    intervention_id:   Optional[str]
    intervention_type: Optional[str]
    canary_passed:     Optional[bool]
    actions_taken:     list[str]
    reasoning:         str
    escalation_reason: Optional[str]
    raw_response:      str

    def to_dict(self) -> dict:
        return {
            "outcome":           self.outcome,
            "intervention_id":   self.intervention_id,
            "intervention_type": self.intervention_type,
            "canary_passed":     self.canary_passed,
            "actions_taken":     self.actions_taken,
            "reasoning":         self.reasoning,
            "escalation_reason": self.escalation_reason,
        }


def _make_tools(db) -> list:
    """
    Return the full Operator tool list — analytics (read) + write tools.
    Each callable is bound to the injected db so the model only passes
    the domain args.
    """

    def run_detection(scenario: str = None, hours: int = 24) -> dict:
        """Run the deterministic detection pipeline."""
        return run_detection_tool(db, scenario=scenario, hours=hours)

    def get_segment_stats(scenario: str = None, hours: int = 24) -> dict:
        """Return per-segment abandonment and conversion rates."""
        return get_segment_stats_tool(db, scenario=scenario, hours=hours)

    def compare_segments(segment_a: str, segment_b: str,
                         scenario: str = None, hours: int = 24) -> dict:
        """Side-by-side segment comparison."""
        return compare_segments_tool(db, segment_a, segment_b,
                                     scenario=scenario, hours=hours)

    def get_journey_details(segment: str = None, result_filter: str = None,
                            scenario: str = None, limit: int = 20,
                            hours: int = 24) -> dict:
        """Retrieve individual journey records for canary pre/post sets."""
        return get_journey_detail(db, segment=segment, result_filter=result_filter,
                                  scenario=scenario, limit=limit, hours=hours)

    def get_recent_business_changes(hours: int = 72) -> dict:
        """Return recent product/pricing changes and past incidents."""
        return get_recent_changes(db, hours=hours)

    def apply_checkout_fix(
        scenario: str,
        affected_segment: str,
        root_cause_confidence: float,
        action: str,
        estimated_csat_post: float = None,
        estimated_margin_post: float = None,
    ) -> dict:
        """Apply a checkout fix (remove_fee or update_copy). Requires confidence >= 0.70."""
        return update_checkout(
            db, scenario=scenario, affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence, action=action,
            estimated_csat_post=estimated_csat_post,
            estimated_margin_post=estimated_margin_post,
        )

    def apply_faq_update(
        scenario: str,
        affected_segment: str,
        root_cause_confidence: float,
        content_summary: str,
        estimated_csat_post: float = None,
    ) -> dict:
        """Update FAQ page to surface fee/pricing info earlier."""
        return update_faq(
            db, scenario=scenario, affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            content_summary=content_summary,
            estimated_csat_post=estimated_csat_post,
        )

    def send_message_to_customers(
        scenario: str,
        affected_segment: str,
        root_cause_confidence: float,
        message_body: str,
        channel: str = "email",
        estimated_csat_post: float = None,
    ) -> dict:
        """Send a targeted message to affected customers. Irreversible."""
        return send_customer_message(
            db, scenario=scenario, affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            message_body=message_body, channel=channel,
            estimated_csat_post=estimated_csat_post,
        )

    def apply_customer_discount(
        scenario: str,
        affected_segment: str,
        root_cause_confidence: float,
        discount_pct: float,
        estimated_margin_post: float,
        estimated_csat_post: float = None,
    ) -> dict:
        """Apply a discount. NEGATIVE MARGIN — estimated_margin_post required, must be >= 0.20."""
        return apply_discount(
            db, scenario=scenario, affected_segment=affected_segment,
            root_cause_confidence=root_cause_confidence,
            discount_pct=discount_pct,
            estimated_margin_post=estimated_margin_post,
            estimated_csat_post=estimated_csat_post,
        )

    def evaluate_canary(
        intervention_id: str,
        pre_journeys: list,
        post_journeys: list,
        csat_post: float = None,
        margin_post: float = None,
    ) -> dict:
        """
        Evaluate a canary cohort. MUST be called before full_rollout.
        On fail, automatically rolls back the intervention.
        pre_journeys and post_journeys are lists of journey dicts.
        """
        return run_canary_tool(
            db, intervention_id=intervention_id,
            pre_journeys=pre_journeys, post_journeys=post_journeys,
            csat_post=csat_post, margin_post=margin_post,
        )

    def promote_to_full_rollout(intervention_id: str) -> dict:
        """Promote a canary-passed intervention to full rollout. Only call after canary passes."""
        return full_rollout_tool(db, intervention_id=intervention_id)

    def rollback_intervention(intervention_id: str, reason: str) -> dict:
        """Manually roll back an intervention and record the reason."""
        return rollback_tool(db, intervention_id=intervention_id, reason=reason)

    def escalate_to_human(reason: str) -> dict:
        """
        Signal that this case requires human review.
        Use when confidence < 0.70 or no safe intervention is available.
        """
        return {
            "action":  "escalated",
            "reason":  reason,
            "message": (
                "This investigation has been escalated to human review. "
                "No business changes have been made."
            ),
        }

    return [
        run_detection,
        get_segment_stats,
        compare_segments,
        get_journey_details,
        get_recent_business_changes,
        apply_checkout_fix,
        apply_faq_update,
        send_message_to_customers,
        apply_customer_discount,
        evaluate_canary,
        promote_to_full_rollout,
        rollback_intervention,
        escalate_to_human,
    ]


def _parse_report(text: str) -> OperatorReport:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return OperatorReport(
                outcome=data.get("outcome", "no_action"),
                intervention_id=data.get("intervention_id"),
                intervention_type=data.get("intervention_type"),
                canary_passed=data.get("canary_passed"),
                actions_taken=data.get("actions_taken", []),
                reasoning=data.get("reasoning", ""),
                escalation_reason=data.get("escalation_reason"),
                raw_response=text,
            )
        except (json.JSONDecodeError, ValueError):
            pass

    return OperatorReport(
        outcome="no_action",
        intervention_id=None,
        intervention_type=None,
        canary_passed=None,
        actions_taken=[],
        reasoning=text,
        escalation_reason="Could not parse structured report",
        raw_response=text,
    )


def operate(
    investigator_report: InvestigatorReport,
    db=None,
    pre_journeys: Optional[list[dict]] = None,
    post_journeys: Optional[list[dict]] = None,
) -> OperatorReport:
    """
    Run the Operator agent on an InvestigatorReport.

    Args:
        investigator_report:  Output from investigator.investigate_from_detection().
        db:                   Supabase client (or None in tests).
        pre_journeys:         Optional list of pre-intervention journeys to pass
                              directly — if None, the agent fetches them via tools.
        post_journeys:        Optional list of post-intervention journeys.

    Returns:
        OperatorReport with outcome, intervention taken, canary result, and reasoning.
    """
    if investigator_report.confidence < 0.1: # Catch the 429 fallback report
        return OperatorReport(outcome="no_action", reasoning="Investigation failed due to API quota.", actions_taken=[], raw_response="", intervention_id=None, intervention_type=None, canary_passed=None, escalation_reason="Quota Limit")
        
    client = _get_client()
    tools = _make_tools(db)

    # Build a rich context string from the Investigator's report
    report_dict = investigator_report.to_dict()
    context_lines = [
        "=== INVESTIGATOR REPORT ===",
        f"Root cause:     {report_dict['root_cause']}",
        f"Confidence:     {report_dict['confidence']:.0%}",
        f"Affected segment: {report_dict['affected_segment']}",
        f"Recommended intervention: {report_dict['recommended_intervention']}",
        f"Needs human review: {report_dict['needs_human_review']}",
        "",
        "Reasoning:",
        report_dict["reasoning"],
        "",
        "=== YOUR TASK ===",
        "Follow the workflow in your system prompt. "
        "Apply the recommended intervention (or a safer alternative), "
        "run canary, and promote or roll back.",
    ]

    if pre_journeys is not None:
        context_lines += [
            "",
            f"Pre-intervention journeys provided: {len(pre_journeys)} records.",
            f"Post-intervention journeys provided: {len(post_journeys or [])} records.",
            "Use these directly for the canary evaluation step.",
        ]

    contents = "\n".join(context_lines)

    # Inject pre/post journeys into tool closures if provided directly
    # (avoids a round-trip DB fetch when the caller already has them)
    if pre_journeys is not None and post_journeys is not None:
        _pre  = pre_journeys
        _post = post_journeys

        def evaluate_canary_with_data(
            intervention_id: str,
            csat_post: float = None,
            margin_post: float = None,
        ) -> dict:
            """
            Evaluate canary using the pre/post journey sets provided by the caller.
            MUST be called before full_rollout.
            """
            return run_canary_tool(
                db, intervention_id=intervention_id,
                pre_journeys=_pre, post_journeys=_post,
                csat_post=csat_post, margin_post=margin_post,
            )

        # Replace the generic evaluate_canary in the tool list
        tools = [t for t in tools if t.__name__ != "evaluate_canary"]
        tools.append(evaluate_canary_with_data)

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=OPERATOR_SYSTEM_PROMPT,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=False,
            ),
            temperature=0.1,   # very low — operator decisions must be deterministic
        ),
    )

    return _parse_report(response.text)


def run_full_pipeline(
    db,
    scenario: Optional[str] = None,
    hours: int = 24,
    pre_journeys: Optional[list[dict]] = None,
    post_journeys: Optional[list[dict]] = None,
) -> dict:
    """
    Convenience function: runs the complete detection → investigation → operation
    pipeline end-to-end.

    Args:
        db:            Supabase client.
        scenario:      Optional scenario filter.
        hours:         Time window for journey fetching.
        pre_journeys:  Optional pre-intervention journeys for canary step.
        post_journeys: Optional post-intervention journeys for canary step.

    Returns a dict with all three stages' outputs.
    """
    from app.business.metrics import run_detection
    from app.tools.analytics import _fetch_journeys
    from app.agents.investigator import investigate_from_detection

    journeys = _fetch_journeys(db, scenario=scenario, hours=hours) if db else []
    detection = run_detection(journeys, scenario=None)

    investigator_report = investigate_from_detection(
        detection, db=db, scenario=scenario
    )

    if investigator_report.needs_human_review:
        return {
            "stage":              "escalated",
            "detection":          detection.to_dict(),
            "investigator_report": investigator_report.to_dict(),
            "operator_report":    None,
        }

    operator_report = operate(
        investigator_report,
        db=db,
        pre_journeys=pre_journeys,
        post_journeys=post_journeys,
    )

    return {
        "stage":               operator_report.outcome,
        "detection":           detection.to_dict(),
        "investigator_report": investigator_report.to_dict(),
        "operator_report":     operator_report.to_dict(),
    }
