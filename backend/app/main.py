import os
import uuid
from typing import Optional, Dict
from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import time

# 1. Load environment variables
load_dotenv()

# Internal project imports
from app.database.db import get_client
from app.agents.orchestrator import Orchestrator, OrchestratorState
from app.simulation.scenario_engine import register_custom_scenario, get_scenario_business_state
from app.simulation.world_events import emit_customer_journey
from app.simulation.personas import PERSONAS
from app.agents.customer_agent import run_customer_simulation, _write_journey_to_db
from app.simulation.scenario_engine import run_scenario as inject_scenario, run_custom_scenario

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for run states
_runs: Dict[str, any] = {}

class CustomScenarioRequest(BaseModel):
    display_name: str = Field(..., max_length=80)
    root_cause: str = Field(..., max_length=200)
    target_device: str = Field("all")
    target_customer_type: str = Field("all")
    abandonment_rate: float = Field(0.5, ge=0.0, le=1.0)
    num_personas: int = Field(8, ge=4, le=20)
    persona_mode: str = Field("static")


def _run_custom_scenario_background(
    run_id: str,
    req: CustomScenarioRequest
):
    print("\n" + "=" * 80)
    print(f"[CUSTOM RUN START] run_id={run_id}")
    print(f"[CUSTOM RUN] request={req.model_dump()}")
    print("=" * 80)

    try:
        scenario_key = f"custom_{run_id[:8]}"
        db = get_client()

        print(f"[CUSTOM RUN] scenario_key={scenario_key}")
        print("[CUSTOM RUN] DB client created")

        register_custom_scenario(
            key=scenario_key,
            display_name=req.display_name,
            root_cause=req.root_cause,
            target_device=req.target_device,
            target_customer_type=req.target_customer_type,
            abandonment_rate=req.abandonment_rate,
        )

        print("[CUSTOM RUN] scenario registered")

        personas = PERSONAS[:req.num_personas]

        print(
            f"[CUSTOM RUN] personas={len(personas)}, "
            f"mode={req.persona_mode}"
        )

        business_state = get_scenario_business_state(scenario_key)

        print(
            f"[CUSTOM RUN] business_state={business_state}"
        )

        if req.persona_mode == "llm":
            print("[CUSTOM RUN] STARTING LLM CUSTOMER SIMULATION")
            journeys = run_customer_simulation(personas=personas, db=db, scenario=scenario_key, run_id=run_id)
            print(f"[CUSTOM RUN] LLM simulation returned {len(journeys)} journeys")
        else:
            print("[CUSTOM RUN] STARTING STATIC CUSTOMER SIMULATION")
            journeys = run_custom_scenario(scenario_key, personas)   # was: inject_scenario(scenario_key, personas)
            print(f"[CUSTOM RUN] run_custom_scenario returned {len(journeys)} journeys")

            for i, j in enumerate(journeys):
                j["customer_id"] = j.get("name", f"customer_{i}")
                print(f"[CUSTOM RUN] emitting world journey for {j['customer_id']}")
                emit_customer_journey(db, run_id, j)
                if db:
                    _write_journey_to_db(j, db)
                    
        print("[CUSTOM RUN] creating orchestrator")

        orch = Orchestrator(
            db=db,
            scenario=scenario_key,
            run_id=run_id,
            initial_journeys=journeys,
        )

        for state in orch.run_steps():
            print(
                f"[CUSTOM RUN] orchestrator state: "
                f"{getattr(state, 'stage', state)}"
            )
            _runs[run_id] = state

    except Exception as exc:

        print("\n" + "!" * 80)
        print(f"[CUSTOM RUN ERROR] run_id={run_id}")
        print(f"[CUSTOM RUN ERROR] {type(exc).__name__}: {exc}")
        print("!" * 80)

        import traceback
        traceback.print_exc()

        _runs[run_id] = {
            "run_id": run_id,
            "stage": "ERROR",
            "error": str(exc),
        }

@app.post("/run-custom")
async def start_custom_run(req: CustomScenarioRequest, background_tasks: BackgroundTasks):
    run_id = str(uuid.uuid4())
    # Initialize state so polling doesn't 404 immediately
    _runs[run_id] = {"stage": "DISCOVER", "run_id": run_id}
    
    background_tasks.add_task(_run_custom_scenario_background, run_id, req)
    return {"run_id": run_id, "message": "Custom scenario started"}

@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if hasattr(state, 'to_dict'):
        return state.to_dict()
    return state

class GenerateScenarioRequest(BaseModel):
    theme: Optional[str] = "any"

@app.post("/generate-scenario")
def generate_scenario(req: GenerateScenarioRequest):
    import os
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY missing"}

    client = genai.Client(api_key=api_key)

    schema = {
        "type": "object",
        "properties": {
            "display_name": {"type": "string"},
            "root_cause": {"type": "string"},
            "target_device": {"type": "string", "enum": ["all", "mobile", "desktop"]},
            "target_customer_type": {"type": "string", "enum": ["all", "first_time", "returning"]},
            "abandonment_rate": {"type": "number"},
        },
        "required": ["display_name", "root_cause", "target_device", "target_customer_type", "abandonment_rate"],
    }
    
    prompt = (
        "Propose one plausible e-commerce problem for a stress-test scenario. "
        "Vary the type each time (pricing, UX, technical, trust-related). "
        f"{'Theme hint: ' + req.theme if req.theme else ''}"
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        import json
        return json.loads(response.text)
    except Exception as exc:
        return {
            "display_name": "Custom Stress Test",
            "root_cause": "Unknown — AI generation failed",
            "target_device": "all",
            "target_customer_type": "all",
            "abandonment_rate": 0.5,
            "error": str(exc),
        }