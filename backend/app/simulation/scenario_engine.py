"""
scenario_engine.py — Deterministic scenario injection engine.

Each scenario has:
  - An "inject" function that turns a persona + business_state into a journey result
  - Ground truth metadata for the evaluation harness
  - Optional YAML ground-truth file (scenarios/{name}.yaml) for full detail

Usage:
    from app.simulation.scenario_engine import run_scenario, SCENARIOS
    journeys = run_scenario("scenario_a", personas)

The inject functions are the authoritative source for synthetic data.
The YAML files are used by the test harness to assert agent behaviour.
"""

from __future__ import annotations

from typing import Callable, Optional


def _scenario_a_inject(persona: dict, business_state: Optional[dict] = None) -> str:
    """
    Scenario A — Mobile Checkout Fee Surprise.

    First-time mobile customers are shown an unexpected processing fee at the
    final payment step and abandon at a high rate.  All other segments complete.
    """
    if persona.get("device") == "mobile" and persona.get("customer_type") == "first_time":
        # ~80 % abandonment for the affected cohort (not 100 % — some persist)
        import random
        return "abandoned" if random.random() < 0.80 else "completed"
    return "completed"


def _scenario_b_inject(persona: dict, business_state: Optional[dict] = None) -> str:
    """
    Scenario B — Pricing Page Copy Confusion.

    Desktop first-time customers who read the pricing page carefully abandon
    when they see a different seat count at checkout.  Mobile users skimmed
    and are comparatively unaffected.
    """
    import random
    if persona.get("device") == "desktop" and persona.get("customer_type") == "first_time":
        return "abandoned" if random.random() < 0.70 else "completed"
    if persona.get("device") == "mobile" and persona.get("customer_type") == "first_time":
        return "abandoned" if random.random() < 0.20 else "completed"
    return "completed"


def _scenario_c_inject(persona: dict, business_state: Optional[dict] = None) -> str:
    """
    Scenario C — Weather Red Herring (Checkout Step Reorder).

    The checkout step order was reordered (payment before confirmation), confusing
    ALL customer segments.  Weather is a concurrent confound but not causal.

    Rate is lower per-segment than Scenario A (55 %) but site-wide.
    """
    import random
    return "abandoned" if random.random() < 0.55 else "completed"


SCENARIOS: dict[str, dict] = {
    "scenario_a": {
        "display_name": "Mobile Checkout Fee Surprise",
        "yaml": "scenarios/scenario_a.yaml",
        "ground_truth": {
            "root_cause": "unexpected_checkout_fee",
            "affected_segment": "mobile_first_time",
            "correct_intervention": "remove_checkout_fee",
        },
        "business_state": {
            "checkout_copy":   "standard",
            "fees_disclosed":  False,
            "hidden_fees":     [{"name": "processing_fee", "amount": 3.99}],
            "pricing_clarity": "high",
        },
        "inject": _scenario_a_inject,
    },

    "scenario_b": {
        "display_name": "Pricing Page Copy Confusion",
        "yaml": "scenarios/scenario_b.yaml",
        "ground_truth": {
            "root_cause": "pricing_confusion",
            "affected_segment": "desktop_first_time",
            "correct_intervention": "update_checkout_copy",
        },
        "business_state": {
            "checkout_copy":   "ambiguous_seats",
            "fees_disclosed":  True,
            "hidden_fees":     [],
            "pricing_clarity": "low",
        },
        "inject": _scenario_b_inject,
    },

    "scenario_c": {
        "display_name": "Weather Red Herring + Canary Rollback",
        "yaml": "scenarios/scenario_c.yaml",
        "ground_truth": {
            "root_cause": "checkout_step_reorder",
            "affected_segment": "all",
            "correct_intervention": "update_checkout_copy",
        },
        "business_state": {
            "checkout_copy":   "reordered_steps",
            "fees_disclosed":  True,
            "hidden_fees":     [],
            "pricing_clarity": "high",
        },
        "inject": _scenario_c_inject,
    },

    # Legacy key kept for backwards-compat with any existing code/tests
    "mobile_checkout_fee": {
        "display_name": "Mobile Checkout Fee (legacy alias → scenario_a)",
        "yaml": "scenarios/scenario_a.yaml",
        "ground_truth": {
            "root_cause": "unexpected_checkout_fee",
            "affected_segment": "first_time_mobile",
        },
        "business_state": {
            "checkout_copy":   "standard",
            "fees_disclosed":  False,
            "hidden_fees":     [{"name": "processing_fee", "amount": 3.99}],
            "pricing_clarity": "high",
        },
        "inject": _scenario_a_inject,
    },
}


