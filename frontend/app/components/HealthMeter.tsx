"use client";

import { OrchestratorState } from "@/app/types";
import { formatMoney } from "@/app/lib/utils";
import { TrendingUp, TrendingDown, DollarSign } from "lucide-react";

interface HealthMeterProps {
  state: OrchestratorState;
}

function GaugeArc({
  value,
  color,
  label,
}: {
  value: number;
  color: string;
  label: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const circumference = 2 * Math.PI * 54;
  const dashOffset = circumference * (1 - clamped / 100);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-32 h-32">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          {/* track */}
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke="#1e293b"
            strokeWidth="10"
          />
          {/* fill */}
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-white">{Math.round(clamped)}</span>
          <span className="text-xs text-slate-400">/ 100</span>
        </div>
      </div>
      <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
        {label}
      </span>
    </div>
  );
}

export function HealthMeter({ state }: HealthMeterProps) {
  const { health_before, health_after, revenue_impact_monthly } = state;

  const beforeColor =
    (health_before ?? 0) >= 70
      ? "#10b981"
      : (health_before ?? 0) >= 40
      ? "#f59e0b"
      : "#ef4444";

  const afterColor =
    (health_after ?? 0) >= 70
      ? "#10b981"
      : (health_after ?? 0) >= 40
      ? "#f59e0b"
      : "#ef4444";

  const delta =
    health_before != null && health_after != null
      ? health_after - health_before
      : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-center gap-8 flex-wrap">
        {health_before != null && (
          <GaugeArc value={health_before} color={beforeColor} label="Before" />
        )}
        {health_after != null && (
          <GaugeArc value={health_after} color={afterColor} label="After" />
        )}
        {health_before == null && health_after == null && (
          <div className="text-slate-500 text-sm">Awaiting metrics…</div>
        )}
      </div>

      {delta != null && (
        <div className="flex items-center justify-center gap-2">
          {delta >= 0 ? (
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          ) : (
            <TrendingDown className="w-4 h-4 text-red-400" />
          )}
          <span
            className={`text-sm font-semibold ${
              delta >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(1)} pts
          </span>
          <span className="text-xs text-slate-500">health improvement</span>
        </div>
      )}

      {revenue_impact_monthly != null && (
        <div className="flex items-center justify-center gap-2 bg-slate-800/60 rounded-lg px-4 py-2">
          <DollarSign className="w-4 h-4 text-amber-400" />
          <span className="text-sm text-slate-300">
            Revenue at risk:{" "}
            <span className="text-amber-300 font-semibold">
              {formatMoney(revenue_impact_monthly)}
            </span>
            <span className="text-slate-500">/mo</span>
          </span>
        </div>
      )}
    </div>
  );
}
