import clsx from "clsx";
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { NavLink, useLocation, useSearchParams } from "react-router-dom";

const base = "relative -mb-px inline-flex h-10 shrink-0 items-center whitespace-nowrap border-b-2 px-1 text-[14px] font-medium no-underline transition-colors hover:no-underline";
const on = "border-brand text-brand";
const off = "border-transparent text-muted hover:border-grey-300 hover:text-ink";
const bar = "mb-5 flex gap-6 overflow-x-auto overflow-y-hidden border-b border-grey-300/70 [scrollbar-width:none]";

/** Underlined tabs for sub-pages (route-based). A tab is active for any path under its first segment,
 * so "simulator/start" stays selected on "simulator/CS-123". */
export function RouteTabs({ tabs, label }: { tabs: [string, string][]; label: string }) {
  const { pathname } = useLocation();
  return (
    <nav aria-label={label} className={bar}>
      {tabs.map(([to, text]) => {
        const seg = to.split("/")[0];
        const active = pathname.split("/").includes(seg);
        return <NavLink key={to} to={to} aria-current={active ? "page" : undefined} className={clsx(base, active ? on : off)}>{text}</NavLink>;
      })}
    </nav>
  );
}

/** In-page tabs that keep a long page to one screen. The chosen tab lives in the URL (?tab=), so links and
 * back/forward keep it. Arrow keys move between tabs (WAI-ARIA tabs pattern). */
export function PageTabs({ tabs, label, param = "tab", variant = "underline", children }: {
  tabs: { id: string; label: string; count?: number }[]; label: string; param?: string;
  /** "segmented" for a second level inside a page that already has underlined tabs. */
  variant?: "underline" | "segmented";
  children: (active: string) => ReactNode;
}) {
  const [sp, setSp] = useSearchParams();
  const active = tabs.some((t) => t.id === sp.get(param)) ? (sp.get(param) as string) : tabs[0].id;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const pick = (id: string) => {
    const n = new URLSearchParams(sp);
    if (id === tabs[0].id) n.delete(param); else n.set(param, id);
    setSp(n, { replace: true });
  };
  const onKey = (e: KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const j = (i + d + tabs.length) % tabs.length;
    pick(tabs[j].id);
    refs.current[j]?.focus();
  };
  return (
    <>
      <div role="tablist" aria-label={label} className={variant === "segmented" ? "mb-4 inline-flex max-w-full overflow-x-auto rounded-[var(--radius-md)] border border-grey-300/70 bg-white p-1 [scrollbar-width:none]" : bar}>
        {tabs.map((t, i) => {
          const sel = active === t.id;
          return (
            <button key={t.id} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`tab-${t.id}`} aria-selected={sel}
              aria-controls={`panel-${t.id}`} tabIndex={sel ? 0 : -1} onClick={() => pick(t.id)} onKeyDown={(e) => onKey(e, i)}
              className={variant === "segmented"
                ? clsx("inline-flex h-8 shrink-0 items-center whitespace-nowrap rounded-[var(--radius-sm)] px-3 text-[14px] font-medium transition-colors", sel ? "bg-brand text-white" : "text-muted hover:text-ink")
                : clsx(base, "bg-transparent", sel ? on : off)}>
              {t.label}{t.count != null && <span className={clsx("ml-1.5 tabular text-[12.5px] font-normal", sel && variant === "segmented" ? "text-white/75" : "text-muted")}>{t.count.toLocaleString()}</span>}
            </button>
          );
        })}
      </div>
      <div key={active} role="tabpanel" id={`panel-${active}`} aria-labelledby={`tab-${active}`} className="fade-in">{children(active)}</div>
    </>
  );
}

/** Segmented control for switching a view in place (e.g. the map metric). */
export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full rounded-[var(--radius-md)] border border-grey-300/70 bg-white p-1">
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
          className={clsx("h-8 shrink-0 whitespace-nowrap rounded-[var(--radius-sm)] px-3 text-[14px] font-medium transition-colors", value === v ? "bg-brand text-white" : "text-muted hover:text-ink")}>{text}</button>
      ))}
    </div>
  );
}
