import { Badge } from "./Badge";

/** "4 source IDs → 1 golden ID · confidence 0.97" + 9-source lineage strip (brief takeaway 1). */
export function IdentityLineage({ data }: { data: { golden_id: string; match_confidence: number; match_method: string; sources: { system: string; ref: string }[]; lineage: string[] } }) {
  return (
    <div className="space-y-3">
      <p className="m-0">{data.sources.length} source IDs → 1 golden ID · match confidence <b className="tabular">{data.match_confidence.toFixed(2)}</b> <span className="text-muted">({data.match_method})</span></p>
      <div className="flex flex-wrap gap-2 font-mono text-sm">{data.sources.map((s) => <span key={s.ref} className="rounded bg-grey-100 px-2 py-0.5">{s.system}:{s.ref}</span>)}</div>
      <div className="flex flex-wrap gap-1"><span className="text-sm text-muted">Lineage:</span>{data.lineage.map((l) => <Badge key={l} kind="neutral">{l}</Badge>)}</div>
    </div>
  );
}
