/** Figma "Case studies" band: dark panel, columns divided by vertical rules. */
export function KpiBand({ items }: { items: { label: string; value: string; delta?: string; definition?: string }[] }) {
  return (
    <div className="grid gap-6 rounded-[var(--radius-xl)] bg-cream p-10 text-ink md:grid-cols-3 md:divide-x md:divide-grey-300">
      {items.map((k) => (
        <div key={k.label} className="md:px-6" title={k.definition}>
          <p className="m-0 text-sm text-muted">{k.label}</p>
          <p className="m-0 text-4xl font-medium tabular">{k.value}</p>
          {k.delta && <p className="m-0 text-gold">{k.delta}</p>}
        </div>
      ))}
    </div>
  );
}
