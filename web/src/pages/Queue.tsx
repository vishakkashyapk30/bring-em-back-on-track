import { Link } from "react-router-dom";

import { useQueue } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { FreshnessPill } from "@/components/FreshnessPill";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

/** Today's NBA queue (priority-sorted). TODO(WS-G): filters, batch-approve toolbar for leads. */
export default function Queue() {
  const q = useQueue();
  return (
    <>
      <SectionTag as="h1" subtitle={<FreshnessPill asOf={q.data?.meta?.as_of} hours={q.data?.meta?.freshness_hours} fixture={q.data?.meta?.fixture} />}>Today's queue</SectionTag>
      <QueryState q={q} empty={q.data?.items.length === 0}>
        <div className="overflow-x-auto rounded-[var(--radius-md)] border border-grey-300 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-grey-100"><tr>{["Customer", "Product", "DPD", "Next best action", "Break risk", "Flags", "Priority"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {q.data?.items.map((it) => (
                <tr key={it.case_id} className="border-t border-grey-300">
                  <td className="px-3 py-2"><Link to={`/customers/${it.golden_id}`} className="text-brand">{it.golden_id} {it.name}</Link></td>
                  <td className="px-3 py-2">{it.product}</td>
                  <td className="px-3 py-2 tabular">{it.dpd}</td>
                  <td className="px-3 py-2">{it.action.treatment.replace("_", " ")}{it.action.channel && ` · ${it.action.channel}`}{it.action.window && ` · ${it.action.window}`}</td>
                  <td className="px-3 py-2 tabular">{it.p_break.toFixed(2)} <span className="text-muted">({it.risk_band.replace("_", " ")})</span></td>
                  <td className="space-x-1 px-3 py-2">{it.hardship_flag !== "none" && <Badge kind="hardship">Hardship {it.hardship_flag}</Badge>}{it.vulnerable && <Badge kind="vulnerable">Vulnerable</Badge>}</td>
                  <td className="px-3 py-2 tabular">{it.priority.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryState>
    </>
  );
}
