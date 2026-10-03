import { Fragment, useState } from "react";

import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { ModelEval } from "@/components/ModelEval";
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
      <DataTable searchable="Search issues" columns={["Issue", "Table(s)", "Records affected", "How we handled it"]}
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
      <DataTable searchable="Search questions" filters={[{ id: "dev", label: "Dev split", test: (r) => r[1] === "dev" }, { id: "refused", label: "Refused", test: (r) => r[3] === "yes" }, { id: "sql", label: "Answered with SQL", test: (r) => String(r[2]).includes("sql") }]} columns={["Question", "Split", "Answered as", "Refused", "Dev score", "Latency"]}
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
      <h2 className="mt-8 text-xl">Promise-break model</h2>
      <ModelEval />
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

const ATTR_LABEL: Record<string, string> = {
  gender_code: "Gender", age_band: "Age band", marital_status: "Marital status", citizenship_status: "Citizenship",
  newcomer_program_flag: "Newcomer", accessibility_needs_flag: "Accessibility needs", vulnerability_type: "Vulnerability type",
  household_size: "Household size", dependants_count: "Dependants",
};
const signed = (v: unknown) => (typeof v === "number" ? `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)} pts` : "n/a");

/** Fairness audit: can the features stand in for a protected attribute (proxy test), and does the promise-break
 * score treat groups the same once it meets real outcomes (outcome test). Aggregates only; small groups hidden. */
