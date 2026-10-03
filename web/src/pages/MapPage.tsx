import { useState } from "react";

import { useGet } from "@/api/hooks";
import { BubbleMap, type MapItem } from "@/components/BubbleMap";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { SqlBlock } from "@/components/SqlBlock";
import { QueryState } from "@/components/States";

const METRICS = [["broken_ptp_rate", "Broken-promise rate"], ["hardship_rate", "Hardship rate"]] as const;

/** S2 collections weather map on real data: one metric per postal area (FSA centroid), small areas suppressed. */
export default function MapPage() {
  const [metric, setMetric] = useState<string>("broken_ptp_rate");
  const q = useGet("map-" + metric, `/map?metric=${metric}`);
  const items: MapItem[] = q.data?.items ?? [];
  const top = [...items].sort((a, b) => b.value - a.value).slice(0, 15);
  return (
    <>
      <SectionTag as="h1" subtitle="Where promises break and hardship clusters, by postal area. Areas under 10 customers are hidden.">Weather map</SectionTag>
      <div className="mb-4 flex gap-2" role="group" aria-label="Metric">
        {METRICS.map(([id, label]) => (
          <button key={id} type="button" aria-pressed={metric === id} onClick={() => setMetric(id)}
            className={`rounded-[var(--radius-md)] border border-ink px-3 py-1.5 ${metric === id ? "bg-brand text-white" : "bg-white"}`}>{label}</button>
        ))}
      </div>
      <QueryState q={q}>
        <p className="mt-0 text-sm text-muted">{items.length} areas shown · {q.data?.suppressed ?? 0} suppressed (fewer than {q.data?.min_group ?? 10} customers)</p>
        <BubbleMap items={items} label={q.data?.label ?? "Value"} />
        <h2 className="mt-8 text-xl">Highest 15 areas</h2>
        <DataTable columns={["FSA", "City", "Province", "Customers", q.data?.label ?? "Value"]}
          rows={top.map((r) => [r.fsa, r.city, r.province, r.customers, `${(r.value * 100).toFixed(1)}%`])} />
        {q.data?.sql && <div className="mt-6"><SqlBlock sql={q.data.sql} source="semantic" /></div>}
      </QueryState>
    </>
  );
}
