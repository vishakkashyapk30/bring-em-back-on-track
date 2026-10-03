import { useSyncExternalStore } from "react";

const KEY = "bot-demo-progress";
const EVENT = "bot-demo-progress-change";
export type DemoProgress = { persona: string; stage: number; total: number } | null;

let cache: { raw: string | null; value: DemoProgress } = { raw: null, value: null };
function read(): DemoProgress {
  let raw: string | null = null;
  try { raw = sessionStorage.getItem(KEY); } catch { /* storage blocked */ }
  if (raw !== cache.raw) { try { cache = { raw, value: raw ? JSON.parse(raw) : null }; } catch { cache = { raw, value: null }; } }
  return cache.value;
}
/** Only the persona and stage number are kept (this tab only): where the person is in the demo. */
export function setDemoProgress(p: DemoProgress) {
  try { if (p) sessionStorage.setItem(KEY, JSON.stringify(p)); else sessionStorage.removeItem(KEY); } catch { /* ignore */ }
  window.dispatchEvent(new Event(EVENT));
}
export function useDemoProgress(): DemoProgress {
  return useSyncExternalStore((cb) => { window.addEventListener(EVENT, cb); return () => window.removeEventListener(EVENT, cb); }, read, () => null);
}