export function Fairness() {
  const q = useGet("fairness", "/governance/fairness");
  const d: Json = q.data ?? {};
  const live = d.proxy && !Array.isArray(d.proxy);
  const proxy: Json[] = live ? d.proxy.groups ?? [] : [];
  const attrs: Json[] = live ? d.outcome?.attributes ?? [] : [];
  const [attr, setAttr] = useState("vulnerability_type");
  const cur = attrs.find((a) => a.attribute === attr) ?? attrs[0];
  const review: string[] = d.review_items ?? [];
  const o: Json = d.outcome?.overall ?? {};
  return (
    <QueryState q={q}>
      {!live ? (
        <Card variant="grey">The fairness audit has not been run yet. Run <code>python -m governance.fairness.report</code>.</Card>
      ) : (
        <>
          <StatTiles items={[
            { label: "Feature groups tested", value: String(proxy.length), note: `${proxy.filter((g) => g.decision === "review").length} above the ${d.proxy.threshold} AUC line`, status: proxy.some((g) => g.decision === "review") ? "warn" : "ok" },
            { label: "Highest proxy AUC", value: Math.max(...proxy.map((g) => g.max_auc)).toFixed(3), note: "0.5 means no signal; line is 0.65", status: "ok" },
            { label: "Test promises audited", value: n(d.outcome?.promises), note: `${d.outcome?.test_period}, ${n(o.customers)} customers` },
            { label: "Groups for review", value: String(review.filter((r) => !r.includes("predicts")).length), note: "a person looks and explains", status: review.length ? "warn" : "ok" },
          ]} />
          <h2 className="text-xl">Proxy test</h2>
          <p className="text-[14px] text-muted">For each group of features, a simple model tries to predict each protected attribute from that group alone ({n(d.proxy.customers)} customers, 5-fold cross-validation). AUC above {d.proxy.threshold} sends the group to review; it is never an automatic drop.</p>
          <DataTable columns={["Feature group", "Features", "Highest AUC", "Predicts best", "Decision"]}
            rows={proxy.map((g) => [g.group.replace(/_/g, " "), g.n_features, g.max_auc.toFixed(3), ATTR_LABEL[g.worst_attribute] ?? g.worst_attribute, g.decision])}
            render={(v, c) => (c === "Decision" ? <Badge kind={v === "keep" ? "ok" : "danger"}>{v === "keep" ? "Keep" : "Review"}</Badge> : String(v ?? "n/a"))} />
          <h2 className="mt-8 text-xl">Outcome test</h2>
          <p className="text-[14px] text-muted">On the {n(d.outcome?.promises)} promises due {d.outcome?.test_period}, by group: how often the promise was broken, how the score compared, and how often the group was flagged high risk (score of {d.outcome?.thresholds?.flag_at} or more). Overall the score runs {Math.abs(o.calibration_gap * 100).toFixed(1)} points {o.calibration_gap < 0 ? "below" : "above"} reality, so a group is flagged for review only when its gap differs from that by more than {d.outcome?.thresholds?.calibration_gap * 100} points, or its flag rate is outside {d.outcome?.thresholds?.flag_ratio?.[0]}x to {d.outcome?.thresholds?.flag_ratio?.[1]}x of everyone's.</p>
          <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1" role="group" aria-label="Protected attribute">
            {attrs.map((a) => (
              <button key={a.attribute} type="button" aria-pressed={cur?.attribute === a.attribute} onClick={() => setAttr(a.attribute)}
                className={`h-9 border-b-2 pb-1 pt-1.5 text-[14.5px] transition-colors ${cur?.attribute === a.attribute ? "border-brand font-semibold text-ink" : "border-transparent font-medium text-ink/70 hover:border-grey-300 hover:text-ink"}`}>
                {ATTR_LABEL[a.attribute] ?? a.attribute}{a.reviews > 0 && <span className="ml-1.5 text-brand-700" aria-label={`${a.reviews} to review`}>•</span>}
              </button>
            ))}
          </div>
          {cur && (
            <DataTable columns={["Group", "Promises", "Broke", "Predicted", "Excess gap", "Flagged", "vs all", "Caught", "False alarms", "Calls / 30d", "Status"]}
              rows={cur.groups.map((r: Json) => [r.group, r.promises, pct(r.break_rate), pct(r.predicted), signed(r.excess_gap), pct(r.flag_rate), r.flag_ratio == null ? "n/a" : `${r.flag_ratio.toFixed(2)}x`, pct(r.tpr), pct(r.fpr), r.attempts_30d.toFixed(1), r.status])}
              render={(v, c) => (c === "Status" ? <Badge kind={v === "ok" ? "ok" : v === "review" ? "danger" : "neutral"}>{v === "ok" ? "OK" : v === "review" ? "Review" : "Low volume"}</Badge> : String(v ?? "n/a"))} />
          )}
          {cur?.suppressed_groups > 0 && <p className="mt-2 text-[13px] text-muted">{cur.suppressed_groups} group(s) with fewer than 10 customers are hidden.</p>}
          {review.some((r) => r.startsWith("vulnerability_type")) && (
            <Card variant="grey" className="mt-6">
              <h3 className="mt-0">What we found, and what it means</h3>
              <p className="mb-2">Customers with a recorded vulnerability break more promises than others (about 72 to 75% against 63%) and the score flags them more often. That follows reality, but the score under-predicts their breaks by a further 3 to 4 points and gives them more false alarms.</p>
              <p className="mb-0">This is acceptable only because a higher break risk never raises pressure: the policy gate runs first, vulnerable and hardship customers get gentler treatment, and risk only decides whether to add a reminder or a person's follow-up. The review is to confirm that in the decisions once Layer 4 produces them, and to recalibrate by segment if the gap persists.</p>
            </Card>
          )}
          <p className="mt-4 text-[13px] text-muted">{d.note} Next-best-action rates by group (pressure actions, contact rates, overrides) are added when Layer 4 decisions exist for the test period.</p>
        </>
      )}
    </QueryState>
  );
}

/** Append-only audit log (ops.db), newest first. */
export function Audit() {
  const q = useGet("audit", "/governance/audit");
  const items: Json[] = q.data?.items ?? [];
  return (
    <QueryState q={q} empty={items.length === 0}>
      <DataTable searchable="Search who, event or subject" filters={[{ id: "decisions", label: "Decisions", test: (r) => String(r[4]).includes("decision") || ["edit", "override"].includes(String(r[4])) }, { id: "hardship", label: "Hardship", test: (r) => String(r[4]).includes("hardship") }, { id: "batch", label: "Batches", test: (r) => String(r[4]).includes("batch") }, { id: "sim", label: "Simulator", test: (r) => String(r[4]).includes("simulator") }]} columns={["#", "When (UTC)", "Who", "Role", "Event", "Subject"]}
        rows={items.map((a) => [a.audit_id, a.ts, a.user_id, a.role, a.event_type, [a.entity_type, a.entity_id].filter(Boolean).join(" ")])} />
    </QueryState>
  );
}
