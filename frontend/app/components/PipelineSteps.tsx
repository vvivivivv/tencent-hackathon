"use client";

import { Stage } from "@/app/types";
import { stageLabel } from "@/app/lib/utils";
import { CheckCircle, Circle, Loader2, XCircle, AlertTriangle } from "lucide-react";

const STAGES: Stage[] = [
  "DISCOVER",
  "OBSERVE",
  "DETECT",
  "INVESTIGATE",
  "PLAN",
  "ACT_CANARY",
  "CANARY_CHECK",
  "ACT_FULL",
  "VERIFY",
  "CLOSE",
];

function stageIndex(stage: Stage): number {
  const idx = STAGES.indexOf(stage);
  return idx === -1 ? 0 : idx;
}

interface PipelineStepsProps {
  currentStage: Stage;
  outcome?: string | null;
}

export function PipelineSteps({ currentStage, outcome }: PipelineStepsProps) {
  const currentIdx = stageIndex(currentStage);
  const isError = currentStage === "ERROR";
  const isEscalated = currentStage === "ESCALATED";
  const isDone = currentStage === "CLOSE";

  return (
    <div className="flex flex-col gap-0">
      {STAGES.map((stage, idx) => {
        const isDoneStage = isDone
          ? true
          : currentIdx > idx;
        const isCurrent = currentStage === stage;
        const isPending = !isDoneStage && !isCurrent;

        let icon: React.ReactNode;
        if (isError && isCurrent) {
          icon = <XCircle className="w-4 h-4 text-red-400" />;
        } else if (isEscalated && idx >= currentIdx) {
          icon = <AlertTriangle className="w-4 h-4 text-amber-400" />;
        } else if (isDoneStage) {
          icon = <CheckCircle className="w-4 h-4 text-emerald-400" />;
        } else if (isCurrent) {
          icon = <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
        } else {
          icon = <Circle className="w-4 h-4 text-slate-600" />;
        }

        return (
          <div key={stage} className="flex items-start gap-3">
            {/* vertical connector + icon */}
            <div className="flex flex-col items-center">
              <div className="mt-0.5">{icon}</div>
              {idx < STAGES.length - 1 && (
                <div
                  className={`w-0.5 flex-1 min-h-[20px] ${
                    isDoneStage ? "bg-emerald-700/50" : "bg-slate-700/40"
                  }`}
                />
              )}
            </div>

            {/* label */}
            <div className="pb-4">
              <p
                className={`text-sm font-medium ${
                  isCurrent
                    ? "text-blue-300"
                    : isDoneStage
                    ? "text-emerald-400"
                    : isPending
                    ? "text-slate-500"
                    : "text-slate-400"
                }`}
              >
                {stageLabel(stage)}
              </p>
              {isCurrent && !isDone && (
                <p className="text-xs text-slate-500 mt-0.5">Running…</p>
              )}
              {isDoneStage && stage === "CLOSE" && outcome && (
                <p className="text-xs text-emerald-500 mt-0.5">{outcome}</p>
              )}
            </div>
          </div>
        );
      })}

      {(isEscalated || isError) && (
        <div className="flex items-start gap-3">
          <div className="mt-0.5">
            {isError ? (
              <XCircle className="w-4 h-4 text-red-400" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-amber-400" />
            )}
          </div>
          <p className="text-sm font-medium text-amber-300">
            {isError ? "Error" : "Escalated to Human"}
          </p>
        </div>
      )}
    </div>
  );
}
