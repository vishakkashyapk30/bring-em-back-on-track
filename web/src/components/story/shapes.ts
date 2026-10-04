import { geoAzimuthalEqualArea, geoDistance, geoEquirectangular, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry, MultiPolygon, Polygon } from "geojson";
import { CatmullRomCurve3, Vector3 } from "three";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";
import indiaOfficial from "@/assets/india-official.geo.json";

/* The four shapes of the hero story, as one target position (plus colour, alpha and size) per particle per shape:
 *   A: a dotted Earth (land in ink, Canada in red, the ocean as a faint shell)
 *   B: the map of Canada (the same Canadian dots, now flat, with a crisp outline and the neighbours dimmed)
 *   C: a ribbon road that climbs away from Canada, red at the start ("behind") to teal at the end ("back on track")
 *   D: one customer card (outline, avatar, a few lines, a status chip, a progress track and a next-step button)
 * Drawn in brand red, ink and teal on the cream page (normal blending, no dark background).
 * Particles that a shape does not need drift to a faint dust field around it, so nothing pops in or out.
 * Built once, on the client, from the map data the old globe already ships (no API, no numbers from the data).
 * The land comes from the world land outline with India's official boundary painted on top (as the Globe does), and no
 * international borders are drawn except Canada's. */

export type Rgb = [number, number, number];
export interface Palette { red: Rgb; redSoft: Rgb; ink: Rgb; teal: Rgb; tealSoft: Rgb }

export const GLOBE_R = 1.2;
export const CANADA_LON = -96, CANADA_LAT = 60;
/** The road, in world units. It starts in the middle of the Canada map (which sits at the origin) and climbs away. */
export const ROAD_POINTS: [number, number, number][] = [
  [0, -0.15, 0.15], [0.6, 0.05, -1.3], [-0.45, 0.55, -2.9], [0.45, 1.15, -4.5], [-0.12, 1.75, -6.0], [0, 2.1, -7.0],
];
export const CARD_CENTER: [number, number, number] = [0, 2.7, -7.6];
export const CARD_W = 2.3, CARD_H = 1.45;

export interface Story {
  count: number;
  pos: Float32Array[]; // 4 x (count * 3)
  col: Float32Array[]; // 4 x (count * 3)
  alpha: Float32Array; // count * 4
  size: Float32Array; // count * 4
  rand: Float32Array; // count * 4: per-transition delay (x, y, z) and a free random (w)
}

const topo = world as unknown as Topology;
const land = feature(topo, topo.objects.land) as unknown as Feature<Geometry>;
const countries = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry>;
const canada = countries.features.find((f) => String(f.id) === "124") as Feature<Geometry>;
const india = indiaOfficial as unknown as Feature<Geometry>;

/** Small seeded generator, so the picture is the same on every visit. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Equirectangular masks of land and of Canada, drawn once on small canvases and read back as bytes. */
function masks() {
  const W = 1024, H = 512;
  const draw = (fs: Feature<Geometry>[]) => {
    const cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const ctx = cv.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("no 2d canvas");
    const path = geoPath(geoEquirectangular().scale(W / (2 * Math.PI)).translate([W / 2, H / 2]), ctx);
    ctx.fillStyle = "#fff"; // mask only, never shown
    for (const f of fs) { ctx.beginPath(); path(f); ctx.fill(); }
    return ctx.getImageData(0, 0, W, H).data;
  };
  const landPx = draw([land, india]), canadaPx = draw([canada]);
  const at = (px: Uint8ClampedArray, lon: number, lat: number) => {
    const x = Math.min(W - 1, Math.max(0, Math.floor(((lon + 180) / 360) * W)));
    const y = Math.min(H - 1, Math.max(0, Math.floor(((90 - lat) / 180) * H)));
    return px[(y * W + x) * 4] > 127;
  };
  return { isLand: (lon: number, lat: number) => at(landPx, lon, lat), isCanada: (lon: number, lat: number) => at(canadaPx, lon, lat) };
}

const DEG = Math.PI / 180;
const sphere = (lon: number, lat: number, r = GLOBE_R): [number, number, number] =>
  [r * Math.cos(lat * DEG) * Math.sin(lon * DEG), r * Math.sin(lat * DEG), r * Math.cos(lat * DEG) * Math.cos(lon * DEG)];

