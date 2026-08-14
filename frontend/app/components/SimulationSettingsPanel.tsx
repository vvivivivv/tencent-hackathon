"use client";
import { useState } from "react";
import { backendApi, type CustomScenarioParams } from "../api/client";

interface Props {
  onClose: () => void;
  onRunStarted: (runId: string) => void;
}

export default function SimulationSettingsPanel({ onClose, onRunStarted }: Props) {
  const [form, setForm] = useState<CustomScenarioParams>({
    display_name: "Custom Stress Test",
    root_cause: "",
    target_device: "all",
    target_customer_type: "all",
    abandonment_rate: 0.5,
    num_personas: 8,
    persona_mode: "static",
  });
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);

  const generateWithAI = async () => {
  setGenerating(true);
  try {
    const suggestion = await backendApi.generateScenario("payment issues");
    setForm(f => ({ 
      ...f, 
      display_name: suggestion.display_name,
      root_cause: suggestion.root_cause,
      target_device: suggestion.target_device,
      target_customer_type: suggestion.target_customer_type,
      abandonment_rate: suggestion.abandonment_rate
    }));
  } catch (error) {
    alert(error);
  } finally {
    setGenerating(false);
  }
};

const run = async () => {
  setRunning(true);
  try {
    // This calls the API we fixed in Step 1
    const res = await backendApi.runCustomScenario(form);
    if (res.run_id) {
      onRunStarted(res.run_id); // This triggers polling in Page.tsx
    }
  } catch (error) {
    alert("Failed to start custom run. Check console for details.");
    console.error(error);
  } finally {
    setRunning(false);
  }
};

  return (
    <div className="fixed inset-0 z-[999] bg-black/80 flex items-center justify-center p-6">
      <div className="w-full max-w-lg bg-[#0a0f1e] border border-white/10 rounded-2xl p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider text-blue-300">Simulation Settings — Custom Stress Test</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white text-lg leading-none">×</button>
        </div>

        <button
          onClick={generateWithAI}
          disabled={generating}
          className="text-xs font-bold uppercase tracking-wide bg-blue-600/20 border border-blue-500/40 text-blue-300 rounded-lg py-2 hover:bg-blue-600/30 disabled:opacity-50"
        >
          {generating ? "Generating..." : "✨ Generate scenario with AI"}
        </button>

        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Scenario name
          <input
            value={form.display_name}
            onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Root cause description
          <textarea
            value={form.root_cause}
            onChange={e => setForm(f => ({ ...f, root_cause: e.target.value }))}
            placeholder="e.g. Confusing refund policy shown only after payment"
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm resize-none h-16"
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Affected device
            <select
              value={form.target_device}
              onChange={e => setForm(f => ({ ...f, target_device: e.target.value as any }))}
              className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-white text-sm"
            >
              <option value="all">All devices</option>
              <option value="mobile">Mobile only</option>
              <option value="desktop">Desktop only</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Affected customer type
            <select
              value={form.target_customer_type}
              onChange={e => setForm(f => ({ ...f, target_customer_type: e.target.value as any }))}
              className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-white text-sm"
            >
              <option value="all">All customers</option>
              <option value="first_time">First-time only</option>
              <option value="returning">Returning only</option>
            </select>
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Abandonment severity: {Math.round(form.abandonment_rate * 100)}%
          <input
            type="range" min={0.1} max={0.95} step={0.05}
            value={form.abandonment_rate}
            onChange={e => setForm(f => ({ ...f, abandonment_rate: parseFloat(e.target.value) }))}
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Customers to simulate: {form.num_personas}
            <input
              type="range" min={4} max={20} step={1}
              value={form.num_personas}
              onChange={e => setForm(f => ({ ...f, num_personas: parseInt(e.target.value) }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            Persona generation
            <select
              value={form.persona_mode}
              onChange={e => setForm(f => ({ ...f, persona_mode: e.target.value as any }))}
              className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-white text-sm"
            >
              <option value="static">Static (fast)</option>
              <option value="llm">LLM-varied (slower, richer)</option>
            </select>
          </label>
        </div>

        <button
          onClick={run}
          disabled={running || !form.root_cause}
          className="mt-2 bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 font-bold uppercase text-xs tracking-wide rounded-lg py-3 hover:bg-emerald-600/30 disabled:opacity-40"
        >
          {running ? "Starting..." : "Run against Investigator/Operator"}
        </button>
        <p className="text-[10px] text-slate-600 leading-relaxed">
          Scenario Backend Investigation
        </p>
      </div>
    </div>
  );
}