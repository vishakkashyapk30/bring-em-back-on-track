import { AlertTriangle, FlaskConical, Inbox, Lock } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "./Card";

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton h-3.5 rounded-full" style={{ width: `${92 - ((i * 13) % 35)}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <Card variant="grey" className="flex flex-col items-center gap-1.5 py-8 text-center">
      <Inbox size={20} aria-hidden className="text-muted" /> <p className="m-0 font-medium">{title}</p>
      {detail && <p className="m-0 text-muted">{detail}</p>}
      {action}
    </Card>
  );
}

export function ErrorState({ title = "Something went wrong", detail, forbidden }: { title?: string; detail?: string; forbidden?: boolean }) {
  return (
    <Card variant="grey" role="alert" className="flex items-start gap-3">
      {forbidden ? <Lock aria-hidden /> : <AlertTriangle aria-hidden className="text-danger" />}
      <div><p className="m-0 font-medium">{title}</p>{detail && <p className="m-0 text-muted">{detail}</p>}</div>
    </Card>
  );
}

/** Ask/assist refusal: names the blocked part and why. */
export function RefusalCard({ reason, alternative }: { reason: string; alternative?: string }) {
  return (
    <Card variant="grey" role="status" className="border-l-4 border-l-brand">
      <p className="m-0 font-medium">I can't answer that</p>
      <p className="m-0 text-muted">{reason}</p>
      {alternative && <p className="mt-2 mb-0">Try: <em>{alternative}</em></p>}
    </Card>
  );
}

export function QueryState({ q, children, empty, banner = true }: { q: { isLoading: boolean; isError: boolean; error: unknown; data?: unknown }; children: ReactNode; empty?: boolean; banner?: boolean }) {
  if (q.isLoading) return <Skeleton lines={5} />;
  if (q.isError) {
    const e = q.error as { forbidden?: boolean; reason?: string; message?: string };
    return <ErrorState forbidden={e.forbidden} title={e.forbidden ? "Not available for your role" : undefined} detail={e.reason ?? e.message} />;
  }
  if (empty) return <EmptyState title="Nothing here yet." />;
  const fixture = (q.data as { meta?: { fixture?: boolean } } | undefined)?.meta?.fixture;
  return <div className="fade-in">{fixture && banner && <SampleDataBanner />}{children}</div>;
}

/** Shown wherever an endpoint still serves sample data (its module isn't built yet), so nothing passes as real. */
export function SampleDataBanner() {
  return (
    <p role="note" className="mb-3 mt-0 inline-flex items-center gap-2 rounded-[var(--radius-sm)] bg-gold px-3 py-1 text-sm text-ink">
      <FlaskConical size={14} aria-hidden /> This part still shows sample data. It isn't the real dataset yet.
    </p>
  );
}

/** Small inline marker for a panel that still shows sample data (Layer 4), for places where a banner is too loud. */
export function SampleBadge() {
  return (
    <span title="This part still shows sample data, not the real dataset."
      className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-amber">
      <FlaskConical size={11} aria-hidden /> Sample data
    </span>
  );
}

/** Source and caveat lines under a table or chart: one style everywhere. */
export function Footnote({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`mb-0 mt-3 max-w-4xl text-[13px] leading-relaxed text-muted ${className}`}>{children}</p>;
}
