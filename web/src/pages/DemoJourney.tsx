import { ArrowLeft, ArrowRight, CheckCircle2, ExternalLink, Sparkles, UserCheck } from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { useJourney, type Journey, type JourneyStage } from "@/api/assistant";
import { useLogin, useMe } from "@/api/hooks";
import { useAssistant } from "@/components/assistant/AssistantContext";
import { setDemoProgress } from "@/components/assistant/demoProgress";
import { EvidenceView } from "@/components/assistant/EvidenceView";
import { clampStage, isCustomerStage, personaFromParam, progressPct, ROLE_LABEL, stageFromKey, stageLabel } from "@/components/assistant/helpers";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";
import { ErrorState, Skeleton } from "@/components/States";

const IdentityConstellation = lazy(() => import("@/components/visuals/IdentityConstellation").then((m) => ({ default: m.IdentityConstellation })));

const STATUS_TEXT: Record<string, string> = { done: "Ran with real data", needs_approval: "Waits for a person's approval", failed: "Could not run", skipped: "Skipped" };

function Stage({ stage, journey }: { stage: JourneyStage; journey: Journey }) {
  const showWho = journey.customer && isCustomerStage(stage.id);
  return (
    <div className="flex flex-col gap-5">
      <p className="m-0 text-[16px] leading-relaxed">{stage.narrative}</p>
      {stage.summary && (
        <p className="m-0 text-[15px]"><span className="font-semibold">What the system found: </span>{stage.summary}
          {stage.status && <span className="mt-1 block text-[13px] text-muted">({STATUS_TEXT[stage.status] ?? stage.status}{stage.ms ? `, ${stage.ms} ms` : ""})</span>}</p>
      )}
      <EvidenceView evidence={stage.evidence} />
      {showWho && journey.customer && (
        <Suspense fallback={<Skeleton lines={4} />}>
          <section aria-label={`How the records for ${journey.customer.name} were matched`}>
            <h3 className="m-0 mb-2 font-[family-name:var(--font-sans)] text-[13px] font-semibold text-muted">One customer, built from several records</h3>
            <IdentityConstellation goldenId={journey.customer.golden_id} height={320} />
          </section>
        </Suspense>
      )}
      <div className="rounded-[var(--radius-md)] bg-grey-100 p-4">
        <h3 className="m-0 text-[1.0625rem]">Why it matters</h3>
        <p className="m-0 mt-1 text-[15px] leading-relaxed">{stage.why_it_matters}</p>
      </div>
      {stage.human_step && (
        <div role="note" className="rounded-[var(--radius-md)] border border-grey-300/70 border-l-4 border-l-brand bg-white p-4">
          <h3 className="m-0 flex items-center gap-2 text-[1.0625rem]"><UserCheck size={18} aria-hidden className="text-brand" />A person decides here</h3>
          <p className="m-0 mt-1 text-[15px] leading-relaxed">{stage.human_step}</p>
        </div>
      )}
    </div>
  );
}

