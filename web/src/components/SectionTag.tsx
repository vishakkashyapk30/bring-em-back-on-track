import clsx from "clsx";
import type { ReactNode } from "react";

/** The one heading pattern for the app.
 * h1 = page title (2.25rem) with an optional subtitle and actions on the right.
 * h2 = section title (1.25rem; `large` = 1.5rem for the public landing sections).
 * h3 = card title (1.0625rem).
 * (Name kept for compatibility; this replaced the oversized red pill headings.) */
export function SectionTag({ children, subtitle, as: Tag = "h2", actions, large = false, id, className }: {
  children: ReactNode; subtitle?: ReactNode; as?: "h1" | "h2" | "h3"; actions?: ReactNode; large?: boolean; id?: string; className?: string;
}) {
  const page = Tag === "h1";
  const size = page ? "text-[2.25rem]" : Tag === "h3" ? "text-[1.0625rem]" : large ? "text-[1.5rem]" : "text-[1.25rem]";
  return (
    <div className={clsx(page ? "mb-6 flex flex-wrap items-end justify-between gap-4" : "mb-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-2", className)}>
      <div className="min-w-0">
        <Tag id={id} className={clsx("m-0 text-ink", size)}>{children}</Tag>
        {subtitle && <p className={page ? "mb-0 mt-1.5 max-w-3xl text-[16px] text-muted" : "mb-0 mt-1 max-w-3xl text-[14px] text-muted"}>{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Small label above a group of values (sentence case, body face). Replaces ad hoc uppercase serif labels. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("text-[13px] font-semibold text-muted", className)}>{children}</div>;
}
