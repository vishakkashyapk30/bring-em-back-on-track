import clsx from "clsx";
import { Bell, ChevronRight, Mail, MessageSquare, Phone, Smartphone, Zap } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

const ICON: Record<string, typeof Phone> = { call: Phone, sms: MessageSquare, email: Mail, push: Smartphone, system: Zap, letter: Bell };
const LABEL: Record<string, string> = { call: "Call", sms: "SMS", email: "Email", push: "App notification", system: "System event", letter: "Letter", ivr: "Phone menu", chat: "Chat" };

type Item = { date: string; type: string; text: string; contact_id?: string | null; transcript_id?: string | null; severity?: string | null };

/** Contact timeline: a vertical rail, one row per contact, newest first; calls with a transcript open the summary. */
export function Timeline({ items, initial = 8 }: { items: Item[]; initial?: number }) {
  const [n, setN] = useState(initial);
  if (!items.length) return <p className="text-sm text-muted">No contacts recorded.</p>;
  return (
    <div>
      <ol className="relative m-0 list-none p-0">
        <span aria-hidden className="absolute bottom-3 left-[15px] top-3 w-px bg-grey-300" />
        {items.slice(0, n).map((it, i) => {
          const Icon = ICON[it.type] ?? Zap;
          const d = new Date(it.date);
          return (
            <li key={i} className="relative flex gap-3 py-2.5">
              <span className={clsx("z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full border bg-white",
                it.severity === "high" ? "border-brand/40 text-brand" : "border-grey-300 text-muted")}><Icon size={15} aria-hidden /></span>
              <div className="min-w-0 flex-1 pt-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[13px] font-medium text-ink">{LABEL[it.type] ?? it.type}</span>
                  <time dateTime={it.date} className="shrink-0 text-[12.5px] text-muted tabular">
                    {d.toLocaleDateString("en-CA", { day: "numeric", month: "short", year: d.getFullYear() !== 2026 ? "numeric" : undefined })}
                  </time>
                </div>
                <p className="m-0 text-[14px] text-ink/85">{it.text}</p>
                {it.contact_id && (
                  <Link to={`/calls/${it.contact_id}`} className="mt-1 inline-flex items-center gap-0.5 text-[13px] font-medium">
                    Read the call summary <ChevronRight size={14} aria-hidden />
                  </Link>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {items.length > n && (
        <button type="button" onClick={() => setN(n + 10)} className="mt-1 w-full rounded-[var(--radius-md)] py-2 text-[13.5px] font-medium text-brand transition-colors hover:bg-brand-50">
          Show {Math.min(10, items.length - n)} more
        </button>
      )}
    </div>
  );
}
