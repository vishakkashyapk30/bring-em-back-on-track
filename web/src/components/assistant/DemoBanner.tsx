import { X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { demoPath } from "./helpers";
import { setDemoProgress, useDemoProgress } from "./demoProgress";

/** Small persistent banner shown on the real screens while a demo is under way, so the person can come back. */
export function DemoBanner() {
  const p = useDemoProgress();
  const loc = useLocation();
  if (!p || loc.pathname.startsWith("/demo")) return null;
  return (
    <div role="region" aria-label="Demo in progress" className="border-b border-grey-300/70 bg-brand-50">
      <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2 text-[14px] md:px-10">
        <span className="font-semibold tabular-nums">Demo: stage {p.stage} of {p.total}</span>
        <Link to={demoPath(p.persona, p.stage)} className="font-semibold text-brand underline underline-offset-4 hover:text-brand-700">Return to the demo</Link>
        <button type="button" onClick={() => setDemoProgress(null)} aria-label="Leave the demo" className="ml-auto inline-flex items-center gap-1 text-muted hover:text-ink"><X size={15} aria-hidden />Leave the demo</button>
      </div>
    </div>
  );
}
