import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { LogOut, Menu, X } from "lucide-react";
import { Suspense, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { post } from "@/api/client";
import { useMe } from "@/api/hooks";
import { NAV } from "@/lib/session";

import { Skeleton } from "./States";

const ROLE_LABEL: Record<string, string> = {
  agent: "Collections agent", hardship_specialist: "Hardship specialist", team_lead: "Team lead",
  analyst: "Strategy analyst", steward: "Data steward",
};
const PUBLIC_LINKS = [["/#how", "How it works"], ["/#layers", "Layers"], ["/#rules", "Ground rules"]];

/** App shell used by every route: a sticky navbar (public links when signed out, role navigation when signed
 * in), a page container with a short enter transition, and a slim footer. */
export function Layout() {
  const me = useMe();
  const nav = useNavigate();
  const qc = useQueryClient();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const signedIn = !!me.data;
  const links = NAV.filter((n) => me.data && n.roles.includes(me.data.role));
  const fullBleed = loc.pathname === "/";

  const signOut = async () => {
    await post("/auth/logout");
    qc.clear();
    nav("/login");
  };

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-grey-300/70 bg-white/85 backdrop-blur-md supports-[backdrop-filter]:bg-white/70">
        <div className="mx-auto flex h-16 w-full max-w-[1400px] items-center gap-6 px-5 md:px-8">
          <Link to={signedIn ? (links[0]?.to ?? "/") : "/"} className="flex shrink-0 items-center gap-2.5 text-ink no-underline hover:no-underline">
            <img src="/favicon.svg" alt="" width={28} height={28} />
            <span className="font-[family-name:var(--font-display)] text-[17px] font-semibold tracking-tight">Collections <span className="text-brand">360</span></span>
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {signedIn
              ? links.map((n) => (
                  <NavLink key={n.to} to={n.to} className={({ isActive }) => clsx(
                    "relative rounded-[var(--radius-md)] px-3 py-2 text-[14px] font-medium no-underline transition-colors hover:no-underline",
                    isActive ? "text-brand" : "text-ink/75 hover:bg-grey-100 hover:text-ink")}>
                    {({ isActive }) => (<>{n.label}{isActive && <span aria-hidden className="absolute inset-x-3 -bottom-[13px] h-0.5 rounded-full bg-brand" />}</>)}
                  </NavLink>))
              : PUBLIC_LINKS.map(([to, label]) => (
                  <a key={to} href={to} className="rounded-[var(--radius-md)] px-3 py-2 text-[14px] font-medium text-ink/75 no-underline transition-colors hover:bg-grey-100 hover:text-ink hover:no-underline">{label}</a>))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {signedIn ? (
              <>
                <div className="hidden text-right leading-tight sm:block">
                  <div className="text-[13px] font-medium">{me.data?.display_name}</div>
                  <div className="text-[12px] text-muted">{ROLE_LABEL[me.data?.role ?? ""]}</div>
                </div>
                <button type="button" onClick={signOut} title="Switch role" className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-grey-300 bg-white px-3 text-[13px] font-medium transition-colors hover:bg-grey-100">
                  <LogOut size={15} aria-hidden /> Switch role
                </button>
              </>
            ) : (
              <Link to="/login" className="inline-flex h-9 items-center rounded-[var(--radius-md)] bg-brand px-4 text-[14px] font-medium text-white no-underline transition-colors hover:bg-brand-700 hover:no-underline">Sign in</Link>
            )}
            <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] border border-grey-300 md:hidden" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        {open && (
          <nav aria-label="Mobile" className="fade-in border-t border-grey-300/70 bg-white px-5 py-2 md:hidden">
            {(signedIn ? links.map((n) => [n.to, n.label]) : PUBLIC_LINKS).map(([to, label]) => (
              <Link key={to} to={to} onClick={() => setOpen(false)} className="block rounded-[var(--radius-md)] px-3 py-2 text-ink no-underline hover:bg-grey-100">{label}</Link>
            ))}
          </nav>
        )}
      </header>

      <main id="main" className={clsx("w-full flex-1", !fullBleed && "mx-auto max-w-[1400px] px-5 py-8 md:px-8")}>
        <Suspense fallback={<div className="mx-auto max-w-[1400px] px-5 py-8 md:px-8"><Skeleton lines={8} /></div>}>
          <div key={loc.pathname} className="page-in"><Outlet /></div>
        </Suspense>
      </main>

      <footer className="border-t border-grey-300/70 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 px-5 py-5 text-[13px] text-muted md:px-8">
          <span>Collections 360 · Team Deep in Debt · CIBC Collections Hackathon</span>
          <span>Synthetic data (Maple Bank, snapshot 28 Sep 2026)</span>
        </div>
      </footer>
    </div>
  );
}
