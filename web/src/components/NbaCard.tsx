import { CalendarClock, CheckCircle2, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useDecide } from "@/api/hooks";
import type { Alternative, NbaProposal } from "@/api/types";

import { Badge } from "./Badge";
import { Button } from "./Button";
import { Card } from "./Card";
import { ExplainAccordion } from "./ExplainAccordion";
import { OverrideDialog } from "./OverrideDialog";
import { SampleBadge } from "./States";
import { actionLabel } from "@/lib/labels";

const ReasonList = ({ items }: { items: { code: string; text: string }[] }) => (
  <ul className="m-0 space-y-1 pl-5">{items.map((r) => <li key={r.code}>{r.text}</li>)}</ul>
);



const label = actionLabel;
const DECIDED: Record<string, string> = { approve: "approved", edit: "changed", override: "overridden" };

/** Edit = pick another action the contact rules allow. Rules that block an option are shown, not hidden. */
function EditDialog({ open, options, onClose, onPick }: { open: boolean; options: Alternative[]; onClose: () => void; onPick: (a: Alternative["action"]) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (open) ref.current?.showModal(); else ref.current?.close(); }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-full max-w-lg rounded-[var(--radius-lg)] border border-grey-300/70 p-6 shadow-[var(--shadow-raised)]">
      <h3 className="mt-0">Choose a different action</h3>
      <p className="mt-0 text-[14px] text-muted">Only actions the contact rules allow can be picked.</p>
      <ul className="m-0 list-none space-y-2 p-0">
        {options.map((o, i) => (
          <li key={i}>
            <button type="button" disabled={!o.allowed} onClick={() => onPick(o.action)}
              className="w-full rounded-[var(--radius-md)] border border-grey-300 bg-white p-3 text-left transition-colors enabled:hover:border-brand enabled:hover:bg-brand-50/40 disabled:cursor-not-allowed disabled:bg-grey-100 disabled:text-muted">
              <span className="block font-medium">{label(o.action)}</span>
              <span className="block text-[13px] text-muted">{o.allowed ? "Allowed" : o.why_not}</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex justify-end"><Button onClick={onClose}>Cancel</Button></div>
    </dialog>
  );
}

/** The NBA card: recommendation + deterministic explanation + Approve / Edit / Override.
 * Keyboard: A approve, O override. */
export function NbaCard({ proposal, sample = false }: { proposal: NbaProposal; sample?: boolean }) {
  const ex = proposal.explanation;
  const me = ex.model_evidence;
  const decide = useDecide(proposal.case_id);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const done = proposal.decision;
  const noAction = proposal.action.treatment === "no_contact";
  const locked = !!done || noAction;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName.match(/INPUT|TEXTAREA|SELECT/) || locked || e.metaKey || e.ctrlKey) return;
      if (e.key === "a") decide.mutate({ decision: "approve" });
      if (e.key === "o") setOverrideOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [decide, locked]);

  return (
    <Card hard className="p-6">
      <div className="mb-1 flex items-center justify-between gap-3">
        <span className="text-[14px] font-semibold text-brand">Suggested next step</span>
        {sample && <SampleBadge />}
      </div>
      <h3 className="mb-3 mt-1 text-[1.25rem] leading-snug">{ex.recommendation}</h3>

      <ul className="mb-5 mt-0 flex list-none flex-wrap gap-x-5 gap-y-1 p-0 text-[13.5px] text-muted">
        {proposal.status === "deferred" && <li className="inline-flex items-center gap-1.5"><CalendarClock size={15} aria-hidden /> {proposal.deferred_reason ?? "Moved to tomorrow"}</li>}
        {proposal.route_to === "hardship_specialist" && <li className="inline-flex items-center gap-1.5"><Users size={15} aria-hidden /> A hardship specialist will take this one</li>}
        {proposal.review_mode === "batch" && <li className="inline-flex items-center gap-1.5"><Users size={15} aria-hidden /> A routine reminder, so your team lead approves it in a batch</li>}
      </ul>

      <ExplainAccordion
        defaultOpen={1}
        items={[
          { title: "Rules we checked", body: <ReasonList items={ex.rules_applied} /> },
          {
            title: "How likely a broken promise is",
            meta: me.p_break != null ? <Badge kind="model-estimate">{Math.round(me.p_break * 100)}% chance the promise breaks (an estimate)</Badge> : <Badge kind="neutral">Not scored</Badge>,
            body: me.p_break != null
              ? <><p className="mt-0">The risk is {me.band?.replace("_", " ")}. These things push it up or down:</p><ReasonList items={me.drivers} /></>
              : <p className="m-0">There is no promise to score here, so the suggestion comes from the contact rules alone.</p>,
          },
          { title: "What's changed", body: ex.what_changed.length ? <ReasonList items={ex.what_changed} /> : <p className="m-0">Nothing new since the last review.</p> },
          { title: "How fresh the data is", body: <p className="m-0">{ex.freshness.text}</p> },
          { title: "Other options we looked at", body: <ul className="m-0 pl-5">{ex.alternatives.map((a, i) => <li key={i}><b>{label(a.action)}</b>: {a.why_not}</li>)}</ul> },
        ]}
      />

      {done ? (
        <p role="status" className="mb-0 mt-5 inline-flex items-center gap-2 text-[14.5px] text-teal">
          <CheckCircle2 size={18} aria-hidden /> You {DECIDED[done.decision] ?? done.decision} this action{done.ts ? ` on ${new Date(done.ts).toLocaleDateString("en-CA", { day: "numeric", month: "short" })}` : ""}. It's in the audit log.
        </p>
      ) : noAction ? (
        <p className="mb-0 mt-5 text-[14.5px] text-muted">Nothing to send today, so there's nothing to approve.</p>
      ) : (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={() => decide.mutate({ decision: "approve" })} disabled={decide.isPending}>Approve (A)</Button>
          <Button onClick={() => setEditOpen(true)}>Change action</Button>
          <Button onClick={() => setOverrideOpen(true)}>Override (O)</Button>
        </div>
      )}

      <EditDialog open={editOpen} options={ex.alternatives} onClose={() => setEditOpen(false)}
        onPick={(action) => { decide.mutate({ decision: "edit", action }); setEditOpen(false); }} />
      <OverrideDialog open={overrideOpen} onClose={() => setOverrideOpen(false)}
        onSubmit={(reason_code, note) => { decide.mutate({ decision: "override", reason_code, note }); setOverrideOpen(false); }} />
    </Card>
  );
}
