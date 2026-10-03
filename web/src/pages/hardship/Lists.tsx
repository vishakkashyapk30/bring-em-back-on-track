import { useGet } from "@/api/hooks";
import { DataTable } from "@/components/DataTable";
import { QueryState } from "@/components/States";

/** Generic list view over a fixture/real endpoint. TODO(WS-G): bespoke columns, actions (confirm/clear flag). */
function ListView({ path, k }: { path: string; k: string }) {
  const q = useGet(k, path);
  const items: Record<string, unknown>[] = q.data?.items ?? [];
  const cols = items[0] ? Object.keys(items[0]) : [];
  return <QueryState q={q}><DataTable columns={cols} rows={items.map((i) => cols.map((c) => i[c]))} /></QueryState>;
}

export const Board = () => <ListView k="hboard" path="/hardship/board" />;
export const Missed = () => <ListView k="hmissed" path="/hardship/missed-offers" />;
export const Overrides = () => <ListView k="hover" path="/hardship/overrides" />;
export { ListView };
