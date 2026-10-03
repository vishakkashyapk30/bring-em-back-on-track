import clsx from "clsx";
import { ArrowLeft, Check, Clock, Copy, Mail, MessageSquare, Phone, ShieldAlert, Smartphone, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { useCustomer, useEligibility, useIdentity, useNba, usePolicyAnswer, useTimeline, useWhatIf } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { EligibilityList } from "@/components/EligibilityList";
import { HoldingsTable } from "@/components/HoldingsTable";
import { IdentityLineage } from "@/components/IdentityLineage";
import { NbaCard } from "@/components/NbaCard";
import { QueryState, SampleBadge, Skeleton } from "@/components/States";
import { Timeline } from "@/components/Timeline";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const cad = (v?: number | null) => (v == null ? "n/a" : v.toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }));
const title = (s?: string | null) => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : "");
const HARDSHIP_LABEL: Record<string, string> = { clear: "confirmed", possible: "possible", none: "none" };

/** Customer 360 workspace: who the customer is and how to reach them (header), what to do next (main column),
 * and help while working the case (one sticky side panel with tabs). */
export default function Customer() {
  const { goldenId = "" } = useParams();
  const c = useCustomer(goldenId);
  const caseId: string | undefined = c.data?.open_case_id ?? undefined;
  const nba = useNba(caseId);
  const tl = useTimeline(goldenId);
  const d: Json = c.data ?? {};
  const holdings: Json[] = d.holdings ?? [];
  const pastDue = holdings.reduce((a, h) => a + (Number(h.overdue) || 0), 0);

  if (c.isLoading) return <div className="space-y-6"><Skeleton lines={4} /><Skeleton lines={8} /></div>;

  return (
    <QueryState q={c}>
      <Link to="/queue" className="mb-4 inline-flex items-center gap-1.5 text-[13.5px] font-medium text-muted no-underline hover:text-ink hover:no-underline">
        <ArrowLeft size={15} aria-hidden /> Today's queue
      </Link>

      <CustomerHeader d={d} pastDue={pastDue} />

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-8">
          <section aria-label="Next best action">
            {caseId ? (
              <QueryState q={nba} banner={false}>{nba.data && <NbaCard proposal={nba.data} sample={!!nba.data.meta?.fixture} />}</QueryState>
            ) : (
              <Card className="text-[15px] text-muted">No open collections case, so there's no next best action for this customer.</Card>
            )}
          </section>

          <section aria-labelledby="holdings-h">
            <SectionTitle id="holdings-h" title="Products" note={`${holdings.length} accounts · ${cad(pastDue)} past due`} />
            <HoldingsTable holdings={holdings as never[]} />
          </section>

          <section aria-labelledby="timeline-h">
            <SectionTitle id="timeline-h" title="Contact history" note="Newest first. Open a call that has a recording to see its summary." />
            <Card><QueryState q={tl}><Timeline items={tl.data?.items ?? []} /></QueryState></Card>
          </section>
        </div>

        <SidePanel goldenId={goldenId} caseId={caseId} />
      </div>
    </QueryState>
  );
}

function SectionTitle({ id, title: t, note }: { id: string; title: string; note?: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 id={id} className="m-0 text-[18px]">{t}</h2>
      {note && <span className="text-[13px] text-muted">{note}</span>}
    </div>
  );
}

