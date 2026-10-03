import { useSyncExternalStore } from "react";

const Q = "(prefers-reduced-motion: reduce)";
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => { const m = window.matchMedia?.(Q); m?.addEventListener?.("change", cb); return () => m?.removeEventListener?.("change", cb); },
    () => !!window.matchMedia?.(Q).matches, () => false);
}
