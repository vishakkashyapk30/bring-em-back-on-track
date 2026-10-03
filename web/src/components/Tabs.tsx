import clsx from "clsx";
import { NavLink } from "react-router-dom";

const base = "relative -mb-px inline-flex h-10 items-center border-b-2 px-1 text-[14px] font-medium no-underline transition-colors hover:no-underline";
const on = "border-brand text-brand";
const off = "border-transparent text-muted hover:border-grey-300 hover:text-ink";

/** Underlined tabs for sub-pages (route-based). */
export function RouteTabs({ tabs, label }: { tabs: [string, string][]; label: string }) {
  return (
    <nav aria-label={label} className="mb-6 flex gap-6 overflow-x-auto overflow-y-hidden border-b border-grey-300/70 [scrollbar-width:none]">
      {tabs.map(([to, text]) => (
        <NavLink key={to} to={to} className={({ isActive }) => clsx(base, isActive ? on : off)}>{text}</NavLink>
      ))}
    </nav>
  );
}

/** Segmented control for switching a view in place (e.g. the map metric). */
export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-[var(--radius-md)] border border-grey-300/70 bg-white p-1 shadow-[var(--shadow-card)]">
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
          className={clsx("h-8 rounded-[7px] px-3 text-[14px] font-medium transition-colors", value === v ? "bg-ink text-white" : "text-muted hover:text-ink")}>{text}</button>
      ))}
    </div>
  );
}
