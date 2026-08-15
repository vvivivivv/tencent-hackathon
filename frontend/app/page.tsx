"use client";
import { Suspense, useState, useCallback, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { runScenario, stopScenario, SCENARIO_META } from "./simulation/scenarios/scenarioEvents";
import { WorldEventBus } from "./simulation/WorldEvents";
import type { StoreType, AgentLogEntry } from "./simulation/WorldEvents";
import type { ScenarioId } from "./simulation/scenarios/scenarioEvents";
import { backendApi } from "./api/client";
import MetricsBar from "./components/MetricsBar";
import AgentLogPanel from "./components/AgentLogPanel";
import { DISPLAY_MAX_W, DISPLAY_MAX_H } from "./simulation/entities/WorldLayout";

import SimulationSettingsPanel from "./components/SimulationSettingsPanel"; 
import { useCustomRunWorldEvents } from "./hooks/useCustomRunWorldEvents";

const PixiWorld = dynamic(() => import("./components/PixiWorld"), { ssr: false });

function PageContent() {
  const searchParams = useSearchParams();
  const debug = searchParams?.get("debug") === "1";

  const [activeScenario, setActiveScenario] = useState<ScenarioId | "custom" | null>(null);
  const [logEntries, setLogEntries] = useState<AgentLogEntry[]>([]);
  const [storeType, setStoreType] = useState<StoreType>("bakery");
  const [metrics, setMetrics] = useState({ abandonment: 8, conversion: 92 });
  const [resolved, setResolved] = useState(false);
  const [progress, setProgress] = useState(0);
  const [traceFullscreen, setTraceFullscreen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);

  const techLogRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const traceScrollRef = useRef<HTMLDivElement>(null);
  const customPollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useCustomRunWorldEvents(currentRunId);

  useEffect(() => {
    const unsub = WorldEventBus.on(event => {
      if (event.type === "SET_STORE_TYPE") setStoreType(event.storeType);
      if (event.type === "METRICS_UPDATE") setMetrics({ abandonment: event.abandonment, conversion: event.conversion });
      if (event.type === "INCIDENT_RESOLVED") { setResolved(true); setProgress(100); }
    });
    return () => { unsub(); stopScenario(); };
  }, []);

  const handleAgentLog = useCallback((entry: Omit<AgentLogEntry, "id" | "time">) => {
    const newEntry: AgentLogEntry = { 
        ...entry, 
        id: `log-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, 
        time: new Date().toLocaleTimeString() 
    };
    setLogEntries(prev => [...prev, newEntry]);
    setProgress(p => Math.min(p + 8, 98));
    WorldEventBus.emit({ type: "AGENT_SPEAK", text: entry.narrative });
  }, []);

  useEffect(() => {
    if (traceScrollRef.current) {
        traceScrollRef.current.scrollTop = traceScrollRef.current.scrollHeight;
    }
  }, [logEntries]);

  const onStart = (id: ScenarioId) => {
    onStop();
    setActiveScenario(id);
    runScenario(id, handleAgentLog);
  };

  const onStop = () => {
    stopScenario();
    if (customPollRef.current) clearTimeout(customPollRef.current);
    setCurrentRunId(null);
    setActiveScenario(null);
    setProgress(0);
    setResolved(false);
    setLogEntries([]);
    WorldEventBus.emit({ type: "RESET_WORLD" });
  };

  const onCustomRunStarted = (runId: string) => {
    onStop();
    setActiveScenario("custom");
    setCurrentRunId(runId);
    setShowSettings(false);

    const seenStages = new Set<string>();
    const poll = async () => {
      try {
        const state = await backendApi.getRunState(runId);
        setProgress(p => Math.min(p + 5, 96));

        if (!seenStages.has(state.stage)) {
          seenStages.add(state.stage);

          if (state.stage === "ERROR") {
            const raw = state.error || "";
            const isQuota = raw.includes("429") || raw.includes("RESOURCE_EXHAUSTED") || raw.toLowerCase().includes("quota");
            handleAgentLog({
              type: "INFO",
              title: isQuota ? "Gemini quota exceeded" : "Run failed",
              narrative: isQuota
                ? "The Gemini API's free-tier daily limit (20 requests/day for this model) has been reached. Wait for the quota to reset, or switch to a different API key."
                : "The pipeline hit an unexpected error and stopped.",
              technical: raw || "No error detail was returned by the backend.",
            });
          } else {
            handleAgentLog({
              type: ["INVESTIGATE", "ROOT_CAUSE"].includes(state.stage) ? "INVESTIGATE" : "INFO",
              title: `Pipeline: ${state.stage}`,
              narrative: state.detection?.summary || `System transitioned to ${state.stage}.`,
              technical: JSON.stringify({ investigator: state.investigator_report, operator: state.operator_report }, null, 2),
            });
          }
        }

        if (["CLOSE", "ESCALATED", "ERROR"].includes(state.stage)) {
          setResolved(state.stage !== "ERROR");
          setProgress(100);
          return;
        }
        customPollRef.current = setTimeout(poll, 2500);
      } catch (e) { console.error(e); }
    };
    poll();
  };

  return (
    <div className="flex flex-col h-screen bg-[#020408] text-[#e2e8f0] font-mono overflow-hidden">
      <div className="h-16 flex-shrink-0 bg-slate-900/40 border-b border-white/5 flex items-center px-6 overflow-hidden">
        <AgentLogPanel entries={logEntries} horizontal={true} onEntryClick={(e) => techLogRefs.current[e.id]?.scrollIntoView({ behavior: "smooth", block: "center" })} />
      </div>

      <div className="flex-1 min-h-0 flex overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center bg-gradient-to-b from-transparent to-black/40 scrollbar-thin">
           <div className="flex flex-col gap-4">
                {activeScenario && (
                    <div className="h-1.5 bg-white/10 rounded-full overflow-hidden" style={{ width: `${DISPLAY_MAX_W}px` }}>
                        <div className="h-full bg-blue-500 transition-all duration-1000" style={{ width: `${progress}%` }} />
                    </div>
                )}
                <div className="border border-white/10 rounded-2xl bg-black shadow-2xl overflow-hidden flex-shrink-0" style={{ width: `${DISPLAY_MAX_W}px`, height: `${DISPLAY_MAX_H}px` }}>
                    <PixiWorld storeType={storeType} debug={debug} />
                </div>
                <div className="flex gap-4 items-center bg-slate-900/30 p-3 rounded-2xl border border-white/5 shadow-lg" style={{ width: `${DISPLAY_MAX_W}px` }}>
                    <div className="flex-1">
                        <MetricsBar abandonment={metrics.abandonment} conversion={metrics.conversion} resolved={resolved} />
                    </div>
                    {activeScenario && (
                        <button onClick={onStop} className="h-12 px-8 bg-red-500/10 border border-red-500/40 text-red-500 rounded-xl text-[10px] font-bold hover:bg-red-500 hover:text-white transition-all">STOP SIMULATION</button>
                    )}
                </div>
           </div>
        </div>

        <div className="w-80 flex-shrink-0 border-l border-white/5 bg-[#05070a] p-6 flex flex-col gap-6 overflow-y-auto scrollbar-hide">
          <h3 className="text-[10px] text-blue-500 font-bold uppercase tracking-[0.2em] opacity-80">Demo Scenarios</h3>
          <div className="flex flex-col gap-3">
              {Object.values(SCENARIO_META).map((sc) => (
                  <button key={sc.id} onClick={() => onStart(sc.id)} className={`p-4 rounded-xl border text-left transition-all ${activeScenario === sc.id ? "border-blue-500 bg-blue-500/10 shadow-lg shadow-blue-500/10" : "border-white/5 bg-white/[0.02] hover:bg-white/[0.05]"}`}>
                      <div className="text-[11px] font-bold text-white uppercase">{sc.storeEmoji} {sc.title}</div>
                      <p className="text-[9px] text-slate-500 mt-1 leading-tight">{sc.problem}</p>
                  </button>
              ))}
              <button onClick={() => setShowSettings(true)} className={`p-4 rounded-xl border-2 border-dashed mt-4 transition-all ${activeScenario === "custom" ? "border-emerald-500 bg-emerald-500/10" : "border-white/10 bg-white/[0.01] hover:border-white/20"}`}>
                  <div className="text-[11px] font-bold text-emerald-400 uppercase tracking-tight">⚙️ Custom Stress Test</div>
                  <div className="text-[9px] text-slate-600">Manual agent pipeline config.</div>
              </button>
          </div>
        </div>
      </div>

      <div className={traceFullscreen ? "fixed inset-0 z-[999] bg-[#020408] flex flex-col min-h-0" : "h-54 flex-shrink-0 border-t border-white/10 bg-black flex flex-col min-h-0"}>
        <div className="flex-shrink-0 px-6 py-2 border-b border-white/5 flex items-center justify-between bg-slate-900/20">
          <span className="text-[10px] font-bold uppercase tracking-widest text-blue-400">Agent Intelligence Trace</span>
          <button onClick={() => setTraceFullscreen(!traceFullscreen)} className="text-[9px] text-slate-500 hover:text-white uppercase tracking-widest underline underline-offset-8 transition-all">{traceFullscreen ? "Minimize" : "Expand Full Log"}</button>
        </div>
        <div ref={traceScrollRef} className="flex-1 min-h-0 overflow-y-auto p-6 space-y-6 scrollbar-thin">
          {logEntries.map(e => (
            <div key={e.id} ref={el => { techLogRefs.current[e.id] = el; }} className="border-l border-white/10 pl-6 group">
              <div className="flex items-center gap-4 text-[9px] mb-2">
                <span className="text-emerald-500 font-bold">[{e.type}]</span>
                <span className="text-slate-600 font-mono tracking-tighter">{e.time}</span>
              </div>
              <h4 className="text-white text-xs font-bold uppercase mb-1">{e.title}</h4>
              <p className="text-blue-200/50 text-[11px] italic mb-3 leading-relaxed">{e.narrative}</p>
              <pre className="bg-slate-900/50 p-4 rounded-lg border border-white/5 text-[10px] text-emerald-400/80 overflow-x-auto whitespace-pre-wrap font-mono shadow-inner">{e.technical}</pre>
            </div>
          ))}
          {logEntries.length === 0 && <div className="text-slate-800 text-[10px] italic text-center py-10 uppercase tracking-[0.3em] opacity-40">System Listening for Backend Signals...</div>}
        </div>
      </div>

      {showSettings && (
        <SimulationSettingsPanel onClose={() => setShowSettings(false)} onRunStarted={onCustomRunStarted} />
      )}
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <PageContent />
    </Suspense>
  );
}