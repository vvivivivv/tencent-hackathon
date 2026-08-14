"use client";

import { SegmentStat } from "@/app/types";
import { formatPct } from "@/app/lib/utils";

interface SegmentTableProps {
  segments: Record<string, SegmentStat>;
  primarySegment?: string | null;
}

const SEGMENT_LABELS: Record<string, string> = {
  mobile_first_time: "Mobile · First-Time",
  mobile_returning: "Mobile · Returning",
  desktop_first_time: "Desktop · First-Time",
  desktop_returning: "Desktop · Returning",
};

export function SegmentTable({ segments, primarySegment }: SegmentTableProps) {
  const rows = Object.values(segments).sort(
    (a, b) => b.abandonment_rate - a.abandonment_rate
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700/50">
            <th className="text-left py-2 pr-4 font-medium">Segment</th>
            <th className="text-right py-2 px-2 font-medium">Total</th>
            <th className="text-right py-2 px-2 font-medium">Abandoned</th>
            <th className="text-right py-2 px-2 font-medium">Completed</th>
            <th className="text-right py-2 px-2 font-medium">Abandon Rate</th>
            <th className="text-right py-2 pl-2 font-medium">Conv. Rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isPrimary = primarySegment === row.segment;
            return (
              <tr
                key={row.segment}
                className={`border-b border-slate-800/60 transition-colors ${
                  isPrimary ? "bg-red-950/20" : "hover:bg-slate-800/30"
                }`}
              >
                <td className="py-2.5 pr-4">
                  <div className="flex items-center gap-2">
                    {isPrimary && (
                      <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
                    )}
                    <span className={isPrimary ? "text-red-300 font-medium" : "text-slate-300"}>
                      {SEGMENT_LABELS[row.segment] ?? row.segment}
                    </span>
                  </div>
                </td>
                <td className="text-right py-2.5 px-2 text-slate-400">{row.total}</td>
                <td className="text-right py-2.5 px-2 text-red-400">{row.abandoned}</td>
                <td className="text-right py-2.5 px-2 text-emerald-400">{row.completed}</td>
                <td className="text-right py-2.5 px-2">
                  <span
                    className={`font-mono font-semibold ${
                      row.abandonment_rate > 0.5
                        ? "text-red-400"
                        : row.abandonment_rate > 0.3
                        ? "text-amber-400"
                        : "text-emerald-400"
                    }`}
                  >
                    {formatPct(row.abandonment_rate)}
                  </span>
                </td>
                <td className="text-right py-2.5 pl-2">
                  {/* mini bar */}
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full"
                        style={{ width: `${row.conversion_rate * 100}%` }}
                      />
                    </div>
                    <span className="text-slate-400 font-mono text-xs w-10 text-right">
                      {formatPct(row.conversion_rate)}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
