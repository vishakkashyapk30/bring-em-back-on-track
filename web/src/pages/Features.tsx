import { useState } from "react";

import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { StatTiles } from "@/components/StatTiles";
import { QueryState } from "@/components/States";

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
      <SectionTag as="h1" subtitle="One definition per feature, used for both training and live scoring.">Feature store</SectionTag>
      <StatTiles items={[
        { label: "Features", value: String(f.length), note: `${by("sql")} from structured data · ${by("rule")} from text` },
        { label: "Training ↔ live parity", value: p.sampled ? `${p.mismatched_rows} mismatches` : "n/a", note: p.sampled ? `${p.sampled} rows × ${p.columns_checked} columns recomputed` : "", status: p.ok ? "ok" : undefined },
        { label: "Text-feature accuracy", value: "99.6%", note: "hardship, on 500 labelled transcripts" },
        { label: "LLM-built features", value: String(by("llm")), note: "offline rules by default; an LLM is optional" },
      ]} />
      <QueryState q={q}>
        <DataTable searchable="Search features" filters={[{ id: "rule", label: "Rule-built", test: (r) => r[5] === "rule" }, { id: "sql", label: "SQL", test: (r) => r[5] === "sql" }, { id: "llm", label: "LLM", test: (r) => r[5] === "llm" }]} columns={["Feature", "Entity", "Type", "Source", "Available from", "Built by"]}
          rows={f.map((x) => [x.name, x.entity, x.type, (x.source as string[]).join(", "), x.available_ts, x.built_by])}
          render={(v, col) => (col === "Built by" ? <Badge kind={v === "llm" ? "llm" : v === "rule" ? "model-estimate" : "sql"}>{String(v)}</Badge> : col === "Feature" ? <code>{String(v)}</code> : String(v ?? ""))} />
      </QueryState>
      <h2 className="mt-10 text-xl">Live feature vector</h2>
      <form className="mb-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); setLookup(gid.trim()); }}>
        <label htmlFor="gid" className="sr-only">Golden ID</label>
        <input id="gid" value={gid} onChange={(e) => setGid(e.target.value)} className="rounded-[var(--radius-md)] border border-grey-300 bg-white transition-colors hover:bg-grey-100 px-3 py-2 font-mono" />
        <button className="rounded-[var(--radius-md)] bg-ink px-4 text-white">Look up</button>
      </form>
      <QueryState q={vec}>
        <Card>
          <p className="mt-0 text-sm text-muted">{vec.data?.golden_id} · as of {vec.data?.as_of}</p>
          <dl className="m-0 grid gap-x-6 gap-y-1 font-mono text-sm md:grid-cols-2">
            {Object.entries(vec.data?.vector ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-grey-300 py-1"><dt>{k}</dt><dd className="m-0">{v == null ? "missing" : String(v)}</dd></div>
            ))}
          </dl>
        </Card>
      </QueryState>
    </>
  );
}
