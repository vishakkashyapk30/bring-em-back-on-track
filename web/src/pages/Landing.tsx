import { ArrowRight } from "lucide-react";
import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";

import { useMe } from "@/api/hooks";
import type { Session } from "@/api/types";
import { usePublicSummary, type PublicSummary } from "@/api/visuals";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { Skeleton } from "@/components/States";
import { DecisionFlow } from "@/components/visuals/DecisionFlow";
import { Hero } from "@/components/visuals/Hero";
import { NAV } from "@/lib/session";

// The map and the constellation are their own chunks, so the greeting and buttons paint first.
const CanadaRiskMap = lazy(() => import("@/components/visuals/CanadaRiskMap").then((m) => ({ default: m.CanadaRiskMap })));
const IdentityConstellation = lazy(() => import("@/components/visuals/IdentityConstellation").then((m) => ({ default: m.IdentityConstellation })));

const LAYERS = [
  { title: "Customer 360", text: "One customer can appear in five different systems, each with its own ID. We match them into a single record per person and show how sure we are about each match." },
  { title: "Collections Ask", text: "Ask a question in plain English. You get the answer along with the SQL or the policy it came from, and anything off-limits is politely refused." },
  { title: "Feature store", text: "Each signal we use, like days past due or the tone of a call, is defined once and used the same way in training and in live scoring." },
  { title: "Next best action", text: "Policy rules come first. Then a model estimates how likely a promise is to break, and treatment rules pick the action. Every suggestion comes with its reason." },
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

export const ROLE_LABEL: Record<string, string> = {
  agent: "Collections agent", hardship_specialist: "Hardship specialist", team_lead: "Team lead", analyst: "Strategy analyst", steward: "Data steward",
};
export const ROLE_BLURB: Record<string, string> = {
  agent: "Work today's queue: review each suggested next step, then approve, edit or override it.",
  hardship_specialist: "Pick up customers who show signs of hardship and choose the right kind of support.",
  team_lead: "See how your team is doing, review overrides and watch where promises are breaking.",
  analyst: "Ask questions in plain English, explore the signals we use and compare strategies.",
  steward: "Check data quality, review identity matches and keep the governance record.",
};

/** The first screen a persona lands on, from the same list the navigation uses. */
export const firstScreen = (role: Session["role"]): string => NAV.find((n) => n.roles.includes(role))?.to ?? "/queue";

/** "/": the globe and the story for visitors, a personal home with the live data for signed-in people.
 * Nothing from the pipeline is requested or drawn until someone is signed in. */
export default function Landing() {
  const me = useMe();
  if (me.isLoading) return <div className="mx-auto max-w-[1680px] px-5 py-12 md:px-10"><Skeleton lines={5} /></div>;
  if (me.data) return <SignedInHome me={me.data} />;
  return <SignedOutLanding />;
}

function SignedOutLanding() {
  return (
    <div>
      <Hero />
      <Section id="how" title="How a next best action is made" text="Rules first, a person last. Nothing reaches a customer without a reason and an approval." cols="lg:grid-cols-5" items={STEPS} label="Step" />
      <Section id="layers" tinted title="Four layers, from scattered systems to a next step" text="Each layer builds on the one before it." cols="md:grid-cols-2 xl:grid-cols-4" items={LAYERS} label="Layer" />
      <Section id="rules" title="Built to be trusted" text="The ground rules are enforced in code and checked by tests, not just written in a document." cols="sm:grid-cols-2 xl:grid-cols-4" items={RULES} />
      <section className="border-t border-grey-300/70 bg-white">
        <div className="mx-auto flex max-w-[1680px] flex-col items-start justify-between gap-5 px-5 py-12 md:flex-row md:items-center md:px-10">
          <div>
            <h2 className="m-0 text-[1.5rem]">Try it as each of the five people who use it</h2>
            <p className="mb-0 mt-1 max-w-2xl text-[14.5px] text-muted">Pick a role: collections agent, hardship specialist, team lead, strategy analyst or data steward. Each one sees different screens.</p>
          </div>
          <Link to="/login" className="inline-flex h-12 shrink-0 items-center gap-2 rounded-[var(--radius-md)] bg-brand px-6 text-[16px] font-semibold text-white no-underline transition-colors hover:bg-brand-700 hover:no-underline">
            Sign in as a persona <ArrowRight size={17} aria-hidden />
          </Link>
        </div>
      </section>
    </div>
  );
}

function Section({ id, title, text, items, cols, label, tinted = false }: {
  id: string; title: string; text: string; items: { title: string; text: string }[]; cols: string; label?: string; tinted?: boolean;
}) {
  return (
    <section id={id} className={`scroll-mt-20 border-t border-grey-300/70 ${tinted ? "bg-white" : ""}`}>
      <div className="mx-auto max-w-[1680px] px-5 py-14 md:px-10">
        <SectionTag subtitle={text}>{title}</SectionTag>
        <ol className={`m-0 mt-6 grid list-none gap-4 p-0 ${cols}`}>
          {items.map((it, i) => (
            <li key={it.title}>
              <Card variant={tinted ? "grey" : "plain"} className="h-full">
                {label && <div className="text-[13px] font-semibold text-muted">{label} {i + 1}</div>}
                <h3 className="mb-1.5 mt-1 text-[1.25rem]">{it.title}</h3>
                <p className="m-0 text-[14.5px] leading-relaxed text-muted">{it.text}</p>
              </Card>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const LINK_BTN = "inline-flex h-12 items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] border px-6 text-base font-medium no-underline transition-colors hover:no-underline";
const fmt = (n?: number | null) => (n == null ? "n/a" : n.toLocaleString("en-CA"));

/** The few numbers that frame the pictures below. Read from the same endpoint the rest of the home uses. */
export function statItems(s: PublicSummary): { value: string; label: string }[] {
  return [
    { value: fmt(s.golden_customers), label: "customers, one record each" },
    { value: fmt(s.open_cases), label: "customers with an open case" },
    { value: s.accounts_linked_pct != null ? `${s.accounts_linked_pct}%` : "n/a", label: "of accounts linked across systems" },
    { value: `${s.contract_tests_passed ?? "n/a"} of ${s.contract_tests ?? "n/a"}`, label: "data tests passing" },
  ];
}

function SignedInHome({ me }: { me: Session }) {
  const summary = usePublicSummary(true);
  const name = me.display_name || me.user_id;
  return (
    <div className="mx-auto max-w-[1680px] px-5 py-10 md:px-10">
      <SectionTag as="h1" subtitle={<>{ROLE_LABEL[me.role] ?? me.role}. {ROLE_BLURB[me.role]}</>}
        actions={<div className="flex flex-wrap gap-2">
          <Link to={`/demo/${me.role}`} className={`${LINK_BTN} border-grey-300 bg-white text-ink hover:border-ink/40 hover:bg-grey-100`}>Watch my demo</Link>
          <Link to={firstScreen(me.role)} className={`${LINK_BTN} border-transparent bg-brand text-white hover:bg-brand-700`}>Open my workspace <ArrowRight size={17} aria-hidden /></Link>
        </div>}>
        Hello, {name}
      </SectionTag>

      {summary.data && (
        <Card className="mb-8 grid gap-y-5 p-5 sm:grid-cols-2 lg:grid-cols-4 lg:divide-x lg:divide-grey-300/70" role="group" aria-label="Live numbers from the pipeline">
          {statItems(summary.data).map((s) => (
            <div key={s.label} className="lg:px-6 lg:first:pl-0">
              <div className="font-[family-name:var(--font-display)] text-[2rem] font-semibold leading-none tabular">{s.value}</div>
              <div className="mt-1.5 text-[14px] text-muted">{s.label}</div>
            </div>
          ))}
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="min-w-0 lg:col-span-7">
          <Suspense fallback={<div role="status" aria-label="Loading" className="skeleton h-[520px] w-full rounded-[var(--radius-lg)]" />}><CanadaRiskMap /></Suspense>
        </div>
        <div className="min-w-0 lg:col-span-5">
          <Suspense fallback={<div role="status" aria-label="Loading" className="skeleton h-[400px] w-full rounded-[var(--radius-lg)]" />}>
            <IdentityConstellation goldenId="sample" height={440} framed />
          </Suspense>
        </div>
        <div className="min-w-0 lg:col-span-12"><DecisionFlow /></div>
      </div>
    </div>
  );
}
