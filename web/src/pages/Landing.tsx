import { ArrowUpRight, Eye, FileCheck2, Scale, UserCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { Card } from "@/components/Card";
import { ExplainAccordion } from "@/components/ExplainAccordion";
import { KpiBand } from "@/components/KpiBand";
import { SectionTag } from "@/components/SectionTag";

const SOURCES = ["cards", "loans", "deposits", "CRM", "collections", "contacts", "notes", "transcripts", "bureau"];
const MODULES: { title: string; to: string; variant: "grey" | "brand" | "dark" }[] = [
  { title: "Collections 360", to: "/queue", variant: "grey" },
  { title: "Collections Ask", to: "/ask", variant: "brand" },
  { title: "Feature store", to: "/features", variant: "dark" },
  { title: "Next best action", to: "/queue", variant: "grey" },
  { title: "Hardship workbench", to: "/hardship", variant: "brand" },
  { title: "Governance", to: "/governance", variant: "dark" },
];

/** Story page for the demo opening. Copy and KPI numbers are placeholders. */
export default function Landing() {
  return (
    <div className="mx-auto max-w-[1240px] space-y-20 px-6 py-10">
      <section className="grid items-center gap-10 md:grid-cols-2">
        <div>
          <h1 className="m-0 text-5xl font-medium leading-tight md:text-[60px]">Bring 'em back on track</h1>
          <p className="text-lg">Every customer in one place, every answer in plain English, every next step explained and approved by a person.</p>
          <Link to="/login" className="inline-block rounded-[var(--radius-md)] bg-ink px-6 py-4 text-white no-underline shadow-[var(--shadow-hard)]">Open today's queue</Link>
        </div>
        <Card landing variant="grey" hard aria-hidden className="grid aspect-[4/3] place-items-center text-6xl font-medium text-brand">C360</Card>
      </section>

      <section aria-label="Sources" className="flex flex-wrap justify-between gap-4 text-muted">
        <span className="font-medium text-ink">9 sources → 1 golden ID</span>
        {SOURCES.map((s) => <span key={s}>{s}</span>)}
      </section>

      <section>
        <SectionTag subtitle="Four layers on one trusted customer record, with a person approving every step that reaches a customer.">Modules</SectionTag>
        <div className="grid gap-8 md:grid-cols-2">
          {MODULES.map((m) => (
            <Card key={m.title} landing hard variant={m.variant} className="flex min-h-[220px] flex-col justify-between">
              <h3 className={`m-0 inline-block self-start rounded px-2 text-3xl font-medium ${m.variant === "brand" ? "bg-white text-ink" : "bg-brand text-white"}`}>{m.title}</h3>
              <Link to={m.to} className={`inline-flex items-center gap-2 no-underline ${m.variant === "grey" ? "text-ink" : "text-white"}`}>
                <span className={`grid h-10 w-10 place-items-center rounded-full ${m.variant === "dark" ? "bg-white text-ink" : "bg-ink text-white"}`}><ArrowUpRight size={20} /></span> Open
              </Link>
            </Card>
          ))}
        </div>
      </section>

      <KpiBand items={[
        { label: "30-day cure rate", value: "TBC", delta: "+2 pts target", definition: "cure_flag and days_to_cure <= 30, weekly cohort" },
        { label: "PTP kept rate", value: "TBC", delta: "leading indicator" },
        { label: "Estimated value", value: "~CAD 0.7M / yr", delta: "recompute at H3" },
      ]} />

      <section>
        <SectionTag subtitle="From raw files to an approved action.">How it works</SectionTag>
        <ExplainAccordion items={[
          { title: "Data Product Factory", body: "Bronze → silver → gold. Identity resolution links every source key to one golden ID, under a published data contract." },
          { title: "Insight and NLP", body: "Plain-English questions become editable chips, certified metrics and guarded SQL, with the working shown and refusals for anything off-limits." },
          { title: "Feature store", body: "One definition per feature for training and live scoring, built from SQL, text and voice, with parity checks." },
          { title: "Next best action", body: "Policy rules first, then a break-risk model, a treatment ladder and a capacity allocator. Every decision is explained and approved by a person." },
        ]} />
      </section>

      <section>
        <SectionTag>Ground rules</SectionTag>
        <div className="grid gap-6 md:grid-cols-2">
          {[[FileCheck2, "Publish a data contract", "Owner, schema, quality rules, allowed uses."],
            [Eye, "Explain every decision", "Rules applied, model evidence, what changed."],
            [UserCheck, "Keep a human in the loop", "Approve, edit or override anything."],
            [Scale, "Treat customers fairly", "No protected attributes; hardship pauses pressure."]].map(([Icon, t, d]) => {
            const I = Icon as typeof Eye;
            return (
              <Card key={t as string} className="flex gap-4">
                <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-brand text-white"><I aria-hidden /></span>
                <div><h3 className="m-0">{t as string}</h3><p className="m-0 text-muted">{d as string}</p></div>
              </Card>
            );
          })}
        </div>
      </section>
    </div>
  );
}
