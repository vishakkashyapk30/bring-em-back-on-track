import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useEligibility, useSimulate } from "@/api/hooks";

import { Badge } from "./Badge";
import { Button } from "./Button";
import { Card } from "./Card";
import { EmptyState } from "./States";

const cad = (n: unknown, d = 0) => (n == null ? "n/a" : Number(n).toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: d }));
const months = (n: unknown) => (n == null ? "more than 50 years" : `${n} months`);

function Slider({ label, value, min, max, step = 1, onChange, fmt }: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; fmt: (v: number) => string }) {
  return (
    <label className="mt-3 block text-[14.5px]">
      <span className="flex justify-between"><span>{label}</span><b className="tabular">{fmt(value)}</b></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} className="mt-1 w-full accent-[var(--color-brand)]" />
    </label>
  );
}

/** H1 plan simulator. Start from a program (its limits become the starting levers) or set levers by hand.
 * Anything beyond the agent-level programs is flagged as needing a team lead. Every run is logged. */
export function SimulatorPanel({ caseId, initialProgram }: { caseId: string; initialProgram?: string | null }) {
  const elig = useEligibility(caseId);
  const programs: { program_id: string; program_name: string; eligible: boolean }[] = elig.data?.programs ?? [];
  const [program, setProgram] = useState<string>(initialProgram ?? "");
  const [levers, setLevers] = useState({ payment_reduction_pct: 0.25, term_extension_months: 0, payment_holiday_months: 0, fee_waiver: false });
  const sim = useSimulate(caseId);
  const d = sim.data;
  const r = d?.results;
  const run = () => sim.mutate(program ? { program_id: program } : levers);
  // arriving with a program chosen (from Missed offers), or picking one, shows its result straight away
  useEffect(() => { if (program) sim.mutate({ program_id: program }); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [program]);
  const share = r?.payment_share_of_surplus;

  return (
    <>
    <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[14px]">
      <span className="text-muted">Case</span><span className="font-mono font-semibold">{caseId}</span>
      <Link to="/hardship/simulator/start" className="inline-flex min-h-10 items-center text-[13.5px] font-medium">Change case</Link>
    </div>
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card>
        <h2 className="mb-3 mt-0 text-[1.0625rem]">Plan</h2>
        <label className="block text-[14.5px]">Start from a program
          <select value={program} onChange={(e) => setProgram(e.target.value)} className="mt-1 block h-10 w-full rounded-[var(--radius-md)] border border-grey-300 bg-white px-2">
            <option value="">Set the levers by hand</option>
            {programs.map((p) => <option key={p.program_id} value={p.program_id} disabled={!p.eligible}>{p.program_name}{p.eligible ? "" : " (not eligible)"}</option>)}
          </select>
        </label>
        {!program && (
          <>
            <Slider label="Payment cut" value={levers.payment_reduction_pct} min={0} max={1} step={0.05} fmt={(v) => `${Math.round(v * 100)}%`} onChange={(v) => setLevers({ ...levers, payment_reduction_pct: v })} />
            <Slider label="Longer term" value={levers.term_extension_months} min={0} max={36} fmt={(v) => `${v} months`} onChange={(v) => setLevers({ ...levers, term_extension_months: v })} />
            <Slider label="Payment holiday" value={levers.payment_holiday_months} min={0} max={3} fmt={(v) => `${v} months`} onChange={(v) => setLevers({ ...levers, payment_holiday_months: v })} />
            <label className="mt-3 flex items-center gap-2 text-[14.5px]"><input type="checkbox" checked={levers.fee_waiver} onChange={(e) => setLevers({ ...levers, fee_waiver: e.target.checked })} /> Waive fees</label>
          </>
        )}
        <Button variant="primary" className="mt-5 w-full" onClick={run} disabled={sim.isPending}>{sim.isPending ? "Running…" : "Run scenario"}</Button>
        <p className="mb-0 mt-3 text-[13px] text-muted">Every run is saved to the audit log. Household size and dependants are never used.</p>
      </Card>

      <div className="min-w-0">
        {sim.isError && <Card variant="grey" role="alert">That scenario couldn't be run. {(sim.error as { reason?: string; message?: string })?.message}</Card>}
        {d && r ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="md:col-span-2 flex flex-wrap items-center gap-3 text-[14.5px]">
              {d.within_program ? <Badge kind="ok">Within program rules</Badge> : <Badge kind="danger">Outside program rules</Badge>}
              <span>Approver: <b>{String(d.approver_level).replace("_", " ")}</b></span>
              <span className="text-muted">Balance {cad(d.inputs?.balance)} at {(d.inputs?.apr * 100).toFixed(2)}% · payment now {cad(d.inputs?.payment_now)}</span>
            </Card>
            <Card>
              <p className="m-0 text-[13.5px] text-muted">New payment vs monthly surplus</p>
              <p className="m-0 mt-1 font-[family-name:var(--font-display)] text-[1.75rem] font-semibold leading-tight tabular">{cad(r.new_payment)}{r.surplus != null && <span className="text-muted"> / {cad(r.surplus)}</span>}</p>
              <p className="m-0 mt-1 text-[14px]">
                {r.surplus == null ? "No surplus estimate for this customer." : r.surplus <= 0 ? "Cash flow is negative on average, so any payment stretches the household." : share != null ? `${Math.round(share * 100)}% of the estimated surplus` : ""}
              </p>
            </Card>
            <Card>
              <p className="m-0 text-[13.5px] text-muted">Time to pay off and total interest</p>
              <p className="m-0 mt-1 font-[family-name:var(--font-display)] text-[1.75rem] font-semibold leading-tight tabular">{r.months_to_clear == null ? "50+ years" : `${r.months_to_clear} mo`} · {cad(r.total_interest)}</p>
              <p className="m-0 mt-1 text-[14px] text-muted">Today: {months(r.months_to_clear_current)} · {cad(r.total_interest_current)}</p>
            </Card>
            <Card>
              <p className="m-0 text-[13.5px] text-muted">Bank impact vs doing nothing (present value)</p>
              <p className="m-0 mt-1 font-[family-name:var(--font-display)] text-[1.75rem] font-semibold leading-tight tabular">{r.bank_impact_vs_status_quo > 0 ? "+" : ""}{cad(r.bank_impact_vs_status_quo)}</p>
            </Card>
            <Card>
              <p className="m-0 text-[13.5px] text-muted">Similar plans that held</p>
              {r.hold_rate_similar ? (<>
                <p className="m-0 mt-1 font-[family-name:var(--font-display)] text-[1.75rem] font-semibold leading-tight tabular">{Math.round(r.hold_rate_similar.value * 100)}%</p>
                <Badge kind="observed">{r.hold_rate_similar.label} · {r.hold_rate_similar.n} finished plans</Badge>
              </>) : <p className="m-0 mt-1 text-[14.5px] text-muted">No finished plans for this kind of program to compare with.</p>}
            </Card>
            <Card variant="grey" className="md:col-span-2 text-[13.5px]">
              <b>Assumptions (not in the data):</b> {Math.round(d.assumptions.annual_discount_rate * 100)}% discount rate, {Math.round(d.assumptions.lgd * 100)}% loss given default.
              <ul className="mb-0 mt-1 pl-5">{(d.notes ?? []).map((n: string) => <li key={n}>{n}</li>)}</ul>
            </Card>
          </div>
        ) : <EmptyState title="No scenario yet" detail="Pick a program or move the levers, then run a scenario to see what it does to the customer and to the bank." />}
      </div>
    </div>
    </>
  );
}
