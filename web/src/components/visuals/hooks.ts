import { useEffect, useRef, useState } from "react";

import { useMe } from "@/api/hooks";

/** Whether someone is signed in. The data visuals only ask the API for numbers when this is true. */
export const useSignedIn = (): boolean => !!useMe().data;

/** True when the person asked their system for less motion. Follows changes while the page is open. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** Whether the element is on screen (and the tab visible); animations pause when it is not. */
export function useInView<T extends Element>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    let onScreen = true, tabVisible = !document.hidden;
    const set = () => setInView(onScreen && tabVisible);
    const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; set(); }, { threshold: 0.05 });
    const vis = () => { tabVisible = !document.hidden; set(); };
    io.observe(el);
    document.addEventListener("visibilitychange", vis);
    return () => { io.disconnect(); document.removeEventListener("visibilitychange", vis); };
  }, []);
  return [ref, inView];
}
