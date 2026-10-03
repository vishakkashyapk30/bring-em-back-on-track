import { Badge, type BadgeKind } from "@/components/Badge";
import { Card } from "@/components/Card";
import { ChipEditor } from "@/components/ChipEditor";
import { ExplainAccordion } from "@/components/ExplainAccordion";
import { FreshnessPill } from "@/components/FreshnessPill";
import { KpiBand } from "@/components/KpiBand";
import { SectionTag } from "@/components/SectionTag";
import { SqlBlock } from "@/components/SqlBlock";
import { EmptyState, ErrorState, RefusalCard, Skeleton } from "@/components/States";

const KINDS: BadgeKind[] = ["risk", "bucket", "consent", "hardship", "vulnerable", "dispute", "llm", "sql", "causal", "observed", "model-estimate", "ok", "danger"];

/** /dev/kit: every component and state in one place. */
export default function DevKit() {
  return (
    <div className="space-y-10">
      <SectionTag as="h1" subtitle="Tokens, components and states.">Component kit</SectionTag>
      <div className="flex flex-wrap gap-2">{KINDS.map((k) => <Badge key={k} kind={k}>{k}</Badge>)}</div>
      <div className="grid gap-4 md:grid-cols-4">{(["grey", "brand", "dark", "plain"] as const).map((v) => <Card key={v} variant={v} hard>{v} card</Card>)}</div>
      <KpiBand items={[{ label: "Cure rate", value: "41%", delta: "+2.1 pts" }, { label: "PTP kept", value: "63%" }, { label: "At risk", value: "$12,990" }]} />
      <ExplainAccordion items={[{ title: "Rules applied", body: "…" }, { title: "Model evidence", body: "…" }]} />
      <ChipEditor chips={[{ key: "a", label: "open promises" }, { key: "b", label: "due 28 Sep - 4 Oct" }]} onRemove={() => {}} />
      <SqlBlock sql={"SELECT 1\nLIMIT 1000"} source="semantic" />
      <FreshnessPill asOf="2026-09-28T06:00:00-04:00" hours={3} />
      <div className="grid gap-4 md:grid-cols-2"><Skeleton /><EmptyState title="No rows" /><ErrorState detail="Example error" /><RefusalCard reason="gender_code is a protected attribute." /></div>
    </div>
  );
}
