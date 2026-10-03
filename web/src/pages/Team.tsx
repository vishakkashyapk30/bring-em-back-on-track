import { useState } from "react";

import { useApproveBatch, useGet, useStressTest } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

import { Button } from "@/components/Button";
import { productLabel } from "@/lib/labels";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const p1 = (v: unknown) => (v == null ? "n/a" : `${v}%`);

/** Team lead: strategy scorecard (S4, real data), agent roster (real), batch approvals (Layer 4). */
export default function Team() {
  const sc = useGet("scorecard", "/scorecard");
  const ag = useGet("agents", "/team/agents");
  return (
    <div className="space-y-10">
      <section>
        <SectionTag as="h1" subtitle="Only cases opened at least 30 days before the snapshot are counted. Compare strategies within the same stage, not across stages.">Strategy scorecard</SectionTag>
        <QueryState q={sc}>
          <DataTable searchable="Search strategies" columns={["Stage", "Strategy", "Randomised cases", "30-day cure (randomised)", "All cases", "30-day cure (all)", "Cost per cure", "Complaints / 1,000"]}
            rows={(sc.data?.items ?? []).map((r: Json) => [r.stage, r.strategy_code, r.randomised_cases, p1(r.cure_rate_30d_randomised), r.all_cases, p1(r.cure_rate_30d_all), r.cost_per_cure_cad == null ? "n/a" : `$${r.cost_per_cure_cad}`, r.complaints_per_1000_cases])}
            render={(v, col) => (col === "30-day cure (randomised)" ? <span>{String(v)} <Badge kind="causal">causal</Badge></span> : col === "30-day cure (all)" ? <span>{String(v)} <Badge kind="observed">observed</Badge></span> : String(v ?? ""))} />
          <Card variant="grey" className="mt-3 text-sm">{sc.data?.note}</Card>
        </QueryState>
      </section>
      <section>
        <SectionTag>Agents</SectionTag>
        <QueryState q={ag}>
          <DataTable searchable="Search agents" filters={[{ id: "hs", label: "Hardship-skilled", test: (r) => r[4] === true || r[4] === "true" || r[4] === 1 }, { id: "vc", label: "Vulnerable-certified", test: (r) => r[5] === "yes" }]} columns={["Agent", "Name", "Site", "Team", "Hardship skill", "Vulnerable-certified", "Case load", "PTP kept (90d)", "Cure (90d)"]}
            rows={(ag.data?.items ?? []).map((a: Json) => [a.agent_id, a.name, a.site, a.team_id, a.skill_hardship, a.vulnerable_customer_certified ? "yes" : "no", `${a.current_case_load} / ${a.max_concurrent_cases}`, a.ptp_kept_rate_90d, a.cure_rate_90d])} />
        </QueryState>
      </section>
      <section><SectionTag subtitle="Routine text and email reminders go out together, once you've looked over a 2% sample.">Batch approvals</SectionTag><Batches /></section>
      <section><SectionTag subtitle="See what happens to today's plan if a channel goes down or some agents are out.">Capacity stress test</SectionTag><StressTest /></section>
    </div>
  );
}

const TREATMENT: Record<string, string> = { reminder: "Reminders", payment_link: "Payment links", plan_offer: "Plan offers", specialist_referral: "Specialist referrals" };
const CHANNEL: Record<string, string> = { sms: "text", email: "email", push: "app message", call: "call", letter: "letter" };

function Batches() {
  const q = useGet("batches", "/batches");
  const approve = useApproveBatch();
  const items: Json[] = q.data?.items ?? [];
  return (
    <QueryState q={q} empty={items.length === 0}>
      <div className="space-y-4">
        {items.map((b) => (
          <Card key={b.batch_id}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="m-0 font-medium">{TREATMENT[b.treatment] ?? b.treatment} by {CHANNEL[b.channel] ?? b.channel}: {b.count.toLocaleString()} customers</p>
                <p className="m-0 text-[13px] text-muted">Check the {b.sample_size} sampled cases below, then approve the whole batch.</p>
              </div>
              <Button variant="primary" disabled={approve.isPending} onClick={() => approve.mutate(b.batch_id)}>Approve {b.count.toLocaleString()}</Button>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer text-[14px] font-medium">Sampled cases</summary>
              <DataTable bare columns={["Customer", "Product", "Days past due", "Break risk", "Why"]}
                rows={(b.sample ?? []).map((s: Json) => [s.name, productLabel(String(s.product)), s.dpd, s.p_break == null ? "n/a" : `${Math.round(s.p_break * 100)}%`, s.headline])} />
            </details>
          </Card>
        ))}
      </div>
    </QueryState>
  );
}

function StressTest() {
  const run = useStressTest();
  const [channel, setChannel] = useState("");
  const [pct, setPct] = useState(0);
  const d = run.data;
  return (
    <Card>
      <div className="flex flex-wrap items-end gap-4">
        <label className="text-[14.5px]">A channel is down
          <select value={channel} onChange={(e) => setChannel(e.target.value)} className="mt-1 block h-10 rounded-[var(--radius-md)] border border-grey-300 bg-white px-2">
            <option value="">None</option>
            {Object.entries(CHANNEL).filter(([k]) => k !== "letter").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="text-[14.5px]">Agents absent: <b className="tabular">{pct}%</b>
          <input type="range" min={0} max={50} step={5} value={pct} onChange={(e) => setPct(+e.target.value)} className="mt-2 block w-48 accent-[var(--color-brand)]" />
        </label>
        <Button variant="primary" disabled={run.isPending || (!channel && !pct)} onClick={() => run.mutate({ channel: channel || null, agents_pct: pct ? pct / 100 : null })}>Run</Button>
      </div>
      {d && (
        <div className="mt-4 text-[14.5px]">
          <p className="m-0"><b className="tabular">{d.moved.toLocaleString()}</b> of {d.scheduled_before.toLocaleString()} planned actions would slip to tomorrow, and <b className="tabular">{d.dropped.toLocaleString()}</b> of them are high or very high break risk.</p>
          <ul className="mb-0 mt-2 pl-5 text-muted">{(d.by_treatment ?? []).map((t: Json) => <li key={t.treatment}>{TREATMENT[t.treatment] ?? t.treatment}: {t.moved.toLocaleString()}</li>)}</ul>
        </div>
      )}
    </Card>
  );
}
