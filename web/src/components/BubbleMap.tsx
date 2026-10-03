import "leaflet/dist/leaflet.css";

import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";

/** S2 weather map: bubbles at FSA centroids, groups < 10 already suppressed server-side. */
export function BubbleMap({ items }: { items: { fsa: string; lat: number; lon: number; value: number; customers: number }[] }) {
  return (
    <MapContainer center={[50, -85]} zoom={4} className="h-[480px] w-full rounded-[var(--radius-lg)]" scrollWheelZoom={false}>
      <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap, &copy; CARTO" />
      {items.map((p) => (
        <CircleMarker key={p.fsa} center={[p.lat, p.lon]} radius={6 + p.value * 40} pathOptions={{ color: "#a71f3e", fillOpacity: 0.45 }}>
          <Tooltip>{p.fsa}: {(p.value * 100).toFixed(0)}% · {p.customers} customers</Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
