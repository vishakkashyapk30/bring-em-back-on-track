import { Outlet } from "react-router-dom";

import { RouteTabs } from "@/components/Tabs";

import { SectionTag } from "@/components/SectionTag";

const TABS = [["board", "Review board"], ["missed", "Missed offers"], ["overrides", "Overrides"], ["simulator/start", "Plan simulator"]];

export default function Hardship() {
  return (
    <>
      <SectionTag as="h1" subtitle="Keep track of every customer who may be in hardship or vulnerable, so no one is missed.">Hardship workbench</SectionTag>
      <RouteTabs tabs={TABS as [string, string][]} label="Hardship" />
      <Outlet />
    </>
  );
}
