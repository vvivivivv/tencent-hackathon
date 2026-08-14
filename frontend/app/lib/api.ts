import {
  OrchestratorState,
  Scenario,
  Journey,
  Incident,
} from "../types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  health: () => apiFetch<{ status: string }>("/health"),

  // Scenarios
  listScenarios: () => apiFetch<Scenario[]>("/scenarios"),

  // Run a scenario — returns a run_id immediately (async job)
  runScenario: (scenario: string) =>
    apiFetch<{ run_id: string; message: string }>("/run", {
      method: "POST",
      body: JSON.stringify({ scenario }),
    }),

  // Poll orchestrator state by run_id
  getRunState: (runId: string) =>
    apiFetch<OrchestratorState>(`/runs/${runId}`),

  // Journeys
  listJourneys: (scenario?: string) =>
    apiFetch<Journey[]>(scenario ? `/journeys?scenario=${scenario}` : "/journeys"),

  // Incidents
  listIncidents: () => apiFetch<Incident[]>("/incidents"),
  getIncident: (id: string) => apiFetch<Incident>(`/incidents/${id}`),
};
