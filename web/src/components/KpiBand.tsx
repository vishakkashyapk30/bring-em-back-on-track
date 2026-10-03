/** Figma "Case studies" band: dark panel, columns divided by vertical rules. */
export function KpiBand({ items }: { items: { label: string; value: string; delta?: string; definition?: string }[] }) {
  return (
    <div className="grid gap-6 rounded-[var(--radius-xl)] bg-navy p-10 text-white md:grid-cols-3 md:divide-x md:divide-white/30">
      {items.map((k) => (
        <div key={k.label} className="md:px-6" title={k.definition}>
          <p className="m-0 text-sm text-white/70">{k.label}</p>
          <p className="m-0 text-4xl font-medium tabular">{k.value}</p>
          {k.delta && <p className="m-0 text-gold">{k.delta}</p>}
        </div>
      ))}
    </div>
  );
}
