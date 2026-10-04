import clsx from "clsx";
import { Star } from "lucide-react";

import { usePins, useTogglePin, type WatchKind } from "@/api/inbox";

/** Follow or stop following a subject (saved watchlist). A toggle button with aria-pressed; the pin list updates at
 * once and rolls back if the server refuses (for example, a subject you may not open). Pins are audited. */
export function WatchButton({ kind, id, label, className }: { kind: WatchKind; id: string; label?: string; className?: string }) {
  const pins = usePins();
  const toggle = useTogglePin();
  const pinned = !!pins.data?.some((p) => p.kind === kind && p.subject_id === id);
  const name = label || id;
  return (
    <button
      type="button"
      aria-pressed={pinned}
      aria-label={pinned ? `Stop watching ${name}` : `Watch ${name}`}
      title={pinned ? "On your watchlist. Select to stop watching." : "Add to your watchlist to see what changes."}
      disabled={pins.isLoading}
      onClick={() => toggle.mutate({ kind, id, label, pinned })}
      className={clsx(
        "inline-flex h-10 select-none items-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] border px-3 text-[14.5px] font-medium",
        "transition-colors duration-150 focus-visible:shadow-[var(--shadow-focus)] focus-visible:outline-none disabled:opacity-50",
        pinned ? "border-brand/40 bg-brand-50 text-brand-700 hover:bg-brand-50/70" : "border-grey-300 bg-white text-ink hover:border-ink/40 hover:bg-cream",
        className,
      )}
    >
      <Star size={16} aria-hidden className={pinned ? "fill-current" : ""} />
      {pinned ? "Watching" : "Watch"}
    </button>
  );
}
