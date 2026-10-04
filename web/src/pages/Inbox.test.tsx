import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import Inbox from "./Inbox";

const item = (id: string, over: Partial<Record<string, unknown>> = {}) => ({
  id, type: "hardship_flags", title: `J. Maddox: possible hardship (${id})`, reason: "Raised by the model. Confirm or clear it.",
  age_days: 19, age_label: "19 days overdue", due: "2026-09-09", overdue: true, link: "/hardship/board", subject_kind: "customer", subject_id: "G-1", ...over,
});
const INBOX = {
  role: "hardship_specialist", total: 12, as_of: "2026-09-28", note: null, top: [item("C1")],
  groups: [
    { type: "hardship_flags", label: "Possible hardship to confirm or clear", why: "Each flag needs a person within 5 business days.", count: 10, items: [item("C1"), item("C2", { overdue: false, age_label: "due in 2 days" })], link: "/hardship/board", link_label: "Open the review board", informational: false },
    { type: "missed_offers", label: "Missed hardship offers", why: "Nobody offered help yet.", count: 2, items: [item("C3", { type: "missed_offers", overdue: false, age_label: "waiting 3 days", link: "/hardship/missed" })], link: "/hardship/missed", link_label: "Open missed offers", informational: false },
    { type: "vulnerability_reviews", label: "Vulnerability reviews due", why: "None due.", count: 0, items: [], link: "/hardship/board", link_label: "Open the review board", informational: false },
  ],
  not_available: [{ source: "Plan offers above an agent's level", reason: "There is no sign-off store." }],
};
let body: unknown = INBOX;
beforeEach(() => {
  body = INBOX;
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } })));
});
const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Inbox /></MemoryRouter></QueryClientProvider>);

test("groups items by type with what, why, age and a link to the real screen", async () => {
  wrap();
  const g = await screen.findByRole("region", { name: /Possible hardship to confirm or clear/ });
  expect(within(g).getByRole("link", { name: "J. Maddox: possible hardship (C1)" }).getAttribute("href")).toBe("/hardship/board");
  expect(within(g).getAllByText("Raised by the model. Confirm or clear it.").length).toBe(2);
  expect(within(g).getByText("19 days overdue")).toBeTruthy();
  expect(within(g).getByText("Overdue:")).toBeTruthy(); // overdue is said in words, not only in colour
  expect(within(g).getByText(/8 more not listed here/)).toBeTruthy();
  expect(within(g).getAllByRole("link", { name: /Open the review board/ })[0].getAttribute("href")).toBe("/hardship/board");
  expect(screen.getByRole("region", { name: /Missed hardship offers/ })).toBeTruthy();
  // empty groups are not shown; the missing source is explained
  expect(screen.queryByRole("region", { name: /Vulnerability reviews due/ })).toBeNull();
  expect(screen.getByText(/There is no sign-off store/)).toBeTruthy();
  // the page approves nothing itself
  expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
});

test("says so when nothing is waiting", async () => {
  body = { ...INBOX, total: 0, top: [], groups: [], not_available: [] };
  wrap();
  expect(await screen.findByText("You're all caught up.")).toBeTruthy();
});
