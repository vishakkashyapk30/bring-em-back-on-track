import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { FilterChips, SearchBox, Toolbar } from "./FilterBar";
import { EmptyState } from "./States";

const PAGE = 25;
const num = (v: unknown) => (typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v.replace(/[$,%]/g, ""))) ? Number(v.replace(/[$,%]/g, "")) : null);

/** Data table: click a header to sort (numbers numerically), numeric columns right-aligned, sticky header,
 * row hover, and 25 rows at a time with "Show more" so long tables stay fast. */
export type RowFilter = { id: string; label: string; test: (row: unknown[]) => boolean };

export function DataTable({ columns, rows: allRows, render, pageSize = PAGE, bare = false, searchable, filters, summary, maxHeight = "min(600px, 68vh)", actions }: {
  columns: string[]; rows: unknown[][]; render?: (v: unknown, col: string) => ReactNode; pageSize?: number; bare?: boolean;
  /** Height of the scroll area; the header stays put while the rows scroll. */
  maxHeight?: string;
  /** Extra controls shown in the toolbar next to the search box. */
  actions?: ReactNode;
  /** Placeholder text; turns on a search box that matches any text or number cell. */
  searchable?: string;
  /** Pill filters with live counts; "All" is added in front. */
  filters?: RowFilter[];
  /** Shown in the footer, e.g. "customers". */
  summary?: string;
}) {
  const [text, setText] = useState("");
  const [filter, setFilter] = useState("all");
  const rows = useMemo(() => {
    const f = filters?.find((x) => x.id === filter);
    const needle = text.trim().toLowerCase();
    return allRows.filter((r) => (!f || f.test(r)) && (!needle || r.some((v) => (typeof v === "string" || typeof v === "number") && String(v).toLowerCase().includes(needle))));
  }, [allRows, filters, filter, text]);
  const [sort, setSort] = useState<{ i: number; dir: 1 | -1 } | null>(null);
  const [shown, setShown] = useState(pageSize);
  const numericCol = useMemo(() => columns.map((_, j) => rows.length > 0 && rows.every((r) => r[j] == null || num(r[j]) !== null)), [columns, rows]);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const { i, dir } = sort;
    return [...rows].sort((a, b) => {
      const x = a[i], y = b[i];
      const nx = num(x), ny = num(y);
      if (nx !== null && ny !== null) return (nx - ny) * dir;
      return String(x ?? "").localeCompare(String(y ?? "")) * dir;
    });
  }, [rows, sort]);
  const toolbar = (searchable || filters || actions) && (
    <Toolbar
      left={filters && <FilterChips label="Filter rows" value={filter} onChange={(v) => { setFilter(v); setShown(pageSize); }}
        chips={[{ id: "all", label: "All", count: allRows.length }, ...filters.map((f) => ({ id: f.id, label: f.label, count: allRows.filter(f.test).length })).filter((c) => c.count > 0 || c.id === filter)]} />}
      right={<>{actions}{searchable && <SearchBox label="Search this table" placeholder={searchable} value={text} onChange={(v) => { setText(v); setShown(pageSize); }} />}</>}
    />
  );
  if (!allRows.length) return <EmptyState title="Nothing to show" />;
  if (!rows.length) return <>{toolbar}<EmptyState title="No matches" detail="Try another filter, or clear the search." /></>;
  // a short tail is not worth a "Show more" click: show up to 10 extra rows straight away
  const limit = sorted.length <= shown + 10 ? sorted.length : shown;
  const toggle = (i: number) => setSort((s) => (s?.i === i ? (s.dir === 1 ? { i, dir: -1 } : null) : { i, dir: 1 }));
  return (
    <>
    {toolbar}
    <div className={clsx("overflow-hidden bg-white", bare ? "rounded-[var(--radius-md)] border border-grey-300/60" : "rounded-[var(--radius-md)] border border-grey-300")}>
      <div className="overflow-auto" style={{ maxHeight }}>
        <table className="w-full border-collapse text-left text-[14px]">
          <thead className="sticky top-0 z-10 bg-white shadow-[inset_0_-2px_0_var(--color-ink)]">
            <tr>{columns.map((c, i) => (
              <th key={c} scope="col" aria-sort={sort?.i === i ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                className={clsx("whitespace-nowrap px-4 py-3 text-[13.5px] font-semibold text-ink", numericCol[i] && "text-right")}>
                {c ? (
                  <button type="button" onClick={() => toggle(i)} className={clsx("inline-flex items-center gap-1.5 bg-transparent hover:text-brand", numericCol[i] && "flex-row-reverse")}>
                    {c}{sort?.i === i ? (sort.dir === 1 ? <ArrowUp size={13} /> : <ArrowDown size={13} />) : <ArrowUpDown size={13} className="opacity-40" />}
                  </button>
                ) : <span className="sr-only">Actions</span>}
              </th>))}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, limit).map((r, i) => (
              <tr key={i} className="border-t border-grey-300/60 transition-colors even:bg-cream/60 hover:bg-brand-50">
                {r.map((v, j) => (
                  <td key={j} className={clsx("px-4 py-2.5 align-top", j === 0 && "font-medium", numericCol[j] && "whitespace-nowrap text-right tabular")}>{render ? render(v, columns[j]) : String(v ?? "n/a")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > limit && (
        <div className="flex items-center justify-between border-t border-grey-300/60 bg-grey-100/50 px-4 py-2 text-[13.5px] text-muted">
          <span aria-live="polite">Showing {limit} of {sorted.length.toLocaleString()}{summary ? ` ${summary}` : ""}</span>
          <button type="button" onClick={() => setShown(shown + pageSize * 2)} className="rounded-[var(--radius-md)] px-3 py-1 font-medium text-brand hover:bg-white">Show more</button>
        </div>
      )}
    </div>
    </>
  );
}