function Recap({ journey, onAssistant }: { journey: Journey; onAssistant: () => void }) {
  const nav = useNavigate();
  const humans = journey.stages.filter((s) => s.human_step).length;
  return (
    <div className="flex flex-col gap-5">
      <p className="m-0 text-[16px] leading-relaxed">
        That was {journey.stages.length} stages, all on real data{journey.customer ? ` for ${journey.customer.name}` : ""}. The system prepared each one; {humans > 0 ? `${humans} ${humans === 1 ? "step is" : "steps are"} left to a person` : "people stay in charge of every change"}, and every decision is written to the audit log.
      </p>
      <ol className="m-0 list-none space-y-2 p-0">
        {journey.stages.map((s, i) => (
          <li key={s.id} className="flex gap-3 text-[15px]">
            <CheckCircle2 size={18} aria-hidden className="mt-0.5 shrink-0 text-teal" />
            <span><span className="font-semibold">{i + 1}. {s.title}.</span> <span className="text-muted">{s.summary ?? s.why_it_matters}</span></span>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-3">
        <Button variant="primary" className="w-full sm:w-auto" onClick={onAssistant}><Sparkles size={18} aria-hidden />{journey.customer ? "Run the assistant on this customer" : "Run the assistant"}</Button>
        <Button className="w-full sm:w-auto" onClick={() => { setDemoProgress(null); nav("/demo"); }}>Try another persona</Button>
      </div>
    </div>
  );
}

/** One persona's guided tour, a stage at a time, against the live API. */
export default function DemoJourney() {
  const { persona: param } = useParams();
  const persona = personaFromParam(param);
  const me = useMe();
  const login = useLogin();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const { open } = useAssistant();
  const mine = !!persona && me.data?.role === persona;
  const j = useJourney(persona ?? "agent", mine);
  const total = (j.data?.stages.length ?? 0) + 1; // the last stage is the recap
  const [i, setI] = useState(() => Math.max(0, Number(sp.get("stage") ?? 1) - 1));
  const idx = j.data ? clampStage(i, total) : 0;

  useEffect(() => { if (persona && j.data) setDemoProgress({ persona, stage: idx + 1, total }); }, [persona, j.data, idx, total]);
  useEffect(() => { if (j.data) setSp({ stage: String(idx + 1) }, { replace: true }); }, [idx, j.data, setSp]);
  useEffect(() => {
    if (!j.data) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey || t?.closest("input,textarea,select,[role=dialog],[tabindex='0']")) return;
      const n = stageFromKey(e.key, idx, total);
      if (n !== null) { e.preventDefault(); setI(n); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [j.data, idx, total]);

  const stage = j.data?.stages[idx];
  const title = useMemo(() => (idx >= total - 1 ? "Recap" : stage?.title ?? ""), [idx, total, stage]);

  if (!persona) return <Navigate to="/demo" replace />;
  if (me.isLoading) return <Skeleton lines={6} />;
  const label = ROLE_LABEL[persona];
  if (!mine) {
    const other = me.data ? ROLE_LABEL[me.data.role] : null;
    return (
      <div className="mx-auto max-w-[640px] py-6">
        <Card className="flex flex-col gap-3 p-6">
          <h1 className="m-0 text-[1.5rem]">{other ? `Switch to ${label}?` : `Sign in as ${label} to watch`}</h1>
          <p className="m-0 text-[15px] text-muted">{other ? `You are signed in as ${other}. This demo shows the ${label.toLowerCase()}'s day, so we need to switch.` : "The demo uses the live system, so it needs a session. No password is needed."}</p>
          <div className="mt-1 flex flex-wrap gap-3">
            <Button variant="primary" disabled={login.isPending} onClick={() => login.mutate(persona)}>{other ? `Switch to ${label}` : `Sign in as ${label}`}</Button>
            <Link to="/demo" className="inline-flex h-10 items-center px-2 font-semibold text-brand underline-offset-4 hover:underline">Pick someone else</Link>
          </div>
          {login.isError && <p role="alert" className="m-0 text-sm text-danger">We couldn't sign you in. Try again.</p>}
        </Card>
      </div>
    );
  }
  if (j.isLoading) return <div className="py-2"><p role="status" className="mb-3 text-muted">Getting the demo ready from live data...</p><Skeleton lines={8} /></div>;
  if (j.isError || !j.data) return <ErrorState title="The demo could not load" detail="The live data did not answer. Nothing was changed. Reload the page to try again." />;

  const journey = j.data;
  const last = idx === total - 1;
  const openScreen = () => { if (stage) nav(stage.screen); };
  return (
    <>
      <SectionTag as="h1" subtitle={`${label} demo. ${journey.intro}${journey.customer ? ` The customer is ${journey.customer.name}.` : " Totals only, no individual customers."}`}>{journey.title}</SectionTag>

      <div className="mb-5">
        <div className="mb-1.5 flex items-baseline justify-between gap-3">
          <span className="whitespace-nowrap text-[15px] font-semibold tabular-nums">{stageLabel(idx, total)}</span>
          <span className="hidden text-[13px] text-muted sm:inline">Use the left and right arrow keys to move</span>
        </div>
        <div role="progressbar" aria-label="Demo progress" aria-valuemin={1} aria-valuemax={total} aria-valuenow={idx + 1} aria-valuetext={stageLabel(idx, total)} className="h-1.5 overflow-hidden rounded-full bg-grey-300">
          <div className="h-full rounded-full bg-brand transition-[width] duration-300" style={{ width: `${progressPct(idx, total)}%` }} />
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[250px_minmax(0,1fr)]">
        <nav aria-label="Demo stages" className="hidden lg:block">
          <ol className="m-0 list-none space-y-1 p-0">
            {[...journey.stages.map((s) => s.title), "Recap"].map((t, n) => (
              <li key={t + n}>
                <button type="button" onClick={() => setI(n)} aria-current={n === idx ? "step" : undefined}
                  className={`flex w-full items-baseline gap-2 rounded-[var(--radius-md)] px-3 py-2 text-left text-[14.5px] transition-colors ${n === idx ? "bg-white font-semibold text-brand shadow-[var(--shadow-card)] ring-1 ring-grey-300" : "text-ink/80 hover:bg-grey-100"}`}>
                  <span className="w-5 shrink-0 tabular-nums text-muted">{n + 1}</span><span>{t}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <Card className="min-w-0 p-5 md:p-7" aria-labelledby="stage-h">
          <p role="status" className="sr-only">{stageLabel(idx, total)}: {title}</p>
          <h2 id="stage-h" className="m-0 mb-4 text-[1.25rem]">{title}</h2>
          {last ? <Recap journey={journey} onAssistant={() => open(journey.customer ? { caseId: journey.customer.case_id, goldenId: journey.customer.golden_id, label: `${journey.customer.name} (${journey.customer.case_id})` } : undefined)} />
            : stage && <Stage key={stage.id} stage={stage} journey={journey} />}
          <div className="mt-7 flex flex-wrap items-center gap-3 border-t border-grey-300/70 pt-5">
            <Button onClick={() => setI(idx - 1)} className="w-24" disabled={idx === 0}><ArrowLeft size={16} aria-hidden />Back</Button>
            {!last && <Button variant="primary" className="w-24" onClick={() => setI(idx + 1)}>Next<ArrowRight size={16} aria-hidden /></Button>}
            {!last && stage && <Button onClick={openScreen} className="sm:ml-auto"><ExternalLink size={16} aria-hidden />Open the real screen</Button>}
          </div>
        </Card>
      </div>
    </>
  );
}
