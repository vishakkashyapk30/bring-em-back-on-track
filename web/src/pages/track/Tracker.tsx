import { ArrowLeft, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { useMe } from "@/api/hooks";
import type { WatchKind } from "@/api/inbox";
import { useTrack } from "@/api/track";
import { Card } from "@/components/Card";
import { ErrorState, Skeleton } from "@/components/States";
import { PageTabs } from "@/components/Tabs";
import { WatchButton } from "@/components/WatchButton";

import { ActionsPanel } from "./actions";
import { Insights, SectionView } from "./parts";

const WATCH_KIND: Record<string, WatchKind> = { customer: "customer", agent: "agent", employer: "employer", cohort: "cohort", identity: "identity", product: "data_product" };
const CARE = /hardship|vulnerable/i;

/** One subject followed over time: header, the insight strip (each with reason and source), then tabs for the
 * history views and the actions open to this person. Compact: one screen per tab, no long scroll. */
export default function Tracker() {
  const { kind = "", id: raw = "" } = useParams();
  const id = decodeURIComponent(raw);
  const q = useTrack(kind, id);
  const me = useMe();
  const back = <Link to={`/track?kind=${kind}`} className="mb-4 inline-flex min-h-10 items-center gap-1.5 text-[13.5px] font-medium text-muted no-underline hover:text-ink hover:no-underline"><ArrowLeft size={15} aria-hidden /> Pick another</Link>;

  if (q.isLoading) return <div className="space-y-6">{back}<Skeleton lines={4} /><Skeleton lines={8} /></div>;
  if (q.isError) {
    const e = q.error as { forbidden?: boolean; reason?: string; status?: number };
    return <div>{back}<ErrorState forbidden={e.forbidden} title={e.forbidden ? "You can't track this" : "Couldn't load this subject"} detail={e.reason ?? "Try again in a moment."} /></div>;
  }
  const v = q.data!;
  const first = v.sections[0];
  const tabs = [
    ...(first ? [{ id: first.id, label: first.label, count: first.kind === "timeline" ? first.events.length : undefined }] : []),
    { id: "actions", label: v.kind === "cohort" ? "Propose" : "Act", count: v.actions.filter((a) => a.kind !== "link").length || undefined },
    ...v.sections.slice(1).map((s) => ({ id: s.id, label: s.label })),
  ];
  return (
    <>
      {back}
      <Card hard className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="m-0 text-[13px] font-semibold text-brand">Tracking {v.kind === "product" ? "a data product" : v.kind === "identity" ? "an identity" : v.kind === "employer" ? "an employer" : v.kind === "agent" ? "an agent" : `a ${v.kind}`}</p>
            <h1 className="m-0 break-words text-[1.75rem] leading-tight">{v.title}</h1>
            {v.subtitle && <p className="mb-0 mt-1 break-words text-[14px] text-muted">{v.subtitle}</p>}
            {v.badges.length > 0 && (
              <p className="mb-0 mt-2 flex flex-wrap gap-x-4 gap-y-1">
                {v.badges.map((b) => <span key={b} className={`inline-flex items-center gap-1.5 text-[14px] font-semibold ${CARE.test(b) ? "text-amber" : "text-ink"}`}>{CARE.test(b) && <ShieldAlert size={14} aria-hidden />}{b}</span>)}
              </p>
            )}
          </div>
          <WatchButton kind={WATCH_KIND[v.kind] ?? "customer"} id={v.id} label={v.title} />
        </div>
        {v.figures.length > 0 && (
          <dl className="m-0 mt-4 grid grid-cols-2 gap-4 border-t border-grey-300/60 pt-4 sm:grid-cols-4">
            {v.figures.map((f) => (
              <div key={f.label} className="min-w-0"><dt className="text-[12.5px] font-medium text-muted">{f.label}</dt>
                <dd className="m-0 mt-0.5 break-words font-[family-name:var(--font-display)] text-[20px] font-semibold tabular">{f.value}</dd></div>
            ))}
          </dl>
        )}
        {v.aggregates_only && <p className="mb-0 mt-3 text-[13px] text-muted">Aggregates only. Groups under 10 are hidden, and no individual customer is shown.</p>}
      </Card>
      <Insights items={v.insights} />
      <PageTabs label="Tracker views" tabs={tabs}>
        {(t) => t === "actions"
          ? <ActionsPanel kind={v.kind} id={v.id} actions={v.actions} />
          : <SectionView s={v.sections.find((s) => s.id === t) ?? first} playable={me.data?.role === "hardship_specialist"} />}
      </PageTabs>
      <p className="mb-0 mt-6 text-[12.5px] text-muted">Data as of {v.meta.as_of?.slice(0, 10) ?? "the last build"}{v.meta.freshness_hours != null ? `, built ${v.meta.freshness_hours} h ago` : ""}. Read-only warehouse; every action is written to the audit log.</p>
    </>
  );
}
