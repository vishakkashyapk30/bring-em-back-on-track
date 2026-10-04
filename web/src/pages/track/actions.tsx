import { ArrowRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { useNba } from "@/api/hooks";
import { useTrackAction, type TrackAction } from "@/api/track";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { NbaCard } from "@/components/NbaCard";
import { QueryState } from "@/components/States";

const field = "mt-1 block h-10 w-full rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[14px] focus:border-brand/50 focus:shadow-[var(--shadow-focus)] focus:outline-none";

function Row({ a, children }: { a: TrackAction; children?: ReactNode }) {
  return (
    <li className="min-w-0 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4">
      <p className="m-0 break-words font-medium">{a.label}</p>
      {a.detail && <p className="mb-0 mt-1 text-[13.5px] text-muted">{a.detail}</p>}
      {!a.enabled && a.why_disabled && <p className="mb-0 mt-2 text-[13.5px] text-amber" role="note">{a.why_disabled}</p>}
      {children && <div className="mt-3">{children}</div>}
    </li>
  );
}

function GoLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link to={to} className="inline-flex min-h-10 items-center gap-1.5 text-[14px] font-medium">{children} <ArrowRight size={15} aria-hidden /></Link>;
}

function NbaAction({ a }: { a: TrackAction }) {
  const nba = useNba(a.enabled ? a.target ?? undefined : undefined);
  if (!a.enabled) return <Row a={a} />;
  return <li className="min-w-0"><QueryState q={nba} banner={false}>{nba.data && <NbaCard proposal={nba.data} sample={!!nba.data.meta?.fixture} />}</QueryState></li>;
}

/** Approve one item through its existing endpoint, after a confirm step. */
function ConfirmAction({ a, run, busy, verb }: { a: TrackAction; run: (endpoint: string, body?: unknown, done?: string) => void; busy: boolean; verb: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Row a={a}>
      <Button variant="primary" disabled={!a.enabled || busy} onClick={() => setOpen(true)}>{verb}</Button>
      <ConfirmDialog open={open} title={`${verb}?`} confirmLabel={verb} busy={busy} onClose={() => setOpen(false)}
        onConfirm={() => { run(a.endpoint!, undefined, `${verb}: done`); setOpen(false); }}>
        <p className="mt-0">{a.label}</p><p className="mb-0">Nothing is sent to a customer from here. The approval goes in the audit log.</p>
      </ConfirmDialog>
    </Row>
  );
}

function HardshipAction({ a, run, busy }: { a: TrackAction; run: (endpoint: string, body?: unknown, done?: string) => void; busy: boolean }) {
  const confirm = a.kind === "hardship_confirm";
  const [choice, setChoice] = useState(a.options[0]?.value ?? "");
  const [reason, setReason] = useState("");
  const ok = a.enabled && !!choice && (confirm || reason.trim().length > 0);
  const id = `${a.id}-choice`;
  return (
    <Row a={a}>
      {a.enabled && (
        <form className="space-y-3" onSubmit={(e) => {
          e.preventDefault();
          if (!ok) return;
          run(a.endpoint!, confirm ? { target: "clear", program_id: choice, reason: reason || null } : { target: choice, reason }, confirm ? "Hardship confirmed" : "Flag lowered");
          setReason("");
        }}>
          <label htmlFor={id} className="block text-[14px]">{confirm ? "Program to link" : "Lower to"}
            <select id={id} value={choice} onChange={(e) => setChoice(e.target.value)} className={field}>
              {a.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="block text-[14px]">{confirm ? "Note (optional)" : "Reason (required)"}
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} required={!confirm}
              className="mt-1 block w-full rounded-[var(--radius-md)] border border-grey-300 bg-white p-2 text-[14px] focus:border-brand/50 focus:shadow-[var(--shadow-focus)] focus:outline-none" />
          </label>
          <Button type="submit" variant="primary" disabled={!ok || busy}>{confirm ? "Confirm and link the program" : "Lower the flag"}</Button>
        </form>
      )}
    </Row>
  );
}

