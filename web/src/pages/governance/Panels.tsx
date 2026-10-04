import { Fragment, useState } from "react";

import { useGet } from "@/api/hooks";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { ModelEval } from "@/components/ModelEval";
import { StatTiles } from "@/components/StatTiles";
import { SectionTag } from "@/components/SectionTag";
import { Footnote, QueryState } from "@/components/States";
import { PageTabs } from "@/components/Tabs";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const n = (v: unknown) => {
  const x = typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : v;
  return typeof x === "number" ? x.toLocaleString() : String(x ?? "n/a");
};
const title = (v: unknown) => (typeof v === "string" && v ? v.charAt(0).toUpperCase() + v.slice(1) : String(v ?? ""));
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
      <PageTabs variant="segmented" label="Data quality sections" param="view" tabs={[{ id: "issues", label: "Issues found", count: issues.length }, { id: "tests", label: "Contract tests", count: tests.length }]}>
        {(view) => view === "issues" ? (
          <DataTable searchable="Search issues" columns={["Issue", "Table(s)", "Records affected", "How we handled it"]}
            rows={issues.map((i) => [i.issue, i.tables, i.records_affected, i.handled])}
            render={(v, col) => (col === "Records affected" ? <span className="tabular">{n(v)}</span> : String(v ?? ""))} />
        ) : (
          <>
            <p className="mb-3 mt-0 text-[13.5px] text-muted">Tests on <code>gold.c360_customer</code>. A failure blocks the nightly publish.</p>
            <DataTable columns={["Test", "Status", "Failing rows"]} rows={tests.map((t) => [t.test, t.status, t.failures])}
              render={(v, col) => (col === "Status" ? <Badge kind={v === "pass" ? "ok" : "danger"}>{v === "pass" ? "Pass" : "Fail"}</Badge> : col === "Test" ? <code className="text-[13px]">{String(v)}</code> : String(v ?? ""))} />
          </>
        )}
      </PageTabs>
      <Footnote>Generated {d.generated_at ?? "n/a"} by governance/quality_report.py. Full report: docs/data_quality_report.md.</Footnote>
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
      <Footnote>The submission file is deliverables/benchmark_answers.csv, produced by the system as it is (make benchmark).</Footnote>
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
  const g: Json = d.guardrails ?? {};
  const zero = (v: unknown) => (v === 0 ? "ok" : "bad") as "ok" | "bad";
  return (
    <QueryState q={q}>
      {d.guardrails && (
        <>
          <SectionTag subtitle="Three counters must stay at zero. Agents' overrides above 25% go to a review.">Guardrails and overrides</SectionTag>
          <StatTiles items={[
            { label: "Override rate", value: (g.decisions_reviewed ?? 0) < 20 ? `${n(g.overrides)} of ${n(g.decisions_reviewed)}` : pct(g.override_rate), note: g.override_rate == null ? "No decisions yet" : g.override_review_triggered ? `Above ${pct(g.override_review_threshold, 0)}: review (${n(g.overrides)} of ${n(g.decisions_reviewed)})` : `${n(g.overrides)} of ${n(g.decisions_reviewed)} decisions`, status: g.override_review_triggered ? "warn" : "ok" },
            { label: "Pressure while in hardship", value: n(g.pressure_on_hardship_count), note: "Must be 0", status: zero(g.pressure_on_hardship_count) },
            { label: "Contact cap breaches", value: n(g.contact_cap_breach_count), note: "Must be 0", status: zero(g.contact_cap_breach_count) },
            { label: "Calls outside hours", value: n(g.out_of_hours_contact_count), note: "Must be 0", status: zero(g.out_of_hours_contact_count) },
            { label: "Complaints per 1,000 contacts", value: g.complaints?.per_1000 == null ? "n/a" : String(g.complaints.per_1000), note: g.complaints?.contacts ? `${n(g.complaints.complaints)} in ${n(g.complaints.contacts)} outbound contacts` : "" },
            { label: "Refusals", value: n(g.refusal_count), note: "Questions and actions turned down" },
            { label: "Hardship recall", value: pct(g.hardship_recall), note: "On the hand-labelled call sample" },
            { label: "Score drift (PSI)", value: g.psi == null ? "n/a" : String(g.psi), note: g.psi == null ? "Not computed yet" : "" },
          ]} />
        </>
      )}
      <StatTiles items={[
        { label: "Data freshness", value: fresh == null ? "n/a" : `${fresh} h`, note: `SLA ${d.freshness_sla_hours ?? 26} h`, status: fresh != null && fresh > (d.freshness_sla_hours ?? 26) ? "bad" : "ok" },
        { label: "Contract tests", value: `${d.contract_tests?.passed ?? 0} / ${d.contract_tests?.total ?? 0}`, status: d.contract_tests?.passed === d.contract_tests?.total ? "ok" : "bad", note: "gold.c360_customer" },
        { label: "Feature parity", value: par.sampled ? `${par.mismatched_rows} mismatches` : "n/a", note: par.sampled ? `${par.sampled} online rows × ${par.columns_checked} columns recomputed` : "", status: par.ok ? "ok" : "bad" },
        { label: "Benchmark (dev)", value: d.benchmark?.dev_mean_score?.toFixed?.(3) ?? "n/a", note: `${n(d.benchmark?.questions)} questions` },
      ]} />
      <SectionTag>Promise-break model</SectionTag>
      <ModelEval />
      <SectionTag className="mt-8" subtitle="How often the rules that read call notes agree with 500 transcripts labelled by hand.">Text features</SectionTag>
      <Card>
        <dl className="m-0 grid gap-x-8 text-[14px] sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(tx).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 border-b border-grey-300/60 py-2"><dt>{k.replace(/_/g, " ")}</dt><dd className="m-0 font-medium tabular">{pct(v)}</dd></div>
          ))}
        </dl>
      </Card>
    </QueryState>
  );
}

