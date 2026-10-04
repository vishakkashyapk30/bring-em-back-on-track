import { AlertTriangle, ArrowRight, Loader2, Search } from "lucide-react";
import { useState } from "react";

import { useAsk, useAskSuggestions } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ChipEditor } from "@/components/ChipEditor";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { SqlBlock } from "@/components/SqlBlock";
import { RefusalCard, Skeleton } from "@/components/States";
import { ModeSwitch, useAnswerMode, useLlmStatus } from "@/lib/answerMode";

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

const heading = (c: string) => { const t = c.replace(/_pct$/, " (%)").replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
/** Answer cells: codes read as words, whole numbers get thousands separators. */
const cellText = (v: unknown) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString("en-CA") : String(v))
  : typeof v === "string" && /^[a-z]+(_[a-z0-9]+)+$/.test(v) ? v.replace(/_/g, " ") : String(v ?? "n/a"));

export default function Ask() {
  const [q, setQ] = useState("");
  const ask = useAsk();
  const [mode] = useAnswerMode();
  const llm = useLlmStatus();
  const sugg = useAskSuggestions();
  const run = (question: string, m: "rules" | "llm" = mode) => ask.mutate({ question, mode: m });
  const r = ask.data;
  const freshness = (r as { freshness?: string | null } | undefined)?.freshness;
  return (
    <>
      <SectionTag as="h1" subtitle="Ask in plain English. Every answer shows the SQL or sources behind it, and any caveats.">Collections Ask</SectionTag>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) run(q); }}
        className="mb-4 flex gap-2 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-2 shadow-[var(--shadow-card)] transition-shadow focus-within:shadow-[var(--shadow-raised)]">
        <label htmlFor="ask-q" className="sr-only">Question</label>
        <div className="flex flex-1 items-center gap-2 px-3"><Search aria-hidden size={18} className="text-muted" />
          <input id="ask-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about collections data or policy" className="w-full border-0 bg-transparent py-2.5 text-[15px] outline-none" />
        </div>
        <Button type="submit" variant="primary" className="px-6" disabled={ask.isPending || !q.trim()}>
          {ask.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null} Ask
        </Button>
      </form>
      <ModeSwitch className="mb-4" />
      {!r && !ask.isPending && (
        <Card className="fade-in mb-6 p-0">
          <p className="m-0 border-b border-grey-300/70 px-5 py-3 text-[13.5px] text-muted">{sugg.data?.intro ?? "Not sure where to start?"} Try one of these.</p>
          <ul className="m-0 list-none divide-y divide-grey-300/60 p-0">
            {(sugg.data?.questions ?? []).map((ex) => (
              <li key={ex}>
                <button type="button" onClick={() => { setQ(ex); run(ex); }}
                  className="group flex w-full items-center justify-between gap-4 bg-transparent px-5 py-2.5 text-left text-[14.5px] text-ink transition-colors hover:bg-cream/70 hover:text-brand">
                  {ex}<ArrowRight size={15} aria-hidden className="shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-brand" />
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {ask.isPending && <Skeleton lines={6} />}
      {r?.refused && (
        <>
          <RefusalCard reason={r.refusal_reason ?? ""} alternative={(sugg.data?.questions ?? [])[0]} />
          {mode === "rules" && llm.available && !String(r.refusal_reason ?? "").startsWith("Refused:") && (
            <p className="mt-3 text-sm">Not what you expected? <button type="button" className="text-brand underline-offset-4 hover:underline" onClick={() => run(q, "llm")}>Try it with the language model</button> (rules still check the SQL and refusals).</p>
          )}
        </>
      )}
      {r && !r.refused && (
        <div className="space-y-4">
          <p className="m-0 flex flex-wrap items-center gap-2 text-sm text-muted">
            <Badge kind={r.answered_by === "language model" ? "llm" : "ok"}>{r.answered_by === "language model" ? "Understood by a language model" : "Answered by rules"}</Badge>
            {r.mode_note && <span>{r.mode_note}</span>}
          </p>
          <ChipEditor chips={chipsFrom(r.chips)} />
          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,1fr)_440px]">
            <div className="min-w-0 space-y-4">
              <DataTable columns={(r.columns ?? []).map(heading)} rows={r.rows ?? []} render={(v) => cellText(v)} />
              {r.insight && <Card><Badge kind="llm">Insight · from these rows only</Badge><p className="mb-0 mt-1">{r.insight}</p></Card>}
            </div>
            <div className="min-w-0 space-y-4">
              <details className="rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4" open>
                <summary className="cursor-pointer font-medium">How I got this</summary>
                <div className="mt-3 space-y-2">
                  {r.sql && <SqlBlock sql={r.sql} source={r.sql_source} />}
                  <p className="m-0 text-[13.5px]">Data products: {(r.sources ?? []).join(", ")}</p>
                  {freshness && <p className="m-0 text-[13.5px]">Data built {new Date(freshness).toLocaleString()}, snapshot 28 Sep 2026.</p>}
                  {(r.preflight?.incidents ?? []).map((i, n) => <p key={n} className="m-0 flex items-start gap-1.5 text-[13.5px] text-amber"><AlertTriangle size={14} aria-hidden className="mt-[3px] shrink-0" /><span>{String(i.event_id ?? "")}: {String(i.text ?? "")}</span></p>)}
                  {(r.caveats ?? []).map((c) => <p key={c} className="m-0 text-[13.5px] text-muted">{c}</p>)}
                </div>
              </details>
              {(r.followups ?? []).length > 0 && (
                <Card className="p-0">
                  <p className="m-0 border-b border-grey-300/70 px-4 py-2.5 text-[13.5px] text-muted">You could also ask</p>
                  <ul className="m-0 list-none divide-y divide-grey-300/60 p-0">
                    {(r.followups ?? []).map((f) => (
                      <li key={f}><button type="button" onClick={() => { setQ(f); run(f); }} className="group flex w-full items-center justify-between gap-3 bg-transparent px-4 py-2 text-left text-[14px] transition-colors hover:bg-cream/70 hover:text-brand">{f}<ArrowRight size={14} aria-hidden className="shrink-0 text-muted group-hover:text-brand" /></button></li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
