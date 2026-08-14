"use client";

import { Journey } from "@/app/types";
import { Badge } from "./ui/Badge";
import { User, Clock, CheckCircle, XCircle } from "lucide-react";

interface JourneyListProps {
  journeys: Journey[];
}

export function JourneyList({ journeys }: JourneyListProps) {
  if (journeys.length === 0) {
    return <p className="text-slate-500 text-sm">No journeys simulated yet.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {journeys.map((j) => (
        <div
          key={j.id}
          className="flex items-start gap-3 bg-slate-800/40 border border-slate-700/40 rounded-lg px-3 py-3"
        >
          {/* Icon */}
          <div
            className={`mt-0.5 flex-shrink-0 ${
              j.result === "completed" ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {j.result === "completed" ? (
              <CheckCircle className="w-4 h-4" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {j.customer && (
                <div className="flex items-center gap-1 text-sm text-slate-300">
                  <User className="w-3 h-3 text-slate-500" />
                  <span className="font-medium">{j.customer.name}</span>
                  <span className="text-slate-500">·</span>
                  <span className="text-slate-500 text-xs">{j.customer.device}</span>
                  <span className="text-slate-500">·</span>
                  <span className="text-slate-500 text-xs">{j.customer.customer_type}</span>
                </div>
              )}
              <Badge variant={j.result === "completed" ? "success" : "danger"}>
                {j.result}
              </Badge>
              <Badge variant="muted">{j.goal}</Badge>
            </div>

            {/* Steps */}
            {j.steps && j.steps.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {j.steps.map((step, i) => (
                  <span
                    key={i}
                    className="text-xs bg-slate-700/60 text-slate-400 px-1.5 py-0.5 rounded"
                  >
                    {step}
                  </span>
                ))}
              </div>
            )}

            <div className="flex items-center gap-1 mt-1 text-xs text-slate-600">
              <Clock className="w-3 h-3" />
              <span>{j.duration_seconds}s</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
