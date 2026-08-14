"use client";

import { OperatorReport } from "@/app/types";
import { CheckCircle, XCircle, RotateCcw, ArrowRight } from "lucide-react";
import { Badge } from "./ui/Badge";

interface OperatorPanelProps {
  report: OperatorReport | null;
}

const outcomeConfig = {
  resolved: { label: "Resolved", variant: "success" as const, icon: CheckCircle },
  rolled_back: { label: "Rolled Back", variant: "warning" as const, icon: RotateCcw },
  escalated: { label: "Escalated", variant: "warning" as const, icon: ArrowRight },
  no_action: { label: "No Action", variant: "muted" as const, icon: XCircle },
};

export function OperatorPanel({ report }: OperatorPanelProps) {
  if (!report) {
    return <p className="text-slate-500 text-sm">Operator has not acted yet.</p>;
  }

  const cfg = outcomeConfig[report.outcome] ?? outcomeConfig.no_action;
  const Icon = cfg.icon;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Icon className={`w-4 h-4 ${report.outcome === "resolved" ? "text-emerald-400" : "text-amber-400"}`} />
          <span className="text-base font-semibold text-white">
            {cfg.label}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={cfg.variant}>{cfg.label}</Badge>
          {report.canary_passed ? (
            <Badge variant="success">Canary ✓</Badge>
          ) : (
            <Badge variant="danger">Canary ✗</Badge>
          )}
        </div>
      </div>

      {/* Intervention */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-slate-800/50 rounded-lg px-3 py-2.5">
          <p className="text-slate-500 text-xs mb-0.5">Intervention Type</p>
          <p className="text-slate-200 font-medium">{report.intervention_type || "—"}</p>
        </div>
        <div className="bg-slate-800/50 rounded-lg px-3 py-2.5">
          <p className="text-slate-500 text-xs mb-0.5">Canary Result</p>
          <p className={`font-medium ${report.canary_passed ? "text-emerald-400" : "text-red-400"}`}>
            {report.canary_passed ? "Passed" : "Failed — Rolled back"}
          </p>
        </div>
      </div>

      {/* Actions Timeline */}
      {report.actions_taken?.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Actions Timeline</p>
          <ol className="flex flex-col gap-1.5">
            {report.actions_taken.map((action, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="w-5 h-5 rounded-full bg-slate-700 text-slate-400 text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <span className="text-slate-300">{action}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Reasoning */}
      {report.reasoning && (
        <div>
          <p className="text-xs text-slate-500 mb-1">Operator Reasoning</p>
          <p className="text-sm text-slate-400 leading-relaxed">{report.reasoning}</p>
        </div>
      )}

      {/* Escalation */}
      {report.escalation_reason && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-3 py-2">
          <p className="text-xs text-amber-400 font-medium">Escalation Reason</p>
          <p className="text-sm text-amber-300 mt-0.5">{report.escalation_reason}</p>
        </div>
      )}
    </div>
  );
}
