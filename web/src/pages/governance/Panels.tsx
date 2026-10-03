import { Fragment } from "react";

import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { StatTiles } from "@/components/StatTiles";
import { QueryState } from "@/components/States";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const n = (v: unknown) => {
  const x = typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : v;
  return typeof x === "number" ? x.toLocaleString() : String(x ?? "n/a");
};
const pct = (v: unknown, d = 1) => (typeof v === "number" ? `${(v * 100).toFixed(d)}%` : "n/a");

/** Data quality report (deliverable 4): every issue with records affected and how it was handled. */
export function Quality() {
  const q = useGet("quality", "/governance/quality");
  const d: Json = q.data ?? {};
  const issues: Json[] = d.issues ?? [];
  const tests: Json[] = d.contract_tests ?? [];
  const id: Json = d.identity ?? {};
  const passed = tests.filter((t) => t.status === "pass").length;
  return (
    <QueryState q={q}>
      <StatTiles items={[
        { label: "Golden customers", value: n(d.c360?.customers), note: `from ${n(id.crm_records)} CRM records` },
        { label: "Accounts linked", value: pct(Number(id.accounts_linked ?? 0) / (Number(id.accounts) || 1)), note: `${n(id.accounts_linked)} of ${n(id.accounts)}` },
        { label: "Issues found", value: n(issues.length), note: "with records affected and handling" },
        { label: "Contract tests", value: `${passed} / ${tests.length}`, note: passed === tests.length ? "all passing" : "failures block publish", status: passed === tests.length ? "ok" : "bad" },
      ]} />
      <h2 className="text-xl">Issues found</h2>
      <DataTable columns={["Issue", "Table(s)", "Records affected", "How we handled it"]}
        rows={issues.map((i) => [i.issue, i.tables, i.records_affected, i.handled])}
        render={(v, col) => (col === "Records affected" ? <span className="tabular">{n(v)}</span> : String(v ?? ""))} />
      <h2 className="mt-8 text-xl">Contract tests (gold.c360_customer)</h2>
      <DataTable columns={["Test", "Status", "Failing rows"]} rows={tests.map((t) => [t.test, t.status, t.failures])}
        render={(v, col) => (col === "Status" ? <Badge kind={v === "pass" ? "ok" : "danger"}>{String(v)}</Badge> : String(v ?? ""))} />
      <p className="text-sm text-muted">Generated {d.generated_at ?? "n/a"} by governance/quality_report.py. Full report: docs/data_quality_report.md.</p>
    </QueryState>
  );
}

