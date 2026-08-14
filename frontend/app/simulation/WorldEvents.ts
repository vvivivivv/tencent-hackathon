// simulation/WorldEvents.ts
import type { StoreZone } from "./entities/WorldLayout";

export type WorldEvent =
  | { type: "CUSTOMER_ENTER";    customerId: string; color: number }
  | { type: "CUSTOMER_BROWSE";   customerId: string; zone: StoreZone }
  | { type: "CUSTOMER_PICK";     customerId: string; product: string }
  | { type: "CUSTOMER_QUEUE";    customerId: string }
  | { type: "CUSTOMER_CHECKOUT"; customerId: string; total: number; fee?: number }
  | { type: "CUSTOMER_SUCCESS";  customerId: string }
  | { type: "CUSTOMER_ABANDON";  customerId: string; reason: string; bubble?: string }
  | { type: "CUSTOMER_EXIT";     customerId: string }
  | { type: "AGENT_DETECT";      message: string }
  | { type: "AGENT_MOVE";        target: StoreZone }
  | { type: "AGENT_SPEAK";       text: string }
  | { type: "AGENT_TOOL_CALL";   tool: string; params?: Record<string, unknown> }
  | { type: "AGENT_FINDING";     message: string }
  | { type: "AGENT_FIX_START";   message: string }
  | { type: "AGENT_FIX_APPLY";   feeFrom: number; feeTo: number; label?: string }
  | { type: "AGENT_FIX_DONE";    message: string }
  | { type: "AGENT_VERIFY";      message: string }
  | { type: "AGENT_RESOLVED";    message: string }
  | { type: "STORE_OPEN" }
  | { type: "ANOMALY_ALERT";     message: string }
  | { type: "METRICS_UPDATE";    abandonment: number; conversion: number }
  | { type: "INCIDENT_RESOLVED" }
  | { type: "SET_STORE_TYPE";    storeType: StoreType; agentStartZone?: StoreZone }
  | { type: "RESET_WORLD" };

export type StoreType = "bakery" | "flower_shop" | "bookstore";

type Handler = (event: WorldEvent) => void;

class WorldEventBusClass {
  private handlers: Handler[] = [];
  on(handler: Handler) {
    this.handlers.push(handler);
    return () => { this.handlers = this.handlers.filter(h => h !== handler); };
  }
  emit(event: WorldEvent) {
    this.handlers.forEach(h => h(event));
  }
}

export const WorldEventBus = new WorldEventBusClass();

export type AgentLogType =
  | "DETECT" | "ANALYZE" | "PATTERN" | "INVESTIGATE"
  | "FOUND" | "ROOT_CAUSE" | "PLAN" | "ACTION"
  | "TOOL" | "SUCCESS" | "VERIFY" | "RESULT"
  | "RESOLVED" | "INFO";

export interface AgentLogEntry {
  id: string;
  time: string;
  type: AgentLogType;
  title: string;
  narrative: string;
  technical: string;
  linkedZone?: StoreZone;
  highlight?: boolean;
}