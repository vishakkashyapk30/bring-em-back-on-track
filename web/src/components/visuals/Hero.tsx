import { ArrowDown, ArrowRight } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

// The globe and the particle story are their own chunks (three.js lives only in the story's), so the headline and
// buttons paint first.
const Globe = lazy(() => import("@/components/Globe").then((m) => ({ default: m.Globe })));
const StoryScene = lazy(() => import("@/components/story/StoryScene"));

const HEADER = 72; // the sticky navbar's height, in px (Layout.tsx)
const LEAD = "One record for every customer, a plain-English way to ask questions, and a suggested next step that a person always approves.";

/** The four beats of the story. `at` is the scroll progress at which each beat is fully formed. */
const BEATS = [
  { at: 0, label: "Customers", title: "Every customer, in one place", text: "" },
  { at: 0.35, label: "Canada", title: "Across Canada", text: "Every account, from every system, matched into one record per person, coast to coast." },
  { at: 0.67, label: "Paths", title: "Every path back on track", text: "Policy rules first, then a model that spots promises at risk, then a suggested step that a person approves." },
  { at: 1, label: "Next step", title: "One customer, one clear next step", text: "With the reason behind it, ready for an agent to approve, edit or override." },
];
const beatAt = (p: number) => (p < 0.2 ? 0 : p < 0.49 ? 1 : p < 0.84 ? 2 : 3);

