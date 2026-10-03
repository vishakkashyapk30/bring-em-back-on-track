import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BadgeCheck, Brain, Database, FileCheck2, Gavel, Layers, MessageSquareText, ScrollText, ShieldCheck,
  UserCheck, Users,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";

type Summary = {
  golden_customers?: number; crm_records?: number; accounts_linked_pct?: number | null; open_cases?: number;
  issues_found?: number; contract_tests_passed?: number; contract_tests?: number; benchmark_questions?: number;
  benchmark_dev_score?: number; parity_mismatches?: number; text_hardship_accuracy?: number;
};

const fmt = (n?: number | null) => (n == null ? "n/a" : n.toLocaleString());

const LAYERS = [
  { n: "01", icon: Database, title: "Customer 360", text: "Five source systems, each with its own customer key, resolved into one golden record with a match confidence and lineage." },
  { n: "02", icon: MessageSquareText, title: "Collections Ask", text: "Plain-English questions answered from certified metrics or current policy, with the SQL or the sources shown, and refusals for anything off-limits." },
  { n: "03", icon: Layers, title: "Feature store", text: "One definition for every feature, used for both training and live scoring, from structured data and from notes and call transcripts." },
  { n: "04", icon: Brain, title: "Next best action", text: "Policy rules first, then a break-risk model and treatment rules, with a plain-English reason for every recommendation." },
];

const STEPS = [
  { title: "Policy rules", text: "Consent, hours, contact caps, hardship and legal holds filter what's allowed." },
  { title: "Break-risk model", text: "Scores how likely a promise is to break, compared against the bank's own model." },
  { title: "Treatment rules", text: "Picks the action, channel and time window, in a fixed and auditable order." },
  { title: "Plain-English reason", text: "Rules applied, the main drivers, what changed and how fresh the data is." },
  { title: "A person decides", text: "The agent approves, edits or overrides, and every decision is written to the audit log." },
];

const RULES: { icon: typeof ShieldCheck; title: string; text: string }[] = [
  { icon: FileCheck2, title: "A published data contract", text: "Owner, schema, quality rules and allowed uses for the golden C360, tested on every build." },
  { icon: ScrollText, title: "Every decision explained", text: "No recommendation reaches an agent without the rules and evidence behind it." },
  { icon: UserCheck, title: "A person in the loop", text: "Anything that affects a customer can be reviewed, edited or overridden, and it's audited." },
  { icon: Gavel, title: "Fair by construction", text: "No protected attributes in any feature, rule or query; signs of hardship pause pressure." },
];

