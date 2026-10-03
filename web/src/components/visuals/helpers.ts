// Pure helpers for the landing visuals: scales, number formats, the table fallback, the Sankey layout and the
// keyboard order between map bubbles. No React in here so they are easy to test.
import type { MapMetric, MetricId, PublicMap } from "@/api/visuals";

export const fmtInt = (n: number | null | undefined) => (n == null ? "n/a" : Math.round(n).toLocaleString("en-CA"));

export function fmtValue(v: number | null | undefined, unit: string): string {
  if (v == null) return "n/a";
  return unit === "%" ? `${v.toFixed(1)}%` : `${v.toFixed(1)} ${unit}`;
}

export function fmtMonth(m: string, long = false): string {
  const [y, mo] = m.split("-").map(Number);
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString("en-CA", { month: long ? "long" : "short", year: long ? "numeric" : "2-digit", timeZone: "UTC" });
}

/** How far a value sits from the national one, in plain words. */
export function versus(v: number | null, national: number | null, unit: string): string {
  if (v == null || national == null) return "n/a";
  const d = v - national;
  if (Math.abs(d) < 0.05) return "same as national";
  const amount = unit === "%" ? `${Math.abs(d).toFixed(1)} points` : Math.abs(d).toFixed(1);
  return `${amount} ${d > 0 ? "above" : "below"} national`;
}

/** Five equal-count classes over a set of values (so the colours stay comparable while the month changes). */
export function quantileBreaks(values: number[], classes = 5): number[] {
  const v = [...values].sort((a, b) => a - b);
  if (!v.length) return Array(classes - 1).fill(0);
  return Array.from({ length: classes - 1 }, (_, k) => v[Math.min(v.length - 1, Math.floor(((k + 1) / classes) * v.length))]);
}

/** Class 0..4 for a value: the number of breaks it is above. */
export const classOf = (v: number, breaks: number[]) => breaks.filter((b) => v > b).length;

export function allValues(m: MapMetric): number[] {
  return Object.values(m.series).flatMap((s) => s.value.filter((x): x is number => x != null));
}

export const radiusFor = (n: number, max: number, rMin = 7, rMax = 36) => rMin + (rMax - rMin) * Math.sqrt(Math.max(0, n) / Math.max(1, max));

export type TableRow = { code: string; name: string; value: number | null; vs: string; n: number | null; top: string | null };

/** The same numbers the map shows, as rows for the "view as table" fallback. Hidden groups come last. */
export function tableRows(map: PublicMap, metric: MetricId, monthIdx: number): TableRow[] {
  const m = map.metrics[metric];
  if (!m) return [];
  const i = m.monthly ? monthIdx : 0;
  const nat = m.national[i] ?? null;
  const rows = map.provinces.map((p) => {
    const s = m.series[p.code];
    const value = s?.value[i] ?? null;
    return { code: p.code, name: p.name, value, vs: versus(value, nat, m.unit), n: s?.n[i] ?? null, top: s?.top[i] ?? null };
  });
  return rows.sort((a, b) => (b.value ?? -1) - (a.value ?? -1) || a.name.localeCompare(b.name));
}

