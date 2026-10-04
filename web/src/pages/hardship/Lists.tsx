import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useEligibility, useFlag, useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { DataTable } from "@/components/DataTable";
import { SortControl, type Dir } from "@/components/SortControl";
import { Footnote, QueryState } from "@/components/States";
import { productLabel } from "@/lib/labels";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const cad = (n: unknown) => (n == null ? "n/a" : Number(n).toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }));
const day = (s?: string) => (s ? new Date(`${s}T00:00:00`).toLocaleDateString("en-CA", { day: "numeric", month: "short", year: "numeric" }) : "n/a");
const SOURCE: Record<string, string> = { model: "Model flag", agent_coded: "Agent coded", customer_form: "Customer form" };

/** Lowering a flag needs a person and a reason (plan section 5). */
function ReasonDialog({ open, title, onClose, onSubmit }: { open: boolean; title: string; onClose: () => void; onSubmit: (reason: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  useEffect(() => { if (open) { setReason(""); ref.current?.showModal(); } else ref.current?.close(); }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-full max-w-md rounded-[var(--radius-lg)] border border-grey-300/70 p-6 shadow-[var(--shadow-raised)]">
      <form onSubmit={(e) => { e.preventDefault(); if (reason.trim()) onSubmit(reason.trim()); }}>
        <h3 className="mt-0">{title}</h3>
        <label className="block text-sm">Reason (required, saved to the audit log)
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="mt-1 block w-full rounded-[var(--radius-md)] border border-grey-300 p-2 outline-none focus:border-brand/50 focus:shadow-[var(--shadow-focus)]" />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" disabled={!reason.trim()}>Save</Button>
        </div>
      </form>
    </dialog>
  );
}


/** Confirming hardship links the customer to a program they qualify for (the latch needs one). */
function ConfirmDialog({ item, onClose, onSubmit }: { item: Json | null; onClose: () => void; onSubmit: (programId: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const elig = useEligibility(item?.case_id);
  const programs: { program_id: string; program_name: string; eligible: boolean }[] = (elig.data?.programs ?? []).filter((p: Json) => p.eligible);
  const [program, setProgram] = useState("");
  useEffect(() => { if (item) { setProgram(""); ref.current?.showModal(); } else ref.current?.close(); }, [item]);
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-full max-w-md rounded-[var(--radius-lg)] border border-grey-300/70 p-6 shadow-[var(--shadow-raised)]">
      <form onSubmit={(e) => { e.preventDefault(); if (program) onSubmit(program); }}>
        <h3 className="mt-0">Confirm hardship for {item?.name}</h3>
        <p className="mt-0 text-[14px] text-muted">Pick the program you are offering. Confirming hardship pauses pressure actions, so it is tied to a real offer.</p>
        {elig.isLoading ? <p className="text-[14px] text-muted">Checking which programs fit…</p> : programs.length === 0 ? (
          <p role="status" className="text-[14px]">No program fits this customer right now, so the flag can't be confirmed. Leave it as possible or use the simulator to see why.</p>
        ) : (
          <label className="block text-[14.5px]">Program
            <select value={program} onChange={(e) => setProgram(e.target.value)} className="mt-1 block h-10 w-full rounded-[var(--radius-md)] border border-grey-300 bg-white px-2">
              <option value="">Choose a program</option>
              {programs.map((p) => <option key={p.program_id} value={p.program_id}>{p.program_name}</option>)}
            </select>
          </label>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" disabled={!program}>Confirm hardship</Button>
        </div>
      </form>
    </dialog>
  );
}

/** Customers flagged "possible" that nobody has confirmed or cleared. Oldest overdue first. */
export function Board() {
  const q = useGet("hboard", "/hardship/board");
  const flag = useFlag();
  const [clearing, setClearing] = useState<Json | null>(null);
  const [confirming, setConfirming] = useState<Json | null>(null);
  const items: Json[] = q.data?.items ?? [];
  return (
    <QueryState q={q} empty={items.length === 0}>
      <p className="mt-0 text-[14.5px] text-muted">
        <b className="font-semibold text-ink">{q.data?.total?.toLocaleString()}</b> customers are flagged as possibly in hardship; <b className="font-semibold text-danger">{q.data?.overdue?.toLocaleString()}</b> are past the {q.data?.review_days}-business-day review target. Showing the {items.length} most overdue.
      </p>
      <DataTable
        searchable="Search customers"
        filters={[{ id: "late", label: "Past review target", test: (r) => Number(r[5]) > 0 }, { id: "model", label: "Model flag", test: (r) => r[1] === "Model flag" }, { id: "agent", label: "Agent coded", test: (r) => r[1] === "Agent coded" }, { id: "form", label: "Customer form", test: (r) => r[1] === "Customer form" }]}
        columns={["Customer", "Flagged by", "Past due", "Days past due", "Raised", "Review was due", ""]}
        rows={items.map((i) => [i.name, SOURCE[i.source] ?? i.source, i.total_overdue, i.dpd, i.raised, i.days_overdue, i])}
        render={(v, col) => {
          if (col === "") {
            const i = v as Json;
            return (
              <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                <Link to={`/customers/${i.golden_id}`} className="mr-1 text-[14px] font-medium">Open</Link>
                <Button size="sm" disabled={flag.isPending} onClick={() => setConfirming(i)}>Confirm</Button>
                <Button size="sm" variant="ghost" onClick={() => setClearing(i)}>Not hardship</Button>
              </span>
            );
          }
          if (col === "Past due") return cad(v);
          if (col === "Raised") return day(String(v));
          if (col === "Review was due") return Number(v) > 0 ? <Badge kind="danger">{String(v)} days ago</Badge> : <Badge kind="ok">On time</Badge>;
          return String(v ?? "n/a");
        }}
      />
      <ConfirmDialog item={confirming} onClose={() => setConfirming(null)}
        onSubmit={(program_id) => { flag.mutate({ golden_id: confirming?.golden_id, target: "clear", reason: "Confirmed by specialist review", program_id }); setConfirming(null); }} />
      <ReasonDialog open={!!clearing} title={`Clear the flag for ${clearing?.name ?? ""}`} onClose={() => setClearing(null)}
        onSubmit={(reason) => { flag.mutate({ golden_id: clearing?.golden_id, target: "none", reason }); setClearing(null); }} />
    </QueryState>
  );
}

const MISSED_SORTS: [string, string][] = [["newest", "Newest flag"], ["days_late", "Days past due"], ["exposure", "Amount past due"], ["days_since_flag", "Days since flag"], ["program", "Program"]];

/** Customers with hardship signs and no program offered, where an agent-level program fits. */
export function Missed() {
  const [sort, setSort] = useState("newest");
  const [dir, setDir] = useState<Dir>("desc");
  const q = useGet("hmissed", `/hardship/missed-offers?sort=${sort}&dir=${dir}`);
  const items: Json[] = q.data?.items ?? [];
  const products = [...new Set(items.map((i) => productLabel(String(i.product))))].sort();
  return (
    <QueryState q={q} empty={items.length === 0}>
      <p className="mt-0 text-[14.5px] text-muted">{q.data?.note}</p>
      <DataTable
        actions={<SortControl value={sort} dir={dir} options={MISSED_SORTS} onChange={(v) => { setSort(v); setDir(v === "program" ? "asc" : "desc"); }} onDir={setDir} />}
        searchable="Customer or program"
        filters={products.map((p) => ({ id: p, label: p, test: (r: unknown[]) => r[1] === p }))}
        columns={["Customer", "Product", "Past due", "Days past due", "Programs that fit", ""]}
        rows={items.map((i) => [i.name, productLabel(String(i.product)), i.overdue, i.dpd, i.eligible_programs.map((p: Json) => p.program_name).join(", "), i])}
        render={(v, col) => {
          if (col === "Past due") return cad(v);
          if (col === "") { const i = v as Json; return <Link to={`/hardship/simulator/${i.case_id}?program=${i.eligible_programs[0]?.program_id}`} className="whitespace-nowrap font-medium">Try in simulator</Link>; }
          return String(v ?? "n/a");
        }}
      />
    </QueryState>
  );
}

/** Offers an agent made although the rules said the customer wasn't eligible. */
export function Overrides() {
  const q = useGet("hover", "/hardship/overrides");
  const items: Json[] = q.data?.items ?? [];
  return (
    <QueryState q={q} empty={items.length === 0}>
      <p className="mt-0 text-[14.5px] text-muted">{q.data?.note} Last {q.data?.window_days} days, by agent and program.</p>
      <DataTable
        searchable="Agent or program"
        columns={["Agent", "Program", "Offers made while not eligible", "Of which the NBA had recommended"]}
        rows={items.map((i) => [`${i.agent_name ?? i.agent_id} (${i.agent_id})`, i.program_id, i.count, i.nba_recommended])}
      />
      <Footnote>A high count is a prompt for a coaching conversation, not a verdict: some overrides are right and the audit log holds the reason.</Footnote>
    </QueryState>
  );
}

export function ListView({ path, k }: { path: string; k: string }) {
  const q = useGet(k, path);
  const items: Record<string, unknown>[] = q.data?.items ?? [];
  const cols = items[0] ? Object.keys(items[0]).filter((c) => typeof items[0][c] !== "object") : [];
  return <QueryState q={q} empty={items.length === 0}><DataTable columns={cols} rows={items.map((i) => cols.map((c) => i[c]))} /></QueryState>;
}
