// Hooks for the public landing visuals and the identity constellation. Server state goes through TanStack Query.
import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export type MetricId = "broken_ptp_rate" | "hardship_rate" | "open_cases" | "promises_at_risk";

export type ProvinceSeries = { value: (number | null)[]; n: (number | null)[]; top: (string | null)[] };
export type FsaDot = { fsa: string; province: string; lat: number; lon: number; n: number; value: number };
export type MapMetric = {
  label: string; unit: string; monthly: boolean; note: string;
  national: (number | null)[]; series: Record<string, ProvinceSeries>; fsas: FsaDot[]; fsas_hidden: number;
};
export type Province = { code: string; name: string; lat: number; lon: number; customers: number };
export type PublicMap = {
  as_of: string; months: string[]; min_group: number; customers: number; provinces: Province[];
  metrics: Partial<Record<MetricId, MapMetric>>;
};

export type FlowNode = { id: string; col: number; label: string; value: number; top?: { label: string; value: number }[] };
export type FlowLink = { source: string; target: string; value: number };
export type PublicFlow = {
  available: boolean; total: number; message?: string; plan_date?: string | null; columns?: string[];
  nodes: FlowNode[]; links: FlowLink[];
};

export type SampleRecord = { system: string; label: string; method: string; confidence: number | null };
export type NextAction = { treatment: string; label: string; channel: string | null };
export type PublicSample = { available: boolean; records: SampleRecord[]; next_action: NextAction | null };

export type PublicSummary = {
  golden_customers?: number; crm_records?: number; accounts_linked_pct?: number | null; open_cases?: number;
  issues_found?: number; contract_tests_passed?: number; contract_tests?: number;
};

const STALE = 10 * 60 * 1000;
/** Every public endpoint needs a session now (the API answers 401 otherwise), so each hook takes `enabled`: pass
 * whether someone is signed in. The visuals are only mounted for signed-in people, which is the real guard. */
export const usePublicSummary = (enabled = true) =>
  useQuery({ queryKey: ["public-summary"], queryFn: () => api<PublicSummary>("/public/summary"), staleTime: STALE, enabled, retry: false });
export const usePublicMap = (enabled = true) =>
  useQuery({ queryKey: ["public-map"], queryFn: () => api<PublicMap>("/public/map"), staleTime: STALE, enabled, retry: false });
export const usePublicFlow = (enabled = true) =>
  useQuery({ queryKey: ["public-flow"], queryFn: () => api<PublicFlow>("/public/flow"), staleTime: STALE, enabled, retry: false });
export const usePublicSample = (enabled = true) =>
  useQuery({ queryKey: ["public-sample"], queryFn: () => api<PublicSample>("/public/sample-customer"), staleTime: STALE, enabled, retry: false });

/** What the constellation draws: source records, then the proposed next action (if the viewer may see it). */
export type ConstellationData = {
  records: { label: string; sub?: string; system: string; confidence: number | null }[];
  action: { label: string; channel?: string | null } | null;
};

const SYSTEM: Record<string, string> = { crm: "CRM", cards: "Cards", lending: "Loans", core_banking: "Deposits", bureau: "Credit bureau", collections: "Collections case" };
const TREATMENT: Record<string, string> = {
  no_contact: "No contact", reminder: "Reminder", payment_link: "Payment link", plan_offer: "Plan offer", specialist_referral: "Specialist referral",
};

type IdentityResp = { sources: { system: string; ref: string; confidence?: number | null }[] };
type CustomerResp = { open_case_id?: string | null };
type NbaResp = { action?: { treatment: string; channel?: string | null } };

/** One customer's records and next action. goldenId "sample" uses the public, anonymous sample. */
export function useConstellationData(goldenId: string, enabled = true) {
  return useQuery({
    queryKey: ["constellation", goldenId],
    enabled,
    retry: false,
    staleTime: STALE,
    queryFn: async (): Promise<ConstellationData> => {
      if (goldenId === "sample") {
        const s = await api<PublicSample>("/public/sample-customer");
        return {
          records: s.records.map((r) => ({ label: r.label, system: r.system, confidence: r.confidence })),
          action: s.next_action ? { label: s.next_action.label, channel: s.next_action.channel } : null,
        };
      }
      const id = await api<IdentityResp>(`/customers/${goldenId}/identity`);
      const records = id.sources.map((r) => ({ label: SYSTEM[r.system] ?? r.system, sub: r.ref, system: r.system, confidence: r.confidence ?? null }));
      let action: ConstellationData["action"] = null;
      try {
        const c = await api<CustomerResp>(`/customers/${goldenId}`);
        if (c.open_case_id) {
          const n = await api<NbaResp>(`/nba/${c.open_case_id}`);
          if (n.action) action = { label: TREATMENT[n.action.treatment] ?? n.action.treatment, channel: n.action.channel };
        }
      } catch {
        // The viewer may not be allowed to see the proposal; the constellation still shows the records.
      }
      return { records, action };
    },
  });
}
