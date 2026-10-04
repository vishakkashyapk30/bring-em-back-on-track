import { useState } from "react";

import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { StatTiles } from "@/components/StatTiles";
import { QueryState } from "@/components/States";
import { Button } from "@/components/Button";
import { PageTabs } from "@/components/Tabs";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/** Layer 3: the feature catalog (features/registry.yaml), the parity check between the training and live stores,
 * and a lookup of one customer's live feature vector. */
export default function Features() {
  const q = useGet("catalog", "/features/catalog");
  const parity = useGet("parity", "/governance/features/parity");
  const [gid, setGid] = useState("G-KIW6380");
  const [lookup, setLookup] = useState("G-KIW6380");
  const vec = useGet("vec-" + lookup, `/features/online/${lookup}`);
  const f: Json[] = q.data?.features ?? [];
  const by = (b: string) => f.filter((x) => x.built_by === b).length;
  const p: Json = parity.data ?? {};
  return (
    <>
      <SectionTag as="h1" subtitle="Each feature is defined once and used the same way for training and for live scoring.">Feature store</SectionTag>
      <StatTiles items={[
        { label: "Features", value: String(f.length), note: `${by("sql")} from structured data · ${by("ai")} from text · ${by("voice")} from voice` },
        { label: "Training ↔ live parity", value: p.sampled ? `${p.mismatched_rows} mismatches` : "n/a", note: p.sampled ? `${p.sampled} rows × ${p.columns_checked} columns recomputed` : "", status: p.ok ? "ok" : undefined },
        { label: "Text-feature accuracy", value: "99.6%", note: "hardship, on 500 labelled transcripts" },
        { label: "Text and voice features", value: String(by("ai") + by("voice")), note: "read by rules by default; a language model is optional" },
      ]} />
      <PageTabs label="Feature store sections" tabs={[{ id: "catalog", label: "Catalog", count: f.length || undefined }, { id: "vector", label: "Live feature vector" }]}>
        {(tab) => tab === "catalog" ? (
          <QueryState q={q}>
            <DataTable searchable="Search features" filters={[{ id: "sql", label: "SQL", test: (r) => r[5] === "sql" }, { id: "ai", label: "Text", test: (r) => r[5] === "ai" }, { id: "voice", label: "Voice", test: (r) => r[5] === "voice" }]} columns={["Feature", "Entity", "Type", "Source", "Available from", "Built by"]}
              rows={f.map((x) => [x.name, x.entity, x.type, (x.source as string[]).join(", "), x.available_ts, x.built_by])}
              render={(v, col) => (col === "Built by" ? <Badge kind={v === "ai" || v === "voice" ? "model-estimate" : "sql"}>{v === "ai" ? "text" : String(v)}</Badge> : col === "Feature" ? <code>{String(v)}</code> : String(v ?? ""))} />
          </QueryState>
        ) : (
          <section aria-label="Live feature vector">
            <p className="mb-4 mt-0 text-[14px] text-muted">The features one customer would be scored with right now, read from the live store.</p>
            <form className="mb-4 flex max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); setLookup(gid.trim()); }}>
              <label htmlFor="gid" className="sr-only">Golden ID</label>
              <input id="gid" value={gid} onChange={(e) => setGid(e.target.value)} className="h-10 min-w-0 flex-1 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 font-mono text-[14px] outline-none focus:border-brand/50 focus:shadow-[var(--shadow-focus)]" />
              <Button type="submit" variant="primary">Look up</Button>
            </form>
            <QueryState q={vec}>
              <Card>
                <p className="mt-0 text-[13.5px] text-muted">{vec.data?.golden_id} · as of {vec.data?.as_of}</p>
                <dl className="m-0 grid gap-x-8 font-mono text-[13px] md:grid-cols-2">
                  {Object.entries(vec.data?.vector ?? {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-4 border-b border-grey-300/60 py-1.5"><dt>{k}</dt><dd className="m-0 tabular">{v == null ? "missing" : String(v)}</dd></div>
                  ))}
                </dl>
              </Card>
            </QueryState>
          </section>
        )}
      </PageTabs>
    </>
  );
}
