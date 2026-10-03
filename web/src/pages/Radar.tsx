import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { BubbleMap } from "@/components/BubbleMap";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

/** S1 employer radar + S2 weather map. A radar, not a layoff detector. TODO(WS-G): detail drawer + playbook batch. */
export default function Radar() {
  const radar = useGet("radar", "/radar/employers");
  const map = useGet("map", "/map");
  return (
    <>
      <SectionTag as="h1" subtitle="Payroll gaps and new EI deposits by employer (10+ customers only).">Employer radar</SectionTag>
      <QueryState q={radar}>
        <div className="mb-10 grid gap-4 md:grid-cols-2">
          {radar.data?.items.map((e: Record<string, any>) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
            <Card key={e.employer_key} hard>
              <h3 className="mt-0">{e.employer} <Badge kind={e.pattern === "layoff-like" ? "danger" : "bucket"}>{e.pattern}</Badge></h3>
              <p className="m-0 tabular">{e.payroll_gap} of {e.customers} with a payroll gap · {e.new_ei} new EI · pay {Math.round(e.avg_pay_change_pct * 100)}%</p>
              <p className="m-0 text-muted tabular">{e.open_cases} open cases · ${e.exposure_cad.toLocaleString()} exposure</p>
            </Card>
          ))}
        </div>
      </QueryState>
      <SectionTag as="h2" subtitle="Broken-promise rate by postal area. Areas under 10 customers are hidden.">Weather map</SectionTag>
      <QueryState q={map}><BubbleMap items={map.data?.items ?? []} /></QueryState>
    </>
  );
}
