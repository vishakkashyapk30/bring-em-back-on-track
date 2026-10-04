import { PATTERN_LABEL, pct, useRadar, type RadarRow } from "@/api/ops";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { QueryState } from "@/components/States";

/** Weekly employer radar (S1): an honest summary first, then the employers closest to a pattern. */
export function RadarPanel() {
  const q = useRadar();
  const d = q.data;
  const rows = (d?.rows ?? []).slice(0, 10);
  return (
    <QueryState q={q}>
      <p className="mt-0 text-[15px]">{d?.summary}</p>
      <p className="mt-0 text-sm text-muted">
        {(d?.employers_shown ?? 0).toLocaleString()} employers shown · {(d?.employers_hidden_small ?? 0).toLocaleString()} hidden (fewer than {d?.min_group ?? 10} customers)
        {d?.week_start ? ` · week of ${d.week_start}` : ""}
      </p>
      {rows.length === 0 ? (
        <Card variant="grey" className="text-[14.5px]">No employer to show this week.</Card>
      ) : (
        <>
          {d?.clusters === 0 && <p className="mb-2 mt-0 text-sm text-muted">No employer stands out, so these are the 10 with the most late payrolls, for context only.</p>}
          <DataTable bare columns={["Employer", "Late payroll", "Customers", "New EI deposits", "Pattern", "Known incident"]}
            rows={rows.map((r: RadarRow) => [r.employer_key, pct(r.gap_rate, 1), r.n_customers, r.n_new_ei, r.pattern, r.explained_by_incident ?? r.known_incidents[0]?.event_id ?? "None"])}
            render={(v, col) => (col === "Pattern" ? (v === "none" ? PATTERN_LABEL.none : <Badge kind="risk">{PATTERN_LABEL[String(v)] ?? String(v)}</Badge>) : String(v ?? ""))} />
        </>
      )}
      <p className="mb-0 mt-3 text-sm font-medium">A radar, not a layoff detector.
        <span className="font-normal text-muted"> It counts late payroll and new EI deposits. No field says a person lost their job, so a person decides what it means.</span></p>
    </QueryState>
  );
}
