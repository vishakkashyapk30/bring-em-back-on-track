import { useMutation, useQueryClient } from "@tanstack/react-query";

import { post } from "@/api/client";
import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

type Side = { system: string; ref: string; name?: string; dob_year?: number; fsa?: string };
type Pair = { pair_id: string; match_probability: number; reason: string; left: Side; right: Side };

const same = (a: unknown, b: unknown) => a != null && a === b;

/** Grey-band identity candidates from the real matcher, masked side by side. A wrong merge means contacting the
 * wrong person, so the steward decides; verdicts are audited. */
export default function StewardIdentity() {
  const q = useGet("idq", "/steward/identity/queue");
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: ({ id, verdict }: { id: string; verdict: string }) => post(`/steward/identity/${id}`, { verdict }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["audit"] }),
  });
  const items: Pair[] = q.data?.items ?? [];
  return (
    <>
      <SectionTag as="h1" subtitle={`${(q.data?.total ?? 0).toLocaleString()} candidate links in the review band. Link only when you're sure: precision comes first.`}>Identity review</SectionTag>
      <QueryState q={q} empty={items.length === 0}>
        {items.map((p) => {
          const rows: [string, keyof Side][] = [["Name", "name"], ["Birth year", "dob_year"], ["Postal area", "fsa"]];
          const done = decide.isSuccess && decide.variables?.id === p.pair_id;
          return (
            <Card key={p.pair_id} className="mb-4">
              <p className="mt-0 text-sm"><span className="font-mono">{p.pair_id}</span> · score {p.match_probability.toFixed(2)} · {p.reason}</p>
              <table className="w-full text-sm">
                <thead><tr><th className="text-left font-medium text-muted"> </th><th className="text-left font-medium">{p.left.system}: <span className="font-mono">{p.left.ref}</span></th><th className="text-left font-medium">candidate <span className="font-mono">{p.right.ref}</span></th><th /></tr></thead>
                <tbody>{rows.map(([label, k]) => (
                  <tr key={k} className="border-t border-grey-300">
                    <td className="py-1 text-muted">{label}</td><td>{String(p.left[k] ?? "missing")}</td><td>{String(p.right[k] ?? "missing")}</td>
                    <td>{same(p.left[k], p.right[k]) ? <Badge kind="ok">agrees</Badge> : <Badge kind="neutral">differs</Badge>}</td>
                  </tr>))}
                </tbody>
              </table>
              <div className="mt-3 flex items-center gap-2">
                {[["link", "Link"], ["no_link", "No link"], ["unsure", "Unsure"]].map(([v, l]) => (
                  <button key={v} type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: p.pair_id, verdict: v })}
                    className={`rounded-[var(--radius-md)] border border-ink px-4 py-2 ${v === "link" ? "bg-brand text-white" : "bg-white"}`}>{l}</button>
                ))}
                <span aria-live="polite" className="text-sm text-muted">{done ? `Saved: ${decide.variables?.verdict.replace("_", " ")} (audited)` : ""}</span>
              </div>
            </Card>
          );
        })}
      </QueryState>
    </>
  );
}