/** Push overlapping bubbles apart a little (they are anchored to real places, so only a few small nudges). */
export function relax<T extends { x: number; y: number; r: number }>(pts: T[], pad = 2, rounds = 40): T[] {
  const p = pts.map((q) => ({ ...q }));
  for (let k = 0; k < rounds; k++) {
    let moved = false;
    for (let i = 0; i < p.length; i++) {
      for (let j = i + 1; j < p.length; j++) {
        const dx = p[j].x - p[i].x, dy = p[j].y - p[i].y;
        const d = Math.hypot(dx, dy) || 0.01;
        const need = p[i].r + p[j].r + pad;
        if (d < need) {
          const push = (need - d) / 2, ux = dx / d, uy = dy / d;
          p[i].x -= ux * push; p[i].y -= uy * push; p[j].x += ux * push; p[j].y += uy * push;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  return p;
}

export type Dir = "left" | "right" | "up" | "down";

/** The nearest point in the pressed arrow's direction, or null when there is none. */
export function nextInDirection(from: string, pts: { code: string; x: number; y: number }[], dir: Dir): string | null {
  const a = pts.find((p) => p.code === from);
  if (!a) return pts[0]?.code ?? null;
  let best: { code: string; score: number } | null = null;
  for (const p of pts) {
    if (p.code === from) continue;
    const dx = p.x - a.x, dy = p.y - a.y;
    const along = dir === "right" ? dx : dir === "left" ? -dx : dir === "down" ? dy : -dy;
    const across = dir === "left" || dir === "right" ? Math.abs(dy) : Math.abs(dx);
    if (along <= 1) continue;
    const score = along + 2 * across; // prefer bubbles that are straight ahead
    if (!best || score < best.score) best = { code: p.code, score };
  }
  return best?.code ?? null;
}

// ---- Sankey layout -------------------------------------------------------------------------------------------

export type SNode = { id: string; col: number; label: string; value: number };
export type SLink = { source: string; target: string; value: number };
export type PlacedNode<N extends SNode = SNode> = N & { x: number; y: number; h: number };
export type PlacedLink = SLink & { d: string; width: number; y0: number; y1: number };

export function layoutSankey<N extends SNode>(
  nodes: N[], links: SLink[], opts: { width: number; height: number; nodeWidth?: number; gap?: number; minH?: number; padX?: [number, number] },
): { nodes: PlacedNode<N>[]; links: PlacedLink[]; scale: number } {
  const { width, height, nodeWidth = 14, gap = 12, minH = 24, padX = [0, 0] } = opts;
  const cols = Math.max(...nodes.map((n) => n.col)) + 1;
  const byCol: N[][] = Array.from({ length: cols }, () => []);
  nodes.forEach((n) => byCol[n.col].push(n));
  // One scale for the whole chart, small enough that the busiest column (with its minimum node heights) still fits.
  let scale = Infinity;
  for (const c of byCol) {
    const total = c.reduce((a, n) => a + n.value, 0) || 1;
    let k = (height - gap * (c.length - 1)) / total;
    for (let i = 0; i < 6; i++) {
      const extra = c.reduce((a, n) => a + Math.max(0, minH - n.value * k), 0);
      k = Math.max(0, (height - gap * (c.length - 1) - extra) / total);
    }
    scale = Math.min(scale, k);
  }
  const x0 = padX[0], span = width - padX[0] - padX[1] - nodeWidth;
  const placed = new Map<string, PlacedNode<N>>();
  byCol.forEach((c, ci) => {
    const hs = c.map((n) => Math.max(minH, n.value * scale));
    let y = (height - (hs.reduce((a, b) => a + b, 0) + gap * (c.length - 1))) / 2;
    c.forEach((n, i) => {
      placed.set(n.id, { ...n, x: x0 + (cols > 1 ? (span * ci) / (cols - 1) : 0), y, h: hs[i] });
      y += hs[i] + gap;
    });
  });
  const outCur = new Map<string, number>(), inCur = new Map<string, number>();
  const nodeOrder = (id: string) => placed.get(id)!.y;
  const sorted = [...links].sort((a, b) => nodeOrder(a.target) - nodeOrder(b.target) || nodeOrder(a.source) - nodeOrder(b.source));
  const outSum = new Map<string, number>(), inSum = new Map<string, number>();
  sorted.forEach((l) => {
    outSum.set(l.source, (outSum.get(l.source) ?? 0) + l.value * scale);
    inSum.set(l.target, (inSum.get(l.target) ?? 0) + l.value * scale);
  });
  const out: PlacedLink[] = sorted.map((l) => {
    const s = placed.get(l.source)!, t = placed.get(l.target)!;
    const w = Math.max(0.6, l.value * scale);
    const so = outCur.get(l.source) ?? (s.h - (outSum.get(l.source) ?? 0)) / 2;
    const to = inCur.get(l.target) ?? (t.h - (inSum.get(l.target) ?? 0)) / 2;
    outCur.set(l.source, so + l.value * scale); inCur.set(l.target, to + l.value * scale);
    const y0 = s.y + so + (l.value * scale) / 2, y1 = t.y + to + (l.value * scale) / 2;
    const xa = s.x + nodeWidth, xb = t.x, mx = (xa + xb) / 2;
    return { ...l, width: w, y0, y1, d: `M${xa},${y0} C${mx},${y0} ${mx},${y1} ${xb},${y1}` };
  });
  return { nodes: [...placed.values()], links: out, scale };
}

/** Every link on a path that runs through `id`: upstream to the start and downstream to the end. */
export function pathThrough(id: string, links: SLink[]): Set<string> {
  const key = (l: SLink) => `${l.source}>${l.target}`;
  const hit = new Set<string>();
  const walk = (start: string, dir: "up" | "down") => {
    const q = [start], seen = new Set<string>([start]);
    while (q.length) {
      const cur = q.shift()!;
      for (const l of links) {
        const next = dir === "down" ? (l.source === cur ? l.target : null) : l.target === cur ? l.source : null;
        if (next == null) continue;
        hit.add(key(l));
        if (!seen.has(next)) { seen.add(next); q.push(next); }
      }
    }
  };
  walk(id, "down"); walk(id, "up");
  return hit;
}
export const linkKey = (l: SLink) => `${l.source}>${l.target}`;

// ---- Plain-English takeaways ------------------------------------------------------------------------------------
// One sentence per visual, computed from the numbers on screen (so it can never disagree with the picture).

/** "1 in 3" for a percentage, or null when it is zero or too close to everything to say it that way. */
export function oneIn(pct: number): string | null {
  if (!(pct > 0)) return null;
  const n = Math.round(100 / pct);
  return n >= 2 ? `1 in ${n}` : null;
}

const SUPERLATIVE: Record<MetricId, string> = {
  broken_ptp_rate: "the highest share of broken promises",
  hardship_rate: "the highest share of hardship cases",
  open_cases: "the most open cases",
  promises_at_risk: "the most promises at risk",
};

/** The province standing out on the current view, in one sentence. Null when no province has a visible value. */
export function mapTakeaway(map: PublicMap, metric: MetricId, monthIdx: number): string | null {
  const m = map.metrics[metric];
  if (!m) return null;
  const top = tableRows(map, metric, monthIdx).find((r) => r.value != null);
  if (!top || top.value == null) return null;
  const i = m.monthly ? monthIdx : 0;
  const nat = m.national[i] ?? null;
  const ratio = m.unit === "%" ? oneIn(top.value) : null;
  const value = ratio ? `${ratio} (${fmtValue(top.value, m.unit)})` : fmtValue(top.value, m.unit);
  const against = nat == null ? "" : `, against ${fmtValue(nat, m.unit)} nationally`;
  return `${top.name} has ${SUPERLATIVE[metric]}: ${value}${against}.`;
}

type FlowLike = { total: number; nodes: { id: string; value: number; label: string }[] };

/** What the nightly plan does with the open cases, in one sentence. */
export function flowTakeaway(flow: FlowLike): string {
  const get = (id: string) => flow.nodes.find((n) => n.id === id)?.value;
  const blocked = get("blocked"), person = get("r_individual");
  if (!flow.total || blocked == null) return `${fmtInt(flow.total)} open cases were planned last night.`;
  const share = Math.round((100 * blocked) / flow.total);
  const tail = person != null ? `, and ${fmtInt(person)} are reviewed one by one by a person` : "";
  return `${fmtInt(blocked)} of ${fmtInt(flow.total)} open cases (${share}%) are stopped by policy before any model sees them${tail}.`;
}

type RecordLike = { system: string; confidence: number | null };

/** What the constellation shows: records in, one customer out, and what a person still has to check. */
export function constellationTakeaway(records: RecordLike[], action: { label: string } | null): string {
  const systems = new Set(records.map((r) => r.system)).size;
  const unsure = records.filter((r) => r.confidence != null && r.confidence < 1).length;
  const head = `${records.length} records from ${systems} ${systems === 1 ? "system" : "systems"} match into one customer`;
  const sure = unsure === 0 ? ", all with full confidence" : `; ${unsure} ${unsure === 1 ? "match is" : "matches are"} below 100% and checked by a person`;
  return `${head}${sure}${action ? `, and the proposed next step is ${action.label.toLowerCase()}` : ""}.`;
}

/** Labels for the break points under the legend ramp, e.g. ["12%", "18%", "24%", "30%"]. */
export function legendStops(breaks: number[], unit: string): string[] {
  return breaks.map((b) => (unit === "%" ? `${b.toFixed(0)}%` : b.toFixed(0)));
}
