"""
business.py — Business-state read tools for the Investigator.

These tools give the Investigator access to higher-level business metrics —
conversion funnels, revenue trends, product/pricing state — without exposing
write access.

Every function:
  - Takes a Supabase client as first arg (injected by the agent runner)
  - Returns a JSON-serialisable dict
  - Has NO side effects
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


def get_business_metrics(
    db,
    scenario: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Return top-level business performance metrics for the last `hours` hours.

    Includes: total_journeys, total_completed, total_abandoned,
    overall_conversion_rate, overall_abandonment_rate, revenue_estimate.

    Args:
        scenario: Optional scenario filter.
        hours:    Time window in hours (default 24).

    Returns a dict with summary metrics.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    q = db.table("journeys").select(
        "id, result, duration_seconds, scenario, created_at"
    ).gte("created_at", cutoff)

    if scenario:
        q = q.eq("scenario", scenario)

    journeys = q.execute().data or []
    total     = len(journeys)
    completed = sum(1 for j in journeys if j.get("result") == "completed")
    abandoned = total - completed
    conversion = completed / total if total else 0.0

    avg_duration = (
        sum(j.get("duration_seconds", 0) for j in journeys) / total
        if total else 0
    )

    return {
        "total_journeys":          total,
        "total_completed":         completed,
        "total_abandoned":         abandoned,
        "overall_conversion_rate": round(conversion, 4),
        "overall_abandonment_rate":round(1 - conversion, 4),
        "avg_journey_duration_s":  round(avg_duration, 1),
        "revenue_estimate":        round(completed * 100, 2),
        "hours":                   hours,
        "scenario_filter":         scenario,
    }


def get_conversion_funnel(
    db,
    scenario: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Return conversion rates at each step of the checkout funnel.

    Step order: website_visit → pricing_view → checkout_start →
                payment_entry → checkout_complete.

    Useful for pinpointing exactly which step customers are dropping off at.

    Args:
        scenario: Optional scenario filter.
        hours:    Time window (default 24 h).

    Returns a dict with per-step counts and drop-off rates.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    events_q = db.table("events").select(
        "id, type, metadata, created_at"
    ).gte("created_at", cutoff)

    if scenario:
        events_q = events_q.eq("metadata->>scenario", scenario)

    events = events_q.execute().data or []

    # Count events by type
    funnel_steps = [
        "WebsiteVisit",
        "PricingView",
        "CheckoutStarted",
        "PaymentEntry",
        "CheckoutCompleted",
        "CheckoutAbandoned",
    ]
    counts: dict[str, int] = {step: 0 for step in funnel_steps}
    for ev in events:
        ev_type = ev.get("type", "")
        if ev_type in counts:
            counts[ev_type] += 1

    total_started = counts["CheckoutStarted"] or 1
    funnel = {
        "website_visit":      counts["WebsiteVisit"],
        "pricing_view":       counts["PricingView"],
        "checkout_started":   counts["CheckoutStarted"],
        "payment_entry":      counts["PaymentEntry"],
        "checkout_completed": counts["CheckoutCompleted"],
        "checkout_abandoned": counts["CheckoutAbandoned"],
        "checkout_to_complete_rate": round(
            counts["CheckoutCompleted"] / total_started, 4
        ),
        "checkout_to_abandon_rate": round(
            counts["CheckoutAbandoned"] / total_started, 4
        ),
        "hours":    hours,
        "scenario": scenario,
    }
    return funnel


def get_customer_segments(
    db,
    scenario: Optional[str] = None,
    hours: int = 24,
) -> dict:
    """
    Return a summary of customer segments active in the time window.

    Groups by device × customer_type to show which populations are
    engaging (and underperforming) most.

    Args:
        scenario: Optional scenario filter.
        hours:    Time window (default 24 h).

    Returns a dict with segment counts and conversion rates.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    journeys_q = db.table("journeys").select(
        "id, result, customer_id, created_at"
    ).gte("created_at", cutoff)

    if scenario:
        journeys_q = journeys_q.eq("scenario", scenario)

    journeys = journeys_q.execute().data or []

    if not journeys:
        return {"segments": {}, "hours": hours}

    customer_ids = list({j["customer_id"] for j in journeys if j.get("customer_id")})
    customers    = (
        db.table("customers")
        .select("id, device, customer_type")
        .in_("id", customer_ids)
        .execute()
        .data or []
    )
    customer_map = {c["id"]: c for c in customers}

    segments: dict[str, dict] = {}
    for j in journeys:
        c = customer_map.get(j.get("customer_id"), {})
        device = c.get("device", "unknown")
        ctype  = c.get("customer_type", "unknown")
        key    = f"{device}_{ctype}"
        if key not in segments:
            segments[key] = {"total": 0, "completed": 0, "abandoned": 0}
        segments[key]["total"] += 1
        if j.get("result") == "completed":
            segments[key]["completed"] += 1
        else:
            segments[key]["abandoned"] += 1

    for seg in segments.values():
        total = seg["total"] or 1
        seg["conversion_rate"]  = round(seg["completed"] / total, 4)
        seg["abandonment_rate"] = round(seg["abandoned"]  / total, 4)

    return {"segments": segments, "hours": hours, "scenario": scenario}


def get_products(db) -> dict:
    """
    Return all products/plans with current price and status.

    Useful for correlating a pricing change with an abandonment spike.

    Returns a list of product dicts: id, name, price, status.
    """
    data = db.table("products").select("id, name, price, status").execute().data or []
    return {"products": data, "count": len(data)}
