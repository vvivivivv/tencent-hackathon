export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function formatPct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

export function formatMoney(v: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v);
}

export function severityColor(s: string) {
  if (s === "high") return "text-red-400";
  if (s === "medium") return "text-amber-400";
  return "text-blue-400";
}

export function severityBadgeVariant(s: string) {
  if (s === "high") return "danger" as const;
  if (s === "medium") return "warning" as const;
  return "info" as const;
}

export function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    DISCOVER: "Discover",
    OBSERVE: "Observe",
    DETECT: "Detect",
    INVESTIGATE: "Investigate",
    PLAN: "Plan",
    ACT_CANARY: "Canary Deploy",
    CANARY_CHECK: "Canary Check",
    ACT_FULL: "Full Rollout",
    VERIFY: "Verify",
    CLOSE: "Closed",
    ESCALATED: "Escalated",
    ERROR: "Error",
  };
  return labels[stage] ?? stage;
}
