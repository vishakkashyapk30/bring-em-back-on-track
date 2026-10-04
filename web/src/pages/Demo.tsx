import { ArrowRight, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useLogin } from "@/api/hooks";
import { demoPath } from "@/components/assistant/helpers";
import { DEMO_PERSONAS } from "@/components/assistant/personas";
import { SectionTag } from "@/components/SectionTag";

/** Demo picker. Shows no data: only the five personas, a one-sentence story and the stages each will see. */
export default function Demo() {
  const login = useLogin();
  const nav = useNavigate();
  return (
    <>
      <SectionTag as="h1" subtitle="Pick a persona and we sign you in, no password. Every customer here is synthetic. Nothing is sent to anyone.">Watch a day in the product</SectionTag>
      <ul className="m-0 list-none divide-y divide-grey-300/70 overflow-hidden rounded-[var(--radius-lg)] border border-grey-300/70 bg-white p-0">
        {DEMO_PERSONAS.map(({ role, title, icon: Icon, story, sees }) => {
          const busy = login.isPending && login.variables === role;
          return (
            <li key={role} className="grid items-center gap-x-8 gap-y-3 px-5 py-5 transition-colors hover:bg-cream/60 md:grid-cols-[260px_minmax(0,1fr)_170px]">
              <div className="flex items-center gap-3">
                <Icon size={20} aria-hidden className="shrink-0 text-muted" />
                <h2 className="m-0 text-[1.25rem] leading-tight">{title}</h2>
              </div>
              <div className="min-w-0">
                <p className="m-0 text-[15px] leading-snug">{story}</p>
                <p className="m-0 mt-1 text-[13.5px] text-muted"><span className="font-semibold">What you will see: </span>{sees}</p>
              </div>
              <div className="flex flex-col gap-2">
              <button type="button" disabled={login.isPending} aria-label={`Start the ${title} demo`}
                onClick={() => login.mutate(role, { onSuccess: () => nav(demoPath(role)) })}
                className="inline-flex h-10 w-full items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] border border-grey-300 bg-white px-4 text-[15px] font-medium text-ink transition-colors hover:border-ink/40 hover:bg-grey-100 focus-visible:shadow-[var(--shadow-focus)] disabled:opacity-70">
                Start demo
                {busy ? <Loader2 size={16} className="animate-spin" aria-label="Signing in" /> : <ArrowRight size={16} aria-hidden />}
              </button>
              <button type="button" disabled={login.isPending} aria-label={`Track one subject as the ${title}`}
                onClick={() => login.mutate(role, { onSuccess: () => nav("/track?start=suggested") })}
                className="inline-flex h-10 w-full items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] px-4 text-[14.5px] font-medium text-brand transition-colors hover:bg-brand-50 focus-visible:shadow-[var(--shadow-focus)] disabled:opacity-70">
                Track one over time
              </button>
              </div>
            </li>
          );
        })}
      </ul>
      {login.isError && <p role="alert" className="mt-4 text-sm text-danger">We couldn't sign you in. Check that the API is running and try again.</p>}
    </>
  );
}
