import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Card } from "@/components/Card";
import { SimulatorPanel } from "@/components/SimulatorPanel";

/** Plan simulator for one case. Pick a case from "Missed offers" (or paste a case ID) to start. */
export default function Simulator() {
  const { caseId = "" } = useParams();
  const [sp] = useSearchParams();
  const [typed, setTyped] = useState("");
  const nav = useNavigate();
  if (!caseId || caseId === "start")
    return (
      <Card variant="grey" className="max-w-xl">
        <p className="mt-0 font-medium">Which case do you want to model?</p>
        <p className="text-[14.5px] text-muted">Open one from the Missed offers tab, or type a case ID.</p>
        <form onSubmit={(e) => { e.preventDefault(); if (typed.trim()) nav(`/hardship/simulator/${typed.trim()}`); }} className="flex gap-2">
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="CS-2026-123456" aria-label="Case ID" className="h-10 flex-1 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 font-mono" />
          <button type="submit" className="h-10 rounded-[var(--radius-md)] bg-brand px-4 font-medium text-white">Open</button>
        </form>
      </Card>
    );
  return <SimulatorPanel key={caseId} caseId={caseId} initialProgram={sp.get("program")} />;
}
