import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import { useMe } from "@/api/hooks";
import { NAV } from "@/lib/session";

type Summary = {
  golden_customers?: number; crm_records?: number; accounts_linked_pct?: number | null; open_cases?: number;
  issues_found?: number; contract_tests_passed?: number; contract_tests?: number; benchmark_questions?: number;
  benchmark_dev_score?: number; parity_mismatches?: number; text_hardship_accuracy?: number;
};

// The globe and its map data load after the page has painted, so they never delay the headline or the buttons.
const Globe = lazy(() => import("@/components/Globe").then((m) => ({ default: m.Globe })));

function GlobePlaceholder() {
  return (
    <div aria-hidden className="mx-auto grid aspect-square w-full max-w-[600px] place-items-center">
      <div className="aspect-square w-[80%] rounded-full bg-gradient-to-br from-white to-grey-100 shadow-[0_0_60px_rgb(167_31_62/0.14)]" />
    </div>
  );
}

function LazyGlobe() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number };
    const go = () => setReady(true);
    if (w.requestIdleCallback) { const id = w.requestIdleCallback(go, { timeout: 800 }); return () => (window as never as { cancelIdleCallback: (n: number) => void }).cancelIdleCallback(id); }
    const t = setTimeout(go, 300);
    return () => clearTimeout(t);
  }, []);
  return ready ? <Suspense fallback={<GlobePlaceholder />}><Globe /></Suspense> : <GlobePlaceholder />;
}

const fmt = (n?: number | null) => (n == null ? "n/a" : n.toLocaleString());

const LAYERS = [
  { n: 1, title: "Customer 360", text: "One customer can appear in five different systems, each with its own ID. We match them into a single record per person and show how sure we are about each match." },
  { n: 2, title: "Collections Ask", text: "Ask a question in plain English. You get the answer along with the SQL or the policy it came from, and anything off-limits is politely refused." },
  { n: 3, title: "Feature store", text: "Each signal we use, like days past due or the tone of a call, is defined once and used the same way in training and in live scoring." },
  { n: 4, title: "Next best action", text: "Policy rules come first. Then a model estimates how likely a promise is to break, and treatment rules pick the action. Every suggestion comes with its reason." },
];

const STEPS = [
  { title: "Policy rules", text: "Consent, calling hours, contact limits, hardship and legal holds decide what we may do." },
  { title: "Break-risk model", text: "Estimates how likely a promise to pay is to be broken, and compares that with the bank's own score." },
  { title: "Treatment rules", text: "Pick the action, the channel and the time of day, always in the same order so it can be audited." },
  { title: "The reason", text: "Says which rules applied, what mattered most, what changed and how fresh the data is." },
  { title: "A person decides", text: "The agent approves, edits or overrides. Every decision goes into the audit log." },
];

const RULES = [
  { title: "A published data contract", text: "Who owns the data, its schema, its quality rules and what it may be used for. We test it on every build." },
  { title: "Every decision explained", text: "No suggestion reaches an agent without the rules and evidence behind it." },
  { title: "A person stays in charge", text: "Anything that affects a customer can be reviewed, edited or overridden, and it's recorded." },
  { title: "Fair by design", text: "No protected attributes in any feature, rule or query. Signs of hardship pause the pressure." },
];

