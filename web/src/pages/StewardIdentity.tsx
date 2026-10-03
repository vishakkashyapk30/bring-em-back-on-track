import { useGet } from "@/api/hooks";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

/** Grey-band identity pairs, masked side by side. A wrong merge = calling the wrong person (D4).
 * TODO(WS-G): verdict buttons -> POST /steward/identity/{pair_id}. */
export default function StewardIdentity() {
  const q = useGet("idq", "/steward/identity/queue");
  return (
    <>
      <SectionTag as="h1" subtitle="Link only when you're sure. Precision comes first.">Identity review</SectionTag>
      <QueryState q={q}>
        {q.data?.items.map((p: Record<string, any>) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
          <Card key={p.pair_id} className="mb-4">
            <p className="mt-0 font-mono text-sm">{p.pair_id} · p = {p.match_probability}</p>
            <div className="grid gap-4 md:grid-cols-2">{[p.left, p.right].map((r: Record<string, string>, i: number) => <Card key={i} variant="grey"><pre className="m-0 font-mono text-sm">{JSON.stringify(r, null, 2)}</pre></Card>)}</div>
            <div className="mt-3 flex gap-2">{["Link", "No link", "Unsure"].map((v) => <button key={v} type="button" className="rounded-[var(--radius-md)] border border-ink bg-white px-4 py-2">{v}</button>)}</div>
          </Card>
        ))}
      </QueryState>
    </>
  );
}
