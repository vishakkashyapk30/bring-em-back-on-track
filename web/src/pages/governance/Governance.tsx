import { Outlet } from "react-router-dom";

import { RouteTabs } from "@/components/Tabs";

import { SectionTag } from "@/components/SectionTag";

const TABS = [["quality", "Data quality"], ["benchmark", "Benchmark"], ["monitoring", "Monitoring"], ["fairness", "Fairness"], ["audit", "Audit log"], ["contract", "Data contract"]];

export default function Governance() {
  return (
    <>
      <SectionTag as="h1" subtitle="Checks that show the data can be trusted, not just joined together.">Governance</SectionTag>
      <RouteTabs tabs={TABS as [string, string][]} label="Governance" />
      <Outlet />
    </>
  );
}
