import { SectionTag } from "@/components/SectionTag";

import { ListView } from "./hardship/Lists";

/** Team lead: batch approvals (2% sample first), scorecard, roster. TODO(WS-G): approve flow, S6 stress test form. */
export default function Team() {
  return (
    <div className="space-y-10">
      <section><SectionTag as="h1" subtitle="Routine digital reminders, approved by batch after a 2% sample check.">Batch approvals</SectionTag><ListView k="batches" path="/batches" /></section>
      <section><SectionTag subtitle="Causal only where cases were randomly assigned.">Strategy scorecard</SectionTag><ListView k="scorecard" path="/scorecard" /></section>
      <section><SectionTag>Agents</SectionTag><ListView k="agents" path="/team/agents" /></section>
    </div>
  );
}
