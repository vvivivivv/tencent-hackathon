"use client";

import { Scenario } from "@/app/types";
import { Shield, AlertTriangle, Info, Play } from "lucide-react";
import { Badge } from "./ui/Badge";
import { severityBadgeVariant } from "@/app/lib/utils";

interface ScenarioCardProps {
  scenario: Scenario;
  onSelect: (key: string) => void;
  isRunning?: boolean;
  isSelected?: boolean;
}

const severityIcon = {
  high: <Shield className="w-4 h-4 text-red-400" />,
  medium: <AlertTriangle className="w-4 h-4 text-amber-400" />,
  low: <Info className="w-4 h-4 text-blue-400" />,
};

export function ScenarioCard({
  scenario,
  onSelect,
  isRunning,
  isSelected,
}: ScenarioCardProps) {
  return (
    <div
      className={`relative rounded-xl border transition-all duration-200 cursor-pointer group ${
        isSelected
          ? "border-blue-500/70 bg-blue-950/20 shadow-[0_0_24px_-6px_rgba(59,130,246,0.4)]"
          : "border-slate-700/50 bg-slate-900/60 hover:border-slate-600/70 hover:bg-slate-800/60"
      }`}
      onClick={() => !isRunning && onSelect(scenario.key)}
    >
      {/* Top accent */}
      <div
        className={`h-1 rounded-t-xl ${
          scenario.severity === "high"
            ? "bg-gradient-to-r from-red-500 to-red-700"
            : scenario.severity === "medium"
            ? "bg-gradient-to-r from-amber-500 to-amber-700"
            : "bg-gradient-to-r from-blue-500 to-blue-700"
        }`}
      />

      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            {severityIcon[scenario.severity]}
            <h3 className="text-base font-semibold text-white leading-tight">
              {scenario.display_name}
            </h3>
          </div>
          <Badge variant={severityBadgeVariant(scenario.severity)}>
            {scenario.severity}
          </Badge>
        </div>

        <p className="text-sm text-slate-400 leading-relaxed mb-4">
          {scenario.description}
        </p>

        {/* Meta */}
        <div className="flex flex-wrap gap-2 mb-4">
          <div className="bg-slate-800/60 rounded-md px-2.5 py-1 text-xs text-slate-400">
            <span className="text-slate-500">Segment: </span>
            <span className="text-slate-200">{scenario.affected_segment}</span>
          </div>
          <div className="bg-slate-800/60 rounded-md px-2.5 py-1 text-xs text-slate-400">
            <span className="text-slate-500">Root Cause: </span>
            <span className="text-slate-200">{scenario.root_cause}</span>
          </div>
        </div>

        <div className="text-xs text-slate-500 mb-4">{scenario.milestone}</div>

        {/* CTA */}
        <button
          disabled={isRunning}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(scenario.key);
          }}
          className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all ${
            isRunning
              ? "bg-slate-800 text-slate-500 cursor-not-allowed"
              : isSelected
              ? "bg-blue-600 text-white hover:bg-blue-500"
              : "bg-slate-800 text-slate-300 hover:bg-slate-700 group-hover:bg-slate-700"
          }`}
        >
          <Play className="w-3.5 h-3.5" />
          {isSelected && isRunning ? "Running…" : "Run Scenario"}
        </button>
      </div>
    </div>
  );
}
