import { useMutation } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { toast } from "sonner";

import { post } from "@/api/client";
import { useCallSummary, useTranscript } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { RecordingCard } from "@/components/RecordingCard";
import { QueryState } from "@/components/States";
import { TranscriptBubbles } from "@/components/TranscriptBubbles";

const label = (v?: string | null) => (v ? v.replace(/_/g, " ") : "none");

/** Post-call summary review: rule-based draft (validated on 500 labelled transcripts), promise checked against the
 * promise recorded on this contact, agent approves before anything is saved (audited). */
export default function CallSummary() {
  const { contactId = "" } = useParams();
  const s = useCallSummary(contactId);
  const t = useTranscript(contactId);
  const approve = useMutation({
    mutationFn: () => post<{ audit_id: number }>(`/calls/${contactId}/summary/approve`, { draft: s.data?.draft }),
    onSuccess: (r) => toast.success("Summary approved", { description: `Saved to the case and the audit log (#${r.audit_id}).` }),
    onError: () => toast.error("Couldn't save the summary"),
  });
  const d = s.data?.draft;
  return (
    <>
      <SectionTag as="h1" subtitle={<>A draft for you to check, written by rules rather than an AI model</>}>Post-call summary</SectionTag>
      <div className="grid gap-6 lg:grid-cols-2">
        <QueryState q={s}>
          {d && (
            <Card hard>
              <p className="mt-0 text-sm text-muted">Case {s.data?.case_id} · transcript {s.data?.transcript_id}</p>
              <h3 className="mt-0">Summary</h3><p>{d.summary.text}</p>
              <h3>Promise</h3>
              <p>{d.promise ? `$${Number(d.promise.amount).toLocaleString()} by ${d.promise.date}` : "No promise made"}{" "}
                {d.promise && (s.data?.checks.promise_matches_record ? <Badge kind="ok">matches the recorded promise</Badge> : <Badge kind="danger">differs from the recorded promise</Badge>)}</p>
              <h3>Signals</h3>
              <ul className="mt-0">
                <li>Hardship: {label(d.signals.hardship_signal)}{d.signals.hardship_reason ? ` (${label(d.signals.hardship_reason)})` : ""}</li>
                <li>Dispute: {d.signals.dispute_signal ? "yes" : "no"} · Complaint: {d.signals.complaint_cue ? "yes" : "no"} · Asked to stop contact: {d.signals.cease_request ? "yes" : "no"}</li>
              </ul>
              <h3>Next step</h3><p>{d.next_steps?.[0]?.text}</p>
              <button type="button" disabled={approve.isPending || approve.isSuccess} onClick={() => approve.mutate()}
                className="rounded-[var(--radius-md)] bg-brand px-5 py-3 text-white disabled:opacity-60">{approve.isSuccess ? "Approved" : "Approve summary"}</button>
            </Card>
          )}
        </QueryState>
        <div className="space-y-6">
          <RecordingCard contactId={contactId} />
          <QueryState q={t}><TranscriptBubbles turns={t.data?.turns ?? []} /></QueryState>
        </div>
      </div>
    </>
  );
}
