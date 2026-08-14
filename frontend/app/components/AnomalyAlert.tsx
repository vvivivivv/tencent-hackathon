"use client";

import { DetectionResult } from "@/app/types";
import { formatPct, severityBadgeVariant } from "@/app/lib/utils";
import { Badge } from "./ui/Badge";
import { AlertTriangle, TrendingUp } from "lucide-react";

interface AnomalyAlertProps {
  detection: DetectionResult;
}

export function AnomalyAlert({ detection }: AnomalyAlertProps) {
  if (!detection.has_anomaly) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-900/20 border border-emerald-700/40">
        <span className="text-emerald-400 text-sm font-medium">✓ No anomaly detected</span>
      </div>
    );
  }

  const { primary_anomaly } = detection;

  return (
    <div className="flex flex-col gap-3">
      {/* Banner */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-950/30 border border-red-700/40">
        <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
        <div>
          <p className="text-red-300 text-sm font-medium">Anomaly Detected</p>
          <p className="text-red-400/80 text-xs mt-0.5">{detection.summary}</p>
        </div>
      </div>

      {/* Primary anomaly */}
      {primary_anomaly && (
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-white">Primary Anomaly</span>
            <Badge variant={severityBadgeVariant(primary_anomaly.severity)}>
              {primary_anomaly.severity}
            </Badge>
          </div>

          <p className="text-sm text-slate-400 mb-3 font-medium">{primary_anomaly.segment}</p>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-slate-900/40 rounded-lg px-2 py-2">
              <p className="text-xs text-slate-500">Current</p>
              <p className="text-lg font-bold text-red-400">
                {formatPct(primary_anomaly.current_rate)}
              </p>
            </div>
            <div className="bg-slate-900/40 rounded-lg px-2 py-2">
              <p className="text-xs text-slate-500">Baseline</p>
              <p className="text-lg font-bold text-slate-400">
                {formatPct(primary_anomaly.baseline_rate)}
              </p>
            </div>
            <div className="bg-slate-900/40 rounded-lg px-2 py-2">
              <p className="text-xs text-slate-500">Delta</p>
              <div className="flex items-center justify-center gap-1">
                <TrendingUp className="w-3.5 h-3.5 text-red-400" />
                <p className="text-lg font-bold text-red-400">
                  +{formatPct(primary_anomaly.diff)}
                </p>
              </div>
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
            <span>Sample size: {primary_anomaly.sample_size}</span>
            <span>Confidence: {(primary_anomaly.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
