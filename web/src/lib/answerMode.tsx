import clsx from "clsx";
import { Brain, ListChecks } from "lucide-react";
import { useCallback, useSyncExternalStore } from "react";

import { useHealth } from "@/api/hooks";

export type AnswerMode = "rules" | "llm";
const KEY = "bot-answer-mode";
const EVENT = "bot-answer-mode-change";

function read(): AnswerMode {
  try { return localStorage.getItem(KEY) === "llm" ? "llm" : "rules"; } catch { return "rules"; }
}

/** The person's choice between deterministic rules and a language model, kept in this browser and shared by every screen. */
export function useAnswerMode(): [AnswerMode, (m: AnswerMode) => void] {
  const mode = useSyncExternalStore(
    (cb) => { window.addEventListener(EVENT, cb); window.addEventListener("storage", cb); return () => { window.removeEventListener(EVENT, cb); window.removeEventListener("storage", cb); }; },
    read, () => "rules" as AnswerMode);
  const set = useCallback((m: AnswerMode) => { try { localStorage.setItem(KEY, m); } catch { /* private mode: keep in memory only */ } window.dispatchEvent(new Event(EVENT)); }, []);
  return [mode, set];
}

/** What the server can offer: is a language model configured and reachable? */
export function useLlmStatus() {
  const h = useHealth();
  const llm = (h.data as { llm?: { available?: boolean; model?: string | null; provider?: string; reason?: string } } | undefined)?.llm;
  return { available: !!llm?.available, model: llm?.model ?? null, provider: llm?.provider ?? "offline", reason: llm?.reason ?? "", loading: h.isLoading };
}

/** Two-way switch: Rules (same answer every time) or Language model (understands unusual wording). */
export function ModeSwitch({ className }: { className?: string }) {
  const [mode, setMode] = useAnswerMode();
  const llm = useLlmStatus();
  const effective: AnswerMode = mode === "llm" && llm.available ? "llm" : "rules";
  const opt = (value: AnswerMode, label: string, icon: JSX.Element, disabled = false, title?: string) => (
    <button type="button" aria-pressed={effective === value} disabled={disabled} title={title} onClick={() => setMode(value)}
      className={clsx("inline-flex h-8 items-center gap-1.5 rounded-[7px] px-3 text-[14px] font-medium transition-colors",
        effective === value ? "bg-ink text-white" : "text-muted hover:text-ink", disabled && "cursor-not-allowed opacity-50 hover:text-muted")}>
      {icon}{label}
    </button>
  );
  return (
    <div className={clsx("flex flex-wrap items-center gap-3", className)}>
      <div role="group" aria-label="How questions are understood" className="inline-flex rounded-[var(--radius-md)] border border-grey-300/70 bg-white p-1 shadow-[var(--shadow-card)]">
        {opt("rules", "Rules", <ListChecks size={15} aria-hidden />, false, "Deterministic rules: the same answer every time, no model.")}
        {opt("llm", "Language model", <Brain size={15} aria-hidden />, !llm.available, llm.available ? `Understands unusual wording (${llm.model ?? llm.provider}). SQL still comes from certified rules.` : llm.reason || "No language model is available.")}
      </div>
      <p className="m-0 text-[13px] text-muted">
        {effective === "llm" ? `Language model: ${llm.model ?? llm.provider}. It picks the certified metric or words the policy answer; rules still write the SQL and check every quote.`
          : llm.available ? "Rules only: the same answer every time." : `Rules only. ${llm.reason}`}
      </p>
    </div>
  );
}
