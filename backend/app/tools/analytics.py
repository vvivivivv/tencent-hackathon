"""
Read-only analytics tools for the Investigator agent.

Every function here:
  - Takes a Supabase client as first arg (injected by the agent runner)
  - Returns a plain JSON-serialisable dict (the SDK passes it straight back
    to the model as the tool-call result)
  - Has NO side effects — no writes, no audit entries
  - Has a clear docstring that the SDK uses as the tool description

The agent runner wraps these into google.genai `Tool` / `FunctionDeclaration`
objects automatically via `types.Tool(function_declarations=[...])` or by
passing the callables directly when using automatic function calling.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from app.business.metrics import (
    get_segment_stats,
    detect_anomalies,
    compare_segments as _compare_segments_pure,
    run_detection,
    BASELINE_ABANDONMENT,
)


def _fetch_journeys(db, scenario: Optional[str] = None, hours: int = 24) -> list[dict]:
    """
    Fetch journeys from Supabase, optionally filtered by scenario and time window.

    Returns plain dicts with at minimum:
        id, customer_id, scenario, result, duration_seconds, created_at,
        steps (jsonb)  — plus joined device/customer_type from customers table.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    if scenario and scenario.startswith("custom_"):
        q = db.table("journeys").select(
            "id, customer_id, scenario, goal, steps, result, duration_seconds, created_at"
        ).eq("scenario", scenario)
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        q = db.table("journeys").select(
            "id, customer_id, scenario, goal, steps, result, duration_seconds, created_at"
        ).gte("created_at", cutoff)
        if scenario:
            q = q.eq("scenario", scenario)

    # Supabase doesn't support a direct join in the Python client the same way
    # SQL does, so we fetch journeys + customers in two queries and merge.
    q = db.table("journeys").select(
        "id, customer_id, scenario, goal, steps, result, duration_seconds, created_at"
    ).gte("created_at", cutoff)

    if scenario:
        q = q.eq("scenario", scenario)

    journeys_resp = q.execute()
    journeys = journeys_resp.data or []

    if not journeys:
        return []

    # Fetch customer metadata (device, customer_type) for every unique customer_id
    customer_ids = list({j["customer_id"] for j in journeys if j.get("customer_id")})
    customers_resp = (
        db.table("customers")
        .select("id, name, persona, device, customer_type")
        .in_("id", customer_ids)
        .execute()
    )
    customer_map = {c["id"]: c for c in (customers_resp.data or [])}

    merged = []
    for j in journeys:
        c = customer_map.get(j.get("customer_id"), {})
        merged.append({
            **j,
            "device":        c.get("device", "unknown"),
            "customer_type": c.get("customer_type", "unknown"),
            "customer_name": c.get("name"),
            "persona":       c.get("persona"),
        })
    return merged


