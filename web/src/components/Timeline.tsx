import { Bell, Mail, MessageSquare, Phone, Smartphone, Zap } from "lucide-react";
import { Link } from "react-router-dom";

const ICON: Record<string, JSX.Element> = {
  call: <Phone size={16} />, sms: <MessageSquare size={16} />, email: <Mail size={16} />,
  push: <Smartphone size={16} />, system: <Zap size={16} />, letter: <Bell size={16} />,
};

type Item = { date: string; type: string; text: string; contact_id?: string; transcript_id?: string; severity?: string };

export function Timeline({ items }: { items: Item[] }) {
  return (
    <ol className="m-0 list-none space-y-3 p-0">
      {items.map((it, i) => (
        <li key={i} className="flex gap-3">
          <span className="w-16 shrink-0 text-sm text-muted tabular">{new Date(it.date).toLocaleDateString("en-CA", { day: "numeric", month: "short" })}</span>
          <span aria-hidden className={it.severity === "high" ? "text-danger" : ""}>{ICON[it.type] ?? <Zap size={16} />}</span>
          <span className="flex-1">
            <span className="sr-only">{it.type}: </span>{it.text}
            {it.contact_id && <> · <Link to={`/calls/${it.contact_id}`} className="text-brand">transcript {it.transcript_id}</Link></>}
          </span>
        </li>
      ))}
    </ol>
  );
}
