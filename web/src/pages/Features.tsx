import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { DataTable } from "@/components/DataTable";
import { SectionTag } from "@/components/SectionTag";
import { QueryState } from "@/components/States";

/** Feature catalog generated from features/registry.yaml (live endpoint). TODO(WS-G): online vector viewer. */
export default function Features() {
  const q = useGet("catalog", "/features/catalog");
  const f: Record<string, unknown>[] = q.data?.features ?? [];
  return (
    <>
      <SectionTag as="h1" subtitle={`${q.data?.count ?? "–"} features · ${q.data?.llm_count ?? "–"} built by LLM`}>Feature store</SectionTag>
      <QueryState q={q}>
        <DataTable columns={["Feature", "Entity", "Type", "Source", "Refresh", "Built by"]}
          rows={f.map((x) => [x.name, x.entity, x.type, (x.source as string[]).join(", "), x.refresh, x.built_by])}
          render={(v, col) => (col === "Built by" ? <Badge kind={v === "llm" ? "llm" : "sql"}>{String(v)}</Badge> : col === "Feature" ? <code>{String(v)}</code> : String(v))} />
      </QueryState>
    </>
  );
}
