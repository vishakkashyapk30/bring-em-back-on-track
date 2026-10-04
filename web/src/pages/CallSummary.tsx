import { useMutation } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { post } from "@/api/client";
import { useCallSummary, useTranscript } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
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
  const nav = useNavigate();
  const cited: number[] = [...(d?.summary?.turns ?? []), ...(d?.promise?.turns ?? [])];
  return (
    <>
      <button type="button" onClick={() => nav(-1)} className="mb-4 inline-flex items-center gap-1.5 bg-transparent text-[13.5px] font-medium text-muted transition-colors hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> Back
      </button>
      <SectionTag as="h1" subtitle="A draft for you to check, written by rules rather than an AI model.">Post-call summary</SectionTag>
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="space-y-6 lg:sticky lg:top-24">
          <QueryState q={s}>
            {d && (
              <Card hard>
                <p className="mb-4 mt-0 text-[13px] text-muted">Case <span className="font-mono">{s.data?.case_id}</span> · transcript {s.data?.transcript_id}</p>
                <dl className="m-0 space-y-4 text-[14.5px]">
                  <div><dt className="text-[13px] font-semibold text-muted">Summary</dt><dd className="m-0 mt-0.5">{d.summary.text}</dd></div>
                  <div><dt className="text-[13px] font-semibold text-muted">Promise</dt>
                    <dd className="m-0 mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="tabular">{d.promise ? `$${Number(d.promise.amount).toLocaleString()} by ${d.promise.date}` : "No promise made"}</span>
                      {d.promise && (s.data?.checks.promise_matches_record ? <Badge kind="ok">Matches the recorded promise</Badge> : <Badge kind="danger">Differs from the recorded promise</Badge>)}
                    </dd></div>
                  <div><dt className="text-[13px] font-semibold text-muted">Signals</dt>
                    <dd className="m-0 mt-0.5">Hardship: {label(d.signals.hardship_signal)}{d.signals.hardship_reason ? ` (${label(d.signals.hardship_reason)})` : ""}<br />
                      Dispute: {d.signals.dispute_signal ? "yes" : "no"} · Complaint: {d.signals.complaint_cue ? "yes" : "no"} · Asked to stop contact: {d.signals.cease_request ? "yes" : "no"}</dd></div>
                  <div><dt className="text-[13px] font-semibold text-muted">Next step</dt><dd className="m-0 mt-0.5">{d.next_steps?.[0]?.text}</dd></div>
                </dl>
                <Button variant="primary" className="mt-5" disabled={approve.isPending || approve.isSuccess} onClick={() => approve.mutate()}>{approve.isSuccess ? "Approved" : "Approve summary"}</Button>
              </Card>
            )}
          </QueryState>
          <RecordingCard contactId={contactId} />
        </div>
        <Card className="p-0">
          <div className="flex items-baseline justify-between gap-3 border-b border-grey-300/70 px-5 py-3">
            <h2 className="m-0 text-[1.0625rem]">Transcript</h2>
            {t.data && <span className="text-[13px] text-muted">{(t.data?.turns ?? []).length} turns · cited turns are outlined</span>}
          </div>
          <div className="max-h-[calc(100vh-260px)] min-h-[320px] overflow-y-auto p-5" tabIndex={0} aria-label="Call transcript">
            <QueryState q={t}><TranscriptBubbles turns={t.data?.turns ?? []} cited={cited} /></QueryState>
          </div>
        </Card>
      </div>
    </>
  );
}