def run_scenario(
    scenario_name: str,
    personas: list[dict],
    business_state: Optional[dict] = None,
) -> list[dict]:
    """
    Inject a scenario's outcome signal into a list of persona dicts.

    Args:
        scenario_name: One of the keys in SCENARIOS.
        personas:      List of persona dicts (from personas.py).
        business_state: Override the scenario's default business state.

    Returns:
        List of journey dicts: each persona dict + result, scenario, goal, device,
        customer_type fields, and the scenario's business_state snapshot.

    Raises:
        KeyError: if scenario_name is not registered.
    """
    scenario = SCENARIOS[scenario_name]
    bs = business_state or scenario.get("business_state", {})
    inject_fn: Callable = scenario["inject"]

    return [
        {
            **p,
            "scenario":       scenario_name,
            "result":         inject_fn(p, bs),
            "business_state": bs,
            "goal":           p.get("goal", "complete a purchase"),
            "device":         p.get("device", "desktop"),
            "customer_type":  p.get("customer_type", "returning"),
        }
        for p in personas
    ]


def get_scenario_ground_truth(scenario_name: str) -> dict:
    """
    Return the ground truth dict for the given scenario (for test assertions).

    Returns {} if the scenario does not exist.
    """
    return SCENARIOS.get(scenario_name, {}).get("ground_truth", {})


def get_scenario_business_state(scenario_name: str) -> dict:
    """Return the default business state for the given scenario."""
    return SCENARIOS.get(scenario_name, {}).get("business_state", {})


def list_scenarios() -> list[dict]:
    """Return a summary list of all registered scenarios for the API layer."""
    return [
        {
            "name":         name,
            "display_name": cfg.get("display_name", name),
            "ground_truth": cfg.get("ground_truth", {}),
        }
        for name, cfg in SCENARIOS.items()
        if name != "mobile_checkout_fee"  # hide legacy alias
    ]


def _custom_inject(persona: dict, business_state: dict | None = None) -> str:
    """
    Generic parametrized injector for user-defined stress-test scenarios.
    business_state carries: target_device, target_customer_type, abandonment_rate.
    "all" or None on target_* matches every persona in that dimension.
    """
    import random
    bs = business_state or {}
    device = persona.get("device")
    ctype = persona.get("customer_type")
    target_device = bs.get("target_device") or "all"
    target_type = bs.get("target_customer_type") or "all"
    rate = float(bs.get("abandonment_rate", 0.5))

    matches = (target_device in ("all", device)) and (target_type in ("all", ctype))
    if matches:
        return "abandoned" if random.random() < rate else "completed"
    return "completed"


def register_custom_scenario(
    key: str,
    display_name: str,
    root_cause: str,
    target_device: str,
    target_customer_type: str,
    abandonment_rate: float,
    extra_business_state: dict | None = None,
) -> dict:
    """
    Register a user-defined stress-test scenario at runtime.
    Returns the registered scenario config dict.
    """
    affected_segment = (
        "all" if target_device == "all" and target_customer_type == "all"
        else f"{target_device}_{target_customer_type}"
    )
    business_state = {
        "checkout_copy": "custom",
        "fees_disclosed": True,
        "hidden_fees": [],
        "pricing_clarity": "high",
        "target_device": target_device,
        "target_customer_type": target_customer_type,
        "abandonment_rate": abandonment_rate,
        **(extra_business_state or {}),
    }
    SCENARIOS[key] = {
        "display_name": display_name,
        "yaml": None,
        "ground_truth": {
            "root_cause": root_cause,
            "affected_segment": affected_segment,
        },
        "business_state": business_state,
        "inject": _custom_inject,
        "is_custom": True,
    }
    return SCENARIOS[key]
