import { useState } from "react";

import { KIND_LABEL, customerCount, useApprovePlaybook, usePlaybooks, type Proposal } from "@/api/ops";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState, QueryState } from "@/components/States";

/** Team lead: playbook proposals from the radar, the weather map and the outage shield. Approving only creates a
 * batch for the usual 2% sample check; nothing is sent. */
export function Playbooks() {
  const q = usePlaybooks();
  const approve = useApprovePlaybook();
  const [open, setOpen] = useState<Proposal | null>(null);
  const items = (q.data?.items ?? []).filter((p) => p.status === "pending_approval");
  return (
    <QueryState q={q}>
      {items.length === 0 ? (
        <EmptyState title="No playbooks today" detail="The employer radar, weather map and outage shield found nothing that needs you." />
      ) : (
        <ul className="m-0 list-none space-y-4 p-0">
          {items.map((p) => (
            <li key={p.proposal_id}>
              <Card>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 max-w-2xl">
                    <p className="m-0 font-medium">{p.title}</p>
                    <p className="mb-0 mt-1 text-[14px] text-muted">{p.detail}</p>
                    <p className="mb-0 mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px]">
                      <span><b className="tabular">{customerCount(p).toLocaleString()}</b> {customerCount(p) === 1 ? "customer" : "customers"}</span>
                      <Badge kind="neutral">{KIND_LABEL[p.kind] ?? p.kind}</Badge>
                      {p.requires_policy_office_signoff && <Badge kind="hardship">Needs Policy Office sign-off</Badge>}
                    </p>
                  </div>
                  <Button variant="primary" aria-label={`Approve and create the batch: ${p.title}`} onClick={() => setOpen(p)}>Approve and create the batch</Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!open} title="Create this batch?" confirmLabel="Approve and create the batch" busy={approve.isPending}
        onClose={() => setOpen(null)} onConfirm={() => open && approve.mutate(open.proposal_id, { onSettled: () => setOpen(null) })}>
        <p className="mt-0">{open?.title}</p>
        <p className="mb-0">This creates a batch for {open ? customerCount(open).toLocaleString() : 0} customers. <b className="text-ink">Nothing is sent until the 2% sample is checked</b>
          {open?.requires_policy_office_signoff ? ", and the Policy Office has signed off." : "."} The approval goes in the audit log.</p>
      </ConfirmDialog>
    </QueryState>
  );
}
