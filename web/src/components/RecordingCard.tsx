import { useMutation, useQuery } from "@tanstack/react-query";
import { AudioLines, Loader2 } from "lucide-react";

import { api, post } from "@/api/client";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";

type VoiceInfo = {
  available: boolean; audio_url?: string; stereo?: boolean; note?: string;
  measures?: { duration_sec: number; dead_air_sec: number; hold_music_sec: number; snr_db: number; packet_loss_pct: number; clipping_pct: number };
};
type VoiceDraft = { stereo: boolean; summary: string; note?: string | null; turns: { speaker: string; text: string }[]; fields: Record<string, unknown> };

const sec = (n: number) => `${Math.round(n)} s`;
const label = (v: unknown) => (v ? String(v).replace(/_/g, " ") : "none");

/** The call's recording (optional voice pack): play it, see the line's call-level measures, and draft the notes from the audio.
 * Only call-level measures are shown, never anything about the speaker's voice. */
export function RecordingCard({ contactId }: { contactId: string }) {
  const info = useQuery({ queryKey: ["voice", contactId], queryFn: () => api<VoiceInfo>(`/voice/${contactId}`), retry: false });
  const draft = useMutation({ mutationFn: () => post<VoiceDraft>(`/voice/${contactId}/draft`) });
  if (info.isLoading || info.isError) return null;
  const v = info.data;
  if (!v?.available) return <Card><p className="m-0 text-sm text-muted">There is no recording for this call.</p></Card>;
  const m = v.measures!;
  const d = draft.data;
  return (
    <Card>
      <h3 className="mt-0 flex items-center gap-2"><AudioLines size={18} aria-hidden /> Recording</h3>
      <audio controls preload="none" src={v.audio_url} className="mb-3 w-full">Your browser can't play this recording.</audio>
      <dl className="m-0 mb-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
        {([["Length", sec(m.duration_sec)], ["Dead air", sec(m.dead_air_sec)], ["Hold music", sec(m.hold_music_sec)],
           ["Noise level", `${m.snr_db.toFixed(0)} dB signal-to-noise`], ["Packet loss", `${m.packet_loss_pct.toFixed(1)}%`], ["Channels", v.stereo ? "agent and customer apart" : "one mixed track"]] as [string, string][]).map(([k, val]) => (
          <div key={k}><dt className="text-muted">{k}</dt><dd className="m-0 font-medium tabular">{val}</dd></div>
        ))}
      </dl>
      <p className="mb-3 text-[13px] text-muted">{v.note}</p>
      <Button size="sm" variant="secondary" disabled={draft.isPending} onClick={() => draft.mutate()}>
        {draft.isPending ? <><Loader2 size={15} className="animate-spin" aria-hidden /> Listening…</> : "Draft the notes from the recording"}
      </Button>
      {draft.isError && <p className="mb-0 mt-3 text-sm text-danger" role="alert">Couldn't read the recording. The transcript on this page is still available.</p>}
      {d && (
        <div className="fade-in mt-4 border-t border-grey-300/70 pt-4">
          <Badge kind="sql">Speech to text, then the same rules as for transcripts</Badge>
          <p className="mb-1 mt-2">{d.summary}</p>
          <p className="m-0 text-sm text-muted">
            Hardship: {label(d.fields.hardship)} · {d.turns.length} turns heard{d.stereo ? "" : " · mixed track, so the customer's lines could not be separated"}.
          </p>
          <p className="mb-0 mt-2 text-[13px] text-muted">Nothing is saved. Compare it with the transcript and approve the summary above.</p>
        </div>
      )}
    </Card>
  );
}
