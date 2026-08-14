// simulation/scenarios/scenarioEvents.ts
import { WorldEventBus, type WorldEvent, type AgentLogEntry, type AgentLogType } from "../WorldEvents";

export interface ScriptBeat {
  delayMs: number;
  worldEvent?: WorldEvent;
  agentLog?: Omit<AgentLogEntry, "id" | "time">;
}

const cid = (n: number) => `C${String(n).padStart(3, "0")}`;
const COLORS = [0xff9f69, 0x69c3ff, 0xb5ff69, 0xffd169, 0xe069ff, 0x69ffe0, 0xff69b4, 0x69ffb4];
const color = (n: number) => COLORS[(n - 1) % COLORS.length];

// Shared five-beat investigation staircase — every scenario gets the same
// structural depth so none of them skip straight to a fix.
function investigationSteps(
  base: number,
  copy: {
    analyze: { narrative: string; technical: string };
    pattern: { narrative: string; technical: string };
    investigate: { narrative: string; technical: string };
    found: { narrative: string; technical: string };
    rootCause: { narrative: string; technical: string };
  }
): ScriptBeat[] {
  const step = (offset: number, type: AgentLogType, title: string, c: { narrative: string; technical: string }, highlight = false): ScriptBeat => ({
    delayMs: base + offset,
    agentLog: { type, title, narrative: c.narrative, technical: c.technical, highlight },
  });
  return [
    step(0, "ANALYZE", "Analyzing signals", copy.analyze),
    step(4500, "PATTERN", "Pattern identified", copy.pattern, true),
    step(9000, "INVESTIGATE", "Investigating further", copy.investigate),
    step(13500, "FOUND", "Finding confirmed", copy.found, true),
    step(18000, "ROOT_CAUSE", "Root cause confirmed", copy.rootCause, true),
  ];
}

