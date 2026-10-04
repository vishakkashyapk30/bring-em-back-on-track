import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { toast } from "sonner";

import { post } from "@/api/client";
import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
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
    onSuccess: (_r, v) => { qc.invalidateQueries({ queryKey: ["audit"] }); toast.success(`Verdict saved: ${v.verdict.replace("_", " ")}`, { description: `Pair ${v.id}, applied on the next identity run.` }); },
    onError: () => toast.error("Couldn't save the verdict"),
  });
  const all: Pair[] = q.data?.items ?? [];
  const [shown, setShown] = useState(6);
  const items = all.slice(0, shown);
  return (
    <>
      <SectionTag as="h1" subtitle={`${(q.data?.total ?? 0).toLocaleString()} possible matches need a human look. Only link two records when you're sure, because a wrong link is worse than a missing one.`}>Identity review</SectionTag>
      <QueryState q={q} empty={items.length === 0}>
        <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-2">
        {items.map((p) => {
          const rows: [string, keyof Side][] = [["Name", "name"], ["Birth year", "dob_year"], ["Postal area", "fsa"]];
          const done = decide.isSuccess && decide.variables?.id === p.pair_id;
          return (
            <li key={p.pair_id}>
            <Card className="h-full">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="font-mono text-[13.5px] font-semibold">{p.pair_id}</span>
                <span className="text-[13px] text-muted">Match score <b className="tabular font-semibold text-ink">{p.match_probability.toFixed(2)}</b> · {p.reason}</span>
              </div>
              <table className="w-full table-fixed text-[14px]">
                <thead><tr className="text-[13px]">
                  <th scope="col" className="w-[24%] pb-1.5 text-left font-medium text-muted"><span className="sr-only">Field</span></th>
                  <th scope="col" className="pb-1.5 text-left font-medium text-muted">{p.left.system} <span className="font-mono text-ink">{p.left.ref}</span></th>
                  <th scope="col" className="pb-1.5 text-left font-medium text-muted">Candidate <span className="font-mono text-ink">{p.right.ref}</span></th>
                  <th scope="col" className="w-[18%] pb-1.5"><span className="sr-only">Result</span></th>
                </tr></thead>
                <tbody>{rows.map(([label, k]) => (
                  <tr key={k} className="border-t border-grey-300/60">
                    <td className="py-1.5 text-muted">{label}</td><td className="py-1.5 font-mono">{String(p.left[k] ?? "missing")}</td><td className="py-1.5 font-mono">{String(p.right[k] ?? "missing")}</td>
                    <td className="py-1.5 text-right">{same(p.left[k], p.right[k]) ? <Badge kind="ok">Agrees</Badge> : <Badge kind="neutral">Differs</Badge>}</td>
                  </tr>))}
                </tbody>
              </table>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {([["link", "Link", "primary"], ["no_link", "No link", "secondary"], ["unsure", "Unsure", "secondary"]] as const).map(([v, l, variant]) => (
                  <Button key={v} size="sm" variant={variant} disabled={decide.isPending} onClick={() => decide.mutate({ id: p.pair_id, verdict: v })}>{l}</Button>
                ))}
                <span aria-live="polite" className="text-[13px] text-muted">{done ? `Saved: ${decide.variables?.verdict.replace("_", " ")} (audited)` : ""}</span>
              </div>
            </Card>
            </li>
          );
        })}
        </ul>
      </QueryState>
      {all.length > shown && (
        <div className="mt-4 flex items-center justify-between rounded-[var(--radius-md)] border border-grey-300/70 bg-white px-4 py-2 text-[13.5px] text-muted">
          <span aria-live="polite">Showing {shown} of {all.length.toLocaleString()} loaded pairs</span>
          <Button variant="ghost" size="sm" onClick={() => setShown(shown + 6)}>Show more</Button>
        </div>
      )}
    </>
  );
}
