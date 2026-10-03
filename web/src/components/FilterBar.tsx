import clsx from "clsx";
import { Search, X } from "lucide-react";
import type { ReactNode } from "react";

export type Chip = { id: string; label: string; count?: number };

/** Filters as plain text with an underline on the active one and a live count. Real buttons with aria-pressed. */
export function FilterChips({ chips, value, onChange, label }: { chips: Chip[]; value: string; onChange: (id: string) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-x-5 gap-y-1">
      {chips.map((c) => {
        const on = c.id === value;
        const empty = c.count === 0 && !on;
        return (
          <button key={c.id} type="button" aria-pressed={on} disabled={empty} onClick={() => onChange(c.id)}
            className={clsx(
              "inline-flex h-9 items-baseline gap-1.5 border-b-2 pb-1 pt-1.5 text-[14.5px] transition-colors",
              on ? "border-brand font-semibold text-ink" : "border-transparent font-medium text-ink/70 hover:border-grey-300 hover:text-ink",
              empty && "cursor-not-allowed opacity-40 hover:border-transparent hover:text-ink/70",
            )}>
            {c.label}
            {c.count != null && <span className="tabular text-[12.5px] font-normal text-muted">{c.count.toLocaleString()}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function SearchBox({ value, onChange, placeholder, label }: { value: string; onChange: (v: string) => void; placeholder: string; label: string }) {
  return (
    <div className="relative w-full sm:w-72">
      <Search size={15} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={label}
        className="h-9 w-full rounded-[var(--radius-md)] border border-grey-300 bg-white pl-9 pr-8 text-[14px] outline-none transition-shadow focus:border-brand/50 focus:shadow-[var(--shadow-focus)] [&::-webkit-search-cancel-button]:hidden" />
      {value && (
        <button type="button" onClick={() => onChange("")} aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-ink">
          <X size={14} aria-hidden />
        </button>
      )}
    </div>
  );
}

export function SortSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <label className="inline-flex items-center gap-2 text-[13.5px] text-muted">
      Sort by
      <select value={value} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-[var(--radius-md)] border border-grey-300 bg-white px-2 text-[14px] text-ink">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

/** One consistent toolbar row: filters on the left, search and sort on the right. */
export function Toolbar({ left, right }: { left?: ReactNode; right?: ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">{<div>{left}</div>}<div className="flex flex-wrap items-center gap-3">{right}</div></div>;
}
