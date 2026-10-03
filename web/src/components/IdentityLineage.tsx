const SYSTEM: Record<string, string> = { crm: "CRM", cards: "Cards", lending: "Lending", core_banking: "Core banking", bureau: "Credit bureau", collections: "Collections" };

type Src = { system: string; ref: string; method?: string; confidence?: number | null };

/** Identity & lineage: how many systems and keys resolve to this golden ID, grouped by system. */
export function IdentityLineage({ data }: { data: { golden_id: string; match_confidence: number; match_method: string; sources: Src[] } }) {
  const groups = data.sources.reduce<Record<string, Src[]>>((a, s) => ({ ...a, [s.system]: [...(a[s.system] ?? []), s] }), {});
  return (
    <div>
      <div className="grid grid-cols-3 gap-2 text-center">
        {[["Systems", Object.keys(groups).length], ["Source keys", data.sources.length], ["Confidence", data.match_confidence.toFixed(2)]].map(([k, v]) => (
          <div key={k} className="rounded-[var(--radius-md)] bg-grey-100 px-2 py-2.5">
            <div className="font-[family-name:var(--font-display)] text-[18px] font-semibold tabular">{v}</div>
            <div className="text-[12px] text-muted">{k}</div>
          </div>
        ))}
      </div>
      <p className="mb-3 mt-3 text-[13px] text-muted">Linked {data.match_method === "deterministic" ? "by exact keys (no fuzzy matching needed)" : "partly by scored matching"}.</p>
      <ul className="m-0 list-none divide-y divide-grey-300/60 p-0">
        {Object.entries(groups).map(([sys, items]) => (
          <li key={sys} className="flex items-start justify-between gap-3 py-2">
            <span className="text-[13.5px] font-medium">{SYSTEM[sys] ?? sys}</span>
            <span className="flex flex-col items-end gap-0.5">
              {items.map((s) => <code key={s.ref} className="text-[12.5px] text-muted">{s.ref}</code>)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