function CustomerHeader({ d, pastDue }: { d: Json; pastDue: number }) {
  const b: Json = d.badges ?? {};
  const initials = String(d.display_name ?? "").split(" ").map((s: string) => s[0]).join("").slice(0, 2);
  const hardship = b.hardship_flag && b.hardship_flag !== "none";
  const blocked = b.contact_block && b.contact_block !== "none";
  const copy = () => { navigator.clipboard.writeText(d.golden_id); toast.success("ID copied"); };
  return (
    <Card hard className="overflow-hidden p-0">
      <div className="flex flex-wrap items-start gap-5 p-6">
        <span aria-hidden className="grid h-14 w-14 shrink-0 place-items-center rounded-[var(--radius-md)] bg-ink font-[family-name:var(--font-display)] text-[22px] font-semibold text-white">{initials}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="m-0 text-[26px] leading-tight">{d.display_name}</h1>
            <button type="button" onClick={copy} title="Copy this ID" className="inline-flex items-center gap-1.5 font-mono text-[13px] text-muted transition-colors hover:text-ink">
              {d.golden_id} <Copy size={12} aria-hidden />
            </button>
          </div>
          <p className="mb-0 mt-1 text-[14px] text-muted">
            {[title(d.segment), [d.city, d.province_code].filter(Boolean).join(", "), d.customer_since && `customer since ${d.customer_since}`].filter(Boolean).join(" · ")}
          </p>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
            {hardship && <Badge kind="hardship">Hardship {HARDSHIP_LABEL[b.hardship_flag] ?? b.hardship_flag}</Badge>}
            {b.vulnerability_flag && <Badge kind="vulnerable">Vulnerable</Badge>}
            {blocked && <Badge kind="danger">Contact blocked: {title(b.contact_block)}</Badge>}
            {b.dispute_open_flag && <Badge kind="dispute">Open dispute</Badge>}
            {b.bucket && <Badge kind="neutral">{b.bucket} days past due</Badge>}
            {b.risk?.score != null && <span title="The bank's general collections risk score. It is separate from the chance that a promise breaks, shown in the next best action below."><Badge kind="neutral">Bank risk score: {String(b.risk.band).replace("_", " ")} ({b.risk.score})</Badge></span>}
          </div>
        </div>
        <dl className="m-0 grid shrink-0 grid-cols-3 gap-6 text-right">
          <Figure label="Past due" value={cad(pastDue)} />
          <Figure label="Days past due" value={d.max_dpd ?? "n/a"} />
          <Figure label="Open case" value={d.open_case_id ?? "none"} mono />
        </dl>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-grey-300/60 bg-grey-100/60 px-6 py-3 text-[13px]">
        <span className="font-medium text-muted">How to contact</span>
        <Consent icon={<Phone size={14} />} label={b.consent?.call && b.consent.call !== "no" ? `Call ${b.consent.call.replace("-", " to ")} local` : "No calls"} ok={!!b.consent?.call && b.consent.call !== "no"} />
        <Consent icon={<MessageSquare size={14} />} label="SMS" ok={!!b.consent?.sms} />
        <Consent icon={<Mail size={14} />} label="Email" ok={!!b.consent?.email} />
        <Consent icon={<Smartphone size={14} />} label="App" ok={!!b.consent?.push} />
        <span className="text-muted">Language {b.consent?.language ?? "EN"}</span>
        <span className="ml-auto inline-flex items-center gap-1 text-muted"><Clock size={13} aria-hidden /> Data from 28 Sep 2026</span>
      </div>
      {hardship && (
        <div role="status" className="flex items-start gap-2.5 border-t border-amber/20 bg-amber-50 px-6 py-3 text-[13.5px] text-amber">
          <ShieldAlert size={17} className="mt-px shrink-0" aria-hidden />
          <span>Hardship is {HARDSHIP_LABEL[b.hardship_flag]}, so we won't apply any pressure. Offer support options first.{b.hardship_source && ` The flag came from ${b.hardship_source.replace("_", " ")}${b.hardship_raised ? ` on ${b.hardship_raised}` : ""}.`}</span>
        </div>
      )}
    </Card>
  );
}

function Figure({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[12px] font-medium text-muted">{label}</dt>
      <dd className={clsx("m-0 mt-0.5 font-semibold tabular", mono ? "font-mono text-[13px]" : "font-[family-name:var(--font-display)] text-[20px]")}>{value}</dd>
    </div>
  );
}

function Consent({ icon, label, ok }: { icon: ReactNode; label: string; ok: boolean }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5", ok ? "text-ink" : "text-muted line-through decoration-muted/50")}>
      <span className={ok ? "text-teal" : "text-muted"}>{icon}</span>{label}
      {ok ? <Check size={13} className="text-teal" aria-label="allowed" /> : <X size={13} aria-label="not allowed" />}
    </span>
  );
}

const TABS = [["assist", "Assist"], ["eligibility", "Eligibility"], ["promise", "Promise"], ["identity", "Identity"]] as const;
type Tab = (typeof TABS)[number][0];

/** One sticky panel for working the case: policy questions, eligibility, promise check, identity. */
function SidePanel({ goldenId, caseId }: { goldenId: string; caseId?: string }) {
  const [tab, setTab] = useState<Tab>("assist");
  return (
    <aside className="lg:sticky lg:top-20">
      <Card className="p-0">
        <div role="tablist" aria-label="Case tools" className="flex border-b border-grey-300/70 px-2">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setTab(id)}
              className={clsx("relative -mb-px flex-1 border-b-2 px-2 py-3 text-[13.5px] font-medium transition-colors",
                tab === id ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink")}>{label}</button>
          ))}
        </div>
        <div key={tab} role="tabpanel" className="fade-in p-5">
          {tab === "assist" && <AssistTab />}
          {tab === "eligibility" && <EligibilityTab caseId={caseId} />}
          {tab === "promise" && <PromiseTab caseId={caseId} />}
          {tab === "identity" && <IdentityTab goldenId={goldenId} />}
        </div>
      </Card>
    </aside>
  );
}

const SUGGESTED = ["Can I call a customer on Sunday?", "What must I do if a customer mentions hardship?", "What is the grace period on a promise?"];

