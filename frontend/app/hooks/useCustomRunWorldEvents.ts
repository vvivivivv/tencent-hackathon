"use client";

import { useEffect } from "react";
import { supabase } from "../api/supabase";
import { WorldEventBus } from "../simulation/WorldEvents";
import type { WorldEvent } from "../simulation/WorldEvents";

function emitWorldEvent(
  row: {
    type: string;
    metadata: Record<string, any>;
  },
  runId: string
) {
  console.log("[WORLD EVENT RECEIVED]", row);

  if (!row.type?.startsWith("WORLD_")) return;
  if (row.metadata?.run_id !== runId) return;

  const worldType = row.type.replace("WORLD_", "");
  const { run_id, ...rest } = row.metadata;

  console.log("[WORLD EVENT EMIT]", {
    type: worldType,
    ...rest,
  });

  WorldEventBus.emit({
    type: worldType,
    ...rest,
  } as WorldEvent);
}

export function useCustomRunWorldEvents(runId: string | null) {
  useEffect(() => {
    if (!runId) return;

    let cancelled = false;

    console.log("[WORLD EVENTS] subscribing to", runId);

    const channel = supabase
      .channel(`world-events-${runId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "events",
        },
        (payload) => {
          if (cancelled) return;

          emitWorldEvent(
            payload.new as {
              type: string;
              metadata: Record<string, any>;
            },
            runId
          );
        }
      )
      .subscribe(async (status) => {
        console.log("[WORLD EVENTS] subscription:", status);

        if (status !== "SUBSCRIBED" || cancelled) {
          return;
        }

        console.log("[WORLD EVENTS] replaying existing events");

        const { data, error } = await supabase
          .from("events")
          .select("type, metadata")
          .eq("metadata->>run_id", runId)
          .like("type", "WORLD_%")
          .order("created_at", { ascending: true });

        if (error) {
          console.error(
            "[WORLD EVENTS] replay failed:",
            error
          );
          return;
        }

        console.log(
          `[WORLD EVENTS] replaying ${data?.length ?? 0} events`
        );

        for (const row of data ?? []) {
          if (cancelled) return;

          emitWorldEvent(
            row as {
              type: string;
              metadata: Record<string, any>;
            },
            runId
          );
        }
      });

    return () => {
      cancelled = true;

      console.log(
        "[WORLD EVENTS] unsubscribing from",
        runId
      );

      supabase.removeChannel(channel);
    };
  }, [runId]);
}