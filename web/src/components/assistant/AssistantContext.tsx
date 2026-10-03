import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

export type AssistantContextIds = { caseId?: string; goldenId?: string; label?: string };
type Ctx = {
  isOpen: boolean;
  /** Preselected customer or case (for example from the demo). The person can clear it in the drawer. */
  preset: AssistantContextIds | null;
  launcherRef: RefObject<HTMLButtonElement>;
  open: (preset?: AssistantContextIds) => void;
  close: () => void;
  clearPreset: () => void;
};
const C = createContext<Ctx | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [preset, setPreset] = useState<AssistantContextIds | null>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const open = useCallback((p?: AssistantContextIds) => { if (p) setPreset(p); setOpen(true); }, []);
  const close = useCallback(() => setOpen(false), []);
  const clearPreset = useCallback(() => setPreset(null), []);
  const value = useMemo(() => ({ isOpen, preset, launcherRef, open, close, clearPreset }), [isOpen, preset, open, close, clearPreset]);
  return <C.Provider value={value}>{children}</C.Provider>;
}

export function useAssistant(): Ctx {
  const c = useContext(C);
  if (!c) throw new Error("useAssistant must be used inside AssistantProvider");
  return c;
}
