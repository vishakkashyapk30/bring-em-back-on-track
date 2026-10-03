import clsx from "clsx";
import { Clock } from "lucide-react";

/** "Data as of 28 Sep 06:00 ET · 3 h old"; amber past the 26 h SLA (contract rule 9). */
export function FreshnessPill({ asOf, hours, fixture }: { asOf?: string; hours?: number; fixture?: boolean }) {
  const stale = (hours ?? 0) > 26;
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm", stale ? "bg-amber-50 text-amber" : "bg-grey-100 text-muted")}>
      <Clock size={14} aria-hidden />
      {asOf ? `Data as of ${new Date(asOf).toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Toronto" })} ET` : "Freshness unknown"}
      {hours !== undefined && ` · ${hours} h old`}
      {fixture && " · fixture"}
    </span>
  );
}
