import { useParams } from "react-router-dom";

import { useCallSummary, useTranscript } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";
import { TranscriptBubbles } from "@/components/TranscriptBubbles";

/** Post-call summary review: draft with turn citations; agent edits + approves.
 * TODO(WS-G): inline edit, approve -> POST, mismatch highlight. Plan: also embed as a panel in C360. */
export default function CallSummary() {
  const { contactId = "" } = useParams();
  const s = useCallSummary(contactId);
  const t = useTranscript(contactId);
  const d = s.data?.draft;
  const cited: number[] = d ? [...d.summary.turns, ...(d.promise?.turns ?? []), ...d.signals.turns] : [];
  return (
    <>
      <SectionTag as="h1" subtitle={<>Draft, needs approval <Badge kind={s.data?.provider === "offline" ? "sql" : "llm"}>{s.data?.provider}</Badge></>}>Post-call summary</SectionTag>
      <div className="grid gap-6 lg:grid-cols-2">
        <QueryState q={s}>
          {d && (
            <Card hard>
              <h3 className="mt-0">Summary</h3><p>{d.summary.text} <span className="text-sm text-muted">turns {d.summary.turns.join(", ")}</span></p>
              <h3>Promise</h3><p>{d.promise ? `$${d.promise.amount} by ${d.promise.date}` : "None found"} {s.data?.checks.promise_matches_record ? <Badge kind="ok">Matches record</Badge> : <Badge kind="danger">Differs from record</Badge>}</p>
              <h3>Signals</h3><p>Hardship: {d.signals.hardship_signal} · Delay reason: {d.signals.stated_delay_reason ?? "—"} · Dispute: {d.signals.dispute_signal ? "yes" : "no"}</p>
              <button type="button" className="rounded-[var(--radius-md)] bg-brand px-5 py-3 text-white">Approve summary</button>
            </Card>
          )}
        </QueryState>
        <QueryState q={t}><TranscriptBubbles turns={t.data?.turns ?? []} cited={cited} /></QueryState>
      </div>
    </>
  );
}
