import clsx from "clsx";
import { Minus, Plus } from "lucide-react";
import { useState, type ReactNode } from "react";

/** Figma "Working Process" numbered accordion. The open item takes the brand fill. */
export function ExplainAccordion({ items, defaultOpen = 0 }: { items: { title: string; meta?: ReactNode; body: ReactNode }[]; defaultOpen?: number }) {
  const [open, setOpen] = useState<number | null>(defaultOpen);
  return (
    <ol className="m-0 list-none space-y-3 p-0">
      {items.map((it, i) => {
        const isOpen = open === i;
        const id = `acc-${i}-${it.title.replace(/\s+/g, "-")}`;
        return (
          <li key={it.title} className={clsx("rounded-[var(--radius-md)] border border-ink", isOpen ? "bg-brand-50" : "bg-grey-100")}>
            <button
              type="button" aria-expanded={isOpen} aria-controls={id}
              onClick={() => setOpen(isOpen ? null : i)}
              className="flex w-full items-center gap-4 bg-transparent px-4 py-3 text-left"
            >
              <span className="text-2xl font-medium tabular">{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1 font-medium">{it.title}</span>
              {it.meta}
              <span className="grid h-8 w-8 place-items-center rounded-full border border-ink bg-white">{isOpen ? <Minus size={16} /> : <Plus size={16} />}</span>
            </button>
            {isOpen && <div id={id} className="border-t border-ink/20 px-4 py-3">{it.body}</div>}
          </li>
        );
      })}
    </ol>
  );
}
