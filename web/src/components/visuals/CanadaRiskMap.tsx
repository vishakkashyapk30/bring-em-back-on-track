import { geoConicConformal, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { Pause, Play, Table2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";

import { type MapMetric, type MetricId, type PublicMap, usePublicMap } from "@/api/visuals";
import { Segmented } from "@/components/Tabs";
import { useInView, useSignedIn } from "./hooks";
import { VisualCard } from "./VisualCard";
import {
  allValues, classOf, fmtInt, fmtMonth, fmtValue, legendStops, mapTakeaway, nextInDirection, quantileBreaks, radiusFor, relax, tableRows, versus, type Dir,
} from "./helpers";
import "./visuals.css";

const W = 800, H = 560;
const topo = world as unknown as Topology;
const countries = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry>;
const byId = (id: string) => countries.features.find((f) => String(f.id) === id) as Feature<Geometry>;
const canada = byId("124"), usa = byId("840"); // ISO 3166-1 numeric

const projection = geoConicConformal().parallels([49, 77]).rotate([96, 0]).fitExtent([[10, 10], [W - 10, H - 24]], canada);
const pathGen = geoPath(projection);
const CANADA_D = pathGen(canada) ?? "";
const USA_D = pathGen(usa) ?? "";

const METRIC_ORDER: MetricId[] = ["broken_ptp_rate", "hardship_rate", "open_cases", "promises_at_risk"];
const METRIC_SHORT: Record<MetricId, string> = {
  broken_ptp_rate: "Broken promises", hardship_rate: "Hardship", open_cases: "Open cases", promises_at_risk: "Promises at risk",
};
const ARROW: Record<string, Dir> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
const isMetric = (s: string | null): s is MetricId => !!s && (METRIC_ORDER as string[]).includes(s);

/** Optional starting state from the address (?metric=hardship_rate&month=2026-07&pin=ON&view=table&play=0), so a view can be shared. */
function initialState(map: PublicMap) {
  const q = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
  const metric = isMetric(q.get("metric")) ? (q.get("metric") as MetricId) : "broken_ptp_rate";
  const mi = map.months.indexOf(q.get("month") ?? "");
  return {
    metric, monthIdx: mi >= 0 ? mi : map.months.length - 1, pin: map.provinces.some((p) => p.code === q.get("pin")) ? q.get("pin") : null,
    postal: q.get("view") === "postal", table: q.get("view") === "table",
  };
}

export function CanadaRiskMap() {
  const q = usePublicMap(useSignedIn());
  if (q.isLoading) return <MapFrame><div className="grid aspect-[800/560] place-items-center text-[15px] text-muted" role="status">Loading the map…</div></MapFrame>;
  if (q.isError || !q.data || !q.data.metrics.broken_ptp_rate) {
    return (
      <MapFrame>
        <div className="grid aspect-[800/560] place-items-center px-6 text-center text-[15px] text-muted" role="status">
          The map numbers are not available right now. Check that the data has been built, then refresh.
        </div>
      </MapFrame>
    );
  }
  return <Loaded map={q.data} />;
}

function MapFrame({ children, takeaway, actions }: { children: React.ReactNode; takeaway?: string | null; actions?: React.ReactNode }) {
  return (
    <VisualCard title="Where promises to pay are breaking" actions={actions} takeaway={takeaway}
      looking="Each circle is a province: its colour is the measure you pick, its size is how many customers live there.">
      {children}
    </VisualCard>
  );
}

function Loaded({ map }: { map: PublicMap }) {
  const init = useMemo(() => initialState(map), [map]);
  const [metricId, setMetric] = useState<MetricId>(init.metric);
  const [monthIdx, setMonth] = useState(init.monthIdx);
  const [playing, setPlaying] = useState(false);
  const [pin, setPin] = useState<string | null>(init.pin);
  const [hover, setHover] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [postal, setPostal] = useState(init.postal);
  const [table, setTable] = useState(init.table);
  const [hoverFsa, setHoverFsa] = useState<string | null>(null);
  const [wrapRef, inView] = useInView<HTMLDivElement>();
  const refs = useRef<Record<string, SVGGElement | null>>({});

  const metric = map.metrics[metricId] ?? (map.metrics.broken_ptp_rate as MapMetric);
  const i = metric.monthly ? monthIdx : 0;
  const month = map.months[monthIdx];
  const national = metric.national[i] ?? null;

  // Month play: advance every 1.1 s, only while on screen. Stops by itself at the last month.
  useEffect(() => {
    if (!playing || !metric.monthly || !inView) return;
    const t = setInterval(() => {
      setMonth((m) => {
        if (m >= map.months.length - 1) { setPlaying(false); return m; }
        return m + 1;
      });
    }, 1100);
    return () => clearInterval(t);
  }, [playing, metric.monthly, inView, map.months.length]);

  const togglePlay = () => {
    if (!playing && monthIdx >= map.months.length - 1) setMonth(0);
    setPlaying((p) => !p);
  };

  // Colour classes come from every month at once, so colours stay comparable while the month moves.
  const breaks = useMemo(() => quantileBreaks(allValues(metric)), [metric]);
  const postalBreaks = useMemo(() => quantileBreaks(metric.fsas.map((f) => f.value)), [metric]);

  const maxCustomers = Math.max(...map.provinces.map((p) => p.customers));
  const placed = useMemo(() => {
    const raw = map.provinces.map((p) => {
      const [x, y] = projection([p.lon, p.lat]) ?? [0, 0];
      return { ...p, x, y, r: radiusFor(p.customers, maxCustomers) };
    });
    return relax(raw, 3).sort((a, b) => b.r - a.r); // biggest first, so small ones are drawn on top
  }, [map.provinces, maxCustomers]);
  const dots = useMemo(() => {
    const max = Math.max(1, ...metric.fsas.map((f) => f.n));
    return metric.fsas.map((f) => {
      const [x, y] = projection([f.lon, f.lat]) ?? [0, 0];
      return { ...f, x, y, r: 2.5 + 5.5 * Math.sqrt(f.n / max) };
    });
  }, [metric]);

  const rows = tableRows(map, metricId, monthIdx);
  const shown = placed.filter((p) => metric.series[p.code]?.value[i] != null);
  const hiddenProvinces = placed.length - shown.length;
  const nav = shown.map((p) => ({ code: p.code, x: p.x, y: p.y }));
  const tabStop = shown.some((p) => p.code === focus) ? focus : shown.find((p) => p.code === pin)?.code ?? shown[0]?.code;

  const moveFocus = useCallback((code: string | null) => { if (code) { setFocus(code); refs.current[code]?.focus(); } }, []);
  const onKey = (e: React.KeyboardEvent, code: string) => {
    if (ARROW[e.key]) { e.preventDefault(); moveFocus(nextInDirection(code, nav, ARROW[e.key])); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPin((p) => (p === code ? null : code)); }
    else if (e.key === "Escape") setPin(null);
  };

  const describe = (code: string) => {
    const p = placed.find((x) => x.code === code)!;
    const s = metric.series[code];
    return { p, v: s?.value[i] ?? null, n: s?.n[i] ?? null, top: s?.top[i] ?? null, series: s };
  };
  const labelFor = (code: string) => {
    const { p, v, n } = describe(code);
    return v == null ? `${p.name}: hidden, fewer than ${map.min_group} customers`
      : `${p.name}: ${METRIC_SHORT[metricId]} ${fmtValue(v, metric.unit)}, ${versus(v, national, metric.unit)}, ${fmtInt(n)} customers`;
  };

  const tip = hover ? describe(hover) : null;
  const pinned = pin ? describe(pin) : null;
  const prev = monthIdx > 0 && metric.monthly ? metric.national[monthIdx - 1] : null;
  const change = metric.monthly && national != null && prev != null ? national - prev : null;
  const colorOf = (v: number, br: number[]) => `var(--color-seq-${classOf(v, br) + 1})`;
  const textOn = (v: number) => (classOf(v, breaks) >= 3 ? "white" : "var(--color-ink)");

  return (
    <MapFrame takeaway={mapTakeaway(map, metricId, monthIdx)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-full">
          <div className="max-w-full overflow-x-auto [&_button]:whitespace-nowrap">
          <Segmented label="What the map shows" value={metricId} onChange={(id) => { setMetric(id); setPlaying(false); }}
            options={METRIC_ORDER.filter((id) => map.metrics[id]).map((id) => [id, METRIC_SHORT[id]] as [MetricId, string])} />
          </div>
          <p className="mb-0 mt-2 max-w-[460px] text-[13.5px] text-muted">{metric.note}</p>
        </div>
        <div aria-live="polite">
          <div className="font-[family-name:var(--font-display)] text-[34px] font-semibold leading-none tabular">{fmtValue(national, metric.unit)}</div>
          <div className="mt-1 text-[13.5px] text-muted">
            nationally, {metric.monthly ? fmtMonth(month, true) : "today"}
            {change != null && Math.abs(change) >= 0.05 ? `, ${change > 0 ? "up" : "down"} ${Math.abs(change).toFixed(1)} points on the month before` : ""}
          </div>
        </div>
      </div>

      <div ref={wrapRef} className="relative mt-4">
        {table ? (
          <div className="max-h-[560px] overflow-auto rounded-[var(--radius-md)] border border-grey-300/80">
            <table className="w-full border-collapse text-left text-[14px]">
              <caption className="px-3 py-2 text-left text-[13.5px] text-muted">
                {METRIC_SHORT[metricId]}, {metric.monthly ? fmtMonth(month, true) : "today"}, by province. Areas with fewer than {map.min_group} customers are hidden.
              </caption>
              <thead className="sticky top-0 bg-grey-100">
                <tr>{["Province", metric.unit === "%" ? "Rate" : "Rate per 1,000 customers", "Compared with national", "Customers", "Most common reason"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-semibold">{h}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.code} className="border-t border-grey-300/60">
                    <th scope="row" className="px-3 py-2 font-medium">{r.name}</th>
                    <td className="px-3 py-2 tabular">{r.value == null ? "Hidden" : fmtValue(r.value, metric.unit)}</td>
                    <td className="px-3 py-2">{r.vs}</td>
                    <td className="px-3 py-2 tabular">{r.n == null ? "n/a" : fmtInt(r.n)}</td>
                    <td className="px-3 py-2">{r.top ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="relative mx-auto max-w-[880px]">
            <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto block h-auto max-h-[430px] w-full" role="group" aria-label={`Map of Canada: ${METRIC_SHORT[metricId]} by ${postal ? "postal area" : "province"}. Use the table view for the same numbers as text.`}>
              <path d={USA_D} fill="var(--color-grey-100)" stroke="var(--color-grey-300)" strokeWidth={0.6} aria-hidden />
              <path d={CANADA_D} fill="var(--color-cream)" stroke="var(--color-muted)" strokeOpacity={0.55} strokeWidth={0.9} strokeLinejoin="round" aria-hidden />
              {postal ? (
                <g>
                  {dots.map((d, k) => (
                    <circle key={d.fsa} cx={d.x} cy={d.y} className="vz-bubble" style={{ r: `${d.r}px`, fill: colorOf(d.value, postalBreaks), animationDelay: `${Math.min(k, 200) * 3}ms` }}
                      stroke="white" strokeWidth={0.6}
                      onMouseEnter={() => setHoverFsa(d.fsa)} onMouseLeave={() => setHoverFsa(null)} />
                  ))}
                </g>
              ) : (
                <g>
                  {placed.map((p) => {
                    const { v } = describe(p.code);
                    if (v == null) return null;
                    const isPin = pin === p.code, isFocus = focus === p.code;
                    return (
                      <g key={p.code}>
                        <g ref={(el) => { refs.current[p.code] = el; }} role="button" tabIndex={tabStop === p.code ? 0 : -1} aria-pressed={isPin} aria-label={labelFor(p.code)}
                          style={{ cursor: "pointer", outline: "none" }}
                          onClick={() => { setPin(isPin ? null : p.code); setFocus(p.code); }} onKeyDown={(e) => onKey(e, p.code)}
                          onFocus={() => { setFocus(p.code); setHover(p.code); }} onBlur={() => { setFocus((f) => (f === p.code ? null : f)); setHover((h) => (h === p.code ? null : h)); }}
                          onMouseEnter={() => setHover(p.code)} onMouseLeave={() => setHover((h) => (h === p.code ? null : h))}>
                          <circle cx={p.x} cy={p.y} r={p.r + 12} fill="transparent" />
                          <circle cx={p.x} cy={p.y} className="vz-bubble" style={{ r: `${p.r}px`, fill: colorOf(v, breaks) }}
                            stroke="white" strokeWidth={1} />
                          {(isPin || isFocus) && <circle cx={p.x} cy={p.y} r={p.r + 4} fill="none" stroke={isPin ? "var(--color-ink)" : "var(--color-brand)"} strokeWidth={2.5} />}
                          {p.r >= 11 && (
                            <text x={p.x} y={p.y} textAnchor="middle" dominantBaseline="central" fontSize={p.r >= 20 ? 14 : 11} fontWeight={600} pointerEvents="none"
                              style={{ fill: textOn(v) }}>{p.code}</text>
                          )}
                        </g>
                      </g>
                    );
                  })}
                </g>
              )}
            </svg>

            {tip && !postal && (
              <div className="pointer-events-none absolute z-10 w-[230px] -translate-x-1/2 rounded-[var(--radius-md)] bg-ink px-3 py-2 text-[13px] leading-snug text-white shadow-[var(--shadow-raised)]"
                style={{ left: `${Math.min(88, Math.max(12, (tip.p.x / W) * 100))}%`, top: `${Math.max(2, ((tip.p.y - tip.p.r) / H) * 100 - 2)}%`, transform: "translate(-50%, -100%)" }}>
                <div className="font-semibold">{tip.p.name}</div>
                <div>{fmtValue(tip.v, metric.unit)} · {versus(tip.v, national, metric.unit)}</div>
                <div className="text-white/70">{fmtInt(tip.n)} customers{tip.top ? ` · mostly: ${tip.top}` : ""}</div>
              </div>
            )}
            {postal && hoverFsa && (() => {
              const d = dots.find((x) => x.fsa === hoverFsa)!;
              return (
                <div className="pointer-events-none absolute z-10 rounded-[var(--radius-md)] bg-ink px-3 py-2 text-[13px] leading-snug text-white shadow-[var(--shadow-raised)]"
                  style={{ left: `${(d.x / W) * 100}%`, top: `${((d.y - d.r) / H) * 100}%`, transform: "translate(-50%, calc(-100% - 6px))" }}>
                  <div className="font-semibold">Postal area {d.fsa}, {d.province}</div>
                  <div>{fmtValue(d.value, metric.unit)} · {fmtInt(d.n)} customers</div>
                </div>
              );
            })()}

            {pinned && !postal && (
              <ProvincePanel name={pinned.p.name} value={pinned.v} n={pinned.n} top={pinned.top} unit={metric.unit}
                national={national} series={pinned.series} natSeries={metric.national} monthIdx={i} monthly={metric.monthly} months={map.months}
                label={METRIC_SHORT[metricId]} onClose={() => setPin(null)} />
            )}
          </div>
        )}
      </div>

      {/* Controls: month scrubber, view switches and the legend */}
      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={togglePlay} disabled={!metric.monthly || table} aria-label={playing ? "Pause the month animation" : "Play the months one by one"}
              className="grid h-10 w-10 shrink-0 cursor-pointer place-items-center rounded-[var(--radius-md)] border border-grey-300 bg-white text-ink transition-colors hover:bg-grey-100 disabled:cursor-not-allowed disabled:opacity-40">
              {playing ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden className="ml-0.5" />}
            </button>
            <div className="flex-1">
              <label htmlFor="month-scrub" className="mb-1 flex items-baseline justify-between text-[13.5px]">
                <span className="font-semibold">{metric.monthly ? fmtMonth(month, true) : "Today"}</span>
                <span className="text-muted">{metric.monthly ? "Drag, or use the arrow keys" : "This view is a snapshot, not by month"}</span>
              </label>
              <input id="month-scrub" type="range" min={0} max={map.months.length - 1} step={1} value={monthIdx} disabled={!metric.monthly}
                aria-valuetext={fmtMonth(month, true)} onChange={(e) => { setPlaying(false); setMonth(Number(e.target.value)); }}
                className="block h-6 w-full cursor-pointer accent-[var(--color-brand)] disabled:cursor-not-allowed disabled:opacity-40" />
              <div className="flex justify-between text-[12px] text-muted" aria-hidden><span>{fmtMonth(map.months[0])}</span><span>{fmtMonth(map.months[map.months.length - 1])}</span></div>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Map detail" value={postal ? "postal" : "province"} onChange={(v) => { setPostal(v === "postal"); setTable(false); setPlaying(false); }}
            options={[["province", "Provinces"], ["postal", "Postal areas"]]} />
          <button type="button" aria-pressed={table} onClick={() => setTable((t) => !t)}
            className={`inline-flex h-10 cursor-pointer items-center gap-2 rounded-[var(--radius-md)] border border-grey-300/70 px-3 text-[14px] font-medium ${table ? "bg-ink text-white" : "bg-white text-ink hover:bg-grey-100"}`}>
            <Table2 size={15} aria-hidden /> {table ? "View as map" : "View as table"}
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-grey-300/70 pt-3 text-[13px]" aria-label="Legend">
        <div className="flex items-start gap-2">
          <span className="mt-px text-muted">Lower</span>
          <div>
            <div className="flex" aria-hidden>{[1, 2, 3, 4, 5].map((k) => <span key={k} className="h-3 w-9 first:rounded-l-[2px] last:rounded-r-[2px]" style={{ background: `var(--color-seq-${k})` }} />)}</div>
            <div className="relative h-4 text-[11.5px] text-muted tabular" aria-hidden>
              {legendStops(postal ? postalBreaks : breaks, metric.unit).map((t, k) => <span key={k} className="absolute -translate-x-1/2" style={{ left: `${(k + 1) * 36}px` }}>{t}</span>)}
            </div>
          </div>
          <span className="mt-px text-muted">Higher</span>
        </div>
        <span className="text-muted">
          {postal ? `${metric.fsas.length} postal areas shown, ` : "Bubble size is the number of customers. "}
          {postal ? `${metric.fsas_hidden} hidden` : `${hiddenProvinces === 0 ? "No" : hiddenProvinces} ${hiddenProvinces === 1 ? "province" : "provinces"} hidden`} (fewer than {map.min_group} customers).
          {" "}Data as of {map.as_of}.
        </span>
        
      </div>
    </MapFrame>
  );
}

function ProvincePanel(props: {
  name: string; value: number | null; n: number | null; top: string | null; unit: string; national: number | null;
  series: { value: (number | null)[] } | undefined; natSeries: (number | null)[]; monthIdx: number; monthly: boolean; months: string[];
  label: string; onClose: () => void;
}) {
  const { name, value, n, top, unit, national, series, natSeries, monthIdx, monthly, months, label, onClose } = props;
  return (
    <aside aria-label={`${name} details`} className="fade-in relative z-10 mt-3 w-full md:absolute md:right-2 md:top-2 md:mt-0 md:w-[290px] rounded-[var(--radius-lg)] border border-grey-300 bg-white p-4 shadow-[var(--shadow-raised)]">
      <div className="flex items-start justify-between gap-2">
        <h3 className="m-0 text-[20px]">{name}</h3>
        <button type="button" onClick={onClose} aria-label="Close province details" className="-mr-1 -mt-1 h-7 w-7 cursor-pointer rounded-full border-0 bg-transparent text-[18px] leading-none text-muted hover:bg-grey-100">×</button>
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="font-[family-name:var(--font-display)] text-[34px] font-semibold leading-none tabular">{fmtValue(value, unit)}</span>
        <span className="text-[13px] text-muted">{label.toLowerCase()}</span>
      </div>
      <p className="m-0 mt-1 text-[13.5px]">{versus(value, national, unit)}</p>
      <dl className="mb-0 mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13.5px]">
        <dt className="text-muted">Customers</dt><dd className="m-0 tabular">{fmtInt(n)}</dd>
        <dt className="text-muted">Most common reason</dt><dd className="m-0">{top ?? "n/a"}</dd>
      </dl>
      {monthly && series && <Sparkline province={series.value} national={natSeries} idx={monthIdx} months={months} unit={unit} />}
    </aside>
  );
}

function Sparkline({ province, national, idx, months, unit }: { province: (number | null)[]; national: (number | null)[]; idx: number; months: string[]; unit: string }) {
  const w = 250, h = 54;
  const all = [...province, ...national].filter((x): x is number => x != null);
  const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
  const x = (k: number) => 4 + (k * (w - 8)) / (months.length - 1);
  const y = (v: number) => h - 6 - ((v - lo) / span) * (h - 14);
  const line = (a: (number | null)[]) => a.map((v, k) => (v == null ? null : `${a[k - 1] == null ? "M" : "L"}${x(k).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean).join(" ");
  const cur = province[idx];
  return (
    <figure className="m-0 mt-3">
      <svg viewBox={`0 0 ${w} ${h}`} className="block h-[54px] w-full" role="img" aria-label={`Twelve month trend, from ${fmtValue(province.find((v) => v != null) ?? null, unit)} in ${fmtMonth(months[0])} to ${fmtValue(province[province.length - 1], unit)} in ${fmtMonth(months[months.length - 1])}`}>
        <path d={line(national)} fill="none" stroke="var(--color-muted)" strokeWidth={1.2} strokeDasharray="3 3" />
        <path d={line(province)} fill="none" stroke="var(--color-brand)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {cur != null && <circle cx={x(idx)} cy={y(cur)} r={4} fill="var(--color-brand)" stroke="white" strokeWidth={2} />}
      </svg>
      <figcaption className="flex justify-between text-[11.5px] text-muted"><span>{fmtMonth(months[0])}</span><span><span className="text-brand">Solid</span> province, dashed national</span><span>{fmtMonth(months[months.length - 1])}</span></figcaption>
    </figure>
  );
}
