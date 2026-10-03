import type { Role } from "@/api/types";
import type { RunStep, StepStatus } from "@/api/assistant";

export const ROLE_LABEL: Record<string, string> = {
  agent: "Collections agent", hardship_specialist: "Hardship specialist", team_lead: "Team lead",
  analyst: "Strategy analyst", steward: "Data steward",
};
export const ROLES: Role[] = ["agent", "hardship_specialist", "team_lead", "analyst", "steward"];

/** The demo route for a persona is /demo/<role>; anything that is not a known role maps to null. */
export const personaFromParam = (p?: string): Role | null => (ROLES as string[]).includes(p ?? "") ? (p as Role) : null;
export const demoPath = (role: string, stage?: number) => `/demo/${role}${stage ? `?stage=${stage}` : ""}`;

/** What the current screen tells the assistant: a customer page gives golden_id, a case route gives case_id. */
export function contextFromPath(pathname: string, search = ""): { golden_id?: string; case_id?: string } {
  let m = pathname.match(/^\/customers\/([^/]+)/);
  if (m) return { golden_id: decodeURIComponent(m[1]) };
  m = pathname.match(/^\/hardship\/simulator\/([^/]+)/);
  if (m) return { case_id: decodeURIComponent(m[1]) };
  if (pathname === "/queue") {
    const c = new URLSearchParams(search).get("case");
    if (c) return { case_id: c };
  }
  return {};
}

export const REVEAL_GAP_MS = 250;
/** Delay before each step appears: the first at once, then one every `gap` ms. Instant under reduced motion. */
export const revealDelays = (count: number, gap = REVEAL_GAP_MS, reduced = false): number[] =>
  Array.from({ length: count }, (_, i) => (reduced ? 0 : i * gap));
/** How many steps are visible after `elapsed` ms. */
export const visibleSteps = (elapsed: number, count: number, gap = REVEAL_GAP_MS, reduced = false): number =>
  reduced ? count : Math.min(count, Math.floor(Math.max(0, elapsed) / gap) + 1);

export const STATUS_LABEL: Record<StepStatus, string> = {
  done: "Done", skipped: "Skipped", failed: "Could not run", needs_approval: "Needs your approval",
};
export const statusLabel = (s: StepStatus) => STATUS_LABEL[s] ?? s;
export const stepsByStatus = (steps: RunStep[], s: StepStatus) => steps.filter((x) => x.status === s);

/** Stage navigation: 0-based index, clamped. */
export const clampStage = (i: number, total: number) => Math.max(0, Math.min(total - 1, i));
export const stageLabel = (i: number, total: number) => `Stage ${i + 1} of ${total}`;
export const stageFromKey = (key: string, i: number, total: number): number | null => {
  if (key === "ArrowRight") return i < total - 1 ? i + 1 : null;
  if (key === "ArrowLeft") return i > 0 ? i - 1 : null;
  if (key === "Home") return 0;
  if (key === "End") return total - 1;
  return null;
};
export const progressPct = (i: number, total: number) => Math.round(((i + 1) / total) * 100);
/** Stages that are about the one customer view, where the identity picture is shown. */
export const isCustomerStage = (id: string) => id === "customer" || id === "lineage";

/** Short display for a cell: numbers rounded to at most 3 decimals, empty as n/a. */
export const cell = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "n/a";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-CA") : String(Math.round(v * 1000) / 1000);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
};
