// "Waiting for you" inbox and the saved watchlist (docs/inbox_and_watchlist.md). Read-only inbox; pins are audited.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, post } from "./client";

export type InboxItem = {
  id: string; type: string; title: string; reason: string; age_days: number | null; age_label: string;
  due: string | null; overdue: boolean; link: string; subject_kind: string | null; subject_id: string | null;
};
export type InboxGroup = {
  type: string; label: string; why: string; count: number; items: InboxItem[]; link: string; link_label: string; informational: boolean;
};
export type Inbox = {
  role: string; total: number; backlog?: number; groups: InboxGroup[]; top: InboxItem[]; not_available: { source: string; reason: string }[];
  as_of: string; note: string | null;
};
export type WatchKind = "customer" | "case" | "agent" | "employer" | "cohort" | "data_product" | "identity";
export type Pin = { kind: WatchKind; subject_id: string };
export type WatchItem = Pin & {
  label: string; created_at: string; last_seen_at: string; link: string; track_link: string; status: string;
  changes: string[]; available: boolean;
};

export const useInbox = (enabled = true) => useQuery({ queryKey: ["inbox"], queryFn: () => api<Inbox>("/inbox"), enabled });
/** Nav badge: refreshed every minute and when the window regains focus. */
export const useInboxCounts = (enabled = true) =>
  useQuery({
    queryKey: ["inbox-counts"], queryFn: () => api<{ total: number; by_type: Record<string, number> }>("/inbox/counts"),
    enabled, refetchInterval: 60_000, staleTime: 15_000,
  });

export const useWatchlist = (enabled = true) =>
  useQuery({ queryKey: ["watchlist"], queryFn: () => api<{ items: WatchItem[]; changed: number }>("/watchlist"), enabled });
export const usePins = () => useQuery({ queryKey: ["watch-pins"], queryFn: () => api<Pin[]>("/watchlist/pins"), staleTime: 30_000 });

const path = (kind: string, id: string) => `/watchlist/${kind}/${encodeURIComponent(id)}`;

/** Pin or unpin with an optimistic update of the pin list; rolled back (with a toast) when the server refuses. */
export const useTogglePin = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, id, label, pinned }: { kind: WatchKind; id: string; label?: string; pinned: boolean }) =>
      pinned ? api<{ pinned: boolean }>(path(kind, id), { method: "DELETE" }) : post<{ pinned: boolean }>("/watchlist", { kind, subject_id: id, label }),
    onMutate: async ({ kind, id, pinned }) => {
      await qc.cancelQueries({ queryKey: ["watch-pins"] });
      const before = qc.getQueryData<Pin[]>(["watch-pins"]);
      const rest = (before ?? []).filter((p) => !(p.kind === kind && p.subject_id === id));
      qc.setQueryData<Pin[]>(["watch-pins"], pinned ? rest : [...rest, { kind, subject_id: id }]);
      return { before };
    },
    onError: (e: { reason?: string }, _v, ctx) => {
      qc.setQueryData(["watch-pins"], ctx?.before);
      toast.error("Couldn't update your watchlist", { description: e.reason ?? "Nothing was changed. Try again." });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["watch-pins"] });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
};

export const useMarkSeen = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, id }: { kind: WatchKind; id: string }) => post(`${path(kind, id)}/seen`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
};

/** True once the Track pages exist (/track/<kind>/<id>): watchlist links go there, else to the existing screen. */
export const TRACK_ROUTE = Object.keys(import.meta.glob(["../pages/Track*.tsx", "../pages/track/**/*.tsx", "!../pages/**/*.test.tsx"])).length > 0;

export const KIND_LABEL: Record<WatchKind, string> = {
  customer: "Customer", case: "Case", agent: "Agent", employer: "Employer", cohort: "Cohort", data_product: "Data product", identity: "Identity",
};