/** Public landing page (navbar comes from the shared Layout). Headline numbers are live from the pipeline. */
export default function Landing() {
  const s = useQuery({ queryKey: ["public-summary"], queryFn: () => api<Summary>("/public/summary") });
  const d = s.data ?? {};
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-grey-300/60 bg-gradient-to-b from-white to-cream">
        <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-[520px] w-[520px] rounded-full bg-brand/5 blur-3xl" />
        <div className="relative mx-auto grid max-w-[1200px] items-center gap-12 px-5 py-16 md:px-8 lg:grid-cols-[1.05fr_1fr] lg:py-24">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-brand/20 bg-brand-50 px-3 py-1 text-[13px] font-medium text-brand-700">
              <span className="h-1.5 w-1.5 rounded-full bg-brand" /> CIBC Collections Hackathon · Team Deep in Debt
            </span>
            <h1 className="mb-0 mt-5 text-[44px] font-semibold leading-[1.05] tracking-[-0.03em] md:text-[58px]">
              Bring 'em back <br className="hidden sm:block" /><span className="text-brand">on track.</span>
            </h1>
            <p className="mb-0 mt-5 max-w-[540px] text-[17px] leading-relaxed text-muted">
              Every customer in one place, every answer in plain English, and every next step explained and approved by a person.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/login" className="inline-flex h-12 items-center gap-2 rounded-[var(--radius-md)] bg-brand px-6 text-[15px] font-medium text-white no-underline shadow-[var(--shadow-raised)] transition-colors hover:bg-brand-700 hover:no-underline">
                Open the app <ArrowRight size={17} aria-hidden />
              </Link>
              <a href="#how" className="inline-flex h-12 items-center rounded-[var(--radius-md)] border border-grey-300 bg-white px-6 text-[15px] font-medium text-ink no-underline transition-colors hover:bg-grey-100 hover:no-underline">
                How it works
              </a>
            </div>
            <p className="mb-0 mt-6 text-[13px] text-muted">Running on the synthetic Maple Bank release: 1,000,000 customers, snapshot 28 Sep 2026.</p>
          </div>
          <ProductPreview />
        </div>
      </section>

      {/* Live numbers */}
      <section aria-label="Live numbers from the pipeline" className="mx-auto max-w-[1200px] px-5 md:px-8">
        <div className="-mt-px grid gap-px overflow-hidden rounded-b-[var(--radius-lg)] border border-t-0 border-grey-300/60 bg-grey-300/60 sm:grid-cols-2 lg:grid-cols-4">
          <Stat value={fmt(d.golden_customers)} label="golden customers" note={`from ${fmt(d.crm_records)} CRM records`} />
          <Stat value={d.accounts_linked_pct != null ? `${d.accounts_linked_pct}%` : "n/a"} label="accounts linked" note="across five source systems" />
          <Stat value={d.benchmark_dev_score != null ? d.benchmark_dev_score.toFixed(3) : "n/a"} label="benchmark score (dev)" note={`${fmt(d.benchmark_questions)} questions answered`} />
          <Stat value={`${d.contract_tests_passed ?? "n/a"}/${d.contract_tests ?? "n/a"}`} label="contract tests passing" note={`${fmt(d.issues_found)} data issues found and handled`} />
        </div>
      </section>

      {/* Layers */}
      <section id="layers" className="mx-auto max-w-[1200px] scroll-mt-24 px-5 py-20 md:px-8">
        <SectionHead eyebrow="Four layers" title="From scattered systems to an approved next step" text="Each layer builds on the one before it, and the whole chain runs on the real dataset." />
        <div className="grid gap-5 md:grid-cols-2">
          {LAYERS.map(({ n, icon: Icon, title, text }) => (
            <div key={n} className="group rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-6 shadow-[var(--shadow-card)] transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-raised)]">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-[var(--radius-md)] bg-brand-50 text-brand"><Icon size={20} aria-hidden /></span>
                <span className="font-[family-name:var(--font-display)] text-sm font-semibold text-muted">Layer {n}</span>
              </div>
              <h3 className="mb-2 mt-4 text-[19px]">{title}</h3>
              <p className="m-0 text-[15px] leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How a decision is made */}
      <section id="how" className="scroll-mt-16 border-y border-grey-300/60 bg-white">
        <div className="mx-auto max-w-[1200px] px-5 py-20 md:px-8">
          <SectionHead eyebrow="How it works" title="How a next best action is made" text="Rules before models, and a person at the end. Nothing reaches a customer without an explanation and an approval." />
          <ol className="m-0 grid list-none gap-6 p-0 md:grid-cols-5">
            {STEPS.map((st, i) => (
              <li key={st.title} className="relative">
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink font-[family-name:var(--font-display)] text-sm font-semibold text-white">{i + 1}</span>
                  {i < STEPS.length - 1 && <span aria-hidden className="hidden h-px flex-1 bg-grey-300 md:block" />}
                </div>
                <h3 className="mb-1.5 mt-4 text-[16px]">{st.title}</h3>
                <p className="m-0 text-[14px] leading-relaxed text-muted">{st.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Ground rules */}
      <section id="rules" className="mx-auto max-w-[1200px] scroll-mt-24 px-5 py-20 md:px-8">
        <SectionHead eyebrow="Ground rules" title="Built to be trusted" text="The hackathon's ground rules are enforced in code and checked by tests, not left to policy documents." />
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {RULES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-5 shadow-[var(--shadow-card)]">
              <Icon size={22} aria-hidden className="text-brand" />
              <h3 className="mb-1.5 mt-3 text-[16px]">{title}</h3>
              <p className="m-0 text-[14px] leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Call to action */}
      <section className="mx-auto max-w-[1200px] px-5 pb-20 md:px-8">
        <div className="flex flex-col items-start justify-between gap-6 rounded-[var(--radius-xl)] bg-navy px-8 py-10 text-white md:flex-row md:items-center md:px-12">
          <div>
            <h2 className="m-0 text-[26px] text-white">See it as each person who uses it</h2>
            <p className="mb-0 mt-2 max-w-xl text-white/70">Sign in as a collections agent, hardship specialist, team lead, strategy analyst or data steward.</p>
          </div>
          <Link to="/login" className="inline-flex h-12 shrink-0 items-center gap-2 rounded-[var(--radius-md)] bg-white px-6 text-[15px] font-medium text-ink no-underline transition-colors hover:bg-grey-100 hover:no-underline">
            <Users size={17} aria-hidden /> Choose a persona
          </Link>
        </div>
      </section>
    </div>
  );
}

function SectionHead({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <div className="mb-10 max-w-2xl">
      <span className="text-[13px] font-semibold uppercase tracking-[0.08em] text-brand">{eyebrow}</span>
      <h2 className="mb-0 mt-2 text-[32px] leading-tight tracking-[-0.02em]">{title}</h2>
      <p className="mb-0 mt-3 text-[16px] leading-relaxed text-muted">{text}</p>
    </div>
  );
}

function Stat({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div className="bg-white px-6 py-6">
      <div className="font-[family-name:var(--font-display)] text-[30px] font-semibold tracking-tight tabular">{value}</div>
      <div className="text-[14px] font-medium">{label}</div>
      <div className="text-[13px] text-muted">{note}</div>
    </div>
  );
}

function Pill({ children, tone }: { children: ReactNode; tone: "red" | "amber" | "teal" }) {
  const c = { red: "bg-brand-50 text-brand-700", amber: "bg-amber-50 text-amber", teal: "bg-teal-50 text-teal" }[tone];
  return <span className={`rounded-[var(--radius-sm)] px-2 py-0.5 text-[12px] font-medium ${c}`}>{children}</span>;
}

/** Illustrative product card in the hero (not interactive; the real screen is behind sign-in). */
function ProductPreview() {
  return (
    <div aria-hidden className="relative">
      <div className="rounded-[var(--radius-xl)] border border-grey-300/70 bg-white p-6 shadow-[0_24px_60px_-20px_rgb(25_26_35/0.25)]">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-brand text-sm font-semibold text-white">KW</span>
          <div className="min-w-0">
            <div className="font-[family-name:var(--font-display)] text-[17px] font-semibold">Kirsten Wang <span className="font-mono text-[12px] font-normal text-muted">G-KIW6380</span></div>
            <div className="text-[13px] text-muted">Carberry, MB · 6 source systems linked · confidence 1.00</div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5"><Pill tone="red">Bucket 31-60</Pill><Pill tone="amber">Hardship: confirmed</Pill><Pill tone="teal">Consent: call · SMS · email</Pill></div>
        <div className="mt-5 rounded-[var(--radius-lg)] border border-grey-300/70 bg-cream/60 p-4">
          <div className="text-[12px] font-semibold uppercase tracking-wide text-muted">Next best action</div>
          <div className="mt-1 text-[15px] font-semibold">Offer the 3-month reduced payment plan</div>
          <ul className="m-0 mt-3 list-none space-y-1.5 p-0 text-[13.5px]">
            <li className="flex items-center gap-2"><BadgeCheck size={15} className="text-teal" /> Hardship confirmed: pressure actions paused</li>
            <li className="flex items-center gap-2"><BadgeCheck size={15} className="text-teal" /> Eligible for HP-LOAN-RED3 (4 of 4 rules)</li>
            <li className="flex items-center gap-2"><BadgeCheck size={15} className="text-teal" /> Inside permitted hours, 2 of 3 contacts this week</li>
          </ul>
          <div className="mt-4 flex gap-2">
            <span className="inline-flex h-9 items-center rounded-[var(--radius-md)] bg-brand px-4 text-[13px] font-medium text-white">Approve</span>
            <span className="inline-flex h-9 items-center rounded-[var(--radius-md)] border border-grey-300 bg-white px-4 text-[13px] font-medium">Override</span>
          </div>
        </div>
      </div>
      <div className="absolute -bottom-8 -right-4 hidden rounded-[var(--radius-lg)] border border-grey-300/70 bg-white px-4 py-3 shadow-[var(--shadow-raised)] sm:block">
        <div className="text-[12px] text-muted">Ask</div>
        <div className="text-[13.5px] font-medium">"Broken-promise rate by agent site?"</div>
        <div className="mt-0.5 text-[12px] text-teal">SQL shown · 7 rows · 0.1 s</div>
      </div>
    </div>
  );
}
