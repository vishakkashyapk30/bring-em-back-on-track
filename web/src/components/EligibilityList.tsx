import { Check, X } from "lucide-react";

import { Badge } from "./Badge";

type Program = { program_id: string; program_name: string; eligible: boolean; approver_level: string; rules: { rule: string; passed: boolean; value: unknown; limit: unknown }[] };

/** Rule-based eligibility: every rule shown pass/fail with its value (the LLM never decides). */
export function EligibilityList({ programs }: { programs: Program[] }) {
  return (
    <div className="space-y-4">
      {programs.map((p) => (
        <div key={p.program_id}>
          <p className="m-0 font-medium">{p.program_name} <span className="font-mono text-sm text-muted">{p.program_id}</span> {p.eligible ? <Badge kind="ok">Eligible</Badge> : <Badge kind="danger">Not eligible</Badge>}</p>
          <ul className="m-0 mt-1 list-none space-y-1 p-0 text-sm">
            {p.rules.map((r) => (
              <li key={r.rule} className="flex items-center gap-2">
                {r.passed ? <Check size={14} className="shrink-0 text-teal" aria-label="passed" /> : <X size={14} className="shrink-0 text-danger" aria-label="failed" />}
                {r.rule}: {String(r.value)} (limit {String(r.limit)})
              </li>
            ))}
          </ul>
          <p className="m-0 mt-1 text-sm text-muted">Approver: {p.approver_level.replace("_", " ")}</p>
        </div>
      ))}
    </div>
  );
}
