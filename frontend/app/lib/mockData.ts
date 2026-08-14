import { Scenario, OrchestratorState } from "@/app/types";

export const MOCK_SCENARIOS: Scenario[] = [
  {
    key: "scenario_a",
    name: "scenario_a",
    display_name: "Mobile Checkout Fee Surprise",
    milestone: "M4 – Investigator / M5 – Operator",
    severity: "high",
    affected_segment: "mobile_first_time",
    root_cause: "unexpected_checkout_fee",
    description:
      "An unexpected processing fee is disclosed only at the final payment step, causing first-time mobile customers to abandon disproportionately.",
  },
  {
    key: "scenario_b",
    name: "scenario_b",
    display_name: "Pricing Page Copy Confusion",
    milestone: "M4 – Investigator / M5 – Operator",
    severity: "medium",
    affected_segment: "desktop_first_time",
    root_cause: "pricing_confusion",
    description:
      "The pricing page copy was reworded — seat-count language is now ambiguous. Desktop first-time customers abandon at checkout after reading conflicting information.",
  },
  {
    key: "scenario_c",
    name: "scenario_c",
    display_name: "Weather Red Herring + Canary Rollback",
    milestone: "M4 – Investigator / M5 – Operator / M6 – Canary guard",
    severity: "high",
    affected_segment: "all",
    root_cause: "checkout_step_reorder",
    description:
      "A checkout step reorder causes all-segment confusion. A weather red herring appears simultaneously. The first intervention fails canary; the agent must rollback and retry.",
  },
];

/** Staged mock state — simulates a real pipeline run over time */
export function buildMockState(
  scenario: string,
  stageIdx: number
): OrchestratorState {
  const stages = [
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
  ] as const;

  const stage = stages[Math.min(stageIdx, stages.length - 1)];
  const isDone = stage === "CLOSE";

  const segmentStats = {
    mobile_first_time: {
      segment: "mobile_first_time",
      total: 5,
      abandoned: 4,
      completed: 1,
      abandonment_rate: 0.8,
      conversion_rate: 0.2,
    },
    mobile_returning: {
      segment: "mobile_returning",
      total: 4,
      abandoned: 1,
      completed: 3,
      abandonment_rate: 0.25,
      conversion_rate: 0.75,
    },
    desktop_first_time: {
      segment: "desktop_first_time",
      total: 3,
      abandoned: 1,
      completed: 2,
      abandonment_rate: 0.33,
      conversion_rate: 0.67,
    },
    desktop_returning: {
      segment: "desktop_returning",
      total: 4,
      abandoned: 0,
      completed: 4,
      abandonment_rate: 0.05,
      conversion_rate: 0.95,
    },
  };

  const detected = stageIdx >= 2;
  const investigated = stageIdx >= 3;
  const operated = stageIdx >= 7;

  return {
    run_id: "mock-run-001",
    scenario,
    stage,
    started_at: new Date(Date.now() - stageIdx * 3000).toISOString(),
    finished_at: isDone ? new Date().toISOString() : null,
    elapsed_seconds: stageIdx * 3,
    journey_count: 16,

    detection: detected
      ? {
          has_anomaly: true,
          summary:
            "Detected unusual increase in mobile_first_time checkout abandonment: 80% vs 15% baseline.",
          primary_anomaly: {
            segment: "mobile_first_time",
            current_rate: 0.8,
            baseline_rate: 0.15,
            diff: 0.65,
            sample_size: 5,
            confidence: 0.92,
            severity: "high",
          },
          anomalies: [
            {
              segment: "mobile_first_time",
              current_rate: 0.8,
              baseline_rate: 0.15,
              diff: 0.65,
              sample_size: 5,
              confidence: 0.92,
              severity: "high",
            },
          ],
          segment_stats: segmentStats,
        }
      : null,

    hypotheses: investigated
      ? [
          { label: "Unexpected processing fee at checkout", confidence: 0.91, falsified: false },
          { label: "Weather / traffic spike", confidence: 0.12, falsified: true },
          { label: "Marketing campaign effect", confidence: 0.08, falsified: true },
        ]
      : [],

    investigator_report: investigated
      ? {
          root_cause: "Unexpected processing fee disclosed only at final payment step",
          confidence: 0.91,
          affected_segment: "mobile_first_time",
          recommended_intervention: "remove_checkout_fee",
          reasoning:
            "compare_segments_tool shows mobile_first_time abandonment at 80% vs 15% desktop_returning baseline. get_recent_business_changes reveals a processing_fee config change 18h ago with fees_disclosed=false. Weather and marketing campaign are falsified as they would affect all segments equally.",
          needs_human_review: false,
        }
      : null,

    operator_report: operated
      ? {
          outcome: "resolved",
          intervention_id: "intv-001",
          intervention_type: "remove_checkout_fee",
          canary_passed: true,
          actions_taken: [
            "Applied checkout fix: remove_fee for segment mobile_first_time",
            "Ran canary evaluation (10% traffic)",
            "Canary passed — abandonment dropped to 18%",
            "Promoted to full rollout",
          ],
          reasoning:
            "Root cause is confirmed as hidden fee. Removing the fee immediately eliminates the abandonment spike. Canary shows +22pp conversion improvement which exceeds the 10pp threshold.",
          escalation_reason: null,
        }
      : null,

    outcome: isDone ? "resolved" : null,
    error: null,

    health_before: detected ? 25.0 : null,
    health_after: isDone ? 85.7 : null,
    revenue_impact_monthly: detected ? 18000 : null,
  };
}
