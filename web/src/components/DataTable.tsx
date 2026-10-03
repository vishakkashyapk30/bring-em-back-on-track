import type { ReactNode } from "react";

import { EmptyState } from "./States";

/** Plain data table with sticky header. TODO(WS-G): sorting, virtualisation > 500 rows, "<10" suppression marker. */
export function DataTable({ columns, rows, render }: { columns: string[]; rows: unknown[][]; render?: (v: unknown, col: string) => ReactNode }) {
  if (!rows.length) return <EmptyState title="No rows" />;
  return (
    <div className="overflow-x-auto rounded-[var(--radius-md)] border border-grey-300 bg-white">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="sticky top-0 bg-grey-100">
          <tr>{columns.map((c) => <th key={c} scope="col" className="px-3 py-2 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-grey-300">
              {r.map((v, j) => <td key={j} className="px-3 py-2 tabular">{render ? render(v, columns[j]) : String(v ?? "—")}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
