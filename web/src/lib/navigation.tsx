import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const TITLES: [RegExp, string][] = [
  [/^\/$/, "Bring 'em back on track"], [/^\/login/, "Sign in"], [/^\/queue/, "Today's queue"],
  [/^\/customers\//, "Customer 360"], [/^\/calls\//, "Post-call summary"], [/^\/ask/, "Collections Ask"],
  [/^\/hardship/, "Hardship workbench"], [/^\/map/, "Weather map"], [/^\/team/, "Team"], [/^\/features/, "Feature store"],
  [/^\/governance/, "Governance"], [/^\/steward/, "Identity review"],
];

/** Natural navigation: new pages start at the top (or at the #section asked for), and the tab title follows. */
export function NavigationEffects() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    const t = TITLES.find(([re]) => re.test(pathname))?.[1] ?? "Collections 360";
    document.title = `${t} · Collections 360`;
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
