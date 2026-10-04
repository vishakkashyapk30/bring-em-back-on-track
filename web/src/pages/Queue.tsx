import { ArrowDown, ArrowUpDown, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useMe, useQueue } from "@/api/hooks";
import type { QueueItem } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { FilterChips, SearchBox, SortSelect, Toolbar, type Chip } from "@/components/FilterBar";
import { SectionTag } from "@/components/SectionTag";
import { EmptyState, QueryState } from "@/components/States";
import { actionLabel, productLabel, windowLabel } from "@/lib/labels";

const BAND = { low: "Low", medium: "Medium", high: "High", very_high: "Very high" } as const;
const SORTS: [string, string][] = [["priority", "Priority"], ["risk", "Break risk"], ["overdue", "Amount past due"], ["dpd", "Days past due"], ["name", "Name"]];
const PAGE = 15;

const money = (n?: number) => (n == null ? "" : n.toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }));

function Risk({ it }: { it: QueueItem }) {
  if (it.p_break == null || !it.risk_band) return <span className="text-muted">No promise to score</span>;
  return <span className="tabular">{BAND[it.risk_band as keyof typeof BAND] ?? it.risk_band}<span className="ml-1.5 text-[12.5px] text-muted">{Math.round(it.p_break * 100)}%</span></span>;
}

function Status({ it }: { it: QueueItem }) {
  if (it.decision) return <Badge kind="ok">{it.decision.decision === "approve" ? "Approved" : it.decision.decision === "edit" ? "Changed" : "Overridden"}</Badge>;
  if (it.status === "deferred") return <span title={it.deferred_reason ?? undefined}><Badge kind="neutral">Tomorrow</Badge></span>;
  return null;
}

/** Debounce so typing in the search box doesn't fire a request per keystroke. */
function useDebounced<T>(v: T, ms = 250) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

/** Today's queue: filter, search and sort. The choices live in the URL, so back/forward and shared links keep them. */
export default function Queue() {
  const nav = useNavigate();
  const me = useMe();
  const [sp, setSp] = useSearchParams();
  const view = sp.get("view") ?? "all";
  const sort = sp.get("sort") ?? "priority";
  const [text, setText] = useState(sp.get("q") ?? "");
  const q = useDebounced(text);
  const [limit, setLimit] = useState(PAGE);

  const set = (k: string, v: string, def: string) => {
    const n = new URLSearchParams(sp);
    if (v === def || !v) n.delete(k); else n.set(k, v);
    setSp(n, { replace: true });
    setLimit(PAGE);
  };
  useEffect(() => { set("q", q, ""); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [q]);

  const res = useQueue({ view, sort, q, limit });
  const items = res.data?.items ?? [];
  const c = res.data?.counts;
  const lead = me.data?.role === "team_lead";
  const chips: Chip[] = [
    { id: "all", label: "To work", count: c?.all },
    { id: "calls", label: "Calls", count: c?.calls },
    { id: "digital", label: "Text and email", count: c?.digital },
    { id: "hardship", label: "Hardship", count: c?.hardship },
    { id: "vulnerable", label: "Vulnerable", count: c?.vulnerable },
    { id: "high_risk", label: "High break risk", count: c?.high_risk },
    { id: "tomorrow", label: "Moved to tomorrow", count: c?.tomorrow },
    ...(lead ? [{ id: "batch", label: "Batch reminders", count: c?.batch }] : []),
    { id: "no_contact", label: "No contact today", count: c?.no_contact },
  ];
  const total = res.data?.total ?? 0;
  const filtered = view !== "all" || q !== "";

  return (
    <>
      <SectionTag as="h1" subtitle={res.data?.scope ? `Showing ${res.data.scope}.${lead ? "" : " Routine reminders go out through your team lead's batch."}` : "The cases to work today."}>Today's queue</SectionTag>
      <Toolbar
        left={<FilterChips label="Filter the queue" chips={chips} value={view} onChange={(v) => set("view", v, "all")} />}
        right={<><SearchBox label="Search the queue" placeholder="Name, case or product" value={text} onChange={setText} /><SortSelect value={sort} onChange={(v) => set("sort", v, "priority")} options={SORTS} /></>}
      />
      <QueryState q={res} empty={false}>
        {items.length === 0 ? (
          <EmptyState title={filtered ? "No matches" : "Nothing to work today"}
            detail={filtered ? "Try another filter, or clear the search." : undefined}
            action={filtered ? <Button size="sm" onClick={() => { setText(""); setSp({}, { replace: true }); }}>Clear filters</Button> : undefined} />
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-md)] border border-grey-300 bg-white">
            <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[14.5px]">
              <thead className="shadow-[inset_0_-2px_0_var(--color-ink)]">
                <tr>
                  {([["Customer", "name"], ["Past due", "overdue"], ["What to do and why", "priority"], ["Break risk", "risk"], ["", ""], ["", ""]] as const).map(([h, key], i) => (
                    <th key={i} scope="col" aria-sort={key && key === sort ? "descending" : "none"} className="px-5 py-3.5 text-[14px] font-semibold text-ink">
                      {key ? (
                        <button type="button" onClick={() => set("sort", key, "priority")} title={`Sort by ${h.toLowerCase()}`}
                          className="inline-flex items-center gap-1.5 bg-transparent transition-colors hover:text-brand">
                          {h}{key === sort ? <ArrowDown size={13} aria-hidden /> : <ArrowUpDown size={13} aria-hidden className="opacity-40" />}
                        </button>
                      ) : h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const open = () => nav(`/customers/${it.golden_id}`);
                  const when = windowLabel(it.action.window);
                  return (
                    <tr key={it.case_id} tabIndex={0} onClick={open} onKeyDown={(e) => { if (e.key === "Enter") open(); }}
                      className="group cursor-pointer border-t border-grey-300/60 outline-none transition-colors even:bg-cream/60 hover:bg-brand-50 focus-visible:bg-brand-50">
                      <td className="px-5 py-3.5">
                        <div className="font-medium">{it.name}</div>
                        <div className="text-[13.5px] text-muted">{productLabel(it.product)} · {it.dpd} days late</div>
                      </td>
                      <td className="px-5 py-3.5 tabular">{money(it.overdue)}</td>
                      <td className="max-w-[520px] px-5 py-3.5">
                        <div className="font-medium">{actionLabel(it.action)}{when && <span className="font-normal text-muted"> · {when}</span>}</div>
                        {it.headline && <div className="text-[14px] text-muted">{it.headline}</div>}
                      </td>
                      <td className="px-5 py-3.5"><Risk it={it} /></td>
                      <td className="px-5 py-3.5"><div className="flex flex-wrap gap-x-3 gap-y-1">
                        {it.hardship_flag && it.hardship_flag !== "none" && <Badge kind="hardship">Hardship</Badge>}
                        {it.vulnerable && <Badge kind="vulnerable">Vulnerable</Badge>}
                        <Status it={it} />
                      </div></td>
                      <td className="px-5 py-3.5 text-right"><ChevronRight size={17} aria-hidden className="inline text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-brand" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
            <div className="flex items-center justify-between border-t border-grey-300/60 bg-grey-100/50 px-4 py-2 text-[13.5px] text-muted">
              <span aria-live="polite">Showing {items.length.toLocaleString()} of {total.toLocaleString()}</span>
              {total > items.length && <Button size="sm" variant="ghost" onClick={() => setLimit(limit + PAGE * 2)}>Show more</Button>}
            </div>
          </div>
        )}
      </QueryState>
    </>
  );
}
