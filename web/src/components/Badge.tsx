import clsx from "clsx";
import { AlertTriangle, Bot, CheckCircle2, Database, FlaskConical, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

export type BadgeKind =
  | "risk" | "bucket" | "consent" | "hardship" | "vulnerable" | "dispute"
  | "llm" | "sql" | "causal" | "observed" | "model-estimate" | "ok" | "danger" | "neutral";

const styles: Record<BadgeKind, string> = {
  risk: "bg-brand-50 text-brand-700",
  bucket: "bg-amber-50 text-amber",
  consent: "bg-teal-50 text-teal",
  hardship: "bg-amber-50 text-amber",
  vulnerable: "bg-amber-50 text-amber",
  dispute: "bg-grey-100 text-ink",
  llm: "bg-gold text-ink",
  sql: "bg-grey-100 text-ink",
  causal: "bg-teal-50 text-teal",
  observed: "bg-grey-100 text-muted",
  "model-estimate": "bg-grey-100 text-muted",
  ok: "bg-teal-50 text-teal",
  danger: "bg-brand-50 text-danger",
  neutral: "bg-grey-100 text-ink",
};
const icons: Partial<Record<BadgeKind, ReactNode>> = {
  hardship: <ShieldAlert size={14} aria-hidden />,
  vulnerable: <ShieldAlert size={14} aria-hidden />,
  llm: <Bot size={14} aria-hidden />,
  sql: <Database size={14} aria-hidden />,
  "model-estimate": <FlaskConical size={14} aria-hidden />,
  ok: <CheckCircle2 size={14} aria-hidden />,
  danger: <AlertTriangle size={14} aria-hidden />,
};

/** Fixed-meaning badges. Colour is never the only signal: hardship etc. always carry an icon + text. */
export function Badge({ kind, children }: { kind: BadgeKind; children: ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-[var(--radius-sm)] px-2 py-0.5 text-sm font-medium", styles[kind])}>
      {icons[kind]}
      {children}
    </span>
  );
}
