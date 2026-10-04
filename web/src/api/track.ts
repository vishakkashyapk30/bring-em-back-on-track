import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, post } from "./client";

// Shapes of /api/track (api/schemas/track.py).
export type TrackKind = "customer" | "agent" | "employer" | "cohort" | "identity" | "product";
export type Tone = "info" | "care" | "good" | "warn";
export type Source = { kind: "sql" | "records" | "report"; label: string; sql?: string | null; table?: string | null; ids: string[] };
export type Insight = { id: string; title: string; reason: string; tone: Tone; source: Source };
export type TrackEvent = { ts: string; type: string; title: string; detail?: string | null; tone: Tone; ref?: string | null; table?: string | null; link?: string | null };
export type Series = { title: string; unit: "pct" | "count" | "cad"; x: string[]; lines: { name: string; values: (number | null)[] }[]; note?: string | null; suppressed: number; source: Source };
export type Table = { title?: string | null; columns: string[]; rows: (string | number | boolean | null)[][]; note?: string | null; source: Source };
export type Fact = { label: string; value: string };
export type Section = { id: string; label: string; kind: "timeline" | "series" | "table" | "facts"; intro?: string | null; events: TrackEvent[]; series: Series[]; tables: Table[]; facts: Fact[] };
export type TrackAction = {
  id: string; kind: "nba" | "summary" | "hardship_confirm" | "hardship_lower" | "simulator" | "batch_approve" | "playbook_approve" | "link" | "identity_verdict" | "drift_approve" | "propose_test";
  label: string; detail?: string | null; endpoint?: string | null; link?: string | null; target?: string | null; enabled: boolean; why_disabled?: string | null; options: Fact[];
};
export type TrackView = {
  meta: { as_of?: string; freshness_hours?: number }; kind: TrackKind; id: string; title: string; subtitle?: string | null; badges: string[]; figures: Fact[];
  insights: Insight[]; sections: Section[]; actions: TrackAction[]; case_id?: string | null; golden_id?: string | null; aggregates_only: boolean;
};
export type Subject = { id: string; label: string; sublabel?: string | null; badges: string[] };
export type Kinds = { role: string; kinds: { kind: TrackKind; label: string; hint: string }[]; suggested?: Subject | null; suggested_kind?: TrackKind | null };

export const trackPath = (kind: string, id: string) => `/track/${kind}/${encodeURIComponent(id)}`;

export const useTrackKinds = () => useQuery({ queryKey: ["track-kinds"], queryFn: () => api<Kinds>("/track/kinds"), staleTime: 60_000 });
export const useTrackSubjects = (kind: string | undefined, q: string) =>
  useQuery({
    queryKey: ["track-subjects", kind, q], enabled: !!kind, placeholderData: keepPreviousData,
    queryFn: () => api<{ kind: TrackKind; items: Subject[]; note?: string | null }>(`/track/subjects?${new URLSearchParams({ kind: kind ?? "", q })}`),
  });
export const useTrack = (kind: string, id: string) =>
  useQuery({ queryKey: ["track", kind, id], queryFn: () => api<TrackView>(`/track/${kind}/${encodeURIComponent(id)}`), retry: false });

/** Run one tracker action through its existing endpoint (each writes the audit log), then refresh the tracker. */
export const useTrackAction = (kind: string, id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ endpoint, body }: { endpoint: string; body?: unknown; done?: string }) => post<{ audit_id: number; note?: string }>(endpoint, body),
    onSuccess: (r, v) => {
      toast.success(v.done ?? "Saved", { description: `${r.note ? `${r.note} ` : ""}Recorded in the audit log (#${r.audit_id}).` });
      qc.invalidateQueries({ queryKey: ["track", kind, id] });
      for (const k of ["batches", "playbooks", "drift", "hboard", "nba"]) qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e: { reason?: string }) => toast.error("That didn't go through", { description: e.reason ?? "Nothing was changed. Try again." }),
  });
};
