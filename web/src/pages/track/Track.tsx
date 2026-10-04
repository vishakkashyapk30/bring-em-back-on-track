import clsx from "clsx";
import { ArrowRight, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { trackPath, useTrackKinds, useTrackSubjects, type TrackKind } from "@/api/track";
import { Card } from "@/components/Card";
import { SearchBox } from "@/components/FilterBar";
import { SectionTag } from "@/components/SectionTag";
import { EmptyState, ErrorState, QueryState, Skeleton } from "@/components/States";

const INTRO: Record<string, string> = {
  agent: "Pick one of your own customers and follow everything that happened, in order.",
  hardship_specialist: "Pick a customer on your board, flagged, or assigned to you, and follow their hardship journey.",
  team_lead: "Pick an agent on your team, or an employer from the radar, and follow it over time.",
  analyst: "Pick a cohort of cases and follow its cure and roll rates. Aggregates only; groups under 10 are hidden.",
  steward: "Pick a customer identity or a data product and follow its lineage, tests and quality.",
};
const PLACEHOLDER: Record<string, string> = {
  customer: "Name, golden ID or case ID", agent: "Name or agent ID", employer: "Employer key or industry", cohort: "Month, province, product, strategy or FSA (e.g. N9A)",
  identity: "Golden ID, e.g. G-JAT7827", product: "Table name, e.g. c360",
};

/** Track: choose ONE subject to follow. The list is scoped by the API (your own cases, your team, your row scope). */
export default function Track() {
  const kinds = useTrackKinds();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const list = kinds.data?.kinds ?? [];
  const kind = (list.some((k) => k.kind === sp.get("kind")) ? sp.get("kind") : list[0]?.kind) as TrackKind | undefined;
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(q), 250); return () => clearTimeout(t); }, [q]);
  const subjects = useTrackSubjects(kind, debounced);
  const sug = kinds.data?.suggested;
  const sugKind = kinds.data?.suggested_kind;

  // From the demo picker: /track?start=suggested goes straight to the suggested subject.
  useEffect(() => {
    if (sp.get("start") === "suggested" && sug && sugKind) nav(trackPath(sugKind, sug.id), { replace: true });
  }, [sp, sug, sugKind, nav]);

  if (kinds.isLoading) return <Skeleton lines={6} />;
  if (kinds.isError) return <ErrorState detail={(kinds.error as { reason?: string }).reason ?? "Couldn't load what you can track."} />;
  if (!list.length) return <EmptyState title="Nothing to track yet" detail="Tracking needs the real warehouse, and none is loaded." />;

  return (
    <>
      <SectionTag as="h1" subtitle={INTRO[kinds.data?.role ?? ""]}>Track</SectionTag>
      {sug && sugKind && (
        <Card className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="m-0 inline-flex items-center gap-1.5 text-[13px] font-semibold text-muted"><Sparkles size={14} aria-hidden /> Suggested to start</p>
            <p className="m-0 font-medium">{sug.label}</p>
            {sug.sublabel && <p className="m-0 text-[13.5px] text-muted">{sug.sublabel}</p>}
          </div>
          <Link to={trackPath(sugKind, sug.id)} className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-md)] bg-brand px-4 text-[15px] font-medium text-white no-underline hover:bg-brand-700 hover:no-underline">
            Track this <ArrowRight size={16} aria-hidden />
          </Link>
        </Card>
      )}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        {list.length > 1 ? (
          <KindSwitch value={kind ?? list[0].kind} options={list.map((k) => [k.kind, k.label])}
            onChange={(v) => { setQ(""); setDebounced(""); setSp({ kind: v }, { replace: true }); }} />
        ) : <p className="m-0 text-[14px] text-muted">{list[0].hint}</p>}
        <SearchBox label={`Search ${list.find((k) => k.kind === kind)?.label.toLowerCase() ?? "subjects"}`} placeholder={PLACEHOLDER[kind ?? ""] ?? "Search"} value={q} onChange={setQ} />
      </div>
      {list.length > 1 && <p className="mb-3 mt-0 text-[13.5px] text-muted">{list.find((k) => k.kind === kind)?.hint}</p>}
      <QueryState q={subjects}>
        {(subjects.data?.items ?? []).length === 0 ? (
          <EmptyState title="No matches" detail={q ? "Try another search." : "There is nothing in your scope to track here."} />
        ) : (
          <>
            <ul aria-label="Subjects you can track" className="m-0 list-none divide-y divide-grey-300/70 overflow-hidden rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-0">
              {subjects.data!.items.map((s) => (
                <li key={s.id}>
                  <Link to={trackPath(kind!, s.id)} className="flex min-h-12 items-center gap-3 px-4 py-3 text-ink no-underline transition-colors hover:bg-cream/70 hover:no-underline focus-visible:bg-brand-50">
                    <span className="min-w-0 flex-1">
                      <span className="block break-words font-medium">{s.label}</span>
                      {s.sublabel && <span className="block break-words text-[13px] text-muted">{s.sublabel}</span>}
                    </span>
                    {s.badges.map((b) => <span key={b} className="hidden shrink-0 text-[13px] font-semibold text-amber sm:inline">{b}</span>)}
                    <ArrowRight size={16} aria-hidden className="shrink-0 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
            {subjects.data?.note && <p className="mb-0 mt-3 text-[13px] text-muted">{subjects.data.note}</p>}
          </>
        )}
      </QueryState>
    </>
  );
}

/** Two or three subject types: white buttons, the chosen one outlined and tinted in brand red (no dark fills). */
export function KindSwitch({ value, options, onChange }: { value: string; options: [string, string][]; onChange: (v: TrackKind) => void }) {
  return (
    <div role="group" aria-label="What to track" className="inline-flex max-w-full flex-wrap gap-2">
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v as TrackKind)}
          className={clsx("h-10 shrink-0 whitespace-nowrap rounded-[var(--radius-md)] border px-4 text-[14.5px] font-medium transition-colors",
            value === v ? "border-brand bg-brand-50 text-brand-700" : "border-grey-300 bg-white text-ink hover:border-ink/40")}>{text}</button>
      ))}
    </div>
  );
}
