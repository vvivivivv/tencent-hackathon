// frontend/app/api/client.ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface CustomScenarioParams {
  display_name: string;
  root_cause: string;
  target_device: string;
  target_customer_type: string;
  abandonment_rate: number;
  num_personas: number;
  persona_mode: "static" | "llm";
}

async function apiFetch(path: string, options?: RequestInit) {
  const url = new URL(path.startsWith('/') ? path.slice(1) : path, BASE_URL).toString();
  
  const defaultHeaders = {
    "Content-Type": "application/json",
    "Accept": "application/json",
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options?.headers,
      },
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      console.error("Server Error Detail:", errorData);
      throw new Error(errorData.detail || `API Error ${res.status}`);
    }

    return res.json();
  } catch (err) {
    if (err instanceof TypeError && err.message === "Load failed") {
      console.error("CORS or Connection Error: Is the backend running on port 8000?");
    }
    throw err;
  }
}

export const backendApi = {
  generateScenario: (theme?: string) => 
    apiFetch("/generate-scenario", { 
      method: "POST", 
      body: JSON.stringify({ theme: theme || "any" }) 
    }),

  runCustomScenario: (params: CustomScenarioParams) => 
    apiFetch("/run-custom", { 
      method: "POST", 
      body: JSON.stringify(params) 
    }),

  getRunState: (runId: string) => 
    apiFetch(`/runs/${runId}`),
};