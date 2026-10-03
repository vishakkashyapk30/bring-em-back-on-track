import { useState } from "react";

import { useSimulate } from "@/api/hooks";

import { Badge } from "./Badge";
import { Card } from "./Card";

/** H1 plan simulator: levers within program limits -> 4 result cards + stated assumptions.
 * TODO(WS-G): limits from the program, "outside program rules" state, scenario compare. */
export function SimulatorPanel({ caseId }: { caseId: string }) {
  const [levers, setLevers] = useState({ payment_reduction_pct: 0.5, term_extension_months: 0, payment_holiday_months: 0, fee_waiver: true });
  const sim = useSimulate(caseId);
  const r = sim.data?.results;
  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <Card variant="grey">
        <h3 className="mt-0">Levers</h3>
        <label className="block">Payment cut {Math.round(levers.payment_reduction_pct * 100)}%
          <input type="range" min={0} max={1} step={0.05} value={levers.payment_reduction_pct} onChange={(e) => setLevers({ ...levers, payment_reduction_pct: +e.target.value })} className="w-full accent-[var(--color-brand)]" /></label>
        <label className="block">Term extension {levers.term_extension_months} months
          <input type="range" min={0} max={24} value={levers.term_extension_months} onChange={(e) => setLevers({ ...levers, term_extension_months: +e.target.value })} className="w-full accent-[var(--color-brand)]" /></label>
        <label className="block">Payment holiday {levers.payment_holiday_months} months
          <input type="range" min={0} max={3} value={levers.payment_holiday_months} onChange={(e) => setLevers({ ...levers, payment_holiday_months: +e.target.value })} className="w-full accent-[var(--color-brand)]" /></label>
        <label className="mt-2 flex items-center gap-2"><input type="checkbox" checked={levers.fee_waiver} onChange={(e) => setLevers({ ...levers, fee_waiver: e.target.checked })} /> Waive fees</label>
        <button type="button" onClick={() => sim.mutate(levers)} className="mt-4 w-full rounded-[var(--radius-md)] bg-brand px-4 py-3 text-white">Run scenario</button>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {r ? (<>
          <Card><p className="m-0 text-sm text-muted">New payment vs monthly surplus</p><p className="m-0 text-3xl tabular">${r.new_payment} / ${r.surplus}</p><p className="m-0">{Math.round(r.payment_share_of_surplus * 100)}% of surplus</p></Card>
          <Card><p className="m-0 text-sm text-muted">Months to clear · total interest</p><p className="m-0 text-3xl tabular">{r.months_to_clear} mo · ${r.total_interest}</p><p className="m-0 text-muted">now {r.months_to_clear_current} mo · ${r.total_interest_current}</p></Card>
          <Card><p className="m-0 text-sm text-muted">Bank impact vs doing nothing</p><p className="m-0 text-3xl tabular">${r.bank_impact_vs_status_quo}</p></Card>
          <Card><p className="m-0 text-sm text-muted">Similar plans that held</p><p className="m-0 text-3xl tabular">{Math.round(r.hold_rate_similar.value * 100)}%</p><Badge kind="observed">{r.hold_rate_similar.label} · n={r.hold_rate_similar.n}</Badge></Card>
          <Card variant="grey" className="md:col-span-2 text-sm">Assumptions (not in the data): discount rate {sim.data?.assumptions.annual_discount_rate * 100}%, LGD {sim.data?.assumptions.lgd * 100}%. Approver: {sim.data?.approver_level}.</Card>
        </>) : <Card variant="grey" className="md:col-span-2">Move the levers and run a scenario. Every run is logged.</Card>}
      </div>
    </div>
  );
}
