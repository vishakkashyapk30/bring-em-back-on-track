import clsx from "clsx";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { useInbox, type InboxGroup, type InboxItem } from "@/api/inbox";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { Footnote, QueryState } from "@/components/States";

const n = (v: number) => v.toLocaleString("en-CA");

/** /inbox: every pending human review for the signed-in person, grouped by type. Read-only: each item links to the
 * screen where it is approved, so the approval rules live in one place. */
export default function Inbox() {
  const q = useInbox();
  const d = q.data;
  const groups = d?.groups ?? [];
  const shown = groups.filter((g) => g.count > 0 || g.informational);
  return (
    <>
      <SectionTag as="h1" subtitle="Everything that needs your review, in one place. Open an item to act on it on its own screen.">
        Waiting for you
      </SectionTag>
      <QueryState q={q}>
        {d && (
          <>
            <p className="mb-4 mt-0 text-[15px]" aria-live="polite">
              {d.total === 0 ? (d.note ?? "Nothing is waiting for you right now.") : <><b className="tabular">{n(d.total)}</b> to look at now{(d.backlog ?? 0) > d.total ? <>, <span className="tabular">{n(d.backlog ?? 0)}</span> in the backlog</> : null}, data as of {d.as_of}.</>}
            </p>
            {shown.length > 1 && (
              <nav aria-label="Jump to a group" className="mb-5 flex flex-wrap gap-2">
                {shown.map((g) => (
                  <a key={g.type} href={`#inbox-${g.type}`} className="inline-flex min-h-10 items-center gap-2 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[14px] text-ink no-underline hover:border-ink/40 hover:no-underline">
                    {g.label} {!g.informational && <span className="tabular font-semibold text-brand-700">{n(g.count)}</span>}
                  </a>
                ))}
              </nav>
            )}
            {shown.length === 0 && (
              <Card className="py-8 text-center">
                <p className="m-0 font-medium">You're all caught up.</p>
                <p className="m-0 text-muted">Nothing waits for your approval. New items appear here as they arrive.</p>
              </Card>
            )}
            <div className="grid gap-4 xl:grid-cols-2">
              {shown.map((g) => <Group key={g.type} g={g} />)}
            </div>
            {d.not_available.length > 0 && (
              <section aria-labelledby="inbox-missing" className="mt-6">
                <h2 id="inbox-missing" className="m-0 text-[1rem]">Not shown here</h2>
                <ul className="mt-1 list-none p-0">
                  {d.not_available.map((m) => <li key={m.source}><Footnote className="my-1"><b>{m.source}:</b> {m.reason}</Footnote></li>)}
                </ul>
              </section>
            )}
          </>
        )}
      </QueryState>
    </>
  );
}

function Group({ g }: { g: InboxGroup }) {
  const more = g.count - g.items.length;
  return (
    <Card className="scroll-mt-24 p-0" id={`inbox-${g.type}`} role="region" aria-labelledby={`inbox-${g.type}-h`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-grey-300/70 px-4 py-3 sm:px-5">
        <h2 id={`inbox-${g.type}-h`} className="m-0 text-[1.125rem]">
          {g.label}{!g.informational && <span className="ml-2 tabular text-brand-700">{n(g.count)}</span>}
        </h2>
        <Link to={g.link} className="inline-flex min-h-10 items-center gap-1 text-[14px] font-semibold">
          {g.link_label} <ArrowRight size={15} aria-hidden />
        </Link>
      </div>
      <p className="m-0 px-4 pt-2 text-[14px] text-muted sm:px-5">{g.why}</p>
      {g.items.length === 0 ? (
        <p className="m-0 px-4 py-3 text-[14px] sm:px-5">Nothing waiting.</p>
      ) : (
        <ul className="m-0 list-none divide-y divide-grey-300/60 p-0">
          {g.items.map((i) => <Row key={i.id} i={i} />)}
        </ul>
      )}
      {more > 0 && <p className="m-0 border-t border-grey-300/70 px-4 py-2.5 text-[13.5px] text-muted sm:px-5">{n(more)} more not listed here. <Link to={g.link}>{g.link_label}</Link></p>}
    </Card>
  );
}

/** One item: what it is (the link), why it needs you, and how long it has waited or when it is due. */
export function Row({ i, compact = false }: { i: InboxItem; compact?: boolean }) {
  return (
    <li className={clsx("flex flex-col gap-0.5 px-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4 sm:px-5", compact ? "py-2.5" : "py-3")}>
      <div className="min-w-0">
        <Link to={i.link} className="break-words text-[15px] font-medium">{i.title}</Link>
        <p className="m-0 text-[14px] text-muted">{i.reason}</p>
      </div>
      <span className={clsx("inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-[13.5px] sm:pt-0.5", i.overdue ? "font-semibold text-danger" : "text-muted")}>
        {i.overdue && <AlertTriangle size={14} aria-hidden />}
        {i.overdue && <span className="sr-only">Overdue: </span>}
        {i.age_label}
      </span>
    </li>
  );
}
