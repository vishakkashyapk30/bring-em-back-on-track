import { X } from "lucide-react";

/** "Understood as" tokens: editable/removable chips. TODO(WS-G): edit + add filter. */
export function ChipEditor({ chips, onRemove }: { chips: { key: string; label: string }[]; onRemove?: (key: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Understood as">
      <span className="text-sm text-muted">Understood as:</span>
      {chips.map((c) => (
        <span key={c.key} className="inline-flex items-center gap-1 rounded-full border border-grey-300 bg-white transition-colors hover:bg-grey-100 px-3 py-1 text-sm">
          {c.label}
          {onRemove && (
            <button type="button" aria-label={`Remove ${c.label}`} onClick={() => onRemove(c.key)} className="bg-transparent p-0"><X size={14} /></button>
          )}
        </span>
      ))}
    </div>
  );
}
