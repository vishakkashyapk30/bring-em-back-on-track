import { Bot, Copy, Database } from "lucide-react";
import { toast } from "sonner";

/** SQL with copy button and its origin (semantic layer vs LLM-written). Light panel in brand cream. */
export function SqlBlock({ sql, source }: { sql: string; source?: "semantic" | "llm" | null }) {
  const copy = () => { navigator.clipboard.writeText(sql); toast.success("SQL copied"); };
  return (
    <div className="relative rounded-[var(--radius-md)] border border-grey-300/70 bg-cream p-4 text-ink">
      <div className="mb-2 flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-muted">
          {source === "llm" ? <><Bot size={14} aria-hidden /> LLM-written SQL</> : <><Database size={14} aria-hidden /> Semantic layer</>}
        </span>
        <button type="button" onClick={copy} className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-[var(--radius-sm)] border border-grey-300 bg-white px-2 text-[13px] text-ink transition-colors hover:bg-grey-100">
          <Copy size={13} aria-hidden /> Copy
        </button>
      </div>
      <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[13px] leading-relaxed"><code>{sql}</code></pre>
    </div>
  );
}
