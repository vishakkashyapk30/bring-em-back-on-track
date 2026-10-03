import type { ReactNode } from "react";

import { Card } from "@/components/Card";
import { SectionTag } from "@/components/SectionTag";

/** The one frame every data visual sits in: the app's Card, a title, one line on what you are looking at, and one
 * line with the takeaway, computed from the same numbers as the picture. */
export function VisualCard({ title, looking, takeaway, actions, children }: {
  title: string; looking: string; takeaway?: string | null; actions?: ReactNode; children: ReactNode;
}) {
  return (
    <Card className="p-5 sm:p-6" role="group" aria-label={title}>
      <SectionTag as="h3" subtitle={looking} actions={actions}>{title}</SectionTag>
      {takeaway && <p className="mb-5 mt-0 border-l-2 border-brand pl-3 text-[15px] font-medium text-ink">{takeaway}</p>}
      {children}
    </Card>
  );
}
