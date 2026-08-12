import time
from app.database.db import get_client
from app.simulation.personas import PERSONAS
from app.simulation.scenario_engine import run_scenario

STEP_SEQUENCE = {
    "completed": ["CustomerEntered", "PricingViewed", "CheckoutStarted", "OrderCompleted"],
    "abandoned": ["CustomerEntered", "PricingViewed", "CheckoutStarted", "CustomerAbandoned"],
}

def run_simulation(scenario_name: str):
    db = get_client()
    journeys = run_scenario(scenario_name, PERSONAS)

    for j in journeys:
        customer = db.table("customers").insert({
            "name": j["name"],
            "persona": j["goal"],
            "device": j["device"],
            "customer_type": j["customer_type"],
        }).execute()
        customer_id = customer.data[0]["id"]

        journey = db.table("journeys").insert({
            "customer_id": customer_id,
            "scenario": scenario_name,
            "goal": j["goal"],
            "result": j["result"],
        }).execute()
        journey_id = journey.data[0]["id"]

        for step in STEP_SEQUENCE[j["result"]]:
            db.table("events").insert({
                "type": step,
                "customer_id": customer_id,
                "journey_id": journey_id,
                "metadata": {"device": j["device"], "customer_type": j["customer_type"]},
            }).execute()
            time.sleep(0.3)

    print(f"Simulation '{scenario_name}' complete: {len(journeys)} journeys.")


    