import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Evidence } from "@/api/assistant";

import { cell } from "./helpers";

export const hasEvidence = (e?: Evidence | null) =>
  !!e && !!((e.columns?.length && e.rows?.length) || e.kv?.length || e.text || e.links?.length);

const ROWS_SHOWN = 8;
const ID = /^[A-Z]{1,4}-[A-Z0-9-]+$/;
const SNAKE = /^[a-z]+(_[a-z0-9]+)+(\b.*)?$/;
/** Table cell text: codes like "specialist_referral" read as words, IDs never wrap. */
const show = (v: unknown) => (typeof v === "string" && SNAKE.test(v) ? v.replace(/_/g, " ") : cell(v));

/** The real numbers behind a step: a table, key values, a text or SQL block, and links to the screen. */
export function EvidenceView({ evidence: e, dense = false }: { evidence?: Evidence | null; dense?: boolean }) {
  const [all, setAll] = useState(false);
  if (!hasEvidence(e) || !e) return null;
  const rows = e.rows ?? [];
  const shown = all ? rows : rows.slice(0, ROWS_SHOWN);
  const th = "whitespace-nowrap px-3 py-2 text-left text-[13px] font-semibold text-ink";
  return (
    <div className="flex flex-col gap-3 text-[14px]">
      {e.kv && e.kv.length > 0 && (
        <dl className={`m-0 grid gap-x-6 gap-y-1.5 ${dense ? "grid-cols-1" : "sm:grid-cols-2"}`}>
          {e.kv.map(([k, v], i) => (
            <div key={`${k}-${i}`} className="flex min-w-0 items-baseline justify-between gap-3 border-b border-grey-300/50 pb-1.5">
              <dt className="shrink-0 text-muted">{k}</dt>
              <dd className="m-0 min-w-0 break-words text-right font-medium tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {e.columns && rows.length > 0 && (
        <div>
          <div className="overflow-x-auto rounded-[var(--radius-md)] border border-grey-300/70 bg-white" tabIndex={0} role="region" aria-label="Evidence table, scrolls sideways">
            <table className="w-full border-collapse">
              <thead className="bg-white shadow-[inset_0_-2px_0_var(--color-ink)]"><tr>{e.columns.map((c) => <th key={c} scope="col" className={th}>{c}</th>)}</tr></thead>
              <tbody>
                {shown.map((r, i) => (
                  <tr key={i} className="border-t border-grey-300/50">
                    {r.map((v, j) => (
                      <td key={j} className={`px-3 py-2 align-top ${typeof v === "number" ? "text-right tabular-nums" : typeof v === "string" && ID.test(v) ? "whitespace-nowrap font-mono text-[13px]" : "min-w-[8rem]"}`}>{show(v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > ROWS_SHOWN && (
            <button type="button" onClick={() => setAll(!all)} className="mt-1.5 text-[13px] font-semibold text-brand underline-offset-4 hover:underline">
              {all ? `Show the first ${ROWS_SHOWN} rows` : `Show all ${rows.length} rows`}
            </button>
          )}
        </div>
      )}
      {e.text && (
        <pre tabIndex={0} aria-label="Detail text" className="m-0 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-[var(--radius-md)] bg-navy p-3 font-mono text-[12.5px] leading-relaxed text-white">{e.text}</pre>
      )}
      {e.links && e.links.length > 0 && (
        <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
          {e.links.map((l) => (
            <li key={l.href + l.label}>
              <Link to={l.href} className="inline-flex items-center gap-1 font-semibold text-brand underline-offset-4 hover:underline">{l.label}<ExternalLink size={13} aria-hidden /></Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Evidence behind a "Show evidence" toggle. */
export function EvidenceToggle({ evidence, id }: { evidence?: Evidence | null; id: string }) {
  const [open, setOpen] = useState(false);
  if (!hasEvidence(evidence)) return null;
  return (
    <div className="mt-2">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 text-[13.5px] font-semibold text-brand underline-offset-4 hover:underline">
        <ChevronDown size={15} aria-hidden className={`transition-transform ${open ? "rotate-180" : ""}`} />{open ? "Hide evidence" : "Show evidence"}
      </button>
      <div id={id} hidden={!open} className="mt-2">{open && <EvidenceView evidence={evidence} dense />}</div>
    </div>
  );
}
