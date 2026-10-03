import { NavLink, Outlet } from "react-router-dom";

import { SectionTag } from "@/components/SectionTag";

const TABS = [["quality", "Data quality"], ["benchmark", "Benchmark"], ["monitoring", "Monitoring"], ["fairness", "Fairness"], ["audit", "Audit log"], ["contract", "Data contract"]];

export default function Governance() {
  return (
    <>
      <SectionTag as="h1" subtitle="Trusted, not just joined.">Governance</SectionTag>
      <nav aria-label="Governance" className="mb-6 flex flex-wrap gap-2">
        {TABS.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => `rounded-[var(--radius-md)] border border-ink px-3 py-1.5 no-underline ${isActive ? "bg-brand text-white" : "bg-white text-ink"}`}>{label}</NavLink>)}
      </nav>
      <Outlet />
    </>
  );
}
