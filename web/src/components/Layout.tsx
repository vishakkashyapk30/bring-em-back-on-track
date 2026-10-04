import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Menu, X } from "lucide-react";
import { Suspense, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { post } from "@/api/client";
import { useMe } from "@/api/hooks";
import { NAV } from "@/lib/session";

import { AssistantDrawer, AssistantLauncher } from "./assistant/AssistantDrawer";
import { AssistantProvider } from "./assistant/AssistantContext";
import { setDemoProgress } from "./assistant/demoProgress";
import { DemoBanner } from "./assistant/DemoBanner";
import { ROLE_LABEL } from "./assistant/helpers";

import { Skeleton } from "./States";

const PUBLIC_LINKS = [["/demo", "Demo"], ["/#how", "How it works"], ["/#layers", "Layers"], ["/#rules", "Ground rules"]];

/** App shell used by every route: a sticky navbar (public links when signed out, role navigation when signed
 * in), a page container with a short enter transition, and a slim footer. */
export function Layout() {
  const me = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const signedIn = !!me.data;
  const links = [...NAV.filter((n) => me.data && n.roles.includes(me.data.role)), ...(me.data ? [{ to: `/demo/${me.data.role}`, label: "My demo", roles: [] }] : [])];
  const fullBleed = loc.pathname === "/";

  const signOut = async () => {
    await post("/auth/logout");
    qc.clear();
    setDemoProgress(null);
    nav("/login");
  };

  return (
    <AssistantProvider>
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-grey-300/70 bg-white/85 backdrop-blur-md supports-[backdrop-filter]:bg-white/70">
        <div className="mx-auto flex h-[72px] w-full max-w-[1680px] items-center gap-3 px-4 sm:gap-8 sm:px-5 md:px-10">
          <Link to="/" aria-label="back-on-track.ai, home page" className="flex shrink-0 items-center gap-2.5 text-ink no-underline hover:no-underline">
            <img src="/favicon.svg" alt="" width={28} height={28} />
            <span className="font-[family-name:var(--font-display)] text-[22px] sm:text-[26px] font-semibold leading-none">back-on-track<span className="text-brand">.ai</span></span>
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {signedIn
              ? links.map((n) => (
                  <NavLink key={n.to} to={n.to} className={({ isActive }) => clsx(
                    "relative rounded-[var(--radius-md)] px-4 py-2.5 text-[16px] font-medium no-underline transition-colors hover:no-underline",
                    isActive ? "text-brand" : "text-ink/75 hover:bg-grey-100 hover:text-ink")}>
                    {({ isActive }) => (<>{n.label}{isActive && <span aria-hidden className="absolute inset-x-4 -bottom-[13px] h-0.5 rounded-full bg-brand" />}</>)}
                  </NavLink>))
              : PUBLIC_LINKS.map(([to, label]) => (
                  <Link key={to} to={to} className="rounded-[var(--radius-md)] px-4 py-2.5 text-[16px] font-medium text-ink/75 no-underline transition-colors hover:bg-grey-100 hover:text-ink hover:no-underline">{label}</Link>))}
          </nav>

          <div className="ml-auto flex items-center">
            {signedIn ? (
              <>
                <AssistantLauncher />
                <div className="hidden leading-tight sm:block">
                  <div className="text-[15px] font-semibold">{me.data?.display_name}</div>
                  <div className="text-[13px] text-muted">{ROLE_LABEL[me.data?.role ?? ""]}</div>
                </div>
                <button type="button" onClick={signOut} className="ml-3 hidden whitespace-nowrap border-l border-grey-300 py-2 pl-4 text-[14.5px] font-semibold text-brand underline-offset-4 hover:underline sm:ml-6 sm:inline sm:pl-6">
                  Switch role
                </button>
              </>
            ) : (
              <Link to="/login" className="inline-flex h-10 items-center whitespace-nowrap rounded-[var(--radius-md)] bg-brand px-4 sm:px-5 text-[15px] font-medium text-white no-underline transition-colors hover:bg-brand-700 hover:no-underline">Sign in</Link>
            )}
            <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] md:hidden" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        {open && (
          <nav aria-label="Mobile" className="fade-in border-t border-grey-300/70 bg-white px-5 py-2 md:hidden">
            {(signedIn ? links.map((n) => [n.to, n.label]) : PUBLIC_LINKS).map(([to, label]) => (
              <Link key={to} to={to} onClick={() => setOpen(false)} className="block rounded-[var(--radius-md)] px-3 py-2 text-ink no-underline hover:bg-grey-100">{label}</Link>
            ))}
            {signedIn && (
              <button type="button" onClick={() => { setOpen(false); signOut(); }} className="block w-full rounded-[var(--radius-md)] px-3 py-2 text-left font-semibold text-brand hover:bg-grey-100 sm:hidden">
                Switch role
              </button>
            )}
          </nav>
        )}
      </header>
      {signedIn && <DemoBanner />}

      <main id="main" className={clsx("w-full flex-1", !fullBleed && "mx-auto max-w-[1680px] px-5 py-8 md:px-10")}>
        <Suspense fallback={<div className="mx-auto max-w-[1680px] px-5 py-8 md:px-10"><Skeleton lines={8} /></div>}>
          <div key={loc.pathname} className="page-in"><Outlet /></div>
        </Suspense>
      </main>

      <footer className="border-t border-grey-300/70 bg-white">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-2 px-5 py-5 text-[13px] text-muted md:px-10">
          <span>back-on-track.ai</span>
          <span>Every customer here is synthetic (Maple Bank, data as of 28 Sep 2026).</span>
        </div>
      </footer>
      {signedIn && <AssistantDrawer key={me.data?.role} />}
    </div>
    </AssistantProvider>
  );
}
