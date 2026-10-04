import { useState } from "react";

import { useGet } from "@/api/hooks";
import { BubbleMap, type MapItem } from "@/components/BubbleMap";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { SqlBlock } from "@/components/SqlBlock";
import { QueryState } from "@/components/States";
import { RadarPanel } from "@/components/RadarPanel";
import { PageTabs, Segmented } from "@/components/Tabs";

const METRICS = [["broken_ptp_rate", "Broken-promise rate"], ["hardship_rate", "Hardship rate"]] as const;

/** S2 collections weather map on real data (one metric per postal area, small areas suppressed), and the weekly
 * employer radar on its own tab so neither needs a long scroll. */
export default function MapPage() {
  return (
    <>
      <SectionTag as="h1" subtitle="Where promises break and where hardship is concentrated, by postal area and by employer. Groups with fewer than 10 customers are hidden.">Map and radar</SectionTag>
      <PageTabs label="Map sections" tabs={[{ id: "map", label: "Weather map" }, { id: "radar", label: "Employer radar" }]}>
        {(tab) => (tab === "map" ? <WeatherMap /> : (
          <section aria-label="Employer radar">
            <RadarPanel />
          </section>
        ))}
      </PageTabs>
    </>
  );
}

function WeatherMap() {
  const [metric, setMetric] = useState<string>("broken_ptp_rate");
  const q = useGet("map-" + metric, `/map?metric=${metric}`);
  const items: MapItem[] = q.data?.items ?? [];
  const top = [...items].sort((a, b) => b.value - a.value).slice(0, 15);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Segmented label="Metric" value={metric} onChange={setMetric} options={METRICS.map(([v, t]) => [v, t] as [string, string])} />
        {q.data && <p className="m-0 text-[13.5px] text-muted">{items.length} areas shown · {q.data?.suppressed ?? 0} hidden (fewer than {q.data?.min_group ?? 10} customers)</p>}
      </div>
      <QueryState q={q}>
        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,1fr)_440px]">
          <BubbleMap items={items} label={q.data?.label ?? "Value"} />
          <section aria-labelledby="top-h">
            <SectionTag as="h2" id="top-h">Highest 15 areas</SectionTag>
            <DataTable maxHeight="482px" columns={["FSA", "City", "Prov.", "Customers", "Rate"]}
              rows={top.map((r) => [r.fsa, r.city, r.province, r.customers, `${(r.value * 100).toFixed(1)}%`])} />
          </section>
        </div>
        {q.data?.sql && (
          <details className="mt-6">
            <summary className="cursor-pointer text-[14px] font-medium text-brand">Show the query behind this map</summary>
            <div className="mt-3"><SqlBlock sql={q.data.sql} source="semantic" /></div>
          </details>
        )}
      </QueryState>
    </>
  );
}
