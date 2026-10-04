import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./Button";

/** Plain confirm step. Native <dialog> traps focus and closes on Esc, like OverrideDialog. */
export function ConfirmDialog({ open, title, children, confirmLabel, busy, onClose, onConfirm }: {
  open: boolean; title: string; children: ReactNode; confirmLabel: string; busy?: boolean; onClose: () => void; onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (open) ref.current?.showModal(); else ref.current?.close(); }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="confirm-title" className="m-auto w-full max-w-md rounded-[var(--radius-lg)] border border-grey-300/70 p-6 shadow-[var(--shadow-raised)]">
      <h3 id="confirm-title" className="mt-0">{title}</h3>
      <div className="text-[14.5px] text-muted">{children}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={busy} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </dialog>
  );
}
