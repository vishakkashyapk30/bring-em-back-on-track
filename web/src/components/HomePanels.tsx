import { ArrowRight, Star } from "lucide-react";
import { Link } from "react-router-dom";

import { KIND_LABEL, TRACK_ROUTE, useInbox, useMarkSeen, useWatchlist, type WatchItem } from "@/api/inbox";
import { Row } from "@/pages/Inbox";

import { Card } from "./Card";
import { SectionTag } from "./SectionTag";
import { Skeleton } from "./States";
import { WatchButton } from "./WatchButton";

/** Signed-in home: the three most urgent inbox items, with a link to the full inbox. */
export function InboxTop() {
  const q = useInbox();
  const d = q.data;
  return (
    <section aria-labelledby="home-inbox" className="min-w-0">
      <SectionTag id="home-inbox" subtitle={d ? (d.total ? `${d.total.toLocaleString("en-CA")} to look at now${(d.backlog ?? 0) > d.total ? `, ${(d.backlog ?? 0).toLocaleString("en-CA")} in the backlog` : ""}. The most urgent first.` : d.note ?? "Nothing is waiting for you right now.") : undefined}
        actions={<Link to="/inbox" className="inline-flex min-h-10 items-center gap-1 text-[14px] font-semibold">Open the inbox <ArrowRight size={15} aria-hidden /></Link>}>
        Waiting for you
      </SectionTag>
      <Card className="p-0">
        {q.isLoading ? <div className="p-5"><Skeleton lines={3} /></div>
          : q.isError ? <p className="m-0 p-5 text-[14px] text-muted">Your inbox can't be loaded right now.</p>
          : d && d.top.length ? <ul className="m-0 list-none divide-y divide-grey-300/60 p-0">{d.top.map((i) => <Row key={i.id} i={i} compact />)}</ul>
          : <p className="m-0 p-5 text-[14px] text-muted">You're all caught up.</p>}
      </Card>
    </section>
  );
}

const href = (w: WatchItem) => (TRACK_ROUTE && w.track_link) || w.link;

/** Signed-in home: what you follow, and what changed since you last looked. Opening an item marks it as seen. */
export function WatchlistPanel() {
  const q = useWatchlist();
  const seen = useMarkSeen();
  const items = q.data?.items ?? [];
  return (
    <section aria-labelledby="home-watch" className="min-w-0">
      <SectionTag id="home-watch" subtitle={q.data ? (items.length ? `${q.data.changed} of ${items.length} changed since you last looked.` : undefined) : undefined}>
        Your watchlist
      </SectionTag>
      <Card className="p-0">
        {q.isLoading ? <div className="p-5"><Skeleton lines={3} /></div>
          : q.isError ? <p className="m-0 p-5 text-[14px] text-muted">Your watchlist can't be loaded right now.</p>
          : items.length === 0 ? (
            <p className="m-0 flex items-start gap-2 p-5 text-[14px] text-muted">
              <Star size={16} aria-hidden className="mt-0.5 shrink-0" />
              Nothing on your watchlist yet. Select Watch on a customer, agent, employer or data product to follow it here.
            </p>
          ) : (
            <ul className="m-0 list-none divide-y divide-grey-300/60 p-0">
              {items.map((w) => (
                <li key={`${w.kind}:${w.subject_id}`} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:justify-between sm:px-5">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-[13px] font-semibold text-muted">{KIND_LABEL[w.kind]}</span>
                      {w.available
                        ? <Link to={href(w)} onClick={() => seen.mutate({ kind: w.kind, id: w.subject_id })} className="break-words text-[15px] font-medium">{w.label}</Link>
                        : <span className="break-words text-[15px] font-medium">{w.label}</span>}
                    </div>
                    <p className="m-0 text-[14px] text-muted">{w.status}</p>
                    {w.changes.length > 0 ? (
                      <ul aria-label="Changed since you last looked" className="m-0 mt-1 list-disc pl-5 text-[14px] text-brand-700">
                        {w.changes.map((c) => <li key={c}>{c}</li>)}
                      </ul>
                    ) : w.available && <p className="m-0 mt-0.5 text-[13px] text-muted">No change since you last looked.</p>}
                  </div>
                  <WatchButton kind={w.kind} id={w.subject_id} label={w.label} className="self-start" />
                </li>
              ))}
            </ul>
          )}
      </Card>
    </section>
  );
}
