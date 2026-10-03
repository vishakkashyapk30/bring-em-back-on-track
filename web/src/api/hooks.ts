import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, post } from "./client";
import type { AskResponse, NbaProposal, QueueResponse, Role, Session } from "./types";

// Generic loose type for endpoints still on fixtures; tighten as `make types` lands.
type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => api<Session>("/me"), retry: false });
export const useLogin = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (role: Role) => post<Session>(`/auth/session?role=${role}`),
    onSuccess: () => qc.invalidateQueries(),
  });
};

export type QueueParams = { view: string; sort: string; q: string; limit: number };
export const useQueue = (p: QueueParams = { view: "all", sort: "priority", q: "", limit: 50 }) =>
  useQuery({
    queryKey: ["queue", p],
    queryFn: () => api<QueueResponse>(`/queue?${new URLSearchParams({ view: p.view, sort: p.sort, q: p.q, limit: String(p.limit) })}`),
    placeholderData: keepPreviousData, // keep the old rows on screen while the next ones load, so the list never flashes
  });
export const useCustomer = (id: string) => useQuery({ queryKey: ["customer", id], queryFn: () => api<Json>(`/customers/${id}`) });
export const useTimeline = (id: string) => useQuery({ queryKey: ["timeline", id], queryFn: () => api<Json>(`/customers/${id}/timeline`) });
export const useIdentity = (id: string) => useQuery({ queryKey: ["identity", id], queryFn: () => api<Json>(`/customers/${id}/identity`) });
export const useNba = (caseId?: string) =>
  useQuery({ queryKey: ["nba", caseId], queryFn: () => api<NbaProposal>(`/nba/${caseId}`), enabled: !!caseId });
export const useEligibility = (caseId?: string) =>
  useQuery({ queryKey: ["elig", caseId], queryFn: () => api<Json>(`/eligibility/${caseId}`), enabled: !!caseId });
const DECISION_TEXT: Record<string, string> = { approve: "Action approved", override: "Override saved", edit: "Edit saved" };
export const useDecide = (caseId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Json) => post<{ audit_id: number }>(`/nba/${caseId}/decision`, body),
    onSuccess: (r, body) => {
      toast.success(DECISION_TEXT[body.decision] ?? "Saved", { description: `Recorded in the audit log (#${r.audit_id}).` });
      qc.invalidateQueries({ queryKey: ["nba", caseId] });
      qc.invalidateQueries({ queryKey: ["queue"] });
    },
    onError: (e: { reason?: string }) => toast.error("Couldn't save the decision", { description: e.reason ?? "Nothing was changed. Try again." }),
  });
};
export const useWhatIf = () => useMutation({ mutationFn: (body: Json) => post<Json>("/nba/what-if", body) });
export const useAsk = () => useMutation({ mutationFn: (question: string) => post<AskResponse>("/ask", { question }) });
export const usePolicyAnswer = () => useMutation({ mutationFn: (question: string) => post<Json>("/assist/policy", { question }) });
export const useCallSummary = (cid: string) => useQuery({ queryKey: ["summary", cid], queryFn: () => api<Json>(`/calls/${cid}/summary`) });
export const useTranscript = (cid: string) => useQuery({ queryKey: ["transcript", cid], queryFn: () => api<Json>(`/calls/${cid}/transcript`) });
export const useGet = (key: string, path: string) => useQuery({ queryKey: [key, path], queryFn: () => api<Json>(path) });
export const useSimulate = (caseId: string) => useMutation({ mutationFn: (levers: Json) => post<Json>(`/simulator/${caseId}`, levers) });
export const useFlag = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ golden_id, ...body }: Json) => post<{ audit_id: number }>(`/hardship/${golden_id}/flag`, body),
    onSuccess: (r) => {
      toast.success("Hardship flag updated", { description: `Recorded in the audit log (#${r.audit_id}).` });
      qc.invalidateQueries({ queryKey: ["hboard"] });
    },
    onError: (e: { reason?: string }) => toast.error("Couldn't change the flag", { description: e.reason ?? "Nothing was changed." }),
  });
};
export const useApproveBatch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post<{ audit_id: number }>(`/batches/${id}/approve`),
    onSuccess: (r) => {
      toast.success("Batch approved", { description: `Recorded in the audit log (#${r.audit_id}).` });
      qc.invalidateQueries({ queryKey: ["batches"] });
    },
    onError: () => toast.error("Couldn't approve the batch", { description: "It may already be approved." }),
  });
};
export const useStressTest = () => useMutation({ mutationFn: (body: Json) => post<Json>("/stress-test", body) });
