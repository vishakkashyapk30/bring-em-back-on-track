import { useEffect, useRef, useState } from "react";

const REASONS = [
  ["customer_request", "Customer request"],
  ["hardship_suspected", "Hardship suspected"],
  ["wrong_data", "Data looks wrong"],
  ["other", "Other"],
] as const;

/** Override needs a reason code. Native <dialog> for focus trapping + Esc. */
export function OverrideDialog({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (reason: string, note: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState<string>("");
  const [note, setNote] = useState("");
  useEffect(() => { if (open) ref.current?.showModal(); else ref.current?.close(); }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-full max-w-md rounded-[var(--radius-lg)] border border-grey-300/70 p-6 shadow-[var(--shadow-raised)]">
      <form method="dialog" onSubmit={(e) => { e.preventDefault(); if (reason) onSubmit(reason, note); }}>
        <h3 className="mt-0">Override this action</h3>
        <fieldset className="m-0 space-y-2 border-0 p-0">
          <legend className="mb-2 text-sm text-muted">Reason (required)</legend>
          {REASONS.map(([v, l]) => (
            <label key={v} className="flex items-center gap-2"><input type="radio" name="reason" value={v} checked={reason === v} onChange={() => setReason(v)} /> {l}</label>
          ))}
        </fieldset>
        <label className="mt-4 block text-sm">Note<textarea value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 block w-full rounded-[var(--radius-md)] border border-ink p-2" rows={3} /></label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-[var(--radius-md)] border border-grey-300 bg-white transition-colors hover:bg-grey-100 px-4 py-2">Cancel</button>
          <button type="submit" disabled={!reason} className="rounded-[var(--radius-md)] bg-brand px-4 py-2 text-white disabled:opacity-50">Save override</button>
        </div>
      </form>
    </dialog>
  );
}
