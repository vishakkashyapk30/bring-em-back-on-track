import clsx from "clsx";
import { Clock } from "lucide-react";

/** "Data as of 28 Sep 06:00 ET · 3 h old"; amber past the 26 h SLA (contract rule 9). */
export function FreshnessPill({ asOf, hours, fixture }: { asOf?: string; hours?: number; fixture?: boolean }) {
  const stale = (hours ?? 0) > 26;
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-[13.5px]", stale ? "font-semibold text-amber" : "text-muted")}>
      <Clock size={14} aria-hidden />
      {asOf ? `Data from ${new Date(asOf).toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Toronto" })} ET` : "We don't know how fresh this is"}
      {hours !== undefined && ` (${hours} h ago)`}
      {fixture && " (sample data)"}
    </span>
  );
}
