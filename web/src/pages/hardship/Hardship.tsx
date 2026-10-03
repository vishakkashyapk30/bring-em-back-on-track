import { NavLink, Outlet } from "react-router-dom";

import { SectionTag } from "@/components/SectionTag";

const TABS = [["board", "Review board"], ["missed", "Missed offers"], ["overrides", "Overrides"], ["simulator/CS-2026-031877", "Plan simulator"]];

export default function Hardship() {
  return (
    <>
      <SectionTag as="h1" subtitle="Hardship and vulnerability: nothing falls off the radar.">Hardship workbench</SectionTag>
      <nav aria-label="Hardship" className="mb-6 flex gap-2">
        {TABS.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => `rounded-[var(--radius-md)] border border-ink px-3 py-1.5 no-underline ${isActive ? "bg-brand text-white" : "bg-white text-ink"}`}>{label}</NavLink>)}
      </nav>
      <Outlet />
    </>
  );
}