/** The data contract (deliverable 3), rendered from docs/contracts/c360_customer.v1.yaml. */
export function Contract() {
  const q = useGet("contract", "/governance/contract");
  const d: Json = q.data ?? {};
  return (
    <QueryState q={q}>
      <div className="mb-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 mt-0 flex flex-wrap items-baseline gap-x-3 text-[1.0625rem]"><span className="font-mono">{d.product}</span> <span className="font-mono text-[13.5px] font-normal text-muted">{d.contract_id} v{d.version}</span> <Badge kind="neutral">{title(d.status)}</Badge></h2>
          <dl className="m-0 grid gap-x-6 gap-y-1.5 text-[14px] md:grid-cols-[160px_1fr]">
            {[["Owner", d.owner], ["Steward", d.steward], ["Policy approver", d.policy_approver], ["Grain", d.grain], ["Refresh", d.refresh], ["Freshness SLA", d.freshness_sla], ["Retention", d.retention], ["Based on", d.based_on]].map(([k, v]) => (
              <Fragment key={String(k)}><dt className="text-muted">{k}</dt><dd className="m-0">{String(v ?? "")}</dd></Fragment>
            ))}
          </dl>
        </Card>
        <Card className="h-full">
          <h3 className="mb-1.5 mt-0">Allowed uses</h3>
          <ul className="mb-4 mt-0 space-y-0.5 pl-5 text-[14px]">{(d.allowed_uses ?? []).map((u: string) => <li key={u}>{u}</li>)}</ul>
          <h3 className="mb-1.5 mt-0">Not allowed</h3>
          <ul className="m-0 space-y-0.5 pl-5 text-[14px]">{(d.not_allowed ?? []).map((u: string) => <li key={u}>{u}</li>)}</ul>
        </Card>
      </div>
      <PageTabs variant="segmented" label="Contract sections" param="view" tabs={[{ id: "schema", label: "Schema", count: (d.schema ?? []).length }, { id: "rules", label: "Quality rules", count: (d.quality_rules ?? []).length }]}>
        {(view) => view === "schema"
          ? <DataTable columns={["Column", "Type", "PII class", "Source rule"]} rows={(d.schema ?? []).map((c: Json) => [c.name, c.type, c.pii_class, c.source_rule])} render={(v, col) => (col === "Column" ? <code className="text-[13px]">{String(v)}</code> : String(v ?? ""))} />
          : <DataTable columns={["#", "Rule", "Severity"]} rows={(d.quality_rules ?? []).map((r: Json) => [r.id, r.rule, r.severity])} render={(v, col) => (col === "Severity" ? (v === "error" ? <Badge kind="danger">Error</Badge> : <Badge kind="neutral">Warning</Badge>) : String(v ?? ""))} />}
      </PageTabs>
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
  const nq = useGet("fairness-nba", "/governance/fairness/nba");
  const nba: Json = nq.data ?? {};
  const d: Json = q.data ?? {};
  const live = d.proxy && !Array.isArray(d.proxy);
  const proxy: Json[] = live ? d.proxy.groups ?? [] : [];
  const attrs: Json[] = live ? d.outcome?.attributes ?? [] : [];
  const [attr, setAttr] = useState("vulnerability_type");
  const cur = attrs.find((a) => a.attribute === attr) ?? attrs[0];
  const review: string[] = d.review_items ?? [];
  const o: Json = d.outcome?.overall ?? {};
  const modelReviews = review.filter((r) => !r.includes("predicts")).length;
  const nbaReviews = (nba.attributes ?? []).flatMap((a: Json) => a.groups ?? []).filter((g: Json) => g.status === "review" && !g.by_design).length;
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
            { label: "Groups for review", value: String(modelReviews + nbaReviews), note: `${modelReviews} in the promise score, ${nbaReviews} in NBA decisions (by-design groups not counted)`, status: modelReviews + nbaReviews ? "warn" : "ok" },
          ]} />
          <PageTabs variant="segmented" label="Fairness tests" param="view" tabs={[{ id: "outcome", label: "Outcome test" }, { id: "proxy", label: "Proxy test" }, { id: "nba", label: "NBA decisions" }]}>
            {(view) => view === "nba" ? <NbaFairness d={nba} loading={nq.isLoading} /> : view === "proxy" ? (
              <>
          <p className="mb-3 mt-0 max-w-4xl text-[14px] text-muted">For each group of features, a simple model tries to predict each protected attribute from that group alone ({n(d.proxy.customers)} customers, 5-fold cross-validation). AUC above {d.proxy.threshold} sends the group to review; it is never an automatic drop.</p>
          <DataTable columns={["Feature group", "Features", "Highest AUC", "Predicts best", "Decision"]}
            rows={proxy.map((g) => [g.group.replace(/_/g, " "), g.n_features, g.max_auc.toFixed(3), ATTR_LABEL[g.worst_attribute] ?? g.worst_attribute, g.decision])}
            render={(v, c) => (c === "Decision" ? <Badge kind={v === "keep" ? "ok" : "danger"}>{v === "keep" ? "Keep" : "Review"}</Badge> : String(v ?? "n/a"))} />
              </>
            ) : (
              <>
          <p className="mb-3 mt-0 max-w-4xl text-[14px] text-muted">On the {n(d.outcome?.promises)} promises due {d.outcome?.test_period}, by group: how often the promise was broken, how the score compared, and how often the group was flagged high risk (score of {d.outcome?.thresholds?.flag_at} or more). Overall the score runs {Math.abs(o.calibration_gap * 100).toFixed(1)} points {o.calibration_gap < 0 ? "below" : "above"} reality, so a group is flagged for review only when its gap differs from that by more than {d.outcome?.thresholds?.calibration_gap * 100} points, or its flag rate is outside {d.outcome?.thresholds?.flag_ratio?.[0]}x to {d.outcome?.thresholds?.flag_ratio?.[1]}x of everyone's.</p>
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
              rows={cur.groups.map((r: Json) => [String(r.group).replace(/_/g, " "), n(r.promises), pct(r.break_rate), pct(r.predicted), signed(r.excess_gap), pct(r.flag_rate), r.flag_ratio == null ? "n/a" : `${r.flag_ratio.toFixed(2)}x`, pct(r.tpr), pct(r.fpr), r.attempts_30d.toFixed(1), r.status])}
              render={(v, c) => (c === "Status" ? <Badge kind={v === "ok" ? "ok" : v === "review" ? "danger" : "neutral"}>{v === "ok" ? "OK" : v === "review" ? "Review" : "Low volume"}</Badge> : String(v ?? "n/a"))} />
          )}
          {cur?.suppressed_groups > 0 && <Footnote>{cur.suppressed_groups} group(s) with fewer than 10 customers are hidden.</Footnote>}
          {review.some((r) => r.startsWith("vulnerability_type")) && (
            <Card variant="grey" className="mt-6">
              <h2 className="mt-0 text-[18px]">What we found, and what it means</h2>
              <p className="mb-2">Customers with a recorded vulnerability break more promises than others (about 72 to 75% against 63%) and the score flags them more often. That follows reality, but the score under-predicts their breaks by a further 3 to 4 points and gives them more false alarms.</p>
              <p className="mb-0">This is acceptable only because a higher break risk never raises pressure: the policy gate runs first, vulnerable and hardship customers get gentler treatment, and risk only decides whether to add a reminder or a person's follow-up. The review is to confirm that in the decisions once Layer 4 produces them, and to recalibrate by segment if the gap persists.</p>
            </Card>
          )}
              </>
            )}
          </PageTabs>
          <Footnote className="mt-4">{d.note}</Footnote>
        </>
      )}
    </QueryState>
  );
}

