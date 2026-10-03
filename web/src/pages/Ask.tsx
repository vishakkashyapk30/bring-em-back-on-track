import { Loader2, Search } from "lucide-react";
import { useState } from "react";

import { useAsk } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { ChipEditor } from "@/components/ChipEditor";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { SqlBlock } from "@/components/SqlBlock";
import { RefusalCard, Skeleton } from "@/components/States";

function chipsFrom(ch: Record<string, unknown> | null | undefined) {
  if (!ch) return [];
  const out: { key: string; label: string }[] = [];
  if (ch.metric_id) out.push({ key: "metric", label: String(ch.metric_id) });
  (ch.filters as { field: string; value: unknown }[] | undefined)?.forEach((f, i) => out.push({ key: `f${i}`, label: `${f.field} = ${String(f.value)}` }));
  const tr = ch.time_range as { label?: string } | undefined;
  if (tr?.label) out.push({ key: "time", label: tr.label });
  (ch.dimensions as string[] | undefined)?.forEach((d) => out.push({ key: `d-${d}`, label: `by ${d}` }));
  return out;
}

/** Collections Ask. TODO(WS-G): question history, chip editing re-runs the query. */
const EXAMPLES = [
  "What was the broken-promise rate by agent site for promises due in July-September 2026?",
  "How many collections cases are open today, by current bucket?",
  "Does the National Do Not Call List stop collection calls?",
  "What is the hardship rate of cases opened in 2026, by primary product?",
  "Summarise the most recent recorded call on case CS-2026-614370: what did the customer say and agree to?",
  "List the gender and marital status of customers who broke a promise last month.",
];

export default function Ask() {
  const [q, setQ] = useState("");
  const ask = useAsk();
  const r = ask.data;
  const freshness = (r as { freshness?: string | null } | undefined)?.freshness;
  return (
    <>
      <SectionTag as="h1" subtitle="Ask in plain English. Every answer shows the SQL or sources behind it, and any caveats.">Collections Ask</SectionTag>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask.mutate(q); }}
        className="mb-4 flex gap-2 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-2 shadow-[var(--shadow-card)] transition-shadow focus-within:shadow-[var(--shadow-raised)]">
        <label htmlFor="ask-q" className="sr-only">Question</label>
        <div className="flex flex-1 items-center gap-2 px-3"><Search aria-hidden size={18} className="text-muted" />
          <input id="ask-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about collections data or policy" className="w-full border-0 bg-transparent py-2.5 text-[15px] outline-none" />
        </div>
        <button disabled={ask.isPending || !q.trim()} className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-md)] bg-brand px-6 font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-60">
          {ask.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null} Ask
        </button>
      </form>
      {!r && !ask.isPending && (
        <div className="fade-in mb-6">
          <p className="mb-2 text-sm text-muted">Not sure where to start? Try one of these.</p>
          <div className="flex flex-col items-start gap-1">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => { setQ(ex); ask.mutate(ex); }}
                className="rounded-[var(--radius-sm)] px-0 py-1 text-left text-[15px] text-brand underline-offset-4 hover:underline">{ex}</button>
            ))}
          </div>
        </div>
      )}
      {ask.isPending && <Skeleton lines={6} />}
      {r?.refused && <RefusalCard reason={r.refusal_reason ?? ""} alternative="Cure rate by province this month" />}
      {r && !r.refused && (
        <div className="space-y-5">
          <ChipEditor chips={chipsFrom(r.chips)} />
          <DataTable columns={r.columns ?? []} rows={r.rows ?? []} />
          {r.insight && <Card><Badge kind="llm">Insight · from these rows only</Badge><p className="mb-0">{r.insight}</p></Card>}
          {(r.followups ?? []).length > 0 && (
            <div>
              <p className="mb-1 text-sm text-muted">You could also ask:</p>
              <div className="flex flex-col items-start gap-1">{(r.followups ?? []).map((f) => <button key={f} type="button" onClick={() => { setQ(f); ask.mutate(f); }} className="px-0 py-0.5 text-left text-[15px] text-brand underline-offset-4 hover:underline">{f}</button>)}</div>
            </div>
          )}
          <details className="rounded-[var(--radius-md)] border border-grey-300 bg-white p-4" open>
            <summary className="cursor-pointer font-medium">How I got this</summary>
            <div className="mt-3 space-y-3">
              {r.sql && <SqlBlock sql={r.sql} source={r.sql_source} />}
              <p className="m-0 text-sm">Data products: {(r.sources ?? []).join(", ")}</p>
              {freshness && <p className="m-0 text-sm">Data built {new Date(freshness).toLocaleString()}, snapshot 28 Sep 2026.</p>}
              {(r.preflight?.incidents ?? []).map((i, n) => <p key={n} className="m-0 text-sm text-amber">⚠ {String(i.event_id ?? "")}: {String(i.text ?? "")}</p>)}
              {(r.caveats ?? []).map((c) => <p key={c} className="m-0 text-sm text-muted">{c}</p>)}
            </div>
          </details>
        </div>
      )}
    </>
  );
}
