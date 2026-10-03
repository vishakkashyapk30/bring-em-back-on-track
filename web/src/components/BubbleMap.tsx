import "leaflet/dist/leaflet.css";

import { useMemo } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";

export type MapItem = { fsa: string; city?: string; province?: string; lat: number; lon: number; value: number; customers: number };

const STEPS = 5;
const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/** S2 weather map. Magnitude = one sequential hue (5 quantile classes, light -> dark) + size = customers.
 * Areas under 10 customers are suppressed server-side. Legend + hover tooltip; the table view sits beside it. */
export function BubbleMap({ items, label }: { items: MapItem[]; label: string }) {
  const { breaks, colors, maxN } = useMemo(() => {
    const vals = items.map((i) => i.value).sort((a, b) => a - b);
    const q = (p: number) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))] ?? 0;
    return {
      breaks: Array.from({ length: STEPS - 1 }, (_, k) => q((k + 1) / STEPS)),
      colors: Array.from({ length: STEPS }, (_, k) => cssVar(`--color-seq-${k + 1}`)),
      maxN: Math.max(1, ...items.map((i) => i.customers)),
    };
  }, [items]);
  const cls = (v: number) => breaks.filter((b) => v > b).length;
  const ink = cssVar("--color-map-stroke");
  return (
    <div>
      <MapContainer center={[52, -90]} zoom={4} className="h-[520px] w-full rounded-[var(--radius-lg)]" scrollWheelZoom={false}>
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
        {items.map((p) => (
          <CircleMarker key={p.fsa} center={[p.lat, p.lon]} radius={4 + 14 * Math.sqrt(p.customers / maxN)}
            pathOptions={{ color: ink, weight: 0.5, fillColor: colors[cls(p.value)], fillOpacity: 0.85 }}>
            <Tooltip>
              <strong>{p.fsa}</strong> {p.city ? `· ${p.city}, ${p.province}` : ""}<br />
              {label}: {pct(p.value)}<br />{p.customers.toLocaleString()} customers
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm" aria-label="Legend">
        <span className="text-muted">{label}:</span>
        {colors.map((c, k) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-3 w-5 rounded-sm border border-ink/20" style={{ background: c }} />
            {k === 0 ? `≤ ${pct(breaks[0] ?? 0)}` : k === STEPS - 1 ? `> ${pct(breaks[STEPS - 2] ?? 0)}` : `${pct(breaks[k - 1])}–${pct(breaks[k])}`}
          </span>
        ))}
        <span className="text-muted">· bubble size = customers</span>
      </div>
    </div>
  );
}
