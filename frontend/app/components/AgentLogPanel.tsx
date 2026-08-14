// components/AgentLogPanel.tsx

"use client";

import { useEffect, useRef } from "react";
import type { AgentLogEntry } from "../simulation/WorldEvents";

interface Props {
  entries: AgentLogEntry[];
  onEntryClick?: (entry: AgentLogEntry) => void;
  horizontal?: boolean;
}

const TYPE_STYLES: Record<AgentLogEntry["type"], { color: string; bg: string; label: string }> = {
  DETECT:      { color: "#ff6b6b", bg: "rgba(255,60,60,0.12)",   label: "DETECT" },
  ANALYZE:     { color: "#60a5fa", bg: "rgba(60,120,255,0.10)",  label: "ANALYZE" },
  PATTERN:     { color: "#f59e0b", bg: "rgba(245,158,11,0.12)",  label: "PATTERN" },
  INVESTIGATE: { color: "#a78bfa", bg: "rgba(139,92,246,0.12)",  label: "INVEST." },
  FOUND:       { color: "#fb923c", bg: "rgba(251,146,60,0.12)",  label: "FOUND" },
  ROOT_CAUSE:  { color: "#ef4444", bg: "rgba(239,68,68,0.15)",   label: "ROOT CAUSE" },
  PLAN:        { color: "#38bdf8", bg: "rgba(56,189,248,0.10)",  label: "PLAN" },
  ACTION:      { color: "#34d399", bg: "rgba(52,211,153,0.12)",  label: "ACTION" },
  TOOL:        { color: "#a3e635", bg: "rgba(163,230,53,0.10)",  label: "TOOL CALL" },
  SUCCESS:     { color: "#4ade80", bg: "rgba(74,222,128,0.15)",  label: "SUCCESS" },
  VERIFY:      { color: "#22d3ee", bg: "rgba(34,211,238,0.10)",  label: "VERIFY" },
  RESULT:      { color: "#86efac", bg: "rgba(134,239,172,0.10)", label: "RESULT" },
  RESOLVED:    { color: "#00ff88", bg: "rgba(0,255,136,0.15)",   label: "RESOLVED" },
  INFO:        { color: "#94a3b8", bg: "rgba(148,163,184,0.08)", label: "INFO" },
};

export default function AgentLogPanel({ entries, onEntryClick, horizontal }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      // If horizontal, scroll right. If vertical, scroll down.
      if (horizontal) {
        scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
      } else {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }
  }, [entries, horizontal]);

  return (
    <div style={{
      display: "flex",
      flexDirection: horizontal ? "row" : "column", // Dynamic direction
      height: "100%",
      width: "100%",
      background: "transparent",
      overflow: "hidden",
      alignItems: "center",
    }}>
      {/* Label - Fixed on left in horizontal mode */}
      <div style={{
        padding: "0 20px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexShrink: 0,
        borderRight: horizontal ? "1px solid rgba(255,255,255,0.1)" : "none",
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: "50%",
          background: entries.length > 0 ? "#00ff88" : "#334",
          boxShadow: entries.length > 0 ? "0 0 6px #00ff88" : "none",
        }} />
        <span style={{ color: "#00aaff", fontFamily: "monospace", fontSize: 10, fontWeight: "bold", letterSpacing: 2 }}>
          LOG
        </span>
      </div>

      {/* Entries Wrapper */}
      <div
        ref={scrollRef}
        style={{
          display: "flex",
          flexDirection: horizontal ? "row" : "column",
          flex: 1,
          overflowX: horizontal ? "auto" : "hidden",
          overflowY: horizontal ? "hidden" : "auto",
          gap: horizontal ? 12 : 2,
          padding: horizontal ? "0 20px" : "10px 0",
          scrollbarWidth: "none",
        }}
      >
        {entries.map(entry => {
          const st = TYPE_STYLES[entry.type];
          return (
            <div
              key={entry.id}
              onClick={() => onEntryClick?.(entry)}
              style={{
                flexShrink: 0,
                padding: "8px 12px",
                background: "rgba(255,255,255,0.03)",
                border: `1px solid ${entry.highlight ? st.color : 'rgba(255,255,255,0.05)'}`,
                borderRadius: 6,
                minWidth: horizontal ? 240 : 'auto',
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 9, color: st.color, fontWeight: "bold" }}>{st.label}</span>
                <span style={{ fontSize: 11, color: "#fff" }}>{entry.title}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}