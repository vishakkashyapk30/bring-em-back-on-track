import clsx from "clsx";
import {
  AlertTriangle, Bell, CheckCircle2, ChevronRight, CircleDot, CreditCard, Database, FileText, FlaskConical, GitMerge, HandCoins,
  Copy, Info, Mail, MessageSquare, Mic, Phone, ShieldAlert, Smartphone, Sparkles, Wrench, Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import type { Fact, Insight, Section, Series, Source, Table, Tone, TrackEvent } from "@/api/track";
import { DataTable } from "@/components/DataTable";
import { FilterChips } from "@/components/FilterBar";
import { RecordingCard } from "@/components/RecordingCard";
import { Footnote } from "@/components/States";

const TONE_TEXT: Record<Tone, string> = { info: "text-ink", care: "text-amber", good: "text-teal", warn: "text-danger" };
const TONE_ICON: Record<Tone, typeof Info> = { info: Info, care: ShieldAlert, good: CheckCircle2, warn: AlertTriangle };
const TONE_WORD: Record<Tone, string> = { info: "Note", care: "Care", good: "Good", warn: "Look at this" };

/** The query behind a number, on a light cream panel (no dark backgrounds), with a copy button. */
function SqlView({ sql }: { sql: string }) {
  const copy = () => { navigator.clipboard?.writeText(sql); toast.success("SQL copied"); };
  return (
    <div className="rounded-[var(--radius-md)] border border-grey-300/70 bg-cream p-3">
      <div className="mb-1 flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-muted"><Database size={13} aria-hidden /> SQL (read-only warehouse)</span>
        <button type="button" onClick={copy} className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-[var(--radius-sm)] border border-grey-300 bg-white px-2 text-[12.5px] text-ink hover:bg-grey-100">
          <Copy size={12} aria-hidden /> Copy
        </button>
      </div>
      <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[12.5px] leading-relaxed text-ink"><code>{sql}</code></pre>
    </div>
  );
}

/** Where a number came from: the SQL (shown verbatim) or the record ids behind it. */
export function SourceView({ source }: { source: Source }) {
  return (
    <details className="group mt-2">
      <summary className="inline-flex min-h-6 cursor-pointer items-center gap-1 text-[13px] font-medium text-brand">
        <Database size={13} aria-hidden /> Source: {source.label}
      </summary>
      <div className="mt-2">
        {source.sql ? <SqlView sql={source.sql} /> : (
          <p className="m-0 break-words text-[13px] text-muted">
            {source.table && <><span className="font-mono">{source.table}</span>{source.ids.length > 0 && ": "}</>}
            {source.ids.length > 0 ? <span className="font-mono">{source.ids.join(", ")}</span> : !source.table && "Report file"}
          </p>
        )}
      </div>
    </details>
  );
}

/** The "what changed recently" strip: each insight says what, why, and where it came from. */
export function Insights({ items }: { items: Insight[] }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = all ? items : items.slice(0, 3);
  return (
    <section aria-labelledby="insights-h" className="mb-6">
      <h2 id="insights-h" className="mb-3 mt-0 text-[1.0625rem]">What changed and why it matters</h2>
      <ul className="m-0 grid list-none grid-cols-[minmax(0,1fr)] gap-3 p-0 md:grid-cols-2 xl:grid-cols-3">
        {shown.map((i) => {
          const Icon = TONE_ICON[i.tone];
          return (
            <li key={i.id} className="min-w-0 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4">
              <p className={clsx("m-0 flex items-start gap-2 font-medium", TONE_TEXT[i.tone])}>
                <Icon size={16} aria-hidden className="mt-0.5 shrink-0" /><span className="sr-only">{TONE_WORD[i.tone]}: </span>
                <span className="min-w-0 break-words text-ink">{i.title}</span>
              </p>
              <p className="mb-0 mt-1 text-[13.5px] text-muted">{i.reason}</p>
              <SourceView source={i.source} />
            </li>
          );
        })}
      </ul>
      {items.length > 3 && (
        <button type="button" aria-expanded={all} onClick={() => setAll(!all)} className="mt-2 min-h-10 rounded-[var(--radius-md)] px-2 text-[13.5px] font-medium text-brand hover:bg-brand-50">
          {all ? "Show fewer" : `Show ${items.length - 3} more`}
        </button>
      )}
    </section>
  );
}

const EV_ICON: Record<string, typeof Info> = {
  account: CreditCard, case: FileText, promise: HandCoins, contact: Mail, note: FileText, call: Phone, recording: Mic, hardship: ShieldAlert,
  nba: Sparkles, summary: CheckCircle2, offer: HandCoins, plan: CircleDot, simulation: FlaskConical, signal: ShieldAlert, merge: GitMerge,
  review: GitMerge, test: CheckCircle2, drift: Wrench, quality: Bell,
};
const EV_LABEL: Record<string, string> = {
  account: "Accounts", case: "Cases", promise: "Promises", contact: "Contacts", note: "Notes", call: "Calls", recording: "Recordings", hardship: "Hardship",
  nba: "Decisions", summary: "Summaries", offer: "Offers", plan: "Plans", simulation: "Simulations", signal: "Signals", merge: "Merges", review: "Reviews",
  drift: "Schema changes", quality: "Incidents", test: "Tests",
};
const CONTACT_ICON: [string, typeof Info][] = [["Call", Phone], ["SMS", MessageSquare], ["Email", Mail], ["App", Smartphone], ["System", Zap]];
const fmt = (ts: string) => {
  const d = new Date(ts.length <= 10 ? `${ts}T00:00:00` : ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleDateString("en-CA", { day: "numeric", month: "short", year: "numeric" });
};

/** One chronological list across every source, with type filters and 20 rows at a time. */
export function TimelineView({ events, playable }: { events: TrackEvent[]; playable?: boolean }) {
  const [type, setType] = useState("all");
  const [n, setN] = useState(20);
  const [playing, setPlaying] = useState<string | null>(null);
  const counts = useMemo(() => events.reduce<Record<string, number>>((a, e) => ({ ...a, [e.type]: (a[e.type] ?? 0) + 1 }), {}), [events]);
  const shown = events.filter((e) => type === "all" || e.type === type);
  if (!events.length) return <p className="text-[14px] text-muted">Nothing on record yet.</p>;
  return (
    <div>
      <div className="mb-3"><FilterChips label="Show events of type" value={type} onChange={(v) => { setType(v); setN(20); }}
        chips={[{ id: "all", label: "All", count: events.length }, ...Object.keys(counts).map((k) => ({ id: k, label: EV_LABEL[k] ?? k, count: counts[k] }))]} /></div>
      <div className="max-h-[min(620px,70vh)] overflow-y-auto rounded-[var(--radius-lg)] border border-grey-300/70 bg-white px-4 py-2" tabIndex={0} aria-label="Timeline, scrollable">
      <ol className="relative m-0 list-none p-0" aria-label="Timeline, newest first">
        <span aria-hidden className="absolute bottom-3 left-[15px] top-3 w-px bg-grey-300" />
        {shown.slice(0, n).map((e, i) => {
          const Icon = (e.type === "contact" && CONTACT_ICON.find(([p]) => e.title.startsWith(p))?.[1]) || EV_ICON[e.type] || Info;
          return (
            <li key={`${e.type}-${e.ref}-${i}`} className="relative flex gap-3 py-2.5">
              <span className={clsx("z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full border bg-white",
                e.tone === "warn" ? "border-brand/40 text-brand" : e.tone === "care" ? "border-amber/40 text-amber" : e.tone === "good" ? "border-teal/40 text-teal" : "border-grey-300 text-muted")}>
                <Icon size={15} aria-hidden />
              </span>
              <div className="min-w-0 flex-1 pt-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="min-w-0 break-words text-[14px] font-medium">{e.title}</span>
                  <time dateTime={e.ts} className="shrink-0 text-[12.5px] text-muted tabular">{fmt(e.ts)}</time>
                </div>
                {e.detail && <p className="m-0 break-words text-[13.5px] text-ink/80">{e.detail}</p>}
                <p className="m-0 break-all text-[12px] text-muted">{e.table && <span className="font-mono">{e.table}</span>}{e.ref && <> · <span className="font-mono">{e.ref}</span></>}</p>
                {e.link && <Link to={e.link} className="mt-0.5 inline-flex min-h-6 items-center gap-0.5 text-[13px] font-medium">{e.type === "recording" ? "Play on the call page" : "Open"} <ChevronRight size={14} aria-hidden /></Link>}
                {playable && !e.link && e.type === "recording" && e.ref && (
                  <button type="button" onClick={() => setPlaying(playing === e.ref ? null : e.ref!)} aria-expanded={playing === e.ref}
                    className="mt-0.5 inline-flex min-h-6 items-center gap-1 text-[13px] font-medium text-brand">
                    <Mic size={13} aria-hidden /> {playing === e.ref ? "Hide the recording" : "Play the recording"}
                  </button>
                )}
                {playing === e.ref && e.type === "recording" && e.ref && <div className="mt-2"><RecordingCard contactId={e.ref} /></div>}
              </div>
            </li>
          );
        })}
      </ol>
      {shown.length > n && (
        <button type="button" onClick={() => setN(n + 30)} className="mt-1 w-full rounded-[var(--radius-md)] py-2 text-[13.5px] font-medium text-brand transition-colors hover:bg-brand-50">
          Show more ({shown.length - n} left)
        </button>
      )}
      </div>
    </div>
  );
}

const css = (v: string, fallback: string) => (typeof document !== "undefined" && getComputedStyle(document.documentElement).getPropertyValue(v).trim()) || fallback;
const DASH = [undefined, "6 4", "2 4"]; // secondary encoding: colour is never the only way to tell lines apart

function fmtValue(v: number | null | undefined, unit: Series["unit"]) {
  if (v == null) return "hidden or n/a";
  if (unit === "pct") return `${(v * 100).toFixed(1)}%`;
  if (unit === "cad") return v.toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });
  return v.toLocaleString();
}

