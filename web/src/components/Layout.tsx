import clsx from "clsx";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useMe } from "@/api/hooks";
import { post } from "@/api/client";
import { NAV } from "@/lib/session";

/** App shell: role-filtered top nav, role switcher, dark rounded footer (Figma footer). */
export function Layout() {
  const me = useMe();
  const nav = useNavigate();
  const role = me.data?.role;
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only">Skip to content</a>
      <header className="flex flex-wrap items-center gap-6 border-b border-grey-300 bg-white px-6 py-3">
        <NavLink to="/" className="flex items-center gap-2 text-xl font-medium text-ink no-underline">
          <img src="/favicon.svg" alt="" width={28} height={28} /> Collections <span className="text-brand">360</span>
        </NavLink>
        <nav aria-label="Main" className="flex flex-wrap gap-1">
          {NAV.filter((n) => role && n.roles.includes(role)).map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => clsx("rounded-[var(--radius-md)] px-3 py-1.5 no-underline", isActive ? "bg-brand text-white" : "text-ink hover:bg-grey-100")}>{n.label}</NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {me.data && <span>{me.data.display_name} · <b>{me.data.role.replace("_", " ")}</b></span>}
          <button type="button" onClick={async () => { await post("/auth/logout"); nav("/login"); }} className="rounded-[var(--radius-md)] border border-ink bg-white px-3 py-1">Switch role</button>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-8"><Outlet /></main>
      <footer className="rounded-t-[var(--radius-xl)] bg-navy px-10 py-6 text-sm text-white/80">
        Collections 360 · Team Deep in Debt · <span className="text-gold">Synthetic data</span> · CIBC Collections Hackathon
      </footer>
    </div>
  );
}