/** Evenly spread points on the sphere (a Fibonacci lattice) that pass `keep`, about `target` of them. */
function lattice(target: number, keep: (lon: number, lat: number) => boolean, rand: () => number): [number, number][] {
  const run = (m: number) => {
    const out: [number, number][] = [];
    const ga = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < m; i++) {
      const y = 1 - ((i + 0.5) / m) * 2;
      const lat = Math.asin(y) / DEG;
      const lon = ((((i * ga) / DEG) % 360) + 360) % 360 - 180;
      if (keep(lon, lat)) out.push([lon, lat]);
    }
    return out;
  };
  const probe = run(20000).length / 20000;
  const pts = run(Math.max(target, Math.round(target / Math.max(probe, 0.01))));
  while (pts.length > target) pts.splice(Math.floor(rand() * pts.length), 1);
  while (pts.length < target && pts.length) pts.push(pts[Math.floor(rand() * pts.length)]);
  return pts;
}

/** Points spread along the outline of a (multi)polygon by length, in degrees. */
function outline(f: Feature<Geometry>, n: number, rand: () => number): [number, number][] {
  const g = f.geometry as Polygon | MultiPolygon;
  const rings = g.type === "Polygon" ? g.coordinates : g.coordinates.flat();
  const segs: { a: number[]; b: number[]; len: number }[] = [];
  let total = 0;
  for (const ring of rings) for (let i = 1; i < ring.length; i++) {
    const a = ring[i - 1], b = ring[i];
    const len = Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * DEG), b[1] - a[1]);
    segs.push({ a, b, len }); total += len;
  }
  const out: [number, number][] = [];
  for (let k = 0; k < n; k++) {
    let d = ((k + rand() * 0.6) / n) * total, s = 0;
    while (s < segs.length - 1 && d > segs[s].len) { d -= segs[s].len; s++; }
    const { a, b, len } = segs[s], t = len ? d / len : 0;
    out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
  }
  return out;
}

