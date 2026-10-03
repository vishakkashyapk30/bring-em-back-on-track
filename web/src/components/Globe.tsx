import { geoDistance, geoGraticule, geoOrthographic, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { useEffect, useRef } from "react";
import { feature, mesh } from "topojson-client";
import type { Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";
import indiaOfficial from "@/assets/india-official.geo.json";

/* Cost control, because this sits on the first screen:
 * - The component is loaded lazily (see Landing), after the page has painted, so the map data is not in the first download.
 * - All the grey land is ONE path and all borders are ONE stroke (about 3 canvas calls instead of 700).
 * - The ocean, glow and rim never change, so they are drawn once into small off-screen canvases and just copied.
 * - 24 frames a second is plenty for a slow turn, and the loop measures its own draw time: if the machine is slow it
 *   drops to 15 fps, and if it is very slow it stops turning and keeps a still picture.
 * - It does nothing when scrolled out of view, when the tab is hidden, or for people who prefer reduced motion. */

const topo = world as unknown as Topology;
const countries = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry>;
const land = feature(topo, topo.objects.land) as unknown as Feature<Geometry>;
const borders = mesh(topo, topo.objects.countries as never, (a, b) => a !== b);
const byId = (id: string) => countries.features.find((f) => String(f.id) === id) as Feature<Geometry>;
const canada = byId("124"); // ISO 3166-1 numeric
// India is drawn from the "India point of view" boundary (Natural Earth, public domain), which shows Jammu and Kashmir,
// Ladakh, Gilgit-Baltistan and Aksai Chin as part of India, as on the Survey of India map. It is painted over the
// plain world map, so the world map's own version of that border never shows through.
const india = indiaOfficial as unknown as Feature<Geometry>;
const graticule = geoGraticule().step([30, 30])();

const CANADA_CITIES: [number, number][] = [
  [-123.1, 49.3], [-113.5, 53.5], [-114.1, 51.0], [-104.6, 50.4], [-97.1, 49.9],
  [-79.4, 43.7], [-75.7, 45.4], [-73.6, 45.5], [-63.6, 44.6], [-52.7, 47.6],
]; // Vancouver, Edmonton, Calgary, Regina, Winnipeg, Toronto, Ottawa, Montréal, Halifax, St. John's
const INDIA_CITIES: [number, number][] = [[77.2, 28.6], [72.9, 19.1], [77.6, 13.0], [78.5, 17.4], [80.3, 13.1]];
// Delhi, Mumbai, Bengaluru, Hyderabad, Chennai
const ARC = { type: "LineString", coordinates: [[77.2, 28.6], [-79.4, 43.7]] } as const; // Delhi to Toronto

const TILT = -24; // look down on the northern hemisphere
const CANADA_LON = -96, INDIA_LON = 80;
const wrap = (d: number) => ((d + 540) % 360) - 180;

export function Globe() {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = box.current, cv = canvas.current;
    const ctx = cv?.getContext("2d", { alpha: true });
    if (!el || !cv || !ctx) return;

    const css = getComputedStyle(document.documentElement);
    const token = (n: string, d: string) => css.getPropertyValue(n).trim() || d;
    const brand = token("--color-brand", "#a71f3e"), ink = token("--color-ink", "#191a23"), gold = token("--color-gold", "#ffd58a");
    const grey = token("--color-grey-300", "#d9d9de"), soft = token("--color-grey-100", "#f3f3f3");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const projection = geoOrthographic().clipAngle(90).precision(1.2);
    const path = geoPath(projection, ctx);
    let base: HTMLCanvasElement | null = null, rim: HTMLCanvasElement | null = null;
    let lon = CANADA_LON, size = 0, dpr = 1, r = 0;
    let visible = true, dragging = false, lastX = 0, resumeAt = 0, raf = 0, lastTick = 0, lastDraw = 0;
    let fps = 24, drawMs = 4, still = reduced;

    /** The parts that never change, drawn once per size. */
    const bake = () => {
      const px = Math.round(size * dpr), c = px / 2, rr = r * dpr;
      const make = () => { const k = document.createElement("canvas"); k.width = px; k.height = px; return k; };
      base = make(); rim = make();
      const b = base.getContext("2d")!, t = rim.getContext("2d")!;
      const glow = b.createRadialGradient(c, c, rr * 0.92, c, c, rr * 1.2); // the red glow, fully inside the canvas
      glow.addColorStop(0, "rgba(167, 31, 62, 0.20)"); glow.addColorStop(1, "rgba(167, 31, 62, 0)");
      b.fillStyle = glow; b.fillRect(0, 0, px, px);
      const sea = b.createRadialGradient(c - rr * 0.35, c - rr * 0.4, rr * 0.1, c, c, rr);
      sea.addColorStop(0, "#ffffff"); sea.addColorStop(1, soft);
      b.fillStyle = sea; b.beginPath(); b.arc(c, c, rr, 0, Math.PI * 2); b.fill();
      t.strokeStyle = ink; t.globalAlpha = 0.5; t.lineWidth = 1.2 * dpr; t.beginPath(); t.arc(c, c, rr, 0, Math.PI * 2); t.stroke();
    };

    const resize = () => {
      size = Math.round(el.getBoundingClientRect().width);
      if (!size) return;
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      cv.width = Math.round(size * dpr); cv.height = Math.round(size * dpr);
      cv.style.width = `${size}px`; cv.style.height = `${size}px`;
      r = (size / 2) * 0.8; // leave room so the glow is not cut off by the box
      projection.translate([size / 2, size / 2]).scale(r);
      bake(); draw(performance.now());
    };

    function draw(now: number) {
      if (!base || !rim) return;
      const t0 = performance.now();
      projection.rotate([-lon, TILT, 0]);
      ctx!.setTransform(1, 0, 0, 1, 0, 0);
      ctx!.clearRect(0, 0, cv!.width, cv!.height);
      ctx!.drawImage(base, 0, 0);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      ctx!.beginPath(); path(graticule); ctx!.strokeStyle = grey; ctx!.globalAlpha = 0.5; ctx!.lineWidth = 0.6; ctx!.stroke(); ctx!.globalAlpha = 1;
      ctx!.beginPath(); path(land); ctx!.fillStyle = grey; ctx!.fill();
      ctx!.beginPath(); path(borders); ctx!.strokeStyle = "#ffffff"; ctx!.lineWidth = 0.6; ctx!.stroke();
      ctx!.beginPath(); path(canada); ctx!.fillStyle = brand; ctx!.fill(); ctx!.strokeStyle = "#ffffff"; ctx!.lineWidth = 0.9; ctx!.stroke();
      ctx!.beginPath(); path(india); ctx!.fillStyle = gold; ctx!.fill(); ctx!.strokeStyle = ink; ctx!.globalAlpha = 0.6; ctx!.lineWidth = 0.9; ctx!.stroke(); ctx!.globalAlpha = 1;

      // a dashed route from India to Canada, moving gently
      ctx!.save(); ctx!.setLineDash([3, 6]); ctx!.lineDashOffset = -now / 70; ctx!.beginPath(); path(ARC as never);
      ctx!.strokeStyle = ink; ctx!.globalAlpha = 0.55; ctx!.lineWidth = 1.2; ctx!.stroke(); ctx!.restore();

      // city dots with a ring that grows and fades (only the ones facing us)
      const facing: [number, number] = [lon, -TILT];
      const dots = (list: [number, number][], seed: number, tint: string) => list.forEach(([x, y], i) => {
        if (geoDistance([x, y], facing) > Math.PI / 2 - 0.08) return;
        const p = projection([x, y]);
        if (!p) return;
        const phase = (now / 2400 + (i + seed) * 0.37) % 1;
        ctx!.beginPath(); ctx!.arc(p[0], p[1], 3 + phase * size * 0.025, 0, Math.PI * 2);
        ctx!.strokeStyle = `rgba(255, 255, 255, ${0.85 * (1 - phase)})`; ctx!.lineWidth = 1.4; ctx!.stroke();
        ctx!.beginPath(); ctx!.arc(p[0], p[1], 3, 0, Math.PI * 2);
        ctx!.fillStyle = tint; ctx!.fill(); ctx!.strokeStyle = ink; ctx!.lineWidth = 1; ctx!.stroke();
      });
      dots(CANADA_CITIES, 0, "#ffffff"); dots(INDIA_CITIES, 3, brand);

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
    <div ref={box} className="mx-auto aspect-square w-full max-w-[600px] [contain:layout_paint]" role="img"
      aria-label="A globe that turns slowly. Canada is red, India is gold, a dashed line joins them, and dots mark cities in both.">
      <canvas ref={canvas} aria-hidden className="block touch-pan-y select-none" />
    </div>
  );
}