function canTell(): boolean {
  if (typeof window === "undefined" || typeof window.WebGLRenderingContext === "undefined") return false;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return false;
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2") || c.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

const BTN = "inline-flex items-center justify-center gap-2 rounded-[var(--radius-md)] border font-semibold no-underline transition-all duration-500 hover:no-underline";

/** The signed-out opening. With WebGL and motion allowed: a scroll story (globe, Canada, a road back on track, one
 * customer card) in a tall section with a sticky frame, after which the page scrolls on as normal. Otherwise, or if
 * WebGL fails: the turning 2D globe behind the headline. Nothing from the data is requested or shown here. */
export function Hero() {
  const [story, setStory] = useState(canTell);
  const fail = useCallback(() => setStory(false), []);
  return story ? <StoryHero onFail={fail} /> : <StaticHero />;
}

function StoryHero({ onFail }: { onFail: () => void }) {
  const section = useRef<HTMLElement>(null);
  const progress = useRef(0);
  const column = useRef<HTMLDivElement>(null), captions = useRef<HTMLDivElement>(null), actions = useRef<HTMLDivElement>(null), rail = useRef<HTMLElement>(null);
  const avoid = useMemo(() => ({ column, captions, actions, rail }), []);
  const [beat, setBeat] = useState(0);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    let raf = 0;
    const read = () => {
      raf = 0;
      const el = section.current;
      if (!el) return;
      const r = el.getBoundingClientRect(), frame = window.innerHeight - HEADER;
      const p = Math.min(1, Math.max(0, (HEADER - r.top) / Math.max(r.height - frame, 1)));
      progress.current = p;
      setBeat(beatAt(p));
      setStarted(p > 0.015);
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(read); };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, []);

  const goTo = (i: number) => {
    const el = section.current;
    if (!el) return;
    const range = el.offsetHeight - (window.innerHeight - HEADER);
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - HEADER + BEATS[i].at * range, behavior: "smooth" });
  };
  const final = beat === 3;

  return (
    <section ref={section} aria-label="back-on-track.ai" className="story-hero relative border-b border-grey-300/70 bg-cream text-ink">
      <div className="sticky overflow-hidden" style={{ top: HEADER, height: `calc(100svh - ${HEADER}px)` }}>
        <div className="absolute inset-0" role="img"
          aria-label="An animation that follows the story as you scroll: a globe of points with Canada in red, the map of Canada, a road that turns from red to teal as it climbs, and one customer card.">
          <Suspense fallback={null}><StoryScene progress={progress} onFail={onFail} avoid={avoid} /></Suspense>
        </div>
        <div aria-hidden className="story-vignette pointer-events-none absolute inset-0" />

        <div className="pointer-events-none relative z-10 mx-auto flex h-full max-w-[1680px] flex-col px-5 pb-14 pt-7 sm:pt-12 md:px-10 lg:justify-center lg:pb-10 lg:pt-10">
          <div ref={column} className="flex h-full max-w-[36rem] flex-col lg:block lg:h-auto lg:max-w-[40rem]">
            <div ref={captions} className="grid">
              <div className={`story-beat [grid-area:1/1] self-start lg:self-end ${beat === 0 ? "is-on" : ""}`}>
                <p className="m-0 text-[12px] font-semibold uppercase tracking-[0.22em] text-brand sm:text-[13px]">{BEATS[0].title}</p>
                <h1 className="mb-0 mt-3 text-[clamp(2.25rem,5.2vw,4.75rem)] font-semibold leading-[1.04] tracking-tight text-ink">Help customers get back on track.</h1>
                <p className="mb-0 mt-4 max-w-[32rem] text-[15.5px] leading-relaxed text-ink/75 sm:mt-5 sm:text-[18px]">{LEAD}</p>
              </div>
              {BEATS.slice(1).map((b, i) => (
                <div key={b.title} aria-hidden={beat !== i + 1} className={`story-beat [grid-area:1/1] self-start lg:self-end ${beat === i + 1 ? "is-on" : ""}`}>
                  <p className="m-0 text-[12px] font-semibold uppercase tracking-[0.22em] text-brand sm:text-[13px]">{b.label}</p>
                  <h2 className="mb-0 mt-3 text-[clamp(1.9rem,4.2vw,3.75rem)] font-semibold leading-[1.06] tracking-tight text-ink">{b.title}</h2>
                  <p className="mb-0 mt-4 max-w-[30rem] text-[15.5px] leading-relaxed text-ink/75 sm:text-[18px]">{b.text}</p>
                </div>
              ))}
            </div>
            <div ref={actions} className="pointer-events-auto mt-auto flex flex-col gap-3 pt-6 sm:flex-row sm:flex-wrap sm:items-center lg:mt-9 lg:pt-0">
              <Link to="/login" className={`${BTN} border-transparent bg-brand text-white hover:bg-brand-700 ${final ? "h-12 px-8 text-[16px] sm:h-14 sm:text-[17px] shadow-[var(--shadow-focus)]" : "h-11 px-6 text-[15.5px] sm:h-12 sm:text-[16px]"}`}>
                Sign in as a persona <ArrowRight size={17} aria-hidden />
              </Link>
              <Link to="/demo" className={`${BTN} border-ink bg-cream text-ink hover:bg-ink hover:text-white ${final ? "h-12 px-8 text-[16px] sm:h-14 sm:text-[17px]" : "h-11 px-6 text-[15.5px] sm:h-12 sm:text-[16px]"}`}>
                Watch the demo
              </Link>
            </div>
          </div>
        </div>

        <nav ref={rail} aria-label="Story" className="absolute bottom-5 left-1/2 z-10 flex -translate-x-1/2 gap-2 lg:bottom-auto lg:left-auto lg:right-8 lg:top-1/2 lg:translate-x-0 lg:-translate-y-1/2 lg:flex-col lg:gap-4">
          {BEATS.map((b, i) => (
            <button key={b.label} type="button" onClick={() => goTo(i)} aria-label={`Go to: ${b.title}`} aria-current={beat === i ? "step" : undefined}
              className="group flex min-h-6 items-center gap-3 bg-transparent p-1 text-left text-ink/55 hover:text-ink">
              <span aria-hidden className={`block h-[3px] rounded-full transition-all duration-500 lg:order-2 ${beat === i ? "w-8 bg-brand" : "w-4 bg-ink/25 group-hover:bg-ink/60"}`} />
              <span className={`hidden text-[12px] font-medium tracking-[0.12em] uppercase transition-colors lg:order-1 lg:block lg:w-24 lg:text-right ${beat === i ? "text-ink" : ""}`}>{b.label}</span>
            </button>
          ))}
        </nav>

        <a href="#how" className={`absolute bottom-5 left-1/2 z-10 hidden lg:flex min-h-10 -translate-x-1/2 flex-col items-center justify-center gap-1 text-[11px] font-medium tracking-[0.25em] text-muted no-underline transition-opacity duration-500 hover:text-ink hover:no-underline ${started ? "pointer-events-none opacity-0" : "opacity-100"}`}
          tabIndex={started ? -1 : 0}>
          SCROLL <ArrowDown size={14} aria-hidden />
        </a>
      </div>
    </section>
  );
}

/** Reduced motion, no WebGL, or WebGL failed: the turning 2D globe centred on the cream page. */
function StaticHero() {
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
        <p className="mb-0 mt-6 max-w-[32rem] text-[18px] leading-relaxed text-ink/75">{LEAD}</p>
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
