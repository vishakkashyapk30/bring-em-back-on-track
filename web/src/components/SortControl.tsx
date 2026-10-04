import { ArrowDown, ArrowUp } from "lucide-react";

import { Button } from "./Button";
import { SortSelect } from "./FilterBar";

export type Dir = "asc" | "desc";

/** Compact "Sort by [field] [direction]" control. The select and the toggle are real form controls, so Tab,
 * arrow keys and Enter work; the toggle announces the current direction and what pressing it does. */
export function SortControl({ value, dir, options, onChange, onDir }: {
  value: string; dir: Dir; options: [string, string][]; onChange: (v: string) => void; onDir: (d: Dir) => void;
}) {
  const Icon = dir === "asc" ? ArrowUp : ArrowDown;
  const text = dir === "asc" ? "Ascending" : "Descending";
  return (
    <div className="inline-flex items-center gap-1.5">
      <SortSelect value={value} onChange={onChange} options={options} />
      <Button size="sm" aria-label={`${text}. Switch to ${dir === "asc" ? "descending" : "ascending"}`} title={text}
        onClick={() => onDir(dir === "asc" ? "desc" : "asc")} className="h-9 w-9 px-0">
        <Icon size={15} aria-hidden />
      </Button>
    </div>
  );
}