export function buildStory(count: number, pal: Palette): Story {
  const rand = rng(20261004);
  const { isLand, isCanada } = masks();
  const pos = [0, 1, 2, 3].map(() => new Float32Array(count * 3));
  const col = [0, 1, 2, 3].map(() => new Float32Array(count * 3));
  const alpha = new Float32Array(count * 4), size = new Float32Array(count * 4), rnd = new Float32Array(count * 4);

  const set = (s: number, i: number, p: ArrayLike<number>, c: Rgb, a: number, z: number) => {
    pos[s].set([p[0], p[1], p[2]], i * 3); col[s].set(c, i * 3); alpha[i * 4 + s] = a; size[i * 4 + s] = z;
  };
  const dust = (s: number, i: number, c: [number, number, number], rMin: number, rMax: number) => {
    const u = rand() * 2 - 1, th = rand() * Math.PI * 2, r = rMin + Math.pow(rand(), 0.7) * (rMax - rMin), q = Math.sqrt(1 - u * u);
    set(s, i, [c[0] + r * q * Math.cos(th), c[1] + r * u * 0.6, c[2] + r * q * Math.sin(th) - 1], pal.ink, 0.04 + rand() * 0.08, 0.008 + rand() * 0.006);
  };
  const mixc = (a: Rgb, b: Rgb, t: number): Rgb => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

  // How the particles are split on the globe.
  const nOutline = Math.round(count * 0.09), nCanada = Math.round(count * 0.17), nOcean = Math.round(count * 0.16);
  const nLand = count - nOutline - nCanada - nOcean;
  const canadaInside: [number, number][] = [];
  while (canadaInside.length < nCanada) { // area-uniform random points inside Canada
    const lon = -141 + rand() * 89, lat = Math.asin(Math.sin(41.5 * DEG) + rand() * (Math.sin(83.5 * DEG) - Math.sin(41.5 * DEG))) / DEG;
    if (isCanada(lon, lat)) canadaInside.push([lon, lat]);
  }
  const ll: { lon: number; lat: number; kind: "outline" | "canada" | "land" | "ocean" }[] = [
    ...outline(canada, nOutline, rand).map(([lon, lat]) => ({ lon, lat, kind: "outline" as const })),
    ...canadaInside.map(([lon, lat]) => ({ lon, lat, kind: "canada" as const })),
    ...lattice(nLand, (lo, la) => isLand(lo, la) && !isCanada(lo, la), rand).map(([lon, lat]) => ({ lon, lat, kind: "land" as const })),
    ...lattice(nOcean, (lo, la) => !isLand(lo, la), rand).map(([lon, lat]) => ({ lon, lat, kind: "ocean" as const })),
  ].slice(0, count);
  while (ll.length < count) ll.push({ lon: rand() * 360 - 180, lat: rand() * 180 - 90, kind: "ocean" });

  // Shape B: an equal-area map centred on Canada, so the globe "unrolls" into the map with every dot in its own place.
  const proj = geoAzimuthalEqualArea().rotate([-CANADA_LON, -CANADA_LAT]).scale(1).translate([0, 0]);
  const [[x0, y0], [x1, y1]] = geoPath(proj).bounds(canada);
  const MAP_W = 2.4, k = MAP_W / (x1 - x0), cx = (x0 + x1) / 2, cy = (y0 + y1) / 2 + 0.04 / k;
  const tilt = -0.22, ct = Math.cos(tilt), st = Math.sin(tilt);
  const flat = (lon: number, lat: number): [number, number, number] | null => {
    if (geoDistance([lon, lat], [CANADA_LON, CANADA_LAT]) > 1.25) return null;
    const p = proj([lon, lat]);
    if (!p) return null;
    const X = (p[0] - cx) * k, Y = -(p[1] - cy) * k;
    return [X, Y * ct, Y * st];
  };

  // Shape C: the road.
  const road = new CatmullRomCurve3(ROAD_POINTS.map((p) => new Vector3(...p)), false, "catmullrom", 0.5);
  const up = new Vector3(0, 1, 0), side = new Vector3(), nrm = new Vector3();
  const roadIdx = new Set<number>();
  const order = Array.from({ length: count }, (_, i) => i).sort(() => rand() - 0.5);
  order.slice(0, Math.round(count * 0.74)).forEach((i) => roadIdx.add(i));

  // Shape D: the card.
  const cardIdx = new Set<number>(order.slice(Math.round(count * 0.12), Math.round(count * 0.12) + Math.round(count * 0.7)));
  const cardPts = cardShape(cardIdx.size, pal, rand);

  let cardK = 0;
  for (let i = 0; i < count; i++) {
    const { lon, lat, kind } = ll[i];
    // A: the globe
    if (kind === "outline") set(0, i, sphere(lon, lat, GLOBE_R * 1.004), mixc(pal.redSoft, pal.ink, 0.35), 0.95, 0.017);
    else if (kind === "canada") set(0, i, sphere(lon, lat), mixc(pal.red, pal.redSoft, rand() * 0.6), 0.85, 0.016 + rand() * 0.006);
    else if (kind === "land") set(0, i, sphere(lon, lat), pal.ink, 0.28 + rand() * 0.2, 0.013 + rand() * 0.005);
    else set(0, i, sphere(lon, lat, GLOBE_R * 0.995), mixc(pal.ink, pal.redSoft, 0.4), 0.05, 0.01);

    // B: Canada, flat
    const f = flat(lon, lat);
    if (kind === "outline" && f) set(1, i, [f[0], f[1], f[2] + 0.004], pal.ink, 0.95, 0.017);
    else if (kind === "canada" && f) set(1, i, [f[0], f[1], f[2] + (rand() - 0.5) * 0.02], mixc(pal.red, pal.redSoft, rand() * 0.7), 0.8, 0.018 + rand() * 0.008);
    else if (kind === "land" && f && Math.abs(f[0]) < 2.4 && Math.abs(f[1]) < 1.7) set(1, i, f, pal.ink, 0.16, 0.013);
    else dust(1, i, [0, 0, 0], 2.2, 6);
    rnd[i * 4] = (kind === "canada" || kind === "outline" ? 0.15 : 0.35) * rand() + (kind === "ocean" ? 0.6 : 0.2) * rand();

    // C: the road
    if (roadIdx.has(i)) {
      const r = rand();
      const t = Math.pow(rand(), 0.85);
      const p = road.getPointAt(t), tan = road.getTangentAt(t);
      side.crossVectors(tan, up).normalize(); nrm.crossVectors(side, tan).normalize();
      const half = 0.36 - 0.12 * t;
      let u: number, a: number, z: number;
      if (r < 0.36) { u = (rand() < 0.5 ? -1 : 1) * (1 - rand() * 0.06); a = 0.85; z = 0.016; } // the two edges
      else if (r < 0.44) { u = (rand() - 0.5) * 0.05; a = (t * 26) % 1 < 0.55 ? 0.7 : 0.04; z = 0.014; } // dashed centre line
      else { u = rand() * 2 - 1; a = 0.18 + rand() * 0.18; z = 0.011 + rand() * 0.005; } // the surface
      const lift = (rand() - 0.5) * 0.015;
      const c = mixc(mixc(pal.red, pal.redSoft, 0.35), pal.tealSoft, smooth(0.12, 0.88, t));
      set(2, i, [p.x + side.x * u * half + nrm.x * lift, p.y + side.y * u * half + nrm.y * lift, p.z + side.z * u * half + nrm.z * lift], c, a, z);
      rnd[i * 4 + 1] = t * 0.85 + rand() * 0.15; // flows out of Canada: the start of the road fills first
    } else {
      const m = road.getPointAt(0.55);
      dust(2, i, [m.x, m.y, m.z], 2.4, 7);
      rnd[i * 4 + 1] = rand();
    }

    // D: the card
    if (cardIdx.has(i)) {
      const c = cardPts[cardK++];
      set(3, i, [CARD_CENTER[0] + c.x, CARD_CENTER[1] + c.y, CARD_CENTER[2] + c.z], c.c, c.a, c.s);
      rnd[i * 4 + 2] = 0.15 + 0.85 * rand();
    } else {
      dust(3, i, CARD_CENTER, 2.2, 6);
      rnd[i * 4 + 2] = rand();
    }
    rnd[i * 4 + 3] = rand();
  }
  return { count, pos, col, alpha, size: size, rand: rnd };
}

