import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { useCustomer, useEligibility, useIdentity, useNba, usePolicyAnswer, useTimeline, useWhatIf } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { EligibilityList } from "@/components/EligibilityList";
import { FreshnessPill } from "@/components/FreshnessPill";
import { HoldingsTable } from "@/components/HoldingsTable";
import { IdentityLineage } from "@/components/IdentityLineage";
import { NbaCard } from "@/components/NbaCard";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";
import { Timeline } from "@/components/Timeline";

/** C360 workspace, the money screen. */
export default function Customer() {
  const { goldenId = "" } = useParams();
  const c = useCustomer(goldenId);
  const caseId: string | undefined = c.data?.open_case_id;
  const nba = useNba(caseId);
  const elig = useEligibility(caseId);
  const ident = useIdentity(goldenId);
  const tl = useTimeline(goldenId);
  const b = c.data?.badges;
  return (
    <QueryState q={c}>
      {b && b.hardship_flag !== "none" && (
        <div role="status" className="mb-4 flex items-center gap-2 rounded-[var(--radius-md)] bg-amber-50 px-4 py-3 text-amber">
          <ShieldAlert aria-hidden /> Pressure actions paused (hardship latch: {b.hardship_flag}). Raised by {b.hardship_source} on {b.hardship_raised}.
        </div>
      )}
      <header className="mb-6 flex flex-wrap items-center gap-4">
        <span className="grid h-14 w-14 place-items-center rounded-full bg-brand text-xl text-white" aria-hidden>{c.data?.display_name?.split(" ").map((s: string) => s[0]).join("")}</span>
        <div className="flex-1">
          <h1 className="m-0 text-3xl font-medium">{c.data?.display_name} <span className="font-mono text-base text-muted">{c.data?.golden_id}</span></h1>
          <p className="m-0 text-muted">{c.data?.segment} · {c.data?.city}, {c.data?.province_code} · customer since {c.data?.customer_since}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge kind="risk">Risk: {b?.risk.band} {b?.risk.score}</Badge>
            <Badge kind="bucket">Bucket {b?.bucket}</Badge>
            <Badge kind="consent">Consent: Call {b?.consent.call} · {b?.consent.sms && "SMS · "}{b?.consent.email && "Email · "}{b?.consent.language}</Badge>
            {b?.hardship_flag !== "none" && <Badge kind="hardship">Hardship: {b?.hardship_flag}</Badge>}
          </div>
        </div>
        <FreshnessPill asOf={c.data?.meta?.as_of} hours={c.data?.meta?.freshness_hours} fixture={c.data?.meta?.fixture} />
      </header>

      <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
        <div className="space-y-6">
          <section><SectionTag as="h2" subtitle="Why we recommend this">Next best action</SectionTag><QueryState q={nba}>{nba.data && <NbaCard proposal={nba.data} />}</QueryState></section>
          <section><SectionTag as="h2">Product holdings</SectionTag><HoldingsTable holdings={c.data?.holdings ?? []} /></section>
          <section><SectionTag as="h2">Contact timeline</SectionTag><Card><QueryState q={tl}><Timeline items={tl.data?.items ?? []} /></QueryState></Card></section>
        </div>
        <aside className="space-y-6">
          <AssistPanel eligibility={elig.data?.programs ?? []} />
          <PromiseCheck caseId={caseId} />
          <Card><h3 className="mt-0">Identity & lineage</h3><QueryState q={ident}>{ident.data && <IdentityLineage data={ident.data as never} />}</QueryState></Card>
        </aside>
      </div>
    </QueryState>
  );
}

function AssistPanel({ eligibility }: { eligibility: never[] }) {
  const [q, setQ] = useState("");
  const ans = usePolicyAnswer();
  return (
    <Card variant="grey">
      <h3 className="mt-0">Agent assist</h3>
      <form onSubmit={(e) => { e.preventDefault(); if (q) ans.mutate(q); }} className="flex gap-2">
        <label className="sr-only" htmlFor="policy-q">Policy question</label>
        <input id="policy-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a policy question…" className="flex-1 rounded-[var(--radius-md)] border border-ink bg-white px-3 py-2" />
        <button className="rounded-[var(--radius-md)] bg-brand px-3 text-white">Ask</button>
      </form>
      {ans.data && (
        <div className="mt-3 text-sm">
          {ans.data.refused ? <p className="m-0">{ans.data.refusal_reason}</p> : <p className="m-0">{ans.data.answer}</p>}
          {ans.data.citations?.map((c: { doc_id: string; section: string }) => <Badge key={c.doc_id + c.section} kind="neutral">{c.doc_id} {c.section}</Badge>)}
        </div>
      )}
      <h4 className="mb-2">Eligibility</h4>
      <EligibilityList programs={eligibility} />
    </Card>
  );
}

function PromiseCheck({ caseId }: { caseId?: string }) {
  const wi = useWhatIf();
  return (
    <Card>
      <h3 className="mt-0">Promise check</h3>
      <p className="m-0">Due 2 Oct is <b>6 days before</b> the expected payday (8 Oct).</p>
      <button type="button" disabled={!caseId} onClick={() => wi.mutate({ case_id: caseId, ptp_amount: 800, ptp_due_date: "2026-10-08" })} className="mt-3 rounded-[var(--radius-md)] border border-ink bg-white px-3 py-2">Try 8 Oct</button>
      {wi.data && <p className="mb-0">Break risk {wi.data.p_break_before} → <b>{wi.data.p_break_after}</b> <Badge kind="model-estimate">{wi.data.label}</Badge></p>}
    </Card>
  );
}
