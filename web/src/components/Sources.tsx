import { FileText, MessageSquareQuote, Table2, Database, ListChecks } from "lucide-react";
import type { ReactNode } from "react";

/** One source behind an answer. Shapes: policy {doc_id, section, quote}; interaction {source, doc_id, turn_index,
 *  label, quote, speaker, ts}; sql and table (model-written SQL); step {tool, label} (assistant run). */
export type Citation = Record<string, unknown>;

const str = (v: unknown): string => (v == null ? "" : String(v));
/** Policy quotes come from Markdown: show them as plain text. */
export const plain = (v: string): string => v.replace(/\*\*|__/g, "");

function heading(c: Citation): { icon: ReactNode; title: string } {
  const kind = str(c.kind);
  if (kind === "sql") return { icon: <Database size={14} aria-hidden />, title: "Query that produced the numbers" };
  if (kind === "table") return { icon: <Table2 size={14} aria-hidden />, title: str(c.label) || str(c.ref) };
  if (kind === "data") return { icon: <Database size={14} aria-hidden />, title: `Data product: ${str(c.ref) || str(c.label)}` };
  if (kind === "step") return { icon: <ListChecks size={14} aria-hidden />, title: str(c.label) || str(c.tool) };
  if (c.source) {
    const who = str(c.speaker) ? `, ${str(c.speaker)}` : "";
    return { icon: <MessageSquareQuote size={14} aria-hidden />, title: str(c.label) || `${str(c.source)} ${str(c.doc_id)}${who}` };
  }
  const turn = str(c.section).startsWith("turn");
  return { icon: turn ? <MessageSquareQuote size={14} aria-hidden /> : <FileText size={14} aria-hidden />,
    title: [turn && str(c.doc_id) ? `Call ${str(c.doc_id)}` : str(c.doc_id), str(c.section)].filter(Boolean).join(", ") };
}

/** The Sources block: every answer a language model words lists what it was grounded on, with the quoted text. */
export function Sources({ citations, label = "Sources", level = 3 }: { citations?: Citation[]; label?: string; level?: 2 | 3 }) {
  const H = level === 2 ? "h2" : "h3";
  const list = (citations ?? []).filter((c) => c && Object.keys(c).length > 0 && heading(c).title.trim() !== "");
  if (list.length === 0) return null;
  return (
    <section aria-label={label} className="rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4">
      <H className="m-0 mb-2 font-[family-name:var(--font-sans)] text-[14px] font-semibold">{label}</H>
      <ol className="m-0 list-none space-y-2.5 p-0">
        {list.map((c, i) => {
          const h = heading(c);
          const isSqlRaw = str(c.kind) === "sql";
          const raw = isSqlRaw ? str(c.quote) || str(c.ref) || str(c.sql) : plain(str(c.quote));
          const tables = isSqlRaw && Array.isArray(c.tables) ? (c.tables as unknown[]).map(str).filter(Boolean) : [];
          const quote = raw && raw.trim() === h.title.trim() ? "" : raw; // a table's label and quote are the same text
          const isSql = str(c.kind) === "sql";
          return (
            <li key={i} className="text-[13.5px]">
              <p className="m-0 flex items-center gap-1.5 font-medium text-ink"><span className="text-muted">{h.icon}</span>{h.title}</p>
              {quote && (isSql
                ? <pre className="m-0 mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] bg-grey-100 p-2 font-mono text-[12.5px]"><code>{quote}</code></pre>
                : <blockquote className="m-0 mt-1 border-l-2 border-brand/40 pl-2.5 text-muted">{quote}</blockquote>)}
              {tables.length > 0 && <p className="m-0 mt-1 text-[12.5px] text-muted">Tables: {tables.join(", ")}</p>}
              {str(c.ts) && <p className="m-0 mt-0.5 text-[12px] text-muted">{str(c.ts).slice(0, 16).replace("T", " ")}</p>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
