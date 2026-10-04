import { useEffect, useMemo, useRef, useState } from "react";

import { type PublicFlow, usePublicFlow } from "@/api/visuals";
import { useInView, useReducedMotion, useSignedIn } from "./hooks";
import { flowTakeaway, fmtInt, layoutSankey, linkKey, pathThrough } from "./helpers";
import { VisualCard } from "./VisualCard";
import "./visuals.css";

const W = 1100, H = 500, TOP = 34, PAD: [number, number] = [6, 196], NODE_W = 14;

const BAND_COLOR: Record<string, string> = {
  band_low: "var(--color-seq-2)", band_medium: "var(--color-seq-3)", band_high: "var(--color-seq-4)", band_very_high: "var(--color-seq-5)",
  band_none: "var(--color-grey-300)", band_blocked: "var(--color-grey-300)",
};
const pct = (v: number, t: number) => (t ? `${((100 * v) / t).toFixed(v / t < 0.1 ? 1 : 0)}%` : "n/a");

function linkColor(l: { source: string; target: string }): string {
  return BAND_COLOR[l.target] ?? BAND_COLOR[l.source] ?? (l.target === "blocked" ? "var(--color-muted)" : "var(--color-grey-300)");
}

export function DecisionFlow() {
  const q = usePublicFlow(useSignedIn());
  if (q.isLoading) return <Frame><div role="status" className="grid h-[320px] place-items-center text-[15px] text-muted">Loading last night's plan…</div></Frame>;
  if (q.isError || !q.data || !q.data.available) {
    return (
      <Frame>
        <div role="status" className="grid h-[240px] place-items-center px-6 text-center text-[15px] text-muted">
          {q.data?.message ?? "Last night's plan is not available yet. It appears here once the nightly run has finished."}
        </div>
      </Frame>
    );
  }
  return <Flow flow={q.data} />;
}

const TITLE = "What happens to every open case, every night";
const LOOKING = "Last night's open cases, left to right: the policy check, the break-risk band, the treatment and the review. A wider band is more cases.";

function Frame({ children, takeaway }: { children: React.ReactNode; takeaway?: string }) {
  return <VisualCard title={TITLE} looking={LOOKING} takeaway={takeaway}>{children}</VisualCard>;
}

