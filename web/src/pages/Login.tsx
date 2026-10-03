import { useNavigate } from "react-router-dom";

import { useLogin } from "@/api/hooks";
import type { Role } from "@/api/types";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";

const PERSONAS: { role: Role; title: string; home: string; blurb: string }[] = [
  { role: "agent", title: "Collections agent", home: "/queue", blurb: "Queue, customer 360, next best action" },
  { role: "hardship_specialist", title: "Hardship specialist", home: "/hardship", blurb: "Review board, missed offers, plan simulator" },
  { role: "team_lead", title: "Team lead", home: "/team", blurb: "Batch approvals, employer radar, stress test" },
  { role: "analyst", title: "Strategy analyst", home: "/ask", blurb: "Collections Ask, scorecard, weather map" },
  { role: "steward", title: "Data steward", home: "/governance", blurb: "Identity review, quality, contract, audit" },
];

/** Demo role picker (team-card style). Production = SSO. */
export default function Login() {
  const login = useLogin();
  const nav = useNavigate();
  return (
    <div className="mx-auto max-w-[1100px] px-6 py-12">
      <SectionTag as="h1" subtitle="Demo sign-in. Pick a persona; what you can see depends on the role.">Sign in</SectionTag>
      <div className="grid gap-6 md:grid-cols-3">
        {PERSONAS.map((p) => (
          <button key={p.role} type="button" className="text-left" onClick={() => login.mutate(p.role, { onSuccess: () => nav(p.home) })}>
            <Card hard className="h-full hover:bg-brand-50">
              <h3 className="mt-0">{p.title}</h3>
              <hr className="border-ink/20" />
              <p className="mb-0 text-muted">{p.blurb}</p>
            </Card>
          </button>
        ))}
      </div>
    </div>
  );
}
