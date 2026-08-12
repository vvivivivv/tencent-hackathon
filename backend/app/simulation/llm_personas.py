"""
LLM-Generated Personas
======================
Wraps the static PERSONAS baseline with Gemini-generated per-run variation.

Design contract:
- Deterministic core: device, customer_type, goal remain fixed per persona slot,
  so scenario injection logic (scenario_engine.py) stays predictable and testable.
- LLM surface layer: each persona gets an `llm_profile` dict containing
  natural-language variation that changes on every run:
    - `greeting_style`   : how the customer opens a chat / support ticket
    - `hesitation_note`  : what makes them pause before converting
    - `complaint_phrasing`: how they'd phrase a complaint if abandoned
    - `urgency`          : "low" | "medium" | "high"
    - `session_notes`    : short freeform context (like a CRM note)

If the LLM call fails (network, quota, missing key) the module falls back
to the static persona unchanged — static testing is never broken.
"""

import os
import re
import time
import logging
from typing import Optional

from app.simulation.personas import PERSONAS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt — minimal to reduce token pressure and avoid quoting issues
# ---------------------------------------------------------------------------

_USER_TEMPLATE = (
    "Customer: {name}, {device}, {customer_type}, goal={goal}.\n"
    "Vary tone each call. "
    "first_time=unfamiliar tone; returning=references past; mobile=on-the-go feel.\n"
    "urgency: renew->high, signup->medium, compare_plans->low, cheapest_plan->medium."
)

# ---------------------------------------------------------------------------
# Response schema — Gemini enforces this at the API level; no JSON parsing needed
# ---------------------------------------------------------------------------

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "greeting_style":    {"type": "string", "description": "Opening message to support, max 12 words"},
        "hesitation_note":   {"type": "string", "description": "What made them pause, max 12 words"},
        "complaint_phrasing":{"type": "string", "description": "How they'd complain if abandoned, max 12 words"},
        "urgency":           {"type": "string", "enum": ["low", "medium", "high"]},
        "session_notes":     {"type": "string", "description": "One-line CRM note, max 12 words"},
    },
    "required": ["greeting_style", "hesitation_note", "complaint_phrasing", "urgency", "session_notes"],
}


def _get_gemini_client():
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning(f"[llm_personas] Gemini client init failed: {e}")
        return None


def generate_llm_profile(persona: dict, client=None, retries: int = 2) -> Optional[dict]:
    """
    Call Gemini with a response_schema so the API enforces valid JSON structure.
    Retries on rate-limit (429) only — schema-validated responses never need
    JSON parse retries.
    Returns a dict on success, None on failure (caller falls back to static).
    """
    if client is None:
        client = _get_gemini_client()
    if client is None:
        return None

    prompt = _USER_TEMPLATE.format(
        name=persona["name"],
        device=persona["device"],
        customer_type=persona["customer_type"],
        goal=persona["goal"],
    )

    from google.genai import types

    for attempt in range(1 + retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    max_output_tokens=300,
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,  # API-level schema enforcement
                ),
            )

            # With response_schema, response.text is guaranteed valid JSON
            # but we still guard against unexpected None
            raw = getattr(response, "text", None)
            if not raw:
                logger.warning(f"[llm_personas] Empty response for {persona['name']} (attempt {attempt+1})")
                if attempt < retries:
                    time.sleep(2)
                continue

            import json
            profile = json.loads(raw.strip())

            # Normalise urgency in case model ignores the enum (defensive)
            if profile.get("urgency") not in {"low", "medium", "high"}:
                profile["urgency"] = "medium"

            return profile

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = 15
                m = re.search(r"retry[_\s]delay.*?(\d+)", err_str, re.IGNORECASE)
                if not m:
                    m = re.search(r"retry in (\d+)", err_str, re.IGNORECASE)
                if m:
                    wait = int(m.group(1)) + 2
                logger.warning(
                    f"[llm_personas] Rate limit for {persona['name']}, "
                    f"waiting {wait}s (attempt {attempt+1}/{1+retries})"
                )
                time.sleep(wait)
            else:
                logger.warning(f"[llm_personas] LLM call failed for {persona['name']}: {e}")
                return None  # non-retryable error

    logger.warning(f"[llm_personas] All attempts exhausted for {persona['name']}, using static fallback")
    return None


def enrich_personas_with_llm(personas: list = None, client=None) -> list:
    """
    Takes a list of static persona dicts and returns enriched copies.
    Each persona gets an `llm_profile` key:
      - On success: dict from Gemini
      - On failure: None  (static core data is untouched)

    The static keys (name, device, customer_type, goal) are never modified,
    so scenario_engine.py injection logic remains fully deterministic.

    Args:
        personas: list of persona dicts. Defaults to PERSONAS if None.
        client:   optional pre-built Gemini client (for testing / reuse).

    Returns:
        list of enriched persona dicts (new objects, originals unchanged).
    """
    if personas is None:
        personas = PERSONAS

    if client is None:
        client = _get_gemini_client()

    enriched = []
    for i, p in enumerate(personas):
        # Free tier: 5 req/min → space calls ~13s apart to stay safely under limit
        if i > 0:
            time.sleep(13)
        profile = generate_llm_profile(p, client=client)
        enriched.append({**p, "llm_profile": profile})
        if profile:
            logger.info(f"[llm_personas] Enriched {p['name']} — urgency={profile['urgency']}")
        else:
            logger.info(f"[llm_personas] {p['name']} — LLM unavailable, using static fallback")

    return enriched


def get_llm_personas() -> list:
    """
    Returns PERSONAS enriched with LLM-generated variation.
    Safe to call even without a valid GEMINI_API_KEY — returns static personas
    with llm_profile=None rather than raising.
    """
    return enrich_personas_with_llm()