/** Public landing page (navbar comes from the shared Layout). Headline numbers are live from the pipeline. */
export default function Landing() {
  const s = useQuery({ queryKey: ["public-summary"], queryFn: () => api<Summary>("/public/summary") });
  const me = useMe();
  const d = s.data ?? {};
  const home = me.data ? NAV.find((n) => n.roles.includes(me.data!.role))?.to ?? "/queue" : "/login";
  return (
    <div>
      {/* Hero */}
      <section className="border-b border-grey-300/70">
        <div className="mx-auto grid max-w-[1680px] items-center gap-10 px-5 py-8 md:px-10 lg:grid-cols-[1fr_0.9fr] lg:py-6">
          <div>
            <h1 className="m-0 text-[48px] leading-[1.05] md:text-[64px]">
              Help customers get back <span className="text-brand">on track.</span>
            </h1>
            <p className="mb-0 mt-5 max-w-[520px] text-[18px] leading-relaxed text-muted">
              Back-on-Track.ai brings each customer's accounts into one place, answers your questions in plain English, and suggests a next step for a person to approve.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
              <Link to={home} className="inline-flex h-12 items-center gap-2 rounded-[var(--radius-md)] bg-brand px-6 text-[16px] font-semibold text-white no-underline transition-colors hover:bg-brand-700 hover:no-underline">
                {me.data ? "Go to your workspace" : "Open the app"} <ArrowRight size={17} aria-hidden />
              </Link>
              <a href="#how" className="text-[16px] font-semibold text-ink underline decoration-brand decoration-2 underline-offset-[6px] hover:no-underline">
                See how it works
              </a>
            </div>
          </div>
          <figure className="m-0">
            <LazyGlobe />
          </figure>
        </div>
      </section>

      {/* Live numbers */}
      <section aria-label="Live numbers from the pipeline" className="border-b border-grey-300/70 bg-white">
        <div className="mx-auto grid max-w-[1680px] gap-y-8 px-5 py-12 sm:grid-cols-2 md:px-10 lg:grid-cols-4">
        <Stat value={fmt(d.golden_customers)} label="customers, one record each" note={`merged from ${fmt(d.crm_records)} CRM records`} />
        <Stat value={d.accounts_linked_pct != null ? `${d.accounts_linked_pct}%` : "n/a"} label="of accounts linked to a customer" note="across five source systems" />
        <Stat value={d.benchmark_dev_score != null ? d.benchmark_dev_score.toFixed(3) : "n/a"} label="score on the practice questions" note={`${fmt(d.benchmark_questions)} questions answered`} />
        <Stat value={`${d.contract_tests_passed ?? "n/a"} of ${d.contract_tests ?? "n/a"}`} label="data contract tests passing" note={`${fmt(d.issues_found)} data issues found and handled`} />
        </div>
      </section>

      {/* Layers */}
      <section id="layers" className="mx-auto max-w-[1680px] scroll-mt-24 px-5 py-16 md:px-10">
        <SectionHead title="Four layers, from scattered systems to a next step" text="Each layer builds on the one before it, and the whole chain runs on the full hackathon dataset." />
        <div className="grid gap-x-10 gap-y-10 md:grid-cols-2 xl:grid-cols-4">
          {LAYERS.map(({ n, title, text }) => (
            <div key={n} className="border-t-2 border-ink pt-4">
              <div className="text-[14px] font-semibold text-brand">Layer {n}</div>
              <h3 className="mb-2 mt-1 text-[26px]">{title}</h3>
              <p className="m-0 text-[16px] leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How a decision is made */}
      <section id="how" className="scroll-mt-16 border-y border-grey-300/70 bg-white">
        <div className="mx-auto max-w-[1680px] px-5 py-16 md:px-10">
          <SectionHead title="How a next best action is made" text="Rules first, a person last. Nothing reaches a customer without a reason and an approval." />
          <ol className="m-0 grid list-none gap-8 p-0 md:grid-cols-5">
            {STEPS.map((st, i) => (
              <li key={st.title}>
                <div aria-hidden className="font-[family-name:var(--font-display)] text-[40px] font-semibold leading-none text-brand">{i + 1}</div>
                <h3 className="mb-1.5 mt-3 text-[20px]">{st.title}</h3>
                <p className="m-0 text-[15px] leading-relaxed text-muted">{st.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Ground rules */}
      <section id="rules" className="mx-auto max-w-[1680px] scroll-mt-24 px-5 py-16 md:px-10">
        <SectionHead title="Built to be trusted" text="The hackathon's ground rules are enforced in code and checked by tests, not just written in a document." />
        <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
          {RULES.map(({ title, text }) => (
            <div key={title} className="border-t-2 border-ink pt-4">
              <h3 className="mb-1.5 mt-0 text-[20px]">{title}</h3>
              <p className="m-0 text-[15px] leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Call to action */}
      <section className="border-t border-grey-300/70 bg-white">
       <div className="mx-auto max-w-[1680px] px-5 py-16 md:px-10">
        <div className="flex flex-col items-start justify-between gap-6 rounded-[var(--radius-md)] bg-navy px-8 py-10 text-white md:flex-row md:items-center md:px-12">
          <div>
            <h2 className="m-0 text-[32px] text-white">Try it as each of the five people who use it</h2>
            <p className="mb-0 mt-2 max-w-xl text-[16px] text-white/75">Pick a role: collections agent, hardship specialist, team lead, strategy analyst or data steward. Each one sees different screens.</p>
          </div>
          <Link to="/login" className="inline-flex h-12 shrink-0 items-center gap-2 rounded-[var(--radius-md)] bg-white px-6 text-[16px] font-semibold text-ink no-underline transition-colors hover:bg-grey-100 hover:no-underline">
            Choose a role <ArrowRight size={17} aria-hidden />
          </Link>
        </div>
       </div>
      </section>
    </div>
  );
}

function SectionHead({ title, text }: { title: string; text: string }) {
  return (
    <div className="mb-10 max-w-2xl">
      <h2 className="m-0 text-[38px] leading-tight">{title}</h2>
      <p className="mb-0 mt-3 text-[17px] leading-relaxed text-muted">{text}</p>
    </div>
  );
}

function Stat({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div>
      <div className="font-[family-name:var(--font-display)] text-[44px] font-semibold leading-none tabular">{value}</div>
      <div className="mt-2 text-[15px] font-semibold">{label}</div>
      <div className="text-[14px] text-muted">{note}</div>
    </div>
  );
}
