# 🛒 First Customer
### Your AI employee. Your toughest customer.

**First Customer** is an autonomous AI business operator designed for solo founders and SMEs. It doesn't just show you a dashboard; it experiences your business as a customer would. It simulates LLM-driven personas navigating a "Digital Twin" of your store, identifies conversion anomalies, investigates root causes using counterfactual reasoning, applies verified fixes with a staged rollout, and re-verifies the outcome — live.

---

## 🌟 The Core Innovation: The Closed Loop

Most business AI agents stop at "I recommend you do X." First Customer completes the entire operational cycle:

1. **Experience** — Customer personas (static or LLM-varied) navigate a pixel-art store, generating real journey data.
2. **Detect** — A deterministic analytics layer (no LLM) flags abandonment spikes against per-segment baselines.
3. **Investigate** — The **Investigator** agent calls read-only tools to compare segments, check recent business changes, and pull journey detail — ruling out red herrings before naming a root cause.
4. **Decide + Act** — The **Operator** agent selects an intervention, enforces business constraints (confidence gate, CSAT floor, margin floor), and applies the fix.
5. **Canary Test** — Before a full rollout, the fix is evaluated on a held-out cohort. A failing canary triggers an automatic rollback — no unproven change ever reaches full rollout.
6. **Verify** — A fresh cohort is simulated post-fix; before/after numbers (conversion, health score, dollar impact) are computed deterministically, not asserted by the model.

---

## 🧠 Multi-Agent Architecture

Three specialized agents, each with a distinct role and tool scope:

| Agent | Role | Tools | Write access |
|---|---|---|---|
| **Customer** | Generates journey narration and outcome per persona | none | none |
| **Investigator** | Diagnoses root cause from evidence | `run_detection`, `get_segment_stats`, `compare_segments`, `get_journey_details`, `get_recent_business_changes` | **read-only** |
| **Operator** | Selects and applies interventions, runs canary, promotes or rolls back | all Investigator tools + `apply_checkout_fix`, `apply_faq_update`, `send_message_to_customers`, `apply_customer_discount`, `evaluate_canary`, `promote_to_full_rollout`, `rollback_intervention`, `escalate_to_human` | **read + write** |

All three run on Google Gemini via the `google-genai` SDK, using automatic function calling — the model calls tools directly, and the SDK handles the round-trip. Model in use: `gemini-flash-latest` for the Investigator/Operator/Customer agents (low temperature, 0.1–0.2, for consistent reasoning), and `gemini-3.5-flash-lite` with a strict JSON `response_schema` for LLM-generated personas and AI-proposed custom scenarios (higher temperature, 0.9, for varied output).

### Deterministic vs. AI — an explicit split

This is a deliberate architecture decision, not an accident, and it's worth stating plainly in Q&A: **anything that needs to be explainable, auditable, or reliable is plain Python. Anything that needs judgment is an LLM call.**

- **Deterministic (`app/business/metrics.py`, `app/business/interventions.py`):** segment stats, anomaly thresholds, confidence scoring, health-score formula, canary pass/fail rules, constraint enforcement (confidence gate ≥ 0.70, CSAT floor ≥ 0.80, margin floor ≥ 0.20). Zero LLM calls. Every number here can be explained in one sentence.
- **AI (`app/agents/*.py`):** hypothesis generation, evidence interpretation, intervention selection, natural-language reasoning.

No LLM ever writes to the database directly. Every write flows: **LLM decision → structured tool call → `validate_intervention()` constraint check → DB mutation → immutable audit log entry** (`app/tools/write_tools.py`, `app/business/interventions.py`).

---

## 📊 Business Health Score

A single 0–100 number, computed deterministically from three weighted components (`app/business/state.py`):

- **Conversion (50%)** — overall conversion rate, normalized between a 50%/95% benchmark band.
- **Reliability (30%)** — starts at 1.0, penalized per flagged anomaly proportional to its confidence and severity.
- **Experience (20%)** — mobile first-time conversion rate specifically, used as a proxy for CX quality since that segment is the most friction-sensitive.

Paired with a plain-English dollar-context string ("Health 57 — estimated $X/month at risk from conversion shortfall") so the number means something to a non-technical founder without decoding a scale.

---

## 🎨 Visual Experience (Digital Twin)

- **Narrative banner** (top) — plain-English story of what the agents are doing, for anyone watching without reading code.
- **Pixel-art world** — customer personas walk between zones (browse → queue → checkout), show emotion via chat bubbles and emoji reactions on success/abandonment, and the AI agent physically moves to the counter to apply a fix.
- **Backend trace panel** (bottom, expandable to fullscreen) — the real tool calls, arguments, and reasoning from the Investigator/Operator, for full behind-the-scenes transparency — not a separate marketing layer, the actual JSON coming back from the agents.

### How the pixel world stays honest

For the three built-in demo scenarios, the world plays a scripted animation — reliable and fast for a live pitch. For **Custom Stress Test**, the world is driven by real backend events, not a script:

