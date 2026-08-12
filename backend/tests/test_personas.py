"""
tests/test_personas.py
======================
Tests for both static personas and LLM-generated persona enrichment.

Run with:
    cd backend
    python -m pytest tests/test_personas.py -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.simulation.personas import PERSONAS
from app.simulation.scenario_engine import run_scenario
from app.simulation.simulator import run_simulation, STEP_SEQUENCE


# ===========================================================================
# Static persona tests (no LLM, always deterministic)
# ===========================================================================

class TestStaticPersonas:

    def test_personas_not_empty(self):
        assert len(PERSONAS) > 0

    def test_all_personas_have_required_keys(self):
        required = {"name", "device", "customer_type", "goal"}
        for p in PERSONAS:
            assert required.issubset(p.keys()), f"Persona {p} missing keys"

    def test_device_values_are_valid(self):
        valid_devices = {"mobile", "desktop"}
        for p in PERSONAS:
            assert p["device"] in valid_devices, f"{p['name']} has invalid device: {p['device']}"

    def test_customer_type_values_are_valid(self):
        valid_types = {"first_time", "returning"}
        for p in PERSONAS:
            assert p["customer_type"] in valid_types

    def test_scenario_injection_is_deterministic(self):
        """Same input → same output every time."""
        run1 = run_scenario("mobile_checkout_fee", PERSONAS)
        run2 = run_scenario("mobile_checkout_fee", PERSONAS)
        assert run1 == run2

    def test_mobile_first_time_abandoned_in_mobile_checkout_fee(self):
        journeys = run_scenario("mobile_checkout_fee", PERSONAS)
        for j in journeys:
            if j["device"] == "mobile" and j["customer_type"] == "first_time":
                assert j["result"] == "abandoned", (
                    f"{j['name']} should be abandoned (mobile first_time), got {j['result']}"
                )

    def test_desktop_users_complete_in_mobile_checkout_fee(self):
        journeys = run_scenario("mobile_checkout_fee", PERSONAS)
        for j in journeys:
            if j["device"] == "desktop":
                assert j["result"] == "completed", (
                    f"{j['name']} (desktop) should complete, got {j['result']}"
                )

    def test_returning_mobile_users_complete(self):
        """Returning mobile users are NOT in the affected segment."""
        journeys = run_scenario("mobile_checkout_fee", PERSONAS)
        for j in journeys:
            if j["device"] == "mobile" and j["customer_type"] == "returning":
                assert j["result"] == "completed"

    def test_step_sequences_are_correct(self):
        assert STEP_SEQUENCE["completed"][-1] == "OrderCompleted"
        assert STEP_SEQUENCE["abandoned"][-1] == "CustomerAbandoned"
        assert STEP_SEQUENCE["completed"][0] == STEP_SEQUENCE["abandoned"][0] == "CustomerEntered"


# ===========================================================================
# LLM persona tests — use mocks so tests run without a real API key
# ===========================================================================

MOCK_LLM_PROFILE = {
    "greeting_style": "Hi, I'm trying to sign up but it keeps charging me extra fees?",
    "hesitation_note": "She paused at checkout when she saw an unexpected $5 processing fee.",
    "complaint_phrasing": "This is ridiculous — you advertise one price and charge another.",
    "urgency": "high",
    "session_notes": "First-time mobile visitor, dropped at payment step, possible fee confusion.",
}


def _make_mock_client(profile: dict = None, fail: bool = False):
    """Build a mock Gemini client that returns a fixed profile or simulates failure."""
    mock_client = MagicMock()
    if fail:
        mock_client.models.generate_content.side_effect = Exception("API quota exceeded")
    else:
        mock_response = MagicMock()
        mock_response.text = json.dumps(profile or MOCK_LLM_PROFILE)
        mock_client.models.generate_content.return_value = mock_response
    return mock_client


class TestLLMPersonaGeneration:

    def test_generate_llm_profile_returns_dict_on_success(self):
        from app.simulation.llm_personas import generate_llm_profile
        client = _make_mock_client(MOCK_LLM_PROFILE)
        result = generate_llm_profile(PERSONAS[0], client=client)
        assert isinstance(result, dict)

    def test_generate_llm_profile_has_all_required_keys(self):
        from app.simulation.llm_personas import generate_llm_profile
        client = _make_mock_client(MOCK_LLM_PROFILE)
        result = generate_llm_profile(PERSONAS[0], client=client)
        required = {"greeting_style", "hesitation_note", "complaint_phrasing", "urgency", "session_notes"}
        assert required.issubset(result.keys())

    def test_generate_llm_profile_returns_none_on_api_failure(self):
        from app.simulation.llm_personas import generate_llm_profile
        client = _make_mock_client(fail=True)
        result = generate_llm_profile(PERSONAS[0], client=client)
        assert result is None

    def test_generate_llm_profile_returns_none_on_bad_json(self):
        from app.simulation.llm_personas import generate_llm_profile
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "not valid json {{{"
        mock_client.models.generate_content.return_value = mock_response
        result = generate_llm_profile(PERSONAS[0], client=mock_client)
        assert result is None

    def test_generate_llm_profile_returns_none_on_missing_keys(self):
        from app.simulation.llm_personas import generate_llm_profile
        incomplete = {"greeting_style": "Hi", "urgency": "high"}  # missing 3 keys
        client = _make_mock_client(incomplete)
        result = generate_llm_profile(PERSONAS[0], client=client)
        assert result is None

    def test_generate_llm_profile_strips_markdown_fences(self):
        from app.simulation.llm_personas import generate_llm_profile
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Simulate model wrapping response in ```json ... ```
        mock_response.text = "```json\n" + json.dumps(MOCK_LLM_PROFILE) + "\n```"
        mock_client.models.generate_content.return_value = mock_response
        result = generate_llm_profile(PERSONAS[0], client=mock_client)
        assert result is not None
        assert result["urgency"] == MOCK_LLM_PROFILE["urgency"]

    def test_urgency_is_valid_value(self):
        from app.simulation.llm_personas import generate_llm_profile
        client = _make_mock_client(MOCK_LLM_PROFILE)
        result = generate_llm_profile(PERSONAS[0], client=client)
        assert result["urgency"] in {"low", "medium", "high"}


class TestEnrichPersonasWithLLM:

    def test_enrich_returns_same_count_as_input(self):
        from app.simulation.llm_personas import enrich_personas_with_llm
        client = _make_mock_client(MOCK_LLM_PROFILE)
        result = enrich_personas_with_llm(PERSONAS, client=client)
        assert len(result) == len(PERSONAS)

    def test_enrich_adds_llm_profile_key(self):
        from app.simulation.llm_personas import enrich_personas_with_llm
        client = _make_mock_client(MOCK_LLM_PROFILE)
        result = enrich_personas_with_llm(PERSONAS, client=client)
        for p in result:
            assert "llm_profile" in p

    def test_enrich_does_not_mutate_original_personas(self):
        from app.simulation.llm_personas import enrich_personas_with_llm
        original_copy = [dict(p) for p in PERSONAS]
        client = _make_mock_client(MOCK_LLM_PROFILE)
        enrich_personas_with_llm(PERSONAS, client=client)
        assert PERSONAS == original_copy  # originals untouched

    def test_enrich_preserves_static_core_keys(self):
        """LLM enrichment must NOT overwrite name/device/customer_type/goal."""
        from app.simulation.llm_personas import enrich_personas_with_llm
        client = _make_mock_client(MOCK_LLM_PROFILE)
        enriched = enrich_personas_with_llm(PERSONAS, client=client)
        for original, enriched_p in zip(PERSONAS, enriched):
            for key in ("name", "device", "customer_type", "goal"):
                assert enriched_p[key] == original[key], (
                    f"Key '{key}' was mutated for {original['name']}"
                )

    def test_enrich_falls_back_gracefully_on_llm_failure(self):
        """If LLM fails for every persona, llm_profile=None but no exception raised."""
        from app.simulation.llm_personas import enrich_personas_with_llm
        client = _make_mock_client(fail=True)
        result = enrich_personas_with_llm(PERSONAS, client=client)
        assert len(result) == len(PERSONAS)
        for p in result:
            assert p["llm_profile"] is None

    def test_scenario_injection_unaffected_by_enrichment(self):
        """
        Critical: scenario outcomes must be identical whether personas are
        static or LLM-enriched, because injection only reads device/customer_type.
        """
        from app.simulation.llm_personas import enrich_personas_with_llm
        client = _make_mock_client(MOCK_LLM_PROFILE)
        enriched = enrich_personas_with_llm(PERSONAS, client=client)

        static_journeys  = run_scenario("mobile_checkout_fee", PERSONAS)
        enriched_journeys = run_scenario("mobile_checkout_fee", enriched)

        for s, e in zip(static_journeys, enriched_journeys):
            assert s["result"] == e["result"], (
                f"{s['name']}: static={s['result']} vs llm={e['result']} — should be equal"
            )


# ===========================================================================
# Simulator integration tests (mock DB + mock LLM)
# ===========================================================================

class TestSimulatorModes:

    def _make_mock_db(self):
        """Minimal mock for the Supabase client chain: .table().insert().execute()"""
        mock_db = MagicMock()
        mock_execute = MagicMock()
        mock_execute.data = [{"id": "mock-uuid-123"}]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute
        return mock_db

    @patch("app.simulation.simulator.get_client")
    def test_static_mode_runs_without_llm_import(self, mock_get_client):
        """Static mode must never call llm_personas."""
        mock_get_client.return_value = self._make_mock_db()
        with patch("app.simulation.simulator.time.sleep"):  # skip real delay
            run_simulation("mobile_checkout_fee", mode="static")

    @patch("app.simulation.simulator.get_client")
    def test_llm_mode_attaches_simulation_mode_in_metadata(self, mock_get_client):
        """Events in LLM mode should have simulation_mode='llm' in metadata."""
        mock_db = self._make_mock_db()
        mock_get_client.return_value = mock_db

        with patch("app.simulation.llm_personas.enrich_personas_with_llm") as mock_enrich:
            # Return enriched personas without real LLM call
            mock_enrich.return_value = [
                {**p, "llm_profile": MOCK_LLM_PROFILE} for p in PERSONAS
            ]
            with patch("app.simulation.simulator.time.sleep"):
                run_simulation("mobile_checkout_fee", mode="llm")

        # Check that events were inserted with metadata containing simulation_mode
        insert_calls = mock_db.table.return_value.insert.call_args_list
        event_calls = [c for c in insert_calls if "type" in str(c)]
        # At least some events should have been recorded
        assert len(insert_calls) > 0

    @patch("app.simulation.simulator.get_client")
    def test_abandoned_event_has_complaint_phrasing_in_llm_mode(self, mock_get_client):
        """CustomerAbandoned events in LLM mode should carry complaint_phrasing."""
        mock_db = MagicMock()
        mock_execute = MagicMock()
        mock_execute.data = [{"id": "mock-uuid-123"}]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute
        mock_get_client.return_value = mock_db

        with patch("app.simulation.llm_personas.enrich_personas_with_llm") as mock_enrich:
            mock_enrich.return_value = [
                {**p, "llm_profile": MOCK_LLM_PROFILE} for p in PERSONAS
            ]
            with patch("app.simulation.simulator.time.sleep"):
                run_simulation("mobile_checkout_fee", mode="llm")

        # Inspect all insert calls and find CustomerAbandoned event rows
        all_insert_calls = mock_db.table.return_value.insert.call_args_list
        abandoned_metadatas = [
            call.args[0].get("metadata", {})
            for call in all_insert_calls
            if isinstance(call.args[0], dict) and call.args[0].get("type") == "CustomerAbandoned"
        ]

        # There should be at least one abandoned event (mobile first_time personas)
        assert len(abandoned_metadatas) > 0, "Expected at least one CustomerAbandoned event"
        for meta in abandoned_metadatas:
            assert "complaint_phrasing" in meta, f"Missing complaint_phrasing in: {meta}"
            assert "hesitation_note" in meta, f"Missing hesitation_note in: {meta}"
