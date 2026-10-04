import { ArrowDown, ArrowRight } from "lucide-react";
import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";

// The globe (and the map data behind it) is its own chunk, so the headline and buttons paint first.
const Globe = lazy(() => import("@/components/Globe").then((m) => ({ default: m.Globe })));

/** The signed-out opening: the turning globe centred on the cream page, the headline, one sentence and two buttons
 * centred in front of it. Nothing from the data is requested or shown here. */
export function Hero() {
  const btn = "inline-flex h-12 items-center justify-center gap-2 rounded-[var(--radius-md)] border px-6 text-[16px] font-semibold no-underline transition-colors hover:no-underline";
  return (
    <section aria-label="back-on-track.ai" className="relative isolate flex items-center justify-center overflow-hidden border-b border-grey-300/70"
      style={{ minHeight: "max(640px, calc(100svh - 72px))" }}>
      <div className="absolute left-1/2 top-1/2 w-[min(860px,130vw,calc(100svh-110px))] -translate-x-1/2 -translate-y-1/2">
        <Suspense fallback={<div aria-hidden className="aspect-square w-full rounded-full border border-grey-300/50 bg-white/40" />}><Globe tone="light" /></Suspense>
      </div>
      <div className="pointer-events-none relative z-10 mx-auto flex max-w-3xl flex-col items-center px-6 py-20 text-center">
        <span aria-hidden className="absolute -inset-x-6 -inset-y-2 -z-10 rounded-[50%] bg-cream/65 blur-2xl" />
        <h1 className="m-0 text-[clamp(2.75rem,6.4vw,5.75rem)] font-semibold leading-[1.04] tracking-tight text-ink">Help customers get back on track.</h1>
        <p className="mb-0 mt-6 max-w-[32rem] text-[18px] leading-relaxed text-ink/75">
          One record for every customer, a plain-English way to ask questions, and a suggested next step that a person always approves.
        </p>
        <div className="pointer-events-auto mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link to="/login" className={`${btn} border-transparent bg-brand text-white hover:bg-brand-700`}>Sign in as a persona <ArrowRight size={17} aria-hidden /></Link>
          <Link to="/demo" className={`${btn} border-ink bg-cream text-ink hover:bg-ink hover:text-white`}>Watch the demo</Link>
        </div>
      </div>
      <a href="#how" className="absolute bottom-3 left-1/2 z-10 flex min-h-10 -translate-x-1/2 justify-center flex-col items-center gap-1 text-[11px] font-medium tracking-[0.25em] text-muted no-underline hover:text-ink hover:no-underline">
        SCROLL <ArrowDown size={14} aria-hidden />
      </a>
    </section>
  );
}