def get_segment_stats_tool(
    db,
    scenario: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Return abandonment and conversion rates for every device × customer_type
    segment for the last `hours` hours.

    Args:
        scenario: If supplied, restrict to journeys matching this scenario name.
        hours:    Time window to look back (default 24 h).

    Returns a dict keyed by segment name, each containing:
        total, abandoned, completed, abandonment_rate, conversion_rate.
    """
    journeys = _fetch_journeys(db, scenario=scenario, hours=hours)
    stats = get_segment_stats(journeys)
    return {
        "segment_stats": {k: v.to_dict() for k, v in stats.items()},
        "total_journeys": len(journeys),
        "scenario_filter": scenario,
        "hours": hours,
    }


def compare_segments_tool(
    db,
    segment_a: str,
    segment_b: str,
    scenario: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Side-by-side comparison of two segments' abandonment rates.

    Use this to rule out or confirm that an anomaly is segment-specific.
    For example, compare 'mobile_first_time' vs 'desktop_first_time' to
    determine if the problem is mobile-only or affects all devices.

    Valid segment names: mobile_first_time, mobile_returning,
                         desktop_first_time, desktop_returning.

    Args:
        segment_a: First segment key (e.g. 'mobile_first_time').
        segment_b: Second segment key to compare against.
        scenario:  Optional scenario filter.
        hours:     Time window to look back (default 24 h).

    Returns abandonment rates for both segments, the absolute diff, and a
    plain-English interpretation of whether a segment-specific cause is likely.
    """
    journeys = _fetch_journeys(db, scenario=scenario, hours=hours)
    stats = get_segment_stats(journeys)
    result = _compare_segments_pure(stats, segment_a, segment_b)
    result["scenario_filter"] = scenario
    result["hours"] = hours
    return result


def get_journey_detail(
    db,
    segment: Optional[str] = None,
    result_filter: Optional[str] = None,
    scenario: Optional[str] = None,
    limit: int = 10,
    hours: int = 24,
) -> dict:
    """
    Return individual journey records for qualitative inspection.

    Useful for understanding *what happened* in abandoned journeys:
    which step they dropped off at, how long each step took, etc.

    Args:
        segment:       Filter by segment (e.g. 'mobile_first_time').
                       Segment is derived from device + customer_type.
        result_filter: 'abandoned', 'completed', or None for both.
        scenario:      Scenario name filter.
        limit:         Maximum number of journeys to return (default 10).
        hours:         Time window (default 24 h).

    Returns a list of journey dicts including steps (the full event trace),
    duration_seconds, result, and customer persona.
    """
    journeys = _fetch_journeys(db, scenario=scenario, hours=hours)

    if segment:
        parts = segment.split("_", 1)   # e.g. "mobile_first_time" → ["mobile", "first_time"]
        if len(parts) == 2:
            device, customer_type = parts[0], parts[1]
            journeys = [
                j for j in journeys
                if j.get("device") == device and j.get("customer_type") == customer_type
            ]

    if result_filter:
        journeys = [j for j in journeys if j.get("result") == result_filter]

    # Sort by most recent first
    journeys.sort(key=lambda j: j.get("created_at", ""), reverse=True)

    return {
        "journeys": journeys[:limit],
        "total_matching": len(journeys),
        "filters": {
            "segment":       segment,
            "result_filter": result_filter,
            "scenario":      scenario,
            "hours":         hours,
        },
    }


def get_recent_changes(
    db,
    hours: int = 72,
) -> dict:
    """
    Return recent business-state changes that could explain an anomaly.

    Looks at:
      - New or updated products/plans (price changes, status changes)
      - Recent incidents (resolved or in-progress investigations)
      - Recent events tagged as config changes

    Args:
        hours: How far back to look (default 72 h — catches changes made
               earlier in the day that might only surface in metrics now).

    Returns lists of recent products, incidents, and config-change events,
    sorted newest-first.  Use this to correlate anomaly onset with a
    specific business change.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    products_resp = (
        db.table("products")
        .select("id, name, price, status")
        .execute()
    )

    incidents_resp = (
        db.table("incidents")
        .select(
            "id, title, severity, affected_segment, root_cause, "
            "confidence, status, created_at, resolved_at"
        )
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .execute()
    )

    # Config-change events are anything intervention-related
    events_resp = (
        db.table("events")
        .select("id, type, metadata, created_at")
        .in_("type", [
            "intervention_applied",
            "full_rollout_applied",
            "intervention_rolled_back",
        ])
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return {
        "products":         products_resp.data or [],
        "recent_incidents": incidents_resp.data or [],
        "recent_changes":   events_resp.data or [],
        "hours":            hours,
    }


def run_detection_tool(
    db,
    scenario: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Run the full deterministic detection pipeline and return a structured
    anomaly report.

    This is the primary entry-point: call this first to get the overview,
    then use compare_segments or get_journey_detail to drill down.

    Args:
        scenario: Optional scenario filter.
        hours:    Time window (default 24 h).

    Returns:
        has_anomaly     bool   — True if any segment exceeded threshold
        primary_anomaly dict   — highest-confidence flagged segment (or null)
        anomalies       list   — all flagged segments sorted by confidence desc
        segment_stats   dict   — raw counts + rates for every segment
        summary         str    — plain-English one-liner
    """
    journeys = _fetch_journeys(db, scenario=scenario, hours=hours)
    result = run_detection(journeys, scenario=None)   # already filtered above
    return result.to_dict()
