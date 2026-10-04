import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, post } from "./client";

export type Proposal = {
  proposal_id: string; playbook: string; kind: string; title: string; detail: string; status: string;
  requires_policy_office_signoff: boolean; payload: { customer_ids?: string[]; n_customers?: number; area?: string };
};
export type RadarRow = {
  employer_key: string; industry_naics2: string | null; n_customers: number; n_payroll_gap: number; n_new_ei: number;
  gap_rate: number; pattern: string; explained_by_incident: string | null;
  known_incidents: { event_id: string; description: string }[];
};
export type Radar = {
  week_start?: string; label: string; summary: string; rows: RadarRow[]; employers_shown: number;
  employers_hidden_small: number; clusters: number; min_group?: number; known_incidents: { event_id: string; description: string }[];
};
export type DriftChange = {
  table: string; renames: { from: string; to: string; complete?: boolean }[];
  type_changes: { column?: string; from?: string; to?: string }[] | Record<string, unknown>[];
  added_columns: string[]; removed_columns: string[]; null_rate_changes: Record<string, number>;
  row_count_change?: number; event_id?: string; event_description?: string;
};
export type DriftFix = {
  fix_id: string; table: string; description: string; diff: string; explanation: string; status: string;
  applied: boolean; change: DriftChange;
};

export const useRadar = () => useQuery({ queryKey: ["radar"], queryFn: () => api<Radar>("/radar") });
export const usePlaybooks = () =>
  useQuery({ queryKey: ["playbooks"], queryFn: () => api<{ items: Proposal[]; pending: number }>("/playbooks") });
export const useDrift = () =>
  useQuery({ queryKey: ["drift"], queryFn: () => api<{ fixes: DriftFix[]; pending: number }>("/drift") });

const fail = (what: string) => (e: { reason?: string }) =>
  toast.error(`Couldn't ${what}`, { description: e.reason ?? "Nothing was changed. Try again." });

export const useApprovePlaybook = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post<{ audit_id: number; batch_id: string; note: string }>(`/playbooks/${id}/approve`),
    onSuccess: (r) => {
      toast.success("Batch created", { description: `${r.note} Recorded in the audit log (#${r.audit_id}).` });
      qc.invalidateQueries({ queryKey: ["playbooks"] });
      qc.invalidateQueries({ queryKey: ["batches"] });
    },
    onError: fail("create the batch"),
  });
};
export const useApproveDrift = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post<{ audit_id: number; note: string }>(`/drift/${id}/approve`),
    onSuccess: (r) => {
      toast.success("Fix approved", { description: `An engineer will apply it. Recorded in the audit log (#${r.audit_id}).` });
      qc.invalidateQueries({ queryKey: ["drift"] });
    },
    onError: fail("approve the fix"),
  });
};

/** How many customers a proposal covers: listed IDs, else the area count, else one (outage items are per customer). */
export function customerCount(p: Proposal): number {
  return p.payload.customer_ids?.length ?? p.payload.n_customers ?? 1;
}
export const KIND_LABEL: Record<string, string> = {
  contact: "Offer early help", hold: "Hold pressure steps", fee_reversal: "Reverse a late fee", pressure_hold: "Hold pressure steps",
};
export const PATTERN_LABEL: Record<string, string> = {
  none: "No cluster", layoff_like: "Late pay with new EI", payroll_delay: "Late pay, no EI",
};
export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
/** Signed change in percentage points, e.g. 0.551 -> "+55.1 pts". */
export const pts = (v: number) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(v * 100).toFixed(1)} pts`;
/** The few columns whose null rate moved the most, largest first. */
export function topNullChanges(m: Record<string, number>, n = 4): [string, number][] {
  return Object.entries(m).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, n);
}
/** "Rows down 71.6% in the new load". */
export const rowChange = (v: number) => `Rows ${v < 0 ? "down" : "up"} ${Math.abs(v * 100).toFixed(1)}% in the new load`;
