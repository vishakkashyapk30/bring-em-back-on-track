import clsx from "clsx";
import { AlertTriangle, Bot, CheckCircle2, Database, FlaskConical, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

export type BadgeKind =
  | "risk" | "bucket" | "consent" | "hardship" | "vulnerable" | "dispute"
  | "llm" | "sql" | "causal" | "observed" | "model-estimate" | "ok" | "danger" | "neutral";

/** Text colour only: no fill, no border, no pill. Colour is reserved for things that need care or action. */
const styles: Record<BadgeKind, string> = {
  risk: "text-brand-700",
  bucket: "text-ink",
  consent: "text-ink",
  hardship: "text-amber",
  vulnerable: "text-amber",
  dispute: "text-ink",
  llm: "text-muted",
  sql: "text-muted",
  causal: "text-teal",
  observed: "text-muted",
  "model-estimate": "text-muted",
  ok: "text-teal",
  danger: "text-danger",
  neutral: "text-ink",
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

/** Fixed-meaning labels. Colour is never the only signal: hardship etc. always carry an icon and text. */
export function Badge({ kind, children }: { kind: BadgeKind; children: ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-[14px] font-semibold", styles[kind])}>
      {icons[kind]}
      {children}
    </span>
  );
}
