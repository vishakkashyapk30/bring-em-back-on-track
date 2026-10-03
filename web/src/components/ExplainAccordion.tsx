import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

/** Numbered accordion (used for the "why we recommend this" steps). Height animates smoothly; one item open. */
export function ExplainAccordion({ items, defaultOpen = 0 }: { items: { title: string; meta?: ReactNode; body: ReactNode }[]; defaultOpen?: number }) {
  const [open, setOpen] = useState<number | null>(defaultOpen);
  const base = useId();
  return (
    <ol className="m-0 list-none divide-y divide-grey-300/70 overflow-hidden rounded-[var(--radius-md)] border border-grey-300/70 p-0">
      {items.map((it, i) => {
        const isOpen = open === i;
        const id = `${base}-${i}`;
        return (
          <li key={it.title} className={clsx("transition-colors", isOpen ? "bg-brand-50/60" : "bg-white")}>
            <button type="button" aria-expanded={isOpen} aria-controls={id} onClick={() => setOpen(isOpen ? null : i)}
              className="flex w-full items-center gap-3 bg-transparent px-4 py-3 text-left transition-colors hover:bg-grey-100/70">
              <span className="w-6 font-[family-name:var(--font-display)] text-sm font-semibold text-muted tabular">{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1 text-[15px] font-medium">{it.title}</span>
              {it.meta}
              <ChevronDown size={18} aria-hidden className={clsx("text-muted transition-transform duration-200", isOpen && "rotate-180")} />
            </button>
            <div id={id} className="reveal" data-open={isOpen}>
              <div><div className="px-4 pb-4 pl-[52px] text-[14.5px]">{it.body}</div></div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