function AssistTab() {
  const [q, setQ] = useState("");
  const ans = usePolicyAnswer();
  const run = (text: string) => { setQ(text); ans.mutate(text); };
  const a: Json | undefined = ans.data;
  return (
    <div>
      <p className="mb-3 text-[13.5px] text-muted">Ask a policy question. Answers quote the current policy and cite the section.</p>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) ans.mutate(q); }} className="flex gap-2">
        <label className="sr-only" htmlFor="policy-q">Policy question</label>
        <input id="policy-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Can I call on Sunday?"
          className="h-10 min-w-0 flex-1 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[14px] outline-none transition-shadow focus:border-brand/50 focus:shadow-[var(--shadow-focus)]" />
        <button disabled={ans.isPending || !q.trim()} className="h-10 rounded-[var(--radius-md)] bg-brand px-4 text-[14px] font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-50">Ask</button>
      </form>
      {!a && !ans.isPending && (
        <div className="mt-3 flex flex-col gap-1.5">
          {SUGGESTED.map((s) => (
            <button key={s} type="button" onClick={() => run(s)} className="rounded-[var(--radius-md)] px-2 py-1.5 text-left text-[13.5px] text-brand transition-colors hover:bg-brand-50">{s}</button>
          ))}
        </div>
      )}
      {ans.isPending && <div className="mt-4"><Skeleton lines={3} /></div>}
      {a && !ans.isPending && (
        <div className="fade-in mt-4 rounded-[var(--radius-md)] bg-grey-100 p-3 text-[14px]">
          {a.refused ? <p className="text-muted">{a.refusal_reason}</p> : <p>{a.answer}</p>}
          <div className="mt-2 flex flex-wrap gap-1">{(a.citations ?? []).map((ct: Json) => <Badge key={ct.doc_id + ct.section} kind="neutral">{ct.doc_id} {ct.section}</Badge>)}</div>
        </div>
      )}
    </div>
  );
}

function EligibilityTab({ caseId }: { caseId?: string }) {
  const e = useEligibility(caseId);
  return (
    <QueryState q={e} banner={false}>
      <div className="mb-3 flex items-center justify-between"><span className="text-[13.5px] text-muted">Hardship programmes this case qualifies for</span>{e.data?.meta?.fixture && <SampleBadge />}</div>
      <EligibilityList programs={e.data?.programs ?? []} />
    </QueryState>
  );
}

const pct = (p: unknown) => (typeof p === "number" ? `${Math.round(p * 100)}%` : "n/a");
const longDate = (s?: string) => (s ? new Date(`${s}T00:00:00`).toLocaleDateString("en-CA", { day: "numeric", month: "short", year: "numeric" }) : "");

/** A2: check a promise date before it is saved. Nothing is written; the answer is a model estimate. */
function PromiseTab({ caseId }: { caseId?: string }) {
  const wi = useWhatIf();
  const [date, setDate] = useState("");
  const [amount, setAmount] = useState("");
  const d: Json | undefined = wi.data;
  const ready = !!caseId && !!date && Number(amount) > 0;
  const field = "mt-1 block h-10 w-full rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[14px]";
  return (
    <div>
      <p className="mb-3 mt-0 text-[13.5px] text-muted">Try a promise date and amount before agreeing to it. Nothing is saved.</p>
      <form onSubmit={(e) => { e.preventDefault(); if (ready) wi.mutate({ case_id: caseId, ptp_amount: Number(amount), ptp_due_date: date }); }} className="space-y-3">
        <label className="block text-[14px]">Promised date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={field} /></label>
        <label className="block text-[14px]">Amount (CAD)<input type="number" min={0} step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} className={field} /></label>
        <button type="submit" disabled={!ready || wi.isPending} className="h-10 w-full rounded-[var(--radius-md)] bg-brand px-4 text-[14px] font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-50">Check this date</button>
      </form>
      {wi.isError && <p role="alert" className="mt-3 text-[14px] text-danger">That check didn't run. Try again in a moment.</p>}
      {d && (
        <div className="fade-in mt-4 rounded-[var(--radius-md)] bg-grey-100 p-3 text-[14px]">
          {d.days_before_payday_after != null && (
            <p className="mt-0">{longDate(d.due_after)} is <b>{Math.abs(d.days_before_payday_after)} days {d.days_before_payday_after >= 0 ? "before" : "after"}</b> the expected payday.</p>
          )}
          <p className="m-0">Chance of breaking: {pct(d.p_break_before)} with the current date ({longDate(d.due_before)}), <b>{pct(d.p_break_after)}</b> with {longDate(d.due_after)}.</p>
          <p className="mb-0 mt-2"><Badge kind="model-estimate">{d.label}</Badge></p>
          {d.note && <p className="mb-0 mt-2 text-[13px] text-muted">{d.note}</p>}
        </div>
      )}
    </div>
  );
}

function IdentityTab({ goldenId }: { goldenId: string }) {
  const ident = useIdentity(goldenId);
  return <QueryState q={ident}>{ident.data && <IdentityLineage data={ident.data as never} />}</QueryState>;
}