export function buildScenarioA(): ScriptBeat[] {
  const b: ScriptBeat[] = [];
  b.push({ delayMs: 0, worldEvent: { type: "SET_STORE_TYPE", storeType: "bakery", agentStartZone: "agent_desk" } });
  b.push({ delayMs: 200, worldEvent: { type: "STORE_OPEN" } });
  b.push({ delayMs: 800, agentLog: { type: "INFO", title: "Monitoring", narrative: "Bakery online. Metrics healthy.", technical: "Baseline conversion: 92%." } });

  // ── Scene 1: normal — 2 customers succeed ──
  [1, 2].forEach((n, i) => {
    const t = 1500 + i * 3500;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1500, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_left" } });
    b.push({ delayMs: t + 4000, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "pastry" } });
    b.push({ delayMs: t + 5000, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 7000, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 8.5 } });
    b.push({ delayMs: t + 8500, worldEvent: { type: "CUSTOMER_SUCCESS",  customerId: cid(n) } });
    b.push({ delayMs: t + 9500, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  // ── Scene 2: problem begins — 4 customers hit the hidden fee ──
  const failStart = 10500;
  [3, 4, 5, 6].forEach((n, i) => {
    const t = failStart + i * 3200;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1500, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_center" } });
    b.push({ delayMs: t + 4000, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "cake" } });
    b.push({ delayMs: t + 5000, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 7000, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 18.0, fee: 5.0 } });
    b.push({ delayMs: t + 8500, worldEvent: { type: "CUSTOMER_ABANDON",  customerId: cid(n), reason: "Unexpected $5 fee", bubble: "$5 fee?! 😠" } });
    b.push({ delayMs: t + 11500, worldEvent: { type: "CUSTOMER_EXIT",    customerId: cid(n) } });
  });

  const lastFailEnd = failStart + 3 * 3200 + 11500; // ~31700
  b.push({ delayMs: lastFailEnd - 2000, worldEvent: { type: "METRICS_UPDATE", abandonment: 45, conversion: 55 } });

  // ── Scene 3: detection ──
  const detectAt = lastFailEnd + 500;
  b.push({ delayMs: detectAt, worldEvent: { type: "ANOMALY_ALERT", message: "Checkout abandonment spike" } });
  b.push({ delayMs: detectAt, agentLog: { type: "DETECT", title: "Anomaly detected", narrative: "Checkout abandonment jumped to 45%.", technical: "Baseline 8% → current 45% over last 4 transactions. Threshold exceeded.", highlight: true } });

  // ── Scene 4: full investigation staircase ──
  const investAt = detectAt + 2500;
  b.push({ delayMs: investAt, worldEvent: { type: "AGENT_MOVE", target: "aisle_center" } });
  b.push({ delayMs: investAt + 500, worldEvent: { type: "AGENT_SPEAK", text: "Reviewing recent transactions..." } });
  b.push(...investigationSteps(investAt + 1500, {
    analyze:     { narrative: "Scanning last 6 checkout attempts.",           technical: "6 journeys pulled. 4 abandoned, 2 completed. All abandons occurred post-checkout-start." },
    pattern:     { narrative: "All 4 abandons share one trait.",              technical: "100% of abandoned carts show a line item added at the payment step that wasn't shown earlier." },
    investigate: { narrative: "Checking checkout configuration history.",     technical: "Querying config change log for the last 48 hours..." },
    found:       { narrative: "Config change found.",                         technical: "cash_handling_fee: $0.00 → $5.00. Changed yesterday 09:14 by admin@store. Not reflected in pricing page." },
    rootCause:   { narrative: "Hidden $5 fee confirmed as the cause.",        technical: "92% correlation between fee exposure and abandonment. Fee is applied silently at final step — never disclosed earlier in the flow." },
  }));

  // ── Scene 5: fix ──
  const fixAt = investAt + 1500 + 22000;
  b.push({ delayMs: fixAt, worldEvent: { type: "AGENT_MOVE", target: "cashier" } });
  b.push({ delayMs: fixAt, agentLog: { type: "PLAN", title: "Fix plan", narrative: "Remove the fee, notify manager, verify.", technical: "1. update_checkout_config(fee: 0)\n2. notify_manager()\n3. run verification cohort" } });
  b.push({ delayMs: fixAt + 4000, worldEvent: { type: "AGENT_FIX_APPLY", feeFrom: 5, feeTo: 0, label: "cash_handling_fee\n$5.00 → $0.00" } });
  b.push({ delayMs: fixAt + 4000, agentLog: { type: "TOOL", title: "update_checkout_config()", narrative: "Fee removed from checkout.", technical: 'fee_type: "cash_handling"\namount: $5.00 → $0.00', highlight: true } });
  b.push({ delayMs: fixAt + 9000, agentLog: { type: "SUCCESS", title: "Configuration updated", narrative: "Fee removed. Manager notified.", technical: "Config write confirmed. Slack notification sent to admin@store." } });

  // ── Scene 6: verify — 3 fresh customers all succeed ──
  const verifyAt = fixAt + 10000;
  b.push({ delayMs: verifyAt, worldEvent: { type: "AGENT_VERIFY", message: "Running verification" } });
  b.push({ delayMs: verifyAt, agentLog: { type: "VERIFY", title: "Verifying fix", narrative: "Sending test customers through checkout.", technical: "Replaying affected segment (mobile_first_time) against updated config." } });
  b.push({ delayMs: verifyAt + 1000, worldEvent: { type: "AGENT_MOVE", target: "agent_desk" } });

  [7, 8, 9].forEach((n, i) => {
    const t = verifyAt + 2500 + i * 4000;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1200, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_right" } });
    b.push({ delayMs: t + 2400, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "bread" } });
    b.push({ delayMs: t + 3000, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 3500, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 9.0 } });
    b.push({ delayMs: t + 3800, worldEvent: { type: "CUSTOMER_SUCCESS",  customerId: cid(n) } });
    b.push({ delayMs: t + 4300, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  const resolveAt = verifyAt + 2500 + 2 * 4000 + 4300 + 800;
  b.push({ delayMs: resolveAt, worldEvent: { type: "METRICS_UPDATE", abandonment: 8, conversion: 92 } });
  b.push({ delayMs: resolveAt, agentLog: { type: "RESOLVED", title: "Incident Resolved", narrative: "Fee removed. Abandonment 45%→8%.", technical: "Root cause: hidden $5 fee (config error).\nAction: fee removed, manager notified.\nResult: abandonment 45%→8%, conversion 55%→92%.", highlight: true } });
  b.push({ delayMs: resolveAt + 500, worldEvent: { type: "INCIDENT_RESOLVED" } });

  return b.sort((a, c) => a.delayMs - c.delayMs);
}


export function buildScenarioB(): ScriptBeat[] {
  const b: ScriptBeat[] = [];
  b.push({ delayMs: 0, worldEvent: { type: "SET_STORE_TYPE", storeType: "flower_shop", agentStartZone: "entrance" } });
  b.push({ delayMs: 200, worldEvent: { type: "STORE_OPEN" } });
  b.push({ delayMs: 800, agentLog: { type: "INFO", title: "Syncing", narrative: "Monitoring flower inventory.", technical: "Catalog status: connected." } });

  [1, 2].forEach((n, i) => {
    const t = 1500 + i * 3500;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1500, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_left" } });
    b.push({ delayMs: t + 4000, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "bouquet" } });
    b.push({ delayMs: t + 5000, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 7000, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 22.0 } });
    b.push({ delayMs: t + 8000, worldEvent: { type: "CUSTOMER_SUCCESS",  customerId: cid(n) } });
    b.push({ delayMs: t + 9000, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  const failStart = 10500;
  [3, 4, 5, 6].forEach((n, i) => {
    const t = failStart + i * 3200;
    b.push({ delayMs: t,         worldEvent: { type: "CUSTOMER_ENTER",  customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1500,  worldEvent: { type: "CUSTOMER_BROWSE", customerId: cid(n), zone: "aisle_center" } });
    b.push({ delayMs: t + 4500,  worldEvent: { type: "CUSTOMER_BROWSE", customerId: cid(n), zone: "aisle_right" } });
    b.push({ delayMs: t + 7500,  worldEvent: { type: "CUSTOMER_ABANDON", customerId: cid(n), reason: "Rose bundle not found", bubble: "No roses? 🤨" } });
    b.push({ delayMs: t + 10500, worldEvent: { type: "CUSTOMER_EXIT",    customerId: cid(n) } });
  });

  const lastFailEnd = failStart + 3 * 3200 + 10500;
  b.push({ delayMs: lastFailEnd - 1500, worldEvent: { type: "METRICS_UPDATE", abandonment: 38, conversion: 62 } });

  const detectAt = lastFailEnd + 500;
  b.push({ delayMs: detectAt, worldEvent: { type: "ANOMALY_ALERT", message: "Browse-abandon pattern" } });
  b.push({ delayMs: detectAt, agentLog: { type: "DETECT", title: "Anomaly detected", narrative: "4 customers browsed and left without buying.", technical: "0 checkouts reached in last 4 sessions. All browsed >2 zones before exit — unusual pattern.", highlight: true } });

  const investAt = detectAt + 2500;
  b.push({ delayMs: investAt, worldEvent: { type: "AGENT_MOVE", target: "aisle_center" } });
  b.push({ delayMs: investAt + 500, worldEvent: { type: "AGENT_SPEAK", text: "Checking search & browse logs..." } });
  b.push(...investigationSteps(investAt + 1500, {
    analyze:     { narrative: "Reviewing browse paths for the 4 abandons.",  technical: "4 sessions pulled. All: aisle_center → aisle_right → exit. None reached queue." },
    pattern:     { narrative: "All 4 searched for the same item.",           technical: "In-store search kiosk logs: \"roses\" × 3, \"rose bouquet\" × 1. 100% overlap with abandoning customers." },
    investigate: { narrative: "Checking live catalog vs. warehouse stock.",  technical: "Querying stock management system for SKU ROSE-BUNDLE-12..." },
    found:       { narrative: "Listing status mismatch found.",              technical: "SKU ROSE-BUNDLE-12: physical stock 24 units. Catalog status: UNLISTED (draft). Last edited 3 days ago — never published." },
    rootCause:   { narrative: "Rose bundle was never published to the live catalog.", technical: "Item exists in warehouse but customers can't find it in-store or online — 100% correlation with abandon events." },
  }));

  const fixAt = investAt + 1500 + 22000;
  b.push({ delayMs: fixAt, worldEvent: { type: "AGENT_MOVE", target: "cashier" } });
  b.push({ delayMs: fixAt, agentLog: { type: "PLAN", title: "Fix plan", narrative: "Publish the listing, set a reorder alert.", technical: "1. publish_catalog_item(sku: ROSE-BUNDLE-12)\n2. set_reorder_alert(threshold: 5)" } });
  b.push({ delayMs: fixAt + 4000, worldEvent: { type: "AGENT_FIX_APPLY", feeFrom: 0, feeTo: 0, label: "catalog_status\ndraft → published" } });
  b.push({ delayMs: fixAt + 4000, agentLog: { type: "TOOL", title: "publish_catalog_item()", narrative: "Rose bundle now live in catalog.", technical: 'sku: "ROSE-BUNDLE-12"\nstatus: draft → published\nprice: $28.00 · stock: 24', highlight: true } });
  b.push({ delayMs: fixAt + 9000, agentLog: { type: "SUCCESS", title: "Catalog updated", narrative: "Listing published. Staff alerted to restock display.", technical: "Catalog write confirmed. Reorder threshold set to 5 units." } });

  const verifyAt = fixAt + 10000;
  b.push({ delayMs: verifyAt, worldEvent: { type: "AGENT_VERIFY", message: "Monitoring next arrivals" } });
  b.push({ delayMs: verifyAt, agentLog: { type: "VERIFY", title: "Verifying fix", narrative: "Watching next customer journeys for roses.", technical: "Replaying affected segment against updated catalog." } });
  b.push({ delayMs: verifyAt + 1000, worldEvent: { type: "AGENT_MOVE", target: "agent_desk" } });

  [7, 8, 9].forEach((n, i) => {
    const t = verifyAt + 2500 + i * 4200;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1200, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_center" } });
    b.push({ delayMs: t + 2600, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "roses" } });
    b.push({ delayMs: t + 3200, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 3800, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 28.0 } });
    b.push({ delayMs: t + 4100, worldEvent: { type: "CUSTOMER_SUCCESS",  customerId: cid(n) } });
    b.push({ delayMs: t + 4600, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  const resolveAt = verifyAt + 2500 + 2 * 4200 + 4600 + 800;
  b.push({ delayMs: resolveAt, worldEvent: { type: "METRICS_UPDATE", abandonment: 6, conversion: 94 } });
  b.push({ delayMs: resolveAt, agentLog: { type: "RESOLVED", title: "Incident Resolved", narrative: "Listing published. Abandonment 38%→6%.", technical: "Root cause: rose bundle never published to live catalog.\nAction: published, reorder alert set.\nResult: abandonment 38%→6%, conversion 62%→94%.", highlight: true } });
  b.push({ delayMs: resolveAt + 500, worldEvent: { type: "INCIDENT_RESOLVED" } });

  return b.sort((a, c) => a.delayMs - c.delayMs);
}


export function buildScenarioC(): ScriptBeat[] {
  const b: ScriptBeat[] = [];
  b.push({ delayMs: 0, worldEvent: { type: "SET_STORE_TYPE", storeType: "bookstore", agentStartZone: "aisle_left" } });
  b.push({ delayMs: 200, worldEvent: { type: "STORE_OPEN" } });
  b.push({ delayMs: 800, agentLog: { type: "INFO", title: "Kiosk link", narrative: "Monitoring self-checkout.", technical: "Kiosk status: online." } });

  [1, 2].forEach((n, i) => {
    const t = 1500 + i * 3500;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1500, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_left" } });
    b.push({ delayMs: t + 4000, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "novel" } });
    b.push({ delayMs: t + 5000, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 6500, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 18.0 } });
    b.push({ delayMs: t + 7500, worldEvent: { type: "CUSTOMER_SUCCESS",  customerId: cid(n) } });
    b.push({ delayMs: t + 8500, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  const failStart = 10500;
  [3, 4, 5, 6].forEach((n, i) => {
    const t = failStart + i * 3600;
    b.push({ delayMs: t,         worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1500,  worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_right" } });
    b.push({ delayMs: t + 4000,  worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "art book" } });
    b.push({ delayMs: t + 5000,  worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 7000,  worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 35.0, fee: 99 } }); // fee=99 signals timeout
    b.push({ delayMs: t + 11000, worldEvent: { type: "CUSTOMER_ABANDON",  customerId: cid(n), reason: "Kiosk timed out", bubble: "Kiosk froze... 😢" } });
    b.push({ delayMs: t + 14000, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  const lastFailEnd = failStart + 3 * 3600 + 14000;
  b.push({ delayMs: lastFailEnd - 1500, worldEvent: { type: "METRICS_UPDATE", abandonment: 42, conversion: 58 } });

  const detectAt = lastFailEnd + 500;
  b.push({ delayMs: detectAt, worldEvent: { type: "ANOMALY_ALERT", message: "Checkout queue stall" } });
  b.push({ delayMs: detectAt, agentLog: { type: "DETECT", title: "Anomaly detected", narrative: "Checkout duration spiked from 45s to 4m.", technical: "Average checkout time: 45s → 4m12s. 4 consecutive abandons at payment step.", highlight: true } });

  const investAt = detectAt + 2500;
  b.push({ delayMs: investAt, worldEvent: { type: "AGENT_MOVE", target: "cashier" } });
  b.push({ delayMs: investAt + 500, worldEvent: { type: "AGENT_SPEAK", text: "Pulling kiosk session logs..." } });
  b.push(...investigationSteps(investAt + 1500, {
    analyze:     { narrative: "Reviewing kiosk transaction logs.",           technical: "4 sessions pulled — all show a SESSION_TIMEOUT event during the payment step." },
    pattern:     { narrative: "All 4 timed out at the same point.",          technical: "Every failed session hit timeout during card-reader handshake, at exactly 90s idle." },
    investigate: { narrative: "Checking kiosk configuration history.",       technical: "Querying device management system for kiosk-01 config changes..." },
    found:       { narrative: "Firmware config rollback found.",            technical: "Firmware update v2.1.4 (yesterday) reset session_timeout: 300s → 90s. Card handshake typically takes 95-140s." },
    rootCause:   { narrative: "Timeout set below the handshake minimum.",   technical: "Every payment attempt now times out mid-transaction — 100% of recent failures match this exact window." },
  }));

  const fixAt = investAt + 1500 + 22000;
  b.push({ delayMs: fixAt, worldEvent: { type: "AGENT_MOVE", target: "cashier" } });
  b.push({ delayMs: fixAt, agentLog: { type: "PLAN", title: "Fix plan", narrative: "Restore timeout, alert staff, log regression.", technical: "1. update_kiosk_config(timeout: 300s)\n2. send_staff_alert()\n3. file_regression_report()" } });
  b.push({ delayMs: fixAt + 4000, worldEvent: { type: "AGENT_FIX_APPLY", feeFrom: 90, feeTo: 300, label: "session_timeout\n90s → 300s" } });
  b.push({ delayMs: fixAt + 4000, agentLog: { type: "TOOL", title: "update_kiosk_config()", narrative: "Timeout restored to 300s.", technical: 'device: "kiosk-01"\nsession_timeout: 90s → 300s\nrestart_required: true', highlight: true } });
  b.push({ delayMs: fixAt + 9000, agentLog: { type: "SUCCESS", title: "Kiosk reconfigured", narrative: "Timeout restored. Staff alerted. Restarting.", technical: "Config write confirmed. Staff notified to manually assist queued customers during 2-min restart." } });

  const verifyAt = fixAt + 10000;
  b.push({ delayMs: verifyAt, worldEvent: { type: "AGENT_VERIFY", message: "Monitoring next checkouts" } });
  b.push({ delayMs: verifyAt, agentLog: { type: "VERIFY", title: "Verifying fix", narrative: "Monitoring checkout durations post-fix.", technical: "Replaying affected cohort against restored kiosk config." } });
  b.push({ delayMs: verifyAt + 1000, worldEvent: { type: "AGENT_MOVE", target: "agent_desk" } });

  [7, 8, 9].forEach((n, i) => {
    const t = verifyAt + 2500 + i * 4200;
    b.push({ delayMs: t,        worldEvent: { type: "CUSTOMER_ENTER",    customerId: cid(n), color: color(n) } });
    b.push({ delayMs: t + 1200, worldEvent: { type: "CUSTOMER_BROWSE",   customerId: cid(n), zone: "aisle_center" } });
    b.push({ delayMs: t + 2600, worldEvent: { type: "CUSTOMER_PICK",     customerId: cid(n), product: "book" } });
    b.push({ delayMs: t + 3200, worldEvent: { type: "CUSTOMER_QUEUE",    customerId: cid(n) } });
    b.push({ delayMs: t + 3800, worldEvent: { type: "CUSTOMER_CHECKOUT", customerId: cid(n), total: 22.0 } });
    b.push({ delayMs: t + 4100, worldEvent: { type: "CUSTOMER_SUCCESS",  customerId: cid(n) } });
    b.push({ delayMs: t + 4600, worldEvent: { type: "CUSTOMER_EXIT",     customerId: cid(n) } });
  });

  const resolveAt = verifyAt + 2500 + 2 * 4200 + 4600 + 800;
  b.push({ delayMs: resolveAt, worldEvent: { type: "METRICS_UPDATE", abandonment: 7, conversion: 93 } });
  b.push({ delayMs: resolveAt, agentLog: { type: "RESOLVED", title: "Incident Resolved", narrative: "Timeout restored. Abandonment 42%→7%.", technical: "Root cause: firmware reset kiosk timeout below handshake minimum.\nAction: timeout restored, staff alerted.\nResult: abandonment 42%→7%, conversion 58%→93%.", highlight: true } });
  b.push({ delayMs: resolveAt + 500, worldEvent: { type: "INCIDENT_RESOLVED" } });

  return b.sort((a, c) => a.delayMs - c.delayMs);
}

export type ScenarioId = "A" | "B" | "C";
let activeTimers: ReturnType<typeof setTimeout>[] = [];

export function runScenario(id: ScenarioId, onLog: (e: Omit<AgentLogEntry, "id" | "time">) => void): () => void {
  stopScenario();
  const script = id === "A" ? buildScenarioA() : id === "B" ? buildScenarioB() : buildScenarioC();
  script.forEach(beat => {
    const t = setTimeout(() => {
      if (beat.worldEvent) WorldEventBus.emit(beat.worldEvent);
      if (beat.agentLog) onLog(beat.agentLog);
    }, beat.delayMs);
    activeTimers.push(t);
  });
  return stopScenario;
}

export function stopScenario() {
  activeTimers.forEach(clearTimeout);
  activeTimers = [];
}

export const SCENARIO_META: Record<ScenarioId, { id: ScenarioId; storeType: string; storeEmoji: string; title: string; problem: string }> = {
  A: { id: "A", storeType: "bakery",      storeEmoji: "🥐", title: "Hidden Fee",     problem: "Undisclosed $5 fee driving abandonment." },
  B: { id: "B", storeType: "flower_shop", storeEmoji: "🌸", title: "Inventory Gap",  problem: "Bestselling item never published to catalog." },
  C: { id: "C", storeType: "bookstore",   storeEmoji: "📚", title: "Kiosk Loop",     problem: "Firmware update stalling every payment." },
};