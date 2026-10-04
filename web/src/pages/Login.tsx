import { ArrowRight, BarChart3, Database, Headset, HeartHandshake, Loader2, UsersRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useLogin } from "@/api/hooks";
import type { Role } from "@/api/types";

const PERSONAS: { role: Role; title: string; home: string; blurb: string; icon: typeof Headset }[] = [
  { role: "agent", title: "Collections agent", home: "/queue", icon: Headset, blurb: "Today's queue, each customer's full picture, the suggested next step and call summaries." },
  { role: "hardship_specialist", title: "Hardship specialist", home: "/hardship", icon: HeartHandshake, blurb: "The hardship review board, offers that were missed, and a simulator for payment plans." },
  { role: "team_lead", title: "Team lead", home: "/team", icon: UsersRound, blurb: "How the team is doing, batch approvals, a stress test and the weather map." },
  { role: "analyst", title: "Strategy analyst", home: "/ask", icon: BarChart3, blurb: "Ask questions of the data, the weather map, the feature store and the fairness checks." },
  { role: "steward", title: "Data steward", home: "/steward/identity", icon: Database, blurb: "Customer matches to review, data quality, the data contract and the audit log." },
];

/** Demo sign-in: pick a persona. In production this is single sign-on with groups mapped to roles. */
export default function Login() {
  const login = useLogin();
  const nav = useNavigate();
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
      <div>
        <h1 className="m-0 text-[2.25rem] leading-tight">Who are you today?</h1>
        <p className="mb-0 mt-3 max-w-xl text-[16px] leading-relaxed text-muted">
          This is a demo sign-in, so there is no password. Pick a role to see the app the way that person does. Each role gets different screens and can do different things, and the server checks the role on every request.
        </p>
        <ul className="m-0 mt-6 max-w-xl list-none space-y-2.5 p-0 text-[15px] text-muted">
          <li>Whatever you approve, override or review is written to an audit log that can only be added to.</li>
          <li>All the data is synthetic: one million made-up Maple Bank customers.</li>
          <li>In production, people would sign in with single sign-on and their group would decide the role.</li>
        </ul>
      </div>
      <div className="space-y-3">
        {PERSONAS.map(({ role, title, blurb, icon: Icon }) => {
          const busy = login.isPending && login.variables === role;
          return (
            <div key={role} className="rounded-[var(--radius-lg)] border border-grey-300/70 bg-white transition-colors hover:border-ink/40">
              <button type="button" disabled={login.isPending}
                onClick={() => login.mutate(role, { onSuccess: () => nav("/", { replace: true }) })}
                className="group flex w-full items-center gap-4 rounded-[var(--radius-lg)] p-4 pb-2 text-left disabled:opacity-70">
                <Icon size={22} aria-hidden className="shrink-0 self-start text-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block font-[family-name:var(--font-display)] text-[1.25rem] font-semibold leading-tight">{title}</span>
                  <span className="mt-0.5 block text-[14.5px] text-muted">{blurb}</span>
                </span>
                {busy ? <Loader2 size={18} className="animate-spin text-brand" aria-label="Signing in" />
                  : <ArrowRight size={18} aria-hidden className="text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-brand" />}
              </button>
              <div className="px-4 pb-3 pl-[54px]">
                <button type="button" disabled={login.isPending} onClick={() => login.mutate(role, { onSuccess: () => nav(`/demo/${role}`) })}
                  className="text-[14px] font-semibold text-brand underline-offset-4 hover:underline disabled:opacity-60">
                  Watch this persona's demo
                </button>
              </div>
            </div>
          );
        })}
        {login.isError && <p role="alert" className="text-sm text-danger">We couldn't sign you in. Check that the API is running and try again.</p>}
      </div>
    </div>
  );
}
