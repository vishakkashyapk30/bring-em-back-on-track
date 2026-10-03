import type { ReactNode } from "react";

/** Figma "Heading & Subheading": highlighted pill + short subtitle beside it. */
export function SectionTag({ children, subtitle, as: Tag = "h2" }: { children: ReactNode; subtitle?: ReactNode; as?: "h1" | "h2" | "h3" }) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-2">
      <Tag className="m-0 inline-block rounded-[var(--radius-sm)] bg-brand px-2 text-2xl font-medium leading-tight text-white md:text-[40px] md:leading-[1.2]">
        {children}
      </Tag>
      {subtitle && <p className="m-0 max-w-xl text-muted">{subtitle}</p>}
    </div>
  );
}
