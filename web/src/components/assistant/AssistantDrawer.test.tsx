import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import type { AssistantRun } from "@/api/assistant";

import { AssistantProvider, useAssistant } from "./AssistantContext";
import { AssistantDrawer } from "./AssistantDrawer";

const RUN: AssistantRun = {
  persona: "agent", goal: "briefing", mode_used: "rules", mode_note: null, audit_id: 118,
  plan: [{ id: "s1", tool: "queue_summary", title: "Read today's queue", why: "Start from your work." }],
  steps: [
    { id: "s1", tool: "queue_summary", title: "Read today's queue", status: "done", ms: 12, summary: "your 261 cases", evidence: { kv: [["In scope", "261"]] } },
    { id: "s2", tool: "hardship_board", title: "Open the board", status: "failed", ms: 1, summary: "That is not assigned to you." },
  ],
  findings: ["58 with a hardship flag"],
  proposals: [{ id: "p1", title: "Approve the referral", detail: "Hand over.", kind: "nba", href: "/customers/G-1", requires_role: "agent" }],
  summary: "261 cases, 58 in hardship.",
};
const mutate = vi.fn((_b: unknown, o: { onSuccess: (r: AssistantRun) => void }) => o.onSuccess(RUN));
vi.mock("@/api/assistant", () => ({
  useAssistantRun: () => ({ mutate, isPending: false, isError: false, error: null }),
  useAssistantSuggestions: () => ({ isLoading: false, isError: false, data: { persona: "agent", briefing: { label: "Brief me", goal: "Brief me on today" }, goals: [{ label: "Review my next case", goal: "Review my next case" }] } }),
}));
vi.mock("@/api/hooks", () => ({
  useMe: () => ({ data: { role: "agent", display_name: "Demo Agent" } }),
  useHealth: () => ({ isLoading: false, data: { llm: { available: false, reason: "No model is configured." } } }),
}));

function Opener() { const a = useAssistant(); return <button onClick={() => a.open()}>open</button>; }

test("drawer runs the briefing, shows steps in order with text status, and closes on Escape", async () => {
  render(<MemoryRouter initialEntries={["/customers/G-1"]}><AssistantProvider><Opener /><AssistantDrawer /></AssistantProvider></MemoryRouter>);
  fireEvent.click(screen.getByText("open"));
  expect(screen.getByRole("dialog", { name: "Assistant" })).toBeInTheDocument();
  expect(screen.getByText(/Demo Agent, Collections agent/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Run my briefing/ }));
  expect(mutate.mock.calls[0][0]).toMatchObject({ golden_id: "G-1", mode: "rules" });
  expect(screen.getByText("Run by rules")).toBeInTheDocument();
  expect(await screen.findByText("Recorded in the audit log,", { exact: false })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("Could not run")).toBeInTheDocument(), { timeout: 2000 });
  expect(screen.getByText("Done")).toBeInTheDocument();
  expect(await screen.findByText("What I found")).toBeInTheDocument();
  expect(screen.getByText("Nothing is sent or changed until you approve it there.")).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
});
