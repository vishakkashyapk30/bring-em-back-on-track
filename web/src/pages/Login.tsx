import { ArrowRight, BarChart3, Database, Headset, HeartHandshake, Loader2, UsersRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useLogin } from "@/api/hooks";
import type { Role } from "@/api/types";

const PERSONAS: { role: Role; title: string; home: string; blurb: string; icon: typeof Headset }[] = [
  { role: "agent", title: "Collections agent", home: "/queue", icon: Headset, blurb: "Today's queue, the customer 360, the next best action and post-call summaries." },
  { role: "hardship_specialist", title: "Hardship specialist", home: "/hardship", icon: HeartHandshake, blurb: "Vulnerability review board, missed offers and the plan simulator." },
  { role: "team_lead", title: "Team lead", home: "/team", icon: UsersRound, blurb: "Strategy scorecard, agents, batch approvals and the weather map." },
  { role: "analyst", title: "Strategy analyst", home: "/ask", icon: BarChart3, blurb: "Collections Ask, the weather map, the feature store and governance." },
  { role: "steward", title: "Data steward", home: "/steward/identity", icon: Database, blurb: "Identity review, data quality, the data contract and the audit log." },
];

/** Demo sign-in: pick a persona. In production this is single sign-on with groups mapped to roles. */
export default function Login() {
  const login = useLogin();
  const nav = useNavigate();
  return (
    <div className="mx-auto grid max-w-[1100px] gap-12 py-6 lg:grid-cols-[0.9fr_1.1fr] lg:py-12">
      <div>
        <span aria-hidden className="mb-3 block h-1 w-8 rounded-full bg-brand" />
        <h1 className="m-0 text-[36px] leading-tight tracking-[-0.02em]">Choose who you are</h1>
        <p className="mb-0 mt-3 text-[16px] leading-relaxed text-muted">
          This is a demo sign-in. Each persona sees different screens and can do different things, because access is enforced by role on every request.
        </p>
        <ul className="m-0 mt-6 list-none space-y-2.5 p-0 text-[14px] text-muted">
          <li>Everything you approve, override or review is written to an append-only audit log.</li>
          <li>Data is fully synthetic (Maple Bank, 1,000,000 customers).</li>
          <li>In production this is single sign-on, with groups mapped to roles.</li>
        </ul>
      </div>
      <div className="space-y-3">
        {PERSONAS.map(({ role, title, home, blurb, icon: Icon }) => {
          const busy = login.isPending && login.variables === role;
          return (
            <button key={role} type="button" disabled={login.isPending}
              onClick={() => login.mutate(role, { onSuccess: () => nav(home) })}
              className="group flex w-full items-center gap-4 rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-4 text-left shadow-[var(--shadow-card)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-brand/30 hover:shadow-[var(--shadow-raised)] disabled:opacity-70">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-[var(--radius-md)] bg-brand-50 text-brand"><Icon size={21} aria-hidden /></span>
              <span className="min-w-0 flex-1">
                <span className="block font-[family-name:var(--font-display)] text-[16px] font-semibold">{title}</span>
                <span className="block text-[14px] text-muted">{blurb}</span>
              </span>
              {busy ? <Loader2 size={18} className="animate-spin text-brand" aria-label="Signing in" />
                : <ArrowRight size={18} aria-hidden className="text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-brand" />}
            </button>
          );
        })}
        {login.isError && <p role="alert" className="text-sm text-danger">Sign-in failed. Is the API running?</p>}
      </div>
    </div>
  );
}
