import { useState } from "react";

import { pts, rowChange, topNullChanges, useApproveDrift, useDrift, type DriftFix } from "@/api/ops";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { SectionTag } from "@/components/SectionTag";
import { EmptyState, QueryState } from "@/components/States";

const STATUS: Record<string, string> = { pending_engineer_approval: "Waiting for your approval", approved: "Approved, waiting for an engineer" };

function Side({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="min-w-0"><h3 className="m-0 font-[family-name:var(--font-sans)] text-[13px] font-semibold text-muted">{title}</h3><div className="mt-1 space-y-1 text-[14.5px]">{children}</div></div>;
}

/** Data steward: schema changes found in a load, with the drafted fix. The app never applies the fix. */
export default function StewardDrift() {
  const q = useDrift();
  const approve = useApproveDrift();
  const [open, setOpen] = useState<DriftFix | null>(null);
  const fixes = q.data?.fixes ?? [];
  return (
    <>
      <SectionTag as="h1" subtitle="Changes found in the latest loads, with a drafted fix. An engineer applies an approved fix; this app never does.">Schema changes</SectionTag>
      <QueryState q={q}>
        {fixes.length === 0 ? <EmptyState title="No schema changes found" detail="Nothing needs an engineer." /> : (
          <ul className="m-0 list-none space-y-5 p-0">
            {fixes.map((f) => {
              const c = f.change;
              const nulls = topNullChanges(c.null_rate_changes);
              const pending = f.status === "pending_engineer_approval";
              return (
                <li key={f.fix_id}>
                  <Card>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <h2 className="m-0 font-mono text-[1.0625rem] font-semibold">{f.table}</h2>
                        <p className="m-0 text-[14px] text-muted">{c.event_description ?? f.description}{c.event_id ? ` (${c.event_id})` : ""}</p>
                      </div>
                      <Badge kind={pending ? "hardship" : "ok"}>{STATUS[f.status] ?? f.status}</Badge>
                    </div>
                    <div className="mt-4 grid gap-5 sm:grid-cols-2">
                      <Side title="Before">
                        {c.renames.map((r) => <p key={r.from} className="m-0">Column <code>{r.from}</code></p>)}
                        {c.removed_columns.map((r) => <p key={r} className="m-0">Column <code>{r}</code></p>)}
                        {c.renames.length + c.removed_columns.length === 0 && <p className="m-0 text-muted">No columns removed or renamed</p>}
                      </Side>
                      <Side title="After">
                        {c.renames.map((r) => <p key={r.to} className="m-0">Renamed to <code>{r.to}</code></p>)}
                        {c.added_columns.filter((a) => !c.renames.some((r) => r.to === a)).map((a) => <p key={a} className="m-0">New column <code>{a}</code></p>)}
                        {c.removed_columns.map((r) => <p key={r} className="m-0">Missing: <code>{r}</code></p>)}
                        {(c.type_changes as { column?: string; from?: string; to?: string }[]).map((t, i) => <p key={i} className="m-0">Type of <code>{t.column}</code> changed from {t.from} to {t.to}</p>)}
                        {typeof c.row_count_change === "number" && <p className="m-0">{rowChange(c.row_count_change)}</p>}
                      </Side>
                    </div>
                    {nulls.length > 0 && (
                      <p className="mb-0 mt-4 text-[14px]"><span className="text-muted">Biggest change in empty values: </span>
                        {nulls.map(([k, v], i) => <span key={k}>{i > 0 && ", "}<code>{k}</code> {pts(v)}</span>)}</p>
                    )}
                    <h3 className="mb-1.5 mt-5 font-[family-name:var(--font-sans)] text-[13px] font-semibold text-muted">Drafted fix</h3>
                    <pre className="m-0 overflow-x-auto rounded-[var(--radius-md)] bg-navy p-4 font-mono text-[13px] leading-relaxed text-white" tabIndex={0} aria-label={`Drafted fix for ${f.table}`}><code>{f.diff}</code></pre>
                    <div className="mt-4 flex justify-end">
                      <Button variant="primary" disabled={!pending} onClick={() => setOpen(f)}>{pending ? "Approve fix" : "Fix approved"}</Button>
                    </div>
                  </Card>
                </li>
              );
            })}
          </ul>
        )}
      </QueryState>
      <ConfirmDialog open={!!open} title="Approve this fix?" confirmLabel="Approve fix" busy={approve.isPending}
        onClose={() => setOpen(null)} onConfirm={() => open && approve.mutate(open.fix_id, { onSettled: () => setOpen(null) })}>
        <p className="mt-0">{open?.description}</p>
        <p className="mb-0">An engineer applies the fix, not this app. Your approval goes in the audit log.</p>
      </ConfirmDialog>
    </>
  );
}