1. As the simulator generates each customer journey, `app/simulation/world_events.py` writes granular `WORLD_*` rows to the Supabase `events` table (`CUSTOMER_ENTER`, `CUSTOMER_BROWSE`, `CUSTOMER_ABANDON`, etc.), tagged with the run's `run_id`.
2. The Orchestrator (`app/agents/orchestrator.py`) does the same at each pipeline stage — `emit_anomaly_alert`, `emit_agent_move`, `emit_agent_fix_apply`, `emit_agent_verify`, `emit_incident_resolved` — so the agent's on-screen movement corresponds to its actual investigation stage.
3. The frontend (`useCustomRunWorldEvents.ts`) subscribes to Supabase Realtime on the `events` table, filters for `WORLD_*` rows matching the active `run_id`, and translates each row directly into a `WorldEventBus.emit()` call.

This means a customer visibly abandoning in the pixel world during a Custom Stress Test corresponds to a real row the Investigator later reads — not a proxy animation running in parallel with the real pipeline.

---

## 🛡️ Safety & Auditability

- **Confidence gate** — the Operator will not act if root-cause confidence is below 70%; it escalates to human review instead.
- **Canary-before-rollout** — enforced in the system prompt *and* in the tools themselves (`evaluate_canary` must run before `promote_to_full_rollout` is meaningful); a failing canary auto-rolls-back.
- **Immutable audit log** — every tool call, whether it succeeds, is rejected by a constraint, or errors, writes an `audit_log` event row with the action, arguments, result, and reason (`app/tools/write_tools.py`).
- **Reversibility** — every intervention type is tagged reversible/irreversible in the catalogue (`INTERVENTION_TYPES`); irreversible actions (e.g. `send_customer_message`) are flagged so the Operator only uses them after a fix is confirmed.

---

## 🧪 Custom Stress Test — user-defined scenarios

Beyond the three built-in scenarios, users can define their own stress test and run it against the real agent pipeline:

1. **AI-proposed or manual** — click "Generate scenario with AI" to have Gemini propose a plausible business problem (`/generate-scenario`, schema-constrained JSON), or fill in the fields manually: affected device, affected customer type, abandonment severity.
2. **Registered at runtime** — `register_custom_scenario()` (`app/simulation/scenario_engine.py`) adds the scenario to the registry with a generic parametrized injector, no code deploy needed.
3. **Persona mode choice** — static (fast, deterministic) or LLM-varied (`persona_mode: "llm"` — each persona gets Gemini-generated tone/urgency/complaint-phrasing variation via `app/simulation/llm_personas.py`, rate-limited to respect the free tier).
4. **Real pipeline, not a replay** — `/run-custom` runs the actual simulator, then the real `Orchestrator` — detection, Investigator, Operator, canary, verification — end to end.

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, Python 3.11 (pinned via `runtime.txt` — newer Python versions lack prebuilt wheels for some dependencies on Render), Google Gemini (`google-genai` SDK), Supabase (Postgres + Realtime).
- **Frontend:** Next.js, PixiJS (canvas rendering for the pixel world), Framer Motion, Supabase Realtime client (`@supabase/supabase-js`).
- **Deployment:** Render (backend), Vercel (frontend).

---

## 🚀 Local Setup

### 1. Prerequisites
- Python 3.11
- Node.js 18+
- [Google Gemini API key](https://aistudio.google.com/)
- [Supabase project](https://supabase.com/)

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
GEMINI_API_KEY=your_gemini_key
SUPABASE_URL=your_project_url
SUPABASE_SERVICE_KEY=your_service_role_key
```

```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=your_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

```bash
npm run dev
```

---

## 🎬 Demo Guide

**Scenario A (Hidden Fee):** watch a customer hit a surprise $5 fee and leave angry, the Investigator rule out unrelated causes via segment comparison, the Operator apply the fix at the counter, and a fresh cohort of customers complete successfully.

**Custom Stress Test:**
1. Open the settings panel.
2. Click "Generate scenario with AI" to let Gemini propose a scenario, or fill in the fields manually.
3. Click "Run against Investigator/Operator" — this triggers a live run through the real pipeline, streamed into the pixel world via Supabase Realtime as it happens.

---

## 📁 Key Files

| File | Role |
|---|---|
| `app/business/metrics.py` | Deterministic detection: segment stats, anomaly thresholds, confidence scoring |
| `app/business/interventions.py` | Deterministic intervention layer: constraints, canary evaluation, rollback, audit |
| `app/business/state.py` | Business Health Score computation |
| `app/agents/investigator.py` | Investigator agent — read-only diagnosis |
| `app/agents/operator.py` | Operator agent — intervention selection, canary, rollout |
| `app/agents/customer_agent.py` | LLM-driven customer journey narration |
| `app/agents/orchestrator.py` | State machine tying detection → investigation → action → verification together |
| `app/simulation/scenario_engine.py` | Scenario injection, including runtime-registered custom scenarios |
| `app/simulation/llm_personas.py` | Per-run LLM persona variation |
| `app/simulation/world_events.py` | Writes granular `WORLD_*` events for the live pixel-world visualization |
| `app/tools/write_tools.py` | Operator's write tools — every one audit-logs before mutating |