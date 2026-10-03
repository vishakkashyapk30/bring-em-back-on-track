// App-facing types. `openapi.ts` is GENERATED from the API (`make types`); derive from it where the
// backend schema is real (e.g. AskResponse), and keep hand-written shapes only for fixture-backed endpoints.
import type { components } from "./openapi";

type S = components["schemas"];

export type Role = S["Role"];
export type HardshipLevel = "none" | "possible" | "clear";
export type Session = S["Session"];
export type AskResponse = S["AskResponse"];
export type Action = S["Action"];

export interface Meta { as_of?: string; freshness_hours?: number; fixture?: boolean }
export interface ReasonCode { code: string; text: string; kind: string; contribution?: number }

export interface Decision { decision: string; reason_code?: string | null; user_id: string; ts: string }
export interface QueueItem {
  case_id: string; golden_id: string; name: string; product: string; dpd: number; action: Action;
  priority: number; risk_band: string | null; p_break: number | null; hardship_flag: boolean | HardshipLevel; vulnerable: boolean;
  route_to?: string | null; review_mode?: "individual" | "batch"; headline?: string; status?: "scheduled" | "deferred" | "no_action";
  deferred_reason?: string | null; overdue?: number; decision?: Decision | null;
}
export interface QueueResponse {
  meta: Meta; date: string | null; scope?: string; total: number; items: QueueItem[]; note?: string;
  counts?: Record<"in_scope" | "all" | "calls" | "digital" | "hardship" | "vulnerable" | "high_risk" | "tomorrow" | "batch" | "no_contact", number>;
}
export interface Alternative { action: Action; why_not: string; allowed?: boolean }
export interface NbaProposal {
  meta: Meta; case_id: string; golden_id: string; action: Action; priority: number;
  route_to?: string | null; review_mode?: "individual" | "batch"; status?: string; deferred_reason?: string | null; decision?: Decision | null;
  explanation: {
    recommendation: string; rules_applied: ReasonCode[];
    model_evidence: { p_break: number | null; band: string | null; label: string; model: string | null; drivers: ReasonCode[] };
    what_changed: ReasonCode[]; freshness: ReasonCode;
    alternatives: Alternative[];
  };
}