function smooth(a: number, b: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

interface CardPt { x: number; y: number; z: number; c: Rgb; a: number; s: number }

/** One customer card, as points on a plane: no real data, just the silhouette of a record. */
function cardShape(n: number, pal: Palette, rand: () => number): CardPt[] {
  const W = CARD_W, H = CARD_H, R = 0.16;
  const out: CardPt[] = [];
  const jz = () => (rand() - 0.5) * 0.012;
  const mixc = (a: Rgb, b: Rgb, t: number): Rgb => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

  /** A point on the edge of a rounded rectangle centred at (cx, cy), uniformly by length. */
  const rrEdge = (cx: number, cy: number, w: number, h: number, r: number): [number, number] => {
    const sw = w - 2 * r, sh = h - 2 * r, arc = (Math.PI / 2) * r, per = 2 * sw + 2 * sh + 4 * arc;
    let d = rand() * per;
    const corner = (qx: number, qy: number, a0: number, dd: number): [number, number] => {
      const a = a0 + dd / r;
      return [cx + qx + Math.cos(a) * r, cy + qy + Math.sin(a) * r];
    };
    if ((d -= sw) < 0) return [cx - sw / 2 + d + sw, cy + h / 2];
    if ((d -= arc) < 0) return corner(sw / 2, sh / 2, 0, d + arc);
    if ((d -= sh) < 0) return [cx + w / 2, cy - sh / 2 + (d + sh)];
    if ((d -= arc) < 0) return corner(sw / 2, -sh / 2, -Math.PI / 2, d + arc);
    if ((d -= sw) < 0) return [cx - sw / 2 + (d + sw), cy - h / 2];
    if ((d -= arc) < 0) return corner(-sw / 2, -sh / 2, Math.PI, d + arc);
    if ((d -= sh) < 0) return [cx - w / 2, cy - sh / 2 + (d + sh)];
    return corner(-sw / 2, sh / 2, Math.PI / 2, Math.min(arc, d));
  };
  const rrInside = (cx: number, cy: number, w: number, h: number, r: number): [number, number] => {
    for (;;) {
      const x = (rand() - 0.5) * w, y = (rand() - 0.5) * h;
      const dx = Math.max(0, Math.abs(x) - (w / 2 - r)), dy = Math.max(0, Math.abs(y) - (h / 2 - r));
      if (dx * dx + dy * dy <= r * r) return [cx + x, cy + y];
    }
  };
  const bar = (x0: number, x1: number, y: number, th: number): [number, number] => rrInside((x0 + x1) / 2, y, x1 - x0, th, th / 2);

  const parts: [number, () => CardPt][] = [
    [0.2, () => { const [x, y] = rrEdge(0, 0, W, H, R); return { x, y, z: jz(), c: pal.ink, a: 0.9, s: 0.016 }; }],
    [0.13, () => { const [x, y] = rrInside(0, 0, W - 0.04, H - 0.04, R); return { x, y, z: jz() - 0.01, c: pal.ink, a: 0.07, s: 0.012 }; }],
    [0.07, () => { const a = rand() * Math.PI * 2; return { x: -0.78 + Math.cos(a) * 0.2, y: 0.35 + Math.sin(a) * 0.2, z: jz(), c: pal.redSoft, a: 0.95, s: 0.016 }; }],
    [0.06, () => { // a head and shoulders inside the avatar
      if (rand() < 0.45) { const a = rand() * Math.PI * 2, r = Math.sqrt(rand()) * 0.065; return { x: -0.78 + Math.cos(a) * r, y: 0.4 + Math.sin(a) * r, z: jz(), c: mixc(pal.red, pal.redSoft, 0.5), a: 0.75, s: 0.014 }; }
      for (;;) { const x = (rand() - 0.5) * 0.24, y = rand() * 0.11; if ((x * x) / 0.0144 + (y * y) / 0.0121 <= 1 && Math.hypot(x, 0.22 + y - 0.35) < 0.19) return { x: -0.78 + x, y: 0.22 + y, z: jz(), c: mixc(pal.red, pal.redSoft, 0.5), a: 0.75, s: 0.014 }; }
    }],
    [0.1, () => { const [x, y] = bar(-0.44, 0.38, 0.43, 0.08); return { x, y, z: jz(), c: pal.ink, a: 0.85, s: 0.015 }; }],
    [0.06, () => { const [x, y] = bar(-0.44, 0.05, 0.27, 0.055); return { x, y, z: jz(), c: pal.ink, a: 0.45, s: 0.013 }; }],
    [0.06, () => { const [x, y] = bar(0.56, 0.95, 0.43, 0.11); return { x, y, z: jz(), c: pal.tealSoft, a: 0.85, s: 0.015 }; }],
    [0.11, () => { // the progress track, red to teal, filled most of the way
      const t = rand(), x = -0.95 + t * 1.9, y = 0.0 + (rand() - 0.5) * 0.05, on = t < 0.78;
      return { x, y, z: jz(), c: on ? mixc(mixc(pal.red, pal.redSoft, 0.4), pal.tealSoft, smooth(0.1, 0.78, t)) : pal.ink, a: on ? 0.9 : 0.18, s: 0.014 };
    }],
    [0.06, () => { const [x, y] = bar(-0.95, 0.4, -0.24, 0.05); return { x, y, z: jz(), c: pal.ink, a: 0.4, s: 0.012 }; }],
    [0.05, () => { const [x, y] = bar(-0.95, 0.05, -0.37, 0.05); return { x, y, z: jz(), c: pal.ink, a: 0.32, s: 0.012 }; }],
    [0.1, () => { const [x, y] = rrInside(0.62, -0.5, 0.62, 0.2, 0.06); return { x, y, z: jz() + 0.01, c: mixc(pal.red, pal.redSoft, 0.25), a: 0.9, s: 0.015 }; }],
  ];
  const total = parts.reduce((s, [w]) => s + w, 0);
  for (const [w, make] of parts) for (let i = 0, m = Math.round((w / total) * n); i < m && out.length < n; i++) out.push(make());
  while (out.length < n) out.push(parts[0][1]());
  return out;
}
