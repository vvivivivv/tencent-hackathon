"""
support.py — Customer support signal tools for the Investigator.

Support tickets are a leading indicator of checkout problems:
customers who abandon often vent their frustration via support channels
before the analytics layer catches the drop-off.

All tools here are read-only.  The Operator's `send_customer_message`
write tool lives in write_tools.py.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


# Simulated in-memory support tickets for scenarios where DB rows are absent.
# In production, these come from the `support_tickets` Supabase table.
_DEMO_TICKETS = [
    {
        "id": "t-001",
        "subject": "Why was I charged a processing fee?",
        "body": "I didn't see any mention of a $3.99 fee until the very last page. "
                "I already entered my card details. This is deceptive.",
        "segment": "mobile_first_time",
        "sentiment": "angry",
        "scenario": "scenario_a",
        "created_at": "2026-08-12T10:15:00Z",
    },
    {
        "id": "t-002",
        "subject": "Confused about Pro vs Business plan",
        "body": "Your pricing page says '3 seats' for Pro but the checkout shows '1 seat'. "
                "Which is correct? I'm not paying until this is clear.",
        "segment": "desktop_first_time",
        "sentiment": "confused",
        "scenario": "scenario_b",
        "created_at": "2026-08-12T11:00:00Z",
    },
    {
        "id": "t-003",
        "subject": "Checkout not working on mobile",
        "body": "I tried to sign up three times on my phone. The checkout page keeps "
                "resetting when I try to confirm. Desktop works fine.",
        "segment": "mobile_first_time",
        "sentiment": "frustrated",
        "scenario": "scenario_c",
        "created_at": "2026-08-12T09:30:00Z",
    },
]


def get_support_tickets(
    db,
    scenario: Optional[str] = None,
    hours: int = 48,
    limit: int = 20,
) -> dict:
    """
    Return recent support tickets that may correlate with a checkout anomaly.

    In production: reads from the `support_tickets` Supabase table.
    In test/demo mode (db=None or table absent): returns seeded demo tickets.

    Args:
        scenario: Optional filter by scenario name.
        hours:    How far back to look (default 48 h — support lags analytics).
        limit:    Maximum tickets to return (default 20).

    Returns a dict with: tickets (list), total, hours, sentiment_summary.
    """
    tickets = []

    if db is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            q = (
                db.table("support_tickets")
                .select("id, subject, body, segment, sentiment, scenario, created_at")
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(limit)
            )
            if scenario:
                q = q.eq("scenario", scenario)
            tickets = q.execute().data or []
        except Exception:
            tickets = []

    if not tickets:
        tickets = _DEMO_TICKETS
        if scenario:
            tickets = [t for t in tickets if t.get("scenario") == scenario]
        tickets = tickets[:limit]

    # Sentiment summary
    sentiments: dict[str, int] = {}
    for t in tickets:
        s = t.get("sentiment", "neutral")
        sentiments[s] = sentiments.get(s, 0) + 1

    return {
        "tickets":          tickets,
        "total":            len(tickets),
        "hours":            hours,
        "scenario_filter":  scenario,
        "sentiment_summary": sentiments,
    }


def get_support_summary(
    db,
    scenario: Optional[str] = None,
    hours: int = 48,
) -> dict:
    """
    Return a high-level summary of support signal strength.

    Useful as a quick check: is support volume elevated above normal?
    What is the dominant sentiment?  What are the top complaint themes?

    Args:
        scenario: Optional scenario filter.
        hours:    Time window (default 48 h).

    Returns a plain-English summary dict with: volume_status, dominant_sentiment,
    top_themes, and is_elevated (bool).
    """
    result = get_support_tickets(db, scenario=scenario, hours=hours)
    tickets = result["tickets"]
    total   = result["total"]

    # Rough elevation threshold: > 3 tickets in 48 h for a small business
    ELEVATION_THRESHOLD = 3
    is_elevated = total >= ELEVATION_THRESHOLD

    dominant_sentiment = "neutral"
    if result["sentiment_summary"]:
        dominant_sentiment = max(
            result["sentiment_summary"],
            key=result["sentiment_summary"].get,
        )

    # Extract top themes from subjects
    themes: dict[str, int] = {}
    theme_keywords = {
        "hidden fee": ["fee", "charge", "charged", "processing"],
        "pricing confusion": ["pricing", "plan", "pro", "business", "seats"],
        "checkout error": ["checkout", "error", "working", "reset", "broken"],
        "mobile issue": ["mobile", "phone", "iphone", "android"],
    }
    for ticket in tickets:
        text = (ticket.get("subject", "") + " " + ticket.get("body", "")).lower()
        for theme, keywords in theme_keywords.items():
            if any(kw in text for kw in keywords):
                themes[theme] = themes.get(theme, 0) + 1

    top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "total_tickets":      total,
        "is_elevated":        is_elevated,
        "dominant_sentiment": dominant_sentiment,
        "top_themes":         [{"theme": t, "count": c} for t, c in top_themes],
        "volume_status":      "elevated" if is_elevated else "normal",
        "hours":              hours,
        "scenario_filter":    scenario,
    }