/** Benchmark run (deliverable 5): every question, how it was answered, dev-split score. */
export function Benchmark() {
  const q = useGet("benchmark", "/governance/benchmark");
  const d: Json = q.data ?? {};
  const items: Json[] = d.items ?? [];
  const kinds = items.reduce<Record<string, number>>((a, i) => ({ ...a, [i.kind]: (a[i.kind] ?? 0) + 1 }), {});
  return (
    <QueryState q={q}>
      <StatTiles items={[
        { label: "Questions answered", value: n(d.questions), note: Object.entries(kinds).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ") },
        { label: "Dev-split score", value: typeof d.dev_mean_score === "number" ? d.dev_mean_score.toFixed(3) : "n/a", note: `${n(d.dev_scored)} questions with gold answers` },
        { label: "Refused", value: n(d.refused), note: "out of scope, protected or personal data" },
        { label: "Slowest answer", value: items.length ? `${Math.max(...items.map((i) => i.latency_ms ?? 0))} ms` : "n/a" },
      ]} />
      <DataTable columns={["Question", "Split", "Answered as", "Refused", "Dev score", "Latency"]}
        rows={items.map((i) => [i.question_id, i.split, i.kind?.replace("_", " "), i.refused ? "yes" : "no", i.score ?? "hidden", `${i.latency_ms} ms`])} />
      <p className="text-sm text-muted">The submission file is deliverables/benchmark_answers.csv, produced by the system as it is (make benchmark).</p>
    </QueryState>
  );
}

/** Monitoring snapshot: freshness, contract tests, feature parity, text-feature accuracy, benchmark. */
export function Monitoring() {
  const q = useGet("monitoring", "/governance/monitoring");
  const d: Json = q.data ?? {};
  const par: Json = d.feature_parity ?? {};
  const tx: Json = d.text_features ?? {};
  const fresh = d.freshness_hours;
  return (
    <QueryState q={q}>
      <StatTiles items={[
        { label: "Data freshness", value: fresh == null ? "n/a" : `${fresh} h`, note: `SLA ${d.freshness_sla_hours ?? 26} h`, status: fresh != null && fresh > (d.freshness_sla_hours ?? 26) ? "bad" : "ok" },
        { label: "Contract tests", value: `${d.contract_tests?.passed ?? 0} / ${d.contract_tests?.total ?? 0}`, status: d.contract_tests?.passed === d.contract_tests?.total ? "ok" : "bad", note: "gold.c360_customer" },
        { label: "Feature parity", value: par.sampled ? `${par.mismatched_rows} mismatches` : "n/a", note: par.sampled ? `${par.sampled} online rows × ${par.columns_checked} columns recomputed` : "", status: par.ok ? "ok" : "bad" },
        { label: "Benchmark (dev)", value: d.benchmark?.dev_mean_score?.toFixed?.(3) ?? "n/a", note: `${n(d.benchmark?.questions)} questions` },
      ]} />
      <h2 className="text-xl">Text features vs 500 labelled transcripts</h2>
      <DataTable columns={["Field", "Accuracy"]} rows={Object.entries(tx).map(([k, v]) => [k.replace(/_/g, " "), pct(v)])} />
      <Card variant="grey" className="mt-6 text-sm">Model drift and calibration (PSI, Brier) appear here once the promise-break model is trained (Layer 4).</Card>
    </QueryState>
  );
}

/** The data contract (deliverable 3), rendered from docs/contracts/c360_customer.v1.yaml. */
export function Contract() {
  const q = useGet("contract", "/governance/contract");
  const d: Json = q.data ?? {};
  return (
    <QueryState q={q}>
      <Card className="mb-6">
        <h2 className="mt-0 text-xl">{d.product} <span className="font-mono text-base text-muted">{d.contract_id} v{d.version}</span> <Badge kind="neutral">{d.status}</Badge></h2>
        <dl className="m-0 grid gap-x-6 gap-y-2 text-sm md:grid-cols-[180px_1fr]">
          {[["Owner", d.owner], ["Steward", d.steward], ["Policy approver", d.policy_approver], ["Grain", d.grain], ["Refresh", d.refresh], ["Freshness SLA", d.freshness_sla], ["Retention", d.retention], ["Based on", d.based_on]].map(([k, v]) => (
            <Fragment key={String(k)}><dt className="font-medium">{k}</dt><dd className="m-0">{String(v ?? "")}</dd></Fragment>
          ))}
        </dl>
      </Card>
      <h2 className="text-xl">Schema</h2>
      <DataTable columns={["Column", "Type", "PII class", "Source rule"]} rows={(d.schema ?? []).map((c: Json) => [c.name, c.type, c.pii_class, c.source_rule])} />
      <h2 className="mt-8 text-xl">Quality rules</h2>
      <DataTable columns={["#", "Rule", "Severity"]} rows={(d.quality_rules ?? []).map((r: Json) => [r.id, r.rule, r.severity])} />
      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <Card><h3 className="mt-0">Allowed uses</h3><ul className="mb-0">{(d.allowed_uses ?? []).map((u: string) => <li key={u}>{u}</li>)}</ul></Card>
        <Card><h3 className="mt-0">Not allowed</h3><ul className="mb-0">{(d.not_allowed ?? []).map((u: string) => <li key={u}>{u}</li>)}</ul></Card>
      </div>
    </QueryState>
  );
}

export function Fairness() {
  const q = useGet("fairness", "/governance/fairness");
  return (
    <QueryState q={q}>
      <Card variant="grey">The fairness audit (proxy test + outcome test by group, aggregates only, groups under 10 suppressed) runs against the promise-break model and the next-best-action decisions, which are being built in Layer 4. Protected attributes are already excluded from every feature, model input and Ask query (constraint tests).</Card>
    </QueryState>
  );
}

/** Append-only audit log (ops.db), newest first. */
export function Audit() {
  const q = useGet("audit", "/governance/audit");
  const items: Json[] = q.data?.items ?? [];
  return (
    <QueryState q={q} empty={items.length === 0}>
      <DataTable columns={["#", "When (UTC)", "Who", "Role", "Event", "Subject"]}
        rows={items.map((a) => [a.audit_id, a.ts, a.user_id, a.role, a.event_type, [a.entity_type, a.entity_id].filter(Boolean).join(" ")])} />
    </QueryState>
  );
}
