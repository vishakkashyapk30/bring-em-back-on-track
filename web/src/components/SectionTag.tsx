import type { ReactNode } from "react";

/** Page and section headings. h1 = page title with a short brand accent; h2/h3 = section titles.
 * (Name kept for compatibility; this replaced the oversized red pill headings.) */
export function SectionTag({ children, subtitle, as: Tag = "h2", actions }: { children: ReactNode; subtitle?: ReactNode; as?: "h1" | "h2" | "h3"; actions?: ReactNode }) {
  const page = Tag === "h1";
  return (
    <div className={page ? "mb-6 flex flex-wrap items-end justify-between gap-4" : "mb-4 mt-2 flex flex-wrap items-end justify-between gap-3"}>
      <div className="min-w-0">
        <Tag className={page ? "m-0 text-[2.25rem] text-ink" : "m-0 text-[1.5rem] text-ink"}>{children}</Tag>
        {subtitle && <p className={page ? "mb-0 mt-1.5 max-w-3xl text-[16px] text-muted" : "mb-0 mt-1 max-w-3xl text-[14.5px] text-muted"}>{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
