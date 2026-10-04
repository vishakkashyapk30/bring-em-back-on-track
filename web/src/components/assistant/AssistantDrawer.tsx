import { Loader2, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useLocation } from "react-router-dom";

import { useAssistantRun, useAssistantSuggestions, type AssistantRun } from "@/api/assistant";
import { useMe } from "@/api/hooks";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/States";
import { ModeSwitch, useAnswerMode, useLlmStatus } from "@/lib/answerMode";

import { useAssistant } from "./AssistantContext";
import { contextFromPath, ROLE_LABEL } from "./helpers";
import { RunView } from "./RunView";

const FOCUSABLE = 'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/** Launcher for the header: opens the assistant drawer. */
export function AssistantLauncher() {
  const { open, isOpen, launcherRef } = useAssistant();
  return (
    <button ref={launcherRef} type="button" onClick={() => open()} aria-haspopup="dialog" aria-expanded={isOpen}
      className="mr-3 inline-flex h-10 items-center gap-2 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[15px] font-medium text-ink transition-colors hover:border-ink/40 hover:bg-grey-100 sm:px-4">
      <Sparkles size={17} aria-hidden className="text-brand" /><span className="hidden sm:inline">Assistant</span><span className="sr-only sm:hidden">Assistant</span>
    </button>
  );
}

/** Right-hand drawer, the same on every persona page. Runs the tools the persona's role may use and shows each step. */
export function AssistantDrawer() {
  const { isOpen, close, preset, clearPreset, launcherRef } = useAssistant();
  const me = useMe();
  const role = me.data?.role;
  const loc = useLocation();
  const [mode] = useAnswerMode();
  const llm = useLlmStatus();
  const sugg = useAssistantSuggestions(role);
  const run = useAssistantRun();
  const [goal, setGoal] = useState("");
  const [result, setResult] = useState<AssistantRun | null>(null);
  const [ignoreRoute, setIgnoreRoute] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const resultTop = useRef<HTMLDivElement>(null);

  // Where the person is: the preset (from the demo) wins over what the current route says.
  const routeCtx = ignoreRoute ? {} : contextFromPath(loc.pathname, loc.search);
  const ctx = preset ? { case_id: preset.caseId, golden_id: preset.goldenId } : routeCtx;
  const ctxLabel = preset?.label ?? ctx.golden_id ?? ctx.case_id;
  useEffect(() => setIgnoreRoute(false), [loc.pathname]);

  useEffect(() => {
    if (!isOpen) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    return () => { (launcherRef.current ?? prev)?.focus(); };
  }, [isOpen, launcherRef]);

  const start = (g?: string) => {
    setResult(null);
    run.mutate({ goal: g || undefined, case_id: ctx.case_id, golden_id: ctx.golden_id, mode: mode === "llm" && llm.available ? "llm" : "rules" },
      { onSuccess: (r) => { setResult(r); setTimeout(() => resultTop.current?.scrollIntoView?.({ block: "start", behavior: "smooth" }), 50); } });
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); return; }
    if (e.key !== "Tab" || !panel.current) return;
    const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement);
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  if (!isOpen || !role) return null;
  const err = run.error as { reason?: string; status?: number } | null;
  return (
    <div className="fixed inset-0 z-50" onKeyDown={onKey}>
      <div className="fade-in absolute inset-0 bg-ink/35" onClick={close} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="assistant-h"
        className="absolute right-0 top-0 flex h-full w-full max-w-[520px] flex-col border-l border-grey-300 bg-cream shadow-[var(--shadow-raised)]">
        <header className="flex items-start gap-3 border-b border-grey-300/70 bg-white px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 id="assistant-h" className="m-0 text-[1.5rem] leading-tight">Assistant</h2>
            <p className="m-0 text-[14px] text-muted">{me.data?.display_name}, {ROLE_LABEL[role] ?? role}. Runs on rules; a language model helps when it is on.</p>
          </div>
          <button type="button" onClick={close} aria-label="Close the assistant" data-autofocus
            className="inline-flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)] text-ink hover:bg-grey-100"><X size={20} aria-hidden /></button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <ModeSwitch />
          {ctxLabel && (
            <p className="m-0 flex flex-wrap items-center gap-2 rounded-[var(--radius-md)] bg-brand-50 px-3 py-2 text-[14px]">
              <span>Working on <span className="font-semibold">{preset?.label ?? (ctx.golden_id ? `customer ${ctx.golden_id}` : `case ${ctx.case_id}`)}</span></span>
              <button type="button" onClick={() => { clearPreset(); setIgnoreRoute(true); }} className="font-semibold text-brand underline-offset-4 hover:underline">Use my whole queue instead</button>
            </p>
          )}

          <div>
            <Button variant="primary" size="lg" className="w-full" disabled={run.isPending} onClick={() => start()}>
              {run.isPending ? <Loader2 size={18} className="animate-spin" aria-hidden /> : <Sparkles size={18} aria-hidden />}Run my briefing
            </Button>
            <p className="m-0 mt-1.5 text-[13px] text-muted">{sugg.data?.briefing.goal ?? "A short tour of what needs you today."}</p>
          </div>

          <section aria-labelledby="goals-h">
            <h3 id="goals-h" className="m-0 mb-2 font-[family-name:var(--font-sans)] text-[13px] font-semibold text-muted">Or pick a goal</h3>
            {sugg.isLoading ? <p role="status" className="m-0 text-[14px] text-muted">Loading goals for your role...</p>
              : sugg.isError ? <p className="m-0 text-[14px] text-muted">Goals could not load. You can still type your own below.</p>
              : (
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                  {sugg.data?.goals.map((g) => (
                    <li key={g.label}>
                      <button type="button" disabled={run.isPending} title={g.goal} onClick={() => { setGoal(g.goal); start(g.goal); }}
                        className="rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 py-1.5 text-left text-[14px] text-ink transition-colors hover:border-ink/40 hover:bg-grey-100 disabled:opacity-50">{g.label}</button>
                    </li>
                  ))}
                </ul>
              )}
          </section>

          <form onSubmit={(e) => { e.preventDefault(); if (goal.trim()) start(goal.trim()); }}>
            <label htmlFor="assistant-goal" className="mb-1.5 block text-[13px] font-semibold text-muted">Or say what you need</label>
            <div className="flex gap-2">
              <input id="assistant-goal" value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={500} placeholder="For example: is this promise safe before payday?"
                className="h-10 min-w-0 flex-1 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[15px] outline-none focus:border-brand/50 focus:shadow-[var(--shadow-focus)]" />
              <Button type="submit" disabled={run.isPending || !goal.trim()}>Run</Button>
            </div>
          </form>

          <div ref={resultTop} className="scroll-mt-2">
            {run.isPending && <p role="status" className="m-0 flex items-center gap-2 text-[14px] text-muted"><Loader2 size={16} className="animate-spin" aria-hidden />Working through the plan. This can take a few seconds.</p>}
            {run.isError && <ErrorState title="The assistant could not finish" detail={err?.reason ?? (err?.status === 403 ? "You do not have access to that case." : "Nothing was changed. Check your connection and try again.")} />}
            {result && !run.isPending && <RunView run={result} onNavigate={close} />}
            {!result && !run.isPending && !run.isError && (
              <p className="m-0 text-[14px] text-muted">Nothing run yet. Start with the briefing, or pick a goal. Each step is shown with its evidence, and anything that changes a customer waits for a person to approve it.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
