# 🛒 First Customer
### Your AI employee. Your toughest customer.

**First Customer** is an autonomous AI business operator designed for solo founders and SMEs. It doesn't just show you a dashboard; it experiences your business as a customer would. It simulates LLM-driven personas to navigate a "Digital Twin" of your store, identifies conversion anomalies, investigates root causes using counterfactual reasoning, and applies verified fixes in real-time.

---

## 🌟 The Core Innovation: The Closed Loop
Most business AI agents stop at "I recommend you do X." First Customer completes the entire operational cycle:

1.  **Experience:** LLM-driven personas (Sarah, Alex, Marcus) with distinct goals and devices navigate a cozy pixel-art store.
2.  **Detect:** A deterministic analytics layer identifies abandonment spikes (e.g., a sudden jump from 8% to 45%).
3.  **Investigate:** The **Investigator Agent** uses tools to rule out "red herrings" (like weather or global outages) to find the true cause.
4.  **Fix:** The **Operator Agent** physically moves to the counter in the simulation and patches the business configuration.
5.  **Verify:** New customers are simulated to prove the fix works with hard numbers before closing the incident.

---

## 🎨 Visual Experience (Digital Twin)
- **Narrative Loop:** A top-level horizontal banner that tells the human story of the business status.
- **Implementation Trace:** A terminal-style console at the bottom showing raw agent tool calls and backend logic for full "Behind the Scenes" transparency.
- **Expressive Actors:** Customers show emotions (😠, 🤨, 😊) via chat bubbles and emojis based on their success or frustration at the register.

---

## 🛠️ Tech Stack
- **Backend:** FastAPI (Python 3.13), Google Gemini 2.0 Flash (Reasoning & Generation), Supabase (Postgres & Real-time WebSockets).
- **Frontend:** Next.js 14, PixiJS v8 (High-performance canvas rendering), Framer Motion (UI transitions).
- **Architecture:** Multi-agent orchestration (Customer -> Investigator -> Operator).

---

## 🚀 Local Setup

### 1. Prerequisites
- Python 3.13+
- Node.js 18+
- [Google Gemini API Key](https://aistudio.google.com/)
- [Supabase Project](https://supabase.com/)

### 2. Backend Setup
    Navigate to the backend folder:
    cd backend

    Create and activate a virtual environment:

    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate

    Install dependencies:
    code Bash

    pip install -r requirements.txt

    Create a .env file in the backend/ directory:
    code Env

    GEMINI_API_KEY=your_gemini_key
    SUPABASE_URL=your_project_url
    SUPABASE_SERVICE_KEY=your_service_role_key

    Start the server:
    code Bash

    uvicorn app.main:app --reload --port 8000

### 3. Frontend Setup
    Navigate to the frontend folder:

    cd frontend

    Install dependencies:
    code Bash

    npm install

    Create a .env.local file in the frontend/ directory:
    code Env

    NEXT_PUBLIC_SUPABASE_URL=your_project_url
    NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
    NEXT_PUBLIC_API_URL=http://127.0.0.1:8000

    Start the development server:
    code Bash

    npm run dev

Generated Scenario Demo

    Scenario A (Hidden Fee): Watch as a customer gets angry at a surprise $5 fee. The AI Robot droid flies to the bread aisle to audit prices, moves to the cashier to patch the code, and a new customer completes a successful purchase.

    Custom Stress Test:

        Open the settings panel.

        Click "Generate scenario with AI" to let Gemini propose a unique business problem.

        Click "Run against Investigator/Operator." to trigger a live investigation based on proposed scenarios.

