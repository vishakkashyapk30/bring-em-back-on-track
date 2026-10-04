import { AlertTriangle, Bot, CheckCircle2, CircleSlash, UserCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import type { AssistantRun, RunStep, StepStatus } from "@/api/assistant";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { Sources } from "@/components/Sources";

import { EvidenceToggle } from "./EvidenceView";
import { REVEAL_GAP_MS, ROLE_LABEL, statusLabel, visibleSteps } from "./helpers";
import { useReducedMotion } from "./useReducedMotion";

const ICON: Record<StepStatus, JSX.Element> = {
  done: <CheckCircle2 size={18} aria-hidden className="text-teal" />,
  skipped: <CircleSlash size={18} aria-hidden className="text-muted" />,
  failed: <AlertTriangle size={18} aria-hidden className="text-danger" />,
  needs_approval: <UserCheck size={18} aria-hidden className="text-amber" />,
};
const TEXT: Record<StepStatus, string> = { done: "text-teal", skipped: "text-muted", failed: "text-danger", needs_approval: "text-amber" };

/** Reveals steps one at a time (instantly when the person prefers reduced motion). */
export function useRevealed(count: number, key: unknown, gap = REVEAL_GAP_MS): number {
  const reduced = useReducedMotion();
  const [n, setN] = useState(() => visibleSteps(0, count, gap, reduced));
  useEffect(() => {
    setN(visibleSteps(0, count, gap, reduced));
    if (reduced || count <= 1) return;
    const t0 = Date.now();
    const id = window.setInterval(() => {
      const v = visibleSteps(Date.now() - t0, count, gap, false);
      setN(v);
      if (v >= count) window.clearInterval(id);
    }, gap / 2);
    return () => window.clearInterval(id);
  }, [count, key, gap, reduced]);
  return n;
}

function StepRow({ s, index }: { s: RunStep; index: number }) {
  return (
    <li className="fade-in group relative flex gap-3 pb-4 last:pb-0">
      <span aria-hidden className="absolute left-[8.5px] top-6 h-[calc(100%-1.5rem)] w-px bg-grey-300 group-last:hidden" />
      <span className="mt-0.5 shrink-0">{ICON[s.status]}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <h4 className="m-0 font-[family-name:var(--font-sans)] text-[15px] font-semibold">{index + 1}. {s.title}</h4>
          <span className={`text-[13px] font-semibold ${TEXT[s.status]}`}>{statusLabel(s.status)}</span>
          <span className="text-[12px] tabular-nums text-muted">{s.ms} ms</span>
        </div>
        <p className="m-0 mt-0.5 text-[14.5px] leading-snug text-ink/90">{s.summary}</p>
        {s.cites && s.cites.length > 0 && (
          <ul aria-label="Sources" className="m-0 mt-1.5 flex list-none flex-wrap gap-1.5 p-0">
            {s.cites.map((c) => <li key={c.doc_id + c.section} className="rounded-[var(--radius-sm)] bg-grey-100 px-2 py-0.5 text-[12px] text-muted">{c.doc_id}, {c.section}</li>)}
          </ul>
        )}
        <EvidenceToggle evidence={s.evidence} id={`ev-${s.id}`} />
      </div>
    </li>
  );
}

/** The result of one run: plan, steps revealed in order, findings, proposals, mode and audit number. */
export function RunView({ run, onNavigate }: { run: AssistantRun; onNavigate?: () => void }) {
  const shown = useRevealed(run.steps.length, run);
  const complete = shown >= run.steps.length;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {run.mode_used === "rules" ? <Badge kind="sql">Run by rules</Badge> : <Badge kind="llm">Worded by a language model</Badge>}
        {run.audit_id != null && <span className="text-[13px] text-muted">Recorded in the audit log, <span className="tabular-nums">#{run.audit_id}</span></span>}
      </div>
      {run.mode_note && <p role="note" className="m-0 rounded-[var(--radius-md)] bg-grey-100 p-3 text-[13.5px] text-muted"><Bot size={14} aria-hidden className="mr-1.5 inline" />{run.mode_note}</p>}

      <section aria-labelledby="plan-h">
        <h3 id="plan-h" className="m-0 mb-1.5 font-[family-name:var(--font-display)] text-[20px] font-semibold">I will:</h3>
        <ol className="m-0 list-decimal space-y-1 pl-5 text-[14.5px]">
          {run.plan.map((p) => <li key={p.id}><span className="font-medium">{p.title}.</span> <span className="text-muted">{p.why}</span></li>)}
        </ol>
      </section>

      <section aria-labelledby="steps-h">
        <h3 id="steps-h" className="m-0 mb-2 font-[family-name:var(--font-display)] text-[20px] font-semibold">What I did</h3>
        <ol aria-live="polite" aria-relevant="additions" className="m-0 list-none p-0">
          {run.steps.slice(0, shown).map((s, i) => <StepRow key={s.id} s={s} index={i} />)}
        </ol>
        {!complete && <p role="status" className="m-0 mt-2 text-[13px] text-muted">Working through step {shown + 1} of {run.steps.length}...</p>}
      </section>

      {complete && (
        <>
          {run.findings.length > 0 && (
            <section aria-labelledby="found-h" className="fade-in">
              <h3 id="found-h" className="m-0 mb-1.5 font-[family-name:var(--font-display)] text-[20px] font-semibold">What I found</h3>
              <ul className="m-0 list-disc space-y-1 pl-5 text-[14.5px]">{run.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </section>
          )}
          <p className="fade-in m-0 rounded-[var(--radius-md)] border-l-4 border-l-brand bg-grey-100 p-3 text-[14.5px]"><span className="font-semibold">In short: </span>{run.summary}</p>
          <Sources citations={run.citations} />
          <section aria-labelledby="prop-h" className="fade-in">
            <h3 id="prop-h" className="m-0 mb-1.5 font-[family-name:var(--font-display)] text-[20px] font-semibold">For you to approve</h3>
            {run.proposals.length === 0 ? (
              <p className="m-0 text-[14.5px] text-muted">Nothing needs your approval from this run.</p>
            ) : (
              <ul className="m-0 list-none space-y-2.5 p-0">
                {run.proposals.map((p) => (
                  <li key={p.id}>
                    <Card className="p-4">
                      <p className="m-0 text-[15px] font-semibold">{p.title}</p>
                      <p className="m-0 mt-1 text-[14px] text-muted">{p.detail}</p>
                      <p className="m-0 mt-1 text-[12.5px] text-muted">Approved by: {ROLE_LABEL[p.requires_role] ?? p.requires_role}</p>
                      <Link to={p.href} onClick={onNavigate} className="mt-3 inline-flex h-9 items-center rounded-[var(--radius-md)] border border-grey-300 bg-white px-4 text-[14px] font-medium text-ink no-underline hover:border-ink/40 hover:bg-grey-100 hover:no-underline">Review on the screen</Link>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
            <p className="m-0 mt-2 text-[13px] text-muted">Nothing is sent or changed until you approve it there.</p>
          </section>
        </>
      )}
    </div>
  );
}
