import { Copy } from "lucide-react";

import { Badge } from "./Badge";

/** SQL with copy button and its origin (semantic layer vs LLM-written). TODO: syntax highlight. */
export function SqlBlock({ sql, source }: { sql: string; source?: "semantic" | "llm" | null }) {
  return (
    <div className="relative rounded-[var(--radius-md)] bg-navy p-4 text-white">
      <div className="mb-2 flex items-center gap-2">
        {source === "llm" ? <Badge kind="llm">LLM-written SQL</Badge> : <Badge kind="sql">Semantic layer</Badge>}
        <button type="button" onClick={() => navigator.clipboard.writeText(sql)} className="ml-auto inline-flex items-center gap-1 rounded bg-white/10 px-2 py-1 text-sm text-white">
          <Copy size={14} aria-hidden /> Copy
        </button>
      </div>
      <pre className="m-0 overflow-x-auto font-mono text-sm leading-relaxed"><code>{sql}</code></pre>
    </div>
  );
}
