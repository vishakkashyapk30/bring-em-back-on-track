import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Button } from "@/components/Button";
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
      <Card className="max-w-xl">
        <h2 className="mt-0 text-[1.0625rem]">Which case do you want to model?</h2>
        <p className="text-[14.5px] text-muted">Open one from the Missed offers tab, or type a case ID.</p>
        <form onSubmit={(e) => { e.preventDefault(); if (typed.trim()) nav(`/hardship/simulator/${typed.trim()}`); }} className="flex gap-2">
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="CS-2026-123456" aria-label="Case ID" className="h-10 min-w-0 flex-1 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 font-mono text-[14px] outline-none focus:border-brand/50 focus:shadow-[var(--shadow-focus)]" />
          <Button type="submit" variant="primary">Open</Button>
        </form>
      </Card>
    );
  return <SimulatorPanel key={caseId} caseId={caseId} initialProgram={sp.get("program")} />;
}
