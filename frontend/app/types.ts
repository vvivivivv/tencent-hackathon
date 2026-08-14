
export type Stage =
  | "DISCOVER"
  | "OBSERVE"
  | "DETECT"
  | "INVESTIGATE"
  | "PLAN"
  | "ACT_CANARY"
  | "CANARY_CHECK"
  | "ACT_FULL"
  | "VERIFY"
  | "CLOSE"
  | "ESCALATED"
  | "ERROR";

export type Severity = "low" | "medium" | "high";
export type IncidentStatus =
  | "open"
  | "investigating"
  | "canary_testing"
  | "resolved"
  | "escalated";

export interface SegmentStat {
  segment: string;
  total: number;
  abandoned: number;
  completed: number;
  abandonment_rate: number;
  conversion_rate: number;
}

export interface Anomaly {
  segment: string;
  current_rate: number;
  baseline_rate: number;
  diff: number;
  sample_size: number;
  confidence: number;
  severity: Severity;
}

export interface DetectionResult {
  has_anomaly: boolean;
  summary: string;
  primary_anomaly: Anomaly | null;
  anomalies: Anomaly[];
  segment_stats: Record<string, SegmentStat>;
}

export interface Hypothesis {
  label: string;
  confidence: number;
  falsified: boolean;
}

export interface InvestigatorReport {
  root_cause: string;
  confidence: number;
  affected_segment: string;
  recommended_intervention: string;
  reasoning: string;
  needs_human_review: boolean;
}

export interface OperatorReport {
  outcome: "resolved" | "rolled_back" | "escalated" | "no_action";
  intervention_id: string;
  intervention_type: string;
  canary_passed: boolean;
  actions_taken: string[];
  reasoning: string;
  escalation_reason: string | null;
}

export interface OrchestratorState {
  run_id: string;
  scenario: string;
  stage: Stage;
  started_at: string;
  finished_at: string | null;
  elapsed_seconds: number;
  journey_count: number;
  detection: DetectionResult | null;
  investigator_report: InvestigatorReport | null;
  operator_report: OperatorReport | null;
  outcome: string | null;
  error: string | null;
  hypotheses: Hypothesis[];
  health_before: number | null;
  health_after: number | null;
  revenue_impact_monthly: number | null;
}

export interface Scenario {
  key: string;
  name: string;
  display_name: string;
  milestone: string;
  severity: Severity;
  affected_segment: string;
  root_cause: string;
  description: string;
}

export interface Journey {
  id: string;
  customer_id: string;
  scenario: string;
  goal: string;
  result: "abandoned" | "completed";
  duration_seconds: number;
  steps: string[];
  created_at: string;
  customer?: {
    name: string;
    device: string;
    customer_type: string;
  };
}

export interface Incident {
  id: string;
  title: string;
  severity: Severity;
  scenario: string;
  affected_segment: string;
  root_cause: string;
  confidence: number;
  status: IncidentStatus;
  actions: unknown[];
  health_before: number;
  health_after: number;
  revenue_impact: number;
  created_at: string;
  resolved_at: string | null;
}