function Flow({ flow }: { flow: PublicFlow }) {
  const reduced = useReducedMotion();
  const [wrap, inView] = useInView<HTMLDivElement>();
  const svg = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const active = hover ?? pinned;

  const layout = useMemo(
    () => layoutSankey(flow.nodes, flow.links, { width: W, height: H - TOP, nodeWidth: NODE_W, gap: 12, minH: 26, padX: PAD }),
    [flow],
  );
  const nodeById = useMemo(() => new Map(layout.nodes.map((n) => [n.id, n])), [layout]);
  const on = useMemo(() => (active ? pathThrough(active, flow.links) : null), [active, flow.links]);

  // Start the draw-in once the chart is on screen; pause the particles whenever it is not.
  useEffect(() => { if (inView) setStarted(true); }, [inView]);
  useEffect(() => {
    const el = svg.current;
    if (!el || !("pauseAnimations" in el)) return;
    if (inView && !reduced) el.unpauseAnimations(); else el.pauseAnimations();
  }, [inView, reduced]);

  const cols = flow.columns ?? [];
  const colX = (c: number) => layout.nodes.find((n) => n.col === c)?.x ?? 0;
  const node = active ? nodeById.get(active) : null;
  const incoming = node ? flow.links.filter((l) => l.target === node.id) : [];
  const outgoing = node ? flow.links.filter((l) => l.source === node.id) : [];
  const label = (id: string) => nodeById.get(id)?.label ?? id;

  return (
    <Frame takeaway={flowTakeaway(flow)}>
      <div ref={wrap} className="overflow-x-auto">
        <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className={`block h-auto w-full min-w-[860px] ${inView ? "" : "vz-paused"}`} role="group"
          aria-label="Flow of last night's open cases through the policy gate, the break-risk band, the treatment and the review step. The same numbers are in the table below.">
          {cols.map((c, i) => (
            <text key={c} x={colX(i)} y={14} fontSize={12} fontWeight={600} style={{ fill: "var(--color-muted)" }}
              >{c}</text>
          ))}
          <g transform={`translate(0 ${TOP})`}>
            <g fill="none">
              {layout.links.map((l, i) => {
                const k = linkKey(l);
                const dim = on ? !on.has(k) : false;
                return (
                  <path key={k} d={l.d} stroke={linkColor(l)} strokeWidth={l.width} className={`vz-link ${started && !reduced ? "vz-draw" : ""}`}
                    style={{ ["--len" as string]: 1600, ["--d" as string]: `${(nodeById.get(l.source)?.col ?? 0) * 260 + i * 6}ms`, opacity: dim ? 0.07 : on ? 0.78 : 0.5 }} />
                );
              })}
            </g>
            {on && !reduced && (
              <g aria-hidden>
                {layout.links.filter((l) => on.has(linkKey(l))).map((l) => (
                  <circle key={linkKey(l)} r={3} style={{ fill: "var(--color-ink)" }}>
                    <animateMotion dur="3.2s" repeatCount="indefinite" path={l.d} />
                  </circle>
                ))}
              </g>
            )}
            <g>
              {layout.nodes.map((n) => {
                const dim = on ? !(n.id === active || [...on].some((k) => k.startsWith(`${n.id}>`) || k.endsWith(`>${n.id}`))) : false;
                return (
                  <g key={n.id} role="button" tabIndex={0} aria-pressed={pinned === n.id}
                    aria-label={`${n.label}: ${fmtInt(n.value)} cases, ${pct(n.value, flow.total)} of open cases`}
                    style={{ cursor: "pointer", outline: "none", opacity: dim ? 0.35 : 1, transition: "opacity 250ms var(--ease-out)" }}
                    onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
                    onClick={() => setPinned((p) => (p === n.id ? null : n.id))}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPinned((p) => (p === n.id ? null : n.id)); } if (e.key === "Escape") setPinned(null); }}>
                    <rect x={n.x - 6} y={n.y - 4} width={NODE_W + 150} height={n.h + 8} fill="transparent" />
                    <rect x={n.x} y={n.y} width={NODE_W} height={n.h} rx={2} style={{ fill: "var(--color-ink)" }} />
                    {active === n.id && <rect x={n.x - 3} y={n.y - 3} width={NODE_W + 6} height={n.h + 6} rx={4} fill="none" stroke="var(--color-brand)" strokeWidth={2} />}
                    <text x={n.x + NODE_W + 8} y={n.y + n.h / 2 - 3} fontSize={13.5} fontWeight={600} dominantBaseline="auto"
                      style={{ fill: "var(--color-ink)", paintOrder: "stroke", stroke: "white", strokeWidth: 4, strokeLinejoin: "round" }}>{n.label}</text>
                    <text x={n.x + NODE_W + 8} y={n.y + n.h / 2 + 12} fontSize={12.5} className="tabular"
                      style={{ fill: "var(--color-muted)", paintOrder: "stroke", stroke: "white", strokeWidth: 4, strokeLinejoin: "round" }}>
                      {fmtInt(n.value)} · {pct(n.value, flow.total)}
                    </text>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
      </div>

      <div className={`mt-4 rounded-[var(--radius-lg)] border border-grey-300/70 p-4 text-[14.5px] ${node ? "min-h-[120px]" : ""}`} aria-live="polite">
        {node ? (
          <div className="grid gap-x-8 gap-y-3 md:grid-cols-[minmax(0,1.1fr)_1fr_1fr]">
            <div>
              <div className="text-[13px] font-semibold text-muted">{cols[node.col]}</div>
              <div className="font-[family-name:var(--font-display)] text-[24px] font-semibold leading-tight">{node.label}</div>
              <div className="tabular"><strong>{fmtInt(node.value)}</strong> cases, {pct(node.value, flow.total)} of all open cases</div>
              {node.top && (
                <ul className="m-0 mt-2 list-none p-0 text-[13.5px]">
                  {node.top.map((t) => (
                    <li key={t.label} className="flex justify-between gap-3"><span>{t.label}</span><span className="tabular text-muted">{fmtInt(t.value)}</span></li>
                  ))}
                </ul>
              )}
            </div>
            <FlowList title="Comes from" links={incoming} pick="source" label={label} total={node.value} />
            <FlowList title="Goes to" links={outgoing} pick="target" label={label} total={node.value} />
          </div>
        ) : (
          <div>
            <p className="m-0 text-muted">Planned for {flow.plan_date}. Point at a step, or tab to it, to follow its path. Click to keep it highlighted.</p>
          </div>
        )}
      </div>

      {/* The wrapper is the screen-reader-only box: an absolutely positioned table would stretch the page below the footer. */}
      <div className="sr-only">
        <table>
          <caption>Cases moving from one step to the next</caption>
          <thead><tr><th scope="col">From</th><th scope="col">To</th><th scope="col">Cases</th></tr></thead>
          <tbody>{flow.links.map((l) => <tr key={linkKey(l)}><td>{label(l.source)}</td><td>{label(l.target)}</td><td>{fmtInt(l.value)}</td></tr>)}</tbody>
        </table>
      </div>
    </Frame>
  );
}

function FlowList({ title, links, pick, label, total }: { title: string; links: { source: string; target: string; value: number }[]; pick: "source" | "target"; label: (id: string) => string; total: number }) {
  if (!links.length) return <div />;
  return (
    <div>
      <div className="text-[13px] font-semibold text-muted">{title}</div>
      <ul className="m-0 mt-1 list-none p-0">
        {[...links].sort((a, b) => b.value - a.value).map((l) => (
          <li key={l[pick]} className="flex justify-between gap-3 py-0.5">
            <span>{label(l[pick])}</span><span className="tabular text-muted">{fmtInt(l.value)} ({pct(l.value, total)})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
