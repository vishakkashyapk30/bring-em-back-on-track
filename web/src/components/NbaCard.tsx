import { useEffect, useState } from "react";

import { useDecide } from "@/api/hooks";
import type { NbaProposal } from "@/api/types";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { ExplainAccordion } from "./ExplainAccordion";
import { OverrideDialog } from "./OverrideDialog";

const ReasonList = ({ items }: { items: { code: string; text: string }[] }) => (
  <ul className="m-0 space-y-1 pl-5">{items.map((r) => <li key={r.code}>{r.text}</li>)}</ul>
);

/** The NBA card: recommendation + deterministic explanation + Approve / Edit / Override.
 * Keyboard: A approve, O override. TODO(WS-G): Edit = pick another allowed action. */
export function NbaCard({ proposal }: { proposal: NbaProposal }) {
  const ex = proposal.explanation;
  const decide = useDecide(proposal.case_id);
  const [overrideOpen, setOverrideOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName.match(/INPUT|TEXTAREA|SELECT/)) return;
      if (e.key === "a") decide.mutate({ decision: "approve" });
      if (e.key === "o") setOverrideOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [decide]);

  return (
    <Card hard className="border-brand">
      <p className="m-0 text-sm text-muted">Recommended next best action</p>
      <h3 className="mt-1 mb-4 text-2xl font-medium">{ex.recommendation}</h3>
      <ExplainAccordion
        defaultOpen={1}
        items={[
          { title: "Rules applied", body: <ReasonList items={ex.rules_applied} /> },
          {
            title: "Model evidence",
            meta: <Badge kind="model-estimate">{ex.model_evidence.p_break.toFixed(2)} · {ex.model_evidence.label}</Badge>,
            body: <><p className="mt-0">Break risk {ex.model_evidence.band.replace("_", " ")}. Top drivers:</p><ReasonList items={ex.model_evidence.drivers} /></>,
          },
          { title: "What changed", body: <ReasonList items={ex.what_changed} /> },
          { title: "Data freshness", body: <p className="m-0">{ex.freshness.text}</p> },
          { title: "Alternatives considered", body: <ul className="m-0 pl-5">{ex.alternatives.map((a, i) => <li key={i}><b>{a.action.treatment.replace("_", " ")}</b>: {a.why_not}</li>)}</ul> },
        ]}
      />
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => decide.mutate({ decision: "approve" })} className="rounded-[var(--radius-md)] bg-brand px-5 py-3 font-medium text-white hover:bg-brand-700">Approve (A)</button>
        <button type="button" disabled className="rounded-[var(--radius-md)] border border-ink bg-white px-5 py-3" title="TODO">Edit</button>
        <button type="button" onClick={() => setOverrideOpen(true)} className="rounded-[var(--radius-md)] border border-ink bg-white px-5 py-3">Override… (O)</button>
        <span aria-live="polite" className="text-sm text-muted">
          {decide.isSuccess && `Saved · audit #${decide.data.audit_id}`}
          {decide.isError && "Couldn't save the decision"}
        </span>
      </div>
      <OverrideDialog open={overrideOpen} onClose={() => setOverrideOpen(false)}
        onSubmit={(reason_code, note) => { decide.mutate({ decision: "override", reason_code, note }); setOverrideOpen(false); }} />
    </Card>
  );
}
