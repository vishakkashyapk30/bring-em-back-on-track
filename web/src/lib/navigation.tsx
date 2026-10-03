import { useEffect, useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";

const TAB_TITLE = "back-on-track.ai"; // the same on every page, by request

/** Natural navigation: new pages start at the top (or at the #section asked for), and the tab title stays the same. */
export function NavigationEffects() {
  const { pathname, hash } = useLocation();
  useEffect(() => { document.title = TAB_TITLE; }, [pathname]);
  // Before the browser paints the new page, so the old scroll position is never seen on it.
  useLayoutEffect(() => {
    if (hash) {
      const el = document.getElementById(hash.slice(1));
      if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    }
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname, hash]);
  return null;
}

/** Load every page's code in the background once the browser is idle, so navigating never shows a loading flash. */
export function preloadPages(loaders: (() => Promise<unknown>)[]) {
  const run = () => loaders.forEach((l) => l().catch(() => undefined));
  const w = window as Window & { requestIdleCallback?: (cb: () => void) => void };
  if (w.requestIdleCallback) w.requestIdleCallback(run); else setTimeout(run, 1200);
}
