import { geoDistance, geoGraticule, geoOrthographic, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { useEffect, useRef } from "react";
import { feature, mesh } from "topojson-client";
import type { Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";
import indiaOfficial from "@/assets/india-official.geo.json";

/* The hero globe: a turning wireframe on a dark sky, drawn on one canvas.
 * Cost control, because it sits on the first screen:
 * - Loaded lazily by the landing page, so the map data is not in the first download.
 * - All land is ONE path and all borders are ONE stroke; the globe's fill and rim are baked once per size.
 * - 24 frames a second, and the loop measures its own draw time: slow machine -> 15 fps, very slow -> a still picture.
 * - It does nothing when scrolled out of view, when the tab is hidden, or for people who prefer reduced motion.
 * Colours come from the existing tokens (ink, cream, grey, brand red); `tone` picks the dark band or the light page. */

const topo = world as unknown as Topology;
const land = feature(topo, topo.objects.land) as unknown as Feature<Geometry>;
const countries = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry>;
const canada = countries.features.find((f) => String(f.id) === "124") as Feature<Geometry>; // ISO 3166-1 numeric
const borders = mesh(topo, topo.objects.countries as never, (a, b) => a !== b);
// India is drawn from the "India point of view" boundary (Natural Earth, public domain): Jammu and Kashmir, Ladakh,
// Gilgit-Baltistan and Aksai Chin inside India, as on the Survey of India map. It is painted over the plain world map,
// so the world map's own version of that border never shows through.
const india = indiaOfficial as unknown as Feature<Geometry>;
const graticule = geoGraticule().step([15, 15])();

const CANADA_CITIES: [number, number][] = [
  [-123.1, 49.3], [-113.5, 53.5], [-97.1, 49.9], [-79.4, 43.7], [-75.7, 45.4], [-73.6, 45.5], [-63.6, 44.6],
]; // Vancouver, Edmonton, Winnipeg, Toronto, Ottawa, Montréal, Halifax
const INDIA_CITIES: [number, number][] = [[77.2, 28.6], [72.9, 19.1], [77.6, 13.0], [78.5, 17.4], [80.3, 13.1]];
// Delhi, Mumbai, Bengaluru, Hyderabad, Chennai
const ARC = { type: "LineString", coordinates: [[77.2, 28.6], [-79.4, 43.7]] } as const; // Delhi to Toronto

const TILT = -22; // look down on the northern hemisphere
const CANADA_LON = -96, INDIA_LON = 80;
const wrap = (d: number) => ((d + 540) % 360) - 180;

export function Globe({ className = "", tone = "light" }: { className?: string; tone?: "dark" | "light" }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = box.current, cv = canvas.current;
    const ctx = cv?.getContext("2d", { alpha: true });
    if (!el || !cv || !ctx) return;

    const css = getComputedStyle(document.documentElement);
    const token = (n: string, d: string) => css.getPropertyValue(n).trim() || d;
    const ink = token("--color-ink", "#191a23"), cream = token("--color-cream", "#f5f2eb"), grey = token("--color-grey-300", "#d9d9de");
    // Dark band: light warm-grey linework on ink, one soft red (the on-dark red). Light page: ink linework, brand red.
    const P = tone === "dark"
      ? { line: cream, land: cream, landA: 0.13, lineA: 0.55, grat: cream, gratA: 0.09, ball: "rgba(255,255,255,0.035)", red: token("--color-brand-300", "#f28b9b"), city: cream }
      : { line: ink, land: grey, landA: 0.55, lineA: 0.45, grat: ink, gratA: 0.1, ball: "rgba(255,255,255,0.9)", red: token("--color-brand", "#a71f3e"), city: ink };
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const projection = geoOrthographic().clipAngle(90).precision(1.2);
    const path = geoPath(projection, ctx);
    let base: HTMLCanvasElement | null = null, rim: HTMLCanvasElement | null = null;
    let lon = INDIA_LON - 45, size = 0, dpr = 1, r = 0;
    let visible = true, dragging = false, lastX = 0, resumeAt = 0, raf = 0, lastTick = 0, lastDraw = 0;
    let fps = 24, drawMs = 4, still = reduced;

    /** The parts that never change, drawn once per size: the dark ball with a faint inner glow, and its rim. */
    const bake = () => {
      const px = Math.round(size * dpr), c = px / 2, rr = r * dpr;
      const make = () => { const k = document.createElement("canvas"); k.width = px; k.height = px; return k; };
      base = make(); rim = make();
      const b = base.getContext("2d")!, t = rim.getContext("2d")!;
      b.fillStyle = P.ball; b.beginPath(); b.arc(c, c, rr, 0, Math.PI * 2); b.fill();
      t.strokeStyle = P.line; t.globalAlpha = 0.4; t.lineWidth = 1 * dpr; t.beginPath(); t.arc(c, c, rr, 0, Math.PI * 2); t.stroke();
    };

    const resize = () => {
      size = Math.round(el.getBoundingClientRect().width);
      if (!size) return;
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      cv.width = Math.round(size * dpr); cv.height = Math.round(size * dpr);
      cv.style.width = `${size}px`; cv.style.height = `${size}px`;
      r = (size / 2) * 0.94;
      projection.translate([size / 2, size / 2]).scale(r);
      bake(); draw(performance.now());
    };

    function draw(_now: number) {
      if (!base || !rim) return;
      const t0 = performance.now();
      projection.rotate([-lon, TILT, 0]);
      ctx!.setTransform(1, 0, 0, 1, 0, 0);
      ctx!.clearRect(0, 0, cv!.width, cv!.height);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx!.setTransform(1, 0, 0, 1, 0, 0); ctx!.drawImage(base, 0, 0); ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      ctx!.beginPath(); path(graticule); ctx!.strokeStyle = P.grat; ctx!.globalAlpha = P.gratA; ctx!.lineWidth = 0.6; ctx!.stroke(); ctx!.globalAlpha = 1;
      ctx!.beginPath(); path(land); ctx!.fillStyle = P.land; ctx!.globalAlpha = P.landA; ctx!.fill();
      ctx!.globalAlpha = P.lineA; ctx!.strokeStyle = P.line; ctx!.lineWidth = 0.6; ctx!.stroke();
      ctx!.beginPath(); path(borders); ctx!.lineWidth = 0.4; ctx!.globalAlpha = P.lineA * 0.5; ctx!.stroke(); ctx!.globalAlpha = 1;
      for (const f of [canada, india]) { // the two countries the story is about: a soft red tint and a crisp red outline
        ctx!.beginPath(); path(f); ctx!.fillStyle = P.red; ctx!.globalAlpha = 0.22; ctx!.fill();
        ctx!.globalAlpha = 1; ctx!.strokeStyle = P.red; ctx!.lineWidth = 1.1; ctx!.stroke();
      }

      // one thin arc, Delhi to Toronto, with a small marker at each end
      ctx!.beginPath(); path(ARC as never); ctx!.strokeStyle = P.red; ctx!.lineWidth = 1.3; ctx!.stroke();
      const facing: [number, number] = [lon, -TILT];
      const mark = (ll: [number, number], rr: number, fill: string) => {
        if (geoDistance(ll, facing) > Math.PI / 2 - 0.05) return;
        const p = projection(ll);
        if (!p) return;
        ctx!.beginPath(); ctx!.arc(p[0], p[1], rr, 0, Math.PI * 2); ctx!.fillStyle = fill; ctx!.fill();
      };
      CANADA_CITIES.forEach((c) => mark(c, 1.6, P.city)); INDIA_CITIES.forEach((c) => mark(c, 1.6, P.city));
      mark([77.2, 28.6], 3.6, P.red); mark([-79.4, 43.7], 3.6, P.red);

      ctx!.setTransform(1, 0, 0, 1, 0, 0); ctx!.drawImage(rim, 0, 0); ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawMs = drawMs * 0.9 + (performance.now() - t0) * 0.1; // smoothed cost of one frame
    }

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - lastDraw < 1000 / fps - 2) return; // frame-rate cap
      const dt = Math.min(now - lastTick || 33, 100); lastTick = now; lastDraw = now;
      if (!dragging && now >= resumeAt) {
        // slow down as Canada or India comes to the middle, so each gets a moment on stage
        const near = Math.min(Math.abs(wrap(lon - CANADA_LON)), Math.abs(wrap(lon - INDIA_LON)));
        lon = wrap(lon + (7 * Math.min(1, Math.max(0.3, near / 35)) * dt) / 1000);
      }
      draw(now);
      if (drawMs > 22) { still = true; stop(); }   // very slow machine: keep a still picture
      else if (drawMs > 10) fps = 15;             // slow machine: fewer frames
    };
    const start = () => { if (!raf && !still && visible) { lastTick = 0; raf = requestAnimationFrame(tick); } };
    const stop = () => { if (raf) cancelAnimationFrame(raf); raf = 0; };

    const onDown = (e: PointerEvent) => { dragging = true; lastX = e.clientX; cv.setPointerCapture(e.pointerId); cv.style.cursor = "grabbing"; };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      lon = wrap(lon - (e.clientX - lastX) * 0.45); lastX = e.clientX;
      if (!raf) draw(performance.now());
    };
    const onUp = () => { dragging = false; resumeAt = performance.now() + 2500; cv.style.cursor = "grab"; };

    const ro = new ResizeObserver(resize); ro.observe(el);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) start(); else stop(); }); io.observe(el);
    const onVis = () => { visible = !document.hidden; if (visible) start(); else stop(); };
    document.addEventListener("visibilitychange", onVis);
    cv.addEventListener("pointerdown", onDown); cv.addEventListener("pointermove", onMove);
    cv.addEventListener("pointerup", onUp); cv.addEventListener("pointercancel", onUp);
    cv.style.cursor = "grab";
    resize();
    start();

    return () => {
      stop(); ro.disconnect(); io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      cv.removeEventListener("pointerdown", onDown); cv.removeEventListener("pointermove", onMove);
      cv.removeEventListener("pointerup", onUp); cv.removeEventListener("pointercancel", onUp);
    };
  }, []);

  return (
    <div ref={box} className={`mx-auto aspect-square w-full [contain:layout_paint] ${className}`} role="img"
      aria-label="A globe that turns slowly. India is tinted red, a thin red line joins Delhi to Toronto, and small dots mark cities in both countries.">
      <canvas ref={canvas} aria-hidden className="globe-in block touch-pan-y select-none" />
    </div>
  );
}
