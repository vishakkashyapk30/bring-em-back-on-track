import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

import { ListView } from "./hardship/Lists";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const p1 = (v: unknown) => (v == null ? "n/a" : `${v}%`);

/** Team lead: strategy scorecard (S4, real data), agent roster (real), batch approvals (Layer 4). */
export default function Team() {
  const sc = useGet("scorecard", "/scorecard");
  const ag = useGet("agents", "/team/agents");
  return (
    <div className="space-y-10">
      <section>
        <SectionTag as="h1" subtitle="Cases opened at least 30 days before the snapshot. Compare strategies within a stage only.">Strategy scorecard</SectionTag>
        <QueryState q={sc}>
          <DataTable columns={["Stage", "Strategy", "Randomised cases", "30-day cure (randomised)", "All cases", "30-day cure (all)", "Cost per cure", "Complaints / 1,000"]}
            rows={(sc.data?.items ?? []).map((r: Json) => [r.stage, r.strategy_code, r.randomised_cases, p1(r.cure_rate_30d_randomised), r.all_cases, p1(r.cure_rate_30d_all), r.cost_per_cure_cad == null ? "n/a" : `$${r.cost_per_cure_cad}`, r.complaints_per_1000_cases])}
            render={(v, col) => (col === "30-day cure (randomised)" ? <span>{String(v)} <Badge kind="causal">causal</Badge></span> : col === "30-day cure (all)" ? <span>{String(v)} <Badge kind="observed">observed</Badge></span> : String(v ?? ""))} />
          <Card variant="grey" className="mt-3 text-sm">{sc.data?.note}</Card>
        </QueryState>
      </section>
      <section>
        <SectionTag>Agents</SectionTag>
        <QueryState q={ag}>
          <DataTable columns={["Agent", "Name", "Site", "Team", "Hardship skill", "Vulnerable-certified", "Case load", "PTP kept (90d)", "Cure (90d)"]}
            rows={(ag.data?.items ?? []).map((a: Json) => [a.agent_id, a.name, a.site, a.team_id, a.skill_hardship, a.vulnerable_customer_certified ? "yes" : "no", `${a.current_case_load} / ${a.max_concurrent_cases}`, a.ptp_kept_rate_90d, a.cure_rate_90d])} />
        </QueryState>
      </section>
      <section><SectionTag subtitle="Routine digital reminders, approved by batch after a 2% sample check.">Batch approvals</SectionTag><ListView k="batches" path="/batches" /></section>
    </div>
  );
}