/** A line chart in the app's chart style (brand red, ink, teal; recessive grid; crosshair tooltip), with a table view. */
export function SeriesChart({ s }: { s: Series }) {
  const colours = [css("--color-brand", "#a71f3e"), css("--color-ink", "#191a23"), css("--color-teal", "#19695d")];
  const grid = css("--color-grey-300", "#d9d9de");
  const muted = css("--color-muted", "#5f6170");
  const white = css("--color-white", "#ffffff");
  const data = s.x.map((x, i) => Object.fromEntries([["x", x], ...s.lines.map((l) => [l.name, l.values[i]])]));
  const hasData = s.lines.some((l) => l.values.some((v) => v != null));
  return (
    <figure className="m-0 min-w-0 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4">
      <figcaption className="mb-2 text-[15px] font-medium">{s.title}</figcaption>
      {hasData ? (
        <div className="h-[260px]" role="img" aria-label={`${s.title}. ${s.lines.map((l) => `${l.name}: latest ${fmtValue([...l.values].reverse().find((v) => v != null), s.unit)}`).join("; ")}. A table view follows.`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -4 }}>
              <CartesianGrid stroke={grid} strokeWidth={1} vertical={false} />
              <XAxis dataKey="x" stroke={grid} tick={{ fill: muted, fontSize: 12 }} interval="preserveStartEnd" minTickGap={16} />
              <YAxis stroke={grid} tick={{ fill: muted, fontSize: 12 }} width={48} domain={s.unit === "pct" ? [0, "auto"] : [0, "auto"]}
                tickFormatter={(v) => (s.unit === "pct" ? `${Math.round(v * 100)}%` : Number(v).toLocaleString())} />
              <Tooltip cursor={{ stroke: grid }} formatter={(v) => fmtValue(v as number, s.unit)} contentStyle={{ borderRadius: 10, border: `1px solid ${grid}`, fontSize: 13 }} />
              {s.lines.length > 1 && <Legend wrapperStyle={{ fontSize: 13, color: muted }} iconType="plainline" />}
              {s.lines.map((l, i) => (
                <Line key={l.name} type="monotone" dataKey={l.name} stroke={colours[i % 3]} strokeWidth={2} strokeDasharray={DASH[i % 3]} connectNulls={false}
                  strokeLinecap="round" dot={{ r: 4, fill: colours[i % 3], stroke: white, strokeWidth: 2 }} activeDot={{ r: 6, stroke: white, strokeWidth: 2 }} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : <p className="m-0 py-8 text-center text-[14px] text-muted">No points to show: every period is empty or hidden (fewer than 10).</p>}
      <details className="mt-2">
        <summary className="cursor-pointer text-[13px] font-medium text-brand">Show as a table</summary>
        <div className="mt-2"><DataTable bare columns={["Period", ...s.lines.map((l) => l.name)]} rows={s.x.map((x, i) => [x, ...s.lines.map((l) => fmtValue(l.values[i], s.unit))])} maxHeight="260px" /></div>
      </details>
      {(s.note || s.suppressed > 0) && <Footnote>{s.note}{s.suppressed > 0 ? ` ${s.suppressed} point(s) hidden for small groups.` : ""}</Footnote>}
      <SourceView source={s.source} />
    </figure>
  );
}

const cell = (v: unknown, col: string) => {
  if (typeof v === "number") {
    if (/rate|survival/i.test(col) && v <= 1 && v >= 0 && !Number.isInteger(v)) return `${(v * 100).toFixed(1)}%`;
    if (/amount|balance|past due|paid|exposure/i.test(col)) return v.toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });
    return v.toLocaleString();
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return v == null || v === "" ? "n/a" : String(v);
};

export function TableView({ t }: { t: Table }) {
  return (
    <div className="min-w-0">
      {t.title && <h3 className="mb-2 mt-0 text-[1.0625rem]">{t.title}</h3>}
      <DataTable bare columns={t.columns} rows={t.rows} render={(v, col) => cell(v, col)} searchable={t.rows.length > 12 ? "Search this table" : undefined} />
      {t.note && <Footnote>{t.note}</Footnote>}
      <SourceView source={t.source} />
    </div>
  );
}

export function Facts({ items }: { items: Fact[] }) {
  return (
    <dl className="m-0 grid grid-cols-2 gap-4 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4 sm:grid-cols-3 lg:grid-cols-4">
      {items.map((f) => <div key={f.label} className="min-w-0"><dt className="text-[13px] text-muted">{f.label}</dt><dd className="m-0 break-words font-semibold tabular">{f.value}</dd></div>)}
    </dl>
  );
}

export function SectionView({ s, playable }: { s: Section; playable?: boolean }) {
  return (
    <section aria-label={s.label} className="min-w-0">
      {s.intro && <p className="mb-3 mt-0 max-w-3xl text-[14px] text-muted">{s.intro}</p>}
      {s.kind === "timeline" && <TimelineView events={s.events} playable={playable} />}
      {s.kind === "series" && <div className={`grid grid-cols-[minmax(0,1fr)] gap-4 ${s.series.length > 1 ? "xl:grid-cols-2" : ""}`}>{s.series.map((x) => <SeriesChart key={x.title} s={x} />)}</div>}
      {s.kind === "table" && <div className="space-y-6">{s.tables.map((t, i) => <TableView key={i} t={t} />)}</div>}
      {s.kind === "facts" && <Facts items={s.facts} />}
    </section>
  );
}
