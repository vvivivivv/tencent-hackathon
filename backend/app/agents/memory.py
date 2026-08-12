"""
memory.py — Episodic memory interface.

Status: wired and present; full incremental learning is a post-hackathon phase.

Current build:
  - Stores past incident records in-process (dict keyed by incident_id).
  - Optionally persists to Supabase's `incidents` table via `load_from_db()`.
  - Exposes `retrieve_similar()` so the Investigator can look up prior incidents
    before forming hypotheses — seed data makes the interface testable now.

Activation path for future-phase learning:
  1. Replace _episodes dict with a vector store (pgvector on Supabase).
  2. Embed the `root_cause` + `reasoning` fields on write.
  3. `retrieve_similar()` becomes a semantic nearest-neighbour query.
  4. Investigator system prompt gains a "PAST INCIDENTS" block built from
     the top-k retrieved episodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Episode:
    """
    One past incident record.

    Fields mirror the incidents table so load_from_db() can populate directly.
    """
    incident_id:       str
    scenario:          str
    affected_segment:  str
    root_cause:        str
    confidence:        float
    intervention_type: str
    outcome:           str
    canary_passed:     Optional[bool]
    improvement_pp:    Optional[float]
    recorded_at:       str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        """Plain-English one-liner for the Investigator's context block."""
        canary = "canary passed" if self.canary_passed else "canary failed"
        return (
            f"[{self.scenario}] {self.root_cause} → "
            f"{self.intervention_type} ({canary}, outcome={self.outcome})"
        )


_episodes: dict[str, Episode] = {}


def record(episode: Episode) -> None:
    """Store an episode in memory (and optionally persist to DB)."""
    _episodes[episode.incident_id] = episode


def retrieve_similar(
    scenario: str | None = None,
    affected_segment: str | None = None,
    limit: int = 3,
) -> list[Episode]:
    """
    Retrieve past episodes that match the given scenario / segment.

    Current implementation: exact-match filter, sorted by recency.
    Future phase: replace with vector similarity search.

    Args:
        scenario:         Match on scenario name (None = any).
        affected_segment: Match on segment (None = any).
        limit:            Maximum number of episodes to return.

    Returns:
        List of Episode objects, most recent first.
    """
    results = list(_episodes.values())

    if scenario:
        results = [e for e in results if e.scenario == scenario]
    if affected_segment:
        results = [e for e in results if e.affected_segment == affected_segment]

    results.sort(key=lambda e: e.recorded_at, reverse=True)
    return results[:limit]


def get_all() -> list[Episode]:
    """Return all stored episodes (for tests and debug)."""
    return list(_episodes.values())


def clear() -> None:
    """Reset the in-memory store (use between tests only)."""
    _episodes.clear()


def load_from_db(db) -> None:
    """
    Populate the memory store from Supabase `incidents` table.

    Loads the 50 most recently resolved incidents so the Investigator
    has historical context on the first run without needing live interaction.
    """
    if db is None:
        return

    try:
        rows = (
            db.table("incidents")
            .select("*")
            .eq("status", "resolved")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        ).data or []
    except Exception:
        return

    for row in rows:
        canary = row.get("canary_result") or {}
        episode = Episode(
            incident_id=row.get("id", ""),
            scenario=row.get("scenario", "unknown"),
            affected_segment=row.get("affected_segment", "unknown"),
            root_cause=row.get("root_cause", "unknown"),
            confidence=float(row.get("confidence", 0.0)),
            intervention_type=(row.get("actions") or [{}])[0].get("intervention_type", "unknown"),
            outcome=row.get("status", "resolved"),
            canary_passed=canary.get("passed"),
            improvement_pp=canary.get("improvement_pp"),
            recorded_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
        _episodes[episode.incident_id] = episode


def save_to_db(episode: Episode, db) -> None:
    """
    Persist a single episode to Supabase as an event row (type='episode_recorded').

    This is supplementary to the incidents row — it writes a structured
    episode snapshot so past incidents survive a process restart.
    """
    if db is None:
        return

    try:
        db.table("events").insert({
            "type":     "episode_recorded",
            "metadata": episode.to_dict(),
        }).execute()
    except Exception:
        pass


def seed_demo_episodes() -> None:
    """
    Seed the memory store with a handful of illustrative past incidents.

    Called once at startup (from main.py) so the Investigator has context
    from the first run.  Does not touch the DB.
    """
    _now = datetime.now(timezone.utc).isoformat()
    demo_episodes = [
        Episode(
            incident_id="demo-001",
            scenario="mobile_checkout_fee",
            affected_segment="mobile_first_time",
            root_cause="Unexpected processing fee disclosed only at final payment step",
            confidence=0.91,
            intervention_type="remove_checkout_fee",
            outcome="resolved",
            canary_passed=True,
            improvement_pp=0.18,
            recorded_at=_now,
        ),
        Episode(
            incident_id="demo-002",
            scenario="pricing_confusion",
            affected_segment="desktop_returning",
            root_cause="Ambiguous plan pricing copy after homepage redesign",
            confidence=0.78,
            intervention_type="update_checkout_copy",
            outcome="resolved",
            canary_passed=True,
            improvement_pp=0.12,
            recorded_at=_now,
        ),
        Episode(
            incident_id="demo-003",
            scenario="weather_red_herring",
            affected_segment="mobile_first_time",
            root_cause="Checkout configuration change (not weather) caused abandonment spike",
            confidence=0.87,
            intervention_type="update_checkout_copy",
            outcome="resolved",
            canary_passed=True,
            improvement_pp=0.15,
            recorded_at=_now,
        ),
    ]
    for ep in demo_episodes:
        _episodes[ep.incident_id] = ep