function VerdictAction({ a, run, busy }: { a: TrackAction; run: (endpoint: string, body?: unknown, done?: string) => void; busy: boolean }) {
  return (
    <Row a={a}>
      {a.enabled && (
        <div role="group" aria-label={`Verdict for ${a.target}`} className="flex flex-wrap gap-2">
          {a.options.map((o, i) => (
            <Button key={o.value} variant={i === 0 ? "primary" : "secondary"} disabled={busy} onClick={() => run(a.endpoint!, { verdict: o.value }, `Verdict saved: ${o.label}`)}>{o.label}</Button>
          ))}
        </div>
      )}
    </Row>
  );
}

function ProposeAction({ a, run, busy }: { a: TrackAction; run: (endpoint: string, body?: unknown, done?: string) => void; busy: boolean }) {
  const [code, setCode] = useState(a.options[0]?.value ?? "");
  const [note, setNote] = useState("");
  return (
    <Row a={a}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (code) run(a.endpoint!, { strategy_code: code, note: note || null }, "Test proposed"); }}>
        <label className="block text-[14px]">Strategy to test
          <select value={code} onChange={(e) => setCode(e.target.value)} className={field}>
            {a.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="block text-[14px]">Why (optional)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="mt-1 block w-full rounded-[var(--radius-md)] border border-grey-300 bg-white p-2 text-[14px] focus:border-brand/50 focus:shadow-[var(--shadow-focus)] focus:outline-none" />
        </label>
        <Button type="submit" variant="primary" disabled={!code || busy}>Send the proposal to a team lead</Button>
      </form>
    </Row>
  );
}

/** Every action a tracker offers. Writes call the existing endpoints (NBA decision, hardship flag, batch, playbook,
 * identity verdict, drift fix, test proposal), each of which writes the audit log; links open the existing screens. */
export function ActionsPanel({ kind, id, actions }: { kind: string; id: string; actions: TrackAction[] }) {
  const m = useTrackAction(kind, id);
  const run = (endpoint: string, body?: unknown, done?: string) => m.mutate({ endpoint, body, done });
  if (!actions.length) return <p className="text-[14px] text-muted">Nothing to do here right now.</p>;
  const links = actions.filter((a) => a.kind === "link" || a.kind === "simulator" || a.kind === "summary");
  const rest = actions.filter((a) => !links.includes(a));
  return (
    <div className="space-y-4">
      <p aria-live="polite" className="sr-only">{m.isSuccess ? "Saved and recorded in the audit log." : ""}</p>
      {rest.length > 0 && (
        <ul className="m-0 grid list-none grid-cols-[minmax(0,1fr)] gap-3 p-0">
          {rest.map((a) => {
            if (a.kind === "nba") return <NbaAction key={a.id} a={a} />;
            if (a.kind === "hardship_confirm" || a.kind === "hardship_lower") return <HardshipAction key={a.id} a={a} run={run} busy={m.isPending} />;
            if (a.kind === "identity_verdict") return <VerdictAction key={a.id} a={a} run={run} busy={m.isPending} />;
            if (a.kind === "propose_test") return <ProposeAction key={a.id} a={a} run={run} busy={m.isPending} />;
            const verb = a.kind === "batch_approve" ? "Approve the batch" : a.kind === "drift_approve" ? "Approve the fix" : "Approve the proposal";
            return <ConfirmAction key={a.id} a={a} run={run} busy={m.isPending} verb={verb} />;
          })}
        </ul>
      )}
      {links.length > 0 && (
        <ul className="m-0 list-none space-y-1 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4">
          {links.map((a) => (
            <li key={a.id} className="min-w-0">
              {a.enabled && a.link ? <GoLink to={a.link}>{a.label}</GoLink> : <span className="text-muted">{a.label}</span>}
              {a.detail && <p className="m-0 text-[13px] text-muted">{a.detail}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
