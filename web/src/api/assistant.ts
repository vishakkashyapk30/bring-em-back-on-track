import { useMutation, useQuery } from "@tanstack/react-query";

import { api, post } from "./client";

export type Evidence = {
  columns?: string[] | null; rows?: unknown[][] | null; kv?: string[][] | null; text?: string | null;
  links?: { label: string; href: string }[] | null;
};
export type StepStatus = "done" | "skipped" | "failed" | "needs_approval";
export type PlanStep = { id: string; tool: string; title: string; why: string };
export type RunStep = {
  id: string; tool: string; title: string; status: StepStatus; ms: number; summary: string; evidence?: Evidence;
  cites?: { doc_id: string; section: string }[] | null;
};
export type Proposal = { id: string; title: string; detail: string; kind: string; href: string; requires_role: string };
export type AssistantRun = {
  persona: string; goal: string; mode_used: "rules" | "language model"; mode_note?: string | null;
  plan: PlanStep[]; steps: RunStep[]; findings: string[]; proposals: Proposal[]; summary: string;
  audit_id?: number | null; case_id?: string | null; golden_id?: string | null;
  citations?: Record<string, unknown>[]; grounded?: boolean | null; model_turns?: number; tool_calls?: number | null;
  stop_reason?: string | null;
};
export type Goal = { label: string; goal: string };
export type Suggestions = { persona: string; briefing: Goal; goals: Goal[] };
export type RunBody = { goal?: string; case_id?: string; golden_id?: string; mode: "rules" | "llm" };

export type JourneyStage = {
  id: string; title: string; narrative: string; screen: string; tool?: string | null; why_it_matters: string;
  evidence?: Evidence; human_step?: string | null; status?: string | null; summary?: string | null; ms?: number | null;
};
export type Journey = {
  persona: string; title: string; intro: string; customer: { golden_id: string; case_id: string; name: string } | null;
  stages: JourneyStage[];
};

export const useAssistantSuggestions = (role?: string) =>
  useQuery({ queryKey: ["assistant-suggestions", role], queryFn: () => api<Suggestions>("/assistant/suggestions"), enabled: !!role, staleTime: 300_000 });
export const useAssistantRun = () => useMutation({ mutationFn: (body: RunBody) => post<AssistantRun>("/assistant/run", body) });
export const useJourney = (persona: string, enabled: boolean) =>
  useQuery({ queryKey: ["journey", persona], queryFn: () => api<Journey>(`/demo/journey/${persona}`), enabled, retry: false, staleTime: 120_000 });
