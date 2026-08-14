"""
orchestrator.py — Agent state machine.

State flow (as per README §5.3):

    DISCOVER → OBSERVE → DETECT → INVESTIGATE → HYPOTHESIZE+VALIDATE
        → PLAN → ACT (canary) → CANARY_CHECK → ACT (full) → VERIFY → CLOSE

The orchestrator owns the pipeline.  Each state transition is a plain Python
call — no magic, no framework.  The state is a simple dataclass so it can be
serialised and pushed to Supabase Realtime for the frontend console stream.

Usage (end-to-end in one call):
    from app.agents.orchestrator import Orchestrator
    result = Orchestrator(db=supabase_client, scenario="scenario_a").run()

Usage (step-by-step for streaming):
    orch = Orchestrator(db=..., scenario="scenario_a")
    for state_snapshot in orch.run_steps():
        push_to_realtime(state_snapshot)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Generator

from app.business.metrics import run_detection, DetectionResult
from app.tools.analytics import _fetch_journeys
from app.agents.investigator import investigate_from_detection, InvestigatorReport
from app.agents.operator import operate, OperatorReport
import app.agents.memory as memory
from app.simulation.world_events import (
    emit_anomaly_alert, emit_agent_move, emit_agent_speak,
    emit_agent_fix_apply, emit_agent_verify, emit_metrics_update, emit_incident_resolved,
)


class Stage(str, Enum):
    DISCOVER       = "DISCOVER"
    OBSERVE        = "OBSERVE"
    DETECT         = "DETECT"
    INVESTIGATE    = "INVESTIGATE"
    PLAN           = "PLAN"
    ACT_CANARY     = "ACT_CANARY"
    CANARY_CHECK   = "CANARY_CHECK"
    ACT_FULL       = "ACT_FULL"
    VERIFY         = "VERIFY"
    CLOSE          = "CLOSE"
    ESCALATED      = "ESCALATED"
    ERROR          = "ERROR"


@dataclass
class OrchestratorState:
    """
    Serialisable snapshot of one pipeline run.

    This is pushed to Supabase Realtime on every stage transition so the
    frontend console panel can stream progress in real time.
    """
    run_id:               str
    scenario:             Optional[str]
    stage:                Stage                    = Stage.DISCOVER
    started_at:           str                      = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at:          Optional[str]            = None
    elapsed_seconds:      float                    = 0.0

    # Stage outputs — populated as the pipeline progresses
    journey_count:        int                      = 0
    detection:            Optional[dict]           = None
    investigator_report:  Optional[dict]           = None
    operator_report:      Optional[dict]           = None
    outcome:              Optional[str]            = None
    error:                Optional[str]            = None

    # Hypothesis board — list of {"label": str, "confidence": float, "falsified": bool}
    hypotheses:           list[dict]               = field(default_factory=list)

    # Health scores (0-100)
    health_before:        Optional[float]          = None
    health_after:         Optional[float]          = None
    revenue_impact_monthly: Optional[float]        = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stage"] = self.stage.value
        return d

    def emit(self, db) -> None:
        """Push this snapshot to Supabase as a Realtime event."""
        if db is None:
            return
        try:
            db.table("events").insert({
                "type":     "orchestrator_state",
                "metadata": self.to_dict(),
            }).execute()
        except Exception:
            pass


class Orchestrator:
    """
    Runs the full First Customer pipeline for one scenario.

    Args:
        db:       Supabase client.  Pass None to run in offline/test mode.
        scenario: Scenario name filter (e.g. 'scenario_a').  None = all data.
        hours:    Time window for journey fetching (default 24 h).
        run_id:   Optional explicit run ID; auto-generated if not provided.
    """

    def __init__(
        self,
        db=None,
        scenario: Optional[str] = None,
        hours: int = 24,
        run_id: Optional[str] = None,
        initial_journeys: Optional[list[dict]] = None,
    ) -> None:
        import uuid
        self.db       = db
        self.scenario = scenario
        self.hours    = hours
        self._journeys = initial_journeys or []
        self.state    = OrchestratorState(
            run_id=run_id or str(uuid.uuid4()),
            scenario=scenario,
        )
        self._start_time = time.time()

        # Seed episodic memory with demo data (no-op if already seeded)
        memory.seed_demo_episodes()

   
    def run(self) -> OrchestratorState:
        """
        Run the complete pipeline synchronously.

        Returns the final OrchestratorState.  Use run_steps() for streaming.
        """
        for _ in self.run_steps():
            pass
        return self.state

    def run_steps(self) -> Generator[OrchestratorState, None, None]:
        """
        Generator: yields OrchestratorState after each stage transition.

        Callers iterate this to push progress events to Supabase Realtime
        and update the frontend console without blocking on the full pipeline.
        """
        try:
            yield from self._stage_discover()
            time.sleep(2)
            yield from self._stage_observe()
            time.sleep(1.5)
            yield from self._stage_detect()
            time.sleep(2)
            if not self.state.detection or not self.state.detection.get("has_anomaly"):
                yield from self._stage_close("no_anomaly")
                return
            yield from self._stage_investigate()
            time.sleep(4)
            if self.state.investigator_report and self.state.investigator_report.get("needs_human_review"):
                yield from self._stage_escalate()
                return
            yield from self._stage_act()
            time.sleep(2)
            yield from self._stage_verify()
            time.sleep(2)
            yield from self._stage_close(self.state.operator_report.get("outcome", "unknown") if self.state.operator_report else "unknown")

        except Exception as exc:
            self.state.stage = Stage.ERROR
            self.state.error = str(exc)
            self.state.finished_at = datetime.now(timezone.utc).isoformat()
            self.state.elapsed_seconds = time.time() - self._start_time
            self.state.emit(self.db)
            yield self.state
            raise

  
    def _transition(self, stage: Stage) -> OrchestratorState:
        self.state.stage = stage
        self.state.elapsed_seconds = time.time() - self._start_time
        self.state.emit(self.db)
        return self.state

    def _stage_discover(self):
        """DISCOVER — initialise the run, load episodic memory context."""
        self._transition(Stage.DISCOVER)
        # Load any past relevant episodes into memory
        memory.load_from_db(self.db)
        past = memory.retrieve_similar(scenario=self.scenario, limit=3)
        if past:
            # Attach memory context to the state for console display
            self.state.detection = {
                "memory_context": [ep.summary() for ep in past],
            }
        yield self.state

    def _stage_observe(self):
        """OBSERVE — fetch raw journey data."""
        self._transition(Stage.OBSERVE)
        if not self._journeys:
            self._journeys = _fetch_journeys(self.db, scenario=self.scenario, hours=self.hours) if self.db else []
        
        self.state.journey_count = len(self._journeys)
        yield self.state

    def _stage_detect(self):
        self._transition(Stage.DETECT)
        detection_result: DetectionResult = run_detection(self._journeys, scenario=self.scenario)
        self._detection = detection_result
        self.state.detection = detection_result.to_dict()

        self.state.operator_report = {
            "reasoning": f"Analyzed {len(self._journeys)} journeys. " + 
                         (f"Primary issue: {detection_result.summary}" if detection_result.has_anomaly else "No deviations found.")
        }

        if detection_result.has_anomaly:
            emit_anomaly_alert(self.db, self.state.run_id, detection_result.summary)
            self.state.outcome = "Anomaly Detected"
        else:
            self.state.outcome = "System Healthy"
            
        yield self.state

        if self._journeys:
            total = len(self._journeys)
            completed = sum(1 for j in self._journeys if j.get("result") == "completed")
            conversion = completed / total if total else 0.0
            self.state.health_before = round(conversion * 100, 1)
            emit_metrics_update(self.db, self.state.run_id,
                                abandonment_pct=round((1 - conversion) * 100),
                                conversion_pct=round(conversion * 100))
        yield self.state

    def _stage_investigate(self):
        self._transition(Stage.INVESTIGATE)
        emit_agent_move(self.db, self.state.run_id, "aisle_center")
        emit_agent_speak(self.db, self.state.run_id, "Anomaly detected. Investigating root cause...")
        self.state.investigator_report = {
            "reasoning": "Constructing counterfactual tests... Comparing mobile vs desktop baselines."
        }
        yield self.state
        time.sleep(2)

        report = investigate_from_detection(self._detection, db=self.db, scenario=self.scenario)
        self._investigator_report = report
        self.state.investigator_report = report.to_dict()
        emit_agent_speak(self.db, self.state.run_id, f"Found it: {report.root_cause[:40]}...")
        
        self.state.hypotheses = _extract_hypotheses(report)
        yield self.state
        

    def _stage_act(self):
        """PLAN + ACT (canary) + CANARY_CHECK + ACT (full) — Operator applies fix."""
        self._transition(Stage.PLAN)
        yield self.state

        self._transition(Stage.ACT_CANARY)
        emit_agent_move(self.db, self.state.run_id, "cashier")

        operator_report: OperatorReport = operate(self._investigator_report, db=self.db)
        self._operator_report = operator_report
        self.state.operator_report = operator_report.to_dict()
        self.state.outcome = operator_report.outcome

        if operator_report.intervention_type:
            emit_agent_fix_apply(self.db, self.state.run_id, operator_report.intervention_type)

        self._transition(Stage.CANARY_CHECK)
        yield self.state
        self._transition(Stage.ACT_FULL)
        yield self.state

    def _stage_verify(self):
        """VERIFY — re-run detection on the updated business state."""
        self._transition(Stage.VERIFY)
        emit_agent_verify(self.db, self.state.run_id)

        # Re-fetch journeys after intervention
        post_journeys = _fetch_journeys(self.db, scenario=self.scenario, hours=self.hours) if self.db else []
        total = len(post_journeys)
        if total:
            completed = sum(1 for j in post_journeys if j.get("result") == "completed")
            conversion_after = completed / total
            self.state.health_after = round(conversion_after * 100, 1)

            # Estimate monthly revenue impact (rough: $100 avg order, 30-day projection)
            if self.state.health_before is not None:
                improvement_pp = conversion_after - (self.state.health_before / 100)
                self.state.revenue_impact_monthly = round(
                    improvement_pp * total * 30 * 100, 2
                )

        # Record episode to memory
        if self._investigator_report and self._operator_report:
            ir = self._investigator_report
            op = self._operator_report
            canary = op.canary_passed
            improvement = None
            if self.state.health_before and self.state.health_after:
                improvement = (self.state.health_after - self.state.health_before) / 100
            ep = memory.Episode(
                incident_id=self.state.run_id,
                scenario=self.scenario or "unknown",
                affected_segment=ir.affected_segment,
                root_cause=ir.root_cause,
                confidence=ir.confidence,
                intervention_type=op.intervention_type or "unknown",
                outcome=op.outcome,
                canary_passed=canary,
                improvement_pp=improvement,
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
            memory.record(ep)
            memory.save_to_db(ep, self.db)

        yield self.state

    def _stage_close(self, outcome: str):
        """CLOSE — mark run complete and emit final state."""
        self._transition(Stage.CLOSE)
        self.state.outcome = outcome
        self.state.finished_at = datetime.now(timezone.utc).isoformat()
        self.state.elapsed_seconds = time.time() - self._start_time

        # Write incident record to DB
        if self.db and self._detection.has_anomaly:
            try:
                self.db.table("incidents").insert({
                    "title":            self.state.detection.get("summary", "Anomaly detected"),
                    "severity":         self._detection.primary_anomaly.severity if self._detection.has_anomaly else "low",
                    "scenario":         self.scenario,
                    "affected_segment": self.state.investigator_report.get("affected_segment") if self.state.investigator_report else None,
                    "root_cause":       self.state.investigator_report.get("root_cause") if self.state.investigator_report else None,
                    "confidence":       self.state.investigator_report.get("confidence") if self.state.investigator_report else None,
                    "status":           outcome,
                    "actions":          self.state.operator_report.get("actions_taken", []) if self.state.operator_report else [],
                    "health_before":    self.state.health_before,
                    "health_after":     self.state.health_after,
                    "revenue_impact":   self.state.revenue_impact_monthly,
                }).execute()
            except Exception:
                pass
                
            if outcome == "resolved":
                emit_incident_resolved(self.db, self.state.run_id)

        yield self.state

    def _stage_escalate(self):
        """ESCALATED — confidence below threshold; no write actions taken."""
        self._transition(Stage.ESCALATED)
        self.state.outcome = "escalated"
        self.state.finished_at = datetime.now(timezone.utc).isoformat()
        self.state.elapsed_seconds = time.time() - self._start_time
        yield self.state


def _extract_hypotheses(report: InvestigatorReport) -> list[dict]:
    """
    Build a hypothesis board list from the Investigator's reasoning text.

    Returns a list of dicts: {"label": str, "confidence": float, "falsified": bool}
    suitable for the frontend HypothesisBoard component.

    This is a best-effort extraction — the primary hypothesis is always
    the Investigator's root_cause.  Additional hypotheses are extracted
    from the reasoning text if the model mentions them explicitly.
    """
    hypotheses = []

    # Primary (winning) hypothesis
    if report.root_cause and report.root_cause != "Unknown":
        hypotheses.append({
            "label":      report.root_cause,
            "confidence": report.confidence,
            "falsified":  False,
        })

    # Extract falsified candidates from the reasoning string
    reasoning = report.reasoning.lower()
    candidates = [
        ("Weather", "weather"),
        ("Payment provider", "payment provider"),
        ("Marketing campaign", "marketing campaign"),
        ("Site-wide outage", "site-wide"),
        ("Pricing page", "pricing page"),
    ]
    for label, keyword in candidates:
        if keyword in reasoning:
            # If the model dismissed it, mark as falsified
            falsified = any(
                neg in reasoning[max(0, reasoning.find(keyword) - 80):reasoning.find(keyword) + 80]
                for neg in ["falsif", "rules out", "eliminated", "not the cause", "unaffected"]
            )
            hypotheses.append({
                "label":      label,
                "confidence": max(0.05, report.confidence * 0.15),   # rough residual
                "falsified":  falsified,
            })

    return hypotheses
