import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, post } from "./client";
import type { AskResponse, NbaProposal, QueueItem, Role, Session } from "./types";

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

export const useQueue = () => useQuery({ queryKey: ["queue"], queryFn: () => api<{ items: QueueItem[] } & Json>("/queue") });
export const useCustomer = (id: string) => useQuery({ queryKey: ["customer", id], queryFn: () => api<Json>(`/customers/${id}`) });
export const useTimeline = (id: string) => useQuery({ queryKey: ["timeline", id], queryFn: () => api<Json>(`/customers/${id}/timeline`) });
export const useIdentity = (id: string) => useQuery({ queryKey: ["identity", id], queryFn: () => api<Json>(`/customers/${id}/identity`) });
export const useNba = (caseId?: string) =>
  useQuery({ queryKey: ["nba", caseId], queryFn: () => api<NbaProposal>(`/nba/${caseId}`), enabled: !!caseId });
export const useEligibility = (caseId?: string) =>
  useQuery({ queryKey: ["elig", caseId], queryFn: () => api<Json>(`/eligibility/${caseId}`), enabled: !!caseId });
export const useDecide = (caseId: string) =>
  useMutation({ mutationFn: (body: Json) => post<{ audit_id: number }>(`/nba/${caseId}/decision`, body) });
export const useWhatIf = () => useMutation({ mutationFn: (body: Json) => post<Json>("/nba/what-if", body) });
export const useAsk = () => useMutation({ mutationFn: (question: string) => post<AskResponse>("/ask", { question }) });
export const usePolicyAnswer = () => useMutation({ mutationFn: (question: string) => post<Json>("/assist/policy", { question }) });
export const useCallSummary = (cid: string) => useQuery({ queryKey: ["summary", cid], queryFn: () => api<Json>(`/calls/${cid}/summary`) });
export const useTranscript = (cid: string) => useQuery({ queryKey: ["transcript", cid], queryFn: () => api<Json>(`/calls/${cid}/transcript`) });
export const useGet = (key: string, path: string) => useQuery({ queryKey: [key, path], queryFn: () => api<Json>(path) });
export const useSimulate = (caseId: string) => useMutation({ mutationFn: (levers: Json) => post<Json>(`/simulator/${caseId}`, levers) });
