"""
customer_agent.py — LLM-generated customer behaviour.

Each simulated customer is a distinct persona (device, customer_type, goal,
personality).  Their journey *through* the business state is AI-generated —
the hesitation phrasing, the page they linger on, the moment they decide to
abandon — but the underlying events (CheckoutStarted, CheckoutAbandoned, etc.)
remain deterministic for measurement purposes.

This means:
  - No two simulation runs are identical at the surface level (authentic variation)
  - The analytics/detection layer still has clean, structured data to work with

Architecture:
  - One Gemini call per persona
  - The model sees: persona description + current business state + scenario context
  - It narrates the journey and emits a final JSON outcome line
  - The runner extracts the JSON, writes the journey to the DB, and continues

Usage:
    from app.agents.customer_agent import run_customer_simulation
    journeys = await run_customer_simulation(personas, business_state, db, scenario)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.genai import types

from app.agents.prompts import CUSTOMER_SYSTEM_PROMPT, build_customer_prompt
from app.simulation.personas import PERSONAS
from app.simulation.world_events import emit_customer_journey


_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


MODEL = "gemini-flash-latest"


def _extract_outcome(text: str) -> dict:
    """
    Parse the final JSON line from the customer's narration.

    Expected format (last line of model output):
        {"event": "CheckoutAbandoned", "reason": "...", "step_abandoned_at": "..."}

    Falls back to a safe default if parsing fails.
    """
    # Try the last non-empty line first
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if "event" in data:
                    return data
            except json.JSONDecodeError:
                continue

    # Try a regex scan as fallback
    match = re.search(
        r'\{"event":\s*"(CheckoutAbandoned|CheckoutCompleted)".*?\}',
        text,
        re.DOTALL,
    )
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Default — could not parse; treat as completed (conservative)
    return {"event": "CheckoutCompleted", "reason": "parse_failed", "step_abandoned_at": None}


def simulate_one_customer(
    persona: dict,
    business_state: dict,
    scenario: Optional[str] = None,
) -> dict:
    """
    Run one LLM-driven customer journey for a single persona.

    Args:
        persona:        Dict with keys: name, device, customer_type, goal.
                        Optionally: personality.
        business_state: Dict describing current checkout config, pricing, fees.
        scenario:       Scenario name for context injection.

    Returns a journey dict:
        {
            customer_id:        str (persona name, used as stable ID in tests),
            persona:            dict,
            narration:          str (full model text),
            event:              "CheckoutAbandoned" | "CheckoutCompleted",
            reason:             str,
            step_abandoned_at:  str | None,
            result:             "abandoned" | "completed",
            duration_seconds:   int,
            scenario:           str | None,
            steps:              list[str],
        }
    """
    client = _get_client()
    prompt = build_customer_prompt(persona, business_state, scenario=scenario)

    import time
    t0 = time.time()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CUSTOMER_SYSTEM_PROMPT,
            temperature=0.8,  # higher temp for authentic human variation
            max_output_tokens=600,
        ),
    )
    duration = int(time.time() - t0)

    narration = response.text or ""
    outcome   = _extract_outcome(narration)

    event  = outcome.get("event", "CheckoutCompleted")
    result = "abandoned" if event == "CheckoutAbandoned" else "completed"

    # Extract steps from the narration (simple heuristic: numbered or bulleted lines)
    steps = _extract_steps(narration)

    return {
        "customer_id":       persona.get("name", "unknown"),
        "persona":           persona,
        "narration":         narration,
        "event":             event,
        "reason":            outcome.get("reason", ""),
        "step_abandoned_at": outcome.get("step_abandoned_at"),
        "result":            result,
        "duration_seconds":  duration,
        "scenario":          scenario,
        "steps":             steps,
        "goal":              persona.get("goal", ""),
        "device":            persona.get("device", "desktop"),
        "customer_type":     persona.get("customer_type", "returning"),
    }


def _extract_steps(narration: str) -> list[str]:
    """
    Heuristically extract journey steps from the model's narration.

    Looks for numbered steps (1. ...) or zone keywords (Website, Pricing,
    Checkout, Payment).  Returns a list of strings for the frontend replay.
    """
    steps = []
    zones = ["website", "pricing", "checkout", "payment", "confirmation"]

    for line in narration.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Numbered step
        if re.match(r"^\d+[\.\)]\s+", line):
            steps.append(re.sub(r"^\d+[\.\)]\s+", "", line)[:120])
        # Zone mention
        elif any(z in line.lower() for z in zones):
            steps.append(line[:120])

    return steps[:10]  # Cap at 10 steps for frontend


def run_customer_simulation(
    personas: Optional[list[dict]] = None,
    business_state: Optional[dict] = None,
    db=None,
    scenario: Optional[str] = None,
    write_to_db: bool = True,
    run_id: str | None = None,
):
    """
    Simulate a full cohort of customers and optionally write journeys to DB.

    Args:
        personas:       List of persona dicts.  Defaults to PERSONAS from personas.py.
        business_state: Current business config dict.  Defaults to a safe baseline.
        db:             Supabase client.  Pass None for offline/test mode.
        scenario:       Scenario name filter.
        write_to_db:    If True and db is not None, write each journey to DB.

    Returns a list of journey dicts (one per persona).
    """
    if personas is None:
        personas = PERSONAS
    if business_state is None:
        business_state = _default_business_state()

    journeys = []
    for persona in personas:
        try:
            journey = simulate_one_customer(persona, business_state, scenario=scenario)
        except Exception as exc:
            # Never crash the whole simulation on one persona failure
            journey = _fallback_journey(persona, scenario, reason=str(exc))

        journeys.append(journey)

        if write_to_db and db is not None:
            _write_journey_to_db(journey, db)
        
        if run_id and db is not None:
            emit_customer_journey(db, run_id, journey)

    return journeys


def _write_journey_to_db(journey: dict, db) -> None:
    """
    Insert one journey record into the `journeys` table.

    Also fires a CheckoutAbandoned or CheckoutCompleted event row.
    """
    try:
        # Upsert the customer row (idempotent — persona name is stable)
        customer_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, journey["customer_id"]))
        db.table("customers").upsert({
            "id":            customer_id,
            "name":          journey["customer_id"],
            "device":        journey["device"],
            "customer_type": journey["customer_type"],
            "persona":       json.dumps(journey["persona"]),
        }).execute()

        # Insert the journey
        journey_id = str(uuid.uuid4())
        db.table("journeys").insert({
            "id":               journey_id,
            "customer_id":      customer_id,
            "scenario":         journey.get("scenario"),
            "goal":             journey.get("goal", ""),
            "result":           journey["result"],
            "duration_seconds": journey.get("duration_seconds", 0),
            "steps":            json.dumps(journey.get("steps", [])),
        }).execute()

        # Fire the outcome event
        db.table("events").insert({
            "type": journey["event"],
            "metadata": {
                "journey_id":      journey_id,
                "customer_id":     customer_id,
                "reason":          journey.get("reason", ""),
                "step_abandoned_at": journey.get("step_abandoned_at"),
                "scenario":        journey.get("scenario"),
            },
        }).execute()

    except Exception:
        # DB write failures must not crash the simulation
        pass


def _default_business_state() -> dict:
    """Baseline (healthy) business state — no hidden fees, clear pricing."""
    return {
        "checkout_copy":   "standard",
        "fees_disclosed":  True,
        "hidden_fees":     [],
        "pricing_clarity": "high",
    }


def _fallback_journey(persona: dict, scenario: Optional[str], reason: str) -> dict:
    """Return a minimal journey dict when the LLM call fails."""
    return {
        "customer_id":       persona.get("name", "unknown"),
        "persona":           persona,
        "narration":         f"[LLM call failed: {reason}]",
        "event":             "CheckoutCompleted",
        "reason":            "llm_error",
        "step_abandoned_at": None,
        "result":            "completed",
        "duration_seconds":  0,
        "scenario":          scenario,
        "steps":             [],
        "goal":              persona.get("goal", ""),
        "device":            persona.get("device", "desktop"),
        "customer_type":     persona.get("customer_type", "returning"),
    }
