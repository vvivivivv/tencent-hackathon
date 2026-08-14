
"use client";

interface Props {
  abandonment: number;
  conversion: number;
  resolved?: boolean;
}

export default function MetricsBar({ abandonment, conversion, resolved }: Props) {
  return (
    <div style={{
      display: "flex",
      gap: 24,
      alignItems: "center",
      padding: "8px 16px",
      background: "rgba(5,5,20,0.95)",
      border: "1px solid rgba(0,170,255,0.15)",
      borderRadius: 8,
      fontFamily: "monospace",
    }}>
      <div style={{ fontSize: 10, color: "#555", letterSpacing: 1 }}>LIVE METRICS</div>

      {/* Abandonment */}
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
          <span style={{ fontSize: 10, color: "#aaa" }}>Checkout Abandonment</span>
          <span style={{ fontSize: 11, color: abandonment > 20 ? "#ff6b6b" : "#4ade80", fontWeight: "bold" }}>
            {abandonment}%
          </span>
        </div>
        <div style={{ height: 5, background: "#111", borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            height: "100%", borderRadius: 3,
            width: `${abandonment}%`,
            background: abandonment > 20 ? "#ef4444" : "#4ade80",
            transition: "width 1.5s ease, background 1s ease",
          }} />
        </div>
      </div>

      <div style={{ width: 1, height: 28, background: "#1a2a3a" }} />

      {/* Conversion */}
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
          <span style={{ fontSize: 10, color: "#aaa" }}>Checkout Conversion</span>
          <span style={{ fontSize: 11, color: conversion > 80 ? "#4ade80" : "#fb923c", fontWeight: "bold" }}>
            {conversion}%
          </span>
        </div>
        <div style={{ height: 5, background: "#111", borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            height: "100%", borderRadius: 3,
            width: `${conversion}%`,
            background: conversion > 80 ? "#4ade80" : "#fb923c",
            transition: "width 1.5s ease, background 1s ease",
          }} />
        </div>
      </div>

      {resolved && (
        <div style={{
          marginLeft: 8,
          fontSize: 10, fontWeight: "bold", letterSpacing: 1,
          color: "#00ff88", border: "1px solid #00ff88",
          borderRadius: 4, padding: "3px 8px",
          boxShadow: "0 0 8px rgba(0,255,136,0.3)",
        }}>
          ✓ RESOLVED
        </div>
      )}
    </div>
  );
}
