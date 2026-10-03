import { RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { type ConstellationData, useConstellationData } from "@/api/visuals";
import { constellationTakeaway } from "./helpers";
import { useReducedMotion, useSignedIn } from "./hooks";
import { VisualCard } from "./VisualCard";
import "./visuals.css";

const TITLE = "One customer, many records";
const LOOKING = "The same person's records in each system, matched into one customer. An anonymous sample: no names, only systems and match confidence.";

/** One customer's source records drawn as nodes that settle onto the golden ID, then one link on to the proposed
 * next best action. `goldenId` "sample" draws the public, anonymous sample. `framed` adds the Card, title and takeaway. */
export function IdentityConstellation({ goldenId, height = 360, framed = false }: { goldenId: string; height?: number; framed?: boolean }) {
  const q = useConstellationData(goldenId, useSignedIn());
  const wrap = (body: React.ReactNode, takeaway?: string) =>
    framed ? <VisualCard title={TITLE} looking={LOOKING} takeaway={takeaway}>{body}</VisualCard> : <>{body}</>;
  if (q.isLoading) return wrap(<div role="status" style={{ height }} className="grid place-items-center text-[15px] text-muted">Gathering the records…</div>);
  if (q.isError || !q.data || !q.data.records.length) {
    return wrap(<div role="status" style={{ height }} className="grid place-items-center px-6 text-center text-[15px] text-muted">No records to show for this customer yet.</div>);
  }
  return wrap(<ConstellationView data={q.data} height={height} showId={goldenId === "sample" ? undefined : goldenId} />, constellationTakeaway(q.data.records, q.data.action));
}

const hash = (i: number, salt: number) => { const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453; return x - Math.floor(x); };
const split = (label: string) => { const m = label.match(/^(.*?)( record \d+)$/); return m ? [m[1], m[2].trim()] : [label, ""]; };
const pctText = (c: number | null) => (c == null ? "n/a" : `${Math.round(c * 100)}%`);

/** The scene. It is drawn straight away (records loosely scattered and drifting), converges once it scrolls into view,
 * and can be replayed. With reduced motion it is one still, composed frame. */
export function ConstellationView({ data, height = 360, showId }: { data: ConstellationData; height?: number; showId?: string }) {
  const reduced = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(720);
  const [run, setRun] = useState(0);
  const [started, setStarted] = useState(false);
  const [visible, setVisible] = useState(true);
  const [settled, setSettled] = useState(reduced);

  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Play the convergence the first time the scene is on screen.
  useEffect(() => {
    const el = box.current;
    if (!el || typeof IntersectionObserver === "undefined") { setStarted(true); return; }
    const io = new IntersectionObserver(([e]) => { setVisible(e.isIntersecting); if (e.isIntersecting) setStarted(true); }, { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (reduced) { setSettled(true); return; }
    if (!started) return;
    setSettled(false);
    const t = requestAnimationFrame(() => requestAnimationFrame(() => setSettled(true)));
    return () => cancelAnimationFrame(t);
  }, [run, started, reduced, data]);

  const compact = w < 560;
  const n = data.records.length;
  const gold = { x: w * (compact ? 0.64 : 0.5), y: compact ? height * 0.4 : height / 2, r: compact ? 28 : 36 };
  const nba = compact ? { x: gold.x, y: height - 38, w: 150, h: 58 } : { x: w - 92, y: height / 2, w: 150, h: 70 };
  const left = compact ? 44 : Math.min(190, w * 0.2), bulge = compact ? 26 : Math.min(90, w * 0.1);
  const pts = useMemo(() => data.records.map((r, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const y = 34 + t * (height - 80);
    const x = left + bulge * Math.sin(Math.PI * t) * 0.9 + (i % 2) * (compact ? 6 : 16);
    // Before the convergence, each record sits a little off its place (kept inside the box).
    const sx = (hash(i, 1) - 0.5) * (compact ? 24 : 70), sy = Math.max(26 - y, Math.min(height - 40 - y, (hash(i, 2) - 0.5) * 60));
    return { ...r, x, y, sx, sy, d: `M${x},${y} Q${(x + gold.x) / 2},${y + (gold.y - y) * 0.25} ${gold.x - gold.r},${gold.y}` };
  }), [data.records, n, height, compact, left, bulge, gold.x, gold.y, gold.r]);

  const settleMs = reduced ? 0 : 1100, stagger = 90;
  const linkStart = reduced ? 0 : settleMs + 150;
  const actionAt = linkStart + n * stagger + 500;
  const names = new Set(data.records.map((r) => r.system));
  const low = (c: number | null) => c != null && c < 1;

  return (
    <div>
      <div ref={box} className={`relative w-full rounded-[var(--radius-lg)] border border-grey-300/70 ${visible ? "" : "vz-paused"}`}>
        <button type="button" onClick={() => { setStarted(true); setRun((r) => r + 1); }}
          className="absolute right-3 top-3 z-10 inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-[var(--radius-md)] border border-grey-300/70 bg-white px-3 text-[13.5px] font-medium text-ink hover:bg-grey-100">
          <RotateCcw size={13} aria-hidden /> Replay
        </button>
        <svg viewBox={`0 0 ${w} ${height}`} width={w} height={height} className="block h-auto w-full" role="img"
          aria-label={`${n} records from ${names.size} systems are matched into one customer${data.action ? `, and the proposed next best action is ${data.action.label}` : ""}.`}>
          {/* links, drawn once the records have settled */}
          {settled && pts.map((p, i) => {
            const conf = p.confidence;
            const mx = p.x + (gold.x - gold.r - p.x) * 0.62, my = p.y + (gold.y - p.y) * 0.36;
            return (
              <g key={`l${run}-${i}`}>
                <path d={p.d} fill="none" stroke="var(--color-muted)" strokeOpacity={0.7} strokeWidth={1.2 + (conf ?? 0.5) * 1.2}
                  className={reduced ? "" : "vz-draw"} style={{ ["--len" as string]: 400, ["--d" as string]: `${linkStart + i * stagger}ms` }} />
                {!compact && (
                  <g className={reduced ? "" : "vz-fade"} style={{ ["--d" as string]: `${linkStart + i * stagger + 500}ms` }}>
                    <rect x={mx - 19} y={my - 9} width={38} height={18} rx={9} style={{ fill: "white", stroke: low(conf) ? "var(--color-brand)" : "var(--color-grey-300)" }} />
                    <text x={mx} y={my} textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={600} className="tabular" style={{ fill: low(conf) ? "var(--color-brand)" : "var(--color-ink)" }}>{pctText(conf)}</text>
                  </g>
                )}
              </g>
            );
          })}

          {/* golden ID to the proposed next best action */}
          {data.action && settled && (
            <g key={`a${run}`}>
              <path d={compact ? `M${gold.x},${gold.y + gold.r} L${nba.x},${nba.y - nba.h / 2}` : `M${gold.x + gold.r},${gold.y} L${nba.x - nba.w / 2},${nba.y}`} stroke="var(--color-brand)" strokeWidth={2.5} fill="none"
                className={reduced ? "" : "vz-draw"} style={{ ["--len" as string]: 400, ["--d" as string]: `${actionAt}ms` }} />
              <text x={compact ? gold.x + 8 : (gold.x + gold.r + nba.x - nba.w / 2) / 2} y={compact ? (gold.y + gold.r + nba.y - nba.h / 2) / 2 : gold.y - 10} textAnchor={compact ? "start" : "middle"} fontSize={12}
                className={reduced ? "" : "vz-fade"} style={{ fill: "var(--color-muted)", ["--d" as string]: `${actionAt + 400}ms` }}>proposes</text>
            </g>
          )}

          {/* source records: always visible, drifting a little until they settle */}
          {pts.map((p, i) => {
            const [a, b] = split(p.label);
            const line2 = p.sub ?? b;
            const compactLine = [line2, low(p.confidence) ? pctText(p.confidence) : ""].filter(Boolean).join(" · ");
            return (
              <g key={`n${i}`} className="vz-settle" style={{ transform: settled ? "translate(0px,0px)" : `translate(${p.sx}px,${p.sy}px)`, transitionDelay: settled ? `${i * stagger}ms` : "0ms" }}>
                <g className={reduced ? "" : "vz-drift"} style={{ ["--dx" as string]: `${(hash(i, 3) - 0.5) * 5}px`, ["--dy" as string]: `${(hash(i, 4) - 0.5) * 6}px`, ["--d" as string]: `${-hash(i, 5) * 4}s` }}>
                  <circle cx={p.x} cy={p.y} r={compact ? 10 : 12} style={{ fill: "white", stroke: "var(--color-ink)" }} strokeWidth={1.5} />
                  <circle cx={p.x} cy={p.y} r={3.5} style={{ fill: "var(--color-ink)" }} />
                  {compact ? (
                    <>
                      <text x={p.x} y={p.y + 24} textAnchor="middle" fontSize={11} fontWeight={600} style={{ fill: "var(--color-ink)" }}>{a}</text>
                      {compactLine && <text x={p.x} y={p.y + 36} textAnchor="middle" fontSize={10.5} style={{ fill: "var(--color-muted)" }}>{compactLine}</text>}
                    </>
                  ) : (
                    <>
                      <text x={p.x - 22} y={p.y - 1} textAnchor="end" fontSize={13} fontWeight={600} style={{ fill: "var(--color-ink)" }}>{a}</text>
                      {line2 && <text x={p.x - 22} y={p.y + 14} textAnchor="end" fontSize={12} style={{ fill: "var(--color-muted)" }}>{line2}</text>}
                    </>
                  )}
                </g>
              </g>
            );
          })}

          {/* the one customer */}
          <g className="vz-settle" style={{ transform: `scale(${settled ? 1 : 0.85})`, transformOrigin: `${gold.x}px ${gold.y}px`, opacity: settled ? 1 : 0.5, transitionDelay: settled ? "300ms" : "0ms", transitionProperty: "transform, opacity" }}>
            <circle cx={gold.x} cy={gold.y} r={gold.r} style={{ fill: "var(--color-brand)" }} />
            <text x={gold.x} y={gold.y - 4} textAnchor="middle" fontSize={compact ? 10 : 12.5} fontWeight={600} style={{ fill: "white" }}>One</text>
            <text x={gold.x} y={gold.y + 11} textAnchor="middle" fontSize={compact ? 10 : 12.5} fontWeight={600} style={{ fill: "white" }}>customer</text>
          </g>
          {showId && <text x={gold.x} y={gold.y + gold.r + 18} textAnchor="middle" fontSize={12} className="tabular" style={{ fill: "var(--color-muted)" }}>{showId}</text>}

          {/* proposed next best action */}
          {data.action && (
            <g className="vz-settle" style={{ opacity: settled ? 1 : 0, transitionDelay: `${settled && !reduced ? actionAt + 300 : 0}ms`, transitionProperty: "opacity, transform", transform: settled ? "none" : "translateX(12px)" }}>
              <rect x={nba.x - nba.w / 2} y={nba.y - nba.h / 2} width={nba.w} height={nba.h} rx={8} style={{ fill: "white", stroke: "var(--color-brand)" }} strokeWidth={1.5} />
              <text x={nba.x} y={nba.y - 14} textAnchor="middle" fontSize={compact ? 10.5 : 11.5} style={{ fill: "var(--color-muted)" }}>Proposed next action</text>
              <text x={nba.x} y={nba.y + 6} textAnchor="middle" fontSize={compact ? 12 : 14} fontWeight={600} style={{ fill: "var(--color-ink)" }}>{data.action.label}</text>
              {data.action.channel && <text x={nba.x} y={nba.y + 24} textAnchor="middle" fontSize={compact ? 11 : 12} style={{ fill: "var(--color-muted)" }}>by {data.action.channel}</text>}
            </g>
          )}
        </svg>
      </div>
      <p className="mb-0 mt-3 text-[13px] text-muted">The percentage on each line is how sure the match is. Anything below 100% is checked by a person.</p>
    </div>
  );
}
