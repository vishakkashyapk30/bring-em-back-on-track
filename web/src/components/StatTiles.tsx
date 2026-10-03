import { Card } from "./Card";

export type Stat = { label: string; value: string; note?: string; status?: "ok" | "warn" | "bad" };

/** KPI row of stat tiles (dataviz: a handful of headline numbers is a stat row, not a chart).
 * Status is never colour alone: a text note always accompanies it. */
export function StatTiles({ items }: { items: Stat[] }) {
  return (
    <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((s) => (
        <Card key={s.label} className="flex flex-col gap-1">
          <span className="text-sm text-muted">{s.label}</span>
          <span className="text-3xl font-medium tabular">{s.value}</span>
          {s.note && (
            <span className={`text-sm ${s.status === "bad" ? "text-danger" : s.status === "warn" ? "text-amber" : s.status === "ok" ? "text-teal" : "text-muted"}`}>
              {s.note}
            </span>
          )}
        </Card>
      ))}
    </div>
  );
}
