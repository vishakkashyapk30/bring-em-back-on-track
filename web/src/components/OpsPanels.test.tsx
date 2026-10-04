import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { customerCount, pts, rowChange, topNullChanges, type Proposal } from "@/api/ops";
import StewardDrift from "@/pages/StewardDrift";

import { Playbooks } from "./Playbooks";
import { RadarPanel } from "./RadarPanel";

const DATA: Record<string, unknown> = {
  "/api/playbooks": { pending: 1, items: [{ proposal_id: "P1", playbook: "employer_radar", kind: "contact", title: "Offer early help at EMP-1", detail: "Why.", status: "pending_approval", requires_policy_office_signoff: true, payload: { customer_ids: ["a", "b"] } }] },
  "/api/radar": { summary: "No cluster: none of the 3 employers is unusual.", label: "x", clusters: 0, employers_shown: 3, employers_hidden_small: 9, min_group: 10, known_incidents: [], rows: [{ employer_key: "EMP-1", n_customers: 20, n_payroll_gap: 2, n_new_ei: 0, gap_rate: 0.1, pattern: "none", explained_by_incident: null, known_incidents: [{ event_id: "ECO-0715", description: "" }], industry_naics2: "62" }] },
  "/api/drift": { pending: 1, fixes: [{ fix_id: "F1", table: "contact_history", description: "map channel", diff: "-a\n+b", explanation: "", status: "pending_engineer_approval", applied: false, change: { table: "contact_history", renames: [{ from: "channel", to: "channel_v2" }], type_changes: [], added_columns: ["channel_v2"], removed_columns: [], null_rate_changes: { channel: 0.55 }, row_count_change: -0.7 } }] },
};
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(DATA[url]), { headers: { "content-type": "application/json" } })));
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
});
const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

test("helpers", () => {
  expect(customerCount({ payload: { customer_ids: ["a", "b"] } } as unknown as Proposal)).toBe(2);
  expect(customerCount({ payload: { n_customers: 40 } } as unknown as Proposal)).toBe(40);
  expect(pts(0.551)).toBe("+55.1 pts");
  expect(rowChange(-0.716)).toBe("Rows down 71.6% in the new load");
  expect(topNullChanges({ a: 0.1, b: -0.5, c: 0.2 }, 2).map(([k]) => k)).toEqual(["b", "c"]);
});
test("playbook card shows sign-off badge and approve button", async () => {
  wrap(<Playbooks />);
  expect(await screen.findByText("Needs Policy Office sign-off")).toBeTruthy();
  expect(screen.getAllByRole("button", { name: /Approve and create the batch/ }).length).toBeGreaterThan(0);
});
test("radar says no cluster and carries the honest label", async () => {
  wrap(<RadarPanel />);
  expect(await screen.findByText(/No cluster: none of the 3/)).toBeTruthy();
  expect(screen.getByText(/A radar, not a layoff detector/)).toBeTruthy();
});
test("drift card shows the fix and the approve button", async () => {
  wrap(<StewardDrift />);
  expect(await screen.findByText("Drafted fix")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Approve fix" })).toBeTruthy();
});
