import time
import logging
from app.database.db import get_client
from app.simulation.personas import PERSONAS
from app.simulation.scenario_engine import run_scenario

logger = logging.getLogger(__name__)

STEP_SEQUENCE = {
    "completed": ["CustomerEntered", "PricingViewed", "CheckoutStarted", "OrderCompleted"],
    "abandoned": ["CustomerEntered", "PricingViewed", "CheckoutStarted", "CustomerAbandoned"],
}

def run_simulation(scenario_name: str, mode: str = "static"):
    """
    Run a simulation scenario.

    Args:
        scenario_name: key into SCENARIOS (e.g. "mobile_checkout_fee")
        mode:
          "static" — use PERSONAS as-is (deterministic, good for unit tests & baseline)
          "llm"    — enrich PERSONAS with Gemini-generated per-run variation before
                     running the scenario. Deterministic core (device/customer_type/goal)
                     is unchanged; only the `llm_profile` surface layer varies.
    """
    db = get_client()

    if mode == "llm":
        from app.simulation.llm_personas import enrich_personas_with_llm
        personas = enrich_personas_with_llm(PERSONAS)
        logger.info(f"[simulator] Mode=llm — enriched {len(personas)} personas via Gemini")
    else:
        # static: wrap with llm_profile=None so downstream code has a uniform shape
        personas = [{**p, "llm_profile": None} for p in PERSONAS]
        logger.info(f"[simulator] Mode=static — using {len(personas)} baseline personas")

    journeys = run_scenario(scenario_name, personas)

    for j in journeys:
        # Build customer record
        customer_row = {
            "name": j["name"],
            "persona": j["goal"],
            "device": j["device"],
            "customer_type": j["customer_type"],
        }
        customer = db.table("customers").insert(customer_row).execute()
        customer_id = customer.data[0]["id"]

        # Build journey record
        journey_row = {
            "customer_id": customer_id,
            "scenario": scenario_name,
            "goal": j["goal"],
            "result": j["result"],
        }
        journey = db.table("journeys").insert(journey_row).execute()
        journey_id = journey.data[0]["id"]

        # Build base event metadata
        base_meta = {
            "device": j["device"],
            "customer_type": j["customer_type"],
            "simulation_mode": mode,
        }

        # If LLM profile exists, surface urgency & session_notes in every event's
        # metadata so dashboards / analyst agents can observe authentic variation
        if j.get("llm_profile"):
            base_meta["urgency"] = j["llm_profile"].get("urgency")
            base_meta["session_notes"] = j["llm_profile"].get("session_notes")

        for step in STEP_SEQUENCE[j["result"]]:
            event_meta = {**base_meta, "step": step}

            # For abandonment events, attach the LLM-generated phrasing so the
            # Investigator agent can read authentic customer voice
            if step == "CustomerAbandoned" and j.get("llm_profile"):
                event_meta["complaint_phrasing"] = j["llm_profile"].get("complaint_phrasing")
                event_meta["hesitation_note"] = j["llm_profile"].get("hesitation_note")

            db.table("events").insert({
                "type": step,
                "customer_id": customer_id,
                "journey_id": journey_id,
                "metadata": event_meta,
            }).execute()
            time.sleep(0.3)

    print(f"Simulation '{scenario_name}' [{mode} mode] complete: {len(journeys)} journeys.")
    _print_summary(journeys, mode)


def _print_summary(journeys: list, mode: str):
    """Print a brief run summary to stdout."""
    completed = sum(1 for j in journeys if j["result"] == "completed")
    abandoned  = sum(1 for j in journeys if j["result"] == "abandoned")
    llm_enriched = sum(1 for j in journeys if j.get("llm_profile") is not None)

    print(f"  completed={completed}  abandoned={abandoned}  llm_enriched={llm_enriched}/{len(journeys)}")

    if mode == "llm":
        for j in journeys:
            p = j.get("llm_profile")
            if p:
                print(f"  [{j['name']}] urgency={p['urgency']}  | {p['session_notes']}")
            else:
                print(f"  [{j['name']}] llm_profile=None (fallback to static)")

