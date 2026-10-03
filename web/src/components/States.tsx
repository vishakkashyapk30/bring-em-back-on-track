import { AlertTriangle, FlaskConical, Inbox, Lock } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "./Card";

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-4 rounded bg-grey-300" style={{ width: `${90 - i * 7}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <Card variant="grey" className="flex flex-col items-center gap-2 text-center">
      <Inbox aria-hidden /> <p className="m-0 font-medium">{title}</p>
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

export function QueryState({ q, children, empty }: { q: { isLoading: boolean; isError: boolean; error: unknown; data?: unknown }; children: ReactNode; empty?: boolean }) {
  if (q.isLoading) return <Skeleton lines={5} />;
  if (q.isError) {
    const e = q.error as { forbidden?: boolean; reason?: string; message?: string };
    return <ErrorState forbidden={e.forbidden} title={e.forbidden ? "Not available for your role" : undefined} detail={e.reason ?? e.message} />;
  }
  if (empty) return <EmptyState title="Nothing here yet" />;
  const fixture = (q.data as { meta?: { fixture?: boolean } } | undefined)?.meta?.fixture;
  return <>{fixture && <SampleDataBanner />}{children}</>;
}

/** Shown wherever an endpoint still serves sample data (its module isn't built yet), so nothing passes as real. */
export function SampleDataBanner() {
  return (
    <p role="note" className="mb-3 mt-0 inline-flex items-center gap-2 rounded-[var(--radius-sm)] bg-gold px-3 py-1 text-sm text-ink">
      <FlaskConical size={14} aria-hidden /> Sample data: this part is still being built (Layer 4), not the real dataset.
    </p>
  );
}
