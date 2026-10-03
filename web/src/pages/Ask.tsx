import { Search } from "lucide-react";
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
export default function Ask() {
  const [q, setQ] = useState("Which customers are most likely to break a promise to pay this week?");
  const ask = useAsk();
  const r = ask.data;
  return (
    <>
      <SectionTag as="h1" subtitle="Plain-English questions. Every answer shows its SQL, sources and caveats.">Collections Ask</SectionTag>
      <Card variant="grey" className="mb-6">
        <form onSubmit={(e) => { e.preventDefault(); ask.mutate(q); }} className="flex gap-3">
          <label htmlFor="ask-q" className="sr-only">Question</label>
          <div className="flex flex-1 items-center gap-2 rounded-[var(--radius-md)] border border-ink bg-white px-3"><Search aria-hidden size={18} /><input id="ask-q" value={q} onChange={(e) => setQ(e.target.value)} className="w-full border-0 py-3 outline-none" /></div>
          <button className="rounded-[var(--radius-md)] bg-ink px-6 text-white shadow-[var(--shadow-hard)]">Ask</button>
        </form>
      </Card>
      {ask.isPending && <Skeleton lines={6} />}
      {r?.refused && <RefusalCard reason={r.refusal_reason ?? ""} alternative="Cure rate by province this month" />}
      {r && !r.refused && (
        <div className="space-y-5">
          <ChipEditor chips={chipsFrom(r.chips)} />
          <DataTable columns={r.columns ?? []} rows={r.rows ?? []} />
          {r.insight && <Card><Badge kind="llm">Insight · from these rows only</Badge><p className="mb-0">{r.insight}</p></Card>}
          <div className="flex flex-wrap gap-2">{(r.followups ?? []).map((f) => <button key={f} type="button" onClick={() => { setQ(f); ask.mutate(f); }} className="rounded-full border border-ink bg-white px-3 py-1 text-sm">{f}</button>)}</div>
          <details className="rounded-[var(--radius-md)] border border-grey-300 bg-white p-4" open>
            <summary className="cursor-pointer font-medium">How I got this</summary>
            <div className="mt-3 space-y-3">
              {r.sql && <SqlBlock sql={r.sql} source={r.sql_source} />}
              <p className="m-0 text-sm">Data products: {(r.sources ?? []).join(", ")}</p>
              {(r.preflight?.incidents ?? []).map((i, n) => <p key={n} className="m-0 text-sm text-amber">⚠ {String(i.event_id ?? "")}: {String(i.text ?? "")}</p>)}
              {(r.caveats ?? []).map((c) => <p key={c} className="m-0 text-sm text-muted">{c}</p>)}
            </div>
          </details>
        </div>
      )}
    </>
  );
}
