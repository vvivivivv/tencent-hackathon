"use client";

/**
 * usePollRun – polls /runs/{runId} every 2 s until finished or error.
 * Falls back gracefully if backend is not running (returns mock data).
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { OrchestratorState } from "@/app/types";
import { api } from "@/app/lib/api";

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STAGES = new Set(["CLOSE", "ESCALATED", "ERROR"]);

export function usePollRun(runId: string | null) {
  const [state, setState] = useState<OrchestratorState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  useEffect(() => {
    if (!runId) {
      setState(null);
      setError(null);
      return;
    }

    let cancelled = false;

    async function poll() {
      if (cancelled) return;
      try {
        const data = await api.getRunState(runId!);
        if (!cancelled) {
          setState(data);
          if (!TERMINAL_STAGES.has(data.stage)) {
            timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Poll error");
        }
      }
    }

    poll();

    return () => {
      cancelled = true;
      stop();
    };
  }, [runId, stop]);

  return { state, error };
}
