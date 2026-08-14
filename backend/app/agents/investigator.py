"""
Investigator agent.

Responsibilities:
  - Receive a DetectionResult anomaly summary from the deterministic layer
  - Use read-only analytics tools to gather evidence (no writes ever)
  - Compare affected vs. unaffected segments before concluding
  - Return a structured InvestigatorReport: root_cause, confidence (0-1),
    recommended intervention type, and reasoning chain

Architecture:
  - google-genai SDK with automatic function calling
  - The SDK handles the tool-call back-and-forth until the model stops
    calling tools and emits its final text
  - All tools are read-only; no DB writes happen here
  - db is injected at call time so tests can pass a mock or None
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types

from app.business.metrics import DetectionResult
from app.tools.analytics import (
    run_detection_tool,
    get_segment_stats_tool,
    compare_segments_tool,
    get_journey_detail,
    get_recent_changes,
)
from app.agents.prompts import INVESTIGATOR_SYSTEM_PROMPT


_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


MODEL = "gemini-3.5-flash"


@dataclass
class InvestigatorReport:
    """Structured output from one investigation run."""
    root_cause:               str
    confidence:               float          # 0-1
    affected_segment:         str
    recommended_intervention: str
    reasoning:                str
    needs_human_review:       bool
    raw_response:             str            # full model text for the console

    def to_dict(self) -> dict:
        return {
            "root_cause":               self.root_cause,
            "confidence":               self.confidence,
            "affected_segment":         self.affected_segment,
            "recommended_intervention": self.recommended_intervention,
            "reasoning":                self.reasoning,
            "needs_human_review":       self.needs_human_review,
        }


def _make_tools(db) -> list:
    """
    Return a list of callables bound to the injected db client.
    The google-genai SDK inspects the function signature + docstring to build
    the FunctionDeclaration automatically when you pass Python callables.
    """

    def run_detection(scenario: str = None, hours: int = 24) -> dict:
        """Run the full deterministic detection pipeline. Call this first."""
        return run_detection_tool(db, scenario=scenario, hours=hours)

    def get_segment_stats(scenario: str = None, hours: int = 24) -> dict:
        """Return abandonment and conversion rates per segment."""
        return get_segment_stats_tool(db, scenario=scenario, hours=hours)

    def compare_segments(
        segment_a: str,
        segment_b: str,
        scenario: str = None,
        hours: int = 24,
    ) -> dict:
        """Side-by-side comparison of two segment abandonment rates."""
        return compare_segments_tool(db, segment_a, segment_b,
                                     scenario=scenario, hours=hours)

    def get_journey_details(
        segment: str = None,
        result_filter: str = None,
        scenario: str = None,
        limit: int = 10,
        hours: int = 24,
    ) -> dict:
        """Return individual journey records for qualitative inspection."""
        return get_journey_detail(db, segment=segment, result_filter=result_filter,
                                  scenario=scenario, limit=limit, hours=hours)

    def get_recent_business_changes(hours: int = 72) -> dict:
        """Return recent product/pricing changes and past incidents."""
        return get_recent_changes(db, hours=hours)

    return [
        run_detection,
        get_segment_stats,
        compare_segments,
        get_journey_details,
        get_recent_business_changes,
    ]


def _parse_report(text: str) -> InvestigatorReport:
    """
    Extract the structured JSON block from the model's final response.
    Falls back to safe defaults if the block is missing or malformed.
    """
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return InvestigatorReport(
                root_cause=data.get("root_cause", "Unknown"),
                confidence=float(data.get("confidence", 0.0)),
                affected_segment=data.get("affected_segment", "unknown"),
                recommended_intervention=data.get("recommended_intervention", "update_faq"),
                reasoning=data.get("reasoning", ""),
                needs_human_review=bool(data.get("needs_human_review", False)),
                raw_response=text,
            )
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback — couldn't parse structured block
    return InvestigatorReport(
        root_cause="Could not parse structured report",
        confidence=0.0,
        affected_segment="unknown",
        recommended_intervention="update_faq",
        reasoning=text,
        needs_human_review=True,
        raw_response=text,
    )


def investigate(
    anomaly_summary: str,
    db=None,
    scenario: Optional[str] = None,
) -> InvestigatorReport:
    """
    Run a full investigation on the given anomaly summary.

    Args:
        anomaly_summary:  Plain-English description of the anomaly (from
                          DetectionResult.summary or a formatted AnomalyRecord).
        db:               Supabase client (or None in tests — tools return
                          empty results gracefully when db is None).
        scenario:         Optional scenario name to scope the investigation.

    Returns:
        InvestigatorReport with root_cause, confidence, recommended_intervention,
        and the full reasoning chain.
    """
    client = _get_client()
    tools = _make_tools(db)

    context = anomaly_summary
    if scenario:
        context = f"[Scenario: {scenario}]\n\n{anomaly_summary}"

    response = client.models.generate_content(
        model=MODEL,
        contents=context,
        config=types.GenerateContentConfig(
            system_instruction=INVESTIGATOR_SYSTEM_PROMPT,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=False,
            ),
            temperature=0.2,   # low temp — we want consistent, factual reasoning
        ),
    )

    return _parse_report(response.text)


def investigate_from_detection(
    detection: DetectionResult,
    db=None,
    scenario: Optional[str] = None,
) -> InvestigatorReport:
    """
    Convenience wrapper: build the anomaly_summary from a DetectionResult
    and call investigate().

    Args:
        detection:  DetectionResult from run_detection() / run_detection_tool().
        db:         Supabase client.
        scenario:   Optional scenario filter.
    """
    if not detection.has_anomaly:
        return InvestigatorReport(
            root_cause="No anomaly detected",
            confidence=1.0,
            affected_segment="none",
            recommended_intervention="none",
            reasoning="Deterministic detection found no anomalies. No investigation needed.",
            needs_human_review=False,
            raw_response="No anomaly.",
        )

    # Build a rich context string so the model has the numbers up front
    primary = detection.primary_anomaly
    lines = [
        detection.summary,
        "",
        f"Primary flagged segment: {primary.segment}",
        f"  current abandonment rate : {primary.current_rate:.1%}",
        f"  baseline abandonment rate: {primary.baseline_rate:.1%}",
        f"  diff                     : +{primary.diff:.1%}",
        f"  sample size              : {primary.sample_size}",
        f"  confidence               : {primary.confidence:.0%}",
        f"  severity                 : {primary.severity}",
        "",
        "All flagged segments:",
    ]
    for a in detection.anomalies:
        lines.append(
            f"  {a.segment}: {a.current_rate:.1%} vs {a.baseline_rate:.1%} baseline "
            f"(+{a.diff:.1%}, confidence={a.confidence:.0%}, severity={a.severity})"
        )

    return investigate(
        anomaly_summary="\n".join(lines),
        db=db,
        scenario=scenario,
    )
