SCENARIOS = {
    "mobile_checkout_fee": {
        "ground_truth": {
            "root_cause": "unexpected_checkout_fee",
            "affected_segment": "first_time_mobile",
        },
        "inject": lambda persona: (
            "abandoned" if persona["device"] == "mobile"
            and persona["customer_type"] == "first_time"
            else "completed"
        ),
    },
}

def run_scenario(scenario_name: str, personas: list) -> list:
    scenario = SCENARIOS[scenario_name]
    return [
        {**p, "scenario": scenario_name, "result": scenario["inject"](p)}
        for p in personas
    ]
