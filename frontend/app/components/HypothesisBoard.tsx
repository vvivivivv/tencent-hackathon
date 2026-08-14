"use client";

import { Hypothesis, InvestigatorReport } from "@/app/types";
import { CheckCircle, XCircle } from "lucide-react";

interface HypothesisBoardProps {
  hypotheses: Hypothesis[];
  report: InvestigatorReport | null;
}

export function HypothesisBoard({ hypotheses, report }: HypothesisBoardProps) {
  if (hypotheses.length === 0 && !report) {
    return (
      <p className="text-slate-500 text-sm">Investigator has not run yet.</p>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Hypotheses */}
      {hypotheses.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1">
            Hypotheses Evaluated
          </h4>
          {hypotheses.map((h, i) => (
            <div
              key={i}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all ${
                h.falsified
                  ? "border-slate-700/30 bg-slate-800/20 opacity-60"
                  : "border-emerald-700/40 bg-emerald-900/10"
              }`}
            >
              {h.falsified ? (
                <XCircle className="w-4 h-4 text-slate-600 flex-shrink-0" />
              ) : (
                <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              )}
              <span
                className={`text-sm flex-1 ${
                  h.falsified
                    ? "line-through text-slate-500"
                    : "text-slate-200"
                }`}
              >
                {h.label}
              </span>
              <div className="flex items-center gap-2 flex-shrink-0">
                <div className="w-20 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      h.falsified ? "bg-slate-600" : "bg-emerald-500"
                    }`}
                    style={{ width: `${h.confidence * 100}%` }}
                  />
                </div>
                <span
                  className={`text-xs font-mono w-10 text-right ${
                    h.falsified ? "text-slate-600" : "text-emerald-400"
                  }`}
                >
                  {(h.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Report */}
      {report && (
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 flex flex-col gap-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Root Cause</p>
              <p className="text-base font-semibold text-white">{report.root_cause}</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <p className="text-xs text-slate-500">Confidence</p>
              <span className="text-lg font-bold text-emerald-400">
                {(report.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                report.confidence >= 0.8
                  ? "bg-emerald-500"
                  : report.confidence >= 0.6
                  ? "bg-amber-500"
                  : "bg-red-500"
              }`}
              style={{ width: `${report.confidence * 100}%` }}
            />
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-slate-500 text-xs">Affected Segment</p>
              <p className="text-slate-200 font-medium mt-0.5">{report.affected_segment}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">Recommended Fix</p>
              <p className="text-slate-200 font-medium mt-0.5">{report.recommended_intervention}</p>
            </div>
          </div>

          {report.reasoning && (
            <div>
              <p className="text-xs text-slate-500 mb-1">Reasoning</p>
              <p className="text-sm text-slate-400 leading-relaxed">{report.reasoning}</p>
            </div>
          )}

          {report.needs_human_review && (
            <div className="flex items-center gap-2 bg-amber-900/20 border border-amber-700/40 rounded-lg px-3 py-2">
              <span className="text-amber-400 text-xs font-medium">⚠ Human review required</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
