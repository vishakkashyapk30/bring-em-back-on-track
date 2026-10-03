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

export interface QueueItem {
  case_id: string; golden_id: string; name: string; product: string; dpd: number; action: Action;
  priority: number; risk_band: string; p_break: number; hardship_flag: HardshipLevel; vulnerable: boolean;
}
export interface NbaProposal {
  meta: Meta; case_id: string; golden_id: string; action: Action; priority: number;
  explanation: {
    recommendation: string; rules_applied: ReasonCode[];
    model_evidence: { p_break: number; band: string; label: string; model: string; drivers: ReasonCode[] };
    what_changed: ReasonCode[]; freshness: ReasonCode;
    alternatives: { action: Action; why_not: string }[];
  };
}
