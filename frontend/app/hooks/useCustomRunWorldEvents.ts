"use client";
import { useEffect } from "react";
import { supabase } from "../api/supabase";
import { WorldEventBus } from "../simulation/WorldEvents";
import type { WorldEvent } from "../simulation/WorldEvents";

/**
 * Subscribes to `events` rows tagged WORLD_* for a given run_id, and
 * translates each into a real WorldEventBus.emit(). This is what makes
 * the pixel world for a Custom Stress Test reflect the real backend
 * pipeline instead of a scripted proxy.
 */
export function useCustomRunWorldEvents(runId: string | null) {
  useEffect(() => {
    if (!runId) return;

    const channel = supabase
      .channel(`world-events-${runId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "events" },
        (payload) => {
          const row = payload.new as { type: string; metadata: Record<string, any> };
          if (!row.type?.startsWith("WORLD_")) return;
          if (row.metadata?.run_id !== runId) return;

          const worldType = row.type.replace("WORLD_", "");
          const { run_id, ...rest } = row.metadata;
          WorldEventBus.emit({ type: worldType, ...rest } as WorldEvent);
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [runId]);
}