/** Next-best-action decisions by group: does the queue treat groups the same way, and does higher risk ever raise
 * pressure for a hardship or vulnerable customer. Aggregates only. */
function NbaFairness({ d, loading }: { d: Json; loading: boolean }) {
  const [attr, setAttr] = useState("vulnerability_type");
  if (!d.design_claim) {
    return loading ? null : <Card variant="grey">The NBA fairness report has not been run yet. Run <code>python -m governance.fairness.nba_rates</code>.</Card>;
  }
  const c: Json = d.design_claim;
  const attrs: Json[] = d.attributes ?? [];
  const cur = attrs.find((a) => a.attribute === attr) ?? attrs[0];
  const o: Json = d.overall ?? {};
  const nByDesign = attrs.flatMap((a: Json) => a.groups ?? []).filter((g: Json) => g.status === "review" && g.by_design).length;
  const x = (v: unknown) => (typeof v === "number" ? `${v.toFixed(2)}x` : "n/a");
  return (
    <>
      <StatTiles items={[
        { label: "Design claim", value: c.holds ? "Holds" : "Broken", note: `${n(c.violations)} violations in ${n(c.care_cases)} hardship or vulnerable cases`, status: c.holds ? "ok" : "bad" },
        { label: "Pressure given to them", value: n(c.pressure_among_care), note: c.counterfactual_checked == null ? "not re-decided" : `re-decided at risk ${d.thresholds?.counterfactual_risk?.join(" and ")}: ${n(c.counterfactual_violations)} raised`, status: c.pressure_among_care === 0 ? "ok" : "bad" },
        { label: "Cases decided", value: n(d.meta?.cases), note: `${n(d.meta?.scheduled)} scheduled, plan date ${d.meta?.plan_date}` },
        { label: "Groups flagged", value: String(d.review_items?.length ?? 0), note: `${nByDesign} by design; outside ${d.thresholds?.ratio?.[0]}x to ${d.thresholds?.ratio?.[1]}x of overall`, status: d.review_items?.length ? "warn" : "ok" },
      ]} />
      <p className="mb-3 mt-0 max-w-4xl text-[14px] text-muted">By group, how the current queue treats {n(o.cases)} open cases: how often each group gets a pressure action (reminder or payment link), any contact, no contact, or a route to a person. A group of {d.thresholds?.min_group} cases or more is flagged when a rate is outside {d.thresholds?.ratio?.[0]}x to {d.thresholds?.ratio?.[1]}x of the overall rate (shown as "vs all" for pressure). Overall: pressure {pct(o.pressure_rate)}, contact {pct(o.contact_rate)}, routed {pct(o.routing_rate)}.</p>
      <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1" role="group" aria-label="Protected attribute">
        {attrs.map((a) => (
          <button key={a.attribute} type="button" aria-pressed={cur?.attribute === a.attribute} onClick={() => setAttr(a.attribute)}
            className={`h-9 border-b-2 pb-1 pt-1.5 text-[14.5px] transition-colors ${cur?.attribute === a.attribute ? "border-brand font-semibold text-ink" : "border-transparent font-medium text-ink/70 hover:border-grey-300 hover:text-ink"}`}>
            {ATTR_LABEL[a.attribute] ?? a.attribute}{a.reviews > 0 && <span className="ml-1.5 text-brand-700" aria-label={`${a.reviews} flagged`}>•</span>}
          </button>
        ))}
      </div>
      {cur && (
        <DataTable columns={["Group", "Cases", "Pressure", "vs all", "Contact", "No contact", "Routed", "Mean risk", "Mean value", "Status"]}
          rows={cur.groups.map((r: Json) => [String(r.group).replace(/_/g, " "), n(r.cases), pct(r.pressure_rate), x(r.ratios?.pressure_rate), pct(r.contact_rate), pct(r.no_contact_rate), pct(r.routing_rate), r.mean_risk == null ? "n/a" : r.mean_risk.toFixed(2), r.mean_value.toFixed(0), r.status === "review" && r.by_design ? "by design" : r.status])}
          render={(v, col) => (col === "Status" ? <Badge kind={v === "ok" || v === "by design" ? "ok" : v === "review" ? "danger" : "neutral"}>{v === "ok" ? "OK" : v === "review" ? "Review" : v === "by design" ? "By design" : "Low volume"}</Badge> : String(v ?? "n/a"))} />
      )}
      {cur?.suppressed_groups > 0 && <Footnote>{cur.suppressed_groups} group(s) with fewer than 10 customers are hidden.</Footnote>}
      <Footnote className="mt-4">{d.note}</Footnote>
    </>
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